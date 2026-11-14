# Writing a theme

A theme is one JSON file, `styles/<id>.json`. The engine (`atlas/`) never changes for a new look — the theme
decides paper, palette, type, how every layer is drawn, what gets scattered over the land, and the page furniture.
Start by copying the closest existing theme (`styles/storybook.json` = illustrated, `styles/hiking.json` = practical),
then change it until nothing of the original look remains.

```
uv run poster.py <slug> --style <id> --lang <en|ka> --png-width 2400     # ≈ 10 s; writes out/<slug>/<id>.<lang>.{svg,png,jpg,json}
```
Look at the JPG after every change (whole poster, then crops at full size: `magick in.png -crop 1200x1000+X+Y +repage out.png`).

Colours: `#rgb`, `#rrggbb` or `rgba(r,g,b,a)` (translucent washes that darken where they overlap).
Units are **millimetres on the page** everywhere (sizes, widths, spacing, dashes). At the default scale 1 mm ≈ 15 m.
All text on a map is in ONE language (`--lang`); never hard-code words — see *Text*.

## Top level
| key | meaning |
|---|---|
| `name`, `description`, `name_local`, `description_local` | shown in the studio's theme picker (English / local language) |
| `seed` | integer; changes every random placement (trees, textures) |
| `palette` | `{ "ink": "#3a2917", … }` — then write `"$ink"` anywhere a colour goes. Keep ALL colours here. |
| `fonts` | font roles, per language — see *Text* |
| `page` | size, frame and paper |
| `order` | drawing order of the map content (bottom → top) |
| `relief`, `layers`, `scatter`, `bridges`, `grid`, `symbols` | the map itself |
| `landmarks`, `custom` | bespoke landmark icons, and the user's own additions from the studio |
| `labels` | place names, river names, small labels |
| `decorations`, `panels` | frame, title, compass, scale bar, legend, landmark index, loose text |
| `filters` | named SVG filters (slow — see *Performance*) |
| `wobble_freq` | waviness of hand-drawn lines (default 0.75; lower = longer, lazier waves) |
| `extends` | id of another theme to inherit from (deep-merged) |

## page
```json
"page": { "width": 300, "height": 400, "margin": 13,
          "frame": ["m + 2", "m + 2", "W - 2*m - 4", "306"],      // x, y, w, h of the map window
          "bg": "$paper", "map_bg": "$paper_light",
          "texture": { "tint": "#5e3f1c", "blend": "multiply", "grain": 0.05, "mottle": 0.11, "fibers": 0.05,
                       "stains": 3, "vignette": 0.34, "edge_wear": 0.3, "opacity": 1 },   // over the whole page
          "map_texture": { … } }                                                          // over the map only
```
Positions may be numbers or expressions over: `W H m` (page width, height, margin), `fx fy fw fh` (frame), `fr fb`
(frame right / bottom), `cx` (page centre x), `mx my` (frame centre). The frame should stay within ~1.15 : 1 either
way (the data is fetched for a square around the place). The page itself may be portrait or landscape (e.g. map left, notes right).
Texture `px_per_mm` (default 4) sets the texture's resolution.
Texture amounts are 0–1 strengths. Omitted keys are NOT zero (defaults: grain 0.05, mottle 0.07, fibers 0.03, vignette 0.18) —
set what you do not want to 0. Dark papers: `"blend": "screen"` + a light tint adds pale grain (it can only lighten); to darken a
dark map toward its edges use `multiply` with a near-black tint. `map_texture` lies over the labels too — keep its vignette gentle.

## order
Tokens: `landcover hillshade contours hachures water waterways ground tracks paths roads bridges buildings trees grid peaks`.
`ground` and `trees` are just two buckets: each runs the scatter entries with that `layer`, wherever you put the token — so forest
trees can go in `ground` to sit under roads, and `hillshade` can come after it to shade the tree-tops. Leave a token out to skip it
(no `bridges` token or no `bridges` key = no bridges; on dark maps they tend to read as stray marks).

