// Admin panel: review suggestions for the public maps, fix or remove public additions, hide or delete maps, block users.
// English only — it is for the site's owner.

import { api, call } from './api.js';
import { session, setSession, renderAccount, signIn } from './session.js';
import { $, h, debounce } from './util.js';
import { setLang } from './i18n.js';
import { toast } from './ui.js';

const root = $('#admin');
let tab = 'submissions';
let subStatus = 'pending';
let query = '';

const when = (s) => (s ? new Date(s * 1000).toLocaleString() : '—');
const KIND = { place: 'Place', path: 'Path', note: 'Note' };

async function act(url, body, okMsg) {
  try {
    await call('POST', url, body);
    if (okMsg) toast(okMsg);
    await render();
  } catch (e) { toast(e.message || e.code, { tone: 'error' }); }
}

async function overview() {
  const o = await call('GET', '/api/admin/overview');
  const q = o.queues;
  const stat = (n, label) => h('div.stat', h('b', String(n)), h('span', label));
  return h('div.admin-stats',
    stat(o.pending, 'suggestions waiting'),
    stat(o.places.ready || 0, 'maps ready'),
    stat((o.places.queued || 0) + (o.places.fetching || 0) + (o.places.rendering || 0), 'maps being made'),
    stat(o.places.failed || 0, 'maps failed'),
    stat(o.users, 'users'),
    stat(`${q.fetch.running + q.fetch.queued} / ${q.render.running + q.render.queued}`, 'fetch / render jobs'),
    stat(`${o.disk_mb.data + o.disk_mb.out} MB`, `disk used · ${Math.round(o.free_mb / 1024)} GB free`));
}

function itemFields(s) {
  const it = s.item;
  const f = h('div.fields');
  const name = it.name != null ? h('input', { value: it.name, 'aria-label': 'Name', 'data-k': 'name' }) : null;
  const note = it.note != null ? h('textarea', { 'aria-label': 'Note', 'data-k': 'note' }, it.note) : null;
  const text = it.text != null ? h('textarea', { 'aria-label': 'Text', 'data-k': 'text' }, it.text) : null;
  f.append(...[name, note, text].filter(Boolean));
  return f;
}

function readFields(row) {
  const out = {};
  row.querySelectorAll('[data-k]').forEach((el) => { out[el.dataset.k] = el.value; });
  return out;
}

async function submissions() {
  const { submissions: list } = await call('GET', `/api/admin/submissions?status=${subStatus}`);
  const tools = h('div.admin-tools', h('select', { onchange: (e) => { subStatus = e.target.value; render(); } },
    ...['pending', 'approved', 'rejected', 'withdrawn'].map((s) => h('option', { value: s, selected: s === subStatus }, s))));
  if (!list.length) return [tools, h('p.muted', 'Nothing here.')];
  return [tools, h('div.admin-list', ...list.map((s) => {
    const it = s.item;
    const where = it.lon != null ? `${it.lat.toFixed(5)}, ${it.lon.toFixed(5)}` : `${it.coords?.length || 0} points, ${it.kind || ''}`;
    const row = h('div.arow',
      h('span'),
      h('div',
        h('h3', `${KIND[s.kind]} on `, h('a', { href: `/m/${s.slug}`, target: '_blank', rel: 'noopener' }, s.place_name_local || s.place_name),
          h('span.pill', { class: `pill ${s.status === 'approved' ? 'ok' : s.status === 'pending' ? 'wait' : 'bad'}` }, s.status)),
        h('p.meta', `by ${s.user_name || ''} <${s.email}> · ${when(s.created)} · ${where}${it.icon ? ` · ${it.icon}` : ''}`),
        s.status === 'pending' ? itemFields(s) : h('p.meta', [it.name, it.note, it.text].filter(Boolean).join(' — ')),
        s.admin_note ? h('p.meta', `note: ${s.admin_note}`) : null),
      s.status === 'pending' ? h('div.arow-actions',
        h('button.btn.btn-primary', { type: 'button', onclick: () => act(`/api/admin/submissions/${s.id}`, { action: 'approve', item: readFields(row) }, 'Approved — the public map is being redrawn.') }, 'Approve'),
        h('button.btn.btn-danger', { type: 'button', onclick: () => { const note = prompt('Reason (optional, shown to nobody but admins):') ?? null; if (note !== null) act(`/api/admin/submissions/${s.id}`, { action: 'reject', note }, 'Rejected.'); } }, 'Reject'))
        : h('span'));
    return row;
  }))];
}

