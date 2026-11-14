"""Shared plumbing: theme loading, projection, DEM sampling, font metrics, i18n."""
import functools, json, math, os, random, subprocess, zlib
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parent.parent
ENV = dict(os.environ, FONTCONFIG_FILE=str(ROOT / "fonts.conf"))


# ------------------------------------------------------------------ themes
def deep_merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _raw_theme(name):
    st = json.loads((ROOT / "styles" / f"{name}.json").read_text())
    if "extends" in st:
        st = deep_merge(_raw_theme(st["extends"]), {k: v for k, v in st.items() if k != "extends"})
    return st


def _resolve(o, pal):
    """Replace "$name" strings with palette colours, anywhere in the theme."""
    if isinstance(o, dict):
        return {k: _resolve(v, pal) for k, v in o.items()}
    if isinstance(o, list):
        return [_resolve(v, pal) for v in o]
    if isinstance(o, str) and o.startswith("$"):
        seen = set()
        while isinstance(o, str) and o.startswith("$") and o not in seen:
            seen.add(o)
            if o[1:] not in pal:
                raise KeyError(f"theme uses {o} but palette has no '{o[1:]}'")
            o = pal[o[1:]]
    return o


def load_theme(name):
    st = _raw_theme(name)
    return _resolve(st, st.get("palette", {}))


# ------------------------------------------------------------------ i18n
@functools.lru_cache(maxsize=None)
def strings(lang):
    """Words the engine prints (legend, units, attribution …): i18n/<lang>.json, one file per language."""
    f = ROOT / "i18n" / f"{lang}.json"
    return json.loads(f.read_text()) if f.exists() else {}


def tr(key, lang, **kw):
    """Localise: `key` is an i18n key, a {"en":..,"ka":..} dict, or literal text. Falls back to English."""
    if isinstance(key, dict):
        s = key.get(lang) or key.get("en") or next(iter(key.values()))
    else:
        s = strings(lang).get(key) or strings("en").get(key) or key
    return s.format(**kw) if kw else s


# ------------------------------------------------------------------ fonts
@functools.lru_cache(maxsize=None)
def font_file(family, weight="normal", style="normal"):
    pat = family + (":bold" if str(weight) in ("bold", "600", "700", "800", "900") else "") + (":italic" if style == "italic" else "")
    try:
        return subprocess.run(["fc-match", "-f", "%{file}", pat], capture_output=True, text=True, env=ENV).stdout.strip()
    except Exception:
        return ""


@functools.lru_cache(maxsize=None)
def _pil_font(path):
    from PIL import ImageFont
    return ImageFont.truetype(path, 200)


@functools.lru_cache(maxsize=None)
def mtavruli_families():
    out = subprocess.run(["fc-list", ":charset=1c90", "family"], capture_output=True, text=True, env=ENV).stdout
    return {f.strip() for line in out.splitlines() for f in line.split(",")}


def text_width(s, family, size, weight="normal", style="normal", ls=0.0):
    """Width in the same units as `size`, measured with the real font file."""
    try:
        w = _pil_font(font_file(family, weight, style)).getlength(s) / 200 * size
    except Exception:
        w = len(s) * size * 0.56
    return w + len(s) * float(ls or 0)


# ------------------------------------------------------------------ geometry
def seeded(*parts):
    return random.Random(zlib.crc32("|".join(map(str, parts)).encode()))


