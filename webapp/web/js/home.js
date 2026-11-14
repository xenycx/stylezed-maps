// Home page: find a place, make its map, browse the maps already made.

import { api, call } from './api.js';
import { session, setSession, renderAccount, signIn } from './session.js';
import { $, h, debounce } from './util.js';
import { t, setLang, applyI18n, onLang, uiLang } from './i18n.js';
import { toast } from './ui.js';

const prefs = {
  get(k) { try { return localStorage.getItem(`site.${k}`); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(`site.${k}`, v); } catch { /* private mode */ } },
};
const LOCAL_LANG = { ge: 'ka', de: 'de', at: 'de', ch: 'de', li: 'de' };

let info = null;          // /api/me
let results = [];         // Nominatim matches
let picked = null;
let size = prefs.get('size') || 'm';
const RADIUS = { s: 800, m: 1400, l: 2200, xl: 4500 };   // half the poster frame's width in metres (server: pipeline.SIZES)
const FRAME_RATIO = 1.13;                                  // frame height / width of the posters

// ---------------------------------------------------------------- frame picker: a small OpenStreetMap you drag
// so the poster's frame sits where you want it. Plain tiles, no library: a handful of <img> moved by a transform.
const TILE = 256;
const framer = { lat: 0, lon: 0, home: null, z: 14, built: false, imgs: new Map(), drag: null };

const wx = (lon, z) => (lon + 180) / 360 * TILE * 2 ** z;
const wy = (lat, z) => { const r = lat * Math.PI / 180; return (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * TILE * 2 ** z; };
const lonOf = (x, z) => x / (TILE * 2 ** z) * 360 - 180;
const latOf = (y, z) => { const n = Math.PI - 2 * Math.PI * y / (TILE * 2 ** z); return 180 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n))); };

function frameZoom(w) {
  // the zoom at which the frame's width takes about 55 % of the preview
  const mpp = (2 * RADIUS[size]) / (w * 0.55);
  return Math.max(3, Math.min(17, Math.floor(Math.log2(156543.03 * Math.cos(framer.lat * Math.PI / 180) / mpp))));
}

function drawFramer() {
  const box = $('#framer');
  const w = box.clientWidth, hgt = box.clientHeight;
  if (!w) return;
  const z = framer.z = frameZoom(w);
  const cx = wx(framer.lon, z), cy = wy(framer.lat, z);
  const left = cx - w / 2, top = cy - hgt / 2;
  const tiles = box.querySelector('.framer-tiles');
  const want = new Set();
  const n = 2 ** z;
  for (let tx = Math.floor(left / TILE); tx <= Math.floor((left + w) / TILE); tx++) {
    for (let ty = Math.floor(top / TILE); ty <= Math.floor((top + hgt) / TILE); ty++) {
      if (ty < 0 || ty >= n) continue;
      const key = `${z}/${((tx % n) + n) % n}/${ty}`;
      want.add(key);
      let img = framer.imgs.get(key);
      if (!img) {
        img = h('img', { src: `https://tile.openstreetmap.org/${key}.png`, alt: '', draggable: 'false', decoding: 'async', width: TILE, height: TILE });
        framer.imgs.set(key, img);
        tiles.append(img);
      }
      img.style.transform = `translate(${Math.round(tx * TILE - left)}px, ${Math.round(ty * TILE - top)}px)`;
    }
  }
  for (const [k, img] of framer.imgs) if (!want.has(k)) { img.remove(); framer.imgs.delete(k); }
  // the poster frame, always in the middle: its size follows the chosen map size
  const mpp = 156543.03 * Math.cos(framer.lat * Math.PI / 180) / 2 ** z;
  const fw = 2 * RADIUS[size] / mpp;
  const fb = box.querySelector('.framer-box');
  fb.style.width = `${fw}px`;
  fb.style.height = `${fw * FRAME_RATIO}px`;
  const moved = framer.home && (Math.abs(framer.lat - framer.home.lat) > 1e-5 || Math.abs(framer.lon - framer.home.lon) > 1e-5);
  $('#frame-reset').hidden = !moved;
}

function panFramer(dx, dy) {
  const z = framer.z;
  framer.lon = lonOf(wx(framer.lon, z) - dx, z);
  framer.lat = Math.max(-84, Math.min(84, latOf(wy(framer.lat, z) - dy, z)));
  drawFramer();
}

