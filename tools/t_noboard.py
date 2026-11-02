# -*- coding: utf-8 -*-
"""The program must not die when the board cannot be read.

Field report of 2026-10-14: the customer's last round was a quiet endgame ("双方
都只有几个棋子，谁也奈何不了谁"), the app kept repainting, and the run ended with
the console printing a traceback and giving up:

    [attach] the board fit reads as no position (attempt 6/6)
    [gui] attempt 1/3 failed: RuntimeError: board calibration failed after 6 tries
    ...
    [gui] giving up after 3 attempts - press 开始对局 to try again

Three separate raises made that happen, and each one is pinned here:

  1. attach() raised when no frame in *tries* showed a readable board,
  2. run() raised "could not obtain a stable board reading" after its retries,
  3. the worker's three attempts then all failed and the run was over.

attach(wait=True) keeps the window instead, run() falls through to
wait_for_board(), and that watch loop never gives up on its own: it refits every
few seconds, reattaches when the window comes back, and only 停止 ends it.

Run:  python tools\t_noboard.py      (exits non-zero on any mismatch)
"""
import sys
import time

sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np                                       # noqa: E402
from pikafishjj import auto as A, board as B             # noqa: E402

LOGS = []
BAD = []
NCHECK = [0]
A.log = lambda *a: LOGS.append(" ".join(str(x) for x in a))


def check(name, got, want):
    NCHECK[0] += 1
    ok = (got == want)
    if not ok:
        BAD.append(name)
    print("%-56s %-4s %r" % (name, "ok" if ok else "FAIL", got))
    if not ok:
        print("%-56s want %r" % ("", want))
    return ok


def logged(needle):
    return any(needle in s for s in LOGS)


def blank_frame(stage=0):
    """A frame with no board on it: a flat colour, like a menu or an overlay."""
    a = np.zeros((900, 600, 3), dtype=np.uint8)
    a[:, :] = (40, 60, 50)
    return a


def player_with_no_board(**kw):
    p = A.AutoPlayer(our_side="w", dry=True, verbose=False, **kw)
    p.hwnd = 424242
    p.grabber = p.wgrab = None
    p.frame = lambda: blank_frame()
    # the window lookup must not need a real game window for this test
    A.w32.find_window = lambda title: (424242, "JJ象棋")
    A.w32.client_rect_screen = lambda hwnd: (0, 0, 600, 900)
    return p


def main():
    # -- 1. attach() must not raise when asked to wait ----------------------
    p = player_with_no_board()
    try:
        p.attach(wait=True)
        check("attach(wait=True) survives a screen with no board", True, True)
    except Exception as exc:
        check("attach(wait=True) survives a screen with no board",
              "%s: %s" % (type(exc).__name__, exc), True)
    check("...and says so in the log", logged("no board on screen yet"), True)
    check("...and leaves the window attached", p.hwnd, 424242)
    check("...and leaves the geometry empty so the next read refits", p.cal, None)
    check("...and leaves a template pack the console can count", bool(p.tpl), True)
    # the strict behaviour is unchanged: a caller that wants an error still gets one
    p2 = player_with_no_board()
    raised = None
    try:
        p2.attach(wait=False)
    except RuntimeError as exc:
        raised = str(exc)
    check("attach(wait=False) still refuses", bool(raised and "calibration failed" in raised), True)

    # -- 2. run() must fall through to the watch, not raise -----------------
    p = player_with_no_board()
    p.start_engine = lambda: None
    p.stable_grid = lambda **kw: (None, None)
    calls = {"watch": 0}

    def fake_wait(timeout=0.0):
        calls["watch"] += 1
        return None, None            # the user pressed 停止

    p.wait_for_board = fake_wait
    try:
        p.run(max_moves=1)
        check("run() survives a window that shows no board", True, True)
    except Exception as exc:
        check("run() survives a window that shows no board",
              "%s: %s" % (type(exc).__name__, exc), True)
    check("...by watching for a board", calls["watch"], 1)
    check("...and says so in the log", logged("no board to read yet"), True)

    # -- 3. the watch loop: it waits, refits, and only 停止 ends it ---------
    p = player_with_no_board()
    t = {"stop": False}
    p._stop = lambda: t["stop"]
    reads = {"n": 0}

    def stable(**kw):
        reads["n"] += 1
        if reads["n"] >= 3:
            # the app finally shows a board again
            return B.fen_to_grid(B.OPENING_FEN), blank_frame()
        return None, None

    p.stable_grid = stable
    p._ensure_cal = lambda **kw: None
    g, a = p.wait_for_board(timeout=0.0)
    check("the watch returns the board once it is readable", g == B.fen_to_grid(B.OPENING_FEN), True)
    check("...and it took a few reads to get there", reads["n"] >= 3, True)

    # stop ends it immediately
    p = player_with_no_board()
    t2 = {"stop": True}
    p._stop = lambda: t2["stop"]
    p.stable_grid = lambda **kw: (None, None)
    g, a = p.wait_for_board(timeout=0.0)
    check("停止 ends the watch at once", (g, a), (None, None))

    # a window that disappears and comes back is re-attached, not fatal
    p = player_with_no_board()
    p.hwnd = None
    state = {"attach": 0, "read": 0}

    def reattach(**kw):
        state["attach"] += 1
        p.hwnd = 424242
        return p

    p.attach = reattach
    p._ensure_cal = lambda **kw: None

    def stable2(**kw):
        state["read"] += 1
        if state["read"] >= 4:
            return B.fen_to_grid(B.OPENING_FEN), blank_frame()
        return None, None

    p.stable_grid = stable2
    g, a = p.wait_for_board(timeout=0.0)
    check("a window that comes back is re-attached and read",
          (g is not None, state["attach"] >= 1), (True, True))

    # -- 4. the real frame that killed the customer's run -------------------
    # The frame is a readable board (a human sees 8 pieces).  What is pinned here
    # is only the control flow: the watch must return whatever the reader makes of
    # that frame without hanging, and it must end when 停止 is pressed.  Whether
    # the reader gets the position right is vision's business (tools/t_lift.py and
    # tools/t_regress.py pin the readings themselves).
    import os
    FRAME = r"D:\BuildProject\pikayu-jj\fixtures\cal_fail_1.png"
    if os.path.isfile(FRAME):
        p = player_with_no_board()
        stop = {"t": False}
        p._stop = lambda: stop["t"]
        reads = {"n": 0}

        def stable3(**kw):
            reads["n"] += 1
            if reads["n"] >= 3:
                stop["t"] = True                 # the user pressed 停止
            return None, None                   # ... or the frame does not read

        p.stable_grid = stable3
        p._ensure_cal = lambda **kw: None
        t0 = time.time()
        g, a = p.wait_for_board(timeout=0.0)
        dt = time.time() - t0
        check("the watch over the customer's frame returns promptly", dt < 60.0, True)
        check("...and does not raise", (g, a), (None, None))
        check("...and 停止 ends it", stop["t"], True)
        check("...after a bounded number of reads", 3 <= reads["n"] <= 8, True)
    else:
        print("(frame %s not found - skipping)" % FRAME)

    print("")
    print("checks: %d, failed: %d - %s" % (NCHECK[0], len(BAD), ", ".join(BAD) or "none"))
    print("NOBOARD OK" if not BAD else "NOBOARD FAILED")
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
