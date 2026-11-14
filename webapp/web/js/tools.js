// Pointer + keyboard interaction on the stage, and the actions the rest of the UI calls.

import { session, signIn } from './session.js';
import { S, bus } from './state.js';
import { store } from './store.js';
import { editablePath, lonLatToScreen, screenBox, itemKeys, pulseAt } from './overlay.js';
import { nearestOnSegment } from './geo.js';
import { clamp, isTyping } from './util.js';
import { t } from './i18n.js';
import { toast } from './ui.js';

let view, stage;
const pointers = new Map();
let gesture = null;
let pinch = null;
let spaceDown = false;
let lastTap = { t: 0, x: 0, y: 0 };
let dragSeq = 0;
let outsideToastAt = 0;

export const TOOLS = ['select', 'place', 'path', 'note', 'measure'];
const TOOL_KEYS = { KeyV: 'select', KeyP: 'place', KeyD: 'path', KeyN: 'note', KeyM: 'measure' };

export function initTools(v, stageEl) {
  view = v;
  stage = stageEl;
  stage.addEventListener('pointerdown', onDown);
  stage.addEventListener('pointermove', onMove);
  stage.addEventListener('pointerup', onUp);
  stage.addEventListener('pointercancel', onCancel);
  stage.addEventListener('pointerleave', () => { if (!gesture) { S.cursor = null; setHover(null); bus.emit('cursor'); } });
  stage.addEventListener('wheel', onWheel, { passive: false });
  stage.addEventListener('dblclick', (e) => e.preventDefault());
  stage.addEventListener('contextmenu', (e) => { if (gesture || S.draft) e.preventDefault(); });
  document.addEventListener('keydown', onKey);
  // the map shows a focus frame only when it was reached with Tab, not every time a shortcut is pressed
  let tabAt = 0;
  document.addEventListener('keydown', (e) => { if (e.key === 'Tab') tabAt = performance.now(); }, true);
  stage.addEventListener('focus', () => { stage.classList.toggle('kbd-focus', performance.now() - tabAt < 250); });
  stage.addEventListener('blur', () => stage.classList.remove('kbd-focus'));
  stage.addEventListener('pointerdown', () => stage.classList.remove('kbd-focus'), true);
  document.addEventListener('keyup', (e) => { if (e.code === 'Space') { spaceDown = false; updateCursor(); } });
  window.addEventListener('blur', () => { spaceDown = false; });
  try { S.kind = localStorage.getItem('studio.kind') || 'trail'; } catch { S.kind = 'trail'; }
  if (!['trail', 'road', 'route'].includes(S.kind)) S.kind = 'trail';
}

// ---------------------------------------------------------------- hit testing

function hitTest(sx, sy, touch) {
  if (!S.proj) return null;
  const tol = touch ? 20 : 9;
  const p = [sx, sy];
  const ed = editablePath();

  if (ed) {
    let best = null;
    ed.coords.forEach((c, i) => {
      const [hx, hy] = lonLatToScreen(c);
      const d = Math.hypot(hx - sx, hy - sy);
      if (d <= tol + 2 && (!best || d < best.d)) best = { type: 'handle', index: i, d, draft: ed.draft };
    });
    if (best) return best;
  }

  if (S.tool === 'select') {
    // places and notes: last drawn is on top
    const keys = itemKeys().reverse();
    for (const key of keys) {
      const b = screenBox(key);
      const pad = touch ? 10 : 4;
      if (b && sx >= b.x - pad && sx <= b.x + b.w + pad && sy >= b.y - pad && sy <= b.y + b.h + pad) {
        const [type, ...rest] = key.split(':');
        return { type, id: rest.join(':') };
      }
    }
  }

  if (ed && ed.coords.length >= 2) {
    const seg = nearestSegment(ed.coords, p);
    if (seg && seg.d <= tol) return { type: 'segment', index: seg.index, sx: seg.x, sy: seg.y, draft: ed.draft };
  }

  if (S.tool === 'select') {
    let best = null;
    for (const path of store.doc.paths) {
      const seg = nearestSegment(path.coords, p);
      if (seg && seg.d <= tol && (!best || seg.d < best.d)) best = { type: 'path', id: path.id, d: seg.d };
    }
    if (best) return best;
  }

  if (S.tool === 'select' || S.tool === 'path') {
    let best = null;
    for (const lm of S.side.landmarks || []) {
      const [lx, ly] = view.toScreen(lm.x, lm.y);
      const r = S.tool === 'path' ? 14 : Math.max((lm.r || 40) * view.k, touch ? 22 : 18);
      const d = Math.hypot(lx - sx, ly - sy);
      if (d <= r && (!best || d < best.d)) best = { type: 'landmark', id: lm.id, d };
    }
    if (best) return best;
  }
  return null;
}

