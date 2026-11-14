"""Small procedural drawings: trees, animals, boats, rocks, houses, compass roses…

Every glyph is drawn in a unit box: it stands on (0,0), is ~1 unit tall, y grows downward
(so the top is at y = -1). The renderer wraps each one in a <symbol> and scales it to millimetres.
Style dict `gs`: ink (outline or None), fill, shade, accent, roof, sw (stroke width in units).
"""
import math, random


def _a(gs, key, default=None):
    return gs.get(key, default)


def _stroke(gs, w=1.0):
    ink = gs.get("ink")
    if not ink:
        return 'stroke="none"'
    return f'stroke="{ink}" stroke-width="{gs.get("sw", 0.07) * w:.3f}" stroke-linecap="round" stroke-linejoin="round"'


def blob(cx, cy, rx, ry, seed, bumps=7, rough=0.16):
    """Closed, smoothly bumpy outline (tree crowns, bushes, sheep)."""
    r = random.Random(seed)
    pts = []
    for i in range(bumps * 2):
        a = i / (bumps * 2) * math.tau
        k = 1 + (rough if i % 2 == 0 else -rough) * r.uniform(0.6, 1.2)
        pts.append((cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k))
    mids = [((pts[i][0] + pts[(i + 1) % len(pts)][0]) / 2, (pts[i][1] + pts[(i + 1) % len(pts)][1]) / 2) for i in range(len(pts))]
    d = f"M{mids[-1][0]:.3f},{mids[-1][1]:.3f}"
    for p, m in zip(pts, mids):
        d += f" Q{p[0]:.3f},{p[1]:.3f} {m[0]:.3f},{m[1]:.3f}"
    return d + "Z"


# ---------------------------------------------------------------- vegetation
def conifer(gs, v=0):
    w = (0.30, 0.36, 0.26)[v % 3]
    t = (0.52, 0.56, 0.6)[v % 3]
    body = f"M0,-1 L{w * .75:.2f},-{t} L{w * .4:.2f},-{t} L{w:.2f},-0.2 L0.06,-0.2 L0.06,0 L-0.06,0 L-0.06,-0.2 L-{w:.2f},-0.2 L-{w * .4:.2f},-{t} L-{w * .75:.2f},-{t} Z"
    shade = f"M0,-1 L{w * .75:.2f},-{t} L{w * .4:.2f},-{t} L{w:.2f},-0.2 L0.06,-0.2 L0,-0.2 Z"
    return (f'<path d="{body}" fill="{gs["fill"]}" {_stroke(gs)}/>'
            + (f'<path d="{shade}" fill="{gs["shade"]}" fill-opacity="{gs.get("shade_opacity", .55)}"/>' if gs.get("shade") else ""))


def round_tree(gs, v=0):
    cy = (-0.62, -0.6, -0.64)[v % 3]
    rx = (0.36, 0.4, 0.33)[v % 3]
    crown = blob(0, cy, rx, 0.34, 11 + v, 6)
    lit = blob(-0.05, cy - 0.05, rx * 0.74, 0.25, 31 + v, 5)
    trunk = f'<path d="M-0.045,0 L-0.035,-0.36 L0.035,-0.36 L0.045,0Z" fill="{gs.get("trunk") or gs.get("ink") or gs.get("shade") or gs["fill"]}"/>'
    if gs.get("shade"):
        return (trunk + f'<path d="{crown}" fill="{gs["shade"]}" {_stroke(gs)}/>'
                + f'<path d="{lit}" fill="{gs["fill"]}"/>')
    return trunk + f'<path d="{crown}" fill="{gs["fill"]}" {_stroke(gs)}/>'


def poplar(gs, v=0):
    crown = blob(0, -0.58, 0.17, 0.42, 5 + v, 6, 0.1)
    return (f'<path d="M-0.03,0 L-0.03,-0.3 L0.03,-0.3 L0.03,0Z" fill="{gs.get("trunk") or gs.get("ink") or gs.get("shade") or gs["fill"]}"/>'
            f'<path d="{crown}" fill="{gs["fill"]}" {_stroke(gs)}/>'
            + (f'<path d="M0.02,-0.98 Q0.2,-0.6 0.05,-0.2 Q0.14,-0.6 0.02,-0.98Z" fill="{gs["shade"]}" fill-opacity=".6"/>' if gs.get("shade") else ""))


