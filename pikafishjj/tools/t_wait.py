# -*- coding: utf-8 -*-
"""Waiting: a repainting board, and a board that moved twice while we looked away.

Field report of 2026-10-13.  The second round was drawn for the other side (red
at the top, the opponent to move first).  The app repaints the board after every
move, so stable_grid could not find three still frames in a row; by the time the
board was readable again the opponent's first move *and* a move the user had made
by hand were both on it.  Four cells is not one ply, so the 1-ply gate rejected
it and the wait then sat on its fallback for the whole 60s timeout - the log the
user sent ends with "ignoring an implausible jump (4 cells)" and, from the
outside, the program had stopped playing.

Nothing here needs a game window: the frame source, V.recognize and dialog's
find_request are stubbed, everything else (stable_grid, wait_change,
handle_dialog, handle_continue, _recognize) is the real code.

Run:  python pikafishjj\tools\t_wait.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)

import numpy as np
from PIL import Image

from pikafishjj import auto as A
from pikafishjj import board as B
from pikafishjj import dialog as D
from pikafishjj import vision as V

OP = B.fen_to_grid(B.OPENING_FEN)
# the two plies of the field report: the opponent pushes a pawn, then our horse
# is moved by hand before the bot manages to read the board
OPP = B.apply_move(B.clone(OP), ((2, 6), (2, 5), OP[6][2], "."))
BOTH = B.apply_move(B.clone(OPP), ((7, 0), (6, 2), OPP[0][7], "."))
# a frame that is not a series of moves: one of our horses simply vanished
TORN = B.clone(OP)
TORN[0][7] = "."
# ... and one where a piece changed letter in place (a misread)
SWAP = B.clone(OP)
SWAP[0][0] = "R"
# five plies at once: too many to be believed from one screen
MANY = B.clone(OP)
for _from, _to in [((0, 6), (0, 5)), ((2, 6), (2, 5)), ((4, 6), (4, 5)),
                   ((6, 6), (6, 5)), ((8, 6), (8, 5))]:
    MANY = B.apply_move(MANY, (_from, _to, MANY[_from[1]][_from[0]], "."))
# a capture: our chariot takes a pawn
CAP = B.apply_move(B.clone(OP), ((0, 9), (0, 3), OP[9][0], OP[3][0]))
SCR_OP = B.screen_to_internal(OP, False)
# a frame that is not a board at all (as a screen grid)
SCR_EMPTY = B.screen_to_internal(B.fen_to_grid("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1"), False)
# real screens: an in-game board, and the result screen that draws it 20% smaller
ROOT = os.path.dirname(os.path.dirname(HERE))
IN_GAME = os.path.join(ROOT, "fixtures", "skin2_now.png")
RESULT = os.path.join(ROOT, "fixtures", "live_now2.png")

FRAME = np.zeros((600, 400, 3), dtype=np.uint8)
LOGS = []
FAILED = []
NCHECK = [0]
CLICKS = []
PANEL = {"d": None}


def check(name, got, want):
    NCHECK[0] += 1
    ok = (got == want)
    if not ok:
        FAILED.append(name)
    print("%-56s %-4s %r" % (name, "ok" if ok else "FAIL", got))
    if not ok:
        print("%-56s want %r" % ("", want))
    return ok


def logged(needle):
    return any(needle in s for s in LOGS)


def fake_recognize(a, cal, tpl, **kw):
    info = kw.get("info")
    if info is not None:
        info["hints"] = {}
    return SCR_OP, 1.0


def fake_find_request(a):
    return PANEL["d"]


def new_player():
    p = A.AutoPlayer(our_side="w", auto_next=True, verbose=True)
    p.flip = False
    p.grid = OP
    p.session_ply = 8
    p.cal = {"cpitch": 65.0, "rpitch": 62.8}
    p.pitch = (65.0, 62.8)
    p.tpl = {}
    p.frame = lambda: FRAME
    p.handle_dialog = lambda a: False
    p.band_changed = lambda prev, a: True
    p.click_point = lambda x, y: CLICKS.append((x, y))
    return p


def main():
    A.log = lambda *a: LOGS.append(" ".join(str(x) for x in a))
    real_recognize = V.recognize
    real_find_request = D.find_request
    V.recognize = fake_recognize
    try:
        # -- 1. reading a difference as whole plies --------------------------
        check("the same board is no change at all", B.explain_change(OP, OP), [])
        one = B.explain_change(OP, OPP)
        check("one move reads as one ply", len(one), 1)
        check("...from the square that emptied", one[0][0] if one else None, (2, 6))
        check("...to the square that gained it", one[0][1] if one else None, (2, 5))
        two = B.explain_change(OP, BOTH)
        check("two moves read as two plies", len(two) if two else None, 2)
        check("...each from the square that emptied",
              [m[0] for m in two] if two else None, [(7, 0), (2, 6)])
        check("a vanishing piece is not a move", B.explain_change(OP, TORN), None)
        check("a piece that changed letter is not a move",
              B.explain_change(OP, SWAP), None)
        check("five plies at once are too many to believe",
              B.explain_change(OP, MANY), None)
        cap = B.explain_change(OP, CAP)
        check("a capture is one ply", len(cap) if cap else None, 1)
        check("...and names what it took", cap[0][3] if cap else None, "p")

        # -- 2. one ply is taken straight away -------------------------------
        del LOGS[:]
        p = new_player()
        p.stable_grid = lambda timeout=8.0, need=3, interval=0.03: (OPP, "frame")
        t0 = time.time()
        g, _a = p.wait_change(OP, timeout=5.0, strict=True)
        check("one ply is taken straight away", g, OPP)
        check("...without waiting for a confirmation", (time.time() - t0) < 0.5, True)

        # -- 3. two plies are taken once they stay put -----------------------
        del LOGS[:]
        p = new_player()
        p.stable_grid = lambda timeout=8.0, need=3, interval=0.03: (BOTH, "frame")
        t0 = time.time()
        g, _a = p.wait_change(OP, timeout=8.0, strict=True)
        took = time.time() - t0
        check("two plies at once are taken", g, BOTH)
        check("...after the confirmation window (%.1fs)" % took, 1.4 <= took <= 4.0, True)
        check("...with the first sighting announced", logged("the board is 2 moves ahead"), True)
        check("...naming both moves", (logged("c3-c4(P)"), logged("h9-g7(n)")), (True, True))
        check("...then taken for real",
              logged("2 moves landed while we were not looking"), True)
        check("...and not called a torn board", logged("is not a series of moves"), False)

        # -- 4. a change no series of moves explains is only held ------------
        del LOGS[:]
        p = new_player()
        p.stable_grid = lambda timeout=8.0, need=3, interval=0.03: (TORN, "frame")
        t0 = time.time()
        g, _a = p.wait_change(OP, timeout=1.2, strict=True)
        took = time.time() - t0
        check("a torn board is reported as such", logged("is not a series of moves"), True)
        check("...and held until the timeout (%.1fs)" % took, took >= 1.1, True)
        check("...then handed back as the fallback", g, TORN)
        check("...with a line saying it is the fallback",
              logged("sticking with the board we kept reading"), True)
        check("...and never called one move", logged("is not a series of moves"), True)

        # -- 5. a board that keeps repainting is still read -------------------
        del LOGS[:]
        p = new_player()
        t0 = time.time()
        g, a = p.stable_grid(timeout=6.0)
        took = time.time() - t0
        check("a repainting board is read anyway", g, OP)
        check("...within a few seconds (%.1fs)" % took, took < 5.0, True)
        check("...after saying it keeps repainting",
              logged("the board keeps repainting"), True)
        check("...and that two readings agreed",
              logged("two readings agree"), True)

        # -- 6. the heartbeat says which state the wait is in -----------------
        del LOGS[:]
        p = new_player()
        p.WAIT_HEARTBEAT = 0.3
        p.grid = OPP
        p.stable_grid = lambda timeout=8.0, need=3, interval=0.03: (OPP, "frame")
        g, _a = p.wait_change(OPP, timeout=0.9, strict=True)
        check("an unchanged board is reported as unchanged",
              logged("the opponent has not moved yet"), True)
        check("...and nothing new is handed back", g, None)
        del LOGS[:]
        p2 = new_player()
        p2.WAIT_HEARTBEAT = 0.3
        p2.stable_grid = lambda timeout=8.0, need=3, interval=0.03: (None, None)
        g2, _a2 = p2.wait_change(OP, timeout=0.9, strict=True)
        check("an unreadable board is reported as unreadable",
              logged("the board cannot be read yet"), True)
        check("...and nothing new is handed back either", g2, None)

        # -- 7. the request panel needs a whole second on screen -------------
        D.find_request = fake_find_request
        PANEL["d"] = {"decline": (100, 200), "accept": (160, 200), "buttons": 2}
        del CLICKS[:]
        p = A.AutoPlayer(our_side="w", verbose=True)
        p.origin = (1000, 500)
        p.click_point = lambda x, y: CLICKS.append((x, y))
        p.handle_dialog(FRAME)
        p.handle_dialog(FRAME)
        check("a panel seen twice is not answered", CLICKS, [])
        for _k in range(3):
            time.sleep(0.42)
            p.handle_dialog(FRAME)
        check("a panel that stays for a second is answered", len(CLICKS), 1)
        check("...at the button's screen point", CLICKS[0] if CLICKS else None, (1100, 700))
        check("...and counted once", p.stats["dialogs"], 1)

        del CLICKS[:]
        p1 = A.AutoPlayer(our_side="w", verbose=True)
        p1.origin = (1000, 500)
        p1.click_point = lambda x, y: CLICKS.append((x, y))
        PANEL["d"] = {"decline": (100, 200), "buttons": 1}
        for _k in range(4):
            p1.handle_dialog(FRAME)
            time.sleep(0.42)
        check("a single button is given a longer look", CLICKS, [])
        for _k in range(3):
            p1.handle_dialog(FRAME)
            time.sleep(0.45)
        check("...but is answered once it has stayed", len(CLICKS), 1)

        # -- 8. nothing is answered right after 再来一局 ----------------------
        D.find_request = real_find_request          # the real detector, on a fake screen
        del CLICKS[:]
        p2 = A.AutoPlayer(our_side="w", auto_next=True, verbose=True)
        p2.origin = (1000, 500)
        p2.click_point = lambda x, y: CLICKS.append((x, y))
        a = np.zeros((800, 400, 3), dtype=np.uint8)
        a[:, :] = (44, 32, 64)
        a[int(0.90 * 800):int(0.95 * 800), int(0.30 * 400):int(0.70 * 400)] = (150, 169, 69)
        hit = p2.handle_continue(a)
        check("the rematch button is recognised", hit, True)
        check("...and clicked", len(CLICKS), 1)
        check("...which buys 8s of silence for the transition",
              round(p2._dlg_skip_t - time.time(), 1), 8.0)
        D.find_request = fake_find_request
        PANEL["d"] = {"decline": (100, 200), "accept": (160, 200), "buttons": 2}
        del CLICKS[:]                       # the rematch press is not a panel click
        seen = [p2.handle_dialog(FRAME) for _k in range(5)]
        check("a panel on the transition screen is never answered", CLICKS, [])
        check("...and the frames are left alone", seen, [False] * 5)

        # -- 9. the shrunken result screen is not read as a board ------------
        del LOGS[:]
        p = new_player()
        p.pitch = (65.4, 62.8)
        p.cal = {"cpitch": 51.4, "rpitch": 50.8}
        check("a board drawn 20% smaller is not read", p._recognize(FRAME), None)
        check("...and the log says what it saw",
              logged("that is the result/menu screen"), True)
        p.PITCH_RELEARN = 0.1
        time.sleep(0.15)
        got = p._recognize(FRAME)
        check("a size that stays for a while is adopted", got, OP)
        check("...and remembered", p.pitch, (51.4, 50.8))
        check("...and reported", logged("adopting that size"), True)

        # -- 10. a fit that belongs to another screen is refitted ------------
        del LOGS[:]
        state = {"ok": False}

        def flaky(a, cal, tpl, **kw):
            info = kw.get("info")
            if info is not None:
                info["hints"] = {}
            return (SCR_OP if state["ok"] else SCR_EMPTY), 1.0

        p = new_player()
        p.band_changed = lambda prev, a: False

        def refit_ok(tries=6, gap=0.35):
            p.cal = {"cpitch": 65.0, "rpitch": 62.8}
            p.fp_band = (0, 0)
            state["ok"] = True
            return FRAME

        p._ensure_cal = refit_ok
        V.recognize = flaky
        g, _a = p.stable_grid(timeout=6.0)
        check("three unreadable frames in a row lead to a refit",
              logged("refitting the board"), True)
        check("...which is taken when the frame reads afterwards",
              logged("the board was refitted"), True)
        check("...and the board is read again", g, OP)

        del LOGS[:]
        state["ok"] = False                  # this time the refit does not help
        p2 = new_player()
        p2.band_changed = lambda prev, a: False
        p2._ensure_cal = lambda tries=6, gap=0.35: FRAME
        g2, _a2 = p2.stable_grid(timeout=4.0)
        check("a refit that still does not read is dropped",
              logged("keeping the fit we had"), True)
        check("...and the window is left alone", g2, None)
        check("...with the old fit kept", (p2.cal or {}).get("cpitch"), 65.0)
        V.recognize = fake_recognize

        # -- 11. the same two screens, for real ------------------------------
        del LOGS[:]
        in_game = np.asarray(Image.open(IN_GAME).convert("RGB"))
        result = np.asarray(Image.open(RESULT).convert("RGB"))
        cal = V.calibrate(in_game, verbose=False)
        check("the in-game board fits", bool(cal and cal.get("model")), True)
        p3 = A.AutoPlayer(our_side="auto")
        p3.cal = cal
        p3.tpl = {}
        g3 = p3._recognize(in_game)
        check("...and reads as a board", p3.plausible(g3), True)
        check("...which fixes the size we are playing at",
              p3.pitch is not None, True)
        cal2 = V.calibrate(result, verbose=False)
        check("the result screen fits a lattice of its own too", bool(cal2), True)
        p3.cal = cal2
        check("...but it is refused as a smaller board", p3._recognize(result), None)
        check("...and the log says what it saw",
              logged("that is the result/menu screen"), True)
    finally:
        V.recognize = real_recognize
        D.find_request = real_find_request

    print("")
    if FAILED:
        print("checks: %d, failed: %d - %s" % (NCHECK[0], len(FAILED), ", ".join(FAILED)))
        print("WAIT FAILED")
        return 1
    print("checks: %d, all passed" % NCHECK[0])
    print("WAIT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
