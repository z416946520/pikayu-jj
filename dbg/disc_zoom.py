# -*- coding: utf-8 -*-
"""Zoom a few discs 6x to compare ink colour, glyph and size."""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V

frames = [("endgame", r"D:\BuildProject\pikayu-jj\fixtures\jj_endgame1.png"),
          ("opening", r"D:\BuildProject\pikayu-jj\fixtures\jj_wechat1.png")]
imgs = {}
cals = {}
for name, p in frames:
    a = np.asarray(Image.open(p).convert("RGB"))
    imgs[name] = a
    cals[name] = V.calibrate(a, verbose=False)

targets = [("endgame", 0, 0, 2, -22),      # the corner piece, corrected offset
           ("opening", 0, 0, 4, 1),        # same square, black rook on the tile
           ("endgame", 8, 5, 4, 0),        # black rook mid-board
           ("endgame", 4, 8, 6, -3),       # red advisor
           ("endgame", 3, 9, 5, -3)]       # red king
h = 46
tiles = []
for (fname, i, j, dx, dy) in targets:
    cal = cals[fname]
    x, y = V.grid_xy(cal, i, j)
    x, y = int(x) + dx, int(y) + dy
    c = imgs[fname][max(0, y - h):y + h, max(0, x - h):x + h]
    tiles.append(c)

canvas = np.full((2 * h, len(tiles) * (2 * h + 8), 3), 30, np.uint8)
x = 0
for t in tiles:
    canvas[:t.shape[0], x:x + t.shape[1]] = t
    x += t.shape[1] + 8
im = Image.fromarray(canvas).resize((canvas.shape[1] * 3, canvas.shape[0] * 3), Image.LANCZOS)
im.save(r"D:\BuildProject\pikayu-jj\dbg\disc_zoom.png")
print("order:", [t[:3] for t in targets])

# ink colour stats: dark pixels inside each tile
for (fname, i, j, dx, dy), t in zip(targets, tiles):
    lum = t.astype(np.float32).mean(axis=2)
    ink = t[lum < np.percentile(lum, 6)]
    print("%-9s (%d,%d) dark-ink mean RGB = %s  (n=%d)" % (
        fname, i, j, np.round(ink.mean(axis=0), 1), len(ink)))
    red = ((t[:, :, 0].astype(int) - t[:, :, 2].astype(int)) > 40)
    print("            reddish pixels %d, mean colour %s" % (
        int(red.sum()), np.round(t[red].mean(axis=0), 1) if red.any() else None))
print("saved dbg/disc_zoom.png")
