# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V, board as B, w32

w32.set_dpi_aware()
hwnd, _ = w32.find_window("JJ")
x, y, w, h = w32.client_rect_screen(hwnd)
a = w32.ScreenGrabber().grab(x, y, w, h)
Image.fromarray(a).save(r"D:\BuildProject\pikayu-jj\live3.png")
print("frame", a.shape, "client", x, y, w, h)

cal = V.calibrate(a, verbose=True)
tpl = V.build_templates(a, cal)
sc_map, br = V.cell_box_scores(a, cal)
grid, sc = V.recognize(a, cal, tpl)
for j in range(10):
    print("  ", "".join(grid[j]))
print("FEN", B.grid_to_fen(grid))
print("model CX", " ".join("%.3f" % v for v in cal["model"][0]))
print("model CY", " ".join("%.3f" % v for v in cal["model"][1]))

REF = B.fen_to_grid("rnbakab1r/9/1c4nc1/p1p1p1p1p/9/9/P.P.P.P.P/1C2C1N2/9/RNBAKAB1R")
ap = V.pad_frame(a)
S = V.sum_image(ap)

def bbox_center(x0, y0, win=30, thr=545.0):
    xi, yi = int(round(x0)) + V.PADV, int(round(y0)) + V.PADV
    sub = S[yi - win:yi + win + 1, xi - win:xi + win + 1] > thr
    ys, xs = np.nonzero(sub)
    if len(xs) == 0:
        return None, 0
    return (x0 - win + xs.min() + (xs.max() - xs.min()) / 2.0,
            y0 - win + ys.min() + (ys.max() - ys.min()) / 2.0), len(xs)

def ncc_all(x0, y0):
    P = V._patch_gray(ap, int(round(x0)), int(round(y0)), V.TPL_HALF, pad=V.PADV)
    out = []
    for t, lst in tpl.items():
        out.append((max(V._ncc(P, T) for T in lst), t))
    out.sort(reverse=True)
    return out

for (i, j) in [(6, 7), (4, 7), (7, 9), (6, 2), (7, 0)]:
    mx, my = V.grid_xy(cal, i, j)
    bc, n = bbox_center(mx, my)
    print()
    print("=== cell (%d,%d) expect %s got %s" % (i, j, REF[j][i], grid[j][i]))
    print("    box score at model centre %.3f" % sc_map[(i, j)])
    print("    model centre (%.1f, %.1f)" % (mx, my))
    if bc:
        print("    bright bbox centre (%.1f, %.1f)  d=(%+.1f, %+.1f)  npx %d" % (bc[0], bc[1], bc[0] - mx, bc[1] - my, n))
    print("    NCC at model centre : " + "  ".join("%s %.3f" % (t, s) for s, t in ncc_all(mx, my)[:4]))
    if bc:
        print("    NCC at bbox centre  : " + "  ".join("%s %.3f" % (t, s) for s, t in ncc_all(bc[0], bc[1])[:4]))
    x0 = int(mx) + V.PADV; y0 = int(my) + V.PADV
    crop = ap[y0 - 40:y0 + 41, x0 - 40:x0 + 41]
    big = np.repeat(np.repeat(crop, 4, 0), 4, 1)
    Image.fromarray(big).save(r"D:\BuildProject\pikayu-jj\dbg_cell_%d_%d.png" % (i, j))