## relief (all optional)
```json
"hillshade": { "shadow": "#5a3c1c", "shadow_opacity": 0.3, "light": "#fff8e0", "light_opacity": 0.25, "exaggeration": 1.5,
               "azimuth": 315, "altitude": 45, "gamma": 1, "blend": "multiply" },   // blend: any CSS mix-blend-mode; none = plain overlay.
                                                                                 // dark maps: "overlay" makes lit slopes glow
"contours":  { "color": "$c", "width": 0.09, "index_width": 0.24, "every": 10, "index_every": 50, "opacity": 0.85, "wobble": 0, "dash",   // every == index_every → one line class
               "labels": { "font": "@text", "size": 1.6, "halo": "$map" } },
"hachures":  { "spacing": 1.25, "min_slope": 0.2, "max_slope": 0.8, "length": [0.6, 1.7], "width": [0.09, 0.26],
               "color": "$ink_soft", "opacity": 0.8, "light": 315,
               "avoid": ["water", "buildings", "roads", "<landcover kind>"] },                    // engraved slope strokes
"peaks":     { "count": 5, "min_distance": 30, "glyph": "mountain", "size": [6, 9], "style": { glyph style },
               "label": { fontspec } }      // without "glyph": a dot ("dot": {size,color}) or "symbol": { symbol rule } + spot height
                                            // "min_height": 0.3 = only in the upper 70 % of the relief; "margin": mm from the frame
```

## layers — how each OSM layer is drawn
`layers.<layer>.<kind>` is a *rule*; `"*"` matches every other kind. Kinds:
`landcover`: wood scrub heath grassland grass meadow farmland orchard vineyard residential cemetery religious bare_rock scree (drawn in the order you list them) ·
`water`: sea, `*` (lakes, ponds) · `waterways`: river stream canal drain · `roads`: major minor · `tracks`: `*` · `paths`: `*` · `buildings`: `*`

Rule keys (areas): `fill`, `fill_opacity`, `stroke`, `width`, `dash`, `opacity`, `wobble` (hand-drawn edge, 0.1–0.6),
`shadow` `{dx,dy,color,opacity}`, `edge` `{stroke,width,opacity,dash,wobble}` (a second outline),
`hatch` `{angle:"auto"|deg, across, gap, gap_jitter, angle_jitter, color, width, opacity, wobble, dash, inset, min_area}`
(parallel strokes — furrows, vineyard rows, engraving tints), `pool` `{color,width,opacity,fx}` (watercolour pigment
gathering at the edge), `fx` (a filter name), `hide`.
Water also takes `shorelines` `{count, gap, color, width, opacity, wobble}` (rings inside the shore).
Rule keys (lines): `stroke`, `width`, `dash`, `linecap`, `opacity`, `wobble`, `casing` `{color,width,opacity}`,
`inner` `{stroke,width,dash,opacity}` (centre line: river flow, road stripe), `sketch` (n extra loose pen passes), `fx`.
Dotted line = `"dash": "0.05 0.85"` (round caps).
Buildings: either footprints (`fill`, `stroke`, `shadow`, `roofs`: list of colours picked at random per house) or little
drawn houses: `{ "glyph": "house", "size": [1.9, 2.5], "min_gap": 1.5, "roofs": ["$r1", "$r2"], "walls": ["$lit", "$dark"], "style": { "ink", "fill", "sw" } }`
(`roofs` / `walls` are picked at random per house — e.g. some windows lit, some dark, at night).

