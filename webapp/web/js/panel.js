// Right-hand panel (a bottom sheet on phones): the landmark list and "My additions" with inline editors.

import { S, bus } from './state.js';
import { store } from './store.js';
import { api } from './api.js';
import { h, reconcile, isNarrow } from './util.js';
import { t, localName, iconLabel, fmtDist, fmtEle, fmtNum, fmtTime, onLang } from './i18n.js';
import { icon, iconMarkup, iconSvg, onIconLoaded } from './icons.js';
import { lineLength } from './geo.js';
import { profileFor, drawProfile } from './profile.js';
import { setTool, select, deselect, deleteItem, flyToItem, openLandmark } from './tools.js';
import { toast } from './ui.js';

let root, tabs, panes, lmList, lmEmpty, addList, addEmpty, addFoot;
const eleCache = new Map(); // "lon,lat" → metres | null (pending)

export function initPanel(el) {
  root = el;
  const tab = (id, key) => h('button.tab', {
    type: 'button', role: 'tab', id: `tab-${id}`, 'aria-controls': `pane-${id}`,
    onclick: () => {
      // on a phone the tab row is also the sheet's handle: tapping the open tab folds the sheet away
      if (isNarrow() && isOpen() && S.tab === id) { setPanel(false); return; }
      setTab(id); setPanel(true);
    },
  }, h('span', { 'data-i18n': key }), h('span.tab-count', { 'aria-hidden': 'true' }));
  tabs = { landmarks: tab('landmarks', 'tab.landmarks'), additions: tab('additions', 'tab.additions') };

  lmList = h('ul.lm-list', { role: 'list' });
  lmEmpty = h('div.empty', h('h3', { 'data-i18n': 'lm.empty.title' }), h('p', { 'data-i18n': 'lm.empty.body' }));
  addList = h('ul.add-list', { role: 'list' });
  addEmpty = h('div.empty',
    h('h3', { 'data-i18n': 'add.empty.title' }),
    h('p', { 'data-i18n': 'add.empty.body' }),
    h('div.empty-actions',
      h('button.btn', { type: 'button', onclick: () => startTool('place') }, h('span', { html: icon('place') }), h('span', { 'data-i18n': 'add.empty.place' })),
      h('button.btn', { type: 'button', onclick: () => startTool('path') }, h('span', { html: icon('path') }), h('span', { 'data-i18n': 'add.empty.path' })),
      h('button.btn', { type: 'button', onclick: () => startTool('note') }, h('span', { html: icon('note') }), h('span', { 'data-i18n': 'add.empty.note' }))));
  const showAll = h('input', { type: 'checkbox', id: 'show-all', onchange: (e) => { S.showAll = e.target.checked; bus.emit('showAll'); } });
  addFoot = h('div.add-foot', { hidden: true },
    h('label.check', { for: 'show-all' }, showAll, h('span', { 'data-i18n': 'add.showAll' })),
    h('p.hint', { 'data-i18n': 'add.showAllHint' }));

  panes = {
    landmarks: h('div.pane', { role: 'tabpanel', id: 'pane-landmarks', 'aria-labelledby': 'tab-landmarks' }, lmEmpty, lmList),
    additions: h('div.pane', { role: 'tabpanel', id: 'pane-additions', 'aria-labelledby': 'tab-additions' }, addEmpty, addList, addFoot),
  };
  root.append(
    h('div.sheet-grip', { 'aria-hidden': 'true' }, h('span')),
    h('div.tabs', { role: 'tablist', 'data-i18n-aria': 'panel.label', onkeydown: onTabKey }, tabs.landmarks, tabs.additions),
    h('div.panel-body', panes.landmarks, panes.additions));

  // phone: drag the grip / tab row up or down to open or fold the sheet
  let dragY = null, dragged = false;
  for (const el of [root.querySelector('.sheet-grip'), root.querySelector('.tabs')]) {
    el.addEventListener('pointerdown', (e) => { if (isNarrow()) { dragY = e.clientY; dragged = false; } });
    el.addEventListener('pointermove', (e) => {
      if (dragY == null || dragged || Math.abs(e.clientY - dragY) < 28) return;
      dragged = true;
      setPanel(e.clientY < dragY);
    });
    el.addEventListener('pointerup', () => { dragY = null; });
    el.addEventListener('pointercancel', () => { dragY = null; });
    el.addEventListener('click', (e) => { if (dragged) { e.stopPropagation(); e.preventDefault(); dragged = false; } }, true);
  }
  root.querySelector('.sheet-grip').addEventListener('click', () => setPanel(!isOpen()));

  bus.on('side place lmEle', renderLandmarks);
  bus.on('doc baked side profile', renderAdditions);
  bus.on('sel', () => { renderLandmarks(); renderAdditions(); });
  bus.on('reveal', reveal);
  onLang(() => { renderLandmarks(); rebuildEditors(); renderAdditions(); });
  onIconLoaded(() => { renderLandmarks(); renderAdditions(); bus.emit('iconLoaded'); });
  S.tab = 'additions';
  setTab('additions');
}

