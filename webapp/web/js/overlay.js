// SVG overlay on top of the raster art.
//   #ov-art — the user's additions in image coordinates, styled from the sidecar's `overlay`
//             so they look at home on the current theme (scaled up a little when zoomed far out).
//   #ov-ui  — selection, handles, hotspots, measuring: screen coordinates, rebuilt on every view change.
//   #ov-fx  — short-lived effects (arrival pulse).

import { S, bus } from './state.js';
import { store } from './store.js';
import { iconMarkup } from './icons.js';
import { esc, h } from './util.js';
import { fmtDist, localName } from './i18n.js';
import { lineLength } from './geo.js';

let view, gArt, gUi, gFx, tipLm, tipMeasure;
const items = new Map(); // "place:p-1" → { g, x, y, base, min, s, box }
let strokes = [];
let scaled = [];
let artDirty = true, raf = 0, lastK = null;

const PLACE_MIN = 38;    // an icon is never smaller than this on screen, however far out you zoom
const LABEL_MIN = 11.5;  // …nor a path label
const NOTE_MIN = 13;

export function initOverlay(v, svg, stage) {
  view = v;
  gArt = svg.querySelector('#ov-art');
  gUi = svg.querySelector('#ov-ui');
  gFx = svg.querySelector('#ov-fx');
  tipLm = h('div.map-tip', { hidden: true });
  tipMeasure = h('div.map-tip.map-tip-measure', { hidden: true });
  stage.append(tipLm, tipMeasure);
  bus.on('doc side sel draft baked tool showAll hoverArt iconLoaded', () => invalidate(true));
  bus.on('hover measure profileMark view cursor', () => invalidate(false));
  document.fonts?.addEventListener?.('loadingdone', () => invalidate(true));
}

export function invalidate(art = true) {
  if (art) artDirty = true;
  if (!raf) raf = requestAnimationFrame(flush);
}

function flush() {
  raf = 0;
  if (!S.proj) {
    gArt.replaceChildren(); gUi.replaceChildren();
    tipLm.hidden = tipMeasure.hidden = true;
    items.clear(); strokes = []; scaled = [];
    return;
  }
  if (artDirty) renderArt();
  artDirty = false;
  applyView();
  renderUi();
}

// ---------------------------------------------------------------- styling from the sidecar

/**
 * The sidecar's `overlay` block, normalised. CONTRACT.md guarantees path.stroke/width_px/dash,
 * place.color/paper/accent/font and note.color/font; the renderer may add more (casing, halo,
 * tone/shade, sizes) and we use whatever is there so live additions match the baked ones.
 */
function overlayStyle() {
  const ov = S.side.overlay || {};
  const pl = ov.place || {}, nt = ov.note || {}, pa = ov.path || {};
  const paper = pl.paper || '#ffffff';
  const width = +pa.width_px || 4;
  const place = {
    ink: pl.color || '#1d1d1d', paper, accent: pl.accent || '#d7261e', tone: pl.tone || null, shade: pl.shade || null,
    halo: pl.halo || null, font: pl.font || '', size: +pl.size_px || 70, fontPx: +pl.font_px || 22,
    labelColor: pl.label_color || pl.color || '#1d1d1d', labelHalo: pl.label_halo || pl.halo || paper,
    // weight / style are not in the contract; bold labels and italic notes are what most themes bake
    weight: pl.font_weight || pl.weight || 'bold', style: pl.font_style || pl.style || 'normal',
  };
  return {
    place,
    note: {
      color: nt.color || '#1d1d1d', font: nt.font || '', fontPx: +nt.font_px || place.fontPx, halo: nt.halo || place.labelHalo,
      weight: nt.font_weight || nt.weight || 'normal', style: nt.font_style || nt.style || 'italic',
    },
    path: {
      stroke: pa.stroke || '#d7261e', width, dash: Array.isArray(pa.dash) && pa.dash.length ? pa.dash : null,
      casing: pa.casing && pa.casing.stroke ? { stroke: pa.casing.stroke, width: +pa.casing.width_px || width * 1.9 } : null,
      kinds: pa.kinds && typeof pa.kinds === 'object' ? pa.kinds : null,
    },
  };
}

/** Line style for a path. Every kind uses the theme's one rule unless the sidecar carries per-kind overrides. */
export function pathStyle(kind, st = overlayStyle()) {
  const base = st.path;
  const own = base.kinds?.[kind];
  if (!own || typeof own !== 'object') return base;
  return {
    ...base,
    stroke: own.stroke || base.stroke,
    width: +own.width_px || base.width,
    dash: 'dash' in own ? (Array.isArray(own.dash) && own.dash.length ? own.dash : null) : base.dash,
  };
}

