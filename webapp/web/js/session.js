// Who is signed in, and the account button shared by every page.

import { api } from './api.js';
import { h } from './util.js';
import { t } from './i18n.js';

export const session = { me: null, google: false, dev: false };

export function setSession(data) {
  session.me = data?.me || null;
  session.google = !!data?.google;
  session.dev = !!data?.dev_login;
}

export function signIn(next = location.pathname + location.search) {
  if (session.google) { location.href = `/auth/google?next=${encodeURIComponent(next)}`; return; }
  if (session.dev) {
    const email = prompt('DEV LOGIN (local testing only) — e-mail:', 'me@example.com');
    if (email) location.href = `/auth/dev?email=${encodeURIComponent(email)}&next=${encodeURIComponent(next)}`;
    return;
  }
  alert(t('auth.notConfigured'));
}

export async function signOut() {
  try { await api.logout(); } catch { /* the cookie is gone either way on reload */ }
  location.reload();
}

/** Fills `el` with a "Sign in with Google" button, or the visitor's avatar and a small menu. */
export function renderAccount(el, { onMenu } = {}) {
  el.replaceChildren();
  const me = session.me;
  if (!me) {
    el.append(h('button.btn.btn-quiet.account-in', { type: 'button', onclick: () => signIn() },
      h('span.g-mark', { 'aria-hidden': 'true', html: G_MARK }), h('span', t('auth.signIn'))));
    return;
  }
  const initials = (me.name || me.email || '?').trim().slice(0, 1).toUpperCase();
  const face = me.picture
    ? h('img.avatar', { src: me.picture, alt: '', referrerpolicy: 'no-referrer', width: 26, height: 26 })
    : h('span.avatar.avatar-letter', initials);
  const btn = h('button.account-btn', { type: 'button', 'aria-haspopup': 'menu', 'aria-expanded': 'false', title: me.email }, face);
  const menu = h('div.account-menu', { role: 'menu', hidden: true },
    h('div.account-who', h('strong', me.name || me.email), h('span', me.email)),
    h('a', { role: 'menuitem', href: '/#mine' }, t('auth.myMaps')),
    me.admin ? h('a', { role: 'menuitem', href: '/admin' }, t('auth.admin')) : null,
    h('button', { type: 'button', role: 'menuitem', onclick: signOut }, t('auth.signOut')));
  const close = (e) => {
    if (e && el.contains(e.target)) return;
    menu.hidden = true; btn.setAttribute('aria-expanded', 'false');
    document.removeEventListener('pointerdown', close, true);
  };
  btn.addEventListener('click', () => {
    const open = menu.hidden;
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
    if (open) { document.addEventListener('pointerdown', close, true); onMenu?.(); }
  });
  menu.addEventListener('keydown', (e) => { if (e.key === 'Escape') { close(); btn.focus(); } });
  el.append(btn, menu);
}

const G_MARK = '<svg viewBox="0 0 18 18" width="16" height="16"><path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92a8.78 8.78 0 0 0 2.68-6.62z"/><path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"/><path fill="#FBBC05" d="M3.97 10.72A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.18.29-1.72V4.95H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.05z"/><path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"/></svg>';
