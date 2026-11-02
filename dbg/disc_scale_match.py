# -*- coding: utf-8 -*-
"""Prototype: locate the disc by the tile-distance map, then match with scale
ladder restricted to the ink side."""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V

a = np.asarray(Image.open(r"D:\BuildProject\pikayu-jj\fixtures\jj_endgame1.png").convert("RGB"))
cal = V.calibrate(a, verbose=False)
tpl, half = V.load_templates(cal=cal)
n = 2 * half
cls, T0, nt = V._match_prep(tpl, half)
ref = V.tile_colour(a, cal.get("band"))

def disc_centre(x, y, win=32, half_box=16):
    """argmax of the box-mean tile-distance over a (2*win)^2 window."""
    x0, y0 = int(round(x)) - win, int(round(y)) - win
    H, W = a.shape[0], a.shape[1]
    sub = a[max(0, y0):min(H, y0 + 2 * win), max(0, x0):min(W, x0 + 2 * win)]
    if sub.size == 0:
        return x, y, 0.0
    m = V._box_mean(V.dist_map(sub, ref), half_box)
    k = int(np.argmax(m))
    dy, dx = np.unravel_index(k, m.shape)
    px = max(0, x0) + dx + half_box
    py = max(0, y0) + dy + half_box
    return float(px), float(py), float(m[dy, dx])

def match_side(cx, cy, side, scales=(1.0, 1.15, 1.30), rad=6, step=2):
    cl = [j for j, c in enumerate(cls) if (c.isupper() == (side == "w"))]
    T = T0[cl]; nt_ = nt[cl]
    best = None
    for sc in scales:
        h = int(np.ceil(half * sc))
        for dy in range(-rad, rad + 1, step):
            for dx in range(-rad, rad + 1, step):
                xi, yi = int(round(cx)) + dx, int(round(cy)) + dy
                reg = a[yi - h:yi + h, xi - xi + 0:0]  # placeholder
                if yi - h < 0 or xi - h < 0 or yi + h > a.shape[0] or xi + h > a.shape[1]:
                    continue
                reg = a[yi - h:yi + h, xi - h:xi + h]
                q = np.empty((n, n), np.float32)
                for c in range(3):
                    q[:, :] += V._resize2d(reg[:, :, c].astype(np.float32), n) / 3.0
                q = q - q.mean()
                nq = np.sqrt(float((q * q).sum()))
                s = (T @ q.ravel()) / (nq * nt_)
                k = int(np.argmax(s))
                if best is None or s[k] > best[0]:
                    best = (float(s[k]), cls[cl[k]], dx, dy, sc)
    return best

def ink_side(x, y, half_patch=None, win=32):
    h = half_patch or half
    xi, yi = int(round(x)), int(round(y))
    p = a[yi - h:yi + h, xi - h:xi + h].astype(np.float32)
    lum = p.mean(axis=2)
    yy, xx = np.mgrid[0:p.shape[0], 0:p.shape[1]]
    r = np.hypot(yy - p.shape[0] / 2.0, xx - p.shape[1] / 2.0)
    sel = (lum < 0.55 * float(np.median(lum))) & (r < 0.62 * h)
    if int(sel.sum()) < 12:
        return None, 0
    return float(np.median(p[:, :, 0][sel] - p[:, :, 2][sel])), int(sel.sum())

print("== corner (0,0): the lifted red rook ==")
mx, my = V.grid_xy(cal, 0, 0)
print("  model centre (%.1f, %.1f)" % (mx, my))
px, py, sc0 = disc_centre(mx, my)
print("  disc centre by score map: (%.1f, %.1f) score %.1f  (offset %+.1f,%+.1f)"
      % (px, py, sc0, px - mx, py - my))
s, npix = ink_side(mx, my)
print("  ink side at model centre: R-B %s n=%d -> %s" % (round(s, 1), npix, "RED" if s > 40 else "dark"))
s2, npix2 = ink_side(px, py)
print("  ink side at disc centre : R-B %s n=%d -> %s" % (round(s2, 1), npix2, "RED" if s2 > 40 else "dark"))
for side in ("w", "b"):
    print("  side %s:" % ("red" if side == "w" else "black"))
    for scales in ((1.0,), (1.0, 1.15, 1.30), (1.0, 1.1, 1.2, 1.3, 1.4)):
        b = match_side(px, py, side, scales=scales)
        print("     scales %-22s -> %s" % (str(scales), None if not b else
              "%.3f %s off(%+d,%+d) sc=%.2f" % b))

print("\n== sanity: normal pieces, side from ink, scale 1.0 only ==")
for (i, j, want) in ((8, 5, "r"), (1, 5, "c"), (3, 2, "a"), (4, 2, "b"), (4, 1, "k"),
                     (2, 8, "n"), (8, 3, "p")):
    x, y = V.grid_xy(cal, i, j)
    px, py, _ = disc_centre(x, y)
    s, npix = ink_side(x, y)
    side = "w" if (s or 0) > 40 else "b"
    b = match_side(px, py, side, scales=(1.0,))
    print("  (%d,%d) want %s ink R-B %5.1f -> %-4s  %s" % (
        i, j, want, s or -99, "RED" if side == "w" else "dark",
        "%.3f %s off(%+d,%+d)" % b if b else "none"))
print("\n== sanity: red pieces ==")
for (i, j, want) in ((4, 7, "B"), (3, 8, "C"), (4, 8, "A"), (3, 9, "K")):
    x, y = V.grid_xy(cal, i, j)
    px, py, _ = disc_centre(x, y)
    s, npix = ink_side(x, y)
    side = "w" if (s or 0) > 40 else "b"
    b = match_side(px, py, side, scales=(1.0,))
    print("  (%d,%d) want %s ink R-B %5.1f -> %-4s  %s" % (
        i, j, want, s or -99, "RED" if side == "w" else "dark",
        "%.3f %s off(%+d,%+d)" % b if b else "none"))