function startTool(tool) {
  setTool(tool);
  if (isNarrow()) setPanel(false);
}

function onTabKey(e) {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
  const next = S.tab === 'landmarks' ? 'additions' : 'landmarks';
  setTab(next);
  tabs[next].focus();
  e.preventDefault();
}

export function setTab(id) {
  S.tab = id;
  for (const [key, el] of Object.entries(tabs)) {
    const on = key === id;
    el.setAttribute('aria-selected', String(on));
    el.tabIndex = on ? 0 : -1;
    panes[key].hidden = !on;
  }
}

export const isOpen = () => document.getElementById('app').dataset.panel === 'open';

export function setPanel(open) {
  const app = document.getElementById('app');
  if ((app.dataset.panel === 'open') === open) return;
  app.dataset.panel = open ? 'open' : 'closed';
  try { localStorage.setItem('studio.panel', open ? 'open' : 'closed'); } catch { /* private mode */ }
  bus.emit('panel');
}

function reveal({ type, id, focus }) {
  setTab('additions');
  setPanel(true);
  renderAdditions();
  const row = addList.querySelector(`[data-key="${CSS.escape(`${type}:${id}`)}"]`);
  if (!row) return;
  // done right away (not on the next frame) so typing can start at once, even in a throttled background tab
  row.scrollIntoView({ block: 'nearest' });
  if (focus) row.querySelector('.editor input, .editor textarea')?.focus({ preventScroll: true });
}

// ---------------------------------------------------------------- landmarks

function landmarkEle(lm) {
  const known = S.place?.landmarks?.find((x) => x.id === lm.id)?.ele;
  if (Number.isFinite(known)) return known;
  return S.lmEle?.get(lm.id);
}

function renderLandmarks() {
  const list = S.side?.landmarks || [];
  tabs.landmarks.querySelector('.tab-count').textContent = list.length ? String(list.length) : '';
  lmEmpty.hidden = list.length > 0;
  lmList.hidden = list.length === 0;
  reconcile(lmList, list, (lm) => lm.id,
    () => {
      const li = h('li');
      li.append(h('button.lm-row', { type: 'button', onclick: () => openLandmark(li.dataset.key, { fly: true }) },
        h('span.chip'), h('span.row-text', h('span.row-name'), h('span.row-meta'))));
      return li;
    },
    (li, lm) => {
      const btn = li.firstChild;
      btn.classList.toggle('is-active', S.lm === lm.id);
      btn.setAttribute('aria-current', S.lm === lm.id ? 'true' : 'false');
      const markup = lm.icon ? iconMarkup(`landmark/${lm.icon}`, S.place.slug) : null;
      const chip = btn.querySelector('.chip');
      const sig = `${lm.icon}|${markup ? 1 : 0}`;
      if (chip.dataset.sig !== sig) { chip.dataset.sig = sig; chip.innerHTML = iconSvg(markup); }
      btn.querySelector('.row-name').textContent = localName(lm) || lm.id;
      const ele = landmarkEle(lm);
      btn.querySelector('.row-meta').textContent = Number.isFinite(ele) ? fmtEle(ele) : '';
    });
}

