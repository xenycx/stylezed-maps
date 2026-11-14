"""Page furniture: textures, frame, title, compass, scale bar, automatic legend, landmark index, notes."""
import math

from shapely.geometry import box

from . import glyphs
from .core import seeded, tr
from .layers import attrs
from .textures import texture_uri

NICE = [50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000, 50000]


class Decor:
    # ------------------------------------------------------------ helpers
    def ev(self, v):
        if isinstance(v, (int, float)):
            return float(v)
        return float(eval(v, {"__builtins__": {}}, self.vars))

    def fmt(self, s):
        s = tr(s, self.lang)
        if "{" not in s:
            return s
        lo, hi = self.frame_elev
        dn = self.meta.get("display_name" if self.lang == "en" else "display_name_local") or self.meta.get("display_name", "")
        parts = [p.strip() for p in dn.split(",")]
        region = ", ".join([p for p in parts[1:-1] if not p.replace(" ", "").isdigit()][:2])
        return s.format(name=self.title_name, region=region, country=parts[-1] if parts else "",
                        ratio=f"{round(1000 / self.map.scale, -2):,.0f}".replace(",", " "), r=f"{round(1000 / self.map.scale, -2):,.0f}".replace(",", " "),
                        elev_min=round(lo), elev_max=round(hi), a=round(lo), b=round(hi),
                        interval=self.R.get("contours", {}).get("every", 10), n=self.R.get("contours", {}).get("every", 10),
                        m=tr("m", self.lang), km=tr("km", self.lang), lat=f'{self.meta["lat"]:.4f}', lon=f'{self.meta["lon"]:.4f}', z=getattr(self, "grid_zone", ""), zone=getattr(self, "grid_zone", ""))

    def texture(self, spec, x, y, w, h, key, clip=None):
        if not spec:
            return
        uri = texture_uri(w, h, spec, seed=seeded(self.seed, key).randrange(1 << 30))
        self.out.append(f'<image x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="none" href="{uri}" '
                        f'{attrs({"opacity": spec.get("opacity"), "clip_path": clip})} style="mix-blend-mode:{spec.get("blend", "multiply")}"/>')

    def backdrop(self, b, spec):
        if not spec:
            return
        p = spec.get("pad", 2)
        self.out.append("<rect " + attrs({"x": f"{b[0] - p:.2f}", "y": f"{b[1] - p:.2f}", "width": f"{b[2] - b[0] + 2 * p:.2f}",
                                          "height": f"{b[3] - b[1] + 2 * p:.2f}", "rx": spec.get("radius", 0), "fill": spec.get("fill", "#fff"),
                                          "opacity": spec.get("opacity"), "stroke": spec.get("stroke"), "stroke_width": spec.get("width"),
                                          "filter": self.fx(spec.get("fx"))}) + "/>")

    # ------------------------------------------------------------ boxes of furniture that sits on the map
    def reserve(self):
        """Furniture flagged "on_map" claims its rectangle before icons, labels and trees are placed."""
        D = self.D
        self.decor_boxes = []
        for key in ("title", "compass", "scalebar", "legend", "index"):
            c = D.get(key)
            if c and c.get("on_map"):
                b = getattr(self, f"{key}_box")(c)
                if b:
                    p = c.get("clear", 2)
                    b = (b[0] - p, b[1] - p, b[2] + p, b[3] + p)
                    self.decor_boxes.append(b)
                    self.occupied.append(b)

    def decor_mask(self):
        return [box(*b) for b in getattr(self, "decor_boxes", [])]

    # ------------------------------------------------------------ frame
    def frame(self):
        fr = self.D.get("frame")
        if not fr:
            return
        m = self.map
        col, w = fr.get("color", "#222"), fr.get("width", .4)
        ck = fr.get("checker")
        gap = fr.get("gap", 1.2)
        if ck:  # antique scale border: alternating blocks, one per N metres
            band, seg = ck.get("band", 1.6), ck.get("metres", 250) * m.scale
            segs = []
            for horiz, a0, a1, fixed in ((True, m.fx, m.fx + m.fw, m.fy - band), (True, m.fx, m.fx + m.fw, m.fy + m.fh),
                                         (False, m.fy, m.fy + m.fh, m.fx - band), (False, m.fy, m.fy + m.fh, m.fx + m.fw)):
                i, p = 0, a0
                while p < a1 - 1e-6:
                    q = min(p + seg, a1)
                    if i % 2 == 0:
                        segs.append(f"M{p:.2f},{fixed:.2f}h{q - p:.2f}v{band}h{p - q:.2f}Z" if horiz else f"M{fixed:.2f},{p:.2f}v{q - p:.2f}h{band}v{p - q:.2f}Z")
                    i, p = i + 1, q
            ring = (f"M{m.fx - band:.2f},{m.fy - band:.2f}h{m.fw + 2 * band:.2f}v{m.fh + 2 * band:.2f}h{-(m.fw + 2 * band):.2f}Z"
                    f"M{m.fx:.2f},{m.fy:.2f}v{m.fh:.2f}h{m.fw:.2f}v{-m.fh:.2f}Z")
            self.out.append(f'<path d="{ring}" fill="{ck.get("alt", "#fff")}" fill-rule="evenodd"/>'
                            f'<path d="{"".join(segs)}" fill="{ck.get("fill", col)}"/>'
                            f'<rect x="{m.fx - band}" y="{m.fy - band}" width="{m.fw + 2 * band}" height="{m.fh + 2 * band}" fill="none" stroke="{col}" stroke-width="{w * .6}"/>')
            gap = max(gap, band + fr.get("gap", 1.2))
        rect = lambda o: self.d(box(m.fx - o, m.fy - o, m.fx + m.fw + o, m.fy + m.fh + o), fr.get("wobble", 0), f"fr{o}")
        self.out.append(f'<path d="{rect(0)}" fill="none" stroke="{col}" stroke-width="{w}" stroke-linejoin="miter"/>')
        if fr.get("style") in ("double", "triple"):
            self.out.append(f'<path d="{rect(gap)}" fill="none" stroke="{col}" stroke-width="{fr.get("outer_width", w * 2.2)}"/>')
        if fr.get("style") == "triple":
            self.out.append(f'<path d="{rect(gap * 1.8)}" fill="none" stroke="{col}" stroke-width="{w * .6}"/>')
        co = fr.get("corners")
        if co:
            s, o = co.get("size", 7), co.get("inset", 1.5)
            for sx, sy, x, y in ((1, 1, m.fx + o, m.fy + o), (-1, 1, m.fx + m.fw - o, m.fy + o),
                                 (1, -1, m.fx + o, m.fy + m.fh - o), (-1, -1, m.fx + m.fw - o, m.fy + m.fh - o)):
                self.out.append(glyphs.corner_ornament(x, y, sx, sy, s, co.get("color", col), co.get("width", .3)))

    # ------------------------------------------------------------ title
    def _title_parts(self, t):
        f = self.font(t["font"])
        name = self.fmt(t.get("text", "{name}"))
        subs = [(self.fmt(s["text"]), self.font(s)) for s in t.get("sub", [])]
        subs = [(s, f_) for s, f_ in subs if s.strip(" ·:")]
        return name, f, subs

    def title_box(self, t):
        name, f, subs = self._title_parts(t)
        x, y, anchor = self.ev(t["x"]), self.ev(t["y"]), t.get("anchor", "middle")
        w = max([self.measure(name, f)] + [self.measure(s, f_) for s, f_ in subs]) + (f["size"] * 3.4 if t.get("style") == "ribbon" else 0)
        h0 = f["size"] * (1.9 if t.get("style") == "ribbon" else 1.1)
        h = h0 + sum(f_["size"] * 1.5 for _, f_ in subs) + (f["size"] * .5 if t.get("style") == "ribbon" else 0)
        x0 = x - w / 2 if anchor == "middle" else (x - w if anchor == "end" else x)
        return (x0, y - h0 / 2, x0 + w, y - h0 / 2 + h)

    def title(self):
        t = self.D.get("title")
        if not t:
            return
        name, f, subs = self._title_parts(t)
        x, y, anchor = self.ev(t["x"]), self.ev(t["y"]), t.get("anchor", "middle")
        b = self.title_box(t)
        self.backdrop(b, t.get("backdrop"))
        style = t.get("style", "plain")
        yy = y + f["size"] * .8
        if style == "ribbon":
            rb = t.get("ribbon", {})
            w = self.measure(name, f) + f["size"] * 1.6
            cx = x if anchor == "middle" else (x + w / 2 if anchor == "start" else x - w / 2)
            self.out.append(glyphs.ribbon(cx, y, w, f["size"] * 1.75, rb))
            self.text(cx, y - f["size"] * .04, name, f)
            x, anchor, yy = cx, "middle", y + f["size"] * 1.75
        else:
            if style == "plaque":
                pq = t.get("plaque", {})
                p = pq.get("pad", 3)
                self.out.append(f'<rect x="{b[0] - p:.2f}" y="{b[1] - p:.2f}" width="{b[2] - b[0] + 2 * p:.2f}" height="{b[3] - b[1] + 2 * p:.2f}" '
                                f'fill="{pq.get("fill", "#fff")}" stroke="{pq.get("ink", "#222")}" stroke-width="{pq.get("width", .5)}"/>'
                                f'<rect x="{b[0] - p + 1:.2f}" y="{b[1] - p + 1:.2f}" width="{b[2] - b[0] + 2 * p - 2:.2f}" height="{b[3] - b[1] + 2 * p - 2:.2f}" '
                                f'fill="none" stroke="{pq.get("ink", "#222")}" stroke-width="{pq.get("width", .5) * .4:.2f}"/>')
            self.text(x, y, name, f, anchor)
        for s, f_ in subs:
            yy += f_["size"] * .5
            self.text(x, yy, s, f_, anchor)
            yy += f_["size"] * 1.0
        ru = t.get("rule")
        if ru:
            self.out.append(f'<path d="M{b[0]:.2f},{yy + ru.get("gap", 1.5):.2f} H{b[0] + ru.get("length", b[2] - b[0]):.2f}" stroke="{ru["color"]}" stroke-width="{ru.get("width", .4)}"/>')

    # ------------------------------------------------------------ compass / scale
    def compass_box(self, c):
        x, y, s = self.ev(c["x"]), self.ev(c["y"]), c.get("size", 9)
        return (x - s * 1.05, y - s * 1.5, x + s * 1.05, y + s * 1.05)

    def compass(self):
        c = self.D.get("compass")
        if not c:
            return
        x, y, s = self.ev(c["x"]), self.ev(c["y"]), c.get("size", 9)
        self.backdrop(self.compass_box(c), c.get("backdrop"))
        mk, (lx, ly) = glyphs.compass(x, y, s, c, c.get("style", "rose8"))
        self.out.append(mk)
        if c.get("font"):
            self.text(lx, ly, tr("north", self.lang), c["font"])

    def _scale_len(self, s):
        if s.get("metres"):
            return s["metres"]
        target = self.map.fw * s.get("fraction", .22) / self.map.scale
        return max([n for n in NICE if n <= target] or [NICE[0]])

    def scalebar_box(self, s):
        L = self._scale_len(s) * self.map.scale
        x, y = self.ev(s["x"]), self.ev(s["y"])
        x0 = x - L / 2 if s.get("anchor") == "middle" else (x - L if s.get("anchor") == "end" else x)
        return (x0 - 2, y - 2, x0 + L + 6, y + 6)

    def scalebar(self):
        s = self.D.get("scalebar")
        if not s:
            return
        metres = self._scale_len(s)
        L = metres * self.map.scale
        b = self.scalebar_box(s)
        self.backdrop(b, s.get("backdrop"))
        x, y, col = b[0] + 2, self.ev(s["y"]), s.get("color", "#222")
        segs, h = s.get("segments", 4), s.get("h", 1.3)
        f = s["font"]
        unit = lambda v: f"{v:g} {tr('m', self.lang)}" if v < 1000 else f"{v / 1000:g} {tr('km', self.lang)}"
        if s.get("style") == "line":
            d = f"M{x:.2f},{y:.2f}H{x + L:.2f}" + "".join(f"M{x + i * L / segs:.2f},{y:.2f}v{-h if i % segs else -h * 1.8:.2f}" for i in range(segs + 1))
            self.out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{s.get("width", .3)}" stroke-linecap="round"/>')
        else:
            for i in range(segs):
                self.out.append(f'<rect x="{x + i * L / segs:.2f}" y="{y:.2f}" width="{L / segs:.2f}" height="{h}" '
                                f'fill="{col if i % 2 == 0 else s.get("alt", "none")}" stroke="{col}" stroke-width=".2"/>')
        ty = y + h + self.font(f)["size"] * .9 if s.get("style") != "line" else y + self.font(f)["size"] * 1.0
        self.text(x, ty, "0", f)
        self.text(x + L / 2, ty, unit(metres / 2), f)
        self.text(x + L, ty, unit(metres), f)

    # ------------------------------------------------------------ automatic legend
    def legend_items(self):
        L, P, items = self.L, self.present, []
        first = lambda d, *ks: next((d[k] for k in ks if k in d), None) if d else None
        def line(rule, key, **kw):
            if rule:
                items.append(("line", rule, tr(key, self.lang, **kw), key))
        if "road_major" in P:
            line(first(L.get("roads"), "major", "*"), "road_major")
        if "road_minor" in P:
            line(first(L.get("roads"), "minor", "*"), "road_minor")
        if "track" in P:
            line(first(L.get("tracks"), "*", "track"), "track")
        if "path" in P:
            line(first(L.get("paths"), "*", "path"), "path")
        if "my_route" in P:
            line(self.st.get("custom", {}).get("path"), "my_route")
        if "river" in P:
            line(first(L.get("waterways"), "river", "*"), "river")
        if "stream" in P:
            line(first(L.get("waterways"), "stream", "*"), "stream")
        c = self.R.get("contours")
        if "contour" in P and c:
            line({"stroke": c["color"], "width": c.get("index_width", c["width"] * 2)}, "contour", n=c.get("every", 10))
        lc = L.get("landcover", {})
        for kind, key in (("wood", "wood"), ("scrub", "scrub"), ("farmland", "farmland"), ("meadow", "meadow"), ("grass", "meadow"),
                          ("grassland", "meadow"), ("orchard", "orchard"), ("vineyard", "vineyard"), ("cemetery", "cemetery")):
            if kind in P and kind in lc and not any(i[2] == tr(key, self.lang) for i in items):
                items.append(("area", lc[kind], tr(key, self.lang), kind))
        if "sea" in P:
            items.append(("area", first(L.get("water"), "sea", "*"), tr("sea", self.lang), "water"))
        if "lake" in P:
            items.append(("area", first(L.get("water"), "*"), tr("lake", self.lang), "water"))
        if "building" in P:
            items.append(("area", first(L.get("buildings"), "*"), tr("building", self.lang), "building"))
        for rule in (self.st.get("symbols") or {}).values():
            if rule.get("legend") in P and not any(i[2] == tr(rule["legend"], self.lang) for i in items):
                items.append(("symbol", rule, tr(rule["legend"], self.lang), rule["legend"]))
        skip = set(self.D.get("legend", {}).get("skip", []))
        return [i for i in items if i[3] not in skip]

    def legend_box(self, lg):
        n = len(self.legend_items()) if getattr(self, "present", None) else lg.get("expect", 12)
        cols = lg.get("columns", 1)
        rows = math.ceil(n / cols)
        x, y = self.ev(lg["x"]), self.ev(lg["y"])
        top = y - (lg.get("gap", 5) * 1.5 if lg.get("title", True) else lg.get("gap", 5) * .5)
        return (x, top, x + cols * lg.get("col_width", 45), y + (rows - .5) * lg.get("gap", 5))

    def legend(self):
        lg = self.D.get("legend")
        if not lg:
            return
        items = self.legend_items()
        if not items:
            return
        self.backdrop(self.legend_box(lg), lg.get("backdrop"))
        x0, y, gap, f = self.ev(lg["x"]), self.ev(lg["y"]), lg.get("gap", 5), lg["font"]
        sw = lg.get("swatch", 8)
        if lg.get("title", True):
            self.text(x0, y - gap * 1.25, tr("legend", self.lang), lg.get("title_font", f), "start")
        per = math.ceil(len(items) / lg.get("columns", 1))
        for i, (kind, rule, label, lk) in enumerate(items):
            x, yy = x0 + (i // per) * lg.get("col_width", 45), y + (i % per) * gap
            if kind == "line":
                d = f"M{x:.2f},{yy:.2f} H{x + sw:.2f}"
                if rule.get("casing"):
                    self.out.append(f'<path d="{d}" stroke="{rule["casing"]["color"]}" stroke-width="{rule["casing"]["width"]}" fill="none"/>')
                self.out.append("<path " + attrs({"d": d, "stroke": rule.get("stroke", "#000"), "stroke_width": rule.get("width", .3),
                                                  "stroke_dasharray": rule.get("dash"), "fill": "none", "stroke_linecap": rule.get("linecap", "round")}) + "/>")
                if rule.get("inner"):
                    self.out.append(f'<path d="{d}" stroke="{rule["inner"]["stroke"]}" stroke-width="{rule["inner"].get("width", .15)}" fill="none"/>')
            elif kind == "area":
                h = gap * .62
                if lk == "building" and rule.get("glyph"):
                    for j in range(2):
                        self.use(f"lgb{j}", rule["glyph"], j, dict(rule.get("style", {}), roof=(rule.get("roofs") or ["#a44"])[j % len(rule.get("roofs") or [1])]),
                                 x + sw * (.3 + .4 * j), yy + h * .5, h * 1.15)
                else:
                    fill = rule.get("fill") or (rule.get("roofs") or ["none"])[0]
                    edge = (rule.get("edge") or {}).get("stroke") or rule.get("stroke")
                    self.out.append("<rect " + attrs({"x": f"{x:.2f}", "y": f"{yy - h / 2:.2f}", "width": sw, "height": f"{h:.2f}", "fill": fill,
                                                      "fill_opacity": rule.get("fill_opacity"), "stroke": edge, "stroke_width": .2 if edge else None}) + "/>")
                    ht = rule.get("hatch")
                    if ht:
                        hl = self.hatch(box(x, yy - h / 2, x + sw, yy + h / 2), dict(ht, angle=ht["angle"] if isinstance(ht.get("angle"), (int, float)) else 18,
                                                                                    inset=0, angle_jitter=0), f"lgh{i}")
                        self.out.append("<path " + attrs({"d": self.d(hl), "fill": "none", "stroke": ht["color"], "stroke_width": ht.get("width", .1),
                                                          "opacity": ht.get("opacity"), "stroke_dasharray": ht.get("dash")}) + "/>")
                    if not rule.get("fill") and not edge and not ht:
                        self.out.append(f'<rect x="{x:.2f}" y="{yy - h / 2:.2f}" width="{sw}" height="{h:.2f}" fill="none" stroke="{self.font(f).get("color", "#000")}" stroke-width=".12" opacity=".5"/>')
                    for j, sc in enumerate(self.st.get("scatter", [])):
                        on = sc.get("on")
                        if (lk == on or (isinstance(on, list) and lk in on)) and sc.get("layer", "trees") in ("trees", "ground") and "count" not in sc:
                            g = sc["glyph"] if isinstance(sc["glyph"], list) else [sc["glyph"]]
                            for q in range(2):
                                self.use(f"lg{j}", g[q % len(g)], q, sc.get("style", {}), x + sw * (.28 + .44 * q), yy + h * .5, min(h * 1.25, 3.2))
                            break
            else:
                self.symbol(x + sw / 2, yy, rule)
            self.text(x + sw + 2.2, yy, label, f, "start")

    # ------------------------------------------------------------ landmark index ("places of note")
    def index_box(self, ix):
        n = len(self.lm_plan) if getattr(self, "lm_plan", None) is not None else ix.get("expect", 12)
        cols = ix.get("columns", 3)
        x, y = self.ev(ix["x"]), self.ev(ix["y"])
        return (x, y - ix.get("row", 8) * 1.2, x + cols * ix.get("col_width", 60), y + (math.ceil(n / cols) - .3) * ix.get("row", 8))

    def index(self):
        ix = self.D.get("index")
        if not ix or not self.lm_plan:
            return
        self.backdrop(self.index_box(ix), ix.get("backdrop"))
        x0, y, row, f = self.ev(ix["x"]), self.ev(ix["y"]), ix.get("row", 8), ix["font"]
        s, cw = ix.get("icon", 6.5), ix.get("col_width", 60)
        if ix.get("title", True):
            self.text(x0, y - row * .95, tr("places_of_note", self.lang), ix.get("title_font", f), "start")
        items = sorted(self.lm_plan, key=lambda i: (i["rank"], self.lm_name(i["lm"])))[: ix.get("max", 99)]
        cols = ix.get("columns", 3)
        for i, it in enumerate(items):
            x, yy = x0 + (i % cols) * cw, y + (i // cols) * row
            self.draw_icon(self.d_ / "icons" / it["lm"]["icon"], x + s / 2, yy + s * .47, s, halo=False)
            tx = x + s + 1.6
            if it["num"] is not None:
                pin = (self.st.get("landmarks") or {}).get("pin", {})
                self.out.append(f'<circle cx="{tx + 1.4:.2f}" cy="{yy:.2f}" r="1.4" fill="{pin.get("fill", "#c33")}"/>')
                self.text(tx + 1.4, yy, str(it["num"]), pin.get("font", {"font": "@text", "size": 1.9, "color": "#fff", "weight": "bold"}))
                tx += 3.6
            ls = self.fit_lines(self.lm_name(it["lm"]), f, cw - (tx - x) - 2, 2)
            fs = self.font(f)["size"]
            for j, t in enumerate(ls):
                self.text(tx, yy + (j - (len(ls) - 1) / 2) * fs * 1.1, t, f, "start")

    def fit_lines(self, text, f, max_w, max_lines):
        """Greedy word wrap into at most max_lines lines no wider than max_w; the last one ends in … if it must."""
        out, cur = [], ""
        for w in text.split():
            t = f"{cur} {w}".strip()
            if cur and self.measure(t, f) > max_w:
                out.append(cur)
                cur = w
            else:
                cur = t
        out.append(cur)
        if len(out) > max_lines:
            out = out[:max_lines - 1] + [" ".join(out[max_lines - 1:])]
        last = out[-1]
        if self.measure(last, f) > max_w:
            while last and self.measure(last + "…", f) > max_w:
                last = last[:-1]
            out[-1] = last.rstrip(" ,.-") + "…"
        return out

    # ------------------------------------------------------------ loose text, panels, attribution
    def ornaments(self):
        """Free decorations anywhere on the page: a moon, stars, a sun, any glyph. {glyph, x, y, size, style, variant, opacity}"""
        for i, o in enumerate(self.D.get("ornaments", [])):
            self.out.append("<g " + attrs({"opacity": o.get("opacity")}) + ">")
            self.use(f"orn{i}", o["glyph"], o.get("variant", 0), o.get("style", {}), self.ev(o["x"]), self.ev(o["y"]), o.get("size", 6), rot=o.get("rot", 0))
            self.out.append("</g>")

    def panels(self):
        for pn in self.st.get("panels", []):
            a = {k: (self.ev(v) if k in ("x", "y", "width", "height") else v) for k, v in pn.items()}
            self.out.append(f"<rect {attrs(a)}/>")

    def texts(self):
        for blk in self.D.get("texts", []):
            x, y = self.ev(blk["x"]), self.ev(blk["y"])
            f = self.font(blk)
            lines_ = [self.fmt(l) for l in blk["lines"]]
            for i, line in enumerate(l for l in lines_ if l.strip()):
                self.text(x, y + i * blk.get("gap", f["size"] * 1.5), line, f, blk.get("anchor", "start"))
        gl = (self.st.get("grid") or {}).get("edge_labels")
        if gl:
            for x, y, txt, anchor in self.grid_edge_labels:
                self.text(x, y, txt, gl, anchor)
        a = self.D.get("attribution")
        if a:
            self.text(self.ev(a.get("x", "W - m")), self.ev(a["y"]), tr("attribution", self.lang), a, a.get("anchor", "end"))
