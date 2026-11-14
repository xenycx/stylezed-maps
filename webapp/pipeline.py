"""Getting a place's data: Nominatim lookup, OpenStreetMap layers from Overpass, elevation, first render.

Reuses the engine's own fetch.py / terrain.py so the public site draws exactly like the command line.
Both OSM services are free and shared: one request at a time, a real User-Agent, and never the same area twice.
"""
import json
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fetch as F  # noqa: E402

UA = {"User-Agent": os.environ.get("OSM_USER_AGENT") or "stylized-maps-site/1.0 (+https://github.com/xenycx/stylezed-maps)"}
F.UA = UA
SIZES = {"s": 800, "m": 1400, "l": 2200}   # half-width of the map in metres
OVERPASS_DEADLINE = int(os.environ.get("OVERPASS_DEADLINE", "1200"))  # seconds before "try again later"
_nominatim_lock = threading.Lock()
_nominatim_last = [0.0]


class PlaceError(Exception):
    pass


def nominatim(path, params):
    with _nominatim_lock:  # their policy: at most one request per second from the whole site
        wait = 1.1 - (time.time() - _nominatim_last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(f"https://nominatim.openstreetmap.org/{path}", params=params, headers=UA, timeout=20)
        finally:
            _nominatim_last[0] = time.time()
    r.raise_for_status()
    return r.json()


def lookup(osm_type, osm_id, lang):
    """The place the visitor picked, checked against OSM (never trust names sent by the browser)."""
    letter = {"node": "N", "way": "W", "relation": "R"}.get(osm_type)
    if not letter or not isinstance(osm_id, int) or osm_id <= 0:
        raise PlaceError("bad_place")
    res = nominatim("lookup", {"osm_ids": f"{letter}{osm_id}", "format": "jsonv2", "namedetails": 1,
                               "addressdetails": 1, "accept-language": "en"})
    if not res:
        raise PlaceError("not_found")
    g = res[0]
    nd = g.get("namedetails") or {}
    name = nd.get("name:en") or g.get("name") or nd.get("name") or g["display_name"].split(",")[0]
    local = nd.get(f"name:{lang}") or nd.get("name") or name
    return {"lat": float(g["lat"]), "lon": float(g["lon"]), "name": name[:120], "name_local": local[:120],
            "display_name": g.get("display_name", "")[:300],
            "country_code": (g.get("address") or {}).get("country_code", "")}


def slug_for(name):
    base = F.slugify(name)[:40].strip("-") or "place"
    return f"{base}-{os.urandom(3).hex()}"


def overpass(bbox):
    t_end = time.time() + OVERPASS_DEADLINE
    query = F.overpass_text(bbox)
    last, attempt = None, 0
    while time.time() < t_end:
        for url in F.OVERPASS:
            if time.time() >= t_end:
                break
            try:
                r = requests.post(url, data={"data": query}, headers=UA, timeout=min(180, max(10, t_end - time.time())))
                r.raise_for_status()
                return r.json()["elements"]
            except Exception as ex:  # noqa: BLE001
                last = ex
                print(f"overpass {url} failed: {ex}", file=sys.stderr)
        attempt += 1
        time.sleep(min(30, 5 * attempt))
    raise PlaceError(f"OpenStreetMap servers are busy ({last}). Try again in a few minutes.")


def fetch_place(slug, place):
    """data/<slug>/meta.json + layers.json, then elevation (terrain.py)."""
    d = ROOT / "data" / slug
    d.mkdir(parents=True, exist_ok=True)
    lat, lon, radius, lang = place["lat"], place["lon"], place["radius"], place["lang"]
    bbox = F.bbox_around(lat, lon, radius)
    fetch_bbox = F.bbox_around(lat, lon, radius * 1.25)
    els = overpass(fetch_bbox)
    if len(els) > 400_000:
        raise PlaceError("This area has too much map data to draw. Choose a smaller size.")
    layers = F.build_layers(els, lang, fetch_bbox)
    del els
    meta = {"query": place["name"], "display_name": place["display_name"], "lat": lat, "lon": lon,
            "center_lat": lat, "center_lon": lon, "landmarks": [], "radius": radius, "bbox": bbox,
            "fetch_bbox": fetch_bbox, "name": place["name"], "name_local": place["name_local"], "lang": lang}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    (d / "layers.json").write_text(json.dumps(
        {k: {"type": "FeatureCollection", "features": v} for k, v in layers.items()}, ensure_ascii=False))
    zoom = 14 if radius <= 1500 else 13
    proc = subprocess.run([sys.executable, "terrain.py", slug, "--zoom", str(zoom)], cwd=ROOT,
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise PlaceError("Elevation data could not be downloaded: " + (proc.stderr or proc.stdout)[-400:])


def render(slug, theme, lang, out_dir, custom=None, thumb=False, width=1600, timeout=300):
    cmd = [sys.executable, str(ROOT / "webapp" / "render_job.py"), slug, theme, lang, str(out_dir), "--width", str(width)]
    if custom:
        cmd += ["--custom", str(custom)]
    if thumb:
        cmd.append("--thumb")

    def limits():
        try:
            import resource
            gb = int(os.environ.get("RENDER_MEMORY_GB", "3"))
            resource.setrlimit(resource.RLIMIT_AS, (gb << 30, gb << 30))
            os.nice(5)
        except (ImportError, ValueError, OSError):
            pass

    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, preexec_fn=limits)
    if proc.returncode != 0:
        raise PlaceError("Drawing failed: " + (proc.stderr or proc.stdout)[-800:])


def metres(lat):
    return 111_320 * math.cos(math.radians(lat))
