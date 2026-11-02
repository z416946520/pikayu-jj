# -*- coding: utf-8 -*-
"""Look at the fitted model vs the real disc near the top-left corner."""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V, board as B

SRC = sys.argv[1] if len(sys.argv) > 1 else r"D:\BuildProject\pikayu-jj\fixtures\jj_endgame1.png"
a = np.asarray(Image.open(SRC).convert("RGB"))
cal = V.calibrate(a, verbose=False)
CX, CY = cal["model"]
print("CX", ["%.4f" % v for v in CX])
print("CY", ["%.4f" % v for v in CY])
print("cx (j=4 row?)", ["%.1f" % v for v in cal["cx"]][:9])
print("cy", ["%.1f" % v for v in cal["cy"]][:10])
print("ndiscs", cal.get("ndiscs"), "used", cal.get("ndiscs_used"), "resid", cal.get("resid"))

# where does the fit put every row/col
for j in range(10):
    xs = [V.grid_xy(cal, i, j) for i in range(9)]
    print("row %d: y=%.1f  x0=%.1f x8=%.1f" % (j, xs[0][1], xs[0][0], xs[8][0]))

loc = V.locate(a, cal, win=24, half=V.BOX_HALF)
print("locate() near the corner:")
for j in range(0, 3):
    for i in range(0, 4):
        mx, my = V.grid_xy(cal, i, j)
        got = loc.get((i, j))
        if got:
            print("  (%d,%d) model (%.1f,%.1f) -> disc (%.1f,%.1f) score %.1f  delta (%.1f,%.1f)"
                  % (i, j, mx, my, got[1], got[2], got[0], got[1] - mx, got[2] - my))
        else:
            print("  (%d,%d) model (%.1f,%.1f) -> none" % (i, j, mx, my))

# annotate a zoom around the top-left corner
cx, cy = V.grid_xy(cal, 0, 0)
half = 72
y0, y1 = int(cy) - half, int(cy) + half
x0, x1 = int(cx) - half, int(cx) + half
y0, x0 = max(0, y0), max(0, x0)
crop = a[y0:y1, x0:x1].copy()
for (px, py), col in (((cx, cy), (255, 0, 0)),):
    for d in range(-8, 9):
        yy, xx = int(py) - y0 + d, int(px) - x0
        if 0 <= yy < crop.shape[0] and 0 <= xx < crop.shape[1]:
            crop[yy, xx] = col
        yy, xx = int(py) - y0, int(px) - x0 + d
        if 0 <= yy < crop.shape[0] and 0 <= xx < crop.shape[1]:
            crop[yy, xx] = col
got = loc.get((0, 0))
if got:
    px, py = got[1], got[2]
    for d in range(-10, 11):
        for (yy, xx) in ((int(py) - y0 + d, int(px) - x0 - 10), (int(py) - y0 + d, int(px) - x0 + 10),
                         (int(py) - y0 - 10, int(px) - x0 + d), (int(py) - y0 + 10, int(px) - x0 + d)):
            if 0 <= yy < crop.shape[0] and 0 <= xx < crop.shape[1]:
                crop[yy, xx] = (0, 200, 0)
print("model (0,0) = (%.1f, %.1f); locate = %s" % (cx, cy, got))
big = Image.fromarray(crop).resize(((x1 - x0) * 4, (y1 - y0) * 4), Image.NEAREST)
big.save(r"D:\BuildProject\pikayu-jj\dbg\corner_zoom.png")
print("saved dbg/corner_zoom.png  crop x0=%d y0=%d" % (x0, y0))
