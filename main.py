#!/usr/bin/env python3
"""Cutest picture entry for make.fun competition cutest-picture-01.

Draws, with only the Python standard library, one 1024x1024 picture of a
chubby baby bunny -- head tilted, one floppy ear, a tiny flower clipped
beside it -- cuddling next to a tiny chick friend, and writes it to
``$MAKEFUN_OUTPUT_DIR/entry.png`` (default ``/output``).

Every shape is a signed-distance field painted into an RGB buffer with
analytic anti-aliasing, so the picture is smooth and vector-clean. The
program is fully deterministic (no randomness, no network, no external
assets): two runs write byte-identical files.
"""

import math
import os
import struct
import zlib

W = H = 1024
W3 = W * 3

# ---------------------------------------------------------------- canvas ---

buf = bytearray(W * H * 3)


def paint(bbox, sdf, color, alpha=1.0, aa=1.3):
    """Paint a shape given by a signed-distance function over a bounding box.

    ``sdf(x, y)`` returns the signed distance to the shape's edge (negative
    inside). Pixels within ``aa`` of the edge are blended for smooth edges.
    """
    x0, y0, x1, y1 = bbox
    if x0 < 0:
        x0 = 0
    if y0 < 0:
        y0 = 0
    if x1 > W - 1:
        x1 = W - 1
    if y1 > H - 1:
        y1 = H - 1
    r, g, b = color
    inv = 1.0 / (2.0 * aa)
    for y in range(y0, y1 + 1):
        base = y * W3
        for x in range(x0, x1 + 1):
            d = sdf(x + 0.5, y + 0.5)
            if d >= aa:
                continue
            if d <= -aa:
                a = alpha
            else:
                a = alpha * (0.5 - d * inv)
            i = base + x * 3
            if a >= 1.0:
                buf[i] = r
                buf[i + 1] = g
                buf[i + 2] = b
            else:
                ia = 1.0 - a
                buf[i] = int(r * a + buf[i] * ia + 0.5)
                buf[i + 1] = int(g * a + buf[i + 1] * ia + 0.5)
                buf[i + 2] = int(b * a + buf[i + 2] * ia + 0.5)


# ------------------------------------------------- signed-distance fields ---

def s_circle(cx, cy, r):
    def f(x, y):
        return math.hypot(x - cx, y - cy) - r

    return f


def s_ellipse(cx, cy, rx, ry, ang=0.0):
    c, s = math.cos(ang), math.sin(ang)
    m = rx if rx < ry else ry

    def f(x, y):
        dx, dy = x - cx, y - cy
        lx = dx * c + dy * s
        ly = -dx * s + dy * c
        qx, qy = lx / rx, ly / ry
        return (math.sqrt(qx * qx + qy * qy) - 1.0) * m

    return f


def s_capsule(ax, ay, bx, by, r):
    vx, vy = bx - ax, by - ay
    ll = vx * vx + vy * vy

    def f(x, y):
        wx, wy = x - ax, y - ay
        t = (wx * vx + wy * vy) / ll
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        return math.hypot(x - (ax + t * vx), y - (ay + t * vy)) - r

    return f


def s_arc(cx, cy, R, a0, a1, w):
    ex0, ey0 = cx + R * math.cos(a0), cy + R * math.sin(a0)
    ex1, ey1 = cx + R * math.cos(a1), cy + R * math.sin(a1)

    def f(x, y):
        ang = math.atan2(y - cy, x - cx)
        d = abs(math.hypot(x - cx, y - cy) - R) - w
        if a0 <= ang <= a1:
            return d
        d0 = math.hypot(x - ex0, y - ey0) - w
        d1 = math.hypot(x - ex1, y - ey1) - w
        return d0 if d0 < d1 else d1

    return f


def s_star(cx, cy, s):
    # Four-point sparkle (astroid): |x|^(2/3) + |y|^(2/3) <= 1.

    def f(x, y):
        ax = abs(x - cx) / s
        ay = abs(y - cy) / s
        return (ax ** (2.0 / 3.0) + ay ** (2.0 / 3.0) - 1.0) * s * 0.6

    return f


def s_heart(cx, cy, s):
    # Two round lobes on top, one diamond point below.

    def f(x, y):
        d1 = math.hypot(x - (cx - 0.45 * s), y - (cy - 0.25 * s)) - 0.55 * s
        d2 = math.hypot(x - (cx + 0.45 * s), y - (cy - 0.25 * s)) - 0.55 * s
        d3 = (abs(x - cx) + abs(y - (cy + 0.28 * s))) * 0.7071 - 0.72 * s
        return min(d1, d2, d3)

    return f


