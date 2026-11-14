"""Draw the site's link-preview banner (Open Graph, 1200×630) from real renders: three prints on the night desk and
the Georgian title. Run from the maps project after rendering; writes webapp/web/og.jpg.

usage: uv run python webapp/make_og.py CENTER.jpg LEFT.jpg RIGHT.jpg
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
W, H = 1200, 630
DESK, PAPER, ACCENT, TEXT2 = (27, 25, 23), (244, 237, 221), (210, 60, 39), (189, 181, 168)
FONT_DIRS = [ROOT / "fonts", Path("/usr/share/fonts/noto"), Path("/usr/share/fonts/truetype/noto")]


def font(name, size):
    for d in FONT_DIRS:
        if (d / name).is_file():
            return ImageFont.truetype(str(d / name), size)
    raise SystemExit(f"font not found: {name}")


def desk():
    """Graphite desk lit by a warm lamp from the upper right."""
    im = Image.new("RGB", (W, H), DESK)
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((560, -260, 1360, 520), fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    warm = Image.new("RGB", (W, H), (64, 50, 36))
    return Image.composite(warm, im, glow)


def place_print(canvas, path, height, cx, cy, angle, dim=1.0):
    p = Image.open(path).convert("RGB")
    p = p.resize((round(p.width * height / p.height), height), Image.LANCZOS)
    if dim < 1:
        p = Image.eval(p, lambda v: int(v * dim))
    pad = 60
    sheet = Image.new("RGBA", (p.width + 2 * pad, p.height + 2 * pad), (0, 0, 0, 0))
    sheet.paste(p, (pad, pad))
    shadow = Image.new("RGBA", sheet.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((pad + 6, pad + 22, pad + p.width + 6, pad + p.height + 22), fill=(0, 0, 0, 200))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    both = Image.alpha_composite(shadow, sheet).rotate(angle, resample=Image.BICUBIC, expand=True)
    canvas.paste(both, (round(cx - both.width / 2), round(cy - both.height / 2)), both)


def main():
    center, left, right = sys.argv[1:4]
    im = desk()
    # prints: back ones first, darker, fanned out
    place_print(im, left, 350, 815, 345, 8, dim=.78)
    place_print(im, right, 370, 1105, 300, -7, dim=.74)
    place_print(im, center, 460, 935, 318, -1.5)
    d = ImageDraw.Draw(im)
    title = font("NotoSerifGeorgian-Medium.ttf", 60)
    sub = font("NotoSansGeorgian-Regular.ttf", 25)
    url = font("FiraGO-Medium.ttf", 23)   # Latin letters: the Georgian faces have none
    x = 64
    d.text((x, 168), "სტილიზებული", font=title, fill=PAPER)
    d.text((x, 246), "რუკები", font=title, fill=PAPER)
    d.text((x, 352), "რეალური ადგილების", font=sub, fill=TEXT2)
    d.text((x, 388), "ილუსტრირებული რუკები", font=sub, fill=TEXT2)
    d.rounded_rectangle((x, 470, x + 6, 498), radius=3, fill=ACCENT)
    d.text((x + 20, 470), "maps.xenyc.ge", font=url, fill=PAPER)
    out = ROOT / "webapp" / "web" / "og.jpg"
    im.save(out, quality=88, optimize=True, progressive=True)
    print(out)


if __name__ == "__main__":
    main()
