"""Map studio — local web app for viewing the poster art and adding your own places, paths and notes.

usage: uv run studio.py [--port 8765] [--root DIR]

Serves web/ (the studio UI) plus read-only /out /data /icons /fonts, and a small JSON API:

  GET  /api/state                         places, themes, icon library, fonts
  GET  /api/render?slug=&theme=&lang=     sidecar of an existing render (+ "_studio")
  POST /api/render   {slug, theme, lang}  run poster.py, return the fresh sidecar, or {error, log} if it failed
  GET  /api/custom/<slug>                 data/<slug>/custom.json (empty shape if missing)
  PUT  /api/custom/<slug>                 validate + atomically write it (unknown keys preserved)
  POST /api/profile  {slug, coords}       elevation profile along a line, from dem.npy
  POST /api/elevation {slug, points}      elevation at single points

Python stdlib + numpy only. Binds 127.0.0.1.
"""
import argparse
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from email.utils import formatdate, parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np

ROOT = Path(__file__).resolve().parent

SLUG_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,80}")
THEME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}")
LANG_RE = re.compile(r"[a-z]{2,3}")
RENDER_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9_-]*)\.([a-z]{2,3})\.json")
STATIC_PREFIXES = ("web", "out", "data", "icons", "fonts")
MIME = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8", ".npy": "application/octet-stream",
}
MAX_BODY = 5 * 1024 * 1024
PATH_KINDS = ("trail", "road", "route")
RENDER_TIMEOUT = 600


class ApiError(Exception):
    def __init__(self, status, code, message=None, **extra):
        super().__init__(message or code)
        self.status, self.code, self.message, self.extra = status, code, message or code, extra


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check_slug(slug):
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug) or not (ROOT / "data" / slug / "meta.json").is_file():
        raise ApiError(404, "unknown_place", f"No place called {slug!r}.")
    return slug


# ---------------------------------------------------------------- fonts

def font_info(path):
    """Family / weight / style straight from the font's own name + OS/2 tables."""
    with open(path, "rb") as f:
        head = f.read(12)
        if len(head) < 12:
            return None
        tables = {}
        for _ in range(struct.unpack(">H", head[4:6])[0]):
            rec = f.read(16)
            if len(rec) < 16:
                return None
            tables[rec[:4]] = struct.unpack(">II", rec[8:16])
        if b"name" not in tables:
            return None
        off, length = tables[b"name"]
        f.seek(off)
        data = f.read(length)
        weight, italic = 400, False
        if b"OS/2" in tables:
            f.seek(tables[b"OS/2"][0])
            os2 = f.read(64)
            if len(os2) >= 64:
                weight = struct.unpack(">H", os2[4:6])[0]
                italic = bool(struct.unpack(">H", os2[62:64])[0] & 1)
    _, count, str_off = struct.unpack(">HHH", data[:6])
    names = {}
    for i in range(count):
        pid, _eid, lid, nid, ln, o = struct.unpack(">HHHHHH", data[6 + 12 * i:18 + 12 * i])
        raw = data[str_off + o:str_off + o + ln]
        if pid in (0, 3):
            text, prio = raw.decode("utf-16-be", "ignore"), (2 if lid == 0x409 else 1)
        elif pid == 1:
            text, prio = raw.decode("mac_roman", "ignore"), 0
        else:
            continue
        if text and (nid not in names or names[nid][0] < prio):
            names[nid] = (prio, text)
    family = (names.get(16) or names.get(1) or (0, None))[1]
    if not family:
        return None
    variable = "[wght]" in Path(path).name
    return {"family": family, "file": Path(path).name,
            "weight": "100 900" if variable else str(weight), "style": "italic" if italic else "normal"}


_fonts_cache = None


def list_fonts():
    global _fonts_cache
    d = ROOT / "fonts"
    if not d.is_dir():
        return []
    stamp = tuple(sorted((p.name, p.stat().st_mtime_ns) for p in d.iterdir() if p.suffix.lower() in (".ttf", ".otf")))
    if _fonts_cache and _fonts_cache[0] == stamp:
        return _fonts_cache[1]
    out = []
    for name, _ in stamp:
        try:
            info = font_info(d / name)
        except (OSError, struct.error):
            info = None
        if info:
            out.append(info)
    _fonts_cache = (stamp, out)
    return out


