// Elevation profiles: fetch + cache from /api/profile, and the small chart.

import { api } from './api.js';
import { S, bus } from './state.js';
import { h, clamp } from './util.js';
import { t, fmtDist, fmtEle } from './i18n.js';
import { pointAlong } from './geo.js';

const cache = new Map();    // coords JSON → profile | { error }
const latest = new Map();   // owner → last good profile (shown while a newer one loads)
const timers = new Map();   // owner → { timer, ctrl }

/**
 * Profile for a line. Returns { data, fresh }: `data` may be the previous answer for this owner
 * while the exact one is still on its way (a 'profile' event follows when it lands).
 */
export function profileFor(owner, coords) {
  if (!S.place?.has_dem || !coords || coords.length < 2) return { data: null, fresh: true, unavailable: !S.place?.has_dem };
  const key = `${S.place.slug}|${JSON.stringify(coords)}`;
  const hit = cache.get(key);
  if (hit) {
    if (!hit.error) latest.set(owner, hit);
    return { data: hit.error ? null : hit, fresh: true, failed: !!hit.error };
  }
  const job = timers.get(owner);
  if (job?.key !== key) {
    if (job) { clearTimeout(job.timer); job.ctrl?.abort(); }
    const next = { key, ctrl: null, timer: 0 };
    next.timer = setTimeout(async () => {
      next.ctrl = new AbortController();
      try {
        const data = await api.profile(S.place.slug, coords, next.ctrl.signal);
        if (cache.size > 300) cache.clear();
        cache.set(key, data);
      } catch (e) {
        if (e.name === 'AbortError') return;
        cache.set(key, { error: e.code || 'error' });
      }
      if (timers.get(owner) === next) timers.delete(owner);
      bus.emit('profile', owner);
    }, 130);
    timers.set(owner, next);
  }
  return { data: latest.get(owner) || null, fresh: false };
}

export function forgetProfile(owner) { latest.delete(owner); }

/**
 * Draw the chart into `host`. One series, so no legend: a 2 px line over a soft area,
 * recessive baseline, min / max in text colour, and a crosshair that also marks the spot on the map.
 */
export function drawProfile(host, data, coords, opts = {}) {
  const W = opts.width || host.clientWidth || 280, H = opts.height || 84;
  const compact = !!opts.compact;
  const padL = compact ? 2 : 4, padR = compact ? 2 : 4, padT = compact ? 4 : 16, padB = compact ? 3 : 16;
  host.replaceChildren();
  if (!data || data.d.length < 2) { host.classList.add('is-empty'); return; }
  host.classList.remove('is-empty');
  const n = data.d.length, total = data.distance_m;
  let lo = data.min_ele, hi = data.max_ele;
  const span = Math.max(40, hi - lo);            // a flat walk should look flat
  const mid = (lo + hi) / 2;
  lo = mid - span / 2; hi = mid + span / 2;
  const X = (d) => padL + (d / total) * (W - padL - padR);
  const Y = (e) => padT + (1 - (e - lo) / (hi - lo)) * (H - padT - padB);
  let line = '';
  for (let i = 0; i < n; i += 1) line += `${i ? 'L' : 'M'}${X(data.d[i]).toFixed(1)} ${Y(data.ele[i]).toFixed(1)}`;
  const base = H - padB;
  const area = `${line}L${X(total).toFixed(1)} ${base}L${X(0).toFixed(1)} ${base}Z`;
  const svg = h('svg.profile-svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': `${t('profile.label')}: ${fmtEle(data.min_ele)} – ${fmtEle(data.max_ele)}` });
  svg.append(
    h('path.pf-area', { d: area }),
    h('line.pf-base', { x1: padL, x2: W - padR, y1: base + 0.5, y2: base + 0.5 }),
  );
  if (!compact) {
    for (const vd of (data.vertex_d || []).slice(1, -1)) {
      svg.append(h('line.pf-vertex', { x1: X(vd).toFixed(1), x2: X(vd).toFixed(1), y1: base - 3, y2: base + 0.5 }));
    }
  }
  svg.append(h('path.pf-line', { d: line }));
  const cross = h('g.pf-cross', { hidden: true }, h('line', { y1: padT - 6, y2: base }), h('circle', { r: 4 }));
  svg.append(cross);
  host.append(svg);
  if (!compact) {
    const iMax = data.ele.indexOf(Math.max(...data.ele));
    const hiLabel = h('span.pf-label.pf-hi', fmtEle(data.max_ele));
    hiLabel.style.left = `${clamp(X(data.d[iMax]) / W * 100, 8, 92)}%`;
    host.append(
      hiLabel,
      h('span.pf-label.pf-x0', `0`),
      h('span.pf-label.pf-x1', fmtDist(total)),
    );
  }
  const tip = h('div.pf-tip', { hidden: true });
  host.append(tip);

  const move = (e) => {
    const r = svg.getBoundingClientRect();
    const d = clamp(((e.clientX - r.left) / r.width * W - padL) / (W - padL - padR), 0, 1) * total;
    const i = clamp(Math.round(d / total * (n - 1)), 0, n - 1);
    const x = X(data.d[i]), y = Y(data.ele[i]);
    cross.removeAttribute('hidden');
    cross.firstChild.setAttribute('x1', x); cross.firstChild.setAttribute('x2', x);
    cross.lastChild.setAttribute('cx', x); cross.lastChild.setAttribute('cy', y);
    tip.hidden = false;
    tip.textContent = t('profile.at', { d: fmtDist(data.d[i]), e: fmtEle(data.ele[i]) });
    const tw = tip.offsetWidth;
    tip.style.left = `${clamp(x / W * r.width - tw / 2, 0, r.width - tw)}px`;
    if (coords && S.proj) { S.profileMark = pointAlong(S.proj, coords, data.d[i]); bus.emit('profileMark'); }
  };
  const leave = () => {
    cross.setAttribute('hidden', ''); tip.hidden = true;
    if (S.profileMark) { S.profileMark = null; bus.emit('profileMark'); }
  };
  svg.addEventListener('pointermove', move);
  svg.addEventListener('pointerdown', move);
  svg.addEventListener('pointerleave', leave);
  svg.addEventListener('pointercancel', leave);
}
