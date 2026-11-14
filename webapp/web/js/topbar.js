// Top bar: home link + place name, style picker, language switch, save state, undo / redo, export, redraw, panel toggle.

import { S, bus, hasRender } from './state.js';
import { store } from './store.js';
import { $, h } from './util.js';
import { t, localName, onLang } from './i18n.js';
import { icon } from './icons.js';
import { menuButton, closeMenu, toast } from './ui.js';
import { api } from './api.js';
import { renderAccount } from './session.js';
import { isOpen, setPanel } from './panel.js';

let actions;

export function initTopbar(handlers) {
  actions = handlers;
  $('#pick-place').append(h('span.picker-value'));
  $('#pick-theme').append(h('span.picker-value'), h('span', { html: icon('chevron') }));
  $('#btn-undo').innerHTML = icon('undo');
  $('#btn-redo').innerHTML = icon('redo');
  $('#btn-panel').innerHTML = icon('panel');
  $('#btn-export').prepend(h('span', { html: icon('export') }));
  $('#btn-export').append(h('span', { html: icon('chevron') }));
  $('.brand').innerHTML = icon('logo');

  menuButton($('#pick-theme'), () => ({
    items: (S.server?.themes || []).map((th) => {
      const drawn = hasRender(th.id, S.lang);
      return {
        label: localName(th), sub: localName(th, 'description') || null, selected: th.id === S.theme,
        meta: t(drawn ? 'theme.drawn' : 'theme.notDrawn'), metaTone: drawn ? 'ok' : 'todo',
        onSelect: () => actions.theme(th.id),
      };
    }),
  }), { minWidth: 340 });

  menuButton($('#btn-export'), () => {
    const side = S.side;
    if (!side) return { items: [], empty: t('export.none') };
    const slug = S.place.slug;
    const mine = side._studio?.mine ? '1' : '0';
    const url = (fmt, paper = '') => api.exportUrl(slug, { theme: side.theme, lang: side.lang, fmt, paper, mine });
    const name = `${slug}-${side.theme}-${side.lang}`;
    return {
      items: [
        { label: t('export.png'), sub: t('export.pngSize'), href: url('png'), download: `${name}.png`, icon: 'export' },
        { label: t('export.jpg'), sub: t('export.size', { w: side.px[0], h: side.px[1] }), href: url('jpg'), download: `${name}.jpg`, icon: 'export' },
        side.svg && { label: t('export.svg'), sub: t('export.scalable'), href: url('svg'), download: `${name}.svg`, icon: 'export' },
        ...(side.svg ? [null, 'A4', 'A3', 'A2'].map((paper) => {
          const [pw, ph] = side.page_mm || [];
          const land = pw > ph;
          const dims = { A4: [210, 297], A3: [297, 420], A2: [420, 594] }[paper] || [pw, ph];
          const [w, hh] = paper && land ? [dims[1], dims[0]] : dims;
          return {
            label: paper ? t('export.pdfPaper', { paper }) : t('export.pdfPoster'),
            sub: w ? t('export.pdfSize', { w: Math.round(w), h: Math.round(hh) }) : t('export.scalable'),
            href: url('pdf', paper || ''),
            download: `${name}${paper ? `-${paper}` : ''}.pdf`, icon: 'export',
          };
        }) : []),
      ].filter(Boolean),
      note: store.needsRedraw ? t('export.stale') : null,
    };
  }, { role: 'menu', align: 'end', minWidth: 260 });

  for (const b of document.querySelectorAll('.lang-seg button')) {
    b.addEventListener('click', () => { if (!S.render.busy) actions.lang(b.dataset.lang); });
    b.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      const other = [...document.querySelectorAll('.lang-seg button')].find((x) => x !== b);
      other.focus(); other.click(); e.preventDefault();
    });
  }
  $('#btn-undo').addEventListener('click', () => store.undo());
  $('#btn-redo').addEventListener('click', () => store.redo());
  $('#btn-redraw').addEventListener('click', () => actions.redraw());
  $('#btn-panel').addEventListener('click', () => setPanel(!isOpen()));
  $('#save-state').addEventListener('click', () => { if (store.saveState === 'error' || store.saveState === 'dirty') store.save(); });

  bus.on('server place target side render save doc baked panel renderTick', render);
  bus.on('session', () => renderAccount($('#account')));
  onLang(() => renderAccount($('#account')));
  onLang(render);
  render();
}

function render() {
  const busy = S.render.busy;
  const place = S.place;
  $('#pick-place .picker-value').textContent = place ? (localName(place) || place.slug) : '—';
  const th = S.server?.themes.find((x) => x.id === S.theme);
  $('#pick-theme .picker-value').textContent = th ? localName(th) : '—';
  $('#pick-theme').disabled = busy || !S.server?.themes.length;
  if (busy) closeMenu();

  for (const b of document.querySelectorAll('.lang-seg button')) {
    const on = b.dataset.lang === S.lang;
    b.setAttribute('aria-checked', String(on));
    b.tabIndex = on ? 0 : -1;
    b.setAttribute('aria-disabled', String(busy));
  }

  const save = $('#save-state');
  save.dataset.state = store.saveState;
  save.querySelector('.save-text').textContent = t(`save.${store.saveState}`);
  save.disabled = !(store.saveState === 'error' || store.saveState === 'dirty');
  save.dataset.tip = store.saveState === 'error' ? 'save.retry' : `save.${store.saveState}`;
  save.hidden = !place;

  $('#btn-undo').disabled = !store.canUndo;
  $('#btn-redo').disabled = !store.canRedo;
  $('#btn-export').disabled = !S.side;

  const redraw = $('#btn-redraw');
  const needs = !!S.side && store.needsRedraw;
  redraw.classList.toggle('btn-primary', needs || busy);
  redraw.classList.toggle('is-busy', busy);
  redraw.disabled = busy || !place || !S.theme;
  redraw.dataset.tip = needs ? 'redraw.tipDirty' : 'redraw.tipClean';
  if (!S.side) delete redraw.dataset.tip;
  const secs = Math.max(0, Math.round((performance.now() - S.render.t0) / 1000));
  redraw.querySelector('.redraw-ic').innerHTML = busy ? '<span class="spinner"></span>' : icon('redraw');
  redraw.querySelector('.full').textContent = busy ? t('redraw.busy', { n: secs }) : t(S.side ? 'redraw.full' : 'state.notDrawn.action');
  redraw.querySelector('.short').textContent = busy ? t('redraw.busy', { n: secs }) : t(S.side ? 'redraw.short' : 'state.notDrawn.action');
  redraw.querySelector('.tiny').textContent = busy ? t('redraw.busy', { n: secs }) : t(S.side ? 'redraw.tiny' : 'state.notDrawn.action');
  redraw.setAttribute('aria-label', busy ? t('redraw.busy', { n: secs }) : t(S.side ? 'redraw.full' : 'state.notDrawn.action'));

  const panelBtn = $('#btn-panel');
  panelBtn.dataset.tip = isOpen() ? 'top.panelHide' : 'top.panelShow';
  panelBtn.setAttribute('aria-pressed', String(isOpen()));
  panelBtn.setAttribute('aria-label', t(panelBtn.dataset.tip));
}
