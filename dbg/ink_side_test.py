# -*- coding: utf-8 -*-
"""Pick a robust ink-side measure: test candidates on every fixture disc."""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V, board as B

CASES = [
    (r"D:\BuildProject\pikayu-jj\fixtures\jj_endgame1.png", None),
    (r"D:\BuildProject\pikayu-jj\fixtures\jj_wechat1.png", None),
    (r"D:\BuildProject\pikayu-jj\fixtures\jj_orig.png", None),
]

def variants(p, half):
    """p: (2h,2h,3) float patch, disc roughly centred."""
    lum = p.mean(axis=2)
    yy, xx = np.mgrid[0:p.shape[0], 0:p.shape[1]]
    r = np.hypot(yy - p.shape[0] / 2.0, xx - p.shape[1] / 2.0)
    rb = p[:, :, 0] - p[:, :, 2]
    med = float(np.median(lum))
    out = {}
    for name, sel in (
            ("A dark<.55med", lum < 0.55 * med),
            ("B +r<.62h", (lum < 0.55 * med) & (r < 0.62 * half)),
            ("C darkest8%", lum <= np.percentile(lum, 8)),
            ("D darkest8% r<.7h", (lum <= np.percentile(lum, 8)) & (r < 0.70 * half)),
            ("E darkest15% r<.7h", (lum <= np.percentile(lum, 15)) & (r < 0.70 * half)),
    ):
        n = int(sel.sum())
        out[name] = (float(np.median(rb[sel])) if n >= 12 else None, n)
    return out

allrows = []
for path, _ in CASES:
    img = np.asarray(Image.open(path).convert("RGB"))
    cal = V.calibrate(img, verbose=False)
    tpl, half = V.load_templates(cal=cal)
    ap = V.pad_frame(img)
    # read the board to know the pieces, then measure the disc at its matched offset
    info = {}
    grid, sc = V.recognize(img, cal, tpl, half=half, info=info)
    for j in range(10):
        for i in range(9):
            ch = grid[j][i]
            if ch == ".":
                continue
            mx, my = V.grid_xy(cal, i, j)
            dx, dy = info["offsets"][j][i]
            cx, cy = int(round(mx + dx)), int(round(my + dy))
            h = half
            p = ap[cy + V.PADV - h:cy + V.PADV + h, cx + V.PADV - h:cx + V.PADV + h].astype(np.float32)
            if p.shape[0] != 2 * h:
                continue
            v = variants(p, half)
            allrows.append((path.split("\\")[-1], i, j, ch, v))

want_red = lambda ch: ch.isupper()
print("%-14s %-4s %-3s  %s" % ("frame", "cell", "ch", "  ".join("%-18s" % n for n in
      ("A dark<.55med", "B +r<.62h", "C darkest8%", "D darkest8% r<.7h", "E darkest15% r<.7h"))))
stats = {}
for f, i, j, ch, v in allrows:
    line = []
    for name, (val, n) in v.items():
        line.append("%-18s" % ("none" if val is None else "%+7.1f n=%4d" % (val, n)))
        stats.setdefault(name, ([], []))[0 if want_red(ch) else 1].append(val)
    print("%-14s (%d,%d) %-3s  %s" % (f, i, j, ch, "  ".join(line)))
print()
for name, (reds, blacks) in stats.items():
    reds = [x for x in reds if x is not None]
    blacks = [x for x in blacks if x is not None]
    print("%-18s red  min %+6.1f med %+6.1f   black max %+6.1f med %+6.1f   %s" % (
        name, min(reds), np.median(reds), max(blacks), np.median(blacks),
        "SEPARABLE" if min(reds) > max(blacks) + 20 else "overlap"))
