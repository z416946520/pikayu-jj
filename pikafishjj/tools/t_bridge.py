# -*- coding: utf-8 -*-
"""The two axes: board source (vision / backend) and move sink (physical / backend).

The backend halves are still being built, so what matters here is that the switch
works, that an unfinished backend half never blocks a run (it falls back, with a
reason in the log), that --no-fallback fails loudly, and that the memory reader
already decodes a located layout correctly.

Run:  python pikafishjj\tools\t_bridge.py
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
from pikafishjj import bridge as BR

OP = B.fen_to_grid(B.OPENING_FEN)
OP2 = B.apply_move(B.clone(OP), ((2, 6), (2, 5), OP[6][2], "."))
LOGS = []
FAILED = []
NCHECK = [0]
CODES = {"K": 1, "A": 2, "B": 3, "N": 4, "R": 5, "C": 6, "P": 7,
         "k": 8, "a": 9, "b": 10, "n": 11, "r": 12, "c": 13, "p": 14}


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


def encode(grid):
    """A 90-cell row-major screen array for *grid* (red drawn at the bottom)."""
    out = []
    for j in range(10):
        for i in range(9):
            out.append(CODES.get(grid[j][i], 0))
    return bytes(out)


def player(**kw):
    p = A.AutoPlayer(our_side="w", verbose=True, **kw)
    p.grid = OP
    p.session_ply = 1
    return p


def main():
    A.log = lambda *a: LOGS.append(" ".join(str(x) for x in a))

    # -- 1. the shipped pair is the default ---------------------------------
    p = player()
    check("default board source is vision", p.board_mode, "vision")
    check("default move sink is physical", p.moves_mode, "physical")
    check("...and the objects match", (isinstance(p.source, BR.VisionSource),
                                       isinstance(p.sink, BR.PhysicalSink)), (True, True))
    check("a vision run needs no bridge resolution", p._ensure_bridge(), None)
    check("...and logs which source it uses", logged("board: vision"), True)

    # -- 2. a backend half that is not ready falls back with a reason -------
    del LOGS[:]
    p = player(board="backend", moves="backend")
    p.source = BR.NullSource(ok=False, reason="no layout cached")
    p.sink = BR.NullSink(ok=False, reason="no channel ready")
    p._ensure_bridge()
    check("an unfinished backend board source falls back", p.board_mode, "vision")
    check("...saying why", logged("no layout cached"), True)
    check("an unfinished backend move channel falls back", p.moves_mode, "physical")
    check("...saying why", logged("no channel ready"), True)
    check("...and the objects were swapped",
          (isinstance(p.source, BR.VisionSource), isinstance(p.sink, BR.PhysicalSink)),
          (True, True))

    # -- 3. no-fallback fails loudly instead --------------------------------
    del LOGS[:]
    p = player(board="backend", fallback=False)
    p.source = BR.NullSource(ok=False, reason="no layout cached")
    raised = None
    try:
        p._ensure_bridge()
    except BR.BridgeUnavailable as exc:
        raised = str(exc)
    check("without fallback the missing backend is an error",
          bool(raised) and "no layout cached" in raised, True)
    p2 = player(moves="backend", fallback=False)
    p2.sink = BR.NullSink(ok=False, reason="no channel ready")
    raised2 = None
    try:
        p2._ensure_bridge()
    except BR.BridgeUnavailable as exc:
        raised2 = str(exc)
    check("...for the move channel too",
          bool(raised2) and "no channel ready" in raised2, True)

    # -- 4. board reads go through the selected source ----------------------
    p = player(board="backend")
    p.source = BR.NullSource(grid=OP2, ok=True)
    g, a = p.stable_grid(timeout=1.0)
    check("a backend source answers stable_grid", g, OP2)
    check("...and was asked exactly once", p.source.reads, 1)
    p.source = BR.VisionSource()
    p._vision_stable_grid = lambda timeout=8.0, need=3, interval=0.03: (OP, "frame")
    g2, a2 = p.stable_grid(timeout=1.0)
    check("a vision source still uses the screenshot path", (g2, a2), (OP, "frame"))

    # -- 5. moves go through the selected sink ------------------------------
    p = player(moves="backend")
    p.sink = BR.NullSink(ok=True)
    called = []
    p._physical_play = lambda fi, fj, ti, tj: called.append((fi, fj, ti, tj))
    p.play_move(7, 7, 4, 7)
    check("a backend sink receives the move", p.sink.moves, [(7, 7, 4, 7)])
    check("...and the mouse is not touched", called, [])
    p.sink = BR.PhysicalSink()
    p.play_move(7, 7, 4, 7)
    check("the physical sink still clicks", called, [(7, 7, 4, 7)])

    # -- 6. the memory reader decodes a located layout ----------------------
    tmp = tempfile.mkdtemp(prefix="jjbridge")
    path = os.path.join(tmp, BR.LAYOUT_NAME)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"appid": BR.APPID, "pid": 1234, "base": 4096, "stride": 1,
                   "order": "row", "flip_rows": False, "flip_cols": False,
                   "empty": 0, "codes": CODES}, fh)
    asked = {}
    blob = encode(OP)

    def reader(pid, base, size):
        asked["call"] = (pid, base, size)
        return blob

    src = BR.MemorySource(reader=reader, path=path, pid=1234)
    check("a cached layout makes the memory source available",
          src.available(None), (True, ""))
    check("...it starts", src.start(None), True)
    g, _a = src.read(player(), timeout=0.5)
    check("...and decodes them back to the board", g, OP)
    check("...reading exactly 90 bytes at the cached base",
          asked.get("call"), (1234, 4096, 90))

    def empty_reader(pid, base, size):
        return None

    src2 = BR.MemorySource(reader=empty_reader, path=path, pid=1234)
    src2.start(None)
    check("an unreadable process reads as no board", src2.read(player(), timeout=0.2),
          (None, None))

    # -- 7. background mode survives both backends and the fallback ----------
    class ReadyButBroken(BR.NullSource):
        def __init__(self):
            BR.NullSource.__init__(self, grid=OP, ok=True)
            self.reason = "the cached layout points at a dead process"

        def start(self, player):
            return False                      # available() said yes, start fails

    p = player(board="backend", moves="backend", background=True)
    p.source = ReadyButBroken()
    p.sink = BR.NullSink(ok=False, reason="no channel ready")
    p._ensure_bridge()
    check("a source that cannot start falls back too", p.board_mode, "vision")
    check("...and says why", logged("dead process"), True)
    check("...the move channel fell back as well", p.moves_mode, "physical")

    style = []
    p.hwnd = 1234                          # a real window is needed for the style
    A.w32.has_no_activate = lambda hwnd: False
    A.w32.set_no_activate = lambda hwnd, on=True: style.append(bool(on)) or True
    p.quiet = False
    check("a quiet run re-applies the window style", p._ensure_quiet(), True)
    check("...with WS_EX_NOACTIVATE on", style, [True])
    check("...and remembers it", p.quiet, True)
    clicked = []
    p._physical_play = lambda fi, fj, ti, tj: clicked.append((fi, fj, ti, tj))
    p.quiet = False                        # the style was lost (new window)
    p.play_move(1, 1, 2, 2)
    check("a physical click re-applies it before clicking", style[-1:], [True])
    check("...and the move still goes through", clicked, [(1, 1, 2, 2)])

    # -- 8. a window that changed size drops the fit ------------------------
    import numpy as np

    class Grab(object):
        def grab(self, *a, **kw):
            return np.zeros((100, 80, 3), dtype=np.uint8)

    p = player()
    p.hwnd = 4321
    p.grabber = Grab()
    p.wgrab = None
    p.cal = {"cpitch": 65.0, "rpitch": 62.0}
    A.w32.client_rect_screen = lambda hwnd: (10, 10, 600, 1100)
    p._client_size = (600, 1000)            # the fit was made for the smaller one
    p.frame()
    check("a bigger client area invalidates the fit", p.cal, None)
    check("...and says so", logged("the board fit is being refitted"), True)

    print("")
    if FAILED:
        print("checks: %d, failed: %d - %s" % (NCHECK[0], len(FAILED), ", ".join(FAILED)))
        print("BRIDGE FAILED")
        return 1
    print("checks: %d, all passed" % NCHECK[0])
    print("BRIDGE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())


