"""Place name -> geocode -> bbox -> Overpass -> normalized GeoJSON layers.

usage: uv run fetch.py "Nikortsminda, Georgia" [--radius 1500] [--slug nikortsminda]
"""
import argparse, json, math, re, sys, time
from pathlib import Path
import requests

UA = {"User-Agent": "stylized-map-maker/0.1 (personal project)"}
OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.private.coffee/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def geocode(q, lang="en", same_as=None):
    """Best Nominatim match for a place name.

    A name often matches both a settlement (a `place` node in the middle of the houses) and its municipality
    (a boundary whose centroid can be kilometres away, up a mountain). Prefer the settlement.
    `same_as` = (osm_type, osm_id) of an earlier pick, to get the same object in another language."""
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": q, "format": "jsonv2", "limit": 6,
                             "accept-language": lang, "namedetails": 1},
                     headers=UA, timeout=30)
    r.raise_for_status()
    res = r.json()
    if not res:
        sys.exit(f"place not found: {q}")
    if same_as:
        return next((x for x in res if (x.get("osm_type"), x.get("osm_id")) == same_as), res[0])
    best = next((x for x in res if x.get("category") == "place"), res[0])
    if len(res) > 1:
        print("  matches (the one marked > is used; pass --pick N or --at LAT,LON to choose another):")
        for i, x in enumerate(res):
            print(f'  {">" if x is best else " "} {i} {x.get("category")}/{x.get("type"):14s} {float(x["lat"]):.4f},{float(x["lon"]):.4f}  {x["display_name"][:70]}')
    return best, res


def bbox_around(lat, lon, radius_m):
    dlat = radius_m / 111_320
    dlon = radius_m / (111_320 * math.cos(math.radians(lat)))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)  # s,w,n,e


def overpass_query(q):
    for attempt in range(3):
        for url in OVERPASS:
            try:
                r = requests.post(url, data={"data": q}, headers=UA, timeout=180)
                r.raise_for_status()
                return r.json()["elements"]
            except Exception as ex:
                print(f"overpass {url} failed: {ex}", file=sys.stderr)
                time.sleep(3 + 5 * attempt)
    sys.exit("all overpass endpoints failed")


LEAN_HIGHWAYS = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|road|pedestrian|track|path|bridleway"
LEAN_AMENITY = ("place_of_worship|school|university|college|kindergarten|library|theatre|cinema|arts_centre|hospital|clinic|"
                "townhall|public_bath|marketplace|fountain|drinking_water|grave_yard|monastery")


def overpass_text(bbox, lean=False):
    """The Overpass query for everything the engine draws inside bbox (s, w, n, e).

    lean=True is for city-sized maps (several km across): buildings come as a centre point + tags instead of an
    outline, footways / service lanes / steps are left out, and only notable kinds of points are fetched. That keeps
    a 9 km city to a few tens of MB instead of hundreds."""
    s, w, n, e = bbox
    b = f"({s},{w},{n},{e})"
    if lean:
        return f"""[out:json][timeout:240];
way["building"]{b};
out tags bb;
(
  way["highway"~"^({LEAN_HIGHWAYS})$"]{b};
  way["waterway"]{b};
  way["natural"]{b}; relation["natural"]{b};
  node["natural"~"beach|bay|cape"]{b};
  way["landuse"]{b}; relation["landuse"]{b};
  way["leisure"]{b};
  way["amenity"~"^({LEAN_AMENITY})$"]{b};
  way["historic"]{b};
  way["railway"]{b};
  node["place"]{b};
  node["natural"~"peak|spring|cave_entrance|saddle"]{b};
  node["amenity"~"^({LEAN_AMENITY})$"]{b}; node["historic"]{b};
  node["tourism"~"museum|attraction|viewpoint|gallery|artwork"]{b};
  node["man_made"~"tower|lighthouse|bridge|water_well"]{b};
);
out body geom;"""
    q = f"""[out:json][timeout:120];
(
  way["building"]{b};
  way["highway"]{b};
  way["waterway"]{b};
  way["natural"]{b}; relation["natural"]{b};
  node["natural"~"beach|bay|cape"]{b};
  way["landuse"]{b}; relation["landuse"]{b};
  way["leisure"]{b};
  way["amenity"]{b};
  way["historic"]{b};
  way["railway"]{b};
  node["place"]{b};
  node["natural"~"peak|spring|cave_entrance|saddle|tree"]{b};
  node["amenity"]{b}; node["historic"]{b}; node["tourism"]{b};
  node["man_made"]{b};
);
out body geom;"""
    return q