// ---------------------------------------------------------------- additions

function allItems() {
  return [
    ...store.doc.paths.map((it) => ({ type: 'path', it })),
    ...store.doc.places.map((it) => ({ type: 'place', it })),
    ...store.doc.notes.map((it) => ({ type: 'note', it })),
  ];
}

export function displayName(type, it) {
  if (type === 'note') return it.text?.trim() || '';
  return it.name?.trim() || '';
}

export function placeholderName(type, it) {
  return t(type === 'path' ? `unnamed.${it.kind}` : `unnamed.${type}`);
}

function renderAdditions() {
  const list = allItems();
  tabs.additions.querySelector('.tab-count').textContent = list.length ? String(list.length) : '';
  addEmpty.hidden = list.length > 0;
  addList.hidden = list.length === 0;
  addFoot.hidden = !list.some(({ type, it }) => store.isBaked(type, it));
  reconcile(addList, list, ({ type, it }) => `${type}:${it.id}`, createRow, updateRow);
}

function createRow({ type, it }) {
  const id = it.id;
  const li = h('li.add-row');
  const main = h('button.row-main', {
    type: 'button',
    onclick: () => {
      if (S.sel?.type === type && S.sel.id === id) deselect();
      else select(type, id, { fly: true });
    },
  }, h('span.row-glyph'), h('span.row-text', h('span.row-name'), h('span.row-meta')));
  li.append(h('div.row-head',
    main,
    h('span.row-state', { 'data-tip-pos': 'left', tabindex: '-1' }),
    h('button.icon-btn.row-share', { type: 'button', 'data-tip': 'share.tip', 'data-tip-pos': 'left', html: icon('share'), onclick: () => shareItem(type, id) }),
    h('button.icon-btn.row-locate', { type: 'button', 'data-tip': 'add.locate', 'data-tip-pos': 'left', html: icon('locate'), onclick: () => { select(type, id, { quiet: true }); flyToItem(type, id); } }),
    h('button.icon-btn.row-delete', { type: 'button', 'data-tip': 'add.delete', 'data-tip-pos': 'left', html: icon('trash'), onclick: () => deleteItem(type, id) })));
  li.querySelectorAll('[data-tip]').forEach((el) => el.setAttribute('aria-label', t(el.dataset.tip)));
  return li;
}

function updateRow(li, { type, it }) {
  const selected = S.sel?.type === type && S.sel.id === it.id;
  li.classList.toggle('is-selected', selected);
  const main = li.querySelector('.row-main');
  main.setAttribute('aria-expanded', String(selected));

  const name = displayName(type, it);
  const nameEl = li.querySelector('.row-name');
  nameEl.textContent = name || placeholderName(type, it);
  nameEl.classList.toggle('is-placeholder', !name);

  let meta = '';
  if (type === 'path' && S.proj) meta = `${t(`kind.${it.kind}`)} · ${fmtDist(lineLength(S.proj, it.coords))}`;
  else if (type === 'place') meta = it.note?.trim() || '';
  li.querySelector('.row-meta').textContent = meta;

  const glyph = li.querySelector('.row-glyph');
  const markup = type === 'place' ? iconMarkup(it.icon || 'library/pin', S.place.slug) : null;
  const sig = type === 'place' ? `place|${it.icon}|${markup ? 1 : 0}` : type;
  if (glyph.dataset.sig !== sig) {
    glyph.dataset.sig = sig;
    glyph.classList.toggle('chip', type === 'place');
    glyph.innerHTML = type === 'place' ? iconSvg(markup) : icon(type);
  }

  const baked = store.isBaked(type, it);
  const state = li.querySelector('.row-state');
  state.classList.toggle('is-baked', baked);
  state.dataset.tip = baked ? 'add.onMap' : 'add.pending';
  state.setAttribute('aria-label', t(state.dataset.tip));
  state.setAttribute('role', 'img');

  const sub = submissionFor(type, it.id);
  const share = li.querySelector('.row-share');
  share.dataset.status = sub?.status || '';
  share.dataset.tip = sub ? `share.${sub.status}` : 'share.tip';
  share.setAttribute('aria-label', t(share.dataset.tip));
  share.innerHTML = icon(sub?.status === 'approved' ? 'check' : 'share');

  let editor = li.querySelector('.editor');
  if (selected && !editor) { editor = buildEditor(type, it.id); li.append(editor); }
  if (!selected && editor) { editor.remove(); editor = null; }
  if (editor) editor.sync(it);
}

