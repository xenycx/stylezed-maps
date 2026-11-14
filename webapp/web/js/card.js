// Landmark card: opens next to the hotspot (a bottom sheet on phones).

import { S, bus } from './state.js';
import { h, isNarrow } from './util.js';
import { t, localName, fmtNum, onLang } from './i18n.js';
import { icon, iconMarkup, iconSvg } from './icons.js';
import { closeLandmark, startPathAt, landmarkLonLat } from './tools.js';

let el, view, current = null;

export function initCard(cardEl, v) {
  el = cardEl;
  view = v;
  bus.on('sel side lmEle iconLoaded', render);
  bus.on('view', position);
  onLang(render);
}

function landmark() {
  return S.lm ? S.side?.landmarks?.find((l) => l.id === S.lm) || null : null;
}

function elevation(lm) {
  const known = S.place?.landmarks?.find((x) => x.id === lm.id)?.ele;
  return Number.isFinite(known) ? known : S.lmEle?.get(lm.id);
}

function render() {
  const lm = landmark();
  if (!lm) { el.hidden = true; current = null; return; }
  const markup = lm.icon ? iconMarkup(`landmark/${lm.icon}`, S.place.slug) : null;
  const ele = elevation(lm);
  const blurb = localName(lm, 'blurb');
  const title = h('h2', { id: 'card-title' }, localName(lm) || lm.id);
  el.replaceChildren(
    h('div.card-top',
      h('span.chip.chip-lg', { html: iconSvg(markup) }),
      h('div.card-head', title, Number.isFinite(ele) ? h('p.card-ele', t('lm.elevation', { n: fmtNum(ele) })) : null),
      h('button.icon-btn.card-close', { type: 'button', 'data-tip': 'lm.close', 'aria-label': t('lm.close'), html: icon('close'), onclick: closeLandmark })),
    blurb ? h('p.card-blurb', blurb) : null,
    h('div.card-actions',
      h('button.btn.btn-primary', { type: 'button', onclick: () => startPathAt(landmarkLonLat(lm)) },
        h('span', { html: icon('path') }), h('span', t('lm.startPath')))));
  const fresh = current !== lm.id;
  current = lm.id;
  el.hidden = false;
  if (fresh) { el.classList.remove('is-in'); requestAnimationFrame(() => el.classList.add('is-in')); }
  position();
}

function position() {
  const lm = landmark();
  if (!lm || el.hidden) return;
  if (isNarrow()) { el.style.transform = ''; return; }
  const [sx, sy] = view.toScreen(lm.x, lm.y);
  const r = Math.max((lm.r || 40) * view.k, 18);
  const w = el.offsetWidth, hh = el.offsetHeight, a = view.avail, gap = 14;
  let x = sx + r + gap;
  if (x + w > a.x + a.w - 4) x = sx - r - gap - w;
  let y = sy - hh / 2;
  if (x < a.x + 4) { x = sx - w / 2; y = sy + r + gap; }
  x = Math.min(a.x + a.w - w - 4, Math.max(a.x + 4, x));
  y = Math.min(view.sh - hh - 10, Math.max(10, y));
  el.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
}
