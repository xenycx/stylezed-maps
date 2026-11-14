// Public site map editor (forked from the local studio) — bootstrap and orchestration: which place / style / language is on screen,
// loading and swapping the art, rendering on demand, and the stage's whole-screen states.

import { api } from './api.js';
import { S, bus, hasRender, themeById } from './state.js';
import { store } from './store.js';
import { View } from './view.js';
import { makeProjection } from './geo.js';
import { $, h, isNarrow, reducedMotion } from './util.js';
import { t, setLang, applyI18n, localName, onLang } from './i18n.js';
import { icon, revalidateIcons } from './icons.js';
import { initOverlay, invalidate, setWipe } from './overlay.js';
import { initTools, setTool, TOOLS, landmarkLonLat } from './tools.js';
import { initPanel, setPanel, setTab, isOpen } from './panel.js';
import { initCard } from './card.js';
import { initHud } from './hud.js';
import { initTopbar } from './topbar.js';
import { initTooltips, toast } from './ui.js';
import { session, setSession, signIn } from './session.js';
import { waitJob } from './api.js';

const stage = $('#stage');
const art = $('#art');
const artNext = $('#art-next');
const glow = $('#glow');
const stateEl = $('#stage-state');
const notice = $('#notice');
const view = new View(stage);
const query = new URLSearchParams(location.search);
let artToken = 0;
let tick = 0;

const prefs = {
  get(key) { try { return localStorage.getItem(`studio.${key}`); } catch { return null; } },
  set(key, v) { try { localStorage.setItem(`studio.${key}`, v); } catch { /* private mode */ } },
};

// ---------------------------------------------------------------- chrome that never changes shape

function buildChrome() {
  const keys = { select: 'V', place: 'P', path: 'D', note: 'N', measure: 'M' };
  $('#rail').append(...TOOLS.map((tool) => h('button.tool', {
    type: 'button', 'data-tool': tool, 'data-tip': `tool.${tool}`, 'data-keys': keys[tool], 'data-tip-pos': 'right',
    'aria-pressed': 'false', html: icon(tool), onclick: () => { setTool(tool); stage.focus({ preventScroll: true }); },
  })));
  const z = (id, ic, tip, key, fn) => h('button.icon-btn', {
    type: 'button', id, 'data-tip': tip, 'data-keys': key, 'data-tip-pos': 'right', html: icon(ic), onclick: fn,
  });
  $('#zoom').append(
    z('z-in', 'plus', 'zoom.in', '+', () => view.zoomBy(1.4)),
    h('output', { id: 'z-val' }, '–'),
    z('z-out', 'minus', 'zoom.out', '−', () => view.zoomBy(1 / 1.4)),
    z('z-fit', 'fit', 'zoom.fit', '0', () => view.fit()),
    z('z-actual', 'actual', 'zoom.actual', '1', () => view.zoomTo(1)));
}

function syncTool() {
  $('#app').dataset.tool = S.tool;
  for (const b of document.querySelectorAll('#rail .tool')) b.setAttribute('aria-pressed', String(b.dataset.tool === S.tool));
  if (isNarrow() && S.tool !== 'select') setPanel(false);
}

// ---------------------------------------------------------------- view ⇄ DOM

function applyView() {
  const { x, y, k } = view;
  const tf = `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px) scale(${k.toFixed(5)})`;
  art.style.transform = tf;
  artNext.style.transform = tf;
  glow.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
  glow.style.width = `${(view.w * k).toFixed(1)}px`;
  glow.style.height = `${(view.h * k).toFixed(1)}px`;
  $('#z-val').textContent = `${Math.round(k * 100)}%`;
  $('#z-in').disabled = k >= view.maxK - 1e-6;
  $('#z-out').disabled = k <= view.minK + 1e-6;
  bus.emit('view');
}