// ---- suggesting an addition for the public map (an admin reviews it first)

function submissionFor(type, id) {
  const subs = (S.server?.submissions || []).filter((x) => x.kind === type && x.item_id === id && x.status !== 'withdrawn');
  return subs[subs.length - 1] || null;
}

async function shareItem(type, id) {
  const sub = submissionFor(type, id);
  if (sub?.status === 'approved' && !confirm(t('share.again'))) return;
  if (!(await store.save())) return;
  try {
    const res = await api.submit(S.place.slug, type, id);
    const list = S.server.submissions || (S.server.submissions = []);
    const old = list.find((x) => x.id === res.id);
    if (old) old.status = 'pending'; else list.push({ id: res.id, kind: type, item_id: id, status: 'pending' });
    toast(t(res.updated ? 'share.updated' : 'share.sent'));
    bus.emit('doc');
  } catch (e) {
    toast(e.message || t('share.failed'), { tone: 'error' });
  }
}

function rebuildEditors() {
  addList.querySelectorAll('.editor').forEach((el) => el.remove());
}

// ---------------------------------------------------------------- editors

let fieldSeq = 0;

function field(labelKey, control, optional) {
  const id = `f-${fieldSeq += 1}`;
  control.id = id;
  return h('div.field',
    h('label', { for: id }, t(labelKey), optional ? h('span.optional', ` · ${t('field.optional')}`) : null),
    control);
}

function bindText(el, type, id, prop) {
  el.addEventListener('input', () => {
    const key = type === 'place' ? 'places' : type === 'path' ? 'paths' : 'notes';
    store.mutate((doc) => { const it = doc[key].find((r) => r.id === id); if (it) it[prop] = el.value; }, `text:${type}:${id}:${prop}`);
  });
  el.addEventListener('blur', () => store.seal());
  el.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (el.tagName === 'INPUT' || e.ctrlKey || e.metaKey)) { el.blur(); document.getElementById('stage').focus({ preventScroll: true }); e.preventDefault(); }
  });
  return (value) => { if (document.activeElement !== el && el.value !== (value || '')) el.value = value || ''; };
}

