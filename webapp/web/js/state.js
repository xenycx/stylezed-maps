// Shared app state and the event bus the modules talk over.
//
// Events: 'server' (api/state loaded) · 'place' · 'side' (displayed render changed) · 'doc' (additions changed)
//         'sel' (selection / active vertex / open landmark) · 'hover' · 'tool' · 'draft' · 'measure'
//         'save' (save state) · 'render' (render busy / failed) · 'baked' · 'profile' · 'view'

import { Emitter } from './util.js';

export const bus = new Emitter();

export const S = {
  server: null,      // /api/state payload
  place: null,       // entry of server.places
  theme: null,       // theme id the user wants
  lang: 'en',        // language the user wants (map + UI)
  side: null,        // sidecar of the render on screen (may lag behind theme/lang while drawing)
  proj: null,        // projection for S.side
  tool: 'select',
  sel: null,         // { type: 'place' | 'path' | 'note', id }
  vertex: null,      // active vertex index of the selected path
  lm: null,          // id of the landmark whose card is open
  hover: null,       // what the pointer is over (see tools.js hitTest)
  draft: null,       // { coords: [[lon, lat], …] } while a path is being drawn
  measure: [],       // [[lon, lat], …] throwaway measuring line
  showAll: false,    // draw baked additions on top of the art as well
  render: { busy: false, error: null, t0: 0, theme: null, lang: null },
  profileMark: null, // [lon, lat] highlighted from the elevation chart
};

export function themeById(id) {
  return S.server?.themes.find((th) => th.id === id) || null;
}

export function hasRender(theme, lang) {
  return !!S.place?.renders.some((r) => r.theme === theme && r.lang === lang);
}