def overpass(bbox):
    return overpass_query(overpass_text(bbox))


def landmarks(lat, lon, search_m):
    """Named sights near the place (caves, springs, peaks, churches, villages...)."""
    s, w, n, e = bbox_around(lat, lon, search_m)
    b = f"({s},{w},{n},{e})"
    q = f"""[out:json][timeout:60];
(
  nwr["tourism"~"attraction|viewpoint|museum"]["name"]{b};
  nwr["natural"~"spring|cave_entrance|peak|waterfall|volcano"]["name"]{b};
  nwr["historic"]["name"]{b};
  nwr["amenity"="place_of_worship"]["name"]{b};
  node["place"~"village|hamlet|town"]{b};
);
out center tags;"""
    out = []
    for el in overpass_query(q):
        c = el.get("center") or el
        if "lat" not in c:
            continue
        t = el.get("tags", {})
        dx = (c["lon"] - lon) * 111_320 * math.cos(math.radians(lat))
        dy = (c["lat"] - lat) * 111_320
        out.append({"name": t.get("name:en") or t.get("name"), "lat": c["lat"], "lon": c["lon"],
                    "is_place": "place" in t,
                    "dx": dx, "dy": dy, "dist": math.hypot(dx, dy)})
    return sorted(out, key=lambda x: x["dist"])


def fit_extent(lat, lon, lms, min_r, pad=1.15):
    """Center + radius so the place and all landmarks fit with padding."""
    xs = [0] + [l["dx"] for l in lms]
    ys = [0] + [l["dy"] for l in lms]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    r = max(min_r, (max(xs) - min(xs)) / 2 * pad + 150, (max(ys) - min(ys)) / 2 * pad + 150)
    clat = lat + cy / 111_320
    clon = lon + cx / (111_320 * math.cos(math.radians(lat)))
    return clat, clon, r


def classify(tags):
    """Return (layer, kind) for an OSM tag set, or None to skip."""
    if "building" in tags:
        return "buildings", tags.get("building")
    if "highway" in tags:
        h = tags["highway"]
        if h in ("motorway", "trunk", "primary", "secondary"):
            return "roads", "major"
        if h in ("tertiary", "unclassified", "residential", "living_street", "service", "road"):
            return "roads", "minor"
        if h in ("track",):
            return "tracks", "track"
        if h in ("path", "footway", "steps", "bridleway", "cycleway", "pedestrian"):
            return "paths", h
        return None
    if "waterway" in tags:
        return "waterways", tags["waterway"]
    nat = tags.get("natural")
    if nat == "water" or tags.get("landuse") in ("reservoir", "basin"):
        return "water", "water"
    if nat in ("wood", "scrub", "heath", "grassland", "bare_rock", "scree", "cliff"):
        return "landcover", nat
    lu = tags.get("landuse")
    if lu == "forest":
        return "landcover", "wood"
    if lu in ("farmland", "meadow", "orchard", "vineyard", "grass", "allotments",
              "residential", "cemetery", "farmyard", "religious"):
        return "landcover", lu
    if tags.get("amenity") == "grave_yard":
        return "landcover", "cemetery"
    return None


POI_KEYS = ("amenity", "historic", "tourism", "man_made", "natural")


def ring_closed(c):
    return len(c) >= 4 and c[0] == c[-1]


def way_geom(el):
    return [[p["lon"], p["lat"]] for p in el.get("geometry", []) if p]


