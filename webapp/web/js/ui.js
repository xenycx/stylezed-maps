// Small shared UI pieces: toasts, tooltips, popover menus.

import { h } from './util.js';
import { t } from './i18n.js';
import { icon } from './icons.js';

// ---------------------------------------------------------------- toasts

let toastHost;

export function toast(message, opts = {}) {
  toastHost ||= document.getElementById('toasts');
  const el = h('div.toast', { role: 'status' }, h('span', message));
  let timer = 0;
  const close = () => {
    clearTimeout(timer);
    el.classList.add('is-leaving');
    setTimeout(() => el.remove(), 180);
  };
  if (opts.action) {
    el.append(h('button.toast-action', { type: 'button', onclick: () => { opts.onAction?.(); close(); } }, opts.action));
  }
  while (toastHost.children.length >= 2) toastHost.firstChild.remove();
  toastHost.append(el);
  timer = setTimeout(close, opts.duration || (opts.action ? 7000 : 4200));
  return close;
}

// ---------------------------------------------------------------- tooltips
// Any element with data-tip="<i18n key>" (and optionally data-keys="V", data-tip-pos="right|left|bottom").

let tipEl, tipTimer = 0, tipTarget = null;

export function initTooltips() {
  tipEl = document.getElementById('tip');
  document.addEventListener('pointerover', (e) => {
    if (e.pointerType === 'touch') return;
    const target = e.target.closest?.('[data-tip]');
    if (target === tipTarget) return;
    hideTip();
    if (target) { tipTarget = target; tipTimer = setTimeout(() => showTip(target), 380); }
  });
  document.addEventListener('pointerdown', hideTip, true);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideTip(); }, true);
  document.addEventListener('focusin', (e) => {
    const target = e.target.closest?.('[data-tip]');
    if (target && target.matches(':focus-visible')) { hideTip(); tipTarget = target; showTip(target); }
  });
  document.addEventListener('focusout', hideTip);
  window.addEventListener('blur', hideTip);
}

function hideTip() {
  clearTimeout(tipTimer);
  tipTarget = null;
  if (tipEl) tipEl.hidden = true;
}

function showTip(target) {
  if (!target.isConnected) return;
  const text = target.dataset.tipText || t(target.dataset.tip);
  tipEl.replaceChildren(h('span', text));
  if (target.dataset.keys) {
    for (const key of target.dataset.keys.split(' ')) tipEl.append(h('kbd', key));
  }
  tipEl.hidden = false;
  const r = target.getBoundingClientRect();
  const w = tipEl.offsetWidth, hh = tipEl.offsetHeight;
  const pos = target.dataset.tipPos || 'bottom';
  let x, y;
  if (pos === 'right') { x = r.right + 8; y = r.top + r.height / 2 - hh / 2; }
  else if (pos === 'left') { x = r.left - w - 8; y = r.top + r.height / 2 - hh / 2; }
  else if (pos === 'top') { x = r.left + r.width / 2 - w / 2; y = r.top - hh - 8; }
  else { x = r.left + r.width / 2 - w / 2; y = r.bottom + 8; }
  if (x + w > innerWidth - 6 && pos === 'right') x = r.left - w - 8;
  x = Math.min(innerWidth - w - 6, Math.max(6, x));
  y = Math.min(innerHeight - hh - 6, Math.max(6, y));
  tipEl.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
}

// ---------------------------------------------------------------- popover menu

let openMenu = null;

export function closeMenu() { openMenu?.close(); }

/**
 * Turn `button` into a menu button. `build()` returns
 *   { items: [{ label, sub, meta, selected, href, download, onSelect, lang }], note, role }
 * and is called each time the menu opens, so it always reflects current state.
 */
export function menuButton(button, build, opts = {}) {
  button.setAttribute('aria-haspopup', opts.role || 'listbox');
  button.setAttribute('aria-expanded', 'false');

  const open = (focusIndex) => {
    closeMenu();
    const spec = build();
    const role = opts.role || 'listbox';
    const menu = h('div.menu', { role, tabindex: '-1' });
    const els = spec.items.map((it) => {
      const tag = it.href ? 'a.menu-item' : 'button.menu-item';
      const el = h(tag, {
        type: it.href ? null : 'button', href: it.href, download: it.download,
        role: role === 'listbox' ? 'option' : 'menuitem',
        'aria-selected': role === 'listbox' ? String(!!it.selected) : null,
        class: `menu-item${it.selected ? ' is-selected' : ''}`,
        lang: it.lang,
        onclick: () => { close(true); it.onSelect?.(); },
      },
      h('span.menu-check', { html: it.selected ? icon('check') : (it.icon ? icon(it.icon) : '') }),
      h('span.menu-text', h('span.menu-label', it.label), it.sub ? h('span.menu-sub', it.sub) : null),
      it.meta ? h('span.menu-meta', { class: `menu-meta${it.metaTone ? ` is-${it.metaTone}` : ''}` }, it.meta) : null);
      return el;
    });
    menu.append(...els);
    if (spec.note) menu.append(h('p.menu-note', spec.note));
    if (!els.length && spec.empty) menu.append(h('p.menu-note', spec.empty));
    document.getElementById('app').append(menu);

    const r = button.getBoundingClientRect();
    const w = Math.max(menu.offsetWidth, opts.minWidth || r.width);
    menu.style.minWidth = `${Math.min(w, innerWidth - 16)}px`;
    let x = opts.align === 'end' ? r.right - menu.offsetWidth : r.left;
    x = Math.min(innerWidth - menu.offsetWidth - 8, Math.max(8, x));
    menu.style.transform = `translate(${Math.round(x)}px, ${Math.round(r.bottom + 6)}px)`;
    menu.style.maxHeight = `${innerHeight - r.bottom - 18}px`;

    const focusAt = (i) => { if (els.length) els[(i + els.length) % els.length].focus(); };
    const onKey = (e) => {
      const i = els.indexOf(document.activeElement);
      if (e.key === 'ArrowDown') { focusAt(i + 1); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { focusAt(i < 0 ? els.length - 1 : i - 1); e.preventDefault(); }
      else if (e.key === 'Home') { focusAt(0); e.preventDefault(); }
      else if (e.key === 'End') { focusAt(els.length - 1); e.preventDefault(); }
      else if (e.key === 'Escape') { close(true); e.preventDefault(); e.stopPropagation(); }
      else if (e.key === 'Tab') { close(false); }
    };
    const onOutside = (e) => { if (!menu.contains(e.target) && !button.contains(e.target)) close(false); };
    menu.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onOutside, true);
    window.addEventListener('resize', onResize);
    function onResize() { close(false); }
    function close(refocus) {
      if (openMenu?.menu !== menu) return;
      openMenu = null;
      menu.remove();
      document.removeEventListener('pointerdown', onOutside, true);
      window.removeEventListener('resize', onResize);
      button.setAttribute('aria-expanded', 'false');
      if (refocus) button.focus();
    }
    openMenu = { menu, close: () => close(false) };
    button.setAttribute('aria-expanded', 'true');
    const sel = spec.items.findIndex((it) => it.selected);
    if (focusIndex != null) focusAt(focusIndex === -1 ? els.length - 1 : (sel >= 0 ? sel : 0));
    else menu.focus();
  };

  button.addEventListener('click', () => {
    if (button.getAttribute('aria-expanded') === 'true') closeMenu(); else open(0);
  });
  button.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { open(0); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { open(-1); e.preventDefault(); }
  });
}