def ink_tree(gs, v=0):
    """Pen-drawn tree for engraved / fantasy maps: no fill, scalloped crown, shaded side."""
    crown = blob(0, -0.62, 0.34, 0.33, 51 + v, 5, 0.2)
    return (f'<path d="M0,0 L0,-0.34" fill="none" {_stroke(gs, 1.2)}/>'
            f'<path d="{crown}" fill="{gs.get("fill", "none")}" {_stroke(gs)}/>'
            f'<path d="M0.1,-0.86 Q0.3,-0.62 0.14,-0.36 M0.2,-0.7 Q0.27,-0.6 0.22,-0.48" fill="none" {_stroke(gs, .8)}/>')


def bush(gs, v=0):
    return f'<path d="{blob(0, -0.2, 0.42, 0.26, 71 + v, 5, 0.2)}" fill="{gs["fill"]}" {_stroke(gs)}/>'


def grass(gs, v=0):
    s = (1, -1, 1)[v % 3]
    return (f'<path d="M-0.28,0 Q-0.3,-0.45 {-0.46 * s:.2f},-0.7 M0,0 L{0.04 * s:.2f},-1 M0.28,0 Q0.3,-0.5 {0.5 * s:.2f},-0.62" '
            f'fill="none" stroke="{gs.get("ink") or gs["fill"]}" stroke-width="{gs.get("sw", .07) * 1.3:.3f}" stroke-linecap="round"/>')


def reed(gs, v=0):
    c = gs.get("ink") or gs["fill"]
    return (f'<path d="M-0.15,0 Q-0.2,-0.5 -0.1,-0.95 M0.15,0 Q0.12,-0.4 0.25,-0.75" fill="none" stroke="{c}" stroke-width="{gs.get("sw", .07):.3f}" stroke-linecap="round"/>'
            f'<ellipse cx="-0.1" cy="-0.86" rx="0.06" ry="0.16" fill="{gs["fill"]}"/><ellipse cx="0.24" cy="-0.68" rx="0.05" ry="0.13" fill="{gs["fill"]}"/>')


def vine(gs, v=0):
    c = gs.get("ink") or gs["fill"]
    return (f'<path d="M0,0 V-0.9" stroke="{c}" stroke-width="{gs.get("sw", .07):.3f}" fill="none"/>'
            f'<circle cx="-0.2" cy="-0.55" r="0.2" fill="{gs["fill"]}"/><circle cx="0.2" cy="-0.72" r="0.2" fill="{gs["fill"]}"/>'
            f'<circle cx="0.12" cy="-0.36" r="0.17" fill="{gs["fill"]}"/>')


# ---------------------------------------------------------------- ground details
def rock(gs, v=0):
    shapes = ["M-0.5,0 L-0.34,-0.5 L0.08,-0.68 L0.5,-0.26 L0.46,0Z", "M-0.5,0 L-0.2,-0.6 L0.3,-0.5 L0.5,0Z",
              "M-0.45,0 L-0.4,-0.36 L-0.05,-0.56 L0.36,-0.42 L0.5,0Z"]
    facets = ["M0.08,-0.68 L0.5,-0.26 L0.46,0 L0.14,0Z", "M0.3,-0.5 L0.5,0 L0.12,0Z", "M-0.05,-0.56 L0.36,-0.42 L0.5,0 L0.1,0Z"]
    return (f'<path d="{shapes[v % 3]}" fill="{gs["fill"]}" {_stroke(gs)}/>'
            + (f'<path d="{facets[v % 3]}" fill="{gs["shade"]}" fill-opacity=".7"/>' if gs.get("shade") else ""))