class Map:
    """lon/lat → page millimetres inside the map frame (north up)."""

    def __init__(self, meta, frame):
        self.meta = meta
        self.lat0 = meta.get("center_lat", meta["lat"])
        self.lon0 = meta.get("center_lon", meta["lon"])
        self.tr = Transformer.from_crs(
            "EPSG:4326", f"+proj=tmerc +lat_0={self.lat0} +lon_0={self.lon0} +k=1 +x_0=0 +y_0=0 +ellps=WGS84", always_xy=True)
        self.fx, self.fy, self.fw, self.fh = frame
        self.scale = min(self.fw, self.fh) / (2 * meta["radius"])  # mm per metre
        self.half_w, self.half_h = self.fw / 2 / self.scale, self.fh / 2 / self.scale
        self.frame = box(self.fx, self.fy, self.fx + self.fw, self.fy + self.fh)
        self.clip = self.frame.buffer(3)

    def _fwd(self, pts):
        x, y = self.tr.transform(pts[:, 0], pts[:, 1])
        return np.column_stack([self.fx + self.fw / 2 + np.asarray(x) * self.scale,
                                self.fy + self.fh / 2 - np.asarray(y) * self.scale])

    def page(self, geom, clip=True):
        g = shapely.transform(geom, self._fwd)
        if not clip:
            return g
        if not g.is_valid:
            g = g.buffer(0) if g.geom_type in ("Polygon", "MultiPolygon") else g
        if not g.intersects(self.clip):
            return None
        g = g.intersection(self.clip)
        return None if g.is_empty else g

    def xy(self, lon, lat):
        p = self._fwd(np.array([[lon, lat]]))[0]
        return float(p[0]), float(p[1])

    def lonlat(self, x, y):
        mx = (np.asarray(x) - self.fx - self.fw / 2) / self.scale
        my = -(np.asarray(y) - self.fy - self.fh / 2) / self.scale
        return self.tr.transform(mx, my, direction="INVERSE")

    def inside(self, x, y, pad=0.0):
        return self.fx + pad < x < self.fx + self.fw - pad and self.fy + pad < y < self.fy + self.fh - pad


class Dem:
    """Elevation + slope lookups in page coordinates."""

    def __init__(self, d, m):
        from scipy.ndimage import gaussian_filter
        self.m = m
        self.raw = np.load(d / "dem.npy").astype(np.float64)
        info = json.loads((d / "dem.json").read_text())
        self.w, self.s, self.e, self.n = info["bounds"]
        self.h, self.wd = self.raw.shape
        self.z = gaussian_filter(self.raw, 1.5)
        lat = (self.s + self.n) / 2
        cx = (self.e - self.w) * 111_320 * math.cos(math.radians(lat)) / self.wd
        cy = (self.n - self.s) * 111_320 / self.h
        zs = gaussian_filter(self.raw, 3)
        d_row, d_col = np.gradient(zs, cy, cx)
        self.gx, self.gy = d_col, -d_row  # east, north slope (m/m)
        self.yn = math.asinh(math.tan(math.radians(self.n)))
        self.ys = math.asinh(math.tan(math.radians(self.s)))

    def rc(self, lon, lat):
        c = (np.asarray(lon) - self.w) / (self.e - self.w) * self.wd - 0.5
        ym = np.arcsinh(np.tan(np.radians(np.asarray(lat))))
        r = (ym - self.yn) / (self.ys - self.yn) * self.h - 0.5
        return (np.clip(np.rint(r), 0, self.h - 1).astype(int), np.clip(np.rint(c), 0, self.wd - 1).astype(int))

    def at_lonlat(self, lon, lat):
        r, c = self.rc(lon, lat)
        return self.z[r, c], self.gx[r, c], self.gy[r, c]

    def at_page(self, x, y):
        lon, lat = self.m.lonlat(x, y)
        return self.at_lonlat(lon, lat)

    def grid_page(self):
        """Page coordinates of every DEM cell (for peak finding / frame stats)."""
        lon = self.w + (np.arange(self.wd) + 0.5) / self.wd * (self.e - self.w)
        ym = self.yn + (np.arange(self.h) + 0.5) / self.h * (self.ys - self.yn)
        lat = np.degrees(np.arctan(np.sinh(ym)))
        LON, LAT = np.meshgrid(lon, lat)
        X, Y = self.m.tr.transform(LON, LAT)
        return self.m.fx + self.m.fw / 2 + X * self.m.scale, self.m.fy + self.m.fh / 2 - Y * self.m.scale


def load_layers(d, m):
    """{layer: [(page_geometry, props)]} clipped to the frame."""
    raw = json.loads((d / "layers.json").read_text())
    out = {}
    for name, fc in raw.items():
        items = []
        for f in fc["features"]:
            try:
                g = m.page(shape(f["geometry"]))
            except Exception:
                continue
            if g is not None:
                items.append((g, f["properties"]))
        out[name] = items
    return out


def hex_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def mix(a, b, t):
    ra, rb = hex_rgb(a), hex_rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))
