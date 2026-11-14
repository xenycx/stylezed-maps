// Contextual bar at the bottom of the map: what the active tool expects, and live figures while drawing.

import { S, bus } from './state.js';
import { h, isCoarse } from './util.js';
import { t, fmtDist, onLang } from './i18n.js';
import { lineLength } from './geo.js';
import { profileFor, drawProfile, forgetProfile } from './profile.js';
import { kindPicker, fillStats } from './panel.js';
import { finishDraft, cancelDraft, setDraftKind, clearMeasure, setTool } from './tools.js';

let el, mode = null, parts = null;

export function initHud(hudEl) {
  el = hudEl;
  bus.on('tool draft measure side', render);
  bus.on('profile', (owner) => { if (owner === 'draft') render(); });
  onLang(() => { mode = null; render(); });
  render();
}

function build(next) {
  mode = next;
  parts = {};
  el.replaceChildren();
  if (next === 'path') {
    parts.hint = h('p.hud-hint');
    parts.stats = h('dl.stats.stats-row');
    parts.chart = h('div.profile.profile-compact');
    parts.kind = kindPicker((k) => { setDraftKind(k); });
    parts.finish = h('button.btn.btn-primary', { type: 'button', onclick: finishDraft, 'data-tip': 'hud.finish', 'data-keys': 'Enter', 'data-tip-pos': 'top' }, t('hud.finish'));
    parts.cancel = h('button.btn', { type: 'button', onclick: () => { cancelDraft(); setTool('select'); }, 'data-tip': 'hud.cancel', 'data-keys': 'Esc', 'data-tip-pos': 'top' }, t('hud.cancel'));
    parts.live = h('div.hud-live', parts.stats, parts.chart);
    el.append(parts.hint, parts.live, h('div.hud-actions', parts.kind.el, h('span.spacer'), parts.cancel, parts.finish));
  } else if (next === 'measure') {
    parts.hint = h('p.hud-hint');
    parts.value = h('p.hud-value');
    parts.clear = h('button.btn', { type: 'button', onclick: clearMeasure }, t('hud.clear'));
    el.append(parts.hint, h('div.hud-line', parts.value, parts.clear));
  } else if (next) {
    el.append(h('p.hud-hint', t(`hud.${next}`)));
  }
}

function render() {
  const want = !S.proj || S.tool === 'select' ? null : S.tool;
  if (want !== mode) build(want);
  el.hidden = !want;
  if (want !== 'path') forgetProfile('draft');
  if (want === 'path') {
    const coords = S.draft?.coords || [];
    const n = coords.length;
    parts.kind.sync(S.draft?.kind || S.kind);
    parts.hint.textContent = n === 0 ? t('hud.path.start')
      : n === 1 ? t('hud.path.second')
        : isCoarse() ? '' : t('hud.path.keys');
    parts.hint.hidden = !parts.hint.textContent;
    parts.live.hidden = n < 2;
    parts.finish.disabled = n < 2;
    parts.cancel.hidden = false;
    if (n >= 2) {
      const res = profileFor('draft', coords);
      fillStats(parts.stats, lineLength(S.proj, coords), res.data, false);
      parts.stats.classList.toggle('is-stale', !res.fresh);
      parts.chart.hidden = !res.data;
      if (res.data && parts.drawn !== res.data) {
        parts.drawn = res.data;
        drawProfile(parts.chart, res.data, coords, { height: 44, compact: true });
      }
    }
  } else if (want === 'measure') {
    const n = S.measure.length;
    parts.hint.hidden = n >= 2;
    parts.hint.textContent = t('hud.measure.start');
    parts.value.parentElement.hidden = n < 2;
    if (n >= 2) parts.value.replaceChildren(h('span', `${t('hud.measure.total')} `), h('strong', fmtDist(lineLength(S.proj, S.measure))));
  }
}
