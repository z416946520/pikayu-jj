# -*- coding: utf-8 -*-
"""Retry / recovery behaviour of AutoPlayer, plus the result screen button.

Nothing here needs a real game window: the parts that talk to Win32 or to the
board are replaced by stubs, so a failure names the exact step that broke.

Run:  python pikafishjj\tools\t_retry.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(PKG)
sys.path.insert(0, PKG)

import numpy as np
from PIL import Image

from pikafishjj import auto as A
from pikafishjj import board as B
from pikafishjj import dialog as D
from pikafishjj.engine import EngineError

OP = B.fen_to_grid(B.OPENING_FEN)
WANT = B.apply_move(B.clone(OP), ((7, 7), (4, 7), OP[7][7], OP[7][4]))
LOGS = []
FAILED = []
NCHECK = [0]


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


def load(name):
    p = os.path.join(ROOT, "fixtures", name)
    if not os.path.isfile(p):
        return None
    return np.asarray(Image.open(p).convert("RGB"))


class Stop(object):
    """A stop_event that trips after *after* calls of is_set()."""

    def __init__(self, after=4):
        self.n = 0
        self.after = after

    def is_set(self):
        self.n += 1
        return self.n > self.after

    def set(self):
        self.n = self.after + 1

    def clear(self):
        self.n = 0


class FakeEngine(object):
    """bestmove() that dies for the first *fails* calls, then plays *bm*."""

    def __init__(self, fails=0, bm="h2e2"):
        self.fails = fails
        self.bm = bm
        self.calls = 0
        self.quit_called = False

    def bestmove(self, fen, movetime=1000, depth=None, extra=()):
        self.calls += 1
        if self.calls <= self.fails:
            raise EngineError("the engine process exited unexpectedly (no output left)")
        info = ["info depth 18 score cp 5 nodes 1000 nps 50000 time 20 pv " + self.bm]
        return self.bm, None, info

    def quit(self):
        self.quit_called = True


def one_ply_run(settle="ok", engine_fails=0, stop_after=40, max_moves=1,
                grid=None, first="me", our_side="w", use_book=True):
    """Drive run() through exactly one of our plies; returns (player, clicks, err)."""
    del LOGS[:]
    eng = FakeEngine(fails=engine_fails)
    p = A.AutoPlayer(our_side=our_side, retries=3, movetime=50, verbose=True,
                      use_book=use_book)
    p.engine = eng
    p.grid = OP if grid is None else grid
    p.session_ply = 1
    p.stop_event = Stop(after=stop_after)
    p.recover = lambda reason: True
    p.stable_grid = lambda timeout=8.0, need=3, interval=0.03: (p.grid, "frame")
    p.wait_change = lambda prev, timeout=8.0, strict=True: (None, None)
    clicks = []
    p.play_move = lambda fi, fj, ti, tj: clicks.append((fi, fj, ti, tj))
    state = {"n": 0, "restart": 0}

    def settle_after(prev, w, timeout=6.0):
        state["n"] += 1
        if settle == "swallow" and state["n"] == 1:
            return None, None, False
        if settle == "never":
            return None, None, False
        return WANT, "frame", False

    def restart():
        state["restart"] += 1
        p.engine = eng
        return True

    p.settle_after = settle_after
    p.restart_engine = restart
    err = None
    try:
        p.run(max_moves=max_moves, first=first, opp_timeout=1.0)
    except Exception as exc:                       # noqa: BLE001 - reported by the caller
        err = exc
    return p, clicks, err, state


def main():
    A.log = lambda *a: LOGS.append(" ".join(str(x) for x in a))
    t0 = time.time()

    # -- 1. parameters ------------------------------------------------------
    p0 = A.AutoPlayer()
    check("retries default", p0.retries, 3)
    check("retries clamped from 0", A.AutoPlayer(retries=0).retries, 1)
    check("auto_next default", p0.auto_next, True)

    # -- 2. no Win32 call may escape as an exception ------------------------
    real_rect = A.w32.client_rect_screen
    try:
        A.w32.client_rect_screen = lambda hwnd: (_ for _ in ()).throw(OSError("window gone"))
        p = A.AutoPlayer(our_side="w")
        p.grabber = None
        check("frame() on a dead window", p.frame(), None)
        check("frame() logged the failure",
              logged("[frame] cannot read the game window"), True)
        check("_recognize(None)", p._recognize(None), None)
    finally:
        A.w32.client_rect_screen = real_rect

    # -- 3. the rematch button ---------------------------------------------
    def synth(cap=True, red=False, W=400, H=800):
        a = np.zeros((H, W, 3), dtype=np.uint8)
        a[:, :] = (44, 32, 64)
        y0, y1 = int(0.90 * H), int(0.95 * H)
        if cap:
            a[y0:y1, int(0.30 * W):int(0.70 * W)] = (150, 169, 69)
        if red:
            a[y0:y1, int(0.05 * W):int(0.22 * W)] = (216, 70, 60)
        return a

    hit = D.find_continue(synth())
    check("find_continue finds a bottom capsule", bool(hit), True)
    if hit:
        check("capsule is in the bottom band", hit["box"][1] > 0.84 * 800, True)
    check("find_continue ignores a green next to red", D.find_continue(synth(red=True)), None)
    check("find_continue ignores a bare board", D.find_continue(synth(cap=False)), None)

    for name, want_hit in (("live_check.png", True), ("dlg_result2.png", True),
                           ("live_probe.png", False), ("skin2_now.png", False),
                           ("skin_now.png", False), ("jj_orig.png", False),
                           ("user_shot.png", False)):
        a = load(name)
        if a is None:
            print("%-54s %s" % ("fixture " + name, "MISSING - skipped"))
            continue
        got = D.find_continue(a)
        if want_hit:
            check("rematch found on " + name, bool(got), True)
            if got:
                check(name + ": in the bottom band",
                      got["box"][1] >= int(0.84 * a.shape[0]), True)
        else:
            check("no rematch on " + name, got, None)

    a = load("live_check.png")
    if a is not None:
        p = A.AutoPlayer(our_side="w", dry=True, auto_next=True)
        p.origin = (100, 200)
        clicked = []
        p.click_point = lambda x, y: clicked.append((x, y))
        del LOGS[:]
        check("handle_continue on a result screen", p.handle_continue(a), True)
        check("rematch counted once", p.stats["rematch"], 1)
        check("dry run does not click",
              logged("[dry] not clicking the rematch button"), True)
        check("no click in dry mode", clicked, [])
        check("pressing twice within 3s", p.handle_continue(a), True)
        check("still counted once", p.stats["rematch"], 1)

        p2 = A.AutoPlayer(our_side="w", dry=False, auto_next=True)
        p2.origin = (100, 200)
        clicked2 = []
        p2.click_point = lambda x, y: clicked2.append((x, y))
        check("handle_continue clicks the button", p2.handle_continue(a), True)
        check("exactly one click", len(clicked2), 1)
        if clicked2:
            want_pt = D.find_continue(a)["point"]
            check("clicked through the window origin", clicked2[0],
                  (100 + want_pt[0], 200 + want_pt[1]))

        p3 = A.AutoPlayer(our_side="w", auto_next=False)
        check("auto_next off -> no press", p3.handle_continue(a), False)
        mid = load("live_probe.png")
        if mid is not None:
            p4 = A.AutoPlayer(our_side="w", dry=True)
            check("no press during a game", p4.handle_continue(mid), False)
            check("nothing counted during a game", p4.stats["rematch"], 0)

    # -- 4. a dead engine is restarted and the ply still lands --------------
    p, clicks, err, st = one_ply_run(engine_fails=2)
    check("run() did not raise", err, None)
    check("the ply was clicked once", clicks, [(7, 7, 4, 7)])
    # The opening book answers the first ply from the position, so a failing
    # engine is only reached once the book is out of moves (it holds ten lines
    # here).  Turn the book off for this case: it is the engine's retry being
    # tested, not the book's.
    p, clicks, err, st = one_ply_run(engine_fails=2, use_book=False)
    check("run() did not raise without a book", err, None)
    check("the ply was clicked once without a book", clicks, [(7, 7, 4, 7)])
    check("the engine was restarted", st["restart"] >= 1, True)
    check("engine failures counted", p.stats["fails"] >= 2, True)
    check("engine failure logged",
          logged("[think] the engine failed on attempt 1/3"), True)
    check("ply confirmed", logged("[play] confirmed h2 -> e2"), True)
    check("moves played", p.stats["moves"], 1)
    check("run finished normally", logged("[done] played 1 of our moves"), True)

    # -- 5. a swallowed click is retried with the very same ply -------------
    p, clicks, err, st = one_ply_run(settle="swallow")
    check("run() survived a swallowed click", err, None)
    check("the same ply was clicked twice", clicks, [(7, 7, 4, 7), (7, 7, 4, 7)])
    check("the missing board was logged",
          logged("[play] no settled board after attempt 1/3"), True)
    check("ply retries counted", p.stats["attempts"] >= 1, True)
    check("ply confirmed after the retry", logged("[play] confirmed h2 -> e2"), True)
    check("exactly one move counted", p.stats["moves"], 1)

    # -- 6. a ply that never lands keeps watching instead of stopping -------
    del LOGS[:]
    p, clicks, err, st = one_ply_run(settle="never", stop_after=60)
    check("run() survived an unlandable ply", err, None)
    check("the stall path was taken", logged("is still not on the board"), True)
    check("no giving-up line", any("giving up" in s for s in LOGS), False)
    check("the ply keeps being played", len(clicks) >= 3, True)
    check("...by thinking again instead of waiting for the opponent",
          logged("nothing moved and it is our turn - thinking again"), True)
    check("stalls counted", p.stats["stalls"] >= 1, True)
    check("no move was counted", p.stats["moves"], 0)

    # -- 6b. "the opponent moves first" must not survive their move ---------
    played = B.apply_move(B.clone(OP), ((2, 6), (2, 5), OP[6][2], "."))
    p, clicks, err, st = one_ply_run(grid=played, first="them", our_side="b")
    check("a board that already moved means it is our turn", err, None)
    check("...so the ply is played instead of waiting", len(clicks) >= 1, True)
    check("...and the reason is logged",
          logged("first-move setting says the opponent plays first"), True)
    del LOGS[:]
    p, clicks, err, st = one_ply_run(first="them", our_side="w")
    check("at the starting position red takes the first move even if told to wait",
          len(clicks) >= 1, True)

    # -- 7. an unreadable screen never ends the run -------------------------
    del LOGS[:]
    p = A.AutoPlayer(our_side="b", retries=3)   # black at the opening: red moves first
    p.engine = FakeEngine()
    p.grid = OP
    p.session_ply = 1
    p.stop_event = Stop(after=60)
    p.frame = lambda: None
    p.handle_continue = lambda a: False
    p.wait_change = lambda prev, timeout=8.0, strict=True: (None, None)
    calls = {"n": 0}

    def sg(timeout=8.0, need=3, interval=0.03):
        calls["n"] += 1
        return (OP, "frame") if calls["n"] == 1 else (None, None)

    p.stable_grid = sg
    p.play_move = lambda *a: None            # this case is about reading, not clicking
    real_find = A.w32.find_window
    try:
        A.w32.find_window = lambda sub: (None, "no window")
        err = None
        try:
            p.run(max_moves=200, first="them", opp_timeout=1.0)
        except Exception as exc:                   # noqa: BLE001
            err = exc
        check("run() survived a vanished window", err, None)
        check("the watch kept going", logged("[wait] still nothing readable"), True)
        check("recovery was attempted", p.stats["recover"] >= 1, True)
        check("no click was made", p.stats["moves"], 0)
    finally:
        A.w32.find_window = real_find

    # recover() itself: no window anywhere -> False, but counted
    p = A.AutoPlayer(our_side="w")
    try:
        A.w32.find_window = lambda sub: (None, "no window")
        del LOGS[:]
        check("recover() without a window", p.recover("test reason"), False)
        check("recovery counted", p.stats["recover"], 1)
        check("recovery logged", logged("[retry] test reason - recovery #1"), True)
    finally:
        A.w32.find_window = real_find

    # -- 8. wait_next_round picks up the new board --------------------------
    p = A.AutoPlayer(our_side="w", auto_next=True)
    p.grid = OP
    p.session_ply = 1
    p.stop_event = Stop(after=10 ** 6)
    p.frame = lambda: np.zeros((8, 8, 3), dtype=np.uint8)
    p.handle_dialog = lambda a: False
    seen = {"n": 0}

    def recognize(a):
        seen["n"] += 1
        return None if seen["n"] == 1 else OP

    p._recognize = recognize
    pressed = []
    p.handle_continue = lambda a: pressed.append(1) or False
    g, a = p.wait_next_round(timeout=3.0)
    check("new round picked up", (g is not None, a is not None), (True, True))
    check("the button was looked for while waiting", len(pressed) >= 1, True)

    print("")
    if FAILED:
        print("checks: %d, failed: %d - %s" % (NCHECK[0], len(FAILED), ", ".join(FAILED)))
        print("RETRY FAILED")
        return 1
    print("checks: %d, all passed, %.1fs" % (NCHECK[0], time.time() - t0))
    print("RETRY OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