## scatter — the illustrated details
A list; each entry sprinkles glyphs over a region. This is where a map gets its character.
```json
{ "layer": "trees",                  // "ground" (under roads), "trees" (over buildings), "sky" (over labels)
  "on": "wood",                      // a landcover kind, a list of kinds, "water" / "lake" / "sea", "frame", or
                                     // "open" = everything except wood, scrub, residential, cemetery and water (fields and meadows ARE in it)
  "glyph": ["round", "conifer"], "weights": [5, 2],
  "spacing": 2.5, "jitter": 0.42,    // grid spacing … OR "count": 14 (exact number) / "count": 0.002 (per mm²)
  "size": [2.5, 3.5],                // glyph height range
  "style": { "ink": "$ink", "fill": "$forest", "shade": "$forest_dark", "sw": 0.055, "trunk": "$ink", "accent": "$red", "roof": "$r1" },
  "elev": [0, 1380], "slope": [0.62, 9],     // only where elevation (m) / slope (rise/run) is in range
  "inset": 0.5,                      // stay this far inside the region edge (negative = spill outside)
  "band": 0.9,                       // ONLY a strip this wide along the region's edge — reeds on a shore: "inset": -0.6, "band": 0.9
  "avoid": ["roads", "paths", "buildings", "water", "landmarks", "decor", "<landcover kind>"], "avoid_dist": 0.5,
  "clump": 0.45,                     // 0–1: thin out into natural-looking clumps
  "flock": { "n": [3, 6], "spread": 4 },     // each point becomes a small group (birds)
  "min_area": 40, "max": 6000, "flip": true,
  "rot": 0,                          // random ± degrees per glyph ("rot": 180 turns `bush` into varied brush dabs)
  "opacity": 1, "legend": "wood" }   // opacity is for the whole group: overlaps do not darken. For glazes use rgba() colours.
```
`style.sw` is the outline weight as a fraction of the glyph's height (0.05–0.1), not millimetres.
Glyphs: `conifer round poplar ink_tree bush grass reed vine rock haystack cow sheep bird grave wave rowboat sailboat mountain hill house`
`moon star sun cloud` (see `atlas/glyphs.py`; each has 3 variants). Style: leave out `ink` for flat, outline-free glyphs; leave out
`shade` for no shading. Roles used — trees/bush/rock/haystack/mountain/hill: `fill`, `shade`, `ink` (+ `trunk`, `shade_opacity`);
grass/reed/bird/wave/grave: `ink` only; cow/sheep: `fill`, `shade`, `ink`; boats: `fill`, `shade`, `ink`, `accent` (pennant);
house: `fill` (wall), `roof`, `ink`; moon: `fill`, `shade`; star/sun/cloud: `fill`, `ink`.
On dark paper a pale rim makes `round` trees look like nuts — use `ink_tree`, `conifer`, `poplar`.
Always add `"landmarks"` and `"decor"` to `avoid` for anything big enough to collide with icons or the title.

## bridges, grid, symbols
`"bridges": { "size": 2, "gap": 0.95, "stroke": "$ink", "width": 0.28, "deck": "$road" }` — drawn wherever a road crosses water.
`"grid": { "step": 1000, "color", "width", "opacity", "edge_labels": { fontspec } }` — real UTM grid (practical maps).
`"symbols"`: small generic marks for repeated things: `{ "spring": { "shape": "drop|circle|dot|cross|triangle|square", "size", "color", "fill", "width", "legend": "spring", "priority", "label": true } , "drinking_water": {…} }`.

## landmarks — the bespoke icons
Icons are drawn per place (see CONTRACT.md); the theme only recolours and sizes them.
```json
"landmarks": { "sizes": [17, 12.5, 8.5],            // mm for rank 1, 2, 3
  "ink", "paper", "tone", "shade", "accent",        // the five colour roles of every icon
  "stroke": 2.0,                                    // outline weight (icon units; 1.6 light … 2.6 heavy)
  "halo": "$paper_light", "halo_width": 6,          // a paper-coloured rim that lifts icons off the map
  "shadow": { "color", "opacity" },                 // ground shadow
  "leader": { "stroke", "width", "dash", "dot" },   // line to the true spot when an icon had to move aside
  "pin": { "r", "fill", "stroke", "font" },         // numbered pin when there is no room at all
  "label": { fontspec }, "label_sizes": [3.5, 2.8, 2.2], "label_width": 30, "label_hero": { "color": "$accent" },
  "max_rank": 3, "label_max_rank": 3 }
```
Check the icons on YOUR paper: `ink` must contrast with `paper`, and `halo` should equal the map background.
What the roles paint: `paper` = walls and bodies, `tone` = roofs, rock, secondary masses, `shade` = doors, windows, dark interiors,
`accent` = the one small highlight (a cross, a flag, a fruit). So on a night map `shade` becomes the lit window.
A rank-1 label is always placed, even if nothing fits — check that it did not land on a neighbouring icon.

