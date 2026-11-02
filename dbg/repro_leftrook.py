# -*- coding: utf-8 -*-
"""Reproduce the top-left red rook misread on the jj_wechat1 frame."""
import sys, os
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V, board as B

SRC = sys.argv[1] if len(sys.argv) > 1 else r"D:\BuildProject\pikayu-jj\fixtures\jj_wechat1.png"
a = np.asarray(Image.open(SRC).convert("RGB"))
print("frame", a.shape)

cal = V.calibrate(a, verbose=False)
print("cal rc=%s cpitch=%s rpitch=%s discs=%s resid=%s" % (
    cal.get("ref_c"), cal.get("cpitch"), cal.get("rpitch"), cal.get("ndiscs"), cal.get("resid")))

tpl, half = V.load_templates(cal=cal)
print("pack classes:", {t: len(v) for t, v in sorted(tpl.items())}, "half", half)
print("meta:", np.load(V.find_templates())["_meta"])

info = {}
grid, sc = V.recognize(a, cal, tpl, half=half, info=info)
print("read FEN:", B.grid_to_fen(grid, "w"))
for j, row in enumerate(grid):
    print("  row%d  %s" % (j, " ".join(row)))

# score the top-left cell against every template class explicitly
prep = V._match_prep(tpl, half)
ap = V.pad_frame(a)
x, y = V.grid_xy(cal, 0, 0)
print("cell (0,0) centre = (%.1f, %.1f)" % (x, y))
r = V._match_cell(ap, x, y, prep, half, V.MATCH_RAD)
print("sharp best:", None if r is None else ("%.3f %s second=%.3f off=(%d,%d)" % r))
r2 = V._match_cell(ap, x, y, prep, half, V.WIDE_RAD)
print("wide  best:", None if r2 is None else ("%.3f %s second=%.3f off=(%d,%d)" % r2))
cprep = V._match_prep_coarse(tpl, half)
cr = V._match_coarse(ap, x, y, cprep, half, r[3], r[4]) if r else None
print("coarse best:", None if cr is None else ("%.3f %s second=%.3f off=(%d,%d)" % cr))

# per-class best score at the winning offset
cls, T0, nt = prep
best_off = (r2[3], r2[4]) if r2 else (0, 0)
n = 2 * half
cx, cy = x + best_off[0], y + best_off[1]
x0 = int(round(cx)) + V.PADV - half
y0 = int(round(cy)) + V.PADV - half
patch = ap[y0:y0 + n, x0:x0 + n].astype(np.float32).mean(axis=2)
p = patch - patch.mean()
scores = {}
for c, T in zip(cls, T0):
    t = T.reshape(n, n)
    tt = t - t.mean()
    d = np.sqrt(float((p * p).sum()) * float((tt * tt).sum()))
    s = float((p * tt).sum() / d) if d > 1e-9 else -1.0
    scores.setdefault(c, []).append(s)
for c in sorted(scores):
    print("   %s  %s" % (c, " ".join("%.3f" % v for v in scores[c])))

# dump the cell patch and the top-left templates for the eye
out = np.clip(patch, 0, 255).astype(np.uint8)
Image.fromarray(out).resize((n * 6, n * 6), Image.NEAREST).save(
    r"D:\BuildProject\pikayu-jj\dbg\cell_00.png")
strip = []
for c in ("r", "R", "p", "A", "a", "P"):
    for T in tpl.get(c, []):
        t = np.clip(np.asarray(T), 0, 255).astype(np.uint8)
        strip.append(np.pad(t, 2, constant_values=255))
if strip:
    w = sum(s.shape[1] + 4 for s in strip)
    h = max(s.shape[0] for s in strip)
    canvas = np.full((h, w), 255, np.uint8)
    xx = 0
    for s in strip:
        canvas[:s.shape[0], xx:xx + s.shape[1]] = s
        xx += s.shape[1] + 4
    Image.fromarray(canvas).resize((w * 4, h * 4), Image.NEAREST).save(
        r"D:\BuildProject\pikayu-jj\dbg\tpl_strip.png")
print("saved dbg/cell_00.png dbg/tpl_strip.png")