async function publicEditor(slug, name) {
  const doc = await call('GET', `/api/admin/public/${slug}`);
  const all = [...doc.places.map((x) => ['places', x]), ...doc.paths.map((x) => ['paths', x]), ...doc.notes.map((x) => ['notes', x])];
  const dlg = h('div.admin-list');
  const save = async () => {
    try { await call('PUT', `/api/admin/public/${slug}`, doc); toast('Saved — the public map is being redrawn.'); } catch (e) { toast(e.message, { tone: 'error' }); }
  };
  if (!all.length) dlg.append(h('p.muted', 'No public additions on this map.'));
  for (const [k, it] of all) {
    const row = h('div.arow', h('span'),
      h('div', h('h3', `${k.slice(0, -1)} · ${it.id}`), itemFields({ item: it })),
      h('div.arow-actions',
        h('button.btn', { type: 'button', onclick: () => { Object.assign(it, readFields(row)); save(); } }, 'Save text'),
        h('button.btn.btn-danger', { type: 'button', onclick: () => { if (confirm('Remove this from the public map?')) { doc[k] = doc[k].filter((x) => x !== it); row.remove(); save(); } } }, 'Remove')));
    dlg.append(row);
  }
  return [h('div.admin-tools', h('button.btn', { type: 'button', onclick: () => render() }, '← Back to maps'), h('strong', { style: 'align-self:center' }, `Public additions on ${name}`)), dlg];
}

async function places() {
  const { places: list } = await call('GET', `/api/admin/places?q=${encodeURIComponent(query)}`);
  const tools = h('div.admin-tools', h('input', { type: 'search', placeholder: 'Search maps or creator e-mail', value: query,
    oninput: debounce((e) => { query = e.target.value; render(); }, 300) }));
  return [tools, h('div.admin-list', ...list.map((p) => {
    const pc = p.public_counts || {};
    const pub = (pc.places || 0) + (pc.paths || 0) + (pc.notes || 0);
    return h('div.arow',
      p.thumb ? h('img.arow-thumb', { src: p.thumb, alt: '' }) : h('span.arow-thumb'),
      h('div',
        h('h3', h('a', { href: `/m/${p.slug}`, target: '_blank', rel: 'noopener' }, p.name_local && p.name_local !== p.name ? `${p.name_local} / ${p.name}` : p.name),
          h('span.pill', { class: `pill ${p.status === 'ready' ? 'ok' : p.status === 'failed' ? 'bad' : 'wait'}` }, p.status),
          p.hidden ? h('span.pill.bad', 'hidden') : null),
        h('p.meta', `${p.slug} · ${p.lang} · size ${p.size} · by ${p.email || '—'} · ${when(p.created)} · ${pub} public additions`),
        h('p.meta', p.display_name),
        p.error ? h('p.meta', `error: ${p.error}`) : null),
      h('div.arow-actions',
        h('button.btn', { type: 'button', onclick: async () => { root.querySelector('.admin-body').replaceChildren(...(await publicEditor(p.slug, p.name))); } }, 'Public additions'),
        h('button.btn', { type: 'button', onclick: () => {
          const name = prompt('English name:', p.name); if (name === null) return;
          const local = prompt('Local-language name:', p.name_local || ''); if (local === null) return;
          act(`/api/admin/places/${p.slug}`, { action: 'rename', name, name_local: local }, 'Renamed — redrawing.');
        } }, 'Rename'),
        p.status === 'failed' ? h('button.btn', { type: 'button', onclick: () => act(`/api/admin/places/${p.slug}`, { action: 'retry' }, 'Queued again.') }, 'Retry') : null,
        p.status === 'ready' ? h('button.btn', { type: 'button', onclick: () => act(`/api/admin/places/${p.slug}`, { action: 'rerender' }, 'Redrawing in the background.') }, 'Redraw') : null,
        h('button.btn', { type: 'button', onclick: () => act(`/api/admin/places/${p.slug}`, { action: p.hidden ? 'unhide' : 'hide' }, p.hidden ? 'Visible again.' : 'Hidden.') }, p.hidden ? 'Unhide' : 'Hide'),
        h('button.btn.btn-danger', { type: 'button', onclick: () => { if (confirm(`Delete "${p.name}" with all its renders and every user's additions on it? This cannot be undone.`)) act(`/api/admin/places/${p.slug}`, { action: 'delete' }, 'Deleted.'); } }, 'Delete')));
  }))];
}