def haystack(gs, v=0):
    """Rachan haystack: a cone of hay built round a pole."""
    return (f'<path d="M0,-0.8 V-1.02" fill="none" {_stroke(gs)}/>'
            f'<path d="M-0.36,0 Q-0.34,-0.55 0,-0.86 Q0.34,-0.55 0.36,0 Q0,0.08 -0.36,0Z" fill="{gs["fill"]}" {_stroke(gs)}/>'
            + (f'<path d="M0.04,-0.84 Q0.34,-0.55 0.36,0 Q0.2,0.05 0.1,0.04 Q0.2,-0.5 0.04,-0.84Z" fill="{gs["shade"]}" fill-opacity=".6"/>' if gs.get("shade") else "")
            + f'<path d="M-0.16,-0.3 L-0.12,-0.1 M0.02,-0.5 L0.04,-0.28" fill="none" {_stroke(gs, .7)}/>')


def cow(gs, v=0):
    f = -1 if v % 2 else 1
    body = (f'<path d="M-0.42,-0.62 Q-0.1,-0.7 0.3,-0.62 Q0.4,-0.6 0.4,-0.46 L0.38,-0.3 L-0.36,-0.3 Q-0.46,-0.46 -0.42,-0.62Z" fill="{gs["fill"]}" {_stroke(gs)}/>'
            f'<path d="M-0.42,-0.6 L-0.6,-0.66 L-0.66,-0.5 L-0.5,-0.44Z" fill="{gs["fill"]}" {_stroke(gs)}/>'
            f'<path d="M-0.3,-0.3 V0 M-0.14,-0.3 V0 M0.18,-0.3 V0 M0.33,-0.3 V0 M0.4,-0.56 Q0.5,-0.4 0.46,-0.24" fill="none" {_stroke(gs, 1.1)}/>'
            + (f'<path d="M-0.05,-0.66 Q0.12,-0.52 0.28,-0.62 Q0.1,-0.7 -0.05,-0.66Z M-0.3,-0.44 Q-0.2,-0.34 -0.1,-0.42 Q-0.2,-0.5 -0.3,-0.44Z" fill="{gs["shade"]}"/>' if gs.get("shade") else ""))
    return f'<g transform="scale({f},1)">{body}</g>'


def sheep(gs, v=0):
    f = -1 if v % 2 else 1
    return (f'<g transform="scale({f},1)"><path d="M-0.22,-0.3 V0 M0.2,-0.3 V0" fill="none" {_stroke(gs, 1.2)}/>'
            f'<path d="{blob(0, -0.46, 0.36, 0.24, 91 + v, 6, 0.14)}" fill="{gs["fill"]}" {_stroke(gs)}/>'
            f'<ellipse cx="-0.4" cy="-0.52" rx="0.12" ry="0.1" fill="{gs.get("shade") or gs.get("ink") or "#333"}"/></g>')


def bird(gs, v=0):
    k = (0.34, 0.26, 0.4)[v % 3]
    return (f'<path d="M-0.5,-{k:.2f} Q-0.28,-{k + .3:.2f} 0,-{k - .12:.2f} Q0.28,-{k + .3:.2f} 0.5,-{k:.2f}" fill="none" '
            f'stroke="{gs.get("ink") or gs["fill"]}" stroke-width="{gs.get("sw", .07) * 1.4:.3f}" stroke-linecap="round" stroke-linejoin="round"/>')


def grave(gs, v=0):
    return f'<path d="M0,0 V-1 M-0.3,-0.66 H0.3" fill="none" {_stroke(gs, 1.5)}/>'


# ---------------------------------------------------------------- water
def wave(gs, v=0):
    return (f'<path d="M-0.5,-0.2 Q-0.34,-0.46 -0.17,-0.2 Q0,0.04 0.17,-0.2 Q0.34,-0.46 0.5,-0.2" fill="none" '
            f'stroke="{gs.get("ink") or gs["fill"]}" stroke-width="{gs.get("sw", .07):.3f}" stroke-linecap="round"/>')


