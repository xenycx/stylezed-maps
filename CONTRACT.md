# Data contract (renderer ⇄ icons ⇄ web studio)

All paths are relative to the project root. `<slug>` is the place id (e.g. `nikortsminda`).

## Inputs produced by the pipeline
| file | what |
|---|---|
| `data/<slug>/meta.json` | geocode result, `lat`/`lon` of the place, `center_lat`/`center_lon` + `radius` of the frame, `bbox` `[s,w,n,e]` |
| `data/<slug>/layers.json` | OSM layers as GeoJSON FeatureCollections (buildings, roads, tracks, paths, waterways, water, landcover, pois, places) |
| `data/<slug>/dem.npy` + `dem.json` | elevation grid (float32 metres) + `bounds` `[w,s,e,n]`; rows are linear in Web-Mercator y |
| `data/<slug>/candidates.json` | landmark candidates from `discover.py` |

## Landmarks — one bespoke icon each
`data/<slug>/landmarks.json`
```json
{ "landmarks": [ {
    "id": "cathedral",                     // kebab-case, unique
    "name": "Nikortsminda Cathedral",      // English / Latin-script name
    "name_local": "ნიკორწმინდის ტაძარი",     // local-script name or null
    "lon": 43.0881, "lat": 42.4592,
    "kind": "cathedral",                   // free text category
    "icon": "cathedral.svg",               // file in data/<slug>/icons/ — NEVER shared by two landmarks
    "blurb": "11th-century cross-dome church famed for its carved stone façades.",  // ≤ 160 chars, factual
    "blurb_local": "XI საუკუნის ჯვარგუმბათოვანი ტაძარი …",                           // same sentence in the local language
    "rank": 1,                             // 1 = hero (drawn largest) … 3 = minor
    "osm": "w712271284"                    // optional source id
} ] }
```
Optional per landmark: `"label"` / `"label_local"` — the text beside the icon on the map when it should differ from the
name (`""` = icon only; the index still lists the full name); `"force_label"` — draw the label even where it collides
(default: true for rank 1). A file with `"auto": true` was written by the site's `webapp/landmarks_auto.py`, which may
rewrite it; icons there come from `icons/auto/` and may repeat by kind.

### Icon files (`data/<slug>/icons/*.svg` and `icons/library/*.svg`)
* `viewBox="0 0 64 64"`, no width/height, no text, no gradients, no filters, no images, no `<use>`.
* Only `g path circle ellipse rect line polyline polygon`. No inline `style=`, no `fill=`/`stroke=` attributes: **colour comes only from classes** so every theme can recolour the icon:

| class | role | default (standalone preview) |
|---|---|---|
| `ink` | outline stroke, no fill | stroke `#2b2118`, width 2.2, round caps/joins |
| `ink thin` | secondary detail stroke | width 1.2 |
| `paper` | light body fill | `#fbf3e0` |
| `tone` | mid-tone fill | `#d9bf94` |
| `shade` | dark fill | `#5b4632` |
| `accent` | the one spot of colour | `#b3402e` |
| `solid` | fill in ink colour, no stroke | `#2b2118` |

  Classes combine: `class="paper ink"` = paper fill + ink outline.
* Each file carries exactly one `<style>` block with those defaults (copy it from `icons/_style.css`) so the file previews on its own. Renderers strip it and inject the theme's colours under a `.lm` scope.
* The subject stands on a ground point at **(32, 60)** — that point is pinned to the landmark's coordinates. Keep everything inside x 4–60, y 4–60.
* Must stay legible at 9 mm on paper (≈ 70 px): silhouette first, ≤ 30 elements, no hairline detail.

`icons/library/*.svg` — generic icons (same spec) the user can pick for places they add in the studio. `icons/library/index.json` = `[{"id":"tent","label":"Camp"}, …]`.

## User additions (written by the studio, drawn by the renderer)
`data/<slug>/custom.json`
```json
{ "places": [ { "id": "p-1", "name": "Grandma's house", "note": "", "lon": 43.09, "lat": 42.46,
                "icon": "library/house",              // "library/<id>" or "landmark/<file-stem>"
                "size": 1.5 } ],                      // optional, 0.5–2.5 × the style's place size (default 1)
  "paths":  [ { "id": "r-1", "name": "Walk to the ice cave", "kind": "trail",   // trail | road | route
                "coords": [[43.088, 42.460], [43.08, 42.462]] } ],
  "notes":  [ { "id": "n-1", "text": "Best light at sunset", "lon": 43.07, "lat": 42.47 } ] }
```
Missing file = no additions. Unknown keys must be preserved on save.
`Poster(..., custom_path=FILE)` (atlas/render.py) bakes another file of this shape instead — the public site (`webapp/`)
keeps one document per visitor and passes the merged one; the default is `data/<slug>/custom.json`.