function nearestSegment(coords, p) {
  let best = null;
  let prev = lonLatToScreen(coords[0]);
  for (let i = 1; i < coords.length; i += 1) {
    const cur = lonLatToScreen(coords[i]);
    const n = nearestOnSegment(p, prev, cur);
    if (!best || n.d < best.d) best = { ...n, index: i - 1 };
    prev = cur;
  }
  return best;
}

function sameHover(a, b) {
  if (!a || !b) return a === b;
  return a.type === b.type && a.id === b.id && a.index === b.index && a.sx === b.sx && a.sy === b.sy;
}

function setHover(hit) {
  if (sameHover(S.hover, hit)) return;
  const artChange = (S.hover?.type === 'path') || (hit?.type === 'path');
  S.hover = hit;
  bus.emit(artChange ? 'hoverArt' : 'hover');
  updateCursor();
}

function updateCursor(sx, sy) {
  let c = 'default';
  if (!S.proj) c = 'default';
  else if (gesture?.kind === 'pan' || pinch) c = 'grabbing';
  else if (spaceDown) c = 'grab';
  else if (S.tool === 'select') {
    const hv = S.hover;
    if (!hv) c = 'grab';
    else if (hv.type === 'handle') c = 'move';
    else if (hv.type === 'segment') c = 'copy';
    else if ((hv.type === 'place' || hv.type === 'note') && S.sel?.type === hv.type && S.sel.id === hv.id) c = 'move';
    else c = 'pointer';
  } else if (S.hover?.type === 'handle') c = 'move';
  else if (S.hover?.type === 'segment') c = 'copy';
  else {
    c = 'crosshair';
    if (sx != null && !inFrameScreen(sx, sy)) c = 'not-allowed';
  }
  if (stage.dataset.cursor !== c) stage.dataset.cursor = c;
}

function inFrameScreen(sx, sy) {
  const [ix, iy] = view.toImage(sx, sy);
  return S.proj.inFrame(ix, iy);
}

function screenToLonLat(sx, sy, clampFrame = false) {
  let [ix, iy] = view.toImage(sx, sy);
  if (clampFrame) [ix, iy] = S.proj.clampToFrame(ix, iy);
  return S.proj.toLonLat(ix, iy);
}

// ---------------------------------------------------------------- pointer

function onDown(e) {
  if (e.target.closest('[data-stage-ui]')) return;
  if (e.pointerType === 'mouse' && e.button !== 0 && e.button !== 1) return;
  if (!S.proj) return;
  try { stage.setPointerCapture(e.pointerId); } catch { /* synthetic event */ }
  if (document.activeElement !== stage) stage.focus({ preventScroll: true });
  if (e.button === 1) e.preventDefault();
  const [sx, sy] = view.local(e);
  pointers.set(e.pointerId, { sx, sy });
  view.stop();
  if (pointers.size === 2) {
    if (gesture?.moved) store.seal();
    gesture = null;
    const [a, b] = [...pointers.values()];
    pinch = { d: Math.hypot(a.sx - b.sx, a.sy - b.sy) || 1, cx: (a.sx + b.sx) / 2, cy: (a.sy + b.sy) / 2 };
    setHover(null);
    return;
  }
  if (pointers.size > 2) return;
  const touch = e.pointerType !== 'mouse';
  const pan = e.button === 1 || spaceDown;
  gesture = {
    pid: e.pointerId, sx0: sx, sy0: sy, px: sx, py: sy, moved: false, touch, pan,
    hit: pan ? null : hitTest(sx, sy, touch), kind: 'tap',
  };
}

