"""Landmarks for a place the site fetched by itself: pick the notable OpenStreetMap points (churches, fortresses,
schools, caves, springs …) and give each one an icon from the shared set in icons/auto/ — the icons first drawn for
Nikortsminda plus a few from the library. Hand-made landmark sets (data/<slug>/landmarks.json without "auto")
are never touched.

usage: python webapp/landmarks_auto.py <slug> [<slug> …]      (also called by the site after every new place)
"""
import json
import math
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "icons" / "auto"
VERSION = 6            # bump when the picking rules change: the site rebuilds older automatic sets at startup
MAX_LANDMARKS = 14
MAX_PER_KIND = 3
MIN_GAP = 0.06        # landmarks at least this share of the frame width apart (a city centre is full of them)
MAX_HEROES = 2         # rank 1 = the largest icons; more than two and the map loses its focus
LABEL_CHARS = 24       # longer names stay in the index only; the map shows the icon
HERO_LABEL_CHARS = 40  # …except the two largest, whose label may wrap onto two lines

# OSM kind -> (icon, rank, English, Georgian, named only?)
KINDS = {
    "place_of_worship": ("church", 1, "Church", "ეკლესია", False),
    "monastery": ("monastery", 1, "Monastery", "მონასტერი", False),
    "cathedral": ("monastery", 1, "Cathedral", "ტაძარი", False),
    "castle": ("fortress", 1, "Fortress", "ციხე", False),
    "fort": ("fortress", 1, "Fortress", "ციხე", False),
    "ruins": ("fortress", 2, "Ruins", "ნანგრევები", False),
    "archaeological_site": ("fortress", 2, "Archaeological site", "არქეოლოგიური ძეგლი", True),
    "cave_entrance": ("cave", 1, "Cave", "მღვიმე", False),
    "waterfall": ("waterfall", 1, "Waterfall", "ჩანჩქერი", False),
    "spring": ("spring", 1, "Spring", "წყარო", True),
    "museum": ("museum", 1, "Museum", "მუზეუმი", True),
    "arts_centre": ("gallery", 2, "Arts centre", "ხელოვნების ცენტრი", True),
    "gallery": ("gallery", 2, "Gallery", "გალერეა", True),
    "theatre": ("theatre", 2, "Theatre", "თეატრი", True),
    "cinema": ("cinema", 3, "Cinema", "კინოთეატრი", True),
    "public_bath": ("bath", 2, "Baths", "აბანო", True),
    "townhall": ("townhall", 2, "Town hall", "მერია", True),
    "mosque": ("mosque", 1, "Mosque", "მეჩეთი", False),
    "synagogue": ("synagogue", 1, "Synagogue", "სინაგოგა", False),
    "bridge": ("bridge", 2, "Bridge", "ხიდი", True),
    "peak": ("peak", 2, "Peak", "მწვერვალი", True),
    "viewpoint": ("viewpoint", 2, "Viewpoint", "გადასახედი", False),
    "attraction": ("sight", 2, "Sight", "ღირსშესანიშნაობა", True),
    "memorial": ("memorial", 3, "Memorial", "მემორიალი", True),
    "monument": ("monument", 2, "Monument", "ძეგლი", True),
    "wayside_shrine": ("memorial", 3, "Shrine", "სალოცავი", True),
    "school": ("school", 3, "School", "სკოლა", False),
    "college": ("university", 3, "College", "კოლეჯი", True),
    "university": ("university", 2, "University", "უნივერსიტეტი", True),
    "kindergarten": ("kindergarten", 3, "Kindergarten", "საბავშვო ბაღი", False),
    "library": ("library", 3, "Library", "ბიბლიოთეკა", False),
    "hospital": ("clinic", 3, "Hospital", "საავადმყოფო", False),
    "clinic": ("clinic", 3, "Clinic", "ამბულატორია", False),
    "doctors": ("clinic", 3, "Doctor", "ექიმი", True),
    "cafe": ("cafe", 3, "Café", "კაფე", True),
    "restaurant": ("restaurant", 3, "Restaurant", "რესტორანი", True),
    "guest_house": ("guest-house", 3, "Guest house", "საოჯახო სასტუმრო", True),
    "hotel": ("guest-house", 3, "Hotel", "სასტუმრო", True),
    "hostel": ("guest-house", 3, "Hostel", "ჰოსტელი", True),
    "communications_tower": ("tower", 3, "Tower", "ანძა", True),
    "lighthouse": ("tower", 2, "Lighthouse", "შუქურა", False),
}
MONASTERY_WORDS = ("monaster", "მონასტ", "lavra", "ლავრ")
CATHEDRAL_WORDS = ("cathedral", "ტაძარ")
# letters a name must contain to be shown on a map in that language (one language per map)
SCRIPTS = {"ka": (0x10D0, 0x10FF), "en": (0x41, 0x7A), "de": (0x41, 0x7A)}


def in_script(text, lang):
    lo, hi = SCRIPTS.get(lang, (0, 0x10FFFF))
    return bool(text) and any(lo <= ord(ch) <= hi for ch in text)


