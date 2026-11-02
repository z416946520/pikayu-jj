# -*- coding: utf-8 -*-
"""Our own clock: the bot must never spend a minute of it doing nothing.

Field report of 2026-10-13: "偶尔不会操作 导致下棋超时 输给对方" - occasionally it stops
playing and loses on time.  The mechanism was in the run loop: when a ply did not
appear on the board after the retries, the loop handed the turn back to the
opponent and waited for the board to change with the full opp_timeout (60 s by
default).  If it really was our turn (the click had been swallowed, the app was
busy, the board was misread) nothing could ever change, so the bot sat there for
a minute while our clock ran - and with a per-move limit that is an outright
loss.  The same shape of wait existed for our own ply (settle_after 6 s x
retries) and for a wedged engine (a flat 10 s per attempt).

Nothing here needs a game window: the frame source, recognition, the engine and
the click are stubbed, the run loop / settle_after / wait_change / stable_grid
are the real code.

Run:  python pikafishjj\tools\t_time.py
"""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)

import numpy as np

from pikafishjj import auto as A
from pikafishjj import board as B
from pikafishjj.engine import Engine, EngineError

OP = B.fen_to_grid(B.OPENING_FEN)
WANT = B.apply_move(B.clone(OP), ((2, 6), (2, 5), OP[6][2], "."))   # c3 -> c4
FRAME = np.zeros((600, 400, 3), dtype=np.uint8)
LOGS = []
FAILED = []
NCHECK = [0]


def check(name, got, want):
    NCHECK[0] += 1
    ok = (got == want)
    if not ok:
        FAILED.append(name)
    print("%-58s %-4s %r" % (name, "ok" if ok else "FAIL", got))
    if not ok:
        print("%-58s want %r" % ("", want))
    return ok


def logged(needle):
    return any(needle in s for s in LOGS)


class FakeEngine(object):
    """Always answers with the same move; counts how often it was asked."""

    def __init__(self):
        self.asked = 0

    def bestmove(self, fen, movetime=2000, depth=None, extra=()):
        self.asked += 1
        time.sleep(0.02)
        return "c3c4", None, []


def stalled_player(seconds):
    """A player whose clicks never land: the board is always the same."""
    p = A.AutoPlayer(our_side="w", dry=False, verbose=True, retries=1)
    p.engine = FakeEngine()
    p.movetime = 10
    p.SETTLE_TIMEOUT = 0.3
    p.STALL_WATCH = 0.3
    p.UNCERTAIN_WAIT = 0.5
    p.background = False
    p.frame = lambda: FRAME
    p.handle_dialog = lambda a: False
    p.handle_continue = lambda a: False
    p.band_changed = lambda prev, a: False
    p._recognize = lambda a: OP
    p.recover = lambda reason: True
    p.clicks = []
    p.play_move = lambda fi, fj, ti, tj: p.clicks.append((fi, fj, ti, tj))
    p.stop_event = threading.Event()
    threading.Timer(seconds, p.stop_event.set).start()
    return p


def main():
    A.log = lambda *a: LOGS.append(" ".join(str(x) for x in a))

    # -- 1. a ply that never lands keeps being played ------------------------
    del LOGS[:]
    p = stalled_player(5.0)
    t0 = time.time()
    p.run(max_moves=200, first="me", opp_timeout=60.0)
    took = time.time() - t0
    check("a stalled turn is retried at least 3 times (%.0f in %.1fs)" % (
        len(p.clicks), took), len(p.clicks) >= 3, True)
    # the book answers the opening plies, so the engine is only asked
    # after the book runs out - either way the ply is replayed, which is what
    # this check is about.
    check("...so the ply is replayed at least 3 times", len(p.clicks) >= 3, True)
    check("...and the engine is asked once the book is out of moves",
          p.engine.asked >= 1, True)
    check("...the turn is watched, not handed over",
          logged("watching the board for"), True)
    check("...and play resumes right after the watch",
          logged("nothing moved and it is our turn - thinking again"), True)
    check("...the stall is counted", p.stats.get("stalls", 0) >= 1, True)
    check("...and our own clock time is accounted",
          p.stats.get("turn_s", 0.0) > 0.0, True)
    check("...with no 60s idle handover", logged("(idle wait 1)"), False)
    check("...and the whole spell stayed short (%.1fs)" % took, took < 12.0, True)
    seen = [s for s in LOGS if "is still not on the board" in s]
    check("...and the stall line carries the elapsed time",
          bool(seen) and "spent)" in seen[0], True)

    # -- 2. a move that does land is fast and logged with its time ----------
    del LOGS[:]
    state = {"played": False}
    p = A.AutoPlayer(our_side="w", dry=False, verbose=True, retries=1)
    p.engine = FakeEngine()
    p.movetime = 10
    p.SETTLE_TIMEOUT = 2.0
    p.frame = lambda: FRAME
    p.handle_dialog = lambda a: False
    p.handle_continue = lambda a: False
    p.band_changed = lambda prev, a: False
    p._recognize = lambda a: (WANT if state["played"] else OP)
    p.recover = lambda reason: True
    p.clicks = []

    def click(fi, fj, ti, tj):
        p.clicks.append((fi, fj, ti, tj))
        state["played"] = True

    p.play_move = click
    p.stop_event = threading.Event()
    threading.Timer(3.0, p.stop_event.set).start()
    p.run(max_moves=1, first="me", opp_timeout=1.0)
    check("a ply that lands is confirmed", logged("confirmed c3 -> c4"), True)
    check("...with the time it cost", logged("in 0."), True)
    check("...counted against our clock", p.stats.get("turn_s", 0.0) > 0.0, True)
    check("...and it was not called slow", p.stats.get("slow", 0), 0)
    check("...with the slowest turn recorded", p.stats.get("turn_max", 0.0) > 0.0, True)

    # -- 3. a wedged engine is given up on quickly --------------------------
    engine = None
    try:
        engine = Engine(A.DEFAULT_EXE, threads=2, hash_mb=64)
        t0 = time.time()
        bm, _pd, _info = engine.bestmove(
            "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
            movetime=200)
        quick = time.time() - t0
        check("a healthy engine still answers (%.2fs)" % quick,
              bool(bm) and quick < 3.0, True)
        engine._readline = lambda timeout: (time.sleep(max(0.05, timeout)), None)[1]
        t0 = time.time()
        raised = False
        try:
            engine.bestmove(
                "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
                movetime=400)
        except EngineError:
            raised = True
        took = time.time() - t0
        check("a wedged engine is given up on (%.1fs)" % took, raised, True)
        check("...within the time we asked it to think plus a little",
              took < 9.0, True)
    except Exception as exc:                       # noqa: BLE001
        check("engine checks", "%s: %s" % (type(exc).__name__, exc), "no exception")
    finally:
        if engine is not None:
            engine.quit()

    print("")
    if FAILED:
        print("checks: %d, failed: %d - %s" % (NCHECK[0], len(FAILED), ", ".join(FAILED)))
        print("TIME FAILED")
        return 1
    print("checks: %d, all passed" % NCHECK[0])
    print("TIME OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