# ------------------------------------------------------- head-local frame ---
# The bunny's head (ears, face, flower) is drawn in a local frame tilted by
# a few degrees around the head centre, for the head-tilt charm.

HCX, HCY = 470.0, 430.0
ANG = math.radians(-6.0)
CA, SA = math.cos(ANG), math.sin(ANG)


def rot_sdf(f):
    def g(x, y):
        dx, dy = x - HCX, y - HCY
        return f(dx * CA + dy * SA, -dx * SA + dy * CA)

    return g


def local_bbox(lx0, ly0, lx1, ly1, m=6):
    xs, ys = [], []
    for lx, ly in ((lx0, ly0), (lx0, ly1), (lx1, ly0), (lx1, ly1)):
        xs.append(HCX + lx * CA - ly * SA)
        ys.append(HCY + lx * SA + ly * CA)
    return (int(min(xs)) - m, int(min(ys)) - m,
            int(max(xs)) + m, int(max(ys)) + m)


def box(cx, cy, rx, ry, m=3):
    return (int(cx - rx) - m, int(cy - ry) - m,
            int(cx + rx) + m, int(cy + ry) + m)


# ------------------------------------------------------------ shape verbs ---

def disc(cx, cy, r, color, alpha=1.0, aa=1.3, head=False):
    if head:
        paint(local_bbox(cx - r - aa, cy - r - aa, cx + r + aa, cy + r + aa),
              rot_sdf(s_circle(cx, cy, r)), color, alpha, aa)
    else:
        paint(box(cx, cy, r + aa, r + aa), s_circle(cx, cy, r),
              color, alpha, aa)


def ellip(cx, cy, rx, ry, color, alpha=1.0, aa=1.3, head=False, ang=0.0):
    if head:
        paint(local_bbox(cx - rx - aa, cy - ry - aa, cx + rx + aa, cy + ry + aa),
              rot_sdf(s_ellipse(cx, cy, rx, ry, ang)), color, alpha, aa)
    else:
        ext = max(rx, ry) + aa
        paint(box(cx, cy, ext, ext), s_ellipse(cx, cy, rx, ry, ang),
              color, alpha, aa)


def caps(ax, ay, bx, by, r, color, alpha=1.0, aa=1.3, head=False):
    if head:
        paint(local_bbox(min(ax, bx) - r - aa, min(ay, by) - r - aa,
                         max(ax, bx) + r + aa, max(ay, by) + r + aa),
              rot_sdf(s_capsule(ax, ay, bx, by, r)), color, alpha, aa)
    else:
        paint((int(min(ax, bx) - r - aa - 1), int(min(ay, by) - r - aa - 1),
               int(max(ax, bx) + r + aa + 1), int(max(ay, by) + r + aa + 1)),
              s_capsule(ax, ay, bx, by, r), color, alpha, aa)


def arc(cx, cy, R, a0, a1, w, color, alpha=1.0, aa=1.3, head=False):
    ext = R + w + aa
    if head:
        paint(local_bbox(cx - ext, cy - ext, cx + ext, cy + ext),
              rot_sdf(s_arc(cx, cy, R, a0, a1, w)), color, alpha, aa)
    else:
        paint(box(cx, cy, ext, ext), s_arc(cx, cy, R, a0, a1, w),
              color, alpha, aa)


def star(cx, cy, s, color, alpha=1.0, aa=1.6):
    paint(box(cx, cy, s + aa, s + aa), s_star(cx, cy, s), color, alpha, aa)


def heart(cx, cy, s, color, alpha=1.0, aa=1.6):
    paint(box(cx, cy, s + aa, 1.4 * s + aa), s_heart(cx, cy, s),
          color, alpha, aa)


def tube_bezier(p0, p1, p2, r, color, head=False, t0=0.0, t1=1.0, n=22):
    """Paint a smooth bent tube: discs sampled along a quadratic Bezier.

    A polyline of capsules leaves notches at the joints; overlapping discs
    along a curve stay smooth, which the floppy ear needs.
    """
    for k in range(n + 1):
        t = t0 + (t1 - t0) * k / n
        u = 1.0 - t
        x = u * u * p0[0] + 2.0 * u * t * p1[0] + t * t * p2[0]
        y = u * u * p0[1] + 2.0 * u * t * p1[1] + t * t * p2[1]
        disc(x, y, r, color, head=head)