function buildEditor(type, id) {
  const ed = h('div.editor');
  const syncs = [];
  if (type === 'place') {
    const name = h('input', { type: 'text', maxlength: 80, placeholder: t('ph.place'), autocomplete: 'off', spellcheck: 'false' });
    const note = h('textarea', { rows: 2, maxlength: 300, placeholder: t('ph.placeNote') });
    syncs.push(((s) => (it) => s(it.name))(bindText(name, type, id, 'name')));
    syncs.push(((s) => (it) => s(it.note))(bindText(note, type, id, 'note')));
    const picker = iconPicker(id);
    const ele = h('p.hint.ele-line');
    syncs.push(picker.sync, (it) => {
      const e = elevationAt([it.lon, it.lat]);
      ele.textContent = Number.isFinite(e) ? t('lm.elevation', { n: fmtNum(e) }) : '';
      ele.hidden = !Number.isFinite(e);
    });
    ed.append(field('field.name', name), field('field.note', note, true), picker.el, ele);
  } else if (type === 'note') {
    const text = h('textarea', { rows: 3, maxlength: 160, placeholder: t('ph.note') });
    syncs.push(((s) => (it) => s(it.text))(bindText(text, type, id, 'text')));
    ed.append(field('field.text', text));
  } else {
    const name = h('input', { type: 'text', maxlength: 80, placeholder: t('ph.path'), autocomplete: 'off', spellcheck: 'false' });
    syncs.push(((s) => (it) => s(it.name))(bindText(name, type, id, 'name')));
    const kind = kindPicker((k) => {
      store.mutate((doc) => { const p = doc.paths.find((r) => r.id === id); if (p) p.kind = k; });
    });
    syncs.push((it) => kind.sync(it.kind));
    const stats = h('dl.stats');
    const chart = h('div.profile');
    const method = h('p.hint');
    let drawn = null;
    syncs.push((it) => {
      const res = profileFor(`path:${id}`, it.coords);
      fillStats(stats, S.proj ? lineLength(S.proj, it.coords) : NaN, res.data, true);
      stats.classList.toggle('is-stale', !res.fresh);
      chart.hidden = !res.data;
      if (res.data && drawn !== res.data) { drawn = res.data; drawProfile(chart, res.data, it.coords, { height: 96 }); }
      method.textContent = res.unavailable ? t('stat.noDem') : res.data ? t(`stat.method.${res.data.method || 'tobler'}`) : '';
      method.hidden = !method.textContent;
    });
    ed.append(field('field.name', name), h('div.field', h('span.label', { id: `k-${id}` }, t('field.kind')), kind.el),
      stats, chart, method, h('p.hint', t('path.editHint')));
    kind.el.setAttribute('aria-labelledby', `k-${id}`);
  }
  ed.sync = (it) => syncs.forEach((fn) => fn(it));
  return ed;
}

/** Segmented control for trail / road / route. Used here and in the drawing HUD. */
export function kindPicker(onPick) {
  const el = h('div.seg', { role: 'radiogroup' });
  const btns = ['trail', 'road', 'route'].map((k) => h('button', {
    type: 'button', role: 'radio', 'data-kind': k,
    onclick: () => { onPick(k); },
    onkeydown: (e) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      const i = (btns.indexOf(e.currentTarget) + (e.key === 'ArrowRight' ? 1 : 2)) % 3;
      btns[i].focus(); btns[i].click(); e.preventDefault(); e.stopPropagation();
    },
  }, t(`kind.${k}`)));
  el.append(...btns);
  return {
    el,
    sync(kind) {
      for (const b of btns) {
        const on = b.dataset.kind === kind;
        b.setAttribute('aria-checked', String(on));
        b.tabIndex = on ? 0 : -1;
      }
    },
  };
}

const STAT_DEFS = [
  ['length', 'stat.length', (len) => fmtDist(len)],
  ['clock', 'stat.time', (len, d) => (d ? fmtTime(d.time_s) : '–')],
  ['ascent', 'stat.ascent', (len, d) => (d ? fmtEle(d.ascent_m) : '–')],
  ['descent', 'stat.descent', (len, d) => (d ? fmtEle(d.descent_m) : '–')],
  [null, 'stat.lowest', (len, d) => (d ? fmtEle(d.min_ele) : '–')],
  [null, 'stat.highest', (len, d) => (d ? fmtEle(d.max_ele) : '–')],
];

/** Fill a <dl> with path figures. `full` adds lowest / highest point. */
export function fillStats(dl, length, data, full) {
  const defs = full ? STAT_DEFS : STAT_DEFS.slice(0, 4);
  if (dl.children.length !== defs.length) {
    dl.replaceChildren(...defs.map(([ic, key]) => h('div.stat',
      h('dt', ic && !full ? h('span.stat-ic', { html: icon(ic) }) : null, h('span', t(key))), h('dd'))));
  }
  defs.forEach(([, , fmt], i) => { dl.children[i].lastChild.textContent = fmt(length, data); });
}

