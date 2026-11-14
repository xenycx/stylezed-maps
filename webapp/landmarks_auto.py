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
MAX_LANDMARKS = 16
MAX_PER_KIND = 3

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
    "arts_centre": ("museum", 2, "Arts centre", "ხელოვნების ცენტრი", True),
    "gallery": ("museum", 2, "Gallery", "გალერეა", True),
    "theatre": ("museum", 2, "Theatre", "თეატრი", True),
    "peak": ("peak", 2, "Peak", "მწვერვალი", True),
    "viewpoint": ("viewpoint", 2, "Viewpoint", "გადასახედი", False),
    "attraction": ("sight", 2, "Sight", "ღირსშესანიშნაობა", True),
    "memorial": ("memorial", 3, "Memorial", "მემორიალი", True),
    "monument": ("memorial", 2, "Monument", "ძეგლი", True),
    "wayside_shrine": ("memorial", 3, "Shrine", "სალოცავი", True),
    "school": ("school", 3, "School", "სკოლა", False),
    "college": ("school", 3, "College", "კოლეჯი", True),
    "university": ("school", 2, "University", "უნივერსიტეტი", True),
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
                     "score": (rank, not named, dist)})
    cand.sort(key=lambda c: c["score"])
    out, per_kind = [], {}
    for c in cand:
        # the same church as a node and as a building outline, or two pins for one place
        if any(abs(c["lat"] - o["lat"]) < 0.0008 and abs(c["lon"] - o["lon"]) < 0.0011 and (c["icon"] == o["icon"] or (c["name"] and c["name"] == o["name"]))
               for o in out):
            continue
        if per_kind.get(c["icon"], 0) >= MAX_PER_KIND:
            continue
        per_kind[c["icon"]] = per_kind.get(c["icon"], 0) + 1
        out.append(c)
        if len(out) >= MAX_LANDMARKS:
            break
    return out


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
        lms.append({"id": f"auto-{i}", "name": c["name"] or c["en"], "name_local": c["local"] or c["ka"],
                    "lon": c["lon"], "lat": c["lat"], "kind": c["kind"], "icon": icon_file, "rank": c["rank"],
                    "blurb": c["en"] if named else None, "blurb_local": c["ka"] if named else None, "osm": c["osm"]})
    for old in (d / "icons").glob("auto-*.svg"):
        if old.stem[5:] not in used:
            old.unlink()
    tmp = f.with_name(".landmarks.json.tmp")
    tmp.write_text(json.dumps({"auto": True, "landmarks": lms}, ensure_ascii=False, indent=1))
    tmp.replace(f)
    return len(lms)


if __name__ == "__main__":
    for slug in sys.argv[1:]:
        print(slug, build(slug))
