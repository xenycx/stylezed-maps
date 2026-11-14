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
      p.thumb ? h('img', { src: p.thumb, alt: '', loading: 'lazy', width: 480, height: 640 }) : '…'),
    h('div.card-name', cardName(p)),
    h('div.card-sub', p.display_name.split(', ').slice(1, 3).join(', ')))));
  if (reset) list.replaceChildren(...cards); else list.append(...cards);
  offset += res.places.length;
  $('#more').hidden = !res.more;
  const empty = $('#gallery-empty');
  empty.hidden = list.children.length > 0;
  empty.textContent = t(tab === 'mine' ? 'home.mineEmpty' : 'home.empty');
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
    b.addEventListener('click', () => { size = b.dataset.size; prefs.set('size', size); syncMake(); });
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
