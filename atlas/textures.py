"""Raster paper textures (grain, mottling, fibres, stains, vignette) embedded into the SVG.

One greyscale "wear" map is built with numpy and tinted, then laid over the artwork with a blend mode:
`multiply` darkens light papers; `screen` puts light grain on dark papers.
"""
import base64, io
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import hex_rgb


def _noise(rng, w, h, cells):
    small = rng.random((max(2, round(cells * h / w)), cells)).astype(np.float32)
    img = Image.fromarray((small * 255).astype(np.uint8), "L").resize((w, h), Image.BICUBIC)
    return np.asarray(img, dtype=np.float32) / 255 - 0.5


def wear_map(w, h, seed=1, grain=0.05, mottle=0.07, fibers=0.03, stains=0, vignette=0.18, edge_wear=0.0):
    """Float array in 0..1 — how much 'ink' the texture adds at each pixel."""
    rng = np.random.default_rng(seed)
    v = np.zeros((h, w), np.float32)
    if mottle:
        for cells, amp in ((4, 1.0), (9, 0.6), (22, 0.35), (60, 0.2)):
            v += _noise(rng, w, h, cells) * amp * mottle
        v += mottle * 0.5
    if grain:
        g = rng.normal(0, 1, (h, w)).astype(np.float32)
        g = np.asarray(Image.fromarray(np.clip(g * 40 + 128, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.6)), np.float32) / 255 - 0.5
        v += g * grain * 2.2
    if fibers:
        im = Image.new("L", (w, h), 0)
        dr = ImageDraw.Draw(im)
        for _ in range(int(w * h / 2600)):
            x, y = rng.integers(0, w), rng.integers(0, h)
            a = rng.uniform(0, np.pi)
            l = rng.uniform(4, 18) * w / 1200
            dr.line([(x, y), (x + np.cos(a) * l, y + np.sin(a) * l)], fill=int(rng.integers(90, 255)), width=1)
        v += np.asarray(im.filter(ImageFilter.GaussianBlur(0.5)), np.float32) / 255 * fibers
    if stains:
        im = Image.new("L", (w, h), 0)
        dr = ImageDraw.Draw(im)
        for _ in range(stains):
            cx, cy = rng.uniform(0.05, 0.95) * w, rng.uniform(0.05, 0.95) * h
            r = rng.uniform(0.04, 0.13) * w
            sq = rng.uniform(0.7, 1.3)
            bb = [cx - r, cy - r * sq, cx + r, cy + r * sq]
            dr.ellipse(bb, fill=int(rng.integers(30, 70)))
            dr.ellipse(bb, outline=int(rng.integers(90, 150)), width=max(1, int(w / 500)))
        v += np.asarray(im.filter(ImageFilter.GaussianBlur(w / 260)), np.float32) / 255 * 0.5
    if vignette or edge_wear:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy)) / (0.5 * min(w, h))
        if vignette:
            v += (1 - np.clip(d / 0.55, 0, 1)) ** 2.2 * vignette
        if edge_wear:
            rough = _noise(rng, w, h, 40) * 0.05
            v += np.clip(1 - (d + rough) / 0.05, 0, 1) * edge_wear
    return np.clip(v, 0, 1)


def texture_uri(w_mm, h_mm, spec, seed=1):
    """spec: {tint, blend, grain, mottle, fibers, stains, vignette, edge_wear, px_per_mm}"""
    k = spec.get("px_per_mm", 4)
    w, h = max(64, round(w_mm * k)), max(64, round(h_mm * k))
    v = wear_map(w, h, seed, spec.get("grain", 0.05), spec.get("mottle", 0.07), spec.get("fibers", 0.03),
                 spec.get("stains", 0), spec.get("vignette", 0.18), spec.get("edge_wear", 0.0))
    tint = np.array(hex_rgb(spec.get("tint", "#7a5a2e")), np.float32)
    base = 0.0 if spec.get("blend", "multiply") == "screen" else 255.0
    rgb = base + (tint - base) * v[..., None]
    buf = io.BytesIO()
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").save(buf, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def hillshade_uri(hs, spec):
    """hs: 0..1 hillshade array → RGBA PNG data URI of tinted shadows/highlights."""
    import math
    flat = math.sin(math.radians(45))
    shadow = np.clip((flat - hs) / flat, 0, 1) ** spec.get("gamma", 1.0) * spec.get("shadow_opacity", 0.5)
    light = np.clip((hs - flat) / (1 - flat), 0, 1) * spec.get("light_opacity", 0.0)
    a = shadow + light
    sc = np.array(hex_rgb(spec.get("shadow", "#000000")), np.float32)
    lc = np.array(hex_rgb(spec.get("light", "#ffffff")), np.float32)
    rgb = np.where(a[..., None] > 0, (sc * shadow[..., None] + lc * light[..., None]) / np.maximum(a, 1e-6)[..., None], 0)
    out = np.dstack([rgb, np.clip(a, 0, 1) * 255]).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(out, "RGBA").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