async function users() {
  const { users: list } = await call('GET', `/api/admin/users?q=${encodeURIComponent(query)}`);
  const tools = h('div.admin-tools', h('input', { type: 'search', placeholder: 'Search name or e-mail', value: query,
    oninput: debounce((e) => { query = e.target.value; render(); }, 300) }));
  return [tools, h('div.admin-list', ...list.map((u) => h('div.arow', h('span'),
    h('div', h('h3', u.name || u.email, u.is_admin ? h('span.pill.ok', 'admin') : null, u.banned ? h('span.pill.bad', 'blocked') : null),
      h('p.meta', `${u.email} · joined ${when(u.created)} · last seen ${when(u.last_seen)} · ${u.places} maps · ${u.submissions} suggestions`)),
    u.id === session.me.id ? h('span.muted', 'you') : h('div.arow-actions',
      u.banned
        ? h('button.btn', { type: 'button', onclick: () => act(`/api/admin/users/${u.id}`, { action: 'unban' }, 'Unblocked.') }, 'Unblock')
        : h('button.btn.btn-danger', { type: 'button', onclick: () => {
          if (!confirm(`Block ${u.email}? They can no longer sign in.`)) return;
          const purge = confirm('Also delete their private additions and reject their waiting suggestions?');
          act(`/api/admin/users/${u.id}`, { action: 'ban', purge }, 'Blocked.');
        } }, 'Block'),
      h('button.btn', { type: 'button', onclick: () => act(`/api/admin/users/${u.id}`, { action: u.is_admin ? 'unadmin' : 'admin' }, 'Updated.') }, u.is_admin ? 'Remove admin' : 'Make admin')))))];
}

async function render() {
  const tabs = h('div.admin-tabs', { role: 'tablist' }, ...[['submissions', 'Suggestions'], ['places', 'Maps'], ['users', 'Users']].map(([id, label]) =>
    h('button', { type: 'button', role: 'tab', 'aria-selected': String(tab === id), onclick: () => { tab = id; query = ''; render(); } }, label)));
  let body;
  try {
    body = tab === 'submissions' ? await submissions() : tab === 'places' ? await places() : await users();
    const stats = await overview();
    root.replaceChildren(h('h1', 'Admin'), h('p.muted', 'Approve what people suggest for the public maps, and remove what is wrong.'), stats, tabs, h('div.admin-body', ...body));
  } catch (e) {
    root.replaceChildren(h('p.admin-denied', e.message || 'Something went wrong.'));
  }
}

async function boot() {
  setLang('en');
  let info;
  try { info = await api.me(); } catch { root.replaceChildren(h('p.admin-denied', 'The site is not answering.')); return; }
  setSession(info);
  renderAccount($('#account'));
  if (!info.me) {
    root.replaceChildren(h('div.admin-denied', h('p', 'Sign in with the Google account listed in ADMIN_EMAILS.'), h('p', { style: 'margin-top:16px' },
      h('button.btn.btn-primary', { type: 'button', onclick: () => signIn('/admin') }, 'Sign in'))));
    return;
  }
  if (!info.me.admin) { root.replaceChildren(h('p.admin-denied', 'This account is not an admin.')); return; }
  render();
}

boot();