## custom — what the user adds in the studio
`"custom": { "path": { line rule }, "path_label": { fontspec }, "place_size": 9, "label": { fontspec }, "note": { fontspec } }`
The path must be unmistakably different from every road/trail in the theme.

## Text
```json
"fonts": { "display": { "en": "Uncial Antiqua", "ka": { "font": "Noto Serif Georgian", "weight": "bold", "scale": 0.92 } },
           "text":    { "en": "IM FELL English", "ka": "Noto Serif Georgian" },
           "italic":  { "en": { "font": "IM FELL English", "style": "italic" }, "ka": { "font": "Noto Serif Georgian", "style": "italic" } } }
```
A *fontspec* is `{ "font": "@role", "size", "color", "weight", "style", "ls" (letter spacing), "upper", "halo", "halo_width", "opacity" }`.
Roles are yours to name. Give every role an `en` font and one for the local language (`ka`; or `local` as a catch-all);
a per-language object may override `weight/style/ls` and `scale` the size. Installed families (project `fonts/` + system):
Latin display/text — Uncial Antiqua, Almendra, Cinzel, Cinzel Decorative, IM FELL English (+ SC), Cormorant Garamond,
EB Garamond, Playfair Display, Caveat, Kalam, Patrick Hand, Amatic SC, Space Grotesk, FiraGO.
Georgian — Noto Serif Georgian, Noto Sans Georgian (both have capitals: `"upper": true` gives Mtavruli; lighter/heavier cuts exist as
families "Noto Serif Georgian Lt/Md", "Noto Sans Georgian Light/Medium"), FiraGO (no capitals). No handwriting face has Georgian, and
Georgian italic is always a synthetic slant. Titles and sub-lines are never wrapped or shrunk: test the longest (Georgian region) line.
Check with `FONTCONFIG_FILE=$PWD/fonts.conf fc-list : family` (the path must be absolute, or you only see system fonts).
A missing family silently falls back to a default sans — look for it. A fontspec `font` may also be a literal family name.
Noto Serif Georgian has no true italic (it stays upright). Faces differ in apparent size: EB Garamond / Cormorant look ~12 % smaller
than Noto Serif Georgian at the same size — even it out with the per-language `scale`. Only `"bold"`/600+ is measured as bold.

The user can replace the font of any role without touching the theme (studio → Fonts, `fonts.py set`, or
`poster.py --font role="Family"`), so name roles by what they are for — `display`, `text`, `italic`, `caps`, `hand` are
the names the studio knows how to describe — and make sure a theme still works when a role's font changes width.

Words come from the engine, already translated: in `texts[].lines` and `title.sub[].text` use the keys
`elevation`, `scale`, `grid_note`, `hiking_map`, `attribution`, or templates `{name} {region} {country} {ratio} {elev_min} {elev_max} {lat} {lon}`,
or `{ "en": "…", "ka": "…" }` for your own wording. The legend and the landmark index write themselves.

`labels`: `place` (the place itself), `place_minor` (neighbours), `poi`, `water` (river names, letter by letter along
the stream: add `"spread"` = distance between letters).

