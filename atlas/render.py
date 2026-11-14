"""Assemble a poster: `uv run poster.py <slug> --style <theme> --lang <en|ka>`."""
import argparse, json, subprocess, sys
from pathlib import Path

import numpy as np

from .annot import Annot
from .core import ENV, ROOT, Dem, Map, load_layers, load_theme
from .decor import Decor
from .layers import LINE_TOKENS, Layers, attrs

DEFAULT_ORDER = ["landcover", "hillshade", "contours", "hachures", "water", "waterways", "ground", "tracks", "paths", "roads",
                 "bridges", "buildings", "trees", "grid", "peaks"]


class Poster(Layers, Annot, Decor):
    def __init__(self, slug, theme_id, lang=None, png_width=3000, fonts=None, custom_path=None):
        self.slug, self.theme_id = slug, theme_id
        self.st = st = load_theme(theme_id)
        self.d_ = ROOT / "data" / slug
        # the additions to bake in: data/<slug>/custom.json unless another file is given (the public site keeps one per user)
        self.custom_path = Path(custom_path) if custom_path else self.d_ / "custom.json"
        self.meta = json.loads((self.d_ / "meta.json").read_text())
        self.lang = lang or self.meta.get("lang", "en")
        self.seed = st.get("seed", 7)
        # font overrides: data/<slug>/fonts.json  {lang: {"*": {role: family}, "<theme>": {role: family}}}, then --font
        self.font_over, self.fonts_used = {}, {}
        ff = self.d_ / "fonts.json"
        if ff.exists():
            try:
                per_lang = json.loads(ff.read_text()).get(self.lang, {})
                self.font_over.update(per_lang.get("*", {}))
                self.font_over.update(per_lang.get(theme_id, {}))
            except Exception:
                pass
        self.font_over.update(fonts or {})
        pg = st["page"]
        self.W, self.H = pg["width"], pg["height"]
        self.vars = {"W": self.W, "H": self.H, "m": pg.get("margin", 10), "min": min, "max": max}
        fr = [self.ev(v) for v in pg.get("frame", ["m", "m", "W - 2*m", "H - 2*m"])]
        self.map = m = Map(self.meta, fr)
        self.vars.update(fx=m.fx, fy=m.fy, fw=m.fw, fh=m.fh, fr=m.fx + m.fw, fb=m.fy + m.fh, cx=self.W / 2, mx=m.fx + m.fw / 2, my=m.fy + m.fh / 2)
        self.k = png_width / self.W
        self.png_width = png_width
        self.L, self.R, self.D = st.get("layers", {}), st.get("relief", {}), st.get("decorations", {})
        self.order = st.get("order", DEFAULT_ORDER)
        self.geo = load_layers(self.d_, m)
        self._trim_waterways()
        self.dem = Dem(self.d_, m) if (self.d_ / "dem.npy").exists() else None
        self.title_name = (self.meta.get("name") if self.lang == "en" else self.meta.get("name_local")) or self.meta.get("name") or slug
        self.defs, self.css, self.out = [], [], []
        self.occupied, self.present = [], set()
        self._regions, self._masks, self._symbols, self._icons = {}, {}, set(), {}
        self._casings_done, self._uid, self._filters = False, 0, set()
        self.grid_edge_labels, self.deferred_spots, self.landmark_hits, self.lm_plan, self.landmark_spots = [], [], [], [], []
        self.frame_elev = (0, 0)
        if self.dem:
            X, Y = self.dem.grid_page()
            ins = (X > m.fx) & (X < m.fx + m.fw) & (Y > m.fy) & (Y < m.fy + m.fh)
            if ins.any():
                self.frame_elev = (max(0.0, float(self.dem.raw[ins].min())) if any(p.get("kind") == "sea" for _, p in self.geo.get("water", []))
                                   else float(self.dem.raw[ins].min()), float(self.dem.raw[ins].max()))

    def _trim_waterways(self):
        """Rivers are mapped as centre lines that run straight through lakes and out to sea: cut those parts away."""
        from shapely.ops import unary_union
        water = [g for g, _ in self.geo.get("water", [])]
        if not water or not self.geo.get("waterways"):
            return
        lake = unary_union(water).buffer(0.15)
        kept = []
        for g, p in self.geo["waterways"]:
            if g.intersects(lake):
                g = g.difference(lake)
            if not g.is_empty:
                kept.append((g, p))
        self.geo["waterways"] = kept

    def uid(self, p):
        self._uid += 1
        return f"{p}{self._uid}"

    def filter_def(self, name, region=None):
        """Emit <filter> `name` (from the theme's "filters") for a region in mm; returns its id."""
        r = region or (0, 0, self.W, self.H)
        fid = f"fx-{name}" if region is None else f"fx-{name}-" + "-".join(str(round(v)) for v in r)
        if fid in self._filters:
            return fid
        self._filters.add(fid)
        f = dict({"blur": {"type": "blur", "std": .5}}, **self.st.get("filters", {})).get(name)
        if f is None:
            raise SystemExit(f"theme '{self.theme_id}': filter '{name}' is not defined in \"filters\"")
        reg = f'filterUnits="userSpaceOnUse" x="{r[0]:.1f}" y="{r[1]:.1f}" width="{r[2] - r[0]:.1f}" height="{r[3] - r[1]:.1f}"'
        if f.get("type", "rough") == "blur":
            body = f'<feGaussianBlur stdDeviation="{f.get("std", .5)}"/>'
        else:
            body = (f'<feTurbulence type="fractalNoise" baseFrequency="{f.get("freq", .35)}" numOctaves="{f.get("octaves", 2)}" seed="{f.get("seed", 3)}" result="n"/>'
                    f'<feDisplacementMap in="SourceGraphic" in2="n" scale="{f.get("scale", 1)}" xChannelSelector="R" yChannelSelector="G"'
                    + (' result="d"/>' + f'<feGaussianBlur in="d" stdDeviation="{f["blur"]}"/>' if f.get("blur") else "/>"))
        self.defs.append(f'<filter id="{fid}" {reg} color-interpolation-filters="sRGB">{body}</filter>')
        return fid

    def filters(self):
        for name in dict({"blur": 1}, **self.st.get("filters", {})):
            self.filter_def(name)

    # ------------------------------------------------------------ assemble
    def render(self):
        st, m, pg = self.st, self.map, self.st["page"]
        self.filters()
        self.defs.append(f'<clipPath id="mapclip"><rect x="{m.fx}" y="{m.fy}" width="{m.fw}" height="{m.fh}"/></clipPath>')
        self.reserve()
        self.plan_landmarks()
        self.plan_custom()
        o = self.out
        o.append(f'<rect width="{self.W}" height="{self.H}" fill="{pg["bg"]}"/>')
        self.panels()
        self.ornaments()
        o.append('<g clip-path="url(#mapclip)">')
        o.append(f'<rect x="{m.fx}" y="{m.fy}" width="{m.fw}" height="{m.fh}" fill="{pg.get("map_bg", pg["bg"])}"/>')
        steps = {"landcover": self.landcover, "hillshade": self.hillshade, "contours": self.contours, "hachures": self.hachures,
                 "water": self.water, "waterways": self.waterways, "bridges": self.bridges, "buildings": self.buildings,
                 "grid": self.grid, "peaks": self.peaks, "ground": lambda: self.scatter("ground"), "trees": lambda: self.scatter("trees")}
        for tok in self.order:
            if tok in LINE_TOKENS:
                self.ways(tok)
            elif tok in steps:
                steps[tok]()
            else:
                raise SystemExit(f"theme '{self.theme_id}': unknown order token '{tok}'")
        self.custom()
        self.symbols()
        self.draw_landmarks()
        self.places()
        self.landmark_labels()
        self.symbol_text()
        self.water_labels()
        self.spots()
        self.scatter("sky")
        self.texture(pg.get("map_texture"), m.fx, m.fy, m.fw, m.fh, "maptex")
        o.append("</g>")
        self.frame()
        self.title()
        self.compass()
        self.scalebar()
        self.legend()
        self.index()
        self.texts()
        self.texture(pg.get("texture"), 0, 0, self.W, self.H, "pagetex")
        style = f'<style>{"".join(self.css)}</style>' if self.css else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{self.W}mm" height="{self.H}mm" '
                f'viewBox="0 0 {self.W} {self.H}"><defs>{style}{"".join(self.defs)}</defs>{"".join(self.out)}</svg>')

    # ------------------------------------------------------------ outputs
    def sidecar(self, base):
        m, st, k = self.map, self.st, self.k
        ex, _ = m.tr.transform(m.lon0 + 0.01, m.lat0)
        _, ny = m.tr.transform(m.lon0, m.lat0 + 0.01)
        cu, lm = st.get("custom", {}), st.get("landmarks", {})
        pr = cu.get("path", {"stroke": "#c0392b", "width": .7, "dash": "1.6 1"})
        lab = self.font(cu.get("label", st["labels"]["poi"]))
        note = self.font(cu.get("note", cu.get("label", st["labels"]["poi"])))
        return {"slug": self.slug, "theme": self.theme_id, "theme_name": st.get("name", self.theme_id), "lang": self.lang,
                "image": f"{base}.jpg", "print": f"{base}.png", "svg": f"{base}.svg",
                "page_mm": [self.W, self.H], "px": [self.png_width, round(self.H * k)], "frame_px": [m.fx * k, m.fy * k, m.fw * k, m.fh * k],
                "center": [m.lon0, m.lat0], "m_per_px": 1 / (m.scale * k), "m_per_deg": [ex / 0.01, ny / 0.01],
                "place": {"name": self.meta.get("name"), "name_local": self.meta.get("name_local")},
                "overlay": {
                    "path": {"stroke": pr.get("stroke", "#c0392b"), "width_px": round(pr.get("width", .7) * k, 1),
                             "dash": [round(float(v) * k, 1) for v in str(pr.get("dash", "")).split()] or None,
                             "casing": ({"stroke": pr["casing"]["color"], "width_px": round(pr["casing"]["width"] * k, 1)} if pr.get("casing") else None)},
                    "place": {"color": lm.get("ink", "#1d1d1d"), "paper": lm.get("paper", "#ffffff"), "tone": lm.get("tone", "#cccccc"),
                              "shade": lm.get("shade", "#666666"), "accent": lm.get("accent", "#d7261e"), "halo": lm.get("halo"),
                              "font": lab["family"], "label_color": lab.get("color", "#1d1d1d"), "label_halo": lab.get("halo"),
                              "size_px": round(cu.get("place_size", 8) * k, 1), "font_px": round(lab["size"] * k, 1),
                              "font_weight": lab.get("weight", "normal"), "font_style": lab.get("style", "normal")},
                    "note": {"color": note.get("color", "#1d1d1d"), "font": note["family"], "font_px": round(note["size"] * k, 1), "halo": note.get("halo"),
                             "font_weight": note.get("weight", "normal"), "font_style": note.get("style", "normal")}},
                "baked": getattr(self, "custom_doc", {"places": [], "paths": [], "notes": []}),
                "fonts": self.fonts_used,
                "landmarks": self.landmark_hits}

    def save(self):
        out = ROOT / "out" / self.slug
        out.mkdir(parents=True, exist_ok=True)
        base = f"{self.theme_id}.{self.lang}"
        svg = self.render()
        (out / f"{base}.svg").write_text(svg)
        subprocess.run(["rsvg-convert", "-w", str(self.png_width), "-o", str(out / f"{base}.png"), str(out / f"{base}.svg")], check=True, env=ENV)
        subprocess.run(["magick", str(out / f"{base}.png"), "-quality", "88", str(out / f"{base}.jpg")], check=True)
        (out / f"{base}.json").write_text(json.dumps(self.sidecar(base), ensure_ascii=False, indent=1))
        return out / f"{base}.png"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render a stylized poster map.")
    ap.add_argument("slug")
    ap.add_argument("--style", default="hiking")
    ap.add_argument("--lang", default=None, help="en or the local language code; default: meta.json 'lang'")
    ap.add_argument("--png-width", type=int, default=3000)
    ap.add_argument("--font", action="append", default=[], metavar="ROLE=FAMILY",
                    help='use your own font for a theme font role, this render only, e.g. --font display="BPG Nino Mtavruli" '
                         "(repeatable; `uv run fonts.py` lists roles and fonts and saves a choice permanently)")
    ap.add_argument("--pdf", nargs="?", const="poster", metavar="PAPER",
                    help="also write a vector PDF: at the poster's own size, or fitted to A4, A3, A2, letter … or WIDTHxHEIGHT (mm)")
    ap.add_argument("--pdf-only", action="store_true", help="make the PDF from the existing render without drawing the map again")
    a = ap.parse_args(argv)
    fonts = dict(f.split("=", 1) for f in a.font if "=" in f)
    if a.pdf_only:
        lang = a.lang or json.loads((ROOT / "data" / a.slug / "meta.json").read_text()).get("lang", "en")
    else:
        poster = Poster(a.slug, a.style, a.lang, a.png_width, fonts)
        print(poster.save())
        lang = poster.lang
    if a.pdf or a.pdf_only:
        from .export import make_pdf, pdf_name
        paper = None if (a.pdf or "poster") == "poster" else a.pdf
        base = ROOT / "out" / a.slug / f"{a.style}.{lang}"
        svg = base.with_name(base.name + ".svg")
        if not svg.exists():
            raise SystemExit(f"{svg.name} has not been rendered yet — run without --pdf-only first.")
        out = base.with_name(pdf_name(base.name, paper))
        try:
            w, h = make_pdf(svg, out, paper, fontconfig=ROOT / "fonts.conf")
        except ValueError as e:
            raise SystemExit(str(e))
        print(f"{out}  ({w:g} × {h:g} mm)")


if __name__ == "__main__":
    main()
