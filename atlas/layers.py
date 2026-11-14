"""Map content: land cover, relief, water, ways, buildings and scattered illustrations."""
import json, math

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point, shape
from shapely.ops import unary_union

from . import glyphs
from .core import seeded, tr
from .textures import hillshade_uri

LINE_TOKENS = ("tracks", "paths", "roads")


def attrs(d):
    return " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in d.items() if v is not None)


def polys(g):
    if g.geom_type == "Polygon":
        return [g]
    return [p for p in getattr(g, "geoms", []) for p in polys(p)]


def lines(g):
    if g.geom_type in ("LineString", "LinearRing"):
        return [g]
    return [p for q in getattr(g, "geoms", []) for p in lines(q)]


class Layers:
    # ------------------------------------------------------------ path data
    def _wob(self, cs, amp, phase, step=1.1):
        """Hand-drawn wobble: densify, then push points along a smooth noise field. The field depends only on
        position (+ phase), so polygons that share an edge still meet after wobbling."""
        out = []
        f = self.st.get("wobble_freq", 0.75)
        for (x0, y0), (x1, y1) in zip(cs[:-1], cs[1:]):
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
            for i in range(n):
                t = i / n
                out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
        out.append(cs[-1])
        res = []
        for x, y in out:
            dx = math.sin(y * f + phase) + .6 * math.sin(x * f * .63 + phase * 1.7) + .4 * math.sin((x + y) * f * 2.9 + phase * .3)
            dy = math.sin(x * f + phase * 2.1) + .6 * math.cos(y * f * .59 + phase) + .4 * math.sin((x - y) * f * 3.1 + phase * .7)
            res.append((x + dx * amp * .6, y + dy * amp * .6))
        return res

    def d(self, geom, wobble=0.0, key="d", phase=None):
        phase = float(self.seed) if phase is None else phase
        parts = []

        def ring(cs, close):
            cs = [(c[0], c[1]) for c in cs]
            if wobble and len(cs) >= 2:
                cs = self._wob(cs, wobble, phase)
            if len(cs) >= 2:
                parts.append("M" + " ".join(f"{x:.2f},{y:.2f}" for x, y in cs) + ("Z" if close else ""))

        for p in polys(geom):
            ring(p.exterior.coords, True)
            for i in p.interiors:
                ring(i.coords, True)
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            for l in lines(geom):
                ring(l.coords, False)
        return " ".join(parts)

    def dd(self, geoms, wobble=0.0, key="d", phase=None):
        return " ".join(filter(None, (self.d(g, wobble, key, phase) for g in geoms)))

    def fx(self, name, geoms=None):
        """Filter reference. With geoms, the filter region is their bounding box (filters are slow: keep regions small)."""
        if not name:
            return None
        if not geoms:
            return f"url(#fx-{name})"
        bs = [g.bounds for g in geoms]
        b = (min(x[0] for x in bs) - 3, min(x[1] for x in bs) - 3, max(x[2] for x in bs) + 3, max(x[3] for x in bs) + 3)
        return f"url(#{self.filter_def(name, b)})"

    # ------------------------------------------------------------ generic rule drawing
    def draw_area(self, geoms, rule, key):
        if not geoms or rule.get("hide"):
            return
        w = rule.get("wobble", 0)
        d = self.dd(geoms, w, key)
        if not d:
            return
        o = self.out
        sh = rule.get("shadow")
        if sh:
            o.append(f'<path d="{d}" transform="translate({sh.get("dx", .25)},{sh.get("dy", .25)})" fill="{sh.get("color", "#000")}" '
                     f'opacity="{sh.get("opacity", .3)}"/>')
        if rule.get("fill") or rule.get("stroke"):
            o.append("<path " + attrs({"d": d, "fill": rule.get("fill", "none"), "fill_opacity": rule.get("fill_opacity"),
                                       "fill_rule": "evenodd", "stroke": rule.get("stroke", "none"), "stroke_width": rule.get("width"),
                                       "stroke_dasharray": rule.get("dash"), "stroke_linejoin": "round",
                                       "opacity": rule.get("opacity"), "filter": self.fx(rule.get("fx"), geoms)}) + "/>")
        pool = rule.get("pool")  # pigment pooling at the edge (watercolour)
        if pool:
            cid = self.uid("cp")
            self.defs.append(f'<clipPath id="{cid}"><path d="{d}" clip-rule="evenodd"/></clipPath>')
            o.append(f'<g clip-path="url(#{cid})"><path d="{d}" fill="none" stroke="{pool["color"]}" stroke-width="{pool.get("width", 1.6)}" '
                     f'opacity="{pool.get("opacity", .4)}" filter="{self.fx(pool.get("fx", "blur"), geoms)}"/></g>')
        h = rule.get("hatch")
        if h:
            hd = " ".join(filter(None, (self.d(self.hatch(p, h, f"{key}h{i}"), h.get("wobble", 0), f"{key}hw{i}")
                                        for i, g in enumerate(geoms) for p in polys(g) if p.area > h.get("min_area", 4))))
            if hd:
                o.append("<path " + attrs({"d": hd, "fill": "none", "stroke": h["color"], "stroke_width": h.get("width", .1),
                                           "opacity": h.get("opacity"), "stroke_dasharray": h.get("dash"), "stroke_linecap": "round"}) + "/>")
        e = rule.get("edge")
        if e:
            o.append("<path " + attrs({"d": self.dd(geoms, e.get("wobble", w), key + "e"), "fill": "none", "stroke": e["stroke"],
                                       "stroke_width": e.get("width", .2), "opacity": e.get("opacity"), "stroke_dasharray": e.get("dash"),
                                       "stroke_linejoin": "round", "stroke_linecap": "round", "filter": self.fx(e.get("fx"), geoms)}) + "/>")

    def hatch(self, poly, h, key):
        rng = seeded(self.seed, key)
        ang = h.get("angle", "auto")
        if ang == "auto":
            cs = list(poly.minimum_rotated_rectangle.exterior.coords)
            e = max(zip(cs[:-1], cs[1:]), key=lambda s: math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]))
            ang = math.degrees(math.atan2(e[1][1] - e[0][1], e[1][0] - e[0][0])) + (90 if h.get("across") else 0)
        ang += rng.uniform(-1, 1) * h.get("angle_jitter", 0)
        gap = h.get("gap", 1.0)
        minx, miny, maxx, maxy = poly.bounds
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        R = math.hypot(maxx - minx, maxy - miny) / 2 + gap
        ls, o = [], -R + rng.uniform(0, gap)
        while o < R:
            ls.append(LineString([(cx - R, cy + o), (cx + R, cy + o)]))
            o += gap * (1 + rng.uniform(-1, 1) * h.get("gap_jitter", 0.15))
        ml = affinity.rotate(MultiLineString(ls), ang, origin=(cx, cy))
        try:
            return ml.intersection(poly.buffer(-h.get("inset", 0.25)))
        except Exception:
            return LineString()

    def line_rule(self, geoms, rule, key, casing_only=False, stroke_only=False):
        if not geoms or rule.get("hide"):
            return
        w = rule.get("wobble", 0)
        o = self.out
        if not stroke_only and rule.get("casing"):
            c = rule["casing"]
            o.append("<path " + attrs({"d": self.dd(geoms, w, key), "fill": "none", "stroke": c["color"], "stroke_width": c["width"],
                                       "stroke_linecap": c.get("linecap", "round"), "stroke_linejoin": "round",
                                       "opacity": c.get("opacity"), "filter": self.fx(rule.get("fx"), geoms)}) + "/>")
        if casing_only:
            return
        for p in range(1 + int(rule.get("sketch", 0))):
            o.append("<path " + attrs({"d": self.dd(geoms, w if p == 0 else max(w, .12) * 1.5, key, None if p == 0 else self.seed + p * 37.3), "fill": "none",
                                       "stroke": rule.get("stroke", "#000"), "stroke_width": rule.get("width", .3) * (1 if p == 0 else .6),
                                       "stroke_dasharray": rule.get("dash"), "stroke_linecap": rule.get("linecap", "round"),
                                       "stroke_linejoin": "round", "opacity": rule.get("opacity") if p == 0 else .5,
                                       "filter": self.fx(rule.get("fx"), geoms)}) + "/>")
        inner = rule.get("inner")
        if inner:
            o.append("<path " + attrs({"d": self.dd(geoms, w, key), "fill": "none", "stroke": inner["stroke"],
                                       "stroke_width": inner.get("width", .15), "stroke_dasharray": inner.get("dash"),
                                       "stroke_linecap": "round", "opacity": inner.get("opacity")}) + "/>")

    def by_kind(self, layer, rules):
        """[(rule, geoms, kind)] in the order the theme lists the kinds."""
        if not rules:
            return []
        groups = {}
        for g, p in self.geo.get(layer, []):
            k = p.get("kind")
            k = k if k in rules else "*"
            if k in rules:
                groups.setdefault(k, []).append(g)
        return [(rules[k], groups[k], k) for k in rules if k in groups]

    # ------------------------------------------------------------ land cover
    def landcover(self):
        for rule, geoms, kind in self.by_kind("landcover", self.L.get("landcover")):
            self.present.add(kind)
            self.draw_area(geoms, rule, "lc" + kind)

    # ------------------------------------------------------------ relief
    def hillshade(self):
        hs = self.R.get("hillshade")
        if not hs or hs.get("hide") or not self.dem:
            return
        D = self.dem
        az, alt = math.radians(hs.get("azimuth", 315)), math.radians(hs.get("altitude", 45))
        z = hs.get("exaggeration", 1.3)
        nx, ny = -D.gx * z, -D.gy * z  # surface normal (east, north, up=1)
        norm = np.sqrt(nx * nx + ny * ny + 1)
        shade = np.clip((nx * math.sin(az) * math.cos(alt) + ny * math.cos(az) * math.cos(alt) + math.sin(alt)) / norm, 0, 1)
        x0, y0 = self.map.xy(D.w, D.n)
        x1, y1 = self.map.xy(D.e, D.s)
        self.out.append(f'<image x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" preserveAspectRatio="none" '
                        f'{attrs({"opacity": hs.get("opacity"), "style": "mix-blend-mode:" + hs["blend"] if hs.get("blend") else None})} '
                        f'href="{hillshade_uri(shade, hs)}"/>')

    def contours(self):
        c = self.R.get("contours")
        f = self.d_ / "contours.json"
        if not c or c.get("hide") or not f.exists():
            return
        every, ie = c.get("every", 10), c.get("index_every", 50)
        norm, idx = [], []
        for ft in json.loads(f.read_text())["features"]:
            ele = ft["properties"]["ele"]
            if ele % every:
                continue
            g = self.map.page(shape(ft["geometry"]))
            if g is not None:
                (idx if ele % ie == 0 else norm).append((g, ele))
        self.present.add("contour")
        for items, w in ((norm, c["width"]), (idx, c.get("index_width", c["width"] * 2))):
            self.out.append("<path " + attrs({"d": self.dd([g for g, _ in items], c.get("wobble", 0), "ct"), "fill": "none", "stroke": c["color"],
                                              "stroke_width": w, "stroke_opacity": c.get("opacity"), "stroke_dasharray": c.get("dash"),
                                              "stroke_linejoin": "round", "filter": self.fx(c.get("fx"))}) + "/>")
        lab = c.get("labels")
        if lab:
            f_ = dict(lab)
            f_.setdefault("color", c["color"])
            for g, ele in idx:
                for ln in lines(g):
                    if ln.length < lab.get("min_length", 60):
                        continue
                    p, p2 = ln.interpolate(0.5, normalized=True), ln.interpolate(min(ln.length, ln.length / 2 + 1))
                    ang = math.degrees(math.atan2(p2.y - p.y, p2.x - p.x))
                    ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
                    self.text(p.x, p.y, str(ele), f_, rotate=ang)

    def hachures(self):
        h = self.R.get("hachures")
        if not h or h.get("hide") or not self.dem:
            return
        m, rng = self.map, np.random.default_rng(self.seed)
        sp = h.get("spacing", 1.0)
        xs, ys = np.meshgrid(np.arange(m.fx, m.fx + m.fw, sp), np.arange(m.fy, m.fy + m.fh, sp))
        xs = xs.ravel() + rng.uniform(-.4, .4, xs.size) * sp
        ys = ys.ravel() + rng.uniform(-.4, .4, ys.size) * sp
        _, gx, gy = self.dem.at_page(xs, ys)
        slope = np.hypot(gx, gy)
        lo, hi = h.get("min_slope", 0.16), h.get("max_slope", 0.75)
        keep = slope > lo
        avoid = self.mask(h.get("avoid", ["water"]), 0.3)
        if avoid is not None:
            keep &= ~shapely.contains_xy(avoid, xs, ys)
        xs, ys, gx, gy, slope = xs[keep], ys[keep], gx[keep], gy[keep], slope[keep]
        t = np.clip((slope - lo) / (hi - lo), 0, 1)
        dx, dy = -gx / slope, gy / slope  # downhill, in page axes (y down)
        l0, l1 = h.get("length", [0.5, 1.5])
        ln = (l0 + (l1 - l0) * t) * rng.uniform(.8, 1.15, t.size)
        la = math.radians(h.get("light", 315))
        shade = 0.5 + 0.5 * (dx * -math.sin(la) + dy * math.cos(la))  # 1 = faces away from the light
        w0, w1 = h.get("width", [0.07, 0.2])
        wd = w0 + (w1 - w0) * np.clip(shade * (0.4 + 0.6 * t), 0, 1)
        buckets = {}
        for x, y, ax, ay, l, w in zip(xs, ys, dx, dy, ln, wd):
            buckets.setdefault(round(float(w) * 25) / 25, []).append(
                f"M{x - ax * l / 2:.2f},{y - ay * l / 2:.2f}L{x + ax * l / 2:.2f},{y + ay * l / 2:.2f}")
        for w, segs in sorted(buckets.items()):
            self.out.append(f'<path d="{"".join(segs)}" fill="none" stroke="{h["color"]}" stroke-width="{w:.2f}" stroke-linecap="round" '
                            f'{attrs({"opacity": h.get("opacity"), "filter": self.fx(h.get("fx"))})}/>')

    def peaks(self):
        pk = self.R.get("peaks")
        if not pk or pk.get("hide") or not self.dem:
            return
        from skimage.feature import peak_local_max
        X, Y = self.dem.grid_page()
        m = self.map
        pad = pk.get("margin", 12 if pk.get("glyph") else 6)
        inside = (X > m.fx + pad) & (X < m.fx + m.fw - pad) & (Y > m.fy + pad) & (Y < m.fy + m.fh - pad)
        if self.decor_boxes:
            for b in self.decor_boxes:
                inside &= ~((X > b[0]) & (X < b[2]) & (Y > b[1]) & (Y < b[3]))
        lo_f, hi_f = self.frame_elev
        inside &= self.dem.z > lo_f + (hi_f - lo_f) * pk.get("min_height", 0.3)   # no "peaks" on plains or at sea
        wm = self.mask(["water"], 1.0)
        if wm is not None:
            inside &= ~shapely.contains_xy(wm, X.ravel(), Y.ravel()).reshape(X.shape)
        z = np.where(inside, self.dem.z, self.dem.z.min())
        px_per_mm = self.dem.wd / (X.max() - X.min())
        found = peak_local_max(z, min_distance=max(3, int(pk.get("min_distance", 14) * px_per_mm)), num_peaks=pk.get("count", 6), exclude_border=False)
        found = [(r, c) for r, c in found if inside[r, c]]
        if not len(found):
            return
        zs = [float(self.dem.raw[r, c]) for r, c in found]
        lo, hi = min(zs), max(zs)
        for (r, c), ele in sorted(zip(found, zs), key=lambda t: Y[t[0][0], t[0][1]]):
            x, y = float(X[r, c]), float(Y[r, c])
            t = (ele - lo) / (hi - lo) if hi > lo else 1
            if pk.get("glyph"):
                s0, s1 = pk.get("size", [4, 7])
                size = s0 + (s1 - s0) * t
                self.use(f"pk-{pk['glyph']}", pk["glyph"], seeded(self.seed, r, c).randrange(3), pk.get("style", {}), x, y + size * .3, size)
                self.occupied.append((x - size * .6, y - size * .7, x + size * .6, y + size * .3))
            elif pk.get("symbol"):
                self.symbol(x, y, pk["symbol"])
                self.occupied.append((x - 1, y - 1, x + 1, y + 1))
            else:
                dot = pk.get("dot", {})
                self.out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{dot.get("size", .45)}" fill="{dot.get("color", "#333")}"/>')
                self.occupied.append((x - .6, y - .6, x + .6, y + .6))
            if pk.get("label"):
                self.deferred_spots.append((x, y, f"{ele:.0f}", pk["label"], (pk.get("size", [4, 7])[1] * .35 if pk.get("glyph") else 1.0)))

    # ------------------------------------------------------------ water
    def water(self):
        rules = self.L.get("water")
        if not rules:
            return
        for rule, geoms, kind in self.by_kind("water", rules):
            self.present.add("sea" if kind == "sea" else "lake")
            self.draw_area(geoms, rule, "wt" + kind)
            sl = rule.get("shorelines")
            if sl:
                u = unary_union(geoms)
                for i in range(sl.get("count", 3)):
                    ring = u.buffer(-(i + 1) * sl.get("gap", .6))
                    if ring.is_empty:
                        break
                    # rings follow the shore, not the map frame
                    line = ring.boundary.difference(self.map.frame.buffer(-.05).boundary.buffer(sl.get("gap", .6) * (i + 1) + .1))
                    if line.is_empty:
                        continue
                    self.out.append("<path " + attrs({"d": self.d(line, sl.get("wobble", 0), f"sl{i}"), "fill": "none", "stroke": sl["color"],
                                                      "stroke_width": round(sl.get("width", .12) * (1 - i * .15), 3), "stroke_linecap": "round",
                                                      "opacity": round(sl.get("opacity", .7) * (1 - i / (sl.get("count", 3) + 1)), 2)}) + "/>")

    def waterways(self):
        groups = self.by_kind("waterways", self.L.get("waterways"))
        for rule, geoms, kind in groups:
            self.present.add("river" if kind == "river" else "stream")
            self.line_rule(geoms, rule, "ww" + kind, casing_only=True)
        for rule, geoms, kind in groups:
            self.line_rule(geoms, rule, "ww" + kind, stroke_only=True)

    # ------------------------------------------------------------ ways
    def ways(self, token):
        if not self._casings_done:
            self._casings_done = True
            for t in [t for t in self.order if t in LINE_TOKENS]:
                for rule, geoms, kind in self.by_kind(t, self.L.get(t)):
                    self.line_rule(geoms, rule, t + kind, casing_only=True)
        for rule, geoms, kind in self.by_kind(token, self.L.get(token)):
            self.present.add({"tracks": "track", "paths": "path"}.get(token, "road_" + kind))
            self.line_rule(geoms, rule, token + kind, stroke_only=True)

    def bridges(self):
        b = self.st.get("bridges")
        if not b or b.get("hide"):
            return
        ww = [g for g, p in self.geo.get("waterways", []) if p.get("kind") in ("river", "stream", "canal")]
        if not ww:
            return
        tree = shapely.STRtree(ww)
        size, seen = b.get("size", 1.4), []
        for layer in ("roads", "tracks"):
            for road, p in self.geo.get(layer, []):
                half = b.get("half_width", {}).get(p.get("kind"), b.get("gap", .7))
                for i in tree.query(road, predicate="intersects"):
                    for pt in (lambda x: [x] if x.geom_type == "Point" else [q for q in getattr(x, "geoms", []) if q.geom_type == "Point"])(road.intersection(ww[i])):
                        if not self.map.inside(pt.x, pt.y, 1) or any(math.hypot(pt.x - a, pt.y - c) < size for a, c in seen):
                            continue
                        seen.append((pt.x, pt.y))
                        for rl in lines(road):
                            if rl.distance(pt) < 1e-6:
                                s = rl.project(pt)
                                a, c = rl.interpolate(max(0, s - size / 2)), rl.interpolate(min(rl.length, s + size / 2))
                                ux, uy = c.x - a.x, c.y - a.y
                                n = math.hypot(ux, uy) or 1
                                ux, uy = ux / n, uy / n
                                nx, ny = -uy, ux
                                if b.get("deck"):
                                    self.out.append(f'<path d="M{a.x:.2f},{a.y:.2f}L{c.x:.2f},{c.y:.2f}" stroke="{b["deck"]}" stroke-width="{half * 2:.2f}"/>')
                                for sgn in (-1, 1):
                                    ox, oy = nx * half * sgn, ny * half * sgn
                                    fl = size * .28
                                    self.out.append(
                                        f'<path d="M{a.x + ox - ux * fl + nx * fl * sgn:.2f},{a.y + oy - uy * fl + ny * fl * sgn:.2f} L{a.x + ox:.2f},{a.y + oy:.2f} '
                                        f'L{c.x + ox:.2f},{c.y + oy:.2f} L{c.x + ox + ux * fl + nx * fl * sgn:.2f},{c.y + oy + uy * fl + ny * fl * sgn:.2f}" '
                                        f'fill="none" stroke="{b.get("stroke", "#000")}" stroke-width="{b.get("width", .22)}" stroke-linecap="round" stroke-linejoin="round"/>')
                                break

    # ------------------------------------------------------------ buildings
    def buildings(self):
        rules = self.L.get("buildings")
        items = self.geo.get("buildings", [])
        if not rules or not items:
            return
        rule = rules.get("*", {})
        if rule.get("hide"):
            return
        self.present.add("building")
        gl = rule.get("glyph")
        if gl:
            # "blocks": draw city buildings (by tag, or by footprint) as a second glyph, e.g. apartment blocks
            bk = rule.get("blocks") or {}
            bk_tags = set(bk.get("tags", ["apartments", "commercial", "office", "retail", "hotel", "dormitory", "hospital",
                                           "university", "college", "public", "civic", "government", "industrial"]))
            bk_area = bk.get("min_area", 450) * self.map.scale ** 2   # m² → page units²
            is_block = (lambda g, p: p.get("building") in bk_tags or g.area >= bk_area) if bk.get("glyph") else (lambda g, p: False)
            pts = sorted(((g.centroid.x, g.centroid.y, p.get("id", ""), is_block(g, p)) for g, p in items), key=lambda t: t[1])
            s0, s1 = rule.get("size", [1.5, 2.0])
            roofs = rule.get("roofs") or [rule.get("style", {}).get("roof", "#a44")]
            keep, grid = [], set()
            cell = rule.get("min_gap", 0.0)
            clear = self.mask(["landmarks", "decor"], 0)
            for x, y, i, blk in pts:  # thin out so tiny houses do not pile up; keep clear of icons and furniture
                c = cell * bk.get("gap_scale", 1.3) if blk else cell
                k = (round(x / c), round(y / c), blk) if c else (x, y, blk)
                if k in grid or (clear is not None and shapely.contains_xy(clear, x, y)):
                    continue
                grid.add(k)
                keep.append((x, y, i, blk))
            walls = rule.get("walls") or [rule.get("style", {}).get("fill", "#fff")]   # e.g. lit and dark windows at night
            b_roofs = bk.get("roofs") or roofs
            b_walls = bk.get("walls") or walls
            b0, b1 = bk.get("size", [s0 * 1.1, s1 * 1.2])
            for x, y, i, blk in keep:
                r = seeded(self.seed, i)
                if blk:
                    ri, wi = r.randrange(len(b_roofs)), r.randrange(len(b_walls))
                    self.use(f"bk{ri}w{wi}", bk["glyph"], r.randrange(3), dict(rule.get("style", {}), **bk.get("style", {}), roof=b_roofs[ri], fill=b_walls[wi]),
                             x, y + b0 * .3, r.uniform(b0, b1))
                    continue
                ri, wi = r.randrange(len(roofs)), r.randrange(len(walls))
                self.use(f"bd{ri}w{wi}", gl, r.randrange(3), dict(rule.get("style", {}), roof=roofs[ri], fill=walls[wi]), x, y + s0 * .3, r.uniform(s0, s1))
            return
        geoms = [g for g, _ in items]
        roofs = rule.get("roofs")
        if roofs:
            sh = rule.get("shadow")
            if sh:
                self.draw_area(geoms, {"shadow": sh}, "bds")
            for i, c in enumerate(roofs):
                sub = [g for g, p in items if seeded(self.seed, p.get("id")).randrange(len(roofs)) == i]
                self.draw_area(sub, {k: v for k, v in dict(rule, fill=c).items() if k != "shadow"}, f"bd{i}")
        else:
            self.draw_area(geoms, rule, "bd")

    # ------------------------------------------------------------ scatter (trees, tufts, animals, boats, birds…)
    def region(self, on):
        key = json.dumps(on)
        if key not in self._regions:
            parts = []
            for k in ([on] if isinstance(on, str) else on):
                if k == "frame":
                    parts.append(self.map.frame)
                elif k == "water":
                    parts += [g for g, _ in self.geo.get("water", [])]
                elif k in ("sea", "lake"):
                    parts += [g for g, p in self.geo.get("water", []) if (p.get("kind") == "sea") == (k == "sea")]
                elif k == "open":
                    taken = unary_union([g for g, p in self.geo.get("landcover", []) if p.get("kind") in ("wood", "residential", "cemetery", "scrub")]
                                        + [g for g, _ in self.geo.get("water", [])])
                    parts.append(self.map.frame.difference(taken))
                else:
                    parts += [g for g, p in self.geo.get("landcover", []) if p.get("kind") == k]
            u = unary_union(parts) if parts else None
            self._regions[key] = None if u is None or u.is_empty else u.intersection(self.map.frame)
        return self._regions[key]

    def mask(self, names, dist):
        if not names:
            return None
        key = json.dumps([names, dist])
        if key not in self._masks:
            parts = []
            for n in names:
                if n == "roads":
                    parts += [g.buffer(dist + .5) for g, _ in self.geo.get("roads", [])] + [g.buffer(dist + .2) for g, _ in self.geo.get("tracks", [])]
                elif n == "paths":
                    parts += [g.buffer(dist) for g, _ in self.geo.get("paths", [])]
                elif n == "buildings":
                    parts += [g.buffer(dist) for g, _ in self.geo.get("buildings", [])]
                elif n == "water":
                    parts += [g.buffer(dist) for g, _ in self.geo.get("water", [])] + [g.buffer(dist + .3) for g, _ in self.geo.get("waterways", [])]
                elif n == "decor":
                    parts += self.decor_mask()
                elif n == "landmarks":
                    parts += [Point(x, y).buffer(s * .7) for x, y, s in self.landmark_spots]
                else:
                    parts += [g.buffer(dist) for g, p in self.geo.get("landcover", []) if p.get("kind") == n]
            u = unary_union(parts) if parts else None
            if u is not None:
                shapely.prepare(u)
            self._masks[key] = u
        return self._masks[key]

    def use(self, sid, glyph, variant, gs, x, y, size, flip=False, rot=0):
        gid = f"{sid}-{glyph}-{variant}"
        if gid not in self._symbols:
            self._symbols.add(gid)
            self.defs.append(f'<g id="{gid}">{glyphs.GLYPHS[glyph](gs, variant)}</g>')
        t = f"translate({x:.2f},{y:.2f}) " + (f"rotate({rot:.0f}) " if rot else "") + f"scale({-size if flip else size:.2f},{size:.2f})"
        self.out.append(f'<use href="#{gid}" transform="{t}"/>')

    def scatter(self, layer):
        for i, sc in enumerate(self.st.get("scatter", [])):
            if sc.get("layer", "trees") != layer or sc.get("hide"):
                continue
            reg = self.region(sc.get("on", "frame"))
            if reg is None or reg.area < sc.get("min_area", 0):
                continue
            rng = seeded(self.seed, "sc", i)
            nrng = np.random.default_rng(rng.randrange(1 << 30))
            inset = sc.get("inset", 0)
            core = reg.buffer(-inset) if inset else reg
            if sc.get("band"):   # only a strip along the region's edge (reeds on a shore, trees along a forest edge)
                core = core.difference(reg.buffer(-sc["band"]))
            if core.is_empty:
                continue
            shapely.prepare(core)
            minx, miny, maxx, maxy = core.bounds
            if "count" in sc:
                n = sc["count"] if isinstance(sc["count"], int) else max(1, round(reg.area * sc["count"]))
                xs = nrng.uniform(minx, maxx, n * 60)
                ys = nrng.uniform(miny, maxy, n * 60)
            else:
                sp = sc.get("spacing", 2.5)
                gx, gy = np.meshgrid(np.arange(minx, maxx + sp, sp), np.arange(miny, maxy + sp, sp * .866))
                gx = gx + (np.arange(gx.shape[0]) % 2)[:, None] * sp / 2
                j = sc.get("jitter", .4) * sp
                xs = gx.ravel() + nrng.uniform(-j, j, gx.size)
                ys = gy.ravel() + nrng.uniform(-j, j, gy.size)
            keep = shapely.contains_xy(core, xs, ys)
            avoid = self.mask(sc.get("avoid"), sc.get("avoid_dist", .6))
            if avoid is not None:
                keep &= ~shapely.contains_xy(avoid, xs, ys)
            if sc.get("clump"):
                f = sc.get("clump_scale", .11)
                noise = (np.sin(xs * f + 1.7) + np.sin(ys * f * 1.3 + .4) + np.sin((xs + ys) * f * .7 + 2.9) + np.sin((xs - ys) * f * 1.9)) / 4
                keep &= noise > (sc["clump"] * 2 - 1) * .55
            if self.dem and ("elev" in sc or "slope" in sc):
                z, gx_, gy_ = self.dem.at_page(xs, ys)
                if "elev" in sc:
                    keep &= (z >= sc["elev"][0]) & (z <= sc["elev"][1])
                if "slope" in sc:
                    s = np.hypot(gx_, gy_)
                    keep &= (s >= sc["slope"][0]) & (s <= sc["slope"][1])
            pts = list(zip(xs[keep], ys[keep]))
            if "count" in sc:
                pts = pts[:n]
            if sc.get("max") and len(pts) > sc["max"]:
                pts = rng.sample(pts, sc["max"])
            fl = sc.get("flock")
            if fl:
                pts = [(x + rng.uniform(-1, 1) * fl.get("spread", 3), y + rng.uniform(-1, 1) * fl.get("spread", 3) * .6)
                       for x, y in pts for _ in range(rng.randint(*fl.get("n", [3, 6])))]
            pts.sort(key=lambda p: p[1])
            gl = sc["glyph"] if isinstance(sc["glyph"], list) else [sc["glyph"]]
            wts = sc.get("weights", [1] * len(gl))
            s0, s1 = sc["size"] if isinstance(sc["size"], list) else (sc["size"], sc["size"])
            self.out.append("<g " + attrs({"opacity": sc.get("opacity"), "filter": self.fx(sc.get("fx"))}) + ">")
            for x, y in pts:
                g = rng.choices(gl, wts)[0]
                self.use(f"s{i}", g, rng.randrange(glyphs.VARIANTS), sc.get("style", {}), x, y, rng.uniform(s0, s1),
                         flip=sc.get("flip", True) and rng.random() < .5, rot=rng.uniform(-1, 1) * sc.get("rot", 0))
            self.out.append("</g>")
            if pts and sc.get("legend"):
                self.present.add(sc["legend"])

    # ------------------------------------------------------------ UTM grid
    def grid(self):
        g = self.st.get("grid")
        if not g or g.get("hide"):
            return
        from pyproj import Transformer
        m = self.map
        zone = int((m.lon0 + 180) // 6) + 1
        epsg = (32600 if m.lat0 >= 0 else 32700) + zone
        to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        to_ll = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
        cl = m.lonlat(np.array([m.fx, m.fx + m.fw, m.fx + m.fw, m.fx]), np.array([m.fy, m.fy, m.fy + m.fh, m.fy + m.fh]))
        ux, uy = to_utm.transform(*cl)
        step = g.get("step", 1000)
        gx0, gx1 = math.floor(min(ux) / step) * step, math.ceil(max(ux) / step) * step
        gy0, gy1 = math.floor(min(uy) / step) * step, math.ceil(max(uy) / step) * step
        fs = g.get("edge_labels", {}).get("size", 2)
        d = []

        def run(fixed, vary, vertical):
            pts = [m.xy(*to_ll.transform(*((fixed, v) if vertical else (v, fixed)))) for v in vary]
            d.append("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts))
            for (xa, ya), (xb, yb) in zip(pts[:-1], pts[1:]):
                if vertical:
                    for edge, off in ((m.fy, -fs * .9), (m.fy + m.fh, fs * .9)):
                        if (ya - edge) * (yb - edge) <= 0 and ya != yb:
                            xe = xa + (edge - ya) / (yb - ya) * (xb - xa)
                            if m.fx + 3 < xe < m.fx + m.fw - 3:
                                self.grid_edge_labels.append((xe, edge + off, f"{fixed // 1000 % 1000:03d}", "middle"))
                else:
                    for edge, off, anc in ((m.fx, -1.2, "end"), (m.fx + m.fw, 1.2, "start")):
                        if (xa - edge) * (xb - edge) <= 0 and xa != xb:
                            ye = ya + (edge - xa) / (xb - xa) * (yb - ya)
                            if m.fy + 3 < ye < m.fy + m.fh - 3:
                                self.grid_edge_labels.append((edge + off, ye, f"{fixed // 1000 % 10000:04d}", anc))

        for X in range(gx0, gx1 + 1, step):
            run(X, np.linspace(gy0, gy1, 20), True)
        for Y in range(gy0, gy1 + 1, step):
            run(Y, np.linspace(gx0, gx1, 20), False)
        self.out.append(f'<path d="{" ".join(d)}" fill="none" stroke="{g["color"]}" stroke-width="{g["width"]}" {attrs({"stroke_opacity": g.get("opacity")})}/>')
        self.grid_zone = f"{zone}{'N' if m.lat0 >= 0 else 'S'}"