function initFramer() {
  if (framer.built) return;
  framer.built = true;
  const box = $('#framer');
  box.addEventListener('pointerdown', (e) => {
    framer.drag = { x: e.clientX, y: e.clientY, id: e.pointerId };
    box.setPointerCapture(e.pointerId);
    box.classList.add('is-dragging');
  });
  box.addEventListener('pointermove', (e) => {
    const d = framer.drag;
    if (!d || d.id !== e.pointerId) return;
    panFramer(e.clientX - d.x, e.clientY - d.y);
    d.x = e.clientX; d.y = e.clientY;
  });
  const end = () => { framer.drag = null; box.classList.remove('is-dragging'); };
  box.addEventListener('pointerup', end);
  box.addEventListener('pointercancel', end);
  box.addEventListener('keydown', (e) => {
    const step = e.shiftKey ? 80 : 24;
    const k = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key];
    if (k) { e.preventDefault(); panFramer(...k); }
  });
  $('#frame-reset').addEventListener('click', () => { Object.assign(framer, framer.home); drawFramer(); });
  window.addEventListener('resize', () => { if (!$('#make').hidden) drawFramer(); });
}

function centreFramer(lat, lon) {
  framer.home = { lat, lon };
  framer.lat = lat; framer.lon = lon;
  initFramer();
  requestAnimationFrame(drawFramer);
}
let tab = 'all';
let offset = 0;
let galleryToken = 0;

function setUi(lang) {
  setLang(lang);
  prefs.set('ui', lang);
  for (const b of document.querySelectorAll('.ui-lang button')) b.setAttribute('aria-checked', String(b.dataset.ui === lang));
  document.title = t('app.title');
}

// ---------------------------------------------------------------- search (in the visitor's browser, straight to Nominatim)

async function search(q) {
  const msg = $('#search-msg');
  msg.hidden = false; msg.textContent = t('home.searching');
  $('#make').hidden = true;
  const url = `https://nominatim.openstreetmap.org/search?${new URLSearchParams({
    q, format: 'jsonv2', limit: '6', addressdetails: '1', 'accept-language': uiLang() === 'ka' ? 'ka,en' : 'en',
  })}`;
  try {
    const res = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(res.statusText);
    results = (await res.json()).filter((r) => ['node', 'way', 'relation'].includes(r.osm_type));
  } catch {
    msg.textContent = t('home.searchFailed');
    return;
  }
  if (!results.length) { msg.textContent = t('home.noResults'); return; }
  msg.hidden = true;
  renderResults();
}

function renderResults() {
  const box = $('#results');
  box.replaceChildren(...results.map((r, i) => {
    const [first, ...rest] = r.display_name.split(', ');
    return h('label.result',
      h('input', { type: 'radio', name: 'pick', value: String(i), checked: i === 0, onchange: () => choose(i) }),
      h('div', h('b', first), h('span', rest.join(', '))));
  }));
  choose(0);
  $('#make').hidden = false;
}

function choose(i) {
  picked = results[i];
  centreFramer(Number(picked.lat), Number(picked.lon));
  const cc = picked.address?.country_code;
  const want = LOCAL_LANG[cc] || (uiLang() === 'ka' ? 'ka' : 'en');
  const sel = $('#map-lang');
  if (info.languages.includes(want)) sel.value = want;
  syncMake();
}

function renderLangs() {
  const sel = $('#map-lang');
  const cur = sel.value;
  sel.replaceChildren(...info.languages.map((code) => h('option', { value: code }, t(`langname.${code}`) === `langname.${code}` ? code : t(`langname.${code}`))));
  if (cur) sel.value = cur;
}

function syncMake() {
  for (const b of document.querySelectorAll('.size-seg button')) b.setAttribute('aria-checked', String(b.dataset.size === size));
  const me = session.me;
  const go = $('#go');
  const note = $('#make-note');
  if (!me) {
    go.textContent = t('auth.signIn');
    note.textContent = t('home.signToMake');
  } else {
    go.textContent = t('home.make');
    note.textContent = me.places_left == null ? '' : t('home.left', { n: me.places_left });
    go.disabled = me.places_left === 0;
  }
}

async function make() {
  if (!picked) return;
  if (!session.me) {
    prefs.set('pending', JSON.stringify({ q: $('#q').value }));
    signIn('/');
    return;
  }
  const go = $('#go');
  go.disabled = true; go.textContent = t('home.making');
  try {
    const res = await call('POST', '/api/places', {
      osm_type: picked.osm_type, osm_id: Number(picked.osm_id), size, lang: $('#map-lang').value,
      ...(framer.home && !$('#frame-reset').hidden ? { center: { lat: framer.lat, lon: framer.lon } } : {}),
    });
    location.href = `/m/${encodeURIComponent(res.slug)}`;
  } catch (e) {
    toast(e.message || e.code, { tone: 'error' });
    go.disabled = false; syncMake();
  }
}