function updateInsets(keepFit) {
  const narrow = isNarrow();
  const app = $('#app');
  const insets = narrow
    ? { top: 8, left: 8, right: 8, bottom: stage.clientHeight < 420 ? 64 : 132 }
    : { top: 12, left: 76, right: isOpen() ? 408 : 12, bottom: 12 };
  view.setInsets(insets);
  view.resize(keepFit);
  const a = view.avail;
  app.style.setProperty('--avail-cx', `${a.cx}px`);
  app.style.setProperty('--avail-w', `${a.w}px`);
  if (view.hasImage) applyView();
}

// ---------------------------------------------------------------- stage states (a blank sheet on the desk)

function showState(kind, data = {}) {
  S.stageState = { kind, data };
  renderState();
}

function hideState() {
  S.stageState = null;
  stateEl.hidden = true;
  stateEl.replaceChildren();
}

function renderState() {
  const st = S.stageState;
  if (!st) return;
  const { kind, data } = st;
  const th = themeById(S.theme);
  const vars = { theme: th ? localName(th) : S.theme, inLang: S.lang === 'en' || S.lang === 'ka' ? t(`in.${S.lang}`) : `(${S.lang.toUpperCase()})` };
  const sheet = h('div.sheet', { class: `sheet is-${kind}` });
  const cmd = (text) => h('code.cmd', text);
  if (kind === 'loading' || kind === 'loadingArt') {
    sheet.append(h('p.sheet-quiet', { role: 'status' }, t(`state.${kind}`)), h('div.bar'));
  } else if (kind === 'unreachable') {
    sheet.append(h('h1', t('state.unreachable.title')), h('p', t('state.unreachable.body')),
      h('div.sheet-actions', h('button.btn.btn-ink', { type: 'button', onclick: () => location.reload() }, t('state.retry'))));
  } else if (kind === 'preparing') {
    const j = data.job;
    const step = data.status === 'rendering' ? 'prep.drawing' : data.status === 'fetching' ? 'prep.fetching' : 'prep.queued';
    sheet.append(h('h1', { role: 'status' }, t('prep.title', { name: data.name || '' })), h('p', t(step)),
      j?.position ? h('p.sheet-quiet', t('prep.position', { n: j.position })) : null,
      h('div.bar'), h('p.sheet-quiet', t('prep.leave')));
  } else if (kind === 'placeFailed') {
    sheet.append(h('h1', t('prep.failed')), h('pre.log', { tabindex: '0' }, data.error || ''),
      h('div.sheet-actions', h('a.btn.btn-ink', { href: '/' }, t('prep.back'))));
  } else if (kind === 'notFound') {
    sheet.append(h('h1', t('prep.notFound')), h('div.sheet-actions', h('a.btn.btn-ink', { href: '/' }, t('prep.back'))));
  } else if (kind === 'noPlaces') {
    sheet.append(h('h1', t('state.noPlaces.title')), h('p', t('state.noPlaces.body')), cmd('uv run fetch.py "Nikortsminda, Georgia"'));
  } else if (kind === 'noThemes') {
    sheet.append(h('h1', t('state.noThemes.title')), h('p', t('state.noThemes.body')));
  } else if (kind === 'notDrawn') {
    sheet.append(h('h1', t('state.notDrawn.title', vars)), h('p', t('state.notDrawn.body')),
      h('div.sheet-actions', h('button.btn.btn-primary', { type: 'button', onclick: () => doRender() }, h('span', { html: icon('redraw') }), h('span', t('state.notDrawn.action')))));
  } else if (kind === 'rendering') {
    const secs = Math.max(0, Math.round((performance.now() - S.render.t0) / 1000));
    sheet.append(h('h1', { role: 'status' }, t('state.rendering.title')), h('p', t('state.rendering.body', vars)),
      h('div.bar'), h('p.sheet-quiet.tnum', S.render.queue ? t('prep.position', { n: S.render.queue }) : t('state.rendering.elapsed', { n: secs })));
  } else if (kind === 'failed') {
    sheet.append(h('h1', t('state.failed.title')), h('p', t('state.failed.body')),
      h('pre.log', { tabindex: '0' }, data.log || t('state.failed.noLog')),
      h('div.sheet-actions', h('button.btn.btn-ink', { type: 'button', onclick: () => doRender() }, h('span', { html: icon('redraw') }), h('span', t('state.retry')))));
  } else if (kind === 'imageFailed') {
    sheet.append(h('h1', t('state.imageFailed')),
      h('div.sheet-actions', h('button.btn.btn-ink', { type: 'button', onclick: () => showTarget(false) }, t('state.retry'))));
  }
  stateEl.replaceChildren(sheet);
  stateEl.hidden = false;
}

