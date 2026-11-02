# -*- coding: utf-8 -*-
"""Wide-offset template search: how far is the true glyph from the model centre?"""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V, board as B

SRC = sys.argv[1] if len(sys.argv) > 1 else r"D:\BuildProject\pikayu-jj\fixtures\jj_endgame1.png"
a = np.asarray(Image.open(SRC).convert("RGB"))
cal = V.calibrate(a, verbose=False)
tpl, half = V.load_templates(cal=cal)
prep = V._match_prep(tpl, half)
ap = V.pad_frame(a)
RAD = 40
print("wide search rad", RAD)
for j in range(10):
    line = []
    for i in range(9):
        x, y = V.grid_xy(cal, i, j)
        r = V._match_cell(ap, x, y, prep, half, RAD)
        if r is None:
            line.append("   none   ")
            continue
        best, piece, second, dx, dy = r
        line.append(" %s %.2f(%+3d,%+3d)" % (piece, best, dx, dy))
    print("row%d " % j + "".join(line))