function onMove(e) {
  const [sx, sy] = view.local(e);
  if (pointers.has(e.pointerId)) pointers.set(e.pointerId, { sx, sy });
  if (pinch) {
    if (pointers.size < 2) return;
    const [a, b] = [...pointers.values()];
    const d = Math.hypot(a.sx - b.sx, a.sy - b.sy) || 1, cx = (a.sx + b.sx) / 2, cy = (a.sy + b.sy) / 2;
    const k = clamp(view.k * (d / pinch.d), view.minK, view.maxK);
    const [ix, iy] = view.toImage(pinch.cx, pinch.cy);
    view.set(cx - ix * k, cy - iy * k, k);
    pinch = { d, cx, cy };
    return;
  }
  const g = gesture;
  if (!g || g.pid !== e.pointerId) {
    if (e.pointerType === 'mouse' && S.proj) {
      S.cursor = [sx, sy];
      setHover(hitTest(sx, sy, false));
      updateCursor(sx, sy);
      if (S.draft || S.measure.length) bus.emit('cursor');
    }
    return;
  }
  if (!g.moved) {
    if (Math.hypot(sx - g.sx0, sy - g.sy0) < (g.touch ? 9 : 4)) return;
    g.moved = true;
    beginDrag(g);
  }
  const dx = sx - g.px, dy = sy - g.py;
  g.px = sx; g.py = sy;
  if (g.kind === 'pan') { view.panBy(dx, dy); return; }
  const lonlat = screenToLonLat(sx + g.offX, sy + g.offY, true);
  if (g.kind === 'vertex') {
    if (g.draft) { S.draft.coords[g.index] = lonlat; bus.emit('draft'); }
    else store.mutate((doc) => { const p = doc.paths.find((r) => r.id === g.id); if (p) p.coords[g.index] = lonlat; }, g.key);
  } else if (g.kind === 'item') {
    store.mutate((doc) => {
      const it = doc[g.type === 'place' ? 'places' : 'notes'].find((r) => r.id === g.id);
      if (it) { it.lon = lonlat[0]; it.lat = lonlat[1]; }
    }, g.key);
  }
}

function beginDrag(g) {
  const hit = g.hit;
  g.offX = 0; g.offY = 0;
  g.key = `drag:${dragSeq += 1}`;
  const ed = editablePath();
  if (g.pan || !hit) { g.kind = 'pan'; }
  else if (hit.type === 'handle' && ed) {
    g.kind = 'vertex'; g.index = hit.index; g.draft = ed.draft; g.id = ed.id;
    const [hx, hy] = lonLatToScreen(ed.coords[hit.index]);
    g.offX = hx - g.sx0; g.offY = hy - g.sy0;
    if (!ed.draft) { S.vertex = hit.index; bus.emit('sel'); }
  } else if (hit.type === 'segment' && ed) {
    const lonlat = screenToLonLat(hit.sx, hit.sy, true);
    g.kind = 'vertex'; g.index = hit.index + 1; g.draft = ed.draft; g.id = ed.id;
    g.offX = hit.sx - g.sx0; g.offY = hit.sy - g.sy0;
    if (ed.draft) { S.draft.coords.splice(g.index, 0, lonlat); bus.emit('draft'); }
    else {
      store.mutate((doc) => { doc.paths.find((r) => r.id === ed.id)?.coords.splice(g.index, 0, lonlat); }, g.key);
      S.vertex = g.index; bus.emit('sel');
    }
  } else if ((hit.type === 'place' || hit.type === 'note') && S.tool === 'select') {
    g.kind = 'item'; g.type = hit.type; g.id = hit.id;
    const it = store.get(hit.type, hit.id);
    const [ax, ay] = lonLatToScreen([it.lon, it.lat]);
    g.offX = ax - g.sx0; g.offY = ay - g.sy0;
    if (!(S.sel?.type === hit.type && S.sel.id === hit.id)) select(hit.type, hit.id, { quiet: true });
  } else { g.kind = 'pan'; }
  setHover(null);
  updateCursor();
}

function onUp(e) {
  pointers.delete(e.pointerId);
  try { stage.releasePointerCapture(e.pointerId); } catch { /* fine */ }
  if (pinch) { if (pointers.size < 2) { pinch = null; pointers.clear(); updateCursor(); } return; }
  const g = gesture;
  if (!g || g.pid !== e.pointerId) return;
  gesture = null;
  if (g.moved) {
    if (g.kind !== 'pan') store.seal();
    updateCursor();
    return;
  }
  const [sx, sy] = view.local(e);
  const now = performance.now();
  const double = now - lastTap.t < 340 && Math.hypot(sx - lastTap.x, sy - lastTap.y) < 10;
  lastTap = double ? { t: 0, x: 0, y: 0 } : { t: now, x: sx, y: sy };
  tap(g, sx, sy, double);
  if (!g.touch) { setHover(hitTest(sx, sy, false)); updateCursor(sx, sy); }
}