/** A render failed while older art is still on screen: say so without taking the map away. */
function renderNotice() {
  const err = S.render.error;
  if (!err || !S.side) { notice.hidden = true; notice.replaceChildren(); return; }
  notice.replaceChildren(
    h('div.notice-head',
      h('span.notice-ic', { html: icon('alert') }),
      h('div', h('h2', t(err.title || 'state.failed.title')), h('p', err.quota ? '' : `${t('state.failed.keep')} ${t('state.failed.body')}`)),
      h('button.icon-btn', { type: 'button', 'data-tip': 'state.failed.dismiss', 'aria-label': t('state.failed.dismiss'), html: icon('close'), onclick: () => { S.render.error = null; renderNotice(); } })),
    h('pre.log', { tabindex: '0' }, err.log || t('state.failed.noLog')),
    h('div.notice-actions', h('button.btn.btn-primary', { type: 'button', onclick: () => doRender() }, h('span', { html: icon('redraw') }), h('span', t('state.retry')))));
  notice.hidden = false;
}

// ---------------------------------------------------------------- art

function artUrl(side) {
  return `${side._studio?.dir || `/out/${encodeURIComponent(S.place.slug)}/`}${encodeURIComponent(side.image)}?v=${side._studio?.mtime || Date.now()}`;
}

/** img.decode(), but also settle on the plain load event (decode can stall in background or embedded views). */
function decoded(img) {
  return new Promise((resolve, reject) => {
    if (img.complete && img.naturalWidth) { resolve(); return; }
    img.addEventListener('load', () => resolve(), { once: true });
    img.addEventListener('error', () => reject(new Error('image')), { once: true });
    img.decode().then(resolve, () => {});
  });
}

// Sharper art for zooming in: the preview is 1600 px wide; on the first zoom past ~1:1 a 4000 px copy is fetched
// (made on the server once per render, then cached) and swapped in under the same on-screen size.
let hdFor = null;
let hdTimer = 0;
function maybeHd() {
  clearTimeout(hdTimer);
  hdTimer = setTimeout(() => {
    const side = S.side;
    if (!side || hdFor === side || S.wipe || !S.place) return;
    if (view.k * (window.devicePixelRatio || 1) < 1.2) return;
    hdFor = side;
    const url = `${api.exportUrl(S.place.slug, { theme: side.theme, lang: side.lang, fmt: 'hd', mine: side._studio?.mine ? '1' : '0' })}&v=${side._studio?.mtime || ''}`;
    const img = new Image();
    img.decoding = 'async';
    img.src = url;
    stage.classList.add('is-sharpening');
    decoded(img)
      .then(() => { if (S.side === side && !S.wipe) art.src = img.src; })
      .catch(() => { /* keep the preview */ })
      .finally(() => stage.classList.remove('is-sharpening'));
  }, 300);
}

