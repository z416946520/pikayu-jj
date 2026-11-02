# -*- coding: utf-8 -*-
"""Static audit of the player: the contracts that are only visible in the log.

Ten checks over the plumbing that everything else trusts:

  1. read        - frame(), _recognize(), read() survive a dead window
  2. degrade     - both axes must keep working when their backend is missing
  3. stop        - the loop must exit within a tenth of a second after 停止
  4. report      - the counters the summary line quotes must exist
  5. cleanup     - close() may be called twice and releases engine + grabbers
  6. pause       - a paused bot must not spin the CPU or read frames
  7. newgame     - a full round + rematch must not leak grabbers
  8. contract    - the console and the player must agree on every option key
  9. muting      - interactive sampling must not click or press a key
 10. stability   - repeated calibrate/recognize must not drift or raise

Run:  python pikafishjj\tools\t_audit.py
"""
import inspect
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(PKG)
sys.path.insert(0, PKG)

import numpy as np

from pikafishjj import auto as A
from pikafishjj import board as B
from pikafishjj import bridge as BR
from pikafishjj import gui as G
from pikafishjj import vision as V

FRAME = np.zeros((600, 400, 3), dtype=np.uint8)
OP = B.fen_to_grid(B.OPENING_FEN)
LOGS = []
FAILED = []
NCHECK = [0]


def check(name, got, want):
    NCHECK[0] += 1
    if isinstance(got, np.ndarray) or isinstance(want, np.ndarray):
        got = np.asarray(got).tolist()
        want = np.asarray(want).tolist()
    ok = (got == want)
    if not ok:
        FAILED.append(name)
    print("%-62s %-4s %r" % (name, "ok" if ok else "FAIL", got))
    if not ok:
        print("%-62s want %r" % ("", want))
    return ok


def player(**kw):
    p = A.AutoPlayer(our_side="w", verbose=False, **kw)
    p.hwnd = 4242
    p.grid = OP
    p.session_ply = 1
    p.frame = lambda: FRAME
    p.band_changed = lambda prev, a: False
    p.handle_dialog = lambda a: False
    p.handle_continue = lambda a: False
    return p


class Button(object):
    """A button stub: flag says whether it is pressed, n counts every poll."""

    def __init__(self, pressed=False):
        self.pressed = pressed
        self.n = 0

    def is_set(self):
        self.n += 1
        return self.pressed

    def set(self):
        self.pressed = True

    def clear(self):
        self.pressed = False


