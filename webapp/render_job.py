"""Render one theme of one place into a folder — run as a subprocess by the site's worker so memory goes back to the
system after every map.

usage: python webapp/render_job.py <slug> <theme> <lang> <out_dir> [--width 1600] [--custom file.json] [--fonts JSON] [--thumb]

Writes <theme>.<lang>.svg (vector), .jpg (screen preview at --width) and .json (sidecar, written last so its presence
means the render is complete). PNG / PDF for printing are made later, only when someone downloads one.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from PIL import Image  # noqa: E402

from atlas.core import ENV  # noqa: E402
from atlas.render import Poster  # noqa: E402

Image.MAX_IMAGE_PIXELS = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("theme")
    ap.add_argument("lang")
    ap.add_argument("out_dir")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--custom")
    ap.add_argument("--fonts", help='JSON {role: family}: the visitor\'s own font choices')
    ap.add_argument("--thumb", action="store_true", help="also write thumb.jpg (gallery card)")
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = f"{a.theme}.{a.lang}"
    fonts = json.loads(a.fonts) if a.fonts else None
    p = Poster(a.slug, a.theme, a.lang, a.width, fonts=fonts, custom_path=a.custom)
    svg = p.render()
    tmp_svg, tmp_png = out / f".{base}.svg.tmp", out / f".{base}.png.tmp"
    tmp_svg.write_text(svg)
    subprocess.run(["rsvg-convert", "-w", str(a.width), "-o", str(tmp_png), str(tmp_svg)], check=True, env=ENV)
    with Image.open(tmp_png) as im:
        rgb = im.convert("RGB")
        rgb.save(out / f"{base}.jpg", quality=86, optimize=True, progressive=True)
        if a.thumb:
            t = rgb.copy()
            t.thumbnail((640, 640), Image.LANCZOS)
            t.save(out / "thumb.jpg", quality=82, optimize=True, progressive=True)
    tmp_png.unlink()
    os.replace(tmp_svg, out / f"{base}.svg")
    for old in out.glob(f"{base}.print*.png"):  # downloads made from an older render
        old.unlink()
    for old in [*out.glob(f"{base}*.pdf"), *out.glob(f"{base}.hd.jpg")]:
        old.unlink()
    side = p.sidecar(base)
    side["print"] = None
    (out / f"{base}.json").write_text(json.dumps(side, ensure_ascii=False))
    print(out / f"{base}.json")


if __name__ == "__main__":
    main()