def rowboat(gs, v=0):
    f = -1 if v % 2 else 1
    return (f'<g transform="scale({f},1)"><path d="M-0.6,-0.36 L0.6,-0.36 Q0.46,-0.06 0.2,-0.04 L-0.26,-0.04 Q-0.5,-0.08 -0.6,-0.36Z" fill="{gs["fill"]}" {_stroke(gs)}/>'
            f'<path d="M-0.42,-0.22 H0.42" fill="none" {_stroke(gs, .7)}/>'
            f'<circle cx="-0.04" cy="-0.56" r="0.1" fill="{gs.get("ink") or gs["shade"]}"/>'
            f'<path d="M-0.04,-0.46 V-0.34 M-0.04,-0.4 L0.42,-0.14 M0.36,-0.2 L0.52,-0.06" fill="none" {_stroke(gs)}/>'
            f'<path d="M-0.8,0.06 Q-0.6,-0.04 -0.4,0.06 M0.3,0.08 Q0.5,-0.02 0.7,0.08" fill="none" {_stroke(gs, .7)}/></g>')


def sailboat(gs, v=0):
    f = -1 if v % 2 else 1
    return (f'<g transform="scale({f},1)"><path d="M-0.5,-0.26 L0.56,-0.26 Q0.4,-0.02 0.18,0 L-0.3,0 Q-0.44,-0.06 -0.5,-0.26Z" fill="{gs.get("shade") or gs["fill"]}" {_stroke(gs)}/>'
            f'<path d="M0,-0.26 V-1" fill="none" {_stroke(gs)}/>'
            f'<path d="M0.04,-0.96 L0.5,-0.34 L0.04,-0.34Z" fill="{gs["fill"]}" {_stroke(gs)}/>'
            f'<path d="M-0.04,-0.86 L-0.4,-0.34 L-0.04,-0.34Z" fill="{gs["fill"]}" {_stroke(gs)}/>'
            + (f'<path d="M0,-1 L0.18,-0.94 L0,-0.88Z" fill="{gs["accent"]}"/>' if gs.get("accent") else "")
            + f'<path d="M-0.8,0.08 Q-0.6,-0.02 -0.4,0.08 M0.3,0.1 Q0.5,0 0.7,0.1" fill="none" {_stroke(gs, .7)}/></g>')


# ---------------------------------------------------------------- relief & buildings
def mountain(gs, v=0):
    outlines = ["M-0.7,0 L-0.12,-1 L0.06,-0.74 L0.2,-0.9 L0.74,0", "M-0.74,0 L-0.3,-0.7 L-0.16,-0.56 L0.1,-1 L0.7,0",
                "M-0.66,0 L0,-1 L0.16,-0.8 L0.3,-0.86 L0.7,0"]
    tops = [(-0.12, -1), (0.1, -1), (0, -1)]
    o = outlines[v % 3]
    tx, ty = tops[v % 3]
    hatch = " ".join(f"M{tx + 0.08 + i * 0.1:.2f},{ty + 0.2 + i * 0.16:.2f} L{tx + 0.02 + i * 0.13:.2f},{min(0, ty + 0.5 + i * 0.2):.2f}" for i in range(5))
    return (f'<path d="{o} Z" fill="{gs["fill"]}" stroke="none"/>'
            + (f'<path d="M{tx},{ty} L0.72,0 L{tx + 0.1:.2f},0 Z" fill="{gs["shade"]}" fill-opacity=".45"/>' if gs.get("shade") else "")
            + f'<path d="{o}" fill="none" {_stroke(gs, 1.2)}/><path d="{hatch}" fill="none" {_stroke(gs, .7)}/>')


def hill(gs, v=0):
    return (f'<path d="M-0.7,0 Q-0.4,-0.72 0,-0.74 Q0.42,-0.72 0.7,0Z" fill="{gs["fill"]}" stroke="none"/>'
            f'<path d="M-0.7,0 Q-0.4,-0.72 0,-0.74 Q0.42,-0.72 0.7,0" fill="none" {_stroke(gs, 1.1)}/>'
            f'<path d="M0.2,-0.6 L0.26,-0.36 M0.36,-0.5 L0.44,-0.22 M0.5,-0.34 L0.56,-0.12" fill="none" {_stroke(gs, .7)}/>')


