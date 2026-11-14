"""PDF export of a rendered poster, at its own size or fitted to a paper size (A4, A3, Letter …).

Standalone on purpose (stdlib only), so the studio server can use it without loading the map engine.
The poster SVG is wrapped in a page of the requested size, scaled to fit and centred; the margins take the
poster's own paper colour. Vector output: text stays text, lines stay lines.
"""
import os, re, subprocess
from pathlib import Path

PAPER = {  # millimetres, portrait
    "A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297), "A5": (148, 210),
    "B3": (353, 500), "B4": (250, 353), "B5": (176, 250),
    "LETTER": (215.9, 279.4), "LEGAL": (215.9, 355.6), "TABLOID": (279.4, 431.8),
}
_ROOT = re.compile(r'<svg\b[^>]*\bwidth="([\d.]+)mm"[^>]*\bheight="([\d.]+)mm"[^>]*>')


def paper_size(spec, landscape=False):
    """'A4', 'letter' or 'WIDTHxHEIGHT' (mm) → (w, h) in mm, turned to match the poster's orientation."""
    s = str(spec).strip().upper()
    if s in PAPER:
        w, h = PAPER[s]
    else:
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*[X×]\s*(\d+(?:\.\d+)?)", s)
        if not m:
            raise ValueError(f"unknown paper size '{spec}' — use one of {', '.join(PAPER)} or WIDTHxHEIGHT in mm")
        w, h = float(m[1]), float(m[2])
        if not (20 <= w <= 5000 and 20 <= h <= 5000):
            raise ValueError("paper width and height must be between 20 and 5000 mm")
    return (max(w, h), min(w, h)) if landscape else (min(w, h), max(w, h))


def poster_mm(svg_text):
    m = _ROOT.search(svg_text[:2000])
    if not m:
        raise ValueError("not a poster SVG (no size in millimetres on its root element)")
    return float(m[1]), float(m[2]), m


def pdf_name(base, paper=None):
    """<theme>.<lang>.pdf at poster size, <theme>.<lang>.A4.pdf on paper."""
    return f"{base}.pdf" if not paper else f"{base}.{str(paper).upper().replace('×', 'x')}.pdf"


def make_pdf(svg_path, out_path, paper=None, margin=0.0, fontconfig=None):
    """Write a PDF of the poster. paper=None keeps the poster's own size. Returns (width_mm, height_mm)."""
    svg_path, out_path = Path(svg_path), Path(out_path)
    env = dict(os.environ)
    if fontconfig:
        env["FONTCONFIG_FILE"] = str(fontconfig)
    src = svg_path
    text = svg_path.read_text()
    w, h, root = poster_mm(text)
    size = (w, h)
    tmp = None
    if paper:
        pw, ph = paper_size(paper, landscape=w > h)
        k = min((pw - 2 * margin) / w, (ph - 2 * margin) / h)
        x, y = (pw - w * k) / 2, (ph - h * k) / 2
        bg = re.search(r'<rect width="[\d.]+" height="[\d.]+" fill="([^"]+)"', text)
        inner = f'<svg x="{x:.3f}" y="{y:.3f}" width="{w * k:.3f}" height="{h * k:.3f}" viewBox="0 0 {w:g} {h:g}">'
        wrapped = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{pw:g}mm" height="{ph:g}mm" '
                   f'viewBox="0 0 {pw:g} {ph:g}"><rect width="{pw:g}" height="{ph:g}" fill="{bg[1] if bg else "#ffffff"}"/>'
                   + inner + text[root.end():] + "</svg>")
        tmp = out_path.with_suffix(".tmp.svg")
        tmp.write_text(wrapped)
        src, size = tmp, (pw, ph)
    try:
        subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(out_path), str(src)], check=True, env=env, capture_output=True, text=True)
    finally:
        if tmp and tmp.exists():
            tmp.unlink()
    return size