def sea_polygons(coast_ways, bbox):
    """OSM has no sea polygons, only `natural=coastline` lines with land on their LEFT.
    Cut the bbox with the coastlines and keep the pieces that lie on the right-hand side."""
    from shapely.geometry import LineString, Point, box
    from shapely.ops import linemerge, polygonize, unary_union
    s, w, n, e = bbox
    frame = box(w, s, e, n)
    merged = linemerge([LineString(c) for c in coast_ways if len(c) >= 2])
    coast = merged.intersection(frame)
    if coast.is_empty:
        return []
    parts = [g for g in getattr(coast, "geoms", [coast]) if g.geom_type == "LineString" and len(g.coords) >= 2]
    faces = list(polygonize(unary_union([frame.boundary] + parts)))
    sea = []
    for f in faces:
        votes = 0
        for ln in parts:
            if ln.distance(f) > 1e-9:
                continue
            for t in (0.25, 0.5, 0.75):
                a, b = ln.interpolate(t - 0.01, normalized=True), ln.interpolate(t + 0.01, normalized=True)
                dx, dy = b.x - a.x, b.y - a.y
                d = math.hypot(dx, dy) or 1
                mid = ln.interpolate(t, normalized=True)
                right = Point(mid.x + dy / d * 1e-5, mid.y - dx / d * 1e-5)   # a step to the right of travel = sea
                left = Point(mid.x - dy / d * 1e-5, mid.y + dx / d * 1e-5)
                votes += f.contains(right) - f.contains(left)
        if votes > 0:
            sea.append([list(map(list, f.exterior.coords))] + [list(map(list, i.coords)) for i in f.interiors])
    return sea