async function showSide(side, opts = {}) {
  const token = artToken += 1;
  const img = new Image();
  img.decoding = 'async';
  img.src = artUrl(side);
  if (!S.side) showState('loadingArt');
  try { await decoded(img); } catch {
    if (token !== artToken) return false;
    if (!S.side) showState('imageFailed'); else toast(t('state.imageFailed'));
    return false;
  }
  if (token !== artToken) return false;
  if (S.wipe) { S.wipe = null; artNext.hidden = true; artNext.style.clipPath = ''; }

  const prev = S.side;
  const sameSheet = !!prev && prev.px[0] === side.px[0] && prev.px[1] === side.px[1]
    && prev.frame_px.every((v, i) => Math.abs(v - side.frame_px[i]) < 0.5) && Math.abs(prev.m_per_px - side.m_per_px) < 1e-6
    && prev.center.every((v, i) => Math.abs(v - side.center[i]) < 1e-7);
  S.side = side;
  S.proj = makeProjection(side);
  if (S.lm && !side.landmarks?.some((l) => l.id === S.lm)) S.lm = null;
  store.setBaked(side._studio?.baked);
  view.setImage(side.px[0], side.px[1]);
  for (const el of [art, artNext]) { el.width = side.px[0]; el.height = side.px[1]; }
  hideState();

  if (!prev) {
    art.src = img.src;
    view.measure();
    updateInsets(true);
    view.fit(false);
    applyView();
    stage.classList.add('has-art');
    art.classList.add('is-in');
    glow.classList.add('is-in');
  } else if (reducedMotion() || !sameSheet) {
    art.src = img.src;
    if (!sameSheet) { view.fit(false); applyView(); }
  } else {
    // the authored moment: fresh ink is laid over the old sheet, top to bottom,
    // and the live copies of the additions give way exactly where the ink has passed
    artNext.src = img.src;
    artNext.style.clipPath = 'inset(0 0 100% 0)';
    artNext.hidden = false;
    glow.classList.remove('is-fresh');
    void glow.offsetWidth;
    glow.classList.add('is-fresh');
    S.wipe = { p: 0 };
    const t0 = performance.now(), dur = 1050;
    const step = (now) => {
      if (token !== artToken) return;
      const t = Math.min(1, (now - t0) / dur);
      const p = 1 - (1 - t) ** 2.6;
      S.wipe.p = p;
      artNext.style.clipPath = `inset(0 0 ${((1 - p) * 100).toFixed(2)}% 0)`;
      setWipe(p);
      if (t < 1) { requestAnimationFrame(step); return; }
      S.wipe = null;
      bus.emit('baked');
      art.src = img.src;
      const hide = () => { if (token === artToken) { artNext.hidden = true; artNext.style.clipPath = ''; } };
      if (art.decode) art.decode().then(hide, hide); else hide();
    };
    requestAnimationFrame(step);
  }
  bus.emit('side');
  loadLandmarkElevations(side);
  return true;
}

async function loadLandmarkElevations(side) {
  S.lmEle = new Map();
  const need = (side.landmarks || []).filter((lm) => !Number.isFinite(S.place.landmarks?.find((x) => x.id === lm.id)?.ele));
  if (!need.length || !S.place.has_dem) return;
  try {
    const res = await api.elevation(S.place.slug, need.map(landmarkLonLat));
    if (S.side !== side) return;
    need.forEach((lm, i) => S.lmEle.set(lm.id, res.elevations[i]));
    bus.emit('lmEle');
  } catch { /* elevation is a nicety */ }
}

// ---------------------------------------------------------------- what is on screen

/** Show S.theme in S.lang: load it if it exists, otherwise draw it (auto) or offer to. */
async function showTarget(auto) {
  const { theme } = S;
  const lang = S.lang;
  bus.emit('target');
  if (!S.place || !theme) return;
  if (hasRender(theme, lang)) {
    let side = null;
    try { side = await api.sidecar(S.place.slug, theme, lang); } catch (e) {
      if (e.network) { if (!S.side) showState('unreachable'); else toast(t('state.unreachable.title')); return; }
      S.place.renders = S.place.renders.filter((r) => !(r.theme === theme && r.lang === lang));
    }
    if (S.theme !== theme || S.lang !== lang) return;
    if (side) { await showSide(side); return; }
  }
  if (auto) await doRender();
  else if (!S.side) showState('notDrawn');
}

