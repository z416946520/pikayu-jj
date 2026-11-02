
# -*- coding: utf-8 -*-
"""Calibration regression: the opening fixture, the live window, and the screens
between rounds.

The lobby is a calibration that must come back without a board - it used to raise
IndexError inside the comb lattice, which turned every retry into an error line
while the GUI kept the old preview.  calibrate() returns the best (model-less)
reading in that case, so "no board" means: no exception and cal["model"] is None.

The result screen is different: the finished position is still painted on the
board, so it must read as that position.  It was the board that failed before -
the lattice rows were anchored on a hard-coded board centre, and the result
banner shifts the whole board up, dropping every row by three ranks (the user's
"整体往下一排").  The FEN below is that final position, checked cell by cell
against logs/live_check_cells.png.

Run:  python tools\t_regress.py     (exits non-zero on any crash or mismatch)
"""
import sys, time
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V, board as B, w32

ROOT = r"D:\BuildProject\pikayu-jj"
FIX = ROOT + r"\fixtures"
OPEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR"
# A stylised skin: porcelain glyphs on a translucent blue board with a moving
# backdrop.  The sharp matcher names 30 of its 32 pieces - the two red horses 傌
# only resolve through the structure-level (blurred) fallback inside recognize().
BLUE = "RNBAKABNR/9/1C5C1/P1P1P3P/6P2/9/p1p1p1p1p/1c5c1/9/rnbakabnr"
BAD = []


def report(tag, a, expect=None):
    """expect: a FEN, 'board', 'none' (no board) or None (anything goes)."""
    t0 = time.perf_counter()
    try:
        cal = V.calibrate(a)
    except Exception as exc:
        print("%-9s CRASHED %s: %s" % (tag, type(exc).__name__, exc))
        BAD.append(tag + ":crash")
        return None
    dt = time.perf_counter() - t0
    m = None if cal is None else cal.get("model")
    if cal is not None:
        print("%-9s cal %.3fs lattice %s discs %d used %s resid %s model_dev %s" % (
            tag, dt, cal.get("lattice"), cal.get("ndiscs"), cal.get("ndiscs_used"),
            cal.get("resid"), None if cal.get("model_dev") is None else round(cal["model_dev"], 2)))
    if not m:
        print("%-9s no board found (menu / result screen?)" % tag)
        if expect not in (None, "none"):
            BAD.append(tag + ":no-board")
        return cal
    if expect == "none":
        print("%-9s found a board, wanted none" % tag)
        BAD.append(tag + ":unexpected-board")
    print("          model CX " + " ".join("%.3f" % v for v in m[0]) +
          " | CY " + " ".join("%.3f" % v for v in m[1]))
    tpl, half = V.load_templates(cal=cal)
    t0 = time.perf_counter()
    g, sc = V.recognize(a, cal, tpl, half=half)
    print("          recognise %.4fs  FEN %s" % (time.perf_counter() - t0, B.grid_to_fen(g)))
    if isinstance(expect, str) and expect not in ("board", "none"):
        ex = B.fen_to_grid(expect)
        bad = [(i, j, ex[j][i], g[j][i]) for j in range(10) for i in range(9) if ex[j][i] != g[j][i]]
        occ = [sc[j][i] for j in range(10) for i in range(9) if g[j][i] != "."]
        print("          accuracy %d/90  wrong %s  ncc min %.3f" % (
            90 - len(bad), bad[:5], min(occ) if occ else -1))
        if bad:
            BAD.append(tag + ":accuracy")
    return cal


report("opening", np.asarray(Image.open(FIX + r"\jj_orig.png").convert("RGB")), OPEN)
report("lobby", np.asarray(Image.open(FIX + r"\lobby_now.png").convert("RGB")), "none")
RESULT = "rC1k1a3/4a4/b5R2/p1p1p1n1p/9/2P3C2/P1c1P1P1P/2N1B3N/9/r2RKAB2"
report("result", np.asarray(Image.open(FIX + r"\live_check.png").convert("RGB")), RESULT)
report("user", np.asarray(Image.open(FIX + r"\user_shot.png").convert("RGB")), "board")
report("blue", np.asarray(Image.open(FIX + r"\blue_now.png").convert("RGB")), BLUE)

w32.set_dpi_aware()
# The live branch is a bonus: with the game closed (or minimised) it simply has
# nothing to read, which must not turn a green regression run into a crash.
live = None
hwnd, _t = w32.find_window("JJ")
if hwnd:
    x, y, w, h = w32.client_rect_screen(hwnd)
    # PrintWindow renders the window even while another window covers it, so this
    # does not depend on the game being on top.
    live = w32.WindowGrabber().grab(hwnd)
    if live is None:
        live = w32.ScreenGrabber().grab(x, y, w, h)
if live is None:
    print("live      skipped - the game window is not readable right now")
else:
    Image.fromarray(live).save(FIX + r"\live10.png")
    report("live", live)

print("")
if BAD:
    print("REGRESS FAILED: %s" % ", ".join(BAD))
    raise SystemExit(1)
print("REGRESS OK")