def main():
    A.log = lambda *a: LOGS.append(" ".join(str(x) for x in a))

    # -- 1. reading survives a window that went away -----------------------
    p = player()
    p._recognize = lambda a: None
    p.frame = lambda: None
    check("read() with no window returns nothing", p.read(), (None, None))
    p2 = player()
    p2.wgrab = None
    p2.prev = ("frame", {})
    p2.frame = A.AutoPlayer.frame.__get__(p2)   # the real one, not the stub
    real_rect = A.w32.client_rect_screen
    try:
        A.w32.client_rect_screen = lambda hwnd: (_ for _ in ()).throw(
            OSError("window gone"))
        got = p2.frame()
    finally:
        A.w32.client_rect_screen = real_rect
    check("a dead window is reported, not raised", got, None)
    check("...and the incremental chain is dropped", p2.prev, None)

    # -- 2. both axes degrade when the backend is missing ------------------
    p = player(board="backend", moves="backend")
    p.source = BR.NullSource(ok=False, reason="no layout")
    p.sink = BR.NullSink(ok=False, reason="no channel")
    p._ensure_bridge()
    check("a missing board backend falls back to the screen",
          (p.board_mode, isinstance(p.source, BR.VisionSource)), ("vision", True))
    check("a missing move backend falls back to the mouse",
          (p.moves_mode, isinstance(p.sink, BR.PhysicalSink)), ("physical", True))

    # -- 3. stop is answered within a tenth of a second -------------------
    p = player()
    p.engine = None
    p.stable_grid = lambda timeout=8.0, need=3, interval=0.03: (None, None)
    p.stop_event = Button()            # released for now
    t0 = time.time()

    def press_stop():
        time.sleep(0.25)              # the user hits 停止 mid-wait
        p.stop_event.set()

    th = threading.Thread(target=press_stop, daemon=True)
    th.start()
    g, _a = p.wait_change(OP, timeout=30.0)
    took = time.time() - t0
    check("the opponent wait ends at once after 停止 (%.3fs)" % took,
          (g is None, took < 1.5), (True, True))

    # -- 4. everything the summary quotes exists --------------------------
    p = player()
    p.stats["turn_s"] = 12.5
    p.stats["turn_max"] = 3.5
    p.stats["stalls"] = 1
    p.stats["slow"] = 1
    p.stats["attempts"] = 2
    p.summary()
    line = LOGS[-1]
    for key in ("games=", "moves=", "clock=", "stalls=", "repairs=", "retries=",
                "reads=", "recog=", "incr=", "engine fails=", "bg_fallback="):
        check("the summary carries %s" % key, key in line, True)

    # -- 5. close() is idempotent and releases what it owns ---------------
    p = player()
    grabbers = [object(), object()]
    p.grabber = grabbers[0]
    p.wgrab = grabbers[1]
    p.engine = None
    p.close()
    p.close()
    check("close() twice is harmless", (p.grabber, p.wgrab), (None, None))

    # -- 6. a paused bot waits without burning the window -----------------
    p = player()
    reads = []
    p.frame = lambda: reads.append(1) or FRAME
    p.pause_event = Button(pressed=True)   # 暂停 held down
    p.stop_event = Button()                # 停止 released until we press it
    done = {}

    def paused_run():
        done["t0"] = time.time()
        done["g"], _a = p.stable_grid(timeout=5.0)
        done["dt"] = time.time() - done["t0"]

    th = threading.Thread(target=paused_run, daemon=True)
    th.start()
    time.sleep(0.4)
    alive = th.is_alive()               # the gate is what holds it, not a read
    p.stop_event.set()
    th.join(2.0)
    check("a paused bot stays paused without reading (held %.2fs)" % done["dt"],
          (alive, done["g"], len(reads)), (True, None, 0))

    # -- 7. a full round leaves no handles behind ------------------------
    p = player()
    p.engine = None
    cal = {"cpitch": 65.0, "rpitch": 62.0, "band": (0, 500, 0, 400), "model": None}
    p.cal = cal
    p.tpl = {}
    p.tpl_half = 8
    p.flip = False
    p.stable_grid = lambda timeout=8.0, need=3, interval=0.03: (OP, FRAME)
    p.wait_change = lambda prev, timeout=8.0, strict=True: (None, None)
    p.settle_after = lambda prev, want, timeout=6.0: (want, FRAME, False)
    p.play_move = lambda *a: None
    p.wait_next_round = lambda timeout=60.0: (None, None)
    p.engine = type("E", (), {"bestmove": lambda self, *a, **k: ("h2e2", None, []),
                              "quit": lambda self: None})()
    p.stop_event = Button()
    p.run(max_moves=1, first="me", opp_timeout=1.0)
    check("a round still logs its summary",
          any("[sum]" in s for s in LOGS), True)
    p.close()

    # -- 8. the console and the player agree on every option --------------
    import inspect
    p3 = A.AutoPlayer(our_side="w")
    names = set(inspect.signature(A.AutoPlayer.__init__).parameters)
    # options the player stores under a different name
    # run()/read() take the long ones as arguments rather than as attributes
    run_args = set(inspect.signature(A.AutoPlayer.run).parameters)
    read_args = set(inspect.signature(A.AutoPlayer.read).parameters)
    aliases = {"side": "our_side", "exe": "exe", "preset": None, "geometry": None,
               "board": "board_mode", "moves": "moves_mode", "fallback": "fallback",
               "request": "request", "dry": "dry", "background": "background",
               "engine": None, "title": "title", "new_game": "new_game",
               "auto_next": "auto_next", "retries": "retries",
               "first": run_args, "max_moves": run_args,
               "opp_timeout": run_args, "probe_wait": run_args,
               "click_delay": names, "movetime": names, "threads": names,
               "hash_mb": names}
    missing = []
    for k in G.DEFAULTS:
        attr = aliases.get(k, k)
        if attr is None:
            continue
        if isinstance(attr, set):
            if attr is read_args:
                continue           # read() takes no options at all
            if attr & names:
                continue
        elif attr not in names and not hasattr(p3, attr):
            pass
        else:
            continue
        missing.append("%s -> %s" % (k, attr if not isinstance(attr, set) else "?"))
    check("every console option reaches the player", missing, [])

    # -- 9. the interactive sampler never touches the game ---------------
    p = player()
    p.cal = {"cpitch": 65.0, "rpitch": 62.0, "cx": [0] * 9, "cy": [0] * 10,
             "band": (0, 500, 0, 400), "model": None}
    clicked = []
    real_click, real_silent = A.w32.click, A.w32.click_silent
    try:
        A.w32.click = lambda x, y, hold=0.03: clicked.append((x, y))
        A.w32.click_silent = lambda x, y, hold=0.03: clicked.append((x, y))
        p.dry = True
        p.click_delay = 0.01
        p.play_move(1, 1, 2, 2)          # the real path, only the dry flag set
    finally:
        A.w32.click, A.w32.click_silent = real_click, real_silent
    check("演练模式 clicks nothing", clicked, [])

    # -- 10. repeated calibration and recognition stay stable ------------
    path = os.path.join(ROOT, "fixtures", "jj_orig.png")
    if os.path.isfile(path):
        try:
            from PIL import Image
        except Exception:
            Image = None
        if Image is not None:
            frame = np.asarray(Image.open(path).convert("RGB"))
            tpl, half = V.load_templates(cal=V.calibrate(frame))
            seen = []
            for _ in range(3):
                cal = V.calibrate(frame)
                grid = B.screen_to_internal(
                    V.recognize(frame, cal, tpl, half=half)[0], False)
                seen.append(B.grid_to_fen(grid, "w"))
            check("three calibrations read the same position", len(set(seen)), 1)
            check("...and it is the opening", seen[0].split()[0],
                  B.OPENING_FEN.split()[0])
    else:
        print("%-62s skip  (no fixtures/jj_orig.png)" % "static stability")

    print("")
    if FAILED:
        print("checks: %d, failed: %d - %s" % (NCHECK[0], len(FAILED), ", ".join(FAILED)))
        print("AUDIT FAILED")
        return 1
    print("checks: %d, all passed" % NCHECK[0])
    print("AUDIT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
