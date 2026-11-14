"""Keyless elevation: AWS Terrarium tiles -> DEM -> contours GeoJSON + hillshade PNG.

usage: uv run terrain.py nikortsminda [--zoom 14] [--interval 10]
Outputs in data/<slug>/: dem.npy, dem.json (bounds), contours.json, hillshade.png
"""
import argparse, io, json, math
from pathlib import Path
import numpy as np
import requests
from PIL import Image
from skimage import measure

TILE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
UA = {"User-Agent": "stylized-map-maker/0.1 (personal project)"}


def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def tile_to_lonlat(x, y, z):
    n = 2 ** z
    lon = x / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


def fetch_dem(bbox, z):
    s, w, n, e = bbox
    x0, y0 = lonlat_to_tile(w, n, z)
    x1, y1 = lonlat_to_tile(e, s, z)
    tx0, ty0, tx1, ty1 = int(x0), int(y0), int(x1), int(y1)
    rows = []
    for ty in range(ty0, ty1 + 1):
        row = []
        for tx in range(tx0, tx1 + 1):
            r = requests.get(TILE.format(z=z, x=tx, y=ty), headers=UA, timeout=30)
            r.raise_for_status()
            a = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"), dtype=np.float64)
            row.append(a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768)
        rows.append(np.hstack(row))
    dem = np.vstack(rows)
    # crop to bbox in pixel space
    px0, py0 = int((x0 - tx0) * 256), int((y0 - ty0) * 256)
    px1, py1 = int(math.ceil((x1 - tx0) * 256)), int(math.ceil((y1 - ty0) * 256))
    dem = fill_holes(dem[py0:py1, px0:px1])
    # exact lon/lat bounds of the cropped grid (pixel edges)
    west, north = tile_to_lonlat(tx0 + px0 / 256, ty0 + py0 / 256, z)
    east, south = tile_to_lonlat(tx0 + px1 / 256, ty0 + py1 / 256, z)
    return dem, (west, south, east, north)


def fill_holes(dem):
    """Terrarium has occasional nodata spikes (e.g. -3000 m); replace with neighbour means."""
    med = np.median(dem)
    bad = (dem < med - 1500) | (dem > med + 3000)
    while bad.any():
        p = np.pad(np.where(bad, 0, dem), 1, mode="edge")
        w = np.pad((~bad).astype(float), 1, mode="edge")
        acc = sum(p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        cnt = sum(w[1 + dy:w.shape[0] - 1 + dy, 1 + dx:w.shape[1] - 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        fill = bad & (cnt > 0)
        dem = np.where(fill, acc / np.maximum(cnt, 1), dem)
        bad &= ~fill
    return dem


def smooth(a, k=2):
    """Cheap box blur so contours from 9 m data don't zig-zag."""
    for _ in range(k):
        p = np.pad(a, 1, mode="edge")
        a = sum(p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx]
                for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9
    return a


def pix_to_lonlat(r, c, shape, bounds, z):
    """Pixel (row, col) -> lon/lat; rows are linear in mercator y."""
    w, s, e, n = bounds
    lon = w + (c + 0.5) / shape[1] * (e - w)
    ymerc_n = math.asinh(math.tan(math.radians(n)))
    ymerc_s = math.asinh(math.tan(math.radians(s)))
    ym = ymerc_n + (r + 0.5) / shape[0] * (ymerc_s - ymerc_n)
    return lon, math.degrees(math.atan(math.sinh(ym)))


def contours(dem, bounds, interval, z):
    sm = smooth(dem, 3)
    feats = []
    lo = math.ceil(sm.min() / interval) * interval
    for lvl in np.arange(lo, sm.max(), interval):
        for line in measure.find_contours(sm, lvl):
            if len(line) < 8:
                continue
            coords = [list(pix_to_lonlat(r, c, sm.shape, bounds, z)) for r, c in line[::2]]
            feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
                          "properties": {"ele": int(lvl), "index": int(lvl) % (interval * 5) == 0}})
    return {"type": "FeatureCollection", "features": feats}


def hillshade(dem, bounds, az=315, alt=45, zfactor=1.3):
    w, s, e, n = bounds
    lat = (s + n) / 2
    cell_x = (e - w) * 111_320 * math.cos(math.radians(lat)) / dem.shape[1]
    cell_y = (n - s) * 111_320 / dem.shape[0]
    d = smooth(dem, 1) * zfactor
    gy, gx = np.gradient(d, cell_y, cell_x)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    azr, altr = math.radians(360 - az + 90), math.radians(alt)
    hs = np.sin(altr) * np.cos(slope) + np.cos(altr) * np.sin(slope) * np.cos(azr - aspect)
    return np.clip(hs, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--zoom", type=int, default=14)
    ap.add_argument("--interval", type=int, default=10)
    a = ap.parse_args()
    d = Path("data") / a.slug
    meta = json.loads((d / "meta.json").read_text())
    dem, bounds = fetch_dem(meta["fetch_bbox"], a.zoom)
    np.save(d / "dem.npy", dem.astype(np.float32))
    (d / "dem.json").write_text(json.dumps({"bounds": bounds, "zoom": a.zoom, "shape": dem.shape,
                                            "min": float(dem.min()), "max": float(dem.max())}))
    (d / "contours.json").write_text(json.dumps(contours(dem, bounds, a.interval, a.zoom)))
    hs = hillshade(dem, bounds)
    Image.fromarray((hs * 255).astype(np.uint8), "L").save(d / "hillshade.png")
    print(f"DEM {dem.shape} {dem.min():.0f}–{dem.max():.0f} m, bounds {bounds}")


if __name__ == "__main__":
    main()
