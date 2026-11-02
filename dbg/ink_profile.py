# -*- coding: utf-8 -*-
"""Where does the red rim ring sit, and how separable is the glyph ink colour?"""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V

a = np.asarray(Image.open(r"D:\BuildProject\pikayu-jj\fixtures\jj_endgame1.png").convert("RGB"))
op = np.asarray(Image.open(r"D:\BuildProject\pikayu-jj\fixtures\jj_wechat1.png").convert("RGB"))
cal = V.calibrate(a, verbose=False)
calo = V.calibrate(op, verbose=False)

def prof(img, cal, i, j, dx=0, dy=0, half=46, tag=""):
    x, y = V.grid_xy(cal, i, j)
    x, y = int(round(x)) + dx, int(round(y)) + dy
    p = img[y - half:y + half, x - half:x + half].astype(np.float32)
    lum = p.mean(axis=2)
    rb = p[:, :, 0] - p[:, :, 2]
    yy, xx = np.mgrid[0:p.shape[0], 0:p.shape[1]]
    r = np.hypot(yy - half, xx - half)
    print("%-22s centre=(%d,%d)" % (tag, x, y))
    for lo in range(0, half, 4):
        sel = (r >= lo) & (r < lo + 4)
        face = sel & (lum > 150)
        dark = sel & (lum <= 150)
        f = "  face n=%4d meanRGB=(%5.0f,%5.0f,%5.0f) R-B=%+5.1f" % (
            face.sum(), *(list(p[face].mean(axis=0)) + [rb[face].mean()])) if face.sum() > 20 else "  face n<20"
        d = "  dark n=%4d meanRGB=(%5.0f,%5.0f,%5.0f) R-B=%+5.1f" % (
            dark.sum(), *(list(p[dark].mean(axis=0)) + [rb[dark].mean()])) if dark.sum() > 20 else "  dark n<20"
        print("   r%2d-%2d%s |%s" % (lo, lo + 4, f, d))

prof(a, cal, 0, 0, 2, -22, tag="endgame 俥 lifted RED")
prof(a, cal, 8, 5, 4, 0, tag="endgame 車 black")
prof(a, cal, 4, 8, 6, -3, tag="endgame 仕 red")
prof(op, calo, 0, 0, 4, 1, tag="opening 車 black")
prof(op, calo, 0, 9, 4, 1, tag="opening 俥 red")