// ---------------------------------------------------------------- gallery

function cardName(p) {
  return uiLang() === 'ka' && p.lang === 'ka' ? (p.name_local || p.name) : (p.name || p.name_local);
}

async function loadGallery(reset) {
  const token = ++galleryToken;
  if (reset) offset = 0;
  const q = $('#filter').value.trim();
  let res;
  try {
    res = await call('GET', `/api/places?${new URLSearchParams({ limit: '24', offset: String(offset), q, mine: tab === 'mine' ? '1' : '0' })}`);
  } catch { return; }
  if (token !== galleryToken) return;
  const list = $('#gallery');
  const cards = res.places.map((p) => h('li', h('a.card', { href: `/m/${encodeURIComponent(p.slug)}` },
    h('div.card-sheet', { class: `card-sheet${p.thumb ? '' : ' is-blank'}` },
      p.thumb ? h('img', { src: p.thumb, alt: '', loading: 'lazy', width: 480, height: 640 }) : ''),
    h('div.card-name', { lang: p.lang === 'ka' && uiLang() === 'ka' ? 'ka' : null }, cardName(p)),
    h('div.card-sub', p.display_name.split(', ').slice(1, 3).join(', ')))));
  if (reset) list.replaceChildren(...cards); else list.append(...cards);
  if (reset && tab === 'all' && !q) fillDesk(res.places);
  offset += res.places.length;
  $('#more').hidden = !res.more;
  const empty = $('#gallery-empty');
  empty.hidden = list.children.length > 0;
  empty.textContent = t(tab === 'mine' ? 'home.mineEmpty' : 'home.empty');
}

/** The three newest prints, laid on the desk beside the search. */
function fillDesk(places) {
  const desk = $('#desk');
  const prints = places.filter((p) => p.thumb).slice(0, 3);
  desk.replaceChildren(...prints.map((p, i) => h('a.print', {
    href: `/m/${encodeURIComponent(p.slug)}`, tabIndex: -1, style: `--i:${i}`,
  }, h('img', { src: p.thumb, alt: '', width: 480, height: 640, decoding: 'async' }))));
  desk.dataset.n = String(prints.length);
}

function setTab(id) {
  tab = id;
  $('#tab-all').setAttribute('aria-selected', String(id === 'all'));
  $('#tab-mine').setAttribute('aria-selected', String(id === 'mine'));
  loadGallery(true);
}

// ---------------------------------------------------------------- boot

async function boot() {
  const pre = prefs.get('ui') || ((navigator.language || '').startsWith('ka') ? 'ka' : 'en');
  setUi(pre);
  applyI18n(document);
  try { info = await api.me(); } catch { info = { me: null, languages: ['en'], google: false }; }
  setSession(info);
  renderAccount($('#account'));
  renderLangs();
  syncMake();
  onLang(() => { renderAccount($('#account')); renderLangs(); syncMake(); if (results.length) renderResults(); loadGallery(true); });

  for (const b of document.querySelectorAll('.ui-lang button')) b.addEventListener('click', () => setUi(b.dataset.ui));
  for (const b of document.querySelectorAll('.size-seg button')) {
    b.addEventListener('click', () => { size = b.dataset.size; prefs.set('size', size); syncMake(); if (framer.home) drawFramer(); });
  }
  $('#search').addEventListener('submit', (e) => { e.preventDefault(); const q = $('#q').value.trim(); if (q) search(q); });
  $('#go').addEventListener('click', make);
  $('#more').addEventListener('click', () => loadGallery(false));
  $('#filter').addEventListener('input', debounce(() => loadGallery(true), 250));
  $('#tab-all').addEventListener('click', () => setTab('all'));
  $('#tab-mine').addEventListener('click', () => setTab('mine'));
  $('#tab-mine').hidden = !session.me;

  const qs = new URLSearchParams(location.search);
  const login = qs.get('login');
  if (login === 'failed') toast(t('home.login.failed', { why: qs.get('why') || '' }), { tone: 'error' });
  if (login === 'banned') toast(t('home.login.banned'), { tone: 'error' });
  if (login) history.replaceState(null, '', '/');

  // came back from signing in with a search in progress: run it again
  const pending = prefs.get('pending');
  if (pending && session.me) {
    prefs.set('pending', '');
    try { const { q } = JSON.parse(pending); if (q) { $('#q').value = q; search(q); } } catch { /* ignore */ }
  }
  setTab(location.hash === '#mine' && session.me ? 'mine' : 'all');
}

boot();