async function doRender() {
  if (S.render.busy || !S.place || !S.theme) return;
  const slug = S.place.slug, theme = S.theme, lang = S.lang;
  S.render = { busy: true, error: null, t0: performance.now(), theme, lang };
  bus.emit('render');
  renderNotice();
  if (!S.side) showState('rendering');
  clearInterval(tick);
  tick = setInterval(() => { bus.emit('renderTick'); if (S.stageState?.kind === 'rendering') renderState(); }, 1000);
  const finish = (error) => {
    clearInterval(tick);
    S.render = { busy: false, error, t0: 0, theme, lang };
    bus.emit('render');
    renderNotice();
    if (error && !S.side) showState('failed', error);
  };
  if (session.me && !(await store.save())) { finish({ log: t('save.errorToast') }); return; }
  let side;
  try {
    side = await api.render(slug, theme, lang, (j) => { S.render.queue = j.status === 'queued' ? j.position : 0; });
  } catch (e) {
    if (e.code === 'quota' || e.code === 'busy') {
      finish(S.side ? { log: e.message, title: 'quota.title', quota: true } : { log: e.message });
      toast(e.message, { tone: 'error' });
      return;
    }
    finish({ log: e.network ? `${t('state.unreachable.title')}\n${t('state.unreachable.body')}` : (e.data?.log || e.message || '') });
    return;
  }
  if (S.place?.slug !== slug) { finish(null); return; }
  const had = hasRender(theme, lang);
  S.place.renders = S.place.renders.filter((r) => !(r.theme === theme && r.lang === lang))
    .concat({ id: `${theme}.${lang}`, theme, lang, mtime: side._studio?.mtime });
  const redrawn = !!S.side && had;
  finish(null);
  revalidateIcons();
  if (S.theme === theme && S.lang === lang && (await showSide(side, { fresh: true }))) {
    toast(t(redrawn ? 'redraw.done' : 'redraw.doneNew'));
  }
}

async function openPlace(slug) {
  const place = S.server.places.find((p) => p.slug === slug) || S.server.places[0];
  if (place.status !== 'ready') { await waitForPlace(place); return; }
  if (store.slug && store.slug !== place.slug) await store.save();
  artToken += 1;
  S.place = place;
  S.side = null; S.proj = null; S.sel = null; S.lm = null; S.draft = null; S.measure = []; S.vertex = null;
  S.render.error = null;
  stage.classList.remove('has-art');
  art.classList.remove('is-in'); glow.classList.remove('is-in');
  art.removeAttribute('src');
  renderNotice();
  prefs.set('place', place.slug);
  bus.emit('place');
  bus.emit('side');
  showState('loading');
  try { store.load(place.slug, await api.custom(place.slug)); } catch (e) {
    showState('unreachable');
    return;
  }
  store.setBaked(null);
  if (!S.server.themes.length) { S.theme = null; bus.emit('target'); showState('noThemes'); return; }

  // the place's own language unless the user chose otherwise for it
  S.lang = query.get('lang') || prefs.get(`lang.${place.slug}`) || place.lang || 'en';
  // a map is drawn in English or in the place's own language (meta.json "lang")
  const local = place.lang && place.lang !== 'en' ? place.lang : null;
  if (S.lang !== 'en' && S.lang !== local) S.lang = local || 'en';
  const localBtn = document.querySelectorAll('.lang-seg [data-lang]')[1];
  if (localBtn) {
    localBtn.hidden = !local;
    if (local) {
      localBtn.dataset.lang = local;
      localBtn.lang = local;
      localBtn.textContent = local === 'ka' ? 'ქართული' : local.toUpperCase();
    }
  }
  setLang(S.lang);

  const ids = S.server.themes.map((th) => th.id);
  const wanted = [query.get('theme'), prefs.get(`theme.${place.slug}`)].find((id) => id && ids.includes(id));
  S.theme = wanted || ids.find((id) => hasRender(id, S.lang)) || ids[0];
  setTab((place.landmarks?.length || 0) > 0 && store.count === 0 ? 'landmarks' : 'additions');
  await showTarget(false);
}

async function pickTheme(id) {
  if (id === S.theme && S.side?.theme === id) return;
  S.theme = id;
  prefs.set(`theme.${S.place.slug}`, id);
  await showTarget(true);
}

async function pickLang(lang) {
  if (lang === S.lang) return;
  S.lang = lang;
  prefs.set('lang', lang);
  if (S.place) prefs.set(`lang.${S.place.slug}`, lang);
  setLang(lang);
  await showTarget(true);
}

// ---------------------------------------------------------------- boot