# ---------------------------------------------------------------- elevation

class Dem:
    def __init__(self, slug):
        d = ROOT / "data" / slug
        meta = read_json(d / "dem.json")
        if not meta or not (d / "dem.npy").is_file():
            raise ApiError(404, "no_dem", "This place has no elevation data.")
        self.grid = np.load(d / "dem.npy", mmap_mode="r")
        self.w, self.s, self.e, self.n = meta["bounds"]
        self.yn, self.ys = self.merc(self.n), self.merc(self.s)

    @staticmethod
    def merc(lat):
        return np.arcsinh(np.tan(np.radians(lat)))

    def sample(self, lon, lat):
        """Bilinear elevation. Columns are linear in longitude, rows linear in Web-Mercator y."""
        lon, lat = np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)
        h, w = self.grid.shape
        c = np.clip((lon - self.w) / (self.e - self.w) * w - 0.5, 0, w - 1)
        r = np.clip((self.yn - self.merc(lat)) / (self.yn - self.ys) * h - 0.5, 0, h - 1)
        c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
        c1, r1 = np.minimum(c0 + 1, w - 1), np.minimum(r0 + 1, h - 1)
        fc, fr = c - c0, r - r0
        g = self.grid
        top = g[r0, c0] * (1 - fc) + g[r0, c1] * fc
        bot = g[r1, c0] * (1 - fc) + g[r1, c1] * fc
        return np.asarray(top * (1 - fr) + bot * fr, dtype=np.float64)


_dems, _dem_lock = {}, threading.Lock()


def get_dem(slug):
    path = ROOT / "data" / slug / "dem.npy"
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        raise ApiError(404, "no_dem", "This place has no elevation data.")
    with _dem_lock:
        hit = _dems.get(slug)
        if not hit or hit[0] != stamp:
            hit = _dems[slug] = (stamp, Dem(slug))
        return hit[1]


def metres_per_degree(lat):
    """WGS84 metres per degree of (lon, lat) at a latitude — same figures the sidecar's m_per_deg uses."""
    a, e2 = 6378137.0, 0.00669437999014
    phi = math.radians(lat)
    s = 1 - e2 * math.sin(phi) ** 2
    return (math.pi / 180 * a / math.sqrt(s) * math.cos(phi), math.pi / 180 * a * (1 - e2) / s ** 1.5)


def parse_coords(raw, least=1, most=5000):
    if not isinstance(raw, list) or not (least <= len(raw) <= most):
        raise ApiError(400, "bad_coords", f"Expected between {least} and {most} [lon, lat] pairs.")
    out = []
    for c in raw:
        if not (isinstance(c, (list, tuple)) and len(c) >= 2 and is_num(c[0]) and is_num(c[1])
                and -180 <= c[0] <= 180 and -85 <= c[1] <= 85):
            raise ApiError(400, "bad_coords", "Each coordinate must be [lon, lat].")
        out.append((float(c[0]), float(c[1])))
    return out


def tobler_kmh(slope):
    """Tobler's hiking function: walking speed (km/h) for a slope dh/dx."""
    return 6.0 * np.exp(-3.5 * np.abs(slope + 0.05))