def house(gs, v=0):
    roof = gs.get("roof", gs.get("shade", "#a33"))
    if v % 3 == 1:  # long house, side-on
        return (f'<path d="M-0.5,0 V-0.44 H0.5 V0Z" fill="{gs["fill"]}" {_stroke(gs)}/>'
                f'<path d="M-0.6,-0.44 L-0.4,-0.86 H0.4 L0.6,-0.44Z" fill="{roof}" {_stroke(gs)}/>'
                f'<path d="M-0.08,0 V-0.26 H0.1 V0" fill="none" {_stroke(gs, .8)}/>')
    if v % 3 == 2:  # tall house with chimney
        return (f'<path d="M0.16,-0.9 V-1.04 H0.3 V-0.74" fill="{gs["fill"]}" {_stroke(gs, .8)}/>'
                f'<path d="M-0.36,0 V-0.56 H0.36 V0Z" fill="{gs["fill"]}" {_stroke(gs)}/>'
                f'<path d="M-0.48,-0.54 L0,-1 L0.48,-0.54Z" fill="{roof}" {_stroke(gs)}/>'
                f'<path d="M-0.12,-0.34 H0.12" fill="none" {_stroke(gs, .8)}/>')
    return (f'<path d="M-0.4,0 V-0.5 H0.4 V0Z" fill="{gs["fill"]}" {_stroke(gs)}/>'
            f'<path d="M-0.52,-0.48 L0,-0.94 L0.52,-0.48Z" fill="{roof}" {_stroke(gs)}/>'
            f'<path d="M-0.06,0 V-0.24 H0.1 V0" fill="none" {_stroke(gs, .8)}/>')


def apartments(gs, v=0):
    """City building: a flat-roofed block with rows of windows (for apartments, offices, shops and big footprints)."""
    roof = gs.get("roof", gs.get("shade", "#a33"))
    win = gs.get("window") or gs.get("ink") or "#000"
    wo = gs.get("window_opacity", .55)

    def block(x0, x1, top, cols, rows):
        w, h = x1 - x0, -top
        cw, rh = w / cols, (h - .14) / rows
        wins = "".join(f"M{x0 + cw * (c + .3):.3f},{top + .12 + rh * (r + .25):.3f}h{cw * .4:.3f}v{rh * .42:.3f}h{-cw * .4:.3f}z"
                       for c in range(cols) for r in range(rows))
        return (f'<path d="M{x0},0 V{top} H{x1} V0Z" fill="{gs["fill"]}" {_stroke(gs)}/>'
                f'<path d="M{x0 - .05},{top} V{top - .09} H{x1 + .05} V{top}Z" fill="{roof}" {_stroke(gs, .8)}/>'
                f'<path d="{wins}" fill="{win}" fill-opacity="{wo}" stroke="none"/>')
    if v % 3 == 1:  # long slab
        return block(-.6, .6, -.74, 5, 3)
    if v % 3 == 2:  # tower with a low wing
        return block(.16, .56, -.5, 2, 2) + block(-.34, .2, -1.3, 2, 5)
    return block(-.38, .38, -1.04, 3, 4)


def moon(gs, v=0):
    """Full moon with a few maria; fill = disc, shade = craters, ink = optional rim."""
    c = gs.get("shade") or gs["fill"]
    return (f'<circle cx="0" cy="-0.5" r="0.5" fill="{gs["fill"]}" {_stroke(gs)}/>'
            f'<circle cx="-0.14" cy="-0.62" r="0.13" fill="{c}" fill-opacity=".5"/><circle cx="0.16" cy="-0.36" r="0.09" fill="{c}" fill-opacity=".5"/>'
            f'<circle cx="0.12" cy="-0.74" r="0.06" fill="{c}" fill-opacity=".5"/><circle cx="-0.2" cy="-0.3" r="0.05" fill="{c}" fill-opacity=".5"/>')