async function boot() {
  buildChrome();
  initTooltips();
  initPanel($('#panel'));
  initOverlay(view, $('#overlay'), stage);
  initTools(view, stage);
  initCard($('#card'), view);
  initHud($('#hud'));
  initTopbar({ place: openPlace, theme: pickTheme, lang: pickLang, redraw: doRender });

  const pre = query.get('lang') || prefs.get('lang') || ((navigator.language || '').startsWith('ka') ? 'ka' : 'en');
  S.lang = pre || 'en';
  setLang(S.lang);
  applyI18n(document);

  if (isNarrow() || prefs.get('panel') === 'closed' || query.get('panel') === 'closed') $('#app').dataset.panel = 'closed';

  view.on('change', applyView);
  view.on('change', maybeHd);
  bus.on('side', maybeHd);
  bus.on('baked', maybeHd);
  bus.on('tool', syncTool);
  bus.on('panel', () => { updateInsets(false); });
  bus.on('landmarkOpen', () => { if (isNarrow()) setPanel(false); });
  const syncReady = () => { // tools only make sense with a map on the desk
    const off = !S.side;
    $('#rail').inert = off; $('#zoom').inert = off;
    $('#app').toggleAttribute('data-noart', off);
  };
  bus.on('side', syncReady);
  syncReady();
  bus.on('render', () => { $('#app').toggleAttribute('data-busy', S.render.busy); });
  bus.on('saveError', () => toast(t('save.errorToast'), { action: t('save.retry'), onAction: () => store.save() }));
  const syncTitle = () => { document.title = S.place ? `${localName(S.place)} · ${t('app.title')}` : t('app.title'); };
  bus.on('place', syncTitle);
  onLang(() => { renderState(); renderNotice(); syncTitle(); });
  new ResizeObserver(() => updateInsets(false)).observe(stage);
  window.addEventListener('pagehide', () => store.flushOnExit());
  window.addEventListener('beforeunload', (e) => {
    if (store.saveState === 'dirty' || store.saveState === 'error') { store.flushOnExit(); if (store.saveState === 'error') e.preventDefault(); }
  });
  syncTool();
  updateInsets(true);

  showState('loading');
  const slug = decodeURIComponent((location.pathname.match(/^\/m\/([^/]+)/) || [])[1] || '');
  try { S.server = await api.state(slug); } catch (e) {
    showState(e.code === 'unknown_place' ? 'notFound' : 'unreachable');
    return;
  }
  setSession(S.server);
  injectFonts(S.server.fonts || []);
  bus.emit('server');
  bus.emit('session');
  await openPlace(slug);
  if (query.get('tab')) setTab(query.get('tab') === 'landmarks' ? 'landmarks' : 'additions');
  if (query.get('tool') && TOOLS.includes(query.get('tool'))) setTool(query.get('tool'));
}

/** A new place is still being downloaded and drawn: show where it is in the line, then open it. */
async function waitForPlace(place) {
  let p = place;
  let job = S.server.job;
  for (;;) {
    if (p.status === 'failed') { showState('placeFailed', { error: p.error }); return; }
    if (p.status === 'ready') break;
    showState('preparing', { name: localName(p) || p.name, status: p.status, job });
    await new Promise((r) => setTimeout(r, 3000));
    try {
      const st = await api.state(p.slug);
      S.server = st; setSession(st);
      p = st.places[0]; job = st.job;
    } catch (e) { if (!e.network) { showState('notFound'); return; } }
  }
  bus.emit('server');
  await openPlace(p.slug);
}

/** Every font the renderer can use is under /fonts; declare them so live additions match the art. */
function injectFonts(fonts) {
  const css = fonts.filter((f) => f.family !== 'FiraGO').map((f) => `@font-face{font-family:"${String(f.family).replace(/["\\]/g, '')}";`
    + `src:url("/fonts/${encodeURIComponent(f.file)}");font-weight:${f.weight};font-style:${f.style};font-display:swap}`).join('\n');
  document.head.append(h('style', css));
  document.fonts?.ready.then(() => invalidate(true));
}

boot();
