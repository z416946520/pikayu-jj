# -*- coding: utf-8 -*-
"""Verify the calibration->pixel mapping used for clicking, by cropping the frame
around the computed cell centres."""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import w32, vision as V, board as B

w32.set_dpi_aware()
hwnd, _t = w32.find_window("JJ")
x0, y0, cw, ch = w32.client_rect_screen(hwnd)
a = w32.WindowGrabber().grab(hwnd)
cal = V.calibrate(a, verbose=False)
print("client origin (%d,%d) size (%d,%d)  cal cpitch=%.2f rpitch=%.2f band=%s" % (
    x0, y0, cw, ch, cal.get("cpitch") or 0, cal.get("rpitch") or 0, cal.get("band")))
print("cx[0..8]:", [round(v, 1) for v in (cal.get("cx") or [])][:9])
print("cy[0..9]:", [round(v, 1) for v in (cal.get("cy") or [])][:10])
boxes = []
for (i, j, tag) in [(6, 1, "chariot?"), (8, 1, "cannon?"), (6, 3, "horse?"),
                    (4, 9, "king?"), (2, 8, "black-chariot?"), (4, 8, "black-pawn?")]:
    gx, gy = V.grid_xy(cal, i, j)
    print("cell (%d,%d) %-14s frame (%d,%d)  screen (%d,%d)" % (
        i, j, tag, gx, gy, x0 + gx, y0 + gy))
    lo_x, lo_y = int(gx) - 34, int(gy) - 34
    patch = a[max(0, lo_y):lo_y + 68, max(0, lo_x):lo_x + 68]
    boxes.append((tag, patch))
H = max(b.shape[0] for _t, b in boxes)
row = np.concatenate([np.pad(b, ((0, H - b.shape[0]), (0, 0), (0, 0)), constant_values=40)
                      for _t, b in boxes], axis=1)
Image.fromarray(row).save(r"D:\BuildProject\pikayu-jj\logs\cellcrop.png")
print("saved logs/cellcrop.png", row.shape, "order:", [t for t, _b in boxes])