def profile(slug, coords, step=15.0, max_samples=2000):
    dem = get_dem(slug)
    pts = np.array(parse_coords(coords))
    if len(pts) == 1:
        ele = float(dem.sample(pts[0, 0], pts[0, 1]))
        return {"distance_m": 0.0, "step_m": 0.0, "d": [0.0], "ele": [round(ele, 1)], "vertex_d": [0.0],
                "ascent_m": 0.0, "descent_m": 0.0, "min_ele": round(ele, 1), "max_ele": round(ele, 1),
                "time_s": 0, "method": "tobler"}
    mx, my = metres_per_degree(float(pts[:, 1].mean()))
    xy = np.column_stack([pts[:, 0] * mx, pts[:, 1] * my])
    seg = np.hypot(*np.diff(xy, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cum[-1])
    if total <= 0:
        ele = float(dem.sample(pts[0, 0], pts[0, 1]))
        return {"distance_m": 0.0, "step_m": 0.0, "d": [0.0], "ele": [round(ele, 1)],
                "vertex_d": [0.0] * len(pts), "ascent_m": 0.0, "descent_m": 0.0,
                "min_ele": round(ele, 1), "max_ele": round(ele, 1), "time_s": 0, "method": "tobler"}
    n = max(1, min(max_samples, int(math.ceil(total / step))))
    d = np.linspace(0.0, total, n + 1)
    lon, lat = np.interp(d, cum, pts[:, 0]), np.interp(d, cum, pts[:, 1])
    ele = dem.sample(lon, lat)
    # A 7 m grid is noisy; smooth over ~5 samples before summing climbs so ripples don't count as ascent.
    k = min(5, len(ele) if len(ele) % 2 else len(ele) - 1)
    if k >= 3:
        pad = k // 2
        sm = np.convolve(np.pad(ele, pad, mode="edge"), np.ones(k) / k, mode="valid")
    else:
        sm = ele
    dh, dd = np.diff(sm), np.diff(d)
    hours = float(np.sum((dd / 1000.0) / tobler_kmh(dh / dd)))
    return {
        "distance_m": round(total, 1), "step_m": round(total / n, 2),
        "d": [round(float(v), 1) for v in d], "ele": [round(float(v), 1) for v in sm],
        "vertex_d": [round(float(v), 1) for v in cum],
        "ascent_m": round(float(dh[dh > 0].sum()), 1), "descent_m": round(float(-dh[dh < 0].sum()), 1),
        "min_ele": round(float(sm.min()), 1), "max_ele": round(float(sm.max()), 1),
        "time_s": int(round(hours * 3600)), "method": "tobler",
    }


def elevations(slug, points):
    dem = get_dem(slug)
    pts = np.array(parse_coords(points))
    return {"elevations": [round(float(v), 1) for v in dem.sample(pts[:, 0], pts[:, 1])]}


# ---------------------------------------------------------------- state

FONT_FILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._\[\],()+-]{0,120}\.(ttf|otf|ttc)", re.I)
MAX_FONT = 25 * 1024 * 1024


def fc_env():
    return dict(os.environ, FONTCONFIG_FILE=str(ROOT / "fonts.conf"))


