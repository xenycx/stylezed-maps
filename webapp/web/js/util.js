// Small DOM + event helpers shared by every module.

const SVG_NS = 'http://www.w3.org/2000/svg';
const SVG_TAGS = new Set(['svg', 'g', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline', 'polygon', 'text', 'tspan', 'defs', 'clipPath']);

/** h('button.cls', {onclick, 'aria-label': …}, child, …) → element. Strings become text nodes. */
export function h(spec, attrs, ...kids) {
  const [tag, ...classes] = spec.split('.');
  const el = SVG_TAGS.has(tag) ? document.createElementNS(SVG_NS, tag) : document.createElement(tag || 'div');
  if (classes.length) el.setAttribute('class', classes.join(' '));
  if (attrs && (attrs instanceof Node || typeof attrs !== 'object' || Array.isArray(attrs))) {
    kids.unshift(attrs);
    attrs = null;
  }
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'html') el.innerHTML = v;
    else if (k === 'hidden') el.toggleAttribute('hidden', !!v);
    else if (k === 'value' || k === 'checked' || k === 'disabled') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, kids);
  return el;
}

function append(el, kids) {
  for (const k of kids) {
    if (k == null || k === false) continue;
    if (Array.isArray(k)) append(el, k);
    else el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}

export const $ = (sel, root = document) => root.querySelector(sel);

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export class Emitter {
  constructor() { this.map = new Map(); }
  on(type, fn) {
    for (const ty of type.split(' ')) {
      if (!this.map.has(ty)) this.map.set(ty, new Set());
      this.map.get(ty).add(fn);
    }
    return this;
  }
  emit(type, payload) {
    this.map.get(type)?.forEach((fn) => fn(payload));
  }
}

export function debounce(fn, ms) {
  let id = 0;
  const wrapped = (...args) => { clearTimeout(id); id = setTimeout(() => fn(...args), ms); };
  wrapped.cancel = () => clearTimeout(id);
  return wrapped;
}

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
export const isCoarse = () => matchMedia('(pointer: coarse)').matches;
export const isNarrow = () => matchMedia('(max-width: 760px)').matches;

export function isTyping(target = document.activeElement) {
  if (!target) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

/** Stable JSON: object keys sorted, so two equal items always serialise the same. */
export function canon(v) {
  if (Array.isArray(v)) return `[${v.map(canon).join(',')}]`;
  if (v && typeof v === 'object') {
    return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${canon(v[k])}`).join(',')}}`;
  }
  return JSON.stringify(v ?? null);
}

/** Keyed list reconciliation that never moves a node that is already in the right place (keeps input focus). */
export function reconcile(container, items, keyOf, create, update) {
  const existing = new Map();
  for (const el of [...container.children]) existing.set(el.dataset.key, el);
  let i = 0;
  for (const item of items) {
    const key = String(keyOf(item));
    let el = existing.get(key);
    if (el) existing.delete(key);
    else { el = create(item); el.dataset.key = key; }
    update(el, item);
    if (container.children[i] !== el) container.insertBefore(el, container.children[i] || null);
    i += 1;
  }
  existing.forEach((el) => el.remove());
}
