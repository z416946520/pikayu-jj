# -*- coding: utf-8 -*-
"""The 再来一局 restart, driven through the run loop's own helpers.

Reproduces the field report of 2026-10-12 ("点击再来一局，之后新对局报错"): ranked
play swaps colours, so the round that follows our own 再来一局 arrives rotated
180 degrees and is read with the finished game's orientation.  Every cell then
differs and the wait used to reject the board as an "implausible jump", which is
the wall of text the user saw, and the loop never adopted the round.

Nothing here needs a game window: the frame source and V.recognize are stubbed,
everything else (wait_next_round, handle_continue, wait_change, set_grid,
start_new_game) is the real code.

Run:  python pikafishjj\tools\t_rematch.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)

import numpy as np

from pikafishjj import auto as A
from pikafishjj import board as B
from pikafishjj import vision as V

OP = B.fen_to_grid(B.OPENING_FEN)
# the position the round ended in; red was at the bottom, so flip was False
FINISHED = B.fen_to_grid(
    "r1bakabnr/9/1cn2c3/p1p1p1p1p/9/2P6/P3P1P1P/1CN2C3/9/R1BAKABNR w - - 0 1")
# the round that follows: the app draws our army at the top now
NEW_ROUND = B.apply_move(B.clone(OP), ((7, 7), (4, 7), OP[7][7], OP[7][4]))
SCR_FINISHED = B.screen_to_internal(FINISHED, False)
SCR_NEW = B.screen_to_internal(NEW_ROUND, True)
# what the new round looks like while it is still read with the old flip
MIRROR_NEW = B.screen_to_internal(SCR_NEW, False)

LOGS = []
FAILED = []
NCHECK = [0]
STAGE = {"v": 0}
CLICKS = []
MARK = 100


def check(name, got, want):
    NCHECK[0] += 1
    ok = (got == want)
    if not ok:
        FAILED.append(name)
    print("%-54s %-4s %r" % (name, "ok" if ok else "FAIL", got))
    if not ok:
        print("%-54s want %r" % ("", want))
    return ok


def logged(needle):
    return any(needle in s for s in LOGS)


def frame_for(stage):
    """A fake client frame: stage 0 = result screen, 1 = the new round."""
    a = np.zeros((800, 400, 3), dtype=np.uint8)
    a[:, :] = (44, 32, 64)
    if stage == 0:
        # the green 再来一局 capsule, at the place the real detector looks for it
        a[int(0.90 * 800):int(0.95 * 800), int(0.30 * 400):int(0.70 * 400)] = \
            (150, 169, 69)
    a[0, 0, 0] = MARK + stage        # stage marker, outside every detector
    return a


def fake_recognize(a, cal, tpl, **kw):
    """V.recognize for the fake frames: the result screen is not a chess board."""
    info = kw.get("info")
    if info is not None:
        info["hints"] = {}
    if int(a[0, 0, 0]) - MARK == 0:
        raise ValueError("no board on the result screen")
    return SCR_NEW, 1.0


def new_player():
    p = A.AutoPlayer(our_side="auto", auto_next=True, verbose=True)
    p.our_side = "w"                 # what attach() derived while flip was False
    p.grid = FINISHED
    p.session_ply = 12
    p.flip = False
    p.scr = SCR_FINISHED
    # A player that is mid-run has already attached, and _recognize reports "no
    # board" without a fit and a pack (auto.py _recognize).  V.recognize is
    # stubbed below, so the values only have to be present, not real.
    p.cal = {"cpitch": 65.0, "rpitch": 62.0}
    p.tpl = {"stub": True}
    p.frame = lambda: frame_for(STAGE["v"])

    def click(x, y):
        CLICKS.append((x, y))
        STAGE["v"] = 1               # the app starts the new round

    p.click_point = click
    return p


def main():
    A.log = lambda *a: LOGS.append(" ".join(str(x) for x in a))
    real_recognize = V.recognize
    V.recognize = fake_recognize
    try:
        # -- 1. the result screen, the press, the mirrored round -------------
        del LOGS[:]
        del CLICKS[:]
        STAGE["v"] = 0
        p = new_player()
        t0 = time.time()
        g, a = p.wait_next_round(timeout=8.0)
        check("the new board was picked up", g is not None, True)
        check("...after the rematch button was pressed", p.stats["rematch"] >= 1, True)
        check("...which took a click", len(CLICKS) >= 1, True)
        check("...once the screen came back", g, MIRROR_NEW)
        check("...and it is a believable position", p.plausible(g), True)
        check("waiting for a round cost %.1fs" % (time.time() - t0), True, True)

        r = p.set_grid(g)
        check("set_grid adopts it as the new round", r, "new")
        check("orientation taken from the frame", p.flip, True)
        check("the side is automatic", p.side_auto, True)
        check("we play black now", p.our_side, "b")
        check("the canonical board is stored", p.grid, NEW_ROUND)
        check("rounds counted", p.stats["games"], 2)
        check("session reset", p.session_ply, 0)
        check("the rematch window is closed", p.waiting_new_round(), False)
        check("the swap was reported", logged("the colours were swapped"), True)
        check("the trigger is named", logged("the 再来一局 button was pressed"), True)
        check("nothing was called a jump that is not a series of moves",
              any("not a series of moves" in s for s in LOGS), False)

        # -- 2. the same board inside wait_change: adopted, not complained about
        del LOGS[:]
        p2 = new_player()
        p2._rematch_t = time.time()
        p2.handle_dialog = lambda a: False
        p2.stable_grid = lambda timeout=8.0, need=3, interval=0.03: (MIRROR_NEW, "frame")
        g2, _a2 = p2.wait_change(FINISHED, timeout=2.0, strict=True)
        check("wait_change hands the mirrored round over", g2, MIRROR_NEW)
        check("...and says why", logged("the board changed after 再来一局 was pressed"), True)
        check("...without the jump complaint",
              any("not a series of moves" in s for s in LOGS), False)

        # -- 3. without our own press the very same board is still rejected ----
        del LOGS[:]
        p3 = new_player()
        p3._rematch_t = 0.0
        p3.handle_dialog = lambda a: False
        p3.stable_grid = lambda timeout=8.0, need=3, interval=0.03: (MIRROR_NEW, "frame")
        t0 = time.time()
        g3, _a3 = p3.wait_change(FINISHED, timeout=1.0, strict=True)
        check("an unexplained board is held back as a fallback", g3, MIRROR_NEW)
        jump = [s for s in LOGS if "not a series of moves" in s]
        check("...and the change is reported", bool(jump), True)
        if jump:
            check("...with the number of cells", "cell change" in jump[0], True)
            check("...truncated to a readable line",
                  ("more)" in jump[0], len(jump[0]) < 300), (True, True))
        check("...after holding it for about a second",
              (time.time() - t0) >= 0.8, True)

        # -- 4. the result screen itself is never a new round ------------------
        p4 = A.AutoPlayer(our_side="w", auto_next=True)
        p4.grid = FINISHED
        p4.session_ply = 12
        p4.scr = SCR_FINISHED
        p4._rematch_t = time.time()
        check("the finished board is not a new round", p4.set_grid(FINISHED), None)
        check("...and the press is still pending", p4.waiting_new_round(), True)
    finally:
        V.recognize = real_recognize

    print("")
    if FAILED:
        print("checks: %d, failed: %d - %s" % (NCHECK[0], len(FAILED), ", ".join(FAILED)))
        print("REMATCH FAILED")
        return 1
    print("checks: %d, all passed" % NCHECK[0])
    print("REMATCH OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
