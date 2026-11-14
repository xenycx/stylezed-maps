"""Text, label placement, generic symbols, bespoke landmark icons and the user's own additions."""
import json, math, re
from xml.sax.saxutils import escape

from shapely.geometry import LineString

from .core import ROOT, mtavruli_families, text_width
from .layers import attrs, lines

_STRIP = re.compile(r"<\?xml.*?\?>|<!--.*?-->|<style.*?</style>|<title.*?</title>|<desc.*?</desc>|</?svg[^>]*>", re.S)
GEORGIAN = re.compile(r"[Ⴀ-ჿᲐ-Ჿ]")



def place_scale(p):
    """A user place's own size: "size" in custom.json, 0.5–2.5 times the style's place size (default 1)."""
    v = p.get("size", 1)
    return min(2.5, max(0.5, float(v))) if isinstance(v, (int, float)) and not isinstance(v, bool) else 1.0

class Annot:
    # ------------------------------------------------------------ fonts & text
    def font(self, f):
        if f.get("_r"):
            return f
        f = dict(f)
        fam = f.get("font", "@text")
        if fam.startswith("@"):
            name = fam[1:]
            role = self.st.get("fonts", {}).get(name, {})
            v = role.get(self.lang) or (role.get("local") if self.lang != "en" else None) or role.get("en", "Noto Sans")
            if isinstance(v, dict):
                f["size"] = f.get("size", 3) * v.get("scale", 1)
                f.update({k: x for k, x in v.items() if k not in ("font", "scale")})
                fam = v["font"]
            else:
                fam = v
            fam = self.font_over.get(name, fam)      # the user's own choice for this role (fonts.json / --font)
            self.fonts_used[name] = fam
        f["family"], f["_r"] = fam, True
        return f

    def case(self, s, f):
        if not f.get("upper"):
            return s
        if GEORGIAN.search(s) and f["family"] not in mtavruli_families():
            return s  # this font has no Georgian capitals (Mtavruli)
        return s.upper()

    def measure(self, s, f):
        f = self.font(f)
        return text_width(self.case(s, f), f["family"], f["size"], f.get("weight", "normal"), f.get("style", "normal"), f.get("ls", 0))

    def text(self, x, y, s, f, anchor="middle", rotate=None, baseline="central"):
        f = self.font(f)
        a = {"x": f"{x:.2f}", "y": f"{y:.2f}", "font_family": f["family"], "font_size": f"{f['size']:.2f}", "fill": f.get("color", "#000"),
             "text_anchor": anchor, "font_weight": f.get("weight"), "font_style": f.get("style"), "letter_spacing": f.get("ls"),
             "dominant_baseline": baseline, "opacity": f.get("opacity"),
             "transform": f"rotate({rotate:.1f} {x:.2f} {y:.2f})" if rotate else None}
        if f.get("halo"):
            a.update(paint_order="stroke", stroke=f["halo"], stroke_width=f.get("halo_width", f["size"] * .28), stroke_linejoin="round")
        self.out.append(f"<text {attrs(a)}>{escape(self.case(s, f))}</text>")

    def box(self, x, y, s, f, anchor="middle"):
        f = self.font(f)
        w, h = self.measure(s, f), f["size"] * 1.15
        x0 = x - w / 2 if anchor == "middle" else (x - w if anchor == "end" else x)
        return (x0, y - h / 2, x0 + w, y + h / 2)

    def fits(self, b, pad=.35, edge=1.0):
        m = self.map
        if b[0] < m.fx + edge or b[2] > m.fx + m.fw - edge or b[1] < m.fy + edge or b[3] > m.fy + m.fh - edge:
            return False
        return not any(b[0] - pad < o[2] and b[2] + pad > o[0] and b[1] - pad < o[3] and b[3] + pad > o[1] for o in self.occupied)

    def place_label(self, x, y, lines_, offsets, force=False):
        """lines_: [(text, fontspec)] stacked; offsets: [(dx, dy, anchor)] tried in order."""
        lines_ = [(t, self.font(f)) for t, f in lines_ if t]
        if not lines_:
            return False
        total = sum(f["size"] * 1.1 for _, f in lines_)
        for n, (dx, dy, anchor) in enumerate(list(offsets) + ([offsets[0]] if force else [])):
            yy = y + dy - total / 2 + lines_[0][1]["size"] * .55
            pos, boxes = [], []
            for t, f in lines_:
                boxes.append(self.box(x + dx, yy, t, f, anchor))
                pos.append((x + dx, yy, t, f))
                yy += f["size"] * 1.1
            if all(self.fits(b) for b in boxes) or (force and n == len(offsets)):
                self.occupied.extend(boxes)
                for px, py, t, f in pos:
                    self.text(px, py, t, f, anchor)
                return True
        return False

    def wrap(self, s, f, max_w):
        if self.measure(s, f) <= max_w or " " not in s:
            return [s]
        words = s.split(" ")
        best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
        return [" ".join(words[:best]), " ".join(words[best:])]

    def name_of(self, p):
        loc = p.get("name_local") or p.get("name_ka")
        return (p.get("name") or loc) if self.lang == "en" else (loc or p.get("name"))

    # ------------------------------------------------------------ generic symbols (springs, taps, …)
    def symbol(self, x, y, r):
        s, col, fill, w = r.get("size", 2), r.get("color", "#000"), r.get("fill", "#fff"), r.get("width", .3)
        shp = r.get("shape", "circle")
        if shp == "circle":
            m = f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{s / 2}" fill="{fill}" stroke="{col}" stroke-width="{w}"/>'
        elif shp == "dot":
            m = f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{s / 2}" fill="{col}"/>'
        elif shp == "cross":
            m = f'<path d="M{x:.2f},{y - s:.2f} V{y + s:.2f} M{x - s * .6:.2f},{y - s * .35:.2f} H{x + s * .6:.2f}" stroke="{col}" stroke-width="{w * 1.6}" fill="none"/>'
        elif shp == "triangle":
            m = f'<path d="M{x:.2f},{y - s * .7:.2f} L{x + s * .65:.2f},{y + s * .5:.2f} L{x - s * .65:.2f},{y + s * .5:.2f} Z" fill="{fill}" stroke="{col}" stroke-width="{w}" stroke-linejoin="round"/>'
        elif shp == "drop":
            m = (f'<path d="M{x:.2f},{y - s * .7:.2f} C{x + s * .6:.2f},{y:.2f} {x + s * .5:.2f},{y + s * .6:.2f} {x:.2f},{y + s * .6:.2f} '
                 f'C{x - s * .5:.2f},{y + s * .6:.2f} {x - s * .6:.2f},{y:.2f} {x:.2f},{y - s * .7:.2f} Z" fill="{fill}" stroke="{col}" stroke-width="{w}"/>')
        else:  # square
            m = f'<rect x="{x - s / 2:.2f}" y="{y - s / 2:.2f}" width="{s}" height="{s}" fill="{fill}" stroke="{col}" stroke-width="{w}"/>'
        self.out.append(m)

    def symbols(self):
        cfg = self.st.get("symbols", {})
        self.symbol_labels = []
        if not cfg:
            return
        taken = {lm["lm"].get("osm") for lm in self.lm_plan}
        spots = [(lm["x"], lm["y"]) for lm in self.lm_plan]
        seen = set()
        items = []
        for g, p in self.geo.get("pois", []):
            if g.geom_type != "Point" or p.get("id") in taken:
                continue
            rule = cfg.get(p.get("natural")) or cfg.get(p.get("kind")) or (cfg.get("*named") if p.get("name") else None)
            if not rule or rule.get("hide") or not self.map.inside(g.x, g.y, 2):
                continue
            if any(math.hypot(g.x - a, g.y - b) < 1.5 for a, b in spots) or (round(g.x), round(g.y)) in seen:
                continue
            seen.add((round(g.x), round(g.y)))
            items.append((rule.get("priority", 5), g.x, g.y, rule, p))
        for _, x, y, rule, p in sorted(items, key=lambda i: i[0]):
            self.symbol(x, y, rule)
            s = rule.get("size", 2)
            self.occupied.append((x - s / 2, y - s / 2, x + s / 2, y + s / 2))
            if rule.get("legend"):
                self.present.add(rule["legend"])
            if rule.get("label") and self.name_of(p):
                self.symbol_labels.append((x, y, self.name_of(p), dict(self.st["labels"]["poi"], **rule.get("font", {})), s / 2 + .7))

    def symbol_text(self):
        for x, y, name, f, g in self.symbol_labels:
            sz = f["size"]
            self.place_label(x, y, [(name, f)], [(g, 0, "start"), (-g, 0, "end"), (0, -g - sz * .5, "middle"), (0, g + sz * .5, "middle"),
                                                 (g, -sz * .8, "start"), (g, sz * .8, "start")])

    # ------------------------------------------------------------ bespoke landmark icons
    def icon_inner(self, path):
        if path not in self._icons:
            self._icons[path] = _STRIP.sub("", path.read_text()).strip() if path.exists() else None
        return self._icons[path]

    def icon_css(self, c):
        ink, sw = c.get("ink", "#222"), c.get("stroke", 2.2)
        halo = c.get("halo")
        css = (f".lm .ink{{fill:none;stroke:{ink};stroke-width:{sw};stroke-linecap:round;stroke-linejoin:round}}"
               f".lm .thin{{stroke-width:{sw * .55:.2f}}}"
               f".lm .paper{{fill:{c.get('paper', '#fff')}}}.lm .tone{{fill:{c.get('tone', '#ccc')}}}.lm .shade{{fill:{c.get('shade', '#666')}}}"
               f".lm .accent{{fill:{c.get('accent', '#c33')}}}.lm .solid{{fill:{ink};stroke:none}}")
        if halo:
            css += f".lmh *{{fill:{halo};stroke:{halo};stroke-width:{c.get('halo_width', 7)};stroke-linejoin:round;stroke-linecap:round}}"
        return css

    def draw_icon(self, path, x, y, s, halo=True):
        """Icon's ground point (32,60) lands on (x,y); s = icon box size in mm."""
        inner = self.icon_inner(path)
        if inner is None:
            self.out.append(f'<circle cx="{x:.2f}" cy="{y - s * .3:.2f}" r="{s * .3:.2f}" fill="{self.st.get("landmarks", {}).get("paper", "#fff")}" '
                            f'stroke="{self.st.get("landmarks", {}).get("ink", "#222")}" stroke-width=".4"/>')
            return
        t = f'transform="translate({x - s / 2:.2f},{y - s * 60 / 64:.2f}) scale({s / 64:.4f})"'
        if halo and self.st.get("landmarks", {}).get("halo"):
            self.out.append(f'<g class="lmh" {t}>{inner}</g>')
        self.out.append(f'<g class="lm" {t}>{inner}</g>')

    def plan_landmarks(self):
        """Decide where every landmark icon goes before anything is drawn, so trees and labels can make room."""
        cfg = self.st.get("landmarks")
        f = self.d_ / "landmarks.json"
        self.lm_plan, self.landmark_spots = [], []
        if not cfg or cfg.get("hide") or not f.exists():
            return
        m = self.map
        cand = []
        for lm in json.loads(f.read_text()).get("landmarks", []):
            x, y = m.xy(lm["lon"], lm["lat"])
            if m.inside(x, y, 2) and lm.get("rank", 3) <= cfg.get("max_rank", 3):
                cand.append((lm.get("rank", 3), math.hypot(x - m.fx - m.fw / 2, y - m.fy - m.fh / 2), x, y, lm))
        sizes = cfg.get("sizes", [13, 10, 7])
        boxes, n_pin = [], 0
        dirs = [(-.7, -.7), (.7, -.7), (-1, 0), (1, 0), (0, -1), (-.7, .7), (.7, .7), (0, 1)]
        for rank, _, x, y, lm in sorted(cand, key=lambda c: c[:2]):
            s = sizes[min(rank, len(sizes)) - 1]
            spot = None
            for dx, dy in [(0, 0)] + [(a * r * s, b * r * s) for r in (.8, 1.2, 1.7, 2.3) for a, b in dirs]:
                gx, gy = x + dx, y + dy + (s * .3 if (dx, dy) != (0, 0) else 0)
                b = (gx - s * .42, gy - s * .9, gx + s * .42, gy + s * .02)
                if b[0] < m.fx + 1 or b[2] > m.fx + m.fw - 1 or b[1] < m.fy + 1 or b[3] > m.fy + m.fh - 1:
                    continue
                if any(b[0] < o[2] and b[2] > o[0] and b[1] < o[3] and b[3] > o[1] for o in boxes):
                    continue
                spot = (gx, gy, b, (dx, dy) != (0, 0))
                break
            item = {"lm": lm, "x": x, "y": y, "s": s, "rank": rank, "num": None}
            if spot:
                item.update(gx=spot[0], gy=spot[1], moved=spot[3])
                boxes.append(spot[2])
                self.occupied.append(spot[2])
                self.landmark_spots.append((spot[0], spot[1] - s * .45, s))
            else:
                n_pin += 1
                item.update(num=n_pin, gx=None)
                self.occupied.append((x - 1.6, y - 1.6, x + 1.6, y + 1.6))
            self.lm_plan.append(item)

    def draw_landmarks(self):
        cfg = self.st.get("landmarks")
        if not self.lm_plan:
            return
        self.css.append(self.icon_css(cfg))
        ld = cfg.get("leader", {})
        for it in self.lm_plan:
            if it["gx"] is not None and it["moved"]:
                self.out.append(f'<path d="M{it["x"]:.2f},{it["y"]:.2f} L{it["gx"]:.2f},{it["gy"] - it["s"] * .12:.2f}" fill="none" stroke="{ld.get("stroke", cfg.get("ink", "#222"))}" '
                                f'stroke-width="{ld.get("width", .25)}" {attrs({"stroke_dasharray": ld.get("dash"), "opacity": ld.get("opacity")})} stroke-linecap="round"/>'
                                f'<circle cx="{it["x"]:.2f}" cy="{it["y"]:.2f}" r="{ld.get("dot", .55)}" fill="{ld.get("stroke", cfg.get("ink", "#222"))}"/>')
        sh = cfg.get("shadow")
        for it in sorted([i for i in self.lm_plan if i["gx"] is not None], key=lambda i: i["gy"]):
            if sh:
                self.out.append(f'<ellipse cx="{it["gx"]:.2f}" cy="{it["gy"] - it["s"] * .03:.2f}" rx="{it["s"] * .4:.2f}" ry="{it["s"] * .09:.2f}" '
                                f'fill="{sh.get("color", "#000")}" opacity="{sh.get("opacity", .25)}"/>')
            self.draw_icon(self.d_ / "icons" / it["lm"]["icon"], it["gx"], it["gy"], it["s"])
        pin = cfg.get("pin", {})
        for it in self.lm_plan:
            if it["num"] is not None:
                r = pin.get("r", 1.5)
                self.out.append(f'<circle cx="{it["x"]:.2f}" cy="{it["y"]:.2f}" r="{r}" fill="{pin.get("fill", cfg.get("accent", "#c33"))}" '
                                f'stroke="{pin.get("stroke", cfg.get("paper", "#fff"))}" stroke-width=".3"/>')
                self.text(it["x"], it["y"], str(it["num"]), pin.get("font", {"font": "@text", "size": 2, "color": "#fff", "weight": "bold"}))
        k = self.k
        for it in self.lm_plan:
            lm = it["lm"]
            cx, cy = (it["gx"], it["gy"] - it["s"] * .45) if it["gx"] is not None else (it["x"], it["y"])
            self.landmark_hits.append({"id": lm["id"], "name": lm.get("name"), "name_local": lm.get("name_local"), "blurb": lm.get("blurb"),
                                       "blurb_local": lm.get("blurb_local"), "icon": lm.get("icon"), "rank": it["rank"], "num": it["num"],
                                       "lon": lm["lon"], "lat": lm["lat"], "x": round(cx * k, 1), "y": round(cy * k, 1),
                                       "r": round(max(it["s"] * .5, 3) * k, 1)})

    def lm_name(self, lm):
        return (lm.get("name") or lm.get("name_local")) if self.lang == "en" else (lm.get("name_local") or lm.get("name"))

    def lm_label(self, lm):
        """Text next to the icon on the map: "label" / "label_local" when given ("" = icon only), else the name."""
        key = "label" if self.lang == "en" else "label_local"
        return lm[key] if isinstance(lm.get(key), str) else self.lm_name(lm)

    def landmark_labels(self):
        cfg = self.st.get("landmarks") or {}
        base = cfg.get("label")
        if not base:
            return
        sizes = cfg.get("label_sizes", [base.get("size", 3)] * 3)
        for it in self.lm_plan:
            if it["gx"] is None or it["rank"] > cfg.get("label_max_rank", 3):
                continue
            f = dict(base, size=sizes[min(it["rank"], len(sizes)) - 1])
            if it["rank"] == 1 and cfg.get("label_hero"):
                f.update(cfg["label_hero"])
            text = self.lm_label(it["lm"])
            if not text:
                continue
            ls = [(t, f) for t in self.wrap(text, f, cfg.get("label_width", 26))]
            s, gx, gy = it["s"], it["gx"], it["gy"]
            h = self.font(f)["size"] * 1.1 * len(ls)
            mid = gy - s * .45
            offs = [(0, s * .08 + h / 2 + .4, "middle"), (s * .5, mid - gy, "start"), (-s * .5, mid - gy, "end"), (0, -s * .98 - h / 2, "middle"),
                    (s * .5, -s * .8, "start"), (-s * .5, -s * .8, "end"), (s * .45, s * .1 + h / 2, "start"), (-s * .45, s * .1 + h / 2, "end")]
            self.place_label(gx, gy, ls, offs, force=it["lm"].get("force_label", it["rank"] == 1))

    # ------------------------------------------------------------ the user's own additions (custom.json)
    def plan_custom(self):
        """Reserve room for the user's places before trees, houses and labels are laid out."""
        f = self.custom_path
        self.custom_doc = {"places": [], "paths": [], "notes": []}
        if not f.exists():
            return
        try:
            cu = json.loads(f.read_text())
        except Exception:
            return
        self.custom_doc = {k: cu.get(k, []) for k in ("places", "paths", "notes")}
        base = self.st.get("custom", {}).get("place_size", 8)
        for p in cu.get("places", []):
            try:
                x, y = self.map.xy(p["lon"], p["lat"])
            except Exception:
                continue
            size = base * place_scale(p)
            if self.map.inside(x, y, 2):
                self.landmark_spots.append((x, y - size * .45, size))
                self.occupied.append((x - size * .4, y - size * .9, x + size * .4, y))

    def custom(self):
        f = self.custom_path
        cfg = self.st.get("custom", {})
        if not f.exists():
            return
        try:
            cu = json.loads(f.read_text())
        except Exception:
            return
        m = self.map
        lab = cfg.get("label", self.st["labels"]["poi"])
        pr = cfg.get("path", {"stroke": "#c0392b", "width": .7, "dash": "1.6 1"})
        for p in cu.get("paths", []):
            if len(p.get("coords", [])) < 2:
                continue
            g = m.page(LineString(p["coords"]))
            if g is None:
                continue
            rule = dict(pr, **pr.get("kinds", {}).get(p.get("kind", "trail"), {}))
            self.line_rule([g], rule, "cu" + p.get("id", ""))
            self.present.add("my_route")
            if p.get("name"):
                ln = max(lines(g), key=lambda l: l.length)
                a, b = ln.interpolate(.5, normalized=True), ln.interpolate(min(ln.length, ln.length / 2 + 1))
                ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
                ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
                fl = self.font(cfg.get("path_label", lab))
                off = fl["size"] * .9
                self.text(a.x + math.sin(math.radians(ang)) * off, a.y - math.cos(math.radians(ang)) * off, p["name"], fl, rotate=ang)
        base = cfg.get("place_size", 8)
        if cu.get("places") and not any(c.startswith(".lm .ink") for c in self.css):
            self.css.append(self.icon_css(self.st.get("landmarks", {})))
        for p in cu.get("places", []):
            x, y = m.xy(p["lon"], p["lat"])
            if not m.inside(x, y, 2):
                continue
            ref = p.get("icon") or "library/pin"
            kind, _, stem = ref.partition("/")
            path = (ROOT / "icons" / "library" / f"{stem}.svg") if kind == "library" else (self.d_ / "icons" / f"{stem}.svg")
            size = base * place_scale(p)
            self.draw_icon(path, x, y, size)
            if p.get("name"):
                h = self.font(lab)["size"]
                self.place_label(x, y, [(t, lab) for t in self.wrap(p["name"], lab, 26)],
                                 [(0, h * .7, "middle"), (size * .5, -size * .45, "start"), (-size * .5, -size * .45, "end"), (0, -size - h * .6, "middle")], force=True)
        nf = cfg.get("note", lab)
        for n in cu.get("notes", []):
            x, y = m.xy(n["lon"], n["lat"])
            if not m.inside(x, y, 2) or not n.get("text"):
                continue
            self.out.append(f'<path d="M{x - .7:.2f},{y:.2f}h1.4M{x:.2f},{y - .7:.2f}v1.4M{x - .5:.2f},{y - .5:.2f}l1,1M{x - .5:.2f},{y + .5:.2f}l1,-1" '
                            f'stroke="{self.font(nf).get("color", "#000")}" stroke-width=".22" stroke-linecap="round"/>')
            ls = [(t, nf) for t in self.wrap(n["text"], nf, 34)]
            self.place_label(x, y, ls, [(1.6, 0, "start"), (-1.6, 0, "end"), (0, 2.4, "middle"), (0, -2.4, "middle")], force=True)

    # ------------------------------------------------------------ place names, river names, spot heights
    def places(self):
        lab = self.st["labels"]
        m = self.map
        main = self.meta.get("name")
        feats = sorted(self.geo.get("places", []), key=lambda t: (t[1].get("name") != main, {"city": 0, "town": 1, "village": 2}.get(t[1].get("place"), 3)))
        for g, p in feats:
            if g.geom_type != "Point" or not m.inside(g.x, g.y):
                continue
            name = self.name_of(p)
            if not name:
                continue
            f = self.font(lab["place"] if p.get("name") == main else lab.get("place_minor", lab["place"]))
            sz = f["size"]
            offs = [(0, 0, "middle"), (0, -sz * 1.5, "middle"), (0, sz * 1.5, "middle"), (0, -sz * 3, "middle"), (0, sz * 3, "middle"),
                    (sz * 2, -sz * 2, "start"), (-sz * 2, -sz * 2, "end"), (sz * 2, sz * 2, "start"), (-sz * 2, sz * 2, "end"),
                    (0, -sz * 4.5, "middle"), (0, sz * 4.5, "middle"), (sz * 4, 0, "start"), (-sz * 4, 0, "end")]
            if not self.place_label(g.x, g.y, [(name, f)], offs):
                w = self.measure(name, f)
                nx = min(max(g.x, m.fx + 2 + w / 2), m.fx + m.fw - 2 - w / 2)
                ny = min(max(g.y, m.fy + 2 + sz), m.fy + m.fh - 2 - sz)
                self.place_label(nx, ny, [(name, f)], offs, force=p.get("name") == main)

    def water_labels(self):
        f = self.st["labels"].get("water")
        if not f:
            return
        f = self.font(f)
        best = {}
        for g, p in self.geo.get("waterways", []):
            name = self.name_of(p)
            if name:
                for ln in lines(g):
                    if ln.length > best.get(name, (0, None))[0]:
                        best[name] = (ln.length, ln)
        for name, (length, ln) in best.items():
            s = self.case(name, f)
            gap = f.get("spread", f["size"] * 1.5)
            need = gap * (len(s) - 1)
            if length < need * 1.15:
                continue
            ln = ln.simplify(.6)
            if ln.coords[0][0] > ln.coords[-1][0]:
                ln = LineString(list(ln.coords)[::-1])
            start = (ln.length - need) / 2
            off = f.get("offset", f["size"] * .75)
            for i, ch in enumerate(s):
                if ch == " ":
                    continue
                a, b = ln.interpolate(start + i * gap - .4), ln.interpolate(start + i * gap + .4)
                ang = math.atan2(b.y - a.y, b.x - a.x)
                px, py = (a.x + b.x) / 2 + math.sin(ang) * off, (a.y + b.y) / 2 - math.cos(ang) * off
                self.text(px, py, ch, dict(f, upper=False), rotate=math.degrees(ang))
                self.occupied.append((px - f["size"] * .5, py - f["size"] * .5, px + f["size"] * .5, py + f["size"] * .5))

    def spots(self):
        for x, y, txt, f, g in self.deferred_spots:
            f = self.font(f)
            self.place_label(x, y, [(txt, f)], [(g, -f["size"] * .4, "start"), (-g, -f["size"] * .4, "end"), (0, g + f["size"] * .6, "middle"),
                                                (0, -g - f["size"] * .6, "middle")])
