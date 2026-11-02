# -*- coding: utf-8 -*-
"""One-shot vision pass on the recon frame: what position does the puzzle show?
(Used only to know which FEN in memory is the live one.)"""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V, board as B

a = np.asarray(Image.open(r"D:\BuildProject\pikayu-jj\logs\jj_recon.png").convert("RGB"))
print("frame", a.shape)
cal = V.calibrate(a, verbose=False)
if not cal:
    print("calibration failed")
    sys.exit(0)
print("cal kind=%s cpitch=%.2f rpitch=%.2f model=%s resid_p80=%s" % (
    cal.get("kind"), cal.get("cpitch") or 0, cal.get("rpitch") or 0,
    bool(cal.get("model")), cal.get("resid_p80")))
tpl, half = V.load_templates(cal=cal)
info = {}
scr, score = V.recognize(a, cal, tpl, half=half, info=info)
n = sum(1 for j in range(10) for i in range(9) if scr[j][i] != ".")
print("pieces", n)
for row in scr:
    print("   " + " ".join(row))
for flip in (False, True):
    g = B.screen_to_internal(scr, flip)
    print("flip=%-5s fen %s" % (flip, B.grid_to_fen(g, "w")))