## decorations
```json
"frame":   { "style": "line|double|triple", "color", "width", "gap", "outer_width", "wobble",   // paper-coloured, 2–3 mm wide, wobbly = a painted, frameless edge
             "corners": { "size": 9, "inset": 2, "width": 0.35 },
             "checker": { "band": 1.6, "metres": 250, "fill", "alt" } },      // antique chequered scale border
             // with a checker the 2nd line sits at band + gap outside the frame, the 3rd ("triple") at 1.8 × that
"title":   { "style": "plain|ribbon|plaque", "x", "y", "anchor", "font": { fontspec }, "text": "{name}", "clear": 3,
             "ribbon": { "ink", "fill", "shade", "sw" }, "plaque": { "fill", "ink", "width", "pad" },
             "sub": [ { "text": "{region}", …fontspec } ], "rule": { "color", "width", "gap", "length" } },
"compass": { "x", "y", "size", "style": "arrow|rose8|rose16", "ink", "fill", "accent", "font": { fontspec } },
"scalebar":{ "x", "y", "anchor": "start|middle|end", "style": "bar|line", "segments": 4, "h": 1.2, "width", "color", "alt",
             "fraction": 0.22, "metres": 500, "font": { fontspec } },
"legend":  { "x", "y", "columns": 2, "col_width": 45, "gap": 5.1, "swatch": 8, "font", "title_font", "title": true,
             "skip": ["scrub", "contour", "road_minor", "drinking_water"] },   // landcover kinds or engine keys
"index":   { "x", "y", "columns": 3, "col_width": 57, "row": 9.2, "icon": 8, "font", "title_font", "max": 15 },   // landmark list with icons
"texts":   [ { "x", "y", "anchor", "lines": ["elevation"], "gap", …fontspec } ],
"attribution": { "x", "y", "anchor", …fontspec }                              // REQUIRED: OpenStreetMap credit must stay legible
```
Any of title / compass / scalebar / legend / index may sit on the map: add `"on_map": true` (icons, labels, trees and
houses then keep clear; `"clear": mm` widens that margin — make it at least the backdrop/plaque pad) and optionally `"backdrop": { "fill", "opacity", "pad", "radius", "stroke", "width" }`.
`panels`: plain rectangles drawn first, under the map window and all furniture: `[{ "x", "y", "width", "height", "fill", "opacity", "rx", …any SVG rect attribute }]`.
`ornaments`: single glyphs anywhere on the page (a moon and stars in a night header, a sun, clouds):
`[{ "glyph": "moon", "x": "m + 14", "y": 30, "size": 16, "style": { "fill": "$moon", "shade": "$sky" }, "opacity": 1 }]` (y = the glyph's foot).
Legend and index grow with the place (8–16 legend rows, 5–20 landmarks; the index lists only landmarks inside the frame):
leave room, and check nothing runs off the page. A legend swatch shows the rule's `fill` (+ `fill_opacity`), its `hatch`, its edge,
and the first two glyphs of a spacing-based scatter entry on that kind — a kind with none of those gets an empty outline box.
Templates also include `{interval}` (contour interval), `{zone}` (UTM zone), `{m}` / `{km}` (unit words).

## Performance
A render should take ~10 s. Two things make it crawl:
* `fx` filters — each use is rasterised separately: a blur costs ~1 s per use, a `rough` displacement 4–6 s per use (fewer octaves
  barely help), and `fx` on a scatter entry always rasterises the whole page. `pool` is free. Use `wobble` for hand-drawn edges;
  keep `fx` for a handful of things (e.g. a soft blur on water or on painted tree dabs). Define in `"filters": { "soft": { "type": "blur", "std": 0.4 }, "rough": { "freq": 0.4, "scale": 0.5, "octaves": 2, "blur": 0 } }`.
* `opacity` on a scatter entry with thousands of glyphs is fine (one group), but do not exceed ~9 000 glyphs in total.
A font role's per-language `weight` / `style` / `ls` override the fontspec that uses it — make a second role for a second weight.

## What makes a theme good (learned the hard way)
* Decide the medium first — ink on parchment, watercolour in a sketchbook, engraved atlas plate, screen-print, night — and make
  every choice obey it: a watercolour has no hard black casings; an engraving has no flat colour fills.
* The land must not be empty. Forest = drawn trees; slopes = hachures or shading; fields = furrows; meadows = tufts; water = shore
  rings, reeds, a boat. Then a few surprises (cows, haystacks, birds).
* One accent colour, used sparingly, and it should *mean* something (the hero landmark, trails and north — or, at night, lit windows).
* Type carries half the mood. Pick a display face with character for the title and place names, a quiet text face for the rest,
  italics for water. Test in Georgian AND English: lengths and letter shapes differ a lot.
* Landmark icons are the heroes: nothing may be louder than them; give them a halo equal to the paper.
* Check at 100 %: label collisions, text touching the frame, legend swatches that show nothing, unreadable light-on-light text.
