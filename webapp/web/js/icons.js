// Two icon systems:
//  1. UI icons — authored here, 20 px grid, one 1.5 px round stroke, currentColor.
//  2. Map icons — the project's class-coloured SVGs (CONTRACT.md), fetched, sanitised and inlined
//     so the surrounding `.lm` scope can colour them per theme.

import { esc } from './util.js';

const UI = {
  select: '<path d="M5 3.2l10.2 5.4-4.5 1.5-1.6 4.5z"/>',
  place: '<path d="M10 17.3s5-4.5 5-8.6a5 5 0 0 0-10 0c0 4.1 5 8.6 5 8.6z"/><circle cx="10" cy="8.6" r="1.7"/>',
  path: '<circle cx="4.8" cy="15.2" r="1.8"/><circle cx="15.2" cy="4.8" r="1.8"/><path d="M6.5 14.4c2.6-.9 1.2-3.9 3.6-4.9 2.2-.9 2.6-2.2 3.6-3.5"/>',
  note: '<path d="M4 16l.8-3.6 8.3-8.3a1.5 1.5 0 0 1 2.1 0l.7.7a1.5 1.5 0 0 1 0 2.1l-8.3 8.3z"/><path d="M11.7 5.5l2.8 2.8"/>',
  measure: '<path d="M3.4 13.3l9.9-9.9 3.3 3.3-9.9 9.9z"/><path d="M6.6 10.1l1.5 1.5M9 7.7l1.5 1.5M11.4 5.3l1.5 1.5"/>',
  plus: '<path d="M10 4.5v11M4.5 10h11"/>',
  minus: '<path d="M4.5 10h11"/>',
  fit: '<path d="M4 7.5V4h3.5M12.5 4H16v3.5M16 12.5V16h-3.5M7.5 16H4v-3.5"/>',
  actual: '<path d="M4.8 7.2l2-1.4v8.7M12.8 7.2l2-1.4v8.7M10 8.4v.01M10 12.2v.01"/>',
  undo: '<path d="M7.5 4.5L4 8l3.5 3.5"/><path d="M4 8h7.5a4 4 0 0 1 0 8H9"/>',
  redo: '<path d="M12.5 4.5L16 8l-3.5 3.5"/><path d="M16 8H8.5a4 4 0 0 0 0 8H11"/>',
  export: '<path d="M10 3.5v9M6.5 9.5L10 13l3.5-3.5M4 16.5h12"/>',
  type: '<path d="M3.5 15.5L7.6 4.5h.8l4.1 11M5 11.800h6"/><path d="M16.500 15.500v-4.300a2 2 0 0 0-3.700-1M16.500 13a1.900 1.900 0 1 1-3.800 0 1.900 1.900 0 0 1 3.800 0z"/>',
  panel: '<path d="M3.5 4.5h13v11h-13zM12 4.5v11"/>',
  chevron: '<path d="M5.5 8l4.5 4.5L14.5 8"/>',
  close: '<path d="M5.5 5.5l9 9M14.5 5.5l-9 9"/>',
  locate: '<circle cx="10" cy="10" r="4.6"/><path d="M10 2.5v2.9M10 14.6v2.9M2.5 10h2.9M14.6 10h2.9"/>',
  trash: '<path d="M4.5 6h11M8 6V4.5h4V6M6 6l.7 9.5h6.6L14 6M8.6 8.8v4.2M11.4 8.8v4.2"/>',
  check: '<path d="M4.5 10.5l3.5 3.5 7.5-8"/>',
  ascent: '<path d="M5.5 14.5l9-9M8 5.5h6.5V12"/>',
  descent: '<path d="M5.5 5.5l9 9M14.5 8v6.5H8"/>',
  clock: '<circle cx="10" cy="10" r="6.5"/><path d="M10 6.3V10l2.6 1.6"/>',
  length: '<path d="M3.5 10h13M3.5 6.8v6.4M16.5 6.8v6.4"/>',
  share: '<path d="M10 12.5V3.5M6.8 6.7L10 3.5l3.2 3.2"/><path d="M5.5 10.5H4.5v6h11v-6h-1"/>',
  logo: '<circle cx="10" cy="10" r="7"/><path d="M12.9 7.1l-1.7 4.1-4.1 1.7 1.7-4.1z"/>',
  alert: '<path d="M10 3.5l7 12.5H3z"/><path d="M10 8.5v3.4M10 14.1v.01"/>',
  redraw: '<path d="M16 10a6 6 0 1 1-1.9-4.4"/><path d="M16.2 3.6v3.6h-3.6"/>',
  landmark: '<path d="M4 16.5h12M5.5 16.5V9M14.5 16.5V9M8.5 16.5V9M11.5 16.5V9M3.8 9h12.4L10 4z"/>',
};