def star(gs, v=0):
    k = (0.16, 0.12, 0.2)[v % 3]
    return (f'<path d="M0,-1 Q{k},-{0.5 + k} 0.5,-0.5 Q{k},-{0.5 - k} 0,0 Q-{k},-{0.5 - k} -0.5,-0.5 Q-{k},-{0.5 + k} 0,-1Z" '
            f'fill="{gs["fill"]}" {_stroke(gs)}/>')


def sun(gs, v=0):
    rays = " ".join(f"M{math.sin(a) * .36:.2f},{-0.5 - math.cos(a) * .36:.2f} L{math.sin(a) * .5:.2f},{-0.5 - math.cos(a) * .5:.2f}"
                    for a in (i / 12 * math.tau for i in range(12)))
    return (f'<path d="{rays}" fill="none" stroke="{gs.get("ink") or gs["fill"]}" stroke-width="{gs.get("sw", .05):.3f}" stroke-linecap="round"/>'
            f'<circle cx="0" cy="-0.5" r="0.27" fill="{gs["fill"]}" {_stroke(gs)}/>')


def cloud(gs, v=0):
    return f'<path d="{blob(0, -0.3, 0.5, 0.24, 17 + v, 5, 0.18)}" fill="{gs["fill"]}" {_stroke(gs)}/>'


GLYPHS = {
    "conifer": conifer, "round": round_tree, "poplar": poplar, "ink_tree": ink_tree, "bush": bush, "grass": grass,
    "reed": reed, "vine": vine, "rock": rock, "haystack": haystack, "cow": cow, "sheep": sheep, "bird": bird,
    "grave": grave, "wave": wave, "rowboat": rowboat, "sailboat": sailboat, "mountain": mountain, "hill": hill,
    "house": house, "apartments": apartments, "moon": moon, "star": star, "sun": sun, "cloud": cloud,
}
VARIANTS = 3


# ---------------------------------------------------------------- one-off ornaments (page units = mm)
def compass(x, y, size, c, style="rose8", label="N", font=None):
    """Returns (markup, label_xy). `c` = {ink, fill, accent}."""
    ink, fill, acc = c.get("ink", "#222"), c.get("fill", "#fff"), c.get("accent", c.get("ink", "#222"))
    out = []
    if style == "arrow":
        out.append(f'<path d="M{x},{y - size} L{x + size * .3},{y + size * .42} L{x},{y + size * .16} Z" fill="{acc}"/>'
                   f'<path d="M{x},{y - size} L{x - size * .3},{y + size * .42} L{x},{y + size * .16} Z" fill="{fill}" stroke="{ink}" stroke-width="{size * .03:.3f}" stroke-linejoin="round"/>')
        return "".join(out), (x, y - size * 1.28)
    n = 16 if style == "rose16" else 8
    sw = size * 0.022
    out.append(f'<circle cx="{x}" cy="{y}" r="{size * .78:.2f}" fill="none" stroke="{ink}" stroke-width="{sw:.3f}"/>'
               f'<circle cx="{x}" cy="{y}" r="{size * .7:.2f}" fill="none" stroke="{ink}" stroke-width="{sw * .5:.3f}"/>')
    for i in range(72):  # degree ticks on the ring
        a = i / 72 * math.tau
        r0, r1 = size * (0.7 if i % 9 else 0.64), size * 0.78
        out.append(f'<path d="M{x + math.sin(a) * r0:.2f},{y - math.cos(a) * r0:.2f} L{x + math.sin(a) * r1:.2f},{y - math.cos(a) * r1:.2f}" stroke="{ink}" stroke-width="{sw * .5:.3f}"/>')
    tiers = [(n, 0.42, 0.1)] if n == 8 else [(16, 0.5, 0.07)]
    tiers += [(8, 0.62, 0.11)] if n == 16 else []
    tiers += [(4, 0.74, 0.14), (4, 1.0, 0.17)]
    for ti, (cnt, length, half) in enumerate(tiers):
        off = math.pi / cnt if ti < len(tiers) - 1 and cnt != 4 else (math.pi / 4 if ti == len(tiers) - 2 else 0)
        for i in range(cnt):
            a = i / cnt * math.tau + off
            tip = (x + math.sin(a) * size * length, y - math.cos(a) * size * length)
            l = (x + math.sin(a - math.pi / 2) * size * half, y - math.cos(a - math.pi / 2) * size * half)
            r = (x + math.sin(a + math.pi / 2) * size * half, y - math.cos(a + math.pi / 2) * size * half)
            north = ti == len(tiers) - 1 and i == 0
            out.append(f'<path d="M{x},{y} L{l[0]:.2f},{l[1]:.2f} L{tip[0]:.2f},{tip[1]:.2f}Z" fill="{acc if north else ink}" stroke="{ink}" stroke-width="{sw:.3f}" stroke-linejoin="round"/>'
                       f'<path d="M{x},{y} L{r[0]:.2f},{r[1]:.2f} L{tip[0]:.2f},{tip[1]:.2f}Z" fill="{fill}" stroke="{ink}" stroke-width="{sw:.3f}" stroke-linejoin="round"/>')
    out.append(f'<circle cx="{x}" cy="{y}" r="{size * .06:.2f}" fill="{fill}" stroke="{ink}" stroke-width="{sw:.3f}"/>')
    return "".join(out), (x, y - size * 1.2)