def font_families(lang=None):
    """[{family, project}] fontconfig can see; with lang only fonts covering that language. Project fonts first."""
    try:
        out = subprocess.run(["fc-list", f":lang={lang}" if lang else ":", "family", "file"],
                             capture_output=True, text=True, env=fc_env(), timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    seen = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        file, fam = line.split(":", 1)
        fam = fam.strip().split(",")[0].strip()
        if fam:
            seen[fam] = seen.get(fam, False) or str(ROOT / "fonts") in file
    return [{"family": f, "project": mine} for f, mine in sorted(seen.items(), key=lambda t: (not t[1], t[0].lower()))]


def theme_font_roles(theme, lang):
    """{role: family} the theme itself uses for this language (follows "extends")."""
    st, seen = {}, set()
    name = theme
    chain = []
    while name and name not in seen and THEME_RE.fullmatch(name):
        seen.add(name)
        raw = read_json(ROOT / "styles" / f"{name}.json")
        if not isinstance(raw, dict):
            break
        chain.append(raw)
        name = raw.get("extends")
    for raw in reversed(chain):
        st.update(raw.get("fonts") or {})
    out = {}
    for role, spec in st.items():
        if not isinstance(spec, dict):
            continue
        v = spec.get(lang) or (spec.get("local") if lang != "en" else None) or spec.get("en", "Noto Sans")
        out[role] = v.get("font") if isinstance(v, dict) else v
    return out


def font_prefs_path(slug):
    return ROOT / "data" / slug / "fonts.json"


def fonts_state(slug, theme, lang):
    prefs = read_json(font_prefs_path(slug))
    prefs = prefs if isinstance(prefs, dict) else {}
    per = prefs.get(lang) if isinstance(prefs.get(lang), dict) else {}
    chosen = dict(per.get("*") or {}, **(per.get(theme) or {}))
    roles = [{"id": r, "theme_font": fam, "font": chosen.get(r, fam), "custom": r in chosen}
             for r, fam in theme_font_roles(theme, lang).items()]
    return {"roles": roles, "families": font_families(lang)}


def set_font(slug, theme, lang, role, family):
    """family=None clears the choice for that role (back to the theme's own font)."""
    if not isinstance(role, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", role):
        raise ApiError(400, "bad_request", "Unknown text role.")
    if family is not None and (not isinstance(family, str) or family not in {f["family"] for f in font_families()}):
        raise ApiError(400, "unknown_font", "That font is not installed. Add the font file first.")
    with slug_lock(slug):
        path = font_prefs_path(slug)
        prefs = read_json(path)
        prefs = prefs if isinstance(prefs, dict) else {}
        per = prefs.setdefault(lang, {})
        for key in (theme, "*"):
            if isinstance(per.get(key), dict):
                per[key].pop(role, None)
        if family is not None:
            per.setdefault(theme, {})[role] = family
        prefs = {l: {t: r for t, r in ts.items() if r} for l, ts in prefs.items() if isinstance(ts, dict)}
        prefs = {l: ts for l, ts in prefs.items() if ts}
        if prefs:
            atomic_write(path, json.dumps(prefs, ensure_ascii=False, indent=1))
        elif path.exists():
            path.unlink()
    return fonts_state(slug, theme, lang)


def save_font_file(name, data):
    name = os.path.basename(name or "")
    if not FONT_FILE_RE.fullmatch(name):
        raise ApiError(400, "bad_font_name", "Font files must be .ttf, .otf or .ttc with a plain file name.")
    if not data or len(data) > MAX_FONT:
        raise ApiError(400, "bad_font_size", "The font file is empty or larger than 25 MB.")
    if data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf"):
        raise ApiError(400, "not_a_font", "This file is not a TrueType or OpenType font.")
    (ROOT / "fonts").mkdir(exist_ok=True)
    target = ROOT / "fonts" / name
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    try:
        out = subprocess.run(["fc-scan", "-f", "%{family}\n", str(target)], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    fams = sorted({l.split(",")[0].strip() for l in out.splitlines() if l.strip()})
    if not fams:
        target.unlink(missing_ok=True)
        raise ApiError(400, "not_a_font", "This file could not be read as a font.")
    return {"file": name, "families": fams}


PAPER_RE = re.compile(r"[A-Za-z0-9]{2,8}|\d{2,4}(\.\d)?[xX]\d{2,4}(\.\d)?")


def pdf_file(slug, theme, lang, paper):
    """Path of the PDF for a render, (re)made when missing or older than the render. paper '' = poster size."""
    from atlas.export import make_pdf, pdf_name
    svg = ROOT / "out" / slug / f"{theme}.{lang}.svg"
    if not svg.is_file():
        raise ApiError(404, "not_rendered", "This theme has not been rendered in this language yet.")
    out = svg.with_name(pdf_name(f"{theme}.{lang}", paper or None))
    with slug_lock(slug):
        if not out.is_file() or out.stat().st_mtime < svg.stat().st_mtime:
            try:
                make_pdf(svg, out, paper or None, fontconfig=ROOT / "fonts.conf")
            except ValueError as e:
                raise ApiError(400, "bad_paper", str(e))
            except (OSError, subprocess.SubprocessError) as e:
                raise ApiError(500, "pdf_failed", f"The PDF could not be made: {e}")
    return out


def list_renders(slug):
    out_dir = ROOT / "out" / slug
    renders = []
    if out_dir.is_dir():
        for p in sorted(out_dir.iterdir()):
            m = RENDER_RE.fullmatch(p.name)
            if not m or not p.is_file():
                continue
            side = read_json(p)
            if not isinstance(side, dict) or not (out_dir / str(side.get("image", ""))).is_file():
                continue
            renders.append({"id": f"{m[1]}.{m[2]}", "theme": m[1], "lang": m[2], "mtime": p.stat().st_mtime})
    return renders


def list_themes():
    themes = []
    d = ROOT / "styles"
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            if p.stem.startswith("_") or p.stem.startswith("debug"):
                continue
            st = read_json(p)
            if not isinstance(st, dict):
                continue
            item = {"id": p.stem, "name": st.get("name") or p.stem, "description": st.get("description") or ""}
            for k in ("name_local", "description_local", "name_ka", "description_ka"):
                if isinstance(st.get(k), str):
                    item[k] = st[k]
            themes.append(item)
    return themes


def list_library():
    d = ROOT / "icons" / "library"
    if not d.is_dir():
        return []
    have = {p.stem for p in d.glob("*.svg")}
    index = read_json(d / "index.json")
    out, seen = [], set()
    if isinstance(index, list):
        for it in index:
            if isinstance(it, dict) and isinstance(it.get("id"), str) and it["id"] in have and it["id"] not in seen:
                seen.add(it["id"])
                out.append({**it, "label": it.get("label") or it["id"]})
    for stem in sorted(have - seen):  # drawn but not indexed yet
        out.append({"id": stem, "label": stem.replace("-", " ").replace("_", " ").capitalize()})
    return out


def place_state(d):
    meta = read_json(d / "meta.json")
    if not isinstance(meta, dict):
        return None
    slug = d.name
    lang = meta.get("lang") if isinstance(meta.get("lang"), str) and LANG_RE.fullmatch(meta["lang"]) else "en"
    place = {"slug": slug, "name": meta.get("name") or slug, "name_local": meta.get("name_local"),
             "lang": lang, "renders": list_renders(slug), "landmarks": None,
             "landmark_icons": sorted(p.stem for p in (d / "icons").glob("*.svg")) if (d / "icons").is_dir() else [],
             "has_dem": (d / "dem.npy").is_file() and (d / "dem.json").is_file()}
    lm = read_json(d / "landmarks.json")
    if isinstance(lm, dict) and isinstance(lm.get("landmarks"), list):
        items = [x for x in lm["landmarks"] if isinstance(x, dict) and isinstance(x.get("id"), str)]
        if place["has_dem"]:
            pts = [(i, x) for i, x in enumerate(items) if is_num(x.get("lon")) and is_num(x.get("lat"))]
            try:
                els = elevations(slug, [[x["lon"], x["lat"]] for _, x in pts])["elevations"] if pts else []
                for (i, _), e in zip(pts, els):
                    items[i] = {**items[i], "ele": e}
            except (ApiError, OSError, ValueError, KeyError):
                pass
        place["landmarks"] = items
    return place


def api_state():
    places = []
    data = ROOT / "data"
    if data.is_dir():
        for d in sorted(data.iterdir()):
            if d.is_dir() and SLUG_RE.fullmatch(d.name) and (d / "meta.json").is_file():
                p = place_state(d)
                if p:
                    places.append(p)
    return {"places": places, "themes": list_themes(), "icons": {"library": list_library()},
            "fonts": list_fonts(),
            "languages": sorted({"en"} | {p.get("lang") or "en" for p in places})}


# ---------------------------------------------------------------- custom.json

_custom_locks, _locks_lock = {}, threading.Lock()


def slug_lock(slug):
    with _locks_lock:
        return _custom_locks.setdefault(slug, threading.Lock())


def load_custom(slug):
    doc = read_json(ROOT / "data" / slug / "custom.json")
    if not isinstance(doc, dict):
        doc = {}
    for k in ("places", "paths", "notes"):
        if not isinstance(doc.get(k), list):
            doc[k] = []
    return doc


def validate_custom(doc):
    if not isinstance(doc, dict):
        raise ApiError(400, "bad_custom", "custom.json must be an object.")

    def fail(msg):
        raise ApiError(400, "bad_custom", msg)

    def ids(kind, items):
        seen = set()
        for it in items:
            if not isinstance(it, dict):
                fail(f"Every entry in {kind} must be an object.")
            if not isinstance(it.get("id"), str) or not it["id"] or len(it["id"]) > 64:
                fail(f"Every entry in {kind} needs a short string id.")
            if it["id"] in seen:
                fail(f"Duplicate id {it['id']!r} in {kind}.")
            seen.add(it["id"])

    def lonlat(kind, it):
        if not (is_num(it.get("lon")) and is_num(it.get("lat")) and -180 <= it["lon"] <= 180 and -85 <= it["lat"] <= 85):
            fail(f"{kind} {it['id']!r} needs a valid lon and lat.")

    for k in ("places", "paths", "notes"):
        if not isinstance(doc.get(k, []), list):
            fail(f"{k} must be a list.")
        doc.setdefault(k, [])
        if len(doc[k]) > 2000:
            fail(f"Too many {k}.")
        ids(k, doc[k])
    for p in doc["places"]:
        lonlat("Place", p)
        if not isinstance(p.get("name"), str) or len(p["name"]) > 200:
            fail(f"Place {p['id']!r} needs a name (a string up to 200 characters).")
        if not isinstance(p.get("note", ""), str) or len(p.get("note", "")) > 1000:
            fail(f"Place {p['id']!r}: note must be a string up to 1000 characters.")
        icon = p.get("icon")
        if icon is not None and not (isinstance(icon, str) and re.fullmatch(r"(library|landmark)/[A-Za-z0-9_.-]{1,80}", icon)):
            fail(f"Place {p['id']!r}: icon must be \"library/<id>\" or \"landmark/<file-stem>\".")
    for r in doc["paths"]:
        if not isinstance(r.get("name"), str) or len(r["name"]) > 200:
            fail(f"Path {r['id']!r} needs a name (a string up to 200 characters).")
        if r.get("kind") not in PATH_KINDS:
            fail(f"Path {r['id']!r}: kind must be one of {', '.join(PATH_KINDS)}.")
        try:
            parse_coords(r.get("coords"), least=2)
        except ApiError:
            fail(f"Path {r['id']!r} needs at least two [lon, lat] coordinates.")
    for n in doc["notes"]:
        lonlat("Note", n)
        if not isinstance(n.get("text"), str) or len(n["text"]) > 1000:
            fail(f"Note {n['id']!r} needs text (a string up to 1000 characters).")
    return doc


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_custom(slug, doc):
    doc = validate_custom(doc)
    path = ROOT / "data" / slug / "custom.json"
    with slug_lock(slug):
        old = read_json(path)
        if isinstance(old, dict):  # keep top-level keys this client never saw
            for k, v in old.items():
                doc.setdefault(k, v)
        atomic_write(path, json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        return {"ok": True, "mtime": path.stat().st_mtime,
                "counts": {k: len(doc[k]) for k in ("places", "paths", "notes")}}


# ---------------------------------------------------------------- render

class Job:
    def __init__(self):
        self.done, self.result = threading.Event(), None


_jobs, _jobs_lock = {}, threading.Lock()


def baked_path(slug, theme, lang):
    return ROOT / "out" / slug / ".studio" / f"{theme}.{lang}.json"


def sidecar_with_studio(slug, theme, lang):
    path = ROOT / "out" / slug / f"{theme}.{lang}.json"
    side = read_json(path)
    if not isinstance(side, dict):
        return None
    mtime = path.stat().st_mtime
    rec = read_json(baked_path(slug, theme, lang))
    baked = None
    # Only trust our record if it describes exactly this render (not one made later from the command line).
    if isinstance(side.get("baked"), dict):
        baked = side["baked"]            # the renderer itself records what it drew (works for command-line renders too)
    elif isinstance(rec, dict) and rec.get("sidecar_mtime_ns") == path.stat().st_mtime_ns:
        baked = rec.get("custom")
    side["_studio"] = {"mtime": mtime, "baked": baked}
    return side


def tail(text, lines=40, chars=6000):
    text = (text or "").replace("\r\n", "\n").strip("\n")
    return "\n".join(text.split("\n")[-lines:])[-chars:]


def do_render(slug, theme, lang):
    with slug_lock(slug):
        custom = load_custom(slug)
    snapshot = {k: custom[k] for k in ("places", "paths", "notes")}
    runner = ["uv", "run"] if shutil.which("uv") else [sys.executable]
    cmd = runner + ["poster.py", slug, "--style", theme, "--lang", lang]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=RENDER_TIMEOUT,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as e:
        err = e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return 200, {"error": "render_timeout", "log": tail(err) or f"No output after {RENDER_TIMEOUT} s.",
                     "command": " ".join(cmd)}
    except OSError as e:
        return 200, {"error": "render_failed", "log": f"Could not start the renderer: {e}", "command": " ".join(cmd)}
    if proc.returncode != 0:
        return 200, {"error": "render_failed", "code": proc.returncode, "command": " ".join(cmd),
                     "log": tail(proc.stderr) or tail(proc.stdout) or f"Renderer exited with code {proc.returncode}."}
    path = ROOT / "out" / slug / f"{theme}.{lang}.json"
    side = read_json(path)
    if not isinstance(side, dict) or path.stat().st_mtime < t0 - 2:
        return 200, {"error": "render_failed", "command": " ".join(cmd),
                     "log": tail(proc.stderr) or tail(proc.stdout) or
                     f"The renderer finished but did not write out/{slug}/{theme}.{lang}.json."}
    try:
        atomic_write(baked_path(slug, theme, lang),
                     json.dumps({"sidecar_mtime_ns": path.stat().st_mtime_ns, "custom": snapshot}, ensure_ascii=False))
    except OSError:
        pass
    side = sidecar_with_studio(slug, theme, lang)
    side["_studio"]["seconds"] = round(time.time() - t0, 1)
    return 200, side


def render(slug, theme, lang):
    check_slug(slug)
    if not isinstance(theme, str) or not THEME_RE.fullmatch(theme) or not (ROOT / "styles" / f"{theme}.json").is_file():
        raise ApiError(404, "unknown_theme", f"No theme called {theme!r}.")
    if not isinstance(lang, str) or not LANG_RE.fullmatch(lang):
        raise ApiError(400, "bad_lang", "lang must be a language code such as en or ka.")
    key = (slug, theme, lang)
    with _jobs_lock:
        job = _jobs.get(key)
        owner = job is None
        if owner:
            job = _jobs[key] = Job()
    if not owner:  # the same render is already running: wait for it and share its answer
        job.done.wait()
        return job.result
    try:
        job.result = do_render(slug, theme, lang)
    except Exception as e:  # noqa: BLE001 — never leave waiters hanging
        job.result = (200, {"error": "render_failed", "log": f"{type(e).__name__}: {e}"})
    finally:
        with _jobs_lock:
            _jobs.pop(key, None)
        job.done.set()
    return job.result


# ---------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    server_version = "MapStudio/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("STUDIO_QUIET"):
            return
        sys.stderr.write("%s  %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # -- helpers
    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            raise ApiError(400, "bad_json", "A JSON body is required.")
        if length > MAX_BODY:
            self.close_connection = True
            raise ApiError(413, "too_large", "Request body is too large.")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "bad_json", "The request body is not valid JSON.")

    def guarded(self, fn):
        try:
            fn()
        except ApiError as e:
            self.send_json({"error": e.code, "message": e.message, **e.extra}, e.status)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"error: {type(e).__name__}: {e}\n")
            try:
                self.send_json({"error": "server_error", "message": f"{type(e).__name__}: {e}"}, 500)
            except OSError:
                self.close_connection = True

    # -- static
    def serve_static(self, url_path):
        try:
            rel = unquote(url_path, errors="strict")
        except UnicodeDecodeError:
            raise ApiError(400, "bad_path")
        if rel in ("/", "/index.html"):
            rel = "/web/index.html"
        parts = [p for p in rel.split("/") if p]
        if (not parts or parts[0] not in STATIC_PREFIXES or "\\" in rel or "\x00" in rel
                or any(p in (".", "..") or p.startswith(".") for p in parts)):
            raise ApiError(404, "not_found", "Not found.")
        base = (ROOT / parts[0]).resolve()
        target = (ROOT / Path(*parts)).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            raise ApiError(404, "not_found", "Not found.")
        st = target.stat()
        ims = self.headers.get("If-Modified-Since")
        if ims:
            try:
                if int(st.st_mtime) <= parsedate_to_datetime(ims).timestamp():
                    self.send_response(304)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            except (TypeError, ValueError, OverflowError):
                pass
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(target.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(st.st_size))
        self.send_header("Last-Modified", formatdate(st.st_mtime, usegmt=True))
        self.send_header("Cache-Control", "public, max-age=86400" if parts[0] == "fonts" else "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            with open(target, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 256 * 1024)

    # -- routes
    def route_get(self):
        url = urlparse(self.path)
        path = url.path
        if path == "/api/state":
            return self.send_json(api_state())
        if path == "/api/render":
            q = parse_qs(url.query)
            slug, theme, lang = (q.get(k, [""])[0] for k in ("slug", "theme", "lang"))
            check_slug(slug)
            if not THEME_RE.fullmatch(theme) or not LANG_RE.fullmatch(lang):
                raise ApiError(400, "bad_request", "slug, theme and lang are required.")
            side = sidecar_with_studio(slug, theme, lang)
            if side is None:
                raise ApiError(404, "not_rendered", "This theme has not been rendered in this language yet.")
            return self.send_json(side)
        m = re.fullmatch(r"/api/custom/([^/]+)", path)
        if m:
            slug = check_slug(m[1])
            with slug_lock(slug):
                return self.send_json(load_custom(slug))
        if path == "/api/pdf":
            q = parse_qs(url.query)
            slug, theme, lang, paper = (q.get(k, [""])[0] for k in ("slug", "theme", "lang", "paper"))
            check_slug(slug)
            if not THEME_RE.fullmatch(theme) or not LANG_RE.fullmatch(lang) or (paper and not PAPER_RE.fullmatch(paper)):
                raise ApiError(400, "bad_request", "slug, theme and lang are required; paper is e.g. A4 or 210x297.")
            out = pdf_file(slug, theme, lang, paper)
            data = out.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'attachment; filename="{slug}-{out.name}"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
            return
        if path == "/api/fonts":
            q = parse_qs(url.query)
            slug, theme, lang = (q.get(k, [""])[0] for k in ("slug", "theme", "lang"))
            check_slug(slug)
            if not THEME_RE.fullmatch(theme) or not LANG_RE.fullmatch(lang):
                raise ApiError(400, "bad_request", "slug, theme and lang are required.")
            return self.send_json(fonts_state(slug, theme, lang))
        if path.startswith("/api/"):
            raise ApiError(404, "not_found", "No such endpoint.")
        self.serve_static(path)

    def route_write(self):
        path = urlparse(self.path).path
        m = re.fullmatch(r"/api/custom/([^/]+)", path)
        if m and self.command in ("PUT", "POST"):
            slug = check_slug(m[1])
            return self.send_json(save_custom(slug, self.read_body()))
        if self.command == "POST" and path == "/api/fonts/upload":
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_FONT:
                raise ApiError(400, "bad_font_size", "The font file is empty or larger than 25 MB.")
            from urllib.parse import unquote
            return self.send_json(save_font_file(unquote(self.headers.get("X-Filename", "")), self.rfile.read(length)))
        if self.command in ("PUT", "POST") and path == "/api/fonts":
            body = self.read_body()
            if not isinstance(body, dict):
                raise ApiError(400, "bad_json", "Expected a JSON object.")
            slug, theme, lang = check_slug(body.get("slug")), body.get("theme"), body.get("lang")
            if not isinstance(theme, str) or not THEME_RE.fullmatch(theme) or not isinstance(lang, str) or not LANG_RE.fullmatch(lang):
                raise ApiError(400, "bad_request", "slug, theme and lang are required.")
            return self.send_json(set_font(slug, theme, lang, body.get("role"), body.get("family")))
        if self.command == "POST" and path in ("/api/render", "/api/profile", "/api/elevation"):
            body = self.read_body()
            if not isinstance(body, dict):
                raise ApiError(400, "bad_json", "Expected a JSON object.")
            if path == "/api/render":
                status, payload = render(body.get("slug"), body.get("theme"), body.get("lang"))
                return self.send_json(payload, status)
            slug = check_slug(body.get("slug"))
            if path == "/api/profile":
                return self.send_json(profile(slug, body.get("coords")))
            return self.send_json(elevations(slug, body.get("points")))
        raise ApiError(404 if path.startswith("/api/") else 405, "not_found", "No such endpoint.")

    def do_GET(self):
        self.guarded(self.route_get)

    do_HEAD = do_GET

    def do_POST(self):
        self.guarded(self.route_write)

    do_PUT = do_POST


def main():
    global ROOT
    ap = argparse.ArgumentParser(description="Map studio server")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--root", default=None, help="project root (default: the folder this file is in)")
    a = ap.parse_args()
    if a.root:
        ROOT = Path(a.root).resolve()
    ThreadingHTTPServer.daemon_threads = True
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    except OSError as e:
        sys.exit(f"Could not listen on 127.0.0.1:{a.port} — {e.strerror or e}. Is the studio already running?")
    print(f"Map studio: http://127.0.0.1:{a.port}/   (root: {ROOT})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
