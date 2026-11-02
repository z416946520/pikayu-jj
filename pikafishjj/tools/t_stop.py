# -*- coding: utf-8 -*-
"""暂停 / 停止 must answer while the bot is busy, not after the current wait.

Measured problems this guards against: a stop during the engine's think time
waited for the whole search; the opponent wait kept spinning; a stop still ran
the recovery path (recalibration + engine restart) before exiting.

Run:  python pikafishjj\tools\t_stop.py
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


class FakeEngine(object):
    """A search that runs until stop() is called (or 5s pass)."""

    def __init__(self):
        self.stopped = threading.Event()
        self.stop_calls = 0

    def bestmove(self, fen, movetime=2000, depth=None, extra=()):
        self.stopped.wait(5.0)
        return "h2e2", None, []

    def stop(self):
        self.stop_calls += 1
        self.stopped.set()
        return True

    def quit(self):
        return True


def btn_player():
    p = A.AutoPlayer(our_side="w", verbose=False)
    p.hwnd = 1
    p.grid = OP
    p.session_ply = 1
    p.engine = FakeEngine()
    p.stop_event = threading.Event()
    p.pause_event = threading.Event()
    return p


def main():
    A.log = lambda *a: None

    # -- 1. stop while the engine is thinking --------------------------------
    p = btn_player()
    p._start_watch()
    t0 = time.time()
    box = {}

    def think():
        box["bm"] = p.engine.bestmove("x", movetime=5000)[0]

    th = threading.Thread(target=think, daemon=True)
    th.start()
    time.sleep(0.2)
    p.stop_event.set()
    th.join(3.0)
    took = time.time() - t0
    check("a stop aborts the engine search (%.2fs)" % took, took < 1.5, True)
    check("...and the search returned a move", box.get("bm"), "h2e2")
    check("...through engine.stop()", p.engine.stop_calls >= 1, True)
    p._stop_watch()

    # -- 2. stop during the opponent wait ------------------------------------
    p = btn_player()
    p.frame = lambda: None                       # nothing readable, so it keeps polling
    threading.Timer(0.3, p.stop_event.set).start()
    t0 = time.time()
    g, _a = p.wait_change(OP, timeout=30.0)
    took = time.time() - t0
    check("a stop ends the opponent wait (%.2fs)" % took,
          g is None and took < 1.5, True)

    # -- 3. stop while paused -------------------------------------------------
    p = btn_player()
    p.frame = lambda: None
    p.pause_event.set()
    threading.Timer(0.3, p.stop_event.set).start()
    t0 = time.time()
    g, _a = p.stable_grid(timeout=20.0)
    took = time.time() - t0
    check("a pause takes the bot out of the loop at once (%.2fs)" % took,
          g is None and took < 1.5, True)
    check("...and the pause aborted the search too", p.engine.stop_calls >= 1, True)

    # -- 4. a pause blocks and a resume carries on ---------------------------
    p = btn_player()
    p.frame = lambda: np.zeros((10, 10, 3), dtype=np.uint8)
    p.pause_event.set()
    seen = {}

    def run_one():
        seen["t0"] = time.time()
        p.stable_grid(timeout=0.4)
        seen["took"] = time.time() - seen["t0"]

    th = threading.Thread(target=run_one, daemon=True)
    th.start()
    time.sleep(0.5)
    check("a paused bot is still paused after 0.5s", th.is_alive(), True)
    p.pause_event.clear()
    th.join(2.0)
    check("...and resumes when the button is released", th.is_alive(), False)

    # -- 5. a stop never runs the repair path --------------------------------
    p = btn_player()
    p.stop_event.set()
    check("recover() does nothing after a stop", p.recover("test"), False)
    check("...and is not counted", p.stats["recover"], 0)

    print("")
    if FAILED:
        print("checks: %d, failed: %d - %s" % (NCHECK[0], len(FAILED), ", ".join(FAILED)))
        print("STOP FAILED")
        return 1
    print("checks: %d, all passed" % NCHECK[0])
    print("STOP OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
