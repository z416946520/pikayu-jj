# -*- coding: utf-8 -*-
"""Side-by-side: the corner disc vs a normal disc vs the R/r templates."""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V

SRC = sys.argv[1] if len(sys.argv) > 1 else r"D:\BuildProject\pikayu-jj\fixtures\jj_endgame1.png"
a = np.asarray(Image.open(SRC).convert("RGB"))
cal = V.calibrate(a, verbose=False)
tpl, half = V.load_templates(cal=cal)

def crop(x, y, h=52):
    return a[max(0, int(y) - h):int(y) + h, max(0, int(x) - h):int(x) + h]

panels = [("corner(0,0) model", crop(*V.grid_xy(cal, 0, 0))),
          ("corner disc +0,-22", crop(V.grid_xy(cal, 0, 0)[0] + 2, V.grid_xy(cal, 0, 0)[1] - 22)),
          ("rook(8,5) black", crop(*V.grid_xy(cal, 8, 5))),
          ("king(3,9) red", crop(*V.grid_xy(cal, 3, 9)))]
for t in ("R", "r"):
    for k, T in enumerate(tpl.get(t, [])[:2]):
        panels.append(("tpl %s#%d" % (t, k), np.clip(np.asarray(T), 0, 255).astype(np.uint8)))

h = max(p.shape[0] for _, p in panels)
w = sum(p.shape[1] + 6 for _, p in panels)
canvas = np.full((h + 18, w, 3), 40, np.uint8)
x = 0
from PIL import ImageDraw
for name, p in panels:
    if p.ndim == 2:
        p = np.stack([p] * 3, -1)
    canvas[18:18 + p.shape[0], x:x + p.shape[1]] = p
    x += p.shape[1] + 6
im = Image.fromarray(canvas).resize((w * 3, (h + 18) * 3), Image.NEAREST)
im.save(r"D:\BuildProject\pikayu-jj\dbg\disc_compare.png")
print("order:", [n for n, _ in panels])
print("saved dbg/disc_compare.png")