function onCancel(e) {
  pointers.delete(e.pointerId);
  if (pointers.size < 2) pinch = null;
  if (gesture?.pid === e.pointerId) { if (gesture.moved && gesture.kind !== 'pan') store.seal(); gesture = null; }
  updateCursor();
}

function onWheel(e) {
  if (!S.proj || e.target.closest('[data-stage-ui]')) return;
  e.preventDefault();
  const [sx, sy] = view.local(e);
  const dy = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1);
  view.zoomBy(Math.exp(-dy * (e.ctrlKey ? 0.01 : 0.0016)), sx, sy, !e.ctrlKey);
}

function warnOutside() {
  const now = performance.now();
  if (now - outsideToastAt > 2500) { outsideToastAt = now; toast(t('hud.outside')); }
}

function tap(g, sx, sy, double) {
  const hit = g.hit;
  const inside = inFrameScreen(sx, sy);
  if (S.tool === 'select') {
    if (!hit) { deselect(); closeLandmark(); return; }
    if (hit.type === 'handle') { S.vertex = S.vertex === hit.index ? null : hit.index; bus.emit('sel'); return; }
    if (hit.type === 'segment') {
      const lonlat = screenToLonLat(hit.sx, hit.sy, true);
      const id = S.sel.id;
      store.mutate((doc) => { doc.paths.find((r) => r.id === id)?.coords.splice(hit.index + 1, 0, lonlat); });
      S.vertex = hit.index + 1; bus.emit('sel');
      return;
    }
    if (hit.type === 'landmark') { openLandmark(hit.id); return; }
    select(hit.type, hit.id);
    return;
  }
  if (S.tool === 'place' || S.tool === 'note') {
    if (!inside) { warnOutside(); return; }
    const lonlat = screenToLonLat(sx, sy);
    if (S.tool === 'place') createPlace(lonlat); else createNote(lonlat);
    return;
  }
  if (S.tool === 'path') {
    if (double && S.draft) { finishDraft(); return; }
    if (hit?.type === 'handle' && S.draft) {
      if (hit.index === S.draft.coords.length - 1 && S.draft.coords.length >= 2) finishDraft();
      return;
    }
    if (hit?.type === 'segment' && S.draft) {
      S.draft.coords.splice(hit.index + 1, 0, screenToLonLat(hit.sx, hit.sy, true));
      bus.emit('draft');
      return;
    }
    let lonlat;
    if (hit?.type === 'landmark') {
      lonlat = landmarkLonLat(S.side.landmarks.find((l) => l.id === hit.id));
    } else {
      if (!inside) { warnOutside(); return; }
      lonlat = screenToLonLat(sx, sy);
    }
    if (!S.draft) S.draft = { coords: [], kind: S.kind };
    S.draft.coords.push(lonlat);
    bus.emit('draft');
    return;
  }
  if (S.tool === 'measure') {
    if (double) { S.measureDone = true; bus.emit('measure'); return; }
    if (!inside) { warnOutside(); return; }
    if (S.measureDone) { S.measure = []; S.measureDone = false; }
    S.measure.push(screenToLonLat(sx, sy));
    bus.emit('measure');
  }
}

// ---------------------------------------------------------------- keyboard