## Language
A map is rendered in ONE language, never bilingual: `en` (English/Latin) or the local language code (`ka` for
Georgia). Every piece of text on the map follows it: title, labels, legend, notes. `meta.json` may carry a default
`"lang"`; the CLI flag wins. The engine's own words (legend, units, attribution) come from `i18n/<lang>.json`
(English fallback); feature names come from `name` (English) / `name_local` (the fetch language) in `layers.json`.

## The user's own fonts
`data/<slug>/fonts.json` — which font replaces a theme's font *role*, per language. Written by the studio's Fonts menu
or `fonts.py set`; read by every render of that place. `"*"` applies to all themes; a theme id wins over it.
```json
{ "ka": { "*": { "display": "BPG Nino Mtavruli" }, "storybook": { "text": "FiraGO" } } }
```
Font files live in the project's `fonts/` folder (`fonts.py add <file>` or the studio's "Add a font file…").

## Render command
```
uv run poster.py <slug> --style <theme-id> --lang <en|ka> [--png-width 3000]
                  [--font ROLE="Family"]…     one-off font for a theme font role
                  [--pdf [A4|A3|letter|WxH]]  also a vector PDF: poster size, or fitted to paper → <theme>.<lang>[.A4].pdf
                  [--pdf-only]                make the PDF from the existing render without redrawing
```
Themes are `styles/<theme-id>.json` (`name`, `description`, and `name_local`, `description_local` for the local-language UI). Exit code 0 on success. Writes to `out/<slug>/`
with basename `<theme>.<lang>` (e.g. `hiking.ka`):
`.svg` (vector), `.png` (print), `.jpg` (studio image, same pixel size), `.json` (sidecar):

```json
{ "slug": "nikortsminda", "theme": "hiking", "theme_name": "Hiking / topographic", "lang": "ka",
  "image": "hiking.ka.jpg", "print": "hiking.ka.png", "svg": "hiking.ka.svg",
  "px": [3000, 4040],                       // image size
  "frame_px": [121.2, 484.8, 2757.6, 3030.3], // x, y, w, h of the map frame inside the image
  "center": [43.0872, 42.4645],             // lon, lat at the centre of the frame
  "m_per_px": 1.494,                        // ground metres per image pixel
  "m_per_deg": [82245.5, 111082.4],         // metres per degree of lon / lat at the centre
  "place": { "name": "Nikortsminda", "name_local": "ნიკორწმინდა" },
  "overlay": {                              // how the studio should draw live (un-baked) additions
    "path":  { "stroke": "#d7261e", "width_px": 4, "dash": [10, 6], "casing": { "stroke": "#fff", "width_px": 7 } },
    "place": { "color", "paper", "tone", "shade", "accent", "halo",       // icon colour roles
               "font", "font_px", "font_weight", "font_style", "label_color", "label_halo", "size_px" },
    "note":  { "color", "halo", "font", "font_px", "font_weight", "font_style" } },
  "baked": { "places": [...], "paths": [...], "notes": [...] },   // the custom.json items drawn into THIS image
  "fonts": { "display": "Noto Serif Georgian", "text": "…" },     // font family actually used for each theme role
  "page_mm": [300, 400],                                          // the poster's own size
  // only landmarks inside the frame; "num" = number on its pin when there was no room for the icon
  "landmarks": [ { "id": "cathedral", "name": "…", "name_local": "…", "blurb": "…", "blurb_local": "…", "rank": 1, "num": null, "lon", "lat",
                   "icon": "cathedral.svg", "x": 1510.2, "y": 2301.7, "r": 60 } ]  // image px; r = hit radius
}
```

### Coordinates
North is up, no rotation. For lon/lat ⇄ image pixel:
```
cx = frame_px.x + frame_px.w/2 ;  cy = frame_px.y + frame_px.h/2
x = cx + (lon - center.lon) * m_per_deg[0] / m_per_px
y = cy - (lat - center.lat) * m_per_deg[1] / m_per_px
```
(accurate to well under a metre for frames up to ~20 km).
