# -*- coding: utf-8 -*-
"""Background mode must stay in the background.

Field report of 2026-10-13: "后台模式会因为某种原因 打着打着自动切换成前台" (background
mode switches itself to the foreground somewhere in the middle of a game).  The
cause was in play_move(): one quiet click that could not be delivered - someone
put a window over the board, the game was minimised, the app was busy - set
bg_ok = False and nothing ever set it back, so every click from then on went
through bring_to_front() and the game window stayed in front.

Nothing here needs a game window or a real click: the Win32 entry points and the
click helpers are stubbed, the decision logic (_quiet_now / _quiet_ok /
_quiet_failed / _click_at / play_move / click_point) is the real code.

Run:  python pikafishjj\tools\t_bg.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)

from pikafishjj import auto as A
from pikafishjj import w32

LOGS = []
FAILED = []
NCHECK = [0]
GAP = 0.15


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


class BG(A.AutoPlayer):
    """An AutoPlayer with a stubbed geometry and click, driven move by move."""

    def __init__(self, plan=()):
        A.AutoPlayer.__init__(self, background=True, dry=False, verbose=True)
        self.hwnd = 1234
        self.origin = (0, 0)
        self.quiet = True
        self.BG_RETRY_GAP = GAP
        self.plan = list(plan)
        self.quiet_clicks = []
        self.foreground = []

    def cell_xy(self, i, j):
        return (100 + i, 200 + j)

    def click_point(self, x, y):
        # what the real one does: the window has to come to the front, and
        # WS_EX_NOACTIVATE is switched off for that click
        self.foreground.append((x, y))
        self.quiet = False
        return True

    def _click_at(self, x, y):
        self.quiet_clicks.append((x, y))
        return self.plan.pop(0) if self.plan else True


def plain(background=True, quiet=True, **kw):
    """A real AutoPlayer (no stubbed click) with a stand-in window handle."""
    p = A.AutoPlayer(background=background, dry=False, verbose=True, **kw)
    p.hwnd = 1234
    p.origin = (0, 0)
    p.quiet = quiet
    p.BG_RETRY_GAP = GAP
    return p


def main():
    A.log = lambda *a: LOGS.append(" ".join(str(x) for x in a))
    real = {n: getattr(w32, n) for n in
            ("point_owner", "title_of", "is_minimized", "set_topmost",
             "click_silent", "bring_to_front", "click", "set_no_activate",
             "raise_window")}
    back = []
    w32.raise_window = lambda hwnd: back.append(hwnd) or True
    STYLE = []
    try:
        w32.set_no_activate = lambda hwnd, on=True: (STYLE.append(bool(on)), True)[1]

        # -- 1. quiet clicks stay quiet --------------------------------------
        del LOGS[:]
        p = BG([True, True])
        p.play_move(1, 1, 2, 2)
        check("a quiet move clicks twice in the background", len(p.quiet_clicks), 2)
        check("...without touching the foreground", p.foreground, [])
        check("...and background mode is still on", p.bg_ok, True)

        # -- 2. one failed quiet click suspends it for a moment --------------
        del LOGS[:]
        p = BG([True, False])
        p.play_move(1, 1, 2, 2)
        check("both clicks of the move are still attempted", len(p.quiet_clicks), 2)
        check("a failure leaves background mode", p.bg_ok, False)
        check("...saying it is temporary", logged("then trying the background again"), True)
        p.play_move(3, 3, 4, 4)
        check("the next move uses ordinary clicks", len(p.foreground), 2)
        check("...and no quiet one", len(p.quiet_clicks), 2)

        # -- 3. ... and it comes back by itself ------------------------------
        del LOGS[:]
        time.sleep(GAP + 0.05)
        p.plan = [True, True]
        p.play_move(5, 5, 6, 6)
        check("after the gap a quiet click is tried again",
              logged("trying quiet clicking again"), True)
        check("...and background mode is restored",
              logged("quiet clicking works again"), True)
        check("...so the flag is on again", p.bg_ok, True)
        check("...the window keeps WS_EX_NOACTIVATE", STYLE[-1] if STYLE else None, True)
        check("...and this move was quiet", len(p.foreground), 2)
        p.play_move(7, 7, 8, 8)
        check("the move after that is quiet too", len(p.foreground), 2)

        # -- 4. the failure says what is in the way --------------------------
        del LOGS[:]
        w32.is_minimized = lambda hwnd: False
        w32.point_owner = lambda x, y: 999
        w32.title_of = lambda hwnd: "\u8bb0\u4e8b\u672c"
        clicks = []
        w32.click_silent = lambda x, y, hold=0.03: clicks.append((x, y)) or True
        tops = []
        w32.set_topmost = lambda hwnd, on=True: tops.append(bool(on)) or True
        p = plain()
        check("a covered click cannot be delivered", p._click_at(10, 10), False)
        check("...and the covering window is named", logged("记事本"), True)
        check("...without clicking anything", clicks, [])
        check("...after raising the game and lowering it again", tops, [True, False])
        check("...and the window that was in the way goes back in front",
              back, [999])

        # -- 5. a minimised window is named as such --------------------------
        del LOGS[:]
        w32.is_minimized = lambda hwnd: True
        tops[:] = []
        p = plain()
        check("a minimised window is not clicked either", p._click_at(10, 10), False)
        check("...and the log says so", logged("is minimised"), True)
        check("...and nothing is raised for it", tops, [])

        # -- 6. an uncovered point is clicked quietly ------------------------
        del LOGS[:]
        w32.is_minimized = lambda hwnd: False
        clicks[:] = []
        p = plain()
        w32.point_owner = lambda x, y: p.hwnd
        check("an uncovered point is clicked", p._click_at(10, 10), True)
        check("...quietly", clicks, [(10, 10)])

        # -- 7. raise_click off: never raise, just report --------------------
        del LOGS[:]
        w32.point_owner = lambda x, y: 999
        tops[:] = []
        p = plain()
        p.raise_click = False
        check("with raising disabled the click is refused", p._click_at(10, 10), False)
        check("...and nothing is raised", tops, [])
        check("...but the reason is logged", logged("the board is covered by"), True)

        # -- 8. the foreground path still works when it is needed ------------
        del LOGS[:]
        front = []
        w32.bring_to_front = lambda hwnd: front.append(hwnd) or True
        w32.click = lambda x, y, hold=0.03: front.append((x, y)) or True
        p = plain()
        p.bg_ok = False
        p.bg_probe_t = time.time() + 30.0
        check("a suspended background mode is not quiet", p._quiet_now(), False)
        p.click_point(11, 12)
        check("...so the click goes to the front", front, [p.hwnd, (11, 12)])
        check("...and activation is handed back for it", p.quiet, False)
    finally:
        for n, fn in real.items():
            setattr(w32, n, fn)

    print("")
    if FAILED:
        print("checks: %d, failed: %d - %s" % (NCHECK[0], len(FAILED), ", ".join(FAILED)))
        print("BG FAILED")
        return 1
    print("checks: %d, all passed" % NCHECK[0])
    print("BG OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