function onKey(e) {
  if (e.defaultPrevented) return;
  const typing = isTyping(e.target);
  const mod = e.ctrlKey || e.metaKey;
  if (mod && !e.altKey && (e.code === 'KeyZ' || e.code === 'KeyY')) {
    if (typing) return; // let the field undo its own text
    e.preventDefault();
    if (e.code === 'KeyY' || e.shiftKey) store.redo(); else store.undo();
    return;
  }
  if (typing) {
    if (e.key === 'Escape') { e.target.blur(); stage.focus({ preventScroll: true }); e.preventDefault(); }
    return;
  }
  if (mod || e.altKey) return;
  if (e.target.closest?.('.menu')) return;
  const onMap = e.target === document.body || e.target === stage || e.target === document.documentElement;

  if (TOOL_KEYS[e.code]) { setTool(TOOL_KEYS[e.code]); e.preventDefault(); return; }
  switch (e.key) {
    case 'Escape': escape(); break;
    case 'Enter':
      if (!onMap) return;
      if (S.tool === 'path' && S.draft) finishDraft();
      else if (S.tool === 'measure' && S.measure.length) { S.measureDone = true; bus.emit('measure'); }
      else return;
      break;
    case 'Backspace':
    case 'Delete':
      if (!onMap && e.target.closest?.('button, a, [role="tab"]') && S.tool === 'select') return;
      if (!removeByKey()) return;
      break;
    case 'ArrowLeft': if (!onMap) return; view.nudge(e.shiftKey ? 240 : 80, 0); break;
    case 'ArrowRight': if (!onMap) return; view.nudge(e.shiftKey ? -240 : -80, 0); break;
    case 'ArrowUp': if (!onMap) return; view.nudge(0, e.shiftKey ? 240 : 80); break;
    case 'ArrowDown': if (!onMap) return; view.nudge(0, e.shiftKey ? -240 : -80); break;
    case '+': case '=': view.zoomBy(1.35); break;
    case '-': case '_': view.zoomBy(1 / 1.35); break;
    case '0': view.fit(); break;
    case '1': view.zoomTo(1); break;
    case ' ':
      if (!onMap) return;
      spaceDown = true; updateCursor();
      break;
    default: return;
  }
  e.preventDefault();
}

function escape() {
  if (S.draft) { cancelDraft(); return; }
  if (S.measure.length) { S.measure = []; S.measureDone = false; bus.emit('measure'); return; }
  if (S.tool !== 'select') { setTool('select'); return; }
  if (S.lm) { closeLandmark(); return; }
  if (S.vertex != null) { S.vertex = null; bus.emit('sel'); return; }
  deselect();
}

function removeByKey() {
  if (S.tool === 'path' && S.draft) {
    S.draft.coords.pop();
    if (!S.draft.coords.length) S.draft = null;
    bus.emit('draft');
    return true;
  }
  if (S.tool === 'measure' && S.measure.length) { S.measure.pop(); S.measureDone = false; bus.emit('measure'); return true; }
  if (S.tool === 'select' && S.sel) {
    if (S.sel.type === 'path' && S.vertex != null) {
      const p = store.get('path', S.sel.id);
      if (p && p.coords.length > 2) {
        const i = S.vertex;
        store.mutate((doc) => { doc.paths.find((r) => r.id === p.id).coords.splice(i, 1); });
        S.vertex = null; bus.emit('sel');
        return true;
      }
    }
    deleteItem(S.sel.type, S.sel.id);
    return true;
  }
  return false;
}

// ---------------------------------------------------------------- actions

export function setTool(tool) {
  if (!TOOLS.includes(tool) || tool === S.tool) return;
  if (!session.me && (tool === 'place' || tool === 'path' || tool === 'note')) {
    toast(t('auth.toAdd'), { action: t('auth.signIn'), onAction: () => signIn() });
    return;
  }
  if (S.tool === 'path' && S.draft) { if (S.draft.coords.length >= 2) commitDraft(false); else { S.draft = null; bus.emit('draft'); } }
  if (S.tool === 'measure') { S.measure = []; S.measureDone = false; bus.emit('measure'); }
  S.tool = tool;
  S.hover = null;
  if (tool !== 'select') { S.vertex = null; S.lm = null; if (S.sel) S.sel = null; bus.emit('sel'); }
  bus.emit('tool');
  updateCursor();
}

export function select(type, id, opts = {}) {
  const changed = !(S.sel?.type === type && S.sel.id === id);
  S.sel = { type, id };
  if (changed) S.vertex = null;
  if (S.lm) { S.lm = null; }
  S.focusEditor = !!opts.focus;
  bus.emit('sel');
  if (!opts.quiet) bus.emit('reveal', { type, id, focus: !!opts.focus });
  if (opts.fly) flyToItem(type, id);
}

export function deselect() {
  if (!S.sel && S.vertex == null) return;
  S.sel = null; S.vertex = null;
  bus.emit('sel');
}

export function createPlace(lonlat) {
  const id = store.nextId('place');
  let icon = null;
  try { icon = localStorage.getItem('studio.icon') || null; } catch { /* private mode */ }
  if (icon && !iconExists(icon)) icon = null;
  store.mutate((doc) => { doc.places.push({ id, name: '', note: '', lon: lonlat[0], lat: lonlat[1], icon }); });
  setTool('select');
  select('place', id, { focus: true });
}

function iconExists(ref) {
  const [kind, stem] = ref.split('/');
  if (kind === 'library') return !!S.server?.icons.library.some((it) => it.id === stem);
  if (kind === 'landmark') return !!S.place?.landmark_icons.includes(stem);
  return false;
}