def ribbon(cx, cy, w, h, c):
    """Banner for titles: a ribbon with folded swallow-tail ends. (cx,cy) = centre of the main band."""
    ink, fill, shade = c.get("ink", "#222"), c.get("fill", "#fff"), c.get("shade", "#bbb")
    sw = c.get("sw", 0.35)
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    t, drop, cut = h * 0.9, h * 0.28, h * 0.3
    tail = lambda s: (f'<path d="M{(x0 if s < 0 else x1) - s * h * .3:.2f},{y0 + drop:.2f} L{(x0 if s < 0 else x1) + s * t:.2f},{y0 + drop:.2f} '
                      f'L{(x0 if s < 0 else x1) + s * (t - cut):.2f},{cy + drop:.2f} L{(x0 if s < 0 else x1) + s * t:.2f},{y1 + drop:.2f} '
                      f'L{(x0 if s < 0 else x1) - s * h * .3:.2f},{y1 + drop:.2f}Z" fill="{fill}" stroke="{ink}" stroke-width="{sw}" stroke-linejoin="round"/>'
                      f'<path d="M{(x0 if s < 0 else x1):.2f},{y1:.2f} L{(x0 if s < 0 else x1) - s * h * .3:.2f},{y1 + drop:.2f} L{(x0 if s < 0 else x1) - s * h * .3:.2f},{y0 + drop:.2f}Z" '
                      f'fill="{shade}" stroke="{ink}" stroke-width="{sw}" stroke-linejoin="round"/>')
    band = (f'<path d="M{x0:.2f},{y0:.2f} Q{cx:.2f},{y0 - h * .12:.2f} {x1:.2f},{y0:.2f} L{x1:.2f},{y1:.2f} Q{cx:.2f},{y1 - h * .12:.2f} {x0:.2f},{y1:.2f}Z" '
            f'fill="{fill}" stroke="{ink}" stroke-width="{sw}" stroke-linejoin="round"/>')
    return tail(-1) + tail(1) + band


def corner_ornament(x, y, sx, sy, size, ink, sw=0.3):
    """Flourish for a frame corner; sx, sy = ±1 pick the quadrant it grows into."""
    p = lambda a, b: f"{x + sx * a * size:.2f},{y + sy * b * size:.2f}"
    return (f'<path d="M{p(0, 1)} L{p(0, .32)} Q{p(0, 0)} {p(.32, 0)} L{p(1, 0)} '
            f'M{p(.16, .78)} L{p(.16, .42)} Q{p(.16, .16)} {p(.42, .16)} L{p(.78, .16)} '
            f'M{p(.16, .78)} Q{p(.3, .74)} {p(.27, .6)} M{p(.78, .16)} Q{p(.74, .3)} {p(.6, .27)}" '
            f'fill="none" stroke="{ink}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="M{p(.34, .26)} L{p(.42, .34)} L{p(.34, .42)} L{p(.26, .34)}Z" fill="{ink}"/>')
