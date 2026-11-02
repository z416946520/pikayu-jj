
# -*- coding: utf-8 -*-
"""The attach calibration gate: a fit must be read through its own frame.

attach() clears self.cal / self.tpl and then asks _ensure_cal(require_readable=True)
to prove the fit it just found is a chess position.  That proof ran through
self.cal / self.tpl - both still None at that moment - so recognising raised
"TypeError: 'NoneType' object is not subscriptable", the read path logged it as a
vision failure, and every attach reported "the board fit reads as no position" six
times before giving up: the user's "还是识别不到图中棋盘" on a 665x1252 board that
reads perfectly.  The gate now builds its own pack for the candidate fit
(read_candidate), and a reading whose piece counts are off is kept in reserve
instead of refused - that is a skin the stored pack matches poorly, whereas a menu
or lobby screen fails the same test on its own (it shows no generals at all).

Run:  python tools\t_gate.py     (exits non-zero on any mismatch)
"""
import os, sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import auto as A, board as B, vision as V

ROOT = r"D:\BuildProject\pikayu-jj"
FIX = ROOT + r"\fixtures"
OPEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR"
MIRROR = "RNBAKABNR/9/1C5C1/P1P1P1P1P/9/9/p1p1p1p1p/1c5c1/9/rnbakabnr"
RESULT = "rC1k1a3/4a4/b5R2/p1p1p1n1p/9/2P3C2/P1c1P1P1P/2N1B3N/9/r2RKAB2"
LOGS = []
BAD = []

A._SINK[0] = LOGS.append


def frame(name):
    return np.asarray(Image.open(os.path.join(FIX, name)).convert("RGB"))


def logged(needle):
    return any(needle in s for s in LOGS)


def check(name, got, want):
    ok = (got == want)
    if not ok:
        BAD.append(name)
    print("%-46s %-4s %r" % (name, "ok" if ok else "FAIL", got))
    if not ok:
        print("%-46s want %r" % ("", want))
    return ok


def pieces(g):
    return sum(1 for row in g for c in row if c != ".")


def gate(name, tries=1):
    """Run the attach gate on one fixture -> (player, frame or None)."""
    img = frame(name)
    p = A.AutoPlayer(our_side="w", verbose=False)
    p.frame = lambda: img
    del LOGS[:]
    got = p._ensure_cal(tries=tries, gap=0.0, require_readable=True)
    return p, got


def board_case(name, want_fen, want_pieces):
    p, a = gate(name)
    check(name + ": attach gate accepts", a is not None, True)
    if a is None:
        return
    check(name + ": fit adopted", p.cal is not None, True)
    check(name + ": pack left for reload", p.tpl, None)
    p._adopt_templates(a)
    g = p._recognize(a)
    check(name + ": pieces", None if g is None else pieces(g), want_pieces)
    if want_fen is not None:
        got = None if g is None else B.grid_to_fen(g, "w").split(" ")[0]
        check(name + ": fen", got, want_fen)


def menu_case(name):
    p, a = gate(name)
    check(name + ": attach gate refuses", a is not None, False)
    check(name + ": reported as no position", logged("reads as no position"), True)
    img = frame(name)
    cal = V.calibrate(img, verbose=False)
    g = p.read_candidate(img, cal) if cal else None
    check(name + ": reading is not a board",
          g is not None and p.board_like(g), False)


print("-- the board the user reported (665x1252, opening position)")
board_case("jj_wechat1.png", OPEN, 32)

print("-- other boards: opening, stylised skins, the finished position")
board_case("jj_orig.png", OPEN, 32)
board_case("skin_now.png", OPEN, 32)
board_case("user_shot.png", MIRROR, 32)
board_case("live_check.png", RESULT, 27)
board_case("live_now2.png", None, 23)

print("-- a skin the stored pack matches poorly")
p, a = gate("skin2_now.png")
check("skin2_now: attach gate keeps it", a is not None, True)
if a is not None:
    img = frame("skin2_now.png")
    g = p.read_candidate(img, p.cal)
    # This blue-grey board used to read as a board whose counts were off, so the
    # gate held it in reserve.  The colour/disc retry reads the squares the sharp
    # matcher cannot explain (its red back rank comes back as 1RBAKA2R), and a
    # position whose counts are on is a plain position - the reserve path is
    # exercised on its own right below.
    check("skin2_now: the read is a whole position",
          (g is not None and p.board_like(g), p.plausible(g)), (True, True))

print("-- the reserve path itself: a fit whose frame reads a poor board is kept")
_real_rec = V.recognize
_bad = B.fen_to_grid(B.OPENING_FEN)
_bad[6][0] = "."                    # two pawns short ...
_bad[6][2] = "."
_bad[7][4] = "C"                    # ... and a third red cannon: counts off, army sized
V.recognize = lambda a, cal, tpl, **kw: ([r[:] for r in _bad], [[0.0] * 9] * 10)
try:
    p, a = gate("skin_now.png")
    check("a poor read is still kept in reserve", a is not None, True)
    check("...and says so in the log", logged("kept in reserve"), True)
finally:
    V.recognize = _real_rec

print("-- menu / lobby / result screens stay refused")
menu_case("lobby_now.png")
menu_case("live10.png")

print("-- the bug itself: the gate must not read through the player's state")
p = A.AutoPlayer(our_side="w", verbose=False)
img = frame("jj_wechat1.png")
check("fresh player: cal and pack are empty", (p.cal, p.tpl), (None, None))
cal = V.calibrate(img, verbose=False)
check("read_candidate works with empty state", p.read_candidate(img, cal) is not None, True)
check("readable_frame works with empty state", p.readable_frame(img, cal), True)
del LOGS[:]
check("_recognize guards a missing fit", p._recognize(img), None)
check("_recognize logs no read failure", logged("recognition failed"), False)
check("no TypeError anywhere in this run", logged("NoneType"), False)

print("")
if BAD:
    print("GATE FAILED: " + ", ".join(BAD))
    sys.exit(1)
print("GATE OK")
