# -*- coding: utf-8 -*-
"""Measure the real disc centres (bright blob segmentation) vs the fitted model."""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V, board as B

SRC = sys.argv[1] if len(sys.argv) > 1 else r"D:\BuildProject\pikayu-jj\fixtures\jj_endgame1.png"
a = np.asarray(Image.open(SRC).convert("RGB"))
cal = V.calibrate(a, verbose=False)
lum = V.luminance(a).astype(np.float32)

# the disc face is bright cream, much brighter than tile/shade: threshold high
thr = float(np.percentile(lum, 92))
print("frame", a.shape, "thr %.1f" % thr)
mask = lum > max(200.0, thr)
# label blobs (4-neighbour flood fill, no scipy)
lab = np.zeros(mask.shape, np.int32)
blobs = []
H, W = mask.shape
from collections import deque
cur = 0
for y0 in range(H):
    xs = np.flatnonzero(mask[y0])
    for x0 in xs:
        if lab[y0, x0]:
            continue
        cur += 1
        q = deque([(y0, x0)])
        lab[y0, x0] = cur
        pix = []
        while q:
            y, x = q.popleft()
            pix.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = cur
                    q.append((yy, xx))
        if len(pix) < 400:
            continue
        ys = np.array([p[0] for p in pix], float)
        xs2 = np.array([p[1] for p in pix], float)
        blobs.append((xs2.mean(), ys.mean(), xs2.min(), xs2.max(), ys.min(), ys.max(), len(pix)))
print("blobs:", len(blobs))

tpl, half = V.load_templates(cal=cal)
grid, sc = V.recognize(a, cal, tpl, half=half)
print("grid:")
for j, row in enumerate(grid):
    print("   " + "".join(row))

for (bx, by, x0, x1, y0, y1, n) in sorted(blobs, key=lambda b: (b[1], b[0])):
    # nearest cell
    best = None
    for j in range(10):
        for i in range(9):
            mx, my = V.grid_xy(cal, i, j)
            d = np.hypot(bx - mx, by - my)
            if best is None or d < best[0]:
                best = (d, i, j, mx, my)
    d, i, j, mx, my = best
    print("blob centre (%6.1f,%6.1f) size (%dx%d) n=%d -> cell (%d,%d) '%s'  model (%6.1f,%6.1f)  delta (%+5.1f,%+5.1f)"
          % (bx, by, x1 - x0, y1 - y0, n, i, j, grid[j][i], mx, my, bx - mx, by - my))