export function icon(name, cls = '') {
  return `<svg class="ic ${cls}" viewBox="0 0 20 20" aria-hidden="true">${UI[name] || ''}</svg>`;
}

// ---------------------------------------------------------------- map icons

const ALLOWED = new Set(['g', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline', 'polygon']);
const ATTRS = new Set(['class', 'd', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'x1', 'y1', 'x2', 'y2', 'points', 'width', 'height', 'transform']);
const CLASSES = new Set(['ink', 'thin', 'paper', 'tone', 'shade', 'accent', 'solid']);

const cache = new Map();    // url → markup string | null (missing / invalid)
const pending = new Map();  // url → promise
let onLoaded = () => {};

export function onIconLoaded(fn) { onLoaded = fn; }

/** "library/tent" | "landmark/cathedral" → URL of the SVG file. */
export function iconUrl(ref, slug) {
  if (!ref || typeof ref !== 'string') return null;
  const [kind, ...rest] = ref.split('/');
  const stem = rest.join('/').replace(/\.svg$/i, '');
  if (!/^[A-Za-z0-9_.-]+$/.test(stem)) return null;
  if (kind === 'library') return `/icons/library/${stem}.svg`;
  if (kind === 'landmark') return `/data/${slug}/icons/${stem}.svg`;
  return null;
}

function clean(node) {
  let out = '';
  for (const el of node.children) {
    const tag = el.localName;
    if (!ALLOWED.has(tag)) continue; // drops <style>, <text>, <use>, <image>, scripts…
    let attrs = '';
    for (const a of el.attributes) {
      if (!ATTRS.has(a.name)) continue; // drops fill/stroke/style/on*
      let v = a.value;
      if (a.name === 'class') v = v.split(/\s+/).filter((c) => CLASSES.has(c)).join(' ');
      attrs += ` ${a.name}="${esc(v)}"`;
    }
    out += `<${tag}${attrs}>${clean(el)}</${tag}>`;
  }
  return out;
}

async function fetchIcon(url) {
  try {
    const res = await fetch(url, { cache: 'no-cache' });
    if (!res.ok) return null;
    const doc = new DOMParser().parseFromString(await res.text(), 'image/svg+xml');
    const root = doc.documentElement;
    if (!root || root.localName !== 'svg' || doc.querySelector('parsererror')) return null;
    return clean(root) || null;
  } catch {
    return null;
  }
}

/** Cached, sanitised inner markup of an icon (viewBox 0 0 64 64), or null. Triggers a load when unknown. */
export function iconMarkup(ref, slug) {
  const url = iconUrl(ref, slug);
  if (!url) return null;
  if (cache.has(url)) return cache.get(url);
  if (!pending.has(url)) {
    pending.set(url, fetchIcon(url).then((m) => {
      cache.set(url, m);
      pending.delete(url);
      onLoaded(ref);
      return m;
    }));
  }
  return null;
}

export function loadIcon(ref, slug) {
  const url = iconUrl(ref, slug);
  if (!url) return Promise.resolve(null);
  if (cache.has(url)) return Promise.resolve(cache.get(url));
  iconMarkup(ref, slug);
  return pending.get(url);
}

/** After a redraw the icon files may have changed: re-read them, keeping the old drawing until the new one is in. */
export function revalidateIcons() {
  for (const url of [...cache.keys()]) {
    fetchIcon(url).then((m) => {
      if (m !== cache.get(url)) { cache.set(url, m); onLoaded(url); }
    });
  }
}

/** Standalone <svg> for chrome (cards, pickers): the icon on its own paper chip, default colours. */
export function iconSvg(markup, cls = '') {
  return `<svg class="lm ${cls}" viewBox="0 0 64 64" aria-hidden="true">${markup || FALLBACK_64}</svg>`;
}

/** Simple marker used when a place has no icon (or the file is missing). Drawn on the 64 grid, ground at (32, 60). */
export const FALLBACK_64 = '<path class="paper ink" d="M32 60C29 46 17 41 17 27a15 15 0 0 1 30 0c0 14-12 19-15 33z"/><circle class="accent" cx="32" cy="27" r="5.5"/>';