def build_layers(elements, lang="en", fetch_bbox=None):
    layers = {k: [] for k in ("buildings", "roads", "tracks", "paths", "waterways",
                              "water", "landcover", "pois", "places")}
    coast = []
    for el in elements:
        tags = el.get("tags", {})
        props = {"id": f'{el["type"][0]}{el["id"]}',
                 "name": tags.get("name:en") or tags.get("name"),
                 "name_local": tags.get(f"name:{lang}") or tags.get("name"),
                 **{k: tags[k] for k in ("highway", "waterway", "building", "amenity", "historic",
                                         "tourism", "natural", "landuse", "place", "ele",
                                         "religion", "man_made", "intermittent", "wikidata", "wikipedia",
                                         "start_date", "description", "leaf_type", "building:levels") if k in tags}}
        if el["type"] == "node":
            if "place" in tags:
                layers["places"].append(feat("Point", [el["lon"], el["lat"]], props))
            elif any(k in tags for k in POI_KEYS):
                props["kind"] = next(tags[k] for k in POI_KEYS if k in tags)
                layers["pois"].append(feat("Point", [el["lon"], el["lat"]], props))
            continue
        if el["type"] == "way" and tags.get("natural") == "coastline":
            coast.append(way_geom(el))
            continue
        cls = classify(tags)
        if el["type"] == "way":
            coords = way_geom(el)
            if len(coords) < 2 and el.get("bounds") and cls and cls[0] == "buildings":
                # lean download: a building is only its bounding box; it stands in for the footprint (size matters:
                # the engine draws big ones as apartment blocks)
                bb = el["bounds"]
                w0, s0, e0, n0 = bb["minlon"], bb["minlat"], bb["maxlon"], bb["maxlat"]
                coords = [[w0, s0], [e0, s0], [e0, n0], [w0, n0], [w0, s0]]
            if len(coords) < 2:
                continue
            # area-ish ways that are also POIs (e.g. a church building) -> add a POI point too
            if any(k in tags for k in ("amenity", "historic", "tourism")) and tags.get("name"):
                cx = sum(c[0] for c in coords) / len(coords)
                cy = sum(c[1] for c in coords) / len(coords)
                p = dict(props, kind=next(tags[k] for k in ("historic", "amenity", "tourism") if k in tags))
                layers["pois"].append(feat("Point", [cx, cy], p))
            if not cls:
                continue
            layer, kind = cls
            props["kind"] = kind
            area = layer in ("buildings", "water", "landcover")
            if area and ring_closed(coords):
                layers[layer].append(feat("Polygon", [coords], props))
            elif not area:
                layers[layer].append(feat("LineString", coords, props))
        elif el["type"] == "relation" and cls:
            layer, kind = cls
            if layer not in ("water", "landcover"):
                continue
            props["kind"] = kind
            outers = [way_geom(m) for m in el.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
            inners = [way_geom(m) for m in el.get("members", []) if m.get("role") == "inner" and m.get("geometry")]
            outers = stitch(outers)
            inners = stitch(inners)
            for o in outers:
                layers[layer].append(feat("Polygon", [o] + inners, props))
    if coast and fetch_bbox:
        for rings in sea_polygons(coast, fetch_bbox):
            layers["water"].append(feat("Polygon", rings, {"id": "sea", "kind": "sea", "name": None, "name_local": None}))
    return layers


def stitch(segs):
    """Join open way segments of a multipolygon into closed rings."""
    segs = [s[:] for s in segs if len(s) >= 2]
    rings = []
    while segs:
        cur = segs.pop(0)
        changed = True
        while not ring_closed(cur) and changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == cur[-1]:
                    cur += s[1:]
                elif s[-1] == cur[-1]:
                    cur += s[::-1][1:]
                elif s[-1] == cur[0]:
                    cur = s[:-1] + cur
                elif s[0] == cur[0]:
                    cur = s[::-1][:-1] + cur
                else:
                    continue
                segs.pop(i)
                changed = True
                break
        if ring_closed(cur):
            rings.append(cur)
    return rings


def feat(t, coords, props):
    return {"type": "Feature", "geometry": {"type": t, "coordinates": coords}, "properties": props}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("place")
    ap.add_argument("--radius", type=float, default=1500, help="half-width of the area in metres")
    ap.add_argument("--slug")
    ap.add_argument("--lang", default="en", help="map language: en, or the local language code (ka, fr, ...)")
    ap.add_argument("--pick", type=int, help="use match number N from the list of geocoding matches")
    ap.add_argument("--at", help="LAT,LON — centre the map here instead of on the geocoded point")
    ap.add_argument("--refresh", action="store_true", help="ignore the cached Overpass response")
    ap.add_argument("--fit", type=float, default=0, metavar="SEARCH_M",
                    help="find named landmarks within SEARCH_M and widen/shift the frame to include them")
    a = ap.parse_args()
    g, matches = geocode(a.place)
    if a.pick is not None:
        g = matches[a.pick]
    lat, lon = float(g["lat"]), float(g["lon"])
    if a.at:
        lat, lon = (float(v) for v in a.at.split(","))
    slug = a.slug or slugify(a.place.split(",")[0])
    out = Path("data") / slug
    out.mkdir(parents=True, exist_ok=True)
    print(f"{g['display_name']}  @ {lat:.5f},{lon:.5f}")
    clat, clon, radius = lat, lon, a.radius
    lms = []
    if a.fit:
        # fit to sights inside the search circle; other villages are shown if they land in frame
        lms = [l for l in landmarks(lat, lon, a.fit) if l["name"] and l["dist"] <= a.fit]
        for l in lms:
            print(f"  landmark {'(village) ' if l['is_place'] else ''}{l['name'][:40]:40s} {l['dist']:5.0f} m")
        clat, clon, radius = fit_extent(lat, lon, [l for l in lms if not l["is_place"]], a.radius)
        print(f"  fitted: center offset {(clon-lon)*111320*math.cos(math.radians(lat)):.0f},{(clat-lat)*111320:.0f} m, radius {radius:.0f} m")
    bbox = bbox_around(clat, clon, radius)
    # fetch a margin so lines run off the frame instead of stopping at it
    fetch_bbox = bbox_around(clat, clon, radius * 1.25)
    raw = out / "overpass_raw.json"   # cache: Overpass is often overloaded, never fetch the same area twice
    cached = json.loads(raw.read_text()) if raw.exists() and not a.refresh else None
    if cached and cached.get("bbox") == list(fetch_bbox):
        els = cached["elements"]
        print("  using cached Overpass response (--refresh to refetch)")
    else:
        els = overpass(fetch_bbox)
        raw.write_text(json.dumps({"bbox": list(fetch_bbox), "elements": els}, ensure_ascii=False))
    layers = build_layers(els, a.lang, fetch_bbox)
    nd = g.get("namedetails") or {}
    meta = {"query": a.place, "display_name": g["display_name"], "lat": lat, "lon": lon,
            "center_lat": clat, "center_lon": clon, "landmarks": lms,
            "radius": radius, "bbox": bbox, "fetch_bbox": fetch_bbox,
            "name": nd.get("name:en") or g.get("name"), "name_local": nd.get("name"), "lang": a.lang}
    if a.lang != "en":
        time.sleep(1.1)  # Nominatim: max 1 request/second
        meta["display_name_local"] = geocode(a.place, a.lang, same_as=(g.get("osm_type"), g.get("osm_id")))["display_name"]
        meta["name_local"] = nd.get(f"name:{a.lang}") or meta["name_local"]
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    (out / "layers.json").write_text(json.dumps(
        {k: {"type": "FeatureCollection", "features": v} for k, v in layers.items()}, ensure_ascii=False))
    for k, v in layers.items():
        print(f"  {k:10s} {len(v)}")


if __name__ == "__main__":
    main()