def flower(cx, cy, s, petal, center, outline=None, head=False):
    for k in range(5):
        a = -math.pi / 2 + k * (2.0 * math.pi / 5.0)
        px, py = cx + 0.62 * s * math.cos(a), cy + 0.62 * s * math.sin(a)
        if outline is not None:
            disc(px, py, 0.52 * s, outline, head=head)
        disc(px, py, 0.46 * s, petal, head=head)
    if outline is not None:
        disc(cx, cy, 0.44 * s, outline, head=head)
    disc(cx, cy, 0.38 * s, center, head=head)


# ---------------------------------------------------------------- colours ---

OUTLINE = (214, 150, 133)       # soft warm outline for the bunny
CREAM = (255, 251, 245)         # bunny fur
INNER_EAR = (255, 183, 205)     # pink inner ear
BLUSH = (255, 148, 178)         # cheek blush
EYE = (46, 34, 34)              # dark glossy eyes
WHITE = (255, 255, 255)
NOSE = (255, 143, 171)          # tiny pink nose
MOUTH = (198, 132, 118)         # smile lines
PETAL = (255, 227, 238)         # flower petals
PETAL_LINE = (244, 178, 202)    # flower outline
FLOWER_CENTRE = (255, 201, 60)  # flower centre
CHICK = (255, 217, 61)          # chick fluff
CHICK_LINE = (232, 169, 61)     # chick outline
WING = (245, 192, 46)           # chick wing
BEAK = (255, 159, 67)           # chick beak and feet


# --------------------------------------------------------------- backdrop ---

def paint_background():
    stops = [(0.0, (255, 213, 227)),
             (0.55, (255, 232, 221)),
             (1.0, (255, 245, 222))]
    for y in range(H):
        t = y / (H - 1)
        if t <= 0.55:
            f = t / 0.55
            c0, c1 = stops[0][1], stops[1][1]
        else:
            f = (t - 0.55) / 0.45
            c0, c1 = stops[1][1], stops[2][1]
        r = int(c0[0] + (c1[0] - c0[0]) * f + 0.5)
        g = int(c0[1] + (c1[1] - c0[1]) * f + 0.5)
        b = int(c0[2] + (c1[2] - c0[2]) * f + 0.5)
        buf[y * W3:(y + 1) * W3] = bytes((r, g, b)) * W


def paint_glow(cx, cy, R, color, peak):
    r2 = float(R * R)
    x0, y0 = max(0, int(cx - R)), max(0, int(cy - R))
    x1, y1 = min(W - 1, int(cx + R)), min(H - 1, int(cy + R))
    r, g, b = color
    for y in range(y0, y1 + 1):
        dy = y + 0.5 - cy
        base = y * W3
        for x in range(x0, x1 + 1):
            dx = x + 0.5 - cx
            d2 = dx * dx + dy * dy
            if d2 >= r2:
                continue
            t = 1.0 - d2 / r2
            a = peak * t * t
            i = base + x * 3
            ia = 1.0 - a
            buf[i] = int(r * a + buf[i] * ia + 0.5)
            buf[i + 1] = int(g * a + buf[i + 1] * ia + 0.5)
            buf[i + 2] = int(b * a + buf[i + 2] * ia + 0.5)


# ------------------------------------------------------------------ chick ---

def paint_chick():
    ccx, ccy = 735.0, 805.0
    # Head tuft (behind the body).
    for (ax, ay, bx, by) in ((717, 733, 707, 703), (735, 727, 735, 697),
                             (753, 733, 763, 703)):
        caps(ax, ay, bx, by, 7, CHICK_LINE)
        caps(ax, ay, bx, by, 4.5, CHICK)
    # Feet.
    ellip(714, 890, 12, 7, BEAK)
    ellip(756, 890, 12, 7, BEAK)
    # Body.
    disc(ccx, ccy, 90, CHICK_LINE)
    disc(ccx, ccy, 84, CHICK)
    # Wing.
    ellip(788, 828, 30, 43, CHICK_LINE, ang=math.radians(-20))
    ellip(788, 828, 24, 37, WING, ang=math.radians(-20))
    # Eyes.
    for ex in (709, 761):
        disc(ex, 784, 12, EYE)
        disc(ex - 3, 780, 4.5, WHITE)
    # Beak.
    ellip(735, 803, 15, 11, BEAK)
    disc(731, 800, 3, WHITE, alpha=0.8)
    # Blush.
    ellip(694, 806, 14, 9, BLUSH, alpha=0.6, aa=5)
    ellip(776, 806, 14, 9, BLUSH, alpha=0.6, aa=5)


# ------------------------------------------------------------------ render ---