def kind_of(p):
    k = p.get("kind")
    if k == "place_of_worship":
        rel = p.get("religion")
        if rel == "muslim":
            return "mosque"
        if rel == "jewish":
            return "synagogue"
        names = f"{p.get('name') or ''} {p.get('name_local') or ''}".lower()
        if any(w in names for w in MONASTERY_WORDS):
            return "monastery"
        if any(w in names for w in CATHEDRAL_WORDS):
            return "cathedral"
    if k == "tower" and p.get("man_made") == "tower":
        return None
    return k if k in KINDS else None


def pick(slug):
    d = ROOT / "data" / slug
    meta = json.loads((d / "meta.json").read_text())
    lang = meta.get("lang", "en")
    layers = json.loads((d / "layers.json").read_text())
    s, w, n, e = meta["bbox"]
    # keep icons off the frame edge
    ms, mw = (n - s) * 0.04, (e - w) * 0.04
    lat0, lon0 = meta.get("center_lat", meta["lat"]), meta.get("center_lon", meta["lon"])
    cand = []
    for f in layers["pois"]["features"]:
        p = f["properties"]
        k = kind_of(p)
        if not k:
            continue
        icon, rank, en, ka, named_only = KINDS[k]
        name, local = p.get("name"), p.get("name_local")
        # a name in another script would put a second language on the map: use the kind instead
        if not in_script(name, "en"):
            name = None
        if not in_script(local, lang):
            local = None
        if named_only and not (local if lang != "en" else name):
            continue
        lon, lat = f["geometry"]["coordinates"]
        if not (s + ms <= lat <= n - ms and w + mw <= lon <= e - mw):
            continue
        dist = math.hypot((lon - lon0) * math.cos(math.radians(lat0)), lat - lat0) * 111_320
        named = bool(local if lang != "en" else name)
        cand.append({"kind": k, "icon": icon, "rank": rank, "en": en, "ka": ka, "name": name, "local": local,
                     "lon": lon, "lat": lat, "osm": p.get("id"), "named": named,
                     # famous first: a Wikipedia / Wikidata entry is OpenStreetMap's best sign of notability
                     "score": (rank, not (p.get("wikidata") or p.get("wikipedia")), not named, dist)})
    kx = 111_320 * math.cos(math.radians(lat0))
    gap = (e - w) * kx * MIN_GAP
    out, per_kind = [], {}
    # greedy: the most important candidate next, and among equals a kind the map does not show yet
    while cand and len(out) < MAX_LANDMARKS:
        # importance = kind rank, one step down for every one of its kind already shown, one more if it has no name
        c = min(cand, key=lambda c: (c["rank"] + per_kind.get(c["icon"], 0) + (not c["named"]), *c["score"][1:]))
        cand.remove(c)
        if per_kind.get(c["icon"], 0) >= MAX_PER_KIND:
            continue
        if any(math.hypot((c["lon"] - o["lon"]) * kx, (c["lat"] - o["lat"]) * 111_320) < gap for o in out):
            continue
        per_kind[c["icon"]] = per_kind.get(c["icon"], 0) + 1
        out.append(c)
    return out


def outdated(slug):
    """No landmarks yet, or an automatic set made by older rules."""
    f = ROOT / "data" / slug / "landmarks.json"
    if not f.exists():
        return True
    try:
        d = json.loads(f.read_text())
    except ValueError:
        return False
    return bool(d.get("auto")) and d.get("version", 1) < VERSION


def build(slug):
    """Write data/<slug>/landmarks.json + icons. Returns the number of landmarks, or None if a hand-made set exists."""
    d = ROOT / "data" / slug
    f = d / "landmarks.json"
    if f.exists():
        try:
            if not json.loads(f.read_text()).get("auto"):
                return None
        except ValueError:
            return None
    chosen = pick(slug)
    (d / "icons").mkdir(exist_ok=True)
    lms, used = [], set()
    for i, c in enumerate(chosen, 1):
        icon_file = f"auto-{c['icon']}.svg"
        if c["icon"] not in used:
            shutil.copy2(ICONS / f"{c['icon']}.svg", d / "icons" / icon_file)
            used.add(c["icon"])
        named = c["named"]
        name, local = c["name"] or c["en"], c["local"] or c["ka"]
        rank = c["rank"] if c["rank"] > 1 or i <= MAX_HEROES else 2
        limit = HERO_LABEL_CHARS if rank == 1 else LABEL_CHARS
        short = lambda t: t if named and len(t) <= limit else ""  # noqa: E731
        lms.append({"id": f"auto-{i}", "name": name, "name_local": local,
                    "label": short(name), "label_local": short(local), "force_label": False,
                    "lon": c["lon"], "lat": c["lat"], "kind": c["kind"], "icon": icon_file, "rank": rank,
                    "blurb": c["en"] if named else None, "blurb_local": c["ka"] if named else None, "osm": c["osm"]})
    for old in (d / "icons").glob("auto-*.svg"):
        if old.stem[5:] not in used:
            old.unlink()
    tmp = f.with_name(".landmarks.json.tmp")
    tmp.write_text(json.dumps({"auto": True, "version": VERSION, "landmarks": lms}, ensure_ascii=False, indent=1))
    tmp.replace(f)
    return len(lms)


if __name__ == "__main__":
    for slug in sys.argv[1:]:
        print(slug, build(slug))