function iconPicker(id) {
  const lib = S.server?.icons.library || [];
  const lms = S.place?.landmark_icons || [];
  const el = h('div.field');
  el.append(h('span.label', { id: `ic-${id}` }, t('field.icon')));
  const grid = h('div.icon-grid', { role: 'radiogroup', 'aria-labelledby': `ic-${id}` });
  const opts = [];
  const add = (ref, label, markup) => {
    const b = h('button.icon-opt', {
      type: 'button', role: 'radio', 'data-ref': ref || '', 'data-tip': 'field.icon', 'data-tip-text': label, 'data-tip-pos': 'top',
      'aria-label': label, html: iconSvg(markup),
      onclick: () => {
        store.mutate((doc) => { const p = doc.places.find((r) => r.id === id); if (p) p.icon = ref; });
        try { if (ref) localStorage.setItem('studio.icon', ref); else localStorage.removeItem('studio.icon'); } catch { /* private mode */ }
      },
    });
    opts.push(b);
    return b;
  };
  const group = (label, nodes) => {
    if (!nodes.length) return;
    if (label) grid.append(h('span.icon-group', label));
    grid.append(...nodes);
  };
  const lmLabel = (stem) => {
    const lm = S.place?.landmarks?.find((x) => String(x.icon || '').replace(/\.svg$/i, '') === stem)
      || S.side?.landmarks?.find((x) => String(x.icon || '').replace(/\.svg$/i, '') === stem);
    return (lm && localName(lm)) || stem;
  };
  const hasPin = lib.some((it) => it.id === 'pin'); // the renderer draws library/pin when a place has no icon
  if (!hasPin) group(null, [add(null, t('icon.none'), null)]);
  group(lms.length ? t('icon.library') : null, lib.map((it) => add(`library/${it.id}`, iconLabel(it), iconMarkup(`library/${it.id}`, S.place.slug))));
  group(t('icon.landmarks'), lms.map((stem) => add(`landmark/${stem}`, lmLabel(stem), iconMarkup(`landmark/${stem}`, S.place.slug))));
  el.append(grid);
  if (!lib.length && !lms.length) el.append(h('p.hint', t('icon.empty')));
  return {
    el,
    sync(it) {
      const cur = it.icon || (hasPin ? 'library/pin' : '');
      for (const b of opts) {
        b.setAttribute('aria-checked', String(b.dataset.ref === cur));
        // icons arrive one by one; fill them in without rebuilding the editor (that would drop input focus)
        if (!b.dataset.drawn && b.dataset.ref) {
          const markup = iconMarkup(b.dataset.ref, S.place.slug);
          if (markup) { b.dataset.drawn = '1'; b.innerHTML = iconSvg(markup); }
        }
      }
    },
  };
}

/** Elevation at a point (cached, async). Returns metres, or undefined while loading / unavailable. */
let elePending = null;
export function elevationAt(lonlat) {
  if (!S.place?.has_dem) return undefined;
  const slug = S.place.slug;
  const key = `${slug}|${lonlat[0].toFixed(5)},${lonlat[1].toFixed(5)}`;
  if (eleCache.has(key)) return eleCache.get(key);
  if (elePending?.key === key) return undefined;
  clearTimeout(elePending?.timer); // only the latest point is worth asking for (a drag asks for many)
  elePending = {
    key,
    timer: setTimeout(() => {
      elePending = null;
      api.elevation(slug, [lonlat]).then((r) => {
        if (eleCache.size > 500) eleCache.clear();
        eleCache.set(key, r.elevations[0]);
        bus.emit('profile', 'ele');
      }).catch(() => {});
    }, 220),
  };
  return undefined;
}