export function createNote(lonlat) {
  const id = store.nextId('note');
  store.mutate((doc) => { doc.notes.push({ id, text: '', lon: lonlat[0], lat: lonlat[1] }); });
  setTool('select');
  select('note', id, { focus: true });
}

export function startPathAt(lonlat) {
  closeLandmark();
  deselect();
  setTool('path');
  S.draft = { coords: [lonlat], kind: S.kind };
  bus.emit('draft');
  stage.focus({ preventScroll: true });
}

function commitDraft(focus) {
  const d = S.draft;
  S.draft = null;
  if (!d || d.coords.length < 2) { bus.emit('draft'); return null; }
  const id = store.nextId('path');
  store.mutate((doc) => { doc.paths.push({ id, name: '', kind: d.kind, coords: d.coords }); });
  bus.emit('draft');
  if (focus != null) {
    S.tool = 'select'; bus.emit('tool'); updateCursor();
    select('path', id, { focus });
  }
  return id;
}

export function finishDraft() {
  if (!S.draft) return;
  // a double click lands twice on the same spot: drop the duplicate
  const c = S.draft.coords;
  if (c.length >= 2) {
    const a = lonLatToScreen(c[c.length - 1]), b = lonLatToScreen(c[c.length - 2]);
    if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 3) c.pop();
  }
  if (c.length < 2) { cancelDraft(); return; }
  commitDraft(true);
}

export function cancelDraft() {
  S.draft = null;
  bus.emit('draft');
}

export function setDraftKind(kind) {
  S.kind = kind;
  try { localStorage.setItem('studio.kind', kind); } catch { /* private mode */ }
  if (S.draft) { S.draft.kind = kind; bus.emit('draft'); }
}

export function clearMeasure() {
  S.measure = []; S.measureDone = false;
  bus.emit('measure');
}

export function deleteItem(type, id) {
  const it = store.get(type, id);
  if (!it) return;
  const key = type === 'place' ? 'places' : type === 'path' ? 'paths' : 'notes';
  const name = (type === 'note' ? it.text : it.name) || t(type === 'path' ? `unnamed.${it.kind}` : `unnamed.${type}`);
  store.mutate((doc) => { doc[key] = doc[key].filter((r) => r.id !== id); });
  if (S.sel?.type === type && S.sel.id === id) { S.sel = null; S.vertex = null; bus.emit('sel'); }
  toast(t('add.deleted', { name: name.length > 40 ? `${name.slice(0, 38)}…` : name }), { action: t('add.undo'), onAction: () => store.undo() });
}

export function flyToItem(type, id) {
  const it = store.get(type, id);
  if (!it || !S.proj) return;
  if (type === 'path') {
    const pts = it.coords.map((c) => S.proj.toPx(c[0], c[1]));
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const a = view.avail;
    const k = clamp(Math.min((a.w - 120) / Math.max(1, x1 - x0), (a.h - 120) / Math.max(1, y1 - y0)), view.fitK, 1.2);
    view.flyTo((x0 + x1) / 2, (y0 + y1) / 2, k);
  } else {
    const [x, y] = S.proj.toPx(it.lon, it.lat);
    view.flyTo(x, y, Math.max(view.k, Math.min(0.8, view.fitK * 3)), { onArrive: () => pulseAt(x, y) });
  }
}

export function openLandmark(id, opts = {}) {
  const lm = S.side?.landmarks?.find((l) => l.id === id);
  if (!lm) return;
  if (S.tool !== 'select') setTool('select');
  S.sel = null; S.vertex = null;
  S.lm = id;
  bus.emit('sel');
  bus.emit('landmarkOpen');
  if (opts.fly) {
    view.flyTo(lm.x, lm.y, Math.max(view.k, Math.min(0.9, view.fitK * 3.2)), { onArrive: () => pulseAt(lm.x, lm.y) });
  }
}

/** Where a landmark really is: its own lon/lat when the sidecar carries it, else the hotspot centre. */
export function landmarkLonLat(lm) {
  if (Number.isFinite(lm.lon) && Number.isFinite(lm.lat)) return [lm.lon, lm.lat];
  return S.proj.toLonLat(lm.x, lm.y);
}

export function closeLandmark() {
  if (!S.lm) return;
  S.lm = null;
  bus.emit('sel');
}
