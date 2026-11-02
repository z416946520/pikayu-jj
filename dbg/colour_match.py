# -*- coding: utf-8 -*-
"""Colour-aware, scale-aware matching experiment for the lifted red rook."""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V

ORIG = r"D:\BuildProject\pikayu-jj\fixtures\jj_orig.png"
END = r"D:\BuildProject\pikayu-jj\fixtures\jj_endgame1.png"

orig = np.asarray(Image.open(ORIG).convert("RGB"))
calo = V.calibrate(orig, verbose=False)
end = np.asarray(Image.open(END).convert("RGB"))
cal = V.calibrate(end, verbose=False)

# -- build RGB templates from the opening frame, same centres as the pack --
half_ref = V.TPL_HALF                     # 23
apo = V.pad_frame(orig)
tplc = {}
for t, sources in V.TPL_SOURCES.items():
    for (i, j) in sources:
        x, y = V.grid_xy(calo, i, j)
        xi, yi = int(round(x)) + V.PADV, int(round(y)) + V.PADV
        p = apo[yi - half_ref:yi + half_ref, xi - half_ref:xi + half_ref].astype(np.float32)
        tplc.setdefault(t, []).append(p)
print("colour templates:", {t: len(v) for t, v in sorted(tplc.items())})

tpl, half = V.load_templates(cal=cal)          # the shipped grayscale pack, scaled
n = 2 * half
# scale the colour templates to n as well
tplc = {t: [np.stack([V._resize2d(p[:, :, c], n) for c in range(3)], -1) for p in v]
        for t, v in tplc.items()}

def redness(p):
    return (p[:, :, 0].astype(np.float32) - p[:, :, 2].astype(np.float32))

# precompute zero-mean gray rows and redness rows
rows, cls2 = [], []
for t in sorted(tplc):
    for p in tplc[t]:
        g = p.mean(axis=2)
        r = redness(p)
        rows.append((g - g.mean(), r - r.mean()))
        cls2.append(t)
G = np.stack([a.ravel() for a, _ in rows])
Rb = np.stack([b.ravel() for _, b in rows])
ng = np.sqrt((G * G).sum(1))
nr = np.sqrt((Rb * Rb).sum(1))
# the pack (grayscale only) for comparison
pcls, T0, nt = V._match_prep(tpl, half)

ape = V.pad_frame(end)

def patch_at(cx, cy, scale):
    h = int(np.ceil(half * scale))
    x0, y0 = int(round(cx)) + V.PADV - h, int(round(cy)) + V.PADV - h
    reg = ape[y0:y0 + 2 * h, x0:x0 + 2 * h]
    out = np.empty((n, n, 3), np.float32)
    for c in range(3):
        out[:, :, c] = V._resize2d(reg[:, :, c].astype(np.float32), n)
    return out

def scores(p):
    g = p.mean(axis=2)
    r = redness(p)
    g = g - g.mean(); r = r - r.mean()
    sg = (G @ g.ravel()) / (ng * np.sqrt(float((g * g).sum())) + 1e-9)
    sr = (Rb @ r.ravel()) / (nr * np.sqrt(float((r * r).sum())) + 1e-9)
    return sg, sr

def best_combined(cx, cy, scale, lam=0.6):
    sg, sr = scores(patch_at(cx, cy, scale))
    comb = sg + lam * sr
    per = {}
    for k, c in enumerate(cls2):
        v = float(comb[k])
        if v > per.get(c, -9):
            per[c] = v
    return sorted(per.items(), key=lambda kv: -kv[1])

print("\n== corner piece: search offsets and scales (combined score, lam=0.6) ==")
best = None
for sc in (1.0, 1.1, 1.2, 1.3):
    for dy in range(-30, 5, 3):
        for dx in range(-14, 15, 3):
            x, y = V.grid_xy(cal, 0, 0)
            top = best_combined(x + dx, y + dy, sc)
            if best is None or top[0][1] > best[0][0][1]:
                best = (top, dx, dy, sc)
print("best overall: %s at offset (%+d,%+d) scale %.2f" % (best[0][:4], best[1], best[2], best[3]))
print("  top red classes:", [c for c, _v in best[0] if c.isupper()][:4])
print("  top black classes:", [c for c, _v in best[0] if c.islower()][:4])

print("\n== per-scale detail at the true offset (+2,-22) ==")
for sc in (1.0, 1.1, 1.2, 1.3):
    print(" scale %.2f: %s" % (sc, best_combined(V.grid_xy(cal, 0, 0)[0] + 2,
                                                V.grid_xy(cal, 0, 0)[1] - 22, sc)[:5]))
print("\n== gray-only (pack) at the same settings, for reference ==")
for sc in (1.0, 1.2):
    sg, sr = scores(patch_at(V.grid_xy(cal, 0, 0)[0] + 2, V.grid_xy(cal, 0, 0)[1] - 22, sc))
    per = {}
    for k, c in enumerate(cls2):
        per.setdefault(c, -9)
        per[c] = max(per[c], float(sg[k]))
    print(" scale %.2f gray: %s" % (sc, sorted(per.items(), key=lambda kv: -kv[1])[:5]))

print("\n== sanity: a normal black rook (8,5) and a red advisor (4,8) ==")
for (i, j, dx, dy, want) in ((8, 5, 4, 0, "r"), (4, 8, 6, -3, "A"), (3, 9, 5, -3, "K"),
                             (1, 5, 4, 0, "c"), (3, 2, 2, 2, "a"), (4, 1, 4, 3, "k")):
    x, y = V.grid_xy(cal, i, j)
    top = best_combined(x + dx, y + dy, 1.0)
    print("  (%d,%d) want %s -> %s" % (i, j, want, top[:4]))
