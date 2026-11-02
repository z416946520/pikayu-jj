# -*- coding: utf-8 -*-
"""Build the shipped template pack from a clean opening-position frame."""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V, board as B

SRC = r"D:\BuildProject\pikayu-jj\fixtures\jj_orig.png"
a = np.asarray(Image.open(SRC).convert("RGB"))
print("source frame", a.shape)
cal = V.calibrate(a, verbose=True)
tpl = V.build_templates(a, cal, validate=True, verbose=True)
print("classes: " + " ".join("%s x%d" % (t, len(v)) for t, v in sorted(tpl.items())))
print("total variants", sum(len(v) for v in tpl.values()))
missing = [c for c in V.TPL_SOURCES if c not in tpl]
print("missing classes", missing)
p = V.save_templates(tpl, cpitch=cal.get("cpitch"), rpitch=cal.get("rpitch"))
print("saved", p)

tpl2, half = V.load_templates(cal=cal)
print("reload: classes %d patch half %d" % (len(tpl2), half))
info = {}
grid, sc = V.recognize(a, cal, tpl2, half=half, info=info)
ex = B.fen_to_grid(B.OPENING_FEN)
ok = sum(1 for j in range(10) for i in range(9) if grid[j][i] == ex[j][i])
print("opening accuracy with pack: %d/90" % ok)
occ = [(i, j) for j in range(10) for i in range(9) if ex[j][i] != "."]
mg = info["margins"]
print("NCC min %.3f   class margin min %.3f   n=%d" % (
    min(sc[j][i] for i, j in occ), min(mg[j][i] for i, j in occ), len(occ)))
for j in range(10):
    print("   " + "".join(grid[j]))
bad = [(i, j, ex[j][i], grid[j][i]) for i, j in occ if grid[j][i] != ex[j][i]]
print("wrong:", bad)
