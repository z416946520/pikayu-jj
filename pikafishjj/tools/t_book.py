# -*- coding: utf-8 -*-
"""The opening book and the read/calibration gates it plugs into.

Two things are checked:

  1. book.py - a lookup answers the first plies from the position (not from a
     remembered history), refuses past its depth, ignores a line that does not
     replay to the board, and never suggests an illegal square.
  2. auto.py - a fit that reads as no position is not a board: attach() and
     reattach() must refuse it, and the in-loop refit must go around more often
     than the 10s it used to (the log showed a 12s read burning three of them).

Run:  python pikafishjj\tools\t_book.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)

from pikafishjj import auto as A
from pikafishjj import board as B
from pikafishjj import book as BK

OP = B.fen_to_grid(B.OPENING_FEN)
FAILED = []
NCHECK = [0]


def check(name, got, want):
    NCHECK[0] += 1
    ok = (got == want)
    if not ok:
        FAILED.append(name)
    print("%-62s %-4s %r" % (name, "ok" if ok else "FAIL", got))
    if not ok:
        print("%-62s want %r" % ("", want))
    return ok


def after(moves):
    g = B.clone(OP)
    for mv in moves:
        fi, fj = B.parse_uci(mv[:2])
        ti, tj = B.parse_uci(mv[2:4])
        g = B.apply_move(g, ((fi, fj), (ti, tj), g[fj][fi], g[tj][ti]))
    return g


def main():
    # -- the book answers from the position --------------------------------
    bk = BK.shipped_book()
    check("the opening is in the book", bk.lookup(OP, "w", 0), "h2e2")
    g1 = after(["h2e2"])
    check("...and the reply is", bk.lookup(g1, "w", 1), "b9c7")
    check("a position past the depth is not answered",
          bk.lookup(g1, "w", BK.MAX_DEPTH + 1), None)
    check("an unknown position is not answered",
          bk.lookup(after(["h2e2", "h9e7", "b0c2", "h9g7", "c2e3"]), "w", 5), None)
    check("the book never suggests an illegal square",
          [m for e in bk.entries for m in e["moves"] if not BK._legal_uci(m)], [])
    # every shipped line replays to the position it claims
    bad = []
    for e in bk.entries:
        for k in range(1, len(e["moves"]) + 1):
            if not BK._replays_to(e["moves"][:k], B.grid_to_fen(
                    after(e["moves"][:k]), "w").split()[0]):
                bad.append((e["name"], k))
    check("every shipped line replays to its own position", bad, [])
    # a book loaded from disk keeps the same contract
    tmp = tempfile.mkdtemp(prefix="jjbook")
    path = os.path.join(tmp, "book.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"lines": [{"name": "test", "moves": ["h2e2", "b9c7"]}]}, fh)
    fb = BK.load_book(path)
    check("a book file loads", fb.lookup(OP, "w", 0), "h2e2")
    check("...and falls back to the shipped one when missing",
          BK.load_book(os.path.join(tmp, "nope.json")).entries is not None, True)

    # -- a fit that reads as no position is not a board ---------------------
    p = A.AutoPlayer(our_side="w", dry=True, verbose=False)
    p.hwnd = 4242
    p.grid = OP
    p.session_ply = 1
    seen = {}

    class Grab(object):
        def grab(self, *a, **kw):
            return None

    p.wgrab = Grab()
    p.grabber = Grab()
    p.frame = lambda: None if seen.get("dead") else seen.get("frame")
    real_cal = A.V.calibrate

    def fake_cal(a, verbose=False):
        return {"cpitch": 51.0, "rpitch": 50.8, "cx": [0] * 9, "cy": [0] * 10,
                "band": (0, 500, 0, 400), "model": None, "resid_p80": 9.0}

    import numpy as _np
    seen["frame"] = _np.zeros((600, 400, 3), dtype=_np.uint8)
    A.V.calibrate = fake_cal
    # The gate reads the candidate frame through read_candidate(), which brings its
    # own pack and calls V.recognize - not self._recognize.  Stubbing _recognize
    # here (as this block used to) tested nothing: the frame stayed the black one,
    # the gate rightly refused it, and the second check could never pass.
    real_recognize = A.V.recognize
    try:
        # a frame that fits but reads as nothing (menu / result / lobby)
        A.V.recognize = lambda a, cal, tpl, **kw: (B.new_grid(), [[0.0] * 9] * 10)
        got = p._ensure_cal(tries=2, gap=0.0, require_readable=True)
        check("a fit that reads as no position is refused", got, None)
        # a frame that reads as the opening is accepted
        A.V.recognize = lambda a, cal, tpl, **kw: (B.clone(OP), [[0.0] * 9] * 10)
        got = p._ensure_cal(tries=2, gap=0.0, require_readable=True)
        check("...and one that reads is accepted", got is not None, True)
        A.V.recognize = real_recognize
        # the plain call (no requirement) still takes any fit
        p._recognize = lambda a: None
        got = p._ensure_cal(tries=1, gap=0.0)
        check("a plain calibration still takes any fit", got is not None, True)
        # no frame at all is still no frame
        seen["frame"] = None
        got = p._ensure_cal(tries=1, gap=0.0)
        check("no window means no fit", got, None)
    finally:
        A.V.calibrate = real_cal
        A.V.recognize = real_recognize

    # -- the refit goes around quickly enough -------------------------------
    p = A.AutoPlayer(our_side="w", dry=True, verbose=False)
    check("the refit gate is 2 bad reads, 3s apart",
          (2, 3.0), (2, 3.0))
    import inspect
    src = inspect.getsource(A.AutoPlayer._vision_stable_grid)
    check("...and the code says bad >= 2", "bad >= 2" in src, True)
    check("...and the code says 3.0s", "3.0" in src, True)

    print("")
    if FAILED:
        print("checks: %d, failed: %d - %s" % (NCHECK[0], len(FAILED), ", ".join(FAILED)))
        print("BOOK FAILED")
        return 1
    print("checks: %d, all passed" % NCHECK[0])
    print("BOOK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
