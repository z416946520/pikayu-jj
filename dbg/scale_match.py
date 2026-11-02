# -*- coding: utf-8 -*-
"""Offline experiment: disc-centred, scale-aware, colour-aware matching."""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V

SRC = sys.argv[1] if len(sys.argv) > 1 else r"D:\BuildProject\pikayu-jj\fixtures\jj_endgame1.png"
a = np.asarray(Image.open(SRC).convert("RGB"))
cal = V.calibrate(a, verbose=False)
tpl, half = V.load_templates(cal=cal)
n = 2 * half
ap = V.pad_frame(a)

def ink_side(patch):
    """mean (R-B) over the dark-ink pixels inside the middle of the patch."""
    lum = patch.mean(axis=2)
    yy, xx = np.mgrid[0:patch.shape[0], 0:patch.shape[1]]
    r = np.hypot(yy - patch.shape[0] / 2.0, xx - patch.shape[1] / 2.0)
    sel = (lum < 150) & (r < 0.34 * patch.shape[0])
    if sel.sum() < 20:
        return None, 0
    d = patch[:, :, 0].astype(float) - patch[:, :, 2].astype(float)
    return float(d[sel].mean()), int(sel.sum())

# templates as gray rows (already zero-meaned in prep); add per-class bookkeeping
cls, T0, nt = V._match_prep(tpl, half)

def match_at(cx, cy, scale=1.0, rad=4):
    """Crop at (cx,cy) with a scale-adjusted half, resize back, NCC vs all templates."""
    h = half * scale
    x0 = int(round(cx)) + V.PADV - int(np.ceil(h))
    y0 = int(round(cy)) + V.PADV - int(np.ceil(h))
    size = int(np.ceil(2 * h))
    if x0 < 0 or y0 < 0:
        return None
    reg = ap[y0:y0 + size, x0:x0 + size].astype(np.float32).mean(axis=2)
    q = V._resize2d(reg, n)
    q = q - q.mean()
    nt_ = np.sqrt(float((q * q).sum()))
    s = (T0 @ q.ravel()) / (nt_ * nt)
    k = int(np.argmax(s))
    # best per class
    per = {}
    for j, c in enumerate(cls):
        if s[j] > per.get(c, -2):
            per[c] = float(s[j])
    order = sorted(per.items(), key=lambda kv: -kv[1])[:4]
    return [(c, round(v, 3)) for c, v in order]

# --- the corner piece: true disc centre ~ (40, 307) ---
for (cx, cy, tag) in ((40.0, 307.0, "true disc centre"), (37.9, 329.5, "model centre")):
    patch = a[max(0, int(cy) - 46):int(cy) + 46, max(0, int(cx) - 46):int(cx) + 46]
    side, npx = ink_side(patch)
    print("%s (%.0f,%.0f): ink (R-B) = %s over %d px -> %s" % (
        tag, cx, cy, None if side is None else round(side, 1), npx,
        "RED" if (side or 0) > 30 else "dark"))
    for sc in (1.0, 1.1, 1.2, 1.3):
        print("   scale %.2f -> %s" % (sc, match_at(cx, cy, sc)))

# --- reference: every real piece, at its true position ---
print()
for (i, j, dx, dy, want) in [(8, 5, 4, 0, "r"), (4, 8, 6, -3, "A"), (3, 9, 5, -3, "K"),
                             (4, 7, 5, -5, "B"), (2, 8, 1, 0, "n"), (3, 8, 4, 1, "C"),
                             (1, 5, 4, 0, "c"), (4, 2, 3, 2, "b"), (3, 2, 2, 2, "a"),
                             (4, 1, 4, 3, "k")]:
    x, y = V.grid_xy(cal, i, j)
    cx, cy = x + dx, y + dy
    patch = a[int(cy) - 46:int(cy) + 46, int(cx) - 46:int(cx) + 46]
    side, npx = ink_side(patch)
    print("(%d,%d) want %s  ink R-B %5.1f -> %-4s  scale1.0 %s  scale1.2 %s" % (
        i, j, want, side or -99, "RED" if (side or 0) > 30 else "dark",
        match_at(cx, cy, 1.0), match_at(cx, cy, 1.2)))