function fontStack(name) {
  const safe = String(name || '').replace(/['"\;{}]/g, '');
  return `${safe && safe !== 'FiraGO' ? `'${safe}', ` : ''}'FiraGO', sans-serif`;
}

const fontAttrs = (f) => `font-weight="${esc(f.weight)}" font-style="${esc(f.style)}"`;

function wrap(text, max, maxLines) {
  const words = String(text || '').trim().split(/\s+/).filter(Boolean);
  const lines = [];
  let cur = '';
  for (let w of words) {
    if (w.length > max + 4) w = `${w.slice(0, max + 3)}…`;
    if (!cur) cur = w;
    else if (cur.length + 1 + w.length <= max) cur += ` ${w}`;
    else { lines.push(cur); cur = w; }
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    lines.length = maxLines;
    lines[maxLines - 1] = `${lines[maxLines - 1].replace(/[\s.,;:!?…]+$/, '')}…`;
  }
  return lines;
}

// ---------------------------------------------------------------- art layer

const f1 = (v) => v.toFixed(1);

function pathD(pts) {
  return pts.map((p, i) => `${i ? 'L' : 'M'}${f1(p[0])} ${f1(p[1])}`).join('');
}

/** Name of a path, written along its middle the way the renderer does it. */
function pathLabel(pts, name, st, style) {
  let total = 0;
  const seg = [];
  for (let i = 1; i < pts.length; i += 1) { const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); seg.push(d); total += d; }
  if (!total) return '';
  let acc = 0, i = 0;
  while (i < seg.length - 1 && acc + seg[i] < total / 2) { acc += seg[i]; i += 1; }
  const f = seg[i] ? (total / 2 - acc) / seg[i] : 0;
  const a = pts[i], b = pts[i + 1];
  const x = a[0] + (b[0] - a[0]) * f, y = a[1] + (b[1] - a[1]) * f;
  let ang = Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI;
  if (ang > 90) ang -= 180; else if (ang < -90) ang += 180;
  const size = st.place.fontPx * 1.05;
  const text = name.length > 44 ? `${name.slice(0, 42)}…` : name;
  return `<g class="a-pathlabel" data-x="${f1(x)}" data-y="${f1(y)}" data-rot="${ang.toFixed(1)}" data-base="${size.toFixed(1)}" data-min="${LABEL_MIN}">`
    + `<text class="a-label" y="${(-size * 0.9).toFixed(1)}" font-size="${size.toFixed(1)}" font-family="${esc(fontStack(st.place.font))}" ${fontAttrs(st.place)} fill="${esc(style.stroke)}" stroke="${esc(st.place.labelHalo)}" stroke-width="${(size * 0.36).toFixed(1)}">${esc(text)}</text></g>`;
}

function pathMarkup(coords, kind, name, st, { selected, hovered, hidden }) {
  if (coords.length < 2) return '';
  const style = pathStyle(kind, st);
  const pts = coords.map((c) => S.proj.toPx(c[0], c[1]));
  const d = pathD(pts);
  const dash = style.dash ? ` data-dash="${style.dash.join(',')}"` : '';
  const cw = style.casing ? style.casing.width : style.width;
  let out = '';
  if (selected || hovered) out += `<path class="p-halo${selected ? ' is-sel' : ''}" d="${d}" data-sw="${cw}" data-ref="${style.width}" data-min="2.5" data-add="${selected ? 9 : 7}"/>`;
  if (!hidden) {
    out += style.casing
      ? `<path class="p-casing" d="${d}" stroke="${esc(style.casing.stroke)}" data-sw="${cw}" data-ref="${style.width}" data-min="2.5"/>`
      : `<path class="p-casing" d="${d}" stroke="${esc(st.place.paper)}" data-sw="${style.width}" data-min="2.5" data-add="2.5"/>`;
    out += `<path class="p-line${style.dash ? ' is-dashed' : ''}" d="${d}" stroke="${esc(style.stroke)}" data-sw="${style.width}" data-min="2.5"${dash}/>`;
    if (name) out += pathLabel(pts, name, st, style);
  } else if (selected) {
    out += `<path class="p-trace" d="${d}" data-sw="0.01" data-min="1.5"/>`;
  }
  return out;
}

/** What the renderer draws for a place: its icon, else the library pin, else a plain ring. */
function placeArt(p) {
  const slug = S.place.slug;
  const ref = p.icon || 'library/pin';
  return iconMarkup(ref, slug) || '<circle class="paper ink" cx="32" cy="40.8" r="19.2"/>';
}

function placeMarkup(p, st, hidden) {
  const [x, y] = S.proj.toPx(p.lon, p.lat);
  const size = st.place.size, sc = size / 64, fs = st.place.fontPx;
  const art = placeArt(p);
  const tf = `transform="translate(${(-32 * sc).toFixed(2)} ${(-60 * sc).toFixed(2)}) scale(${sc.toFixed(4)})"`;
  const lines = wrap(p.name, 22, 3);
  const label = lines.map((ln, i) => `<tspan x="0" y="${(fs * 0.7 + i * fs * 1.18).toFixed(1)}">${esc(ln)}</tspan>`).join('');
  return `<g class="a-place${hidden ? ' is-baked' : ''}" data-item="place:${esc(p.id)}" data-x="${f1(x)}" data-y="${f1(y)}" data-base="${size}" data-min="${PLACE_MIN}">`
    + (st.place.halo ? `<g class="lmh" ${tf}>${art}</g>` : '')
    + `<g class="lm" ${tf}>${art}</g>`
    + (label ? `<text class="a-label" font-size="${fs}" font-family="${esc(fontStack(st.place.font))}" ${fontAttrs(st.place)} fill="${esc(st.place.labelColor)}" stroke="${esc(st.place.labelHalo)}" stroke-width="${(fs * 0.36).toFixed(1)}">${label}</text>` : '')
    + '</g>';
}

function noteMarkup(n, st, hidden) {
  const [x, y] = S.proj.toPx(n.lon, n.lat);
  const fs = st.note.fontPx, arm = fs * 0.32, d = arm * 0.72;
  const lines = wrap(n.text, 30, 4);
  const body = (lines.length ? lines : ['…']).map((ln, i) => `<tspan x="${(fs * 0.75).toFixed(1)}" y="${(i * fs * 1.18).toFixed(1)}">${esc(ln)}</tspan>`).join('');
  return `<g class="a-note${hidden ? ' is-baked' : ''}" data-item="note:${esc(n.id)}" data-x="${f1(x)}" data-y="${f1(y)}" data-base="${fs}" data-min="${NOTE_MIN}">`
    + `<path class="a-note-mark" d="M${-arm} 0H${arm}M0 ${-arm}V${arm}M${-d} ${-d}L${d} ${d}M${-d} ${d}L${d} ${-d}" stroke="${esc(st.note.color)}" stroke-width="${(fs * 0.1).toFixed(2)}"/>`
    + `<text class="a-label a-note-text" font-size="${fs}" font-family="${esc(fontStack(st.note.font))}" ${fontAttrs(st.note)} fill="${esc(st.note.color)}" stroke="${esc(st.note.halo)}" stroke-width="${(fs * 0.36).toFixed(1)}">${body}</text>`
    + '</g>';
}

function renderArt() {
  const st = overlayStyle();
  const css = gArt.style;
  css.setProperty('--lm-ink', st.place.ink);
  css.setProperty('--lm-paper', st.place.paper);
  css.setProperty('--lm-accent', st.place.accent);
  css.setProperty('--lm-halo', st.place.halo || st.place.paper);
  if (st.place.tone) css.setProperty('--lm-tone', st.place.tone); else css.removeProperty('--lm-tone');
  if (st.place.shade) css.setProperty('--lm-shade', st.place.shade); else css.removeProperty('--lm-shade');
  const isSel = (type, id) => S.sel?.type === type && S.sel.id === id;
  const isHover = (type, id) => S.hover?.type === type && S.hover.id === id;
  // While fresh art is being laid over the old sheet (S.wipe), the live copies of what it contains
  // stay until the wipe line passes them: they go into a group clipped to the not-yet-redrawn part.
  const baked = (type, it) => !S.showAll && store.isBaked(type, it);
  const hide = (type, it) => !S.wipe && baked(type, it);
  let html = '', going = '';
  const put = (type, it, markup) => { if (S.wipe && baked(type, it)) going += markup; else html += markup; };
  for (const p of store.doc.paths) {
    put('path', p, pathMarkup(p.coords, p.kind, (p.name || '').trim(), st, {
      selected: isSel('path', p.id), hovered: isHover('path', p.id), hidden: hide('path', p),
    }));
  }
  if (S.draft) html += pathMarkup(S.draft.coords, S.draft.kind, '', st, { selected: true });
  for (const p of store.doc.places) put('place', p, placeMarkup(p, st, hide('place', p)));
  for (const n of store.doc.notes) put('note', n, noteMarkup(n, st, hide('note', n)));
  if (going) {
    const { w, h: ph } = S.proj.size;
    html += `<defs><clipPath id="ov-wipe" clipPathUnits="userSpaceOnUse"><rect id="ov-wipe-rect" x="${-w}" width="${3 * w}" y="0" height="${2 * ph}"/></clipPath></defs>`
      + `<g clip-path="url(#ov-wipe)">${going}</g>`;
  }
  gArt.innerHTML = html;
  if (going) setWipe(S.wipe.p);

  strokes = [];
  gArt.querySelectorAll('[data-sw]').forEach((el) => {
    strokes.push({
      el, w: +el.dataset.sw, ref: +el.dataset.ref || +el.dataset.sw, min: +el.dataset.min || 0, add: +el.dataset.add || 0,
      dash: el.dataset.dash ? el.dataset.dash.split(',').map(Number) : null,
    });
  });
  items.clear();
  scaled = [];
  gArt.querySelectorAll('g[data-base]').forEach((g) => {
    const it = { g, x: +g.dataset.x, y: +g.dataset.y, rot: +g.dataset.rot || 0, base: +g.dataset.base, min: +g.dataset.min, s: 1, box: null };
    scaled.push(it);
    if (!g.dataset.item) return;
    let b = { x: -20, y: -20, width: 40, height: 40 };
    try { b = g.getBBox(); } catch { /* not rendered */ }
    it.box = { x: b.x, y: b.y, w: b.width, h: b.height };
    items.set(g.dataset.item, it);
  });
  lastK = null;
}

function applyView() {
  const { x, y, k } = view;
  gArt.setAttribute('transform', `matrix(${k} 0 0 ${k} ${x} ${y})`);
  if (k === lastK) return;
  lastK = k;
  for (const s of strokes) {
    // grow thin lines so they stay visible when zoomed far out; casing and dashes grow with the line
    const f = Math.max(1, s.min / (s.ref * k));
    s.el.setAttribute('stroke-width', (s.w * f + s.add / k).toFixed(3));
    if (s.dash) s.el.setAttribute('stroke-dasharray', s.dash.map((v) => (v * f).toFixed(2)).join(' '));
  }
  for (const it of scaled) {
    it.s = Math.max(1, it.min / (it.base * k));
    it.g.setAttribute('transform', `translate(${it.x} ${it.y})${it.rot ? ` rotate(${it.rot})` : ''} scale(${it.s.toFixed(4)})`);
  }
}

/** Move the wipe line: live copies above it (already redrawn) are clipped away. p = 0…1 down the sheet. */
export function setWipe(p) {
  const rect = gArt.querySelector('#ov-wipe-rect');
  if (rect) rect.setAttribute('y', (p * S.proj.size.h).toFixed(1));
}

/** Screen-space box of a place / note (for outlines and hit testing). */
export function screenBox(key) {
  const it = items.get(key);
  if (!it) return null;
  const f = it.s * view.k;
  const [sx, sy] = view.toScreen(it.x, it.y);
  return { x: sx + it.box.x * f, y: sy + it.box.y * f, w: it.box.w * f, h: it.box.h * f };
}

export function itemKeys() { return [...items.keys()]; }

// ---------------------------------------------------------------- ui layer

/** The path whose points can be dragged right now: the draft while drawing, else the selected path. */
export function editablePath() {
  if (S.tool === 'path' && S.draft) return { coords: S.draft.coords, draft: true };
  if (S.tool === 'select' && S.sel?.type === 'path') {
    const p = store.get('path', S.sel.id);
    if (p) return { coords: p.coords, id: p.id, draft: false };
  }
  return null;
}

export function lonLatToScreen(c) {
  const [x, y] = S.proj.toPx(c[0], c[1]);
  return view.toScreen(x, y);
}

function placeTip(el, text, sx, sy, above = true) {
  el.textContent = text;
  el.hidden = false;
  const w = el.offsetWidth, hh = el.offsetHeight;
  const x = Math.min(view.sw - w - 6, Math.max(6, sx - w / 2));
  const y = above ? Math.max(6, sy - hh - 10) : Math.min(view.sh - hh - 6, sy + 12);
  el.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
}

function renderUi() {
  const k = view.k;
  let html = '';
  let lmTip = null;

  // landmark hotspots: the one under the pointer and the one whose card is open
  const hoverLm = S.hover?.type === 'landmark' ? S.hover.id : null;
  for (const lm of S.side.landmarks || []) {
    if (lm.id !== hoverLm && lm.id !== S.lm) continue;
    const [sx, sy] = view.toScreen(lm.x, lm.y);
    const r = Math.max((lm.r || 40) * k, 18);
    html += `<circle class="lm-ring${lm.id === S.lm ? ' is-open' : ''}" cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="${r.toFixed(1)}"/>`;
    if (lm.id === hoverLm && lm.id !== S.lm) lmTip = { text: localName(lm) || lm.id, sx, sy: sy - r };
  }
  if (lmTip) placeTip(tipLm, lmTip.text, lmTip.sx, lmTip.sy); else tipLm.hidden = true;

  // outlines of the selected / hovered place or note
  const outline = (sel, cls) => {
    if (!sel || (sel.type !== 'place' && sel.type !== 'note')) return;
    const b = screenBox(`${sel.type}:${sel.id}`);
    if (!b) return;
    const pad = 6;
    html += `<rect class="item-box ${cls}" x="${(b.x - pad).toFixed(1)}" y="${(b.y - pad).toFixed(1)}" width="${(b.w + pad * 2).toFixed(1)}" height="${(b.h + pad * 2).toFixed(1)}" rx="8"/>`;
  };
  if (S.hover && !(S.sel && S.hover.type === S.sel.type && S.hover.id === S.sel.id)) outline(S.hover, 'is-hover');
  outline(S.sel, 'is-sel');
  if (S.sel && (S.sel.type === 'place' || S.sel.type === 'note')) {
    const it = store.get(S.sel.type, S.sel.id);
    if (it) {
      const [sx, sy] = lonLatToScreen([it.lon, it.lat]);
      html += `<circle class="anchor-dot" cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="3.5"/>`;
    }
  }

  // rubber band from the last drawn point to the pointer
  const ed = editablePath();
  if (ed?.draft && ed.coords.length && S.cursor && !S.hover) {
    const [ax, ay] = lonLatToScreen(ed.coords[ed.coords.length - 1]);
    html += `<line class="rubber" x1="${ax.toFixed(1)}" y1="${ay.toFixed(1)}" x2="${S.cursor[0].toFixed(1)}" y2="${S.cursor[1].toFixed(1)}"/>`;
  }

  // handles
  if (ed) {
    ed.coords.forEach((c, i) => {
      const [sx, sy] = lonLatToScreen(c);
      const active = !ed.draft && S.vertex === i;
      const hot = S.hover?.type === 'handle' && S.hover.index === i;
      const end = ed.draft && i === ed.coords.length - 1;
      html += `<circle class="handle${active ? ' is-active' : ''}${hot ? ' is-hot' : ''}${end ? ' is-end' : ''}" cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="${active || hot ? 6.5 : 5.5}"/>`;
    });
    if (S.hover?.type === 'segment') {
      html += `<circle class="handle is-ghost" cx="${S.hover.sx.toFixed(1)}" cy="${S.hover.sy.toFixed(1)}" r="5"/>`;
    }
  }

  // measuring line
  if (S.measure.length) {
    const pts = S.measure.map(lonLatToScreen);
    const line = pts.slice();
    if (S.tool === 'measure' && S.cursor && !S.measureDone) line.push(S.cursor);
    const d = line.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join('');
    html += `<path class="m-casing" d="${d}"/><path class="m-line" d="${d}"/>`;
    for (const p of pts) html += `<circle class="m-dot" cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3.5"/>`;
    let total = lineLength(S.proj, S.measure);
    const last = line[line.length - 1];
    if (line.length > pts.length) {
      const [ix, iy] = view.toImage(S.cursor[0], S.cursor[1]);
      total += S.proj.dist(S.measure[S.measure.length - 1], S.proj.toLonLat(ix, iy));
    }
    if (line.length > 1) placeTip(tipMeasure, fmtDist(total), last[0], last[1] - 4); else tipMeasure.hidden = true;
  } else {
    tipMeasure.hidden = true;
  }

  // point picked on the elevation chart
  if (S.profileMark) {
    const [sx, sy] = lonLatToScreen(S.profileMark);
    html += `<circle class="profile-mark" cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="6"/>`;
  }

  gUi.innerHTML = html;
}

/** The authored arrival: an ink ring that opens around the place we flew to. */
export function pulseAt(ix, iy) {
  const [sx, sy] = view.toScreen(ix, iy);
  const c = h('circle.pulse', { cx: sx.toFixed(1), cy: sy.toFixed(1), r: 26 });
  c.addEventListener('animationend', () => c.remove());
  gFx.append(c);
  setTimeout(() => c.remove(), 1500);
}