def render():
    paint_background()
    paint_glow(512, 430, 520, WHITE, 0.38)

    # Soft bokeh dots.
    for (x, y, r, a) in ((150, 200, 60, 0.22), (880, 180, 45, 0.28),
                         (900, 480, 70, 0.18), (120, 550, 40, 0.20),
                         (850, 880, 55, 0.18), (180, 900, 50, 0.16)):
        disc(x, y, r, WHITE, alpha=a, aa=26)

    # Sparkles and floating hearts.
    for (x, y, s) in ((200, 130, 26), (840, 300, 20), (920, 640, 24),
                      (110, 720, 18), (640, 120, 16)):
        star(x, y, s, WHITE, alpha=0.9, aa=2.0)
    heart(150, 330, 22, NOSE, alpha=0.85)
    heart(890, 420, 18, NOSE, alpha=0.8)
    heart(700, 90, 15, (255, 178, 196), alpha=0.7)

    # Ground shadow.
    ellip(500, 905, 300, 34, (178, 118, 128), alpha=0.16, aa=18)

    # Bunny tail (a fluffy round puff at the body's side), body, belly, feet.
    disc(285, 820, 59, OUTLINE)
    disc(285, 820, 52, CREAM)
    ellip(470, 790, 202, 162, OUTLINE)
    ellip(470, 790, 195, 155, CREAM)
    ellip(470, 812, 130, 105, WHITE, alpha=0.9, aa=6)
    for fx in (385, 555):
        ellip(fx, 895, 64, 36, OUTLINE)
        ellip(fx, 895, 58, 30, CREAM)
        ellip(fx, 890, 26, 12, INNER_EAR, alpha=0.85, aa=3)

    paint_chick()

    # Ears in the tilted head frame (behind the head).
    # Left ear: upright.
    caps(-85, -160, -165, -335, 56, OUTLINE, head=True)
    caps(-85, -160, -165, -335, 49, CREAM, head=True)
    caps(-88, -185, -155, -305, 30, INNER_EAR, head=True)
    # Right ear: floppy, curving smoothly over along a Bezier.
    tube_bezier((85, -160), (135, -305), (240, -268), 54, OUTLINE, head=True)
    tube_bezier((85, -160), (135, -305), (240, -268), 47, CREAM, head=True)
    tube_bezier((85, -160), (135, -305), (240, -268), 26, INNER_EAR,
                head=True, t0=0.14, t1=0.9, n=16)

    # Head.
    disc(0, 0, 212, OUTLINE, head=True)
    disc(0, 0, 205, CREAM, head=True)

    # Face: big glossy eyes, blush, tiny nose, cat-smile mouth.
    for ex in (-78, 78):
        ellip(ex, -10, 36, 52, EYE, head=True)
        disc(ex - 11, -27, 13, WHITE, head=True)
        disc(ex + 13, 5, 6, WHITE, head=True)
    ellip(-128, 64, 44, 24, BLUSH, alpha=0.55, aa=10, head=True)
    ellip(128, 64, 44, 24, BLUSH, alpha=0.55, aa=10, head=True)
    ellip(0, 46, 17, 12, NOSE, head=True)
    disc(-5, 42, 4, WHITE, alpha=0.85, head=True)
    arc(-23, 52, 23, math.radians(20), math.radians(160), 2.75, MOUTH,
        head=True)
    arc(23, 52, 23, math.radians(20), math.radians(160), 2.75, MOUTH,
        head=True)

    # Tiny flower clipped beside the floppy ear.
    flower(108, -168, 24, PETAL, FLOWER_CENTRE, outline=PETAL_LINE, head=True)

    # Tiny ground flowers.
    flower(170, 935, 13, PETAL, FLOWER_CENTRE, outline=PETAL_LINE)
    flower(865, 930, 11, PETAL, FLOWER_CENTRE, outline=PETAL_LINE)


# ------------------------------------------------------------- PNG writer ---
# Pure-stdlib PNG encoder: 8-bit RGB, Up filter, zlib level 9. Deterministic.

def png_bytes(w, h, rgb):
    stride = w * 3
    raw = bytearray()
    prev = bytes(stride)
    for y in range(h):
        row = bytes(rgb[y * stride:(y + 1) * stride])
        if y == 0:
            raw.append(0)
            raw += row
        else:
            raw.append(2)
            raw += bytes((c - p) & 0xFF for c, p in zip(row, prev))
        prev = row
    data = zlib.compress(bytes(raw), 9)

    def chunk(typ, payload):
        out = struct.pack(">I", len(payload)) + typ + payload
        return out + struct.pack(">I", zlib.crc32(typ + payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", data) + chunk(b"IEND", b""))


def main():
    render()
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "entry.png"), "wb") as f:
        f.write(png_bytes(W, H, buf))


if __name__ == "__main__":
    main()
