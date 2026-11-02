
# -*- coding: utf-8 -*-
"""tools/t_newgame.py - the round-restart bookkeeping of AutoPlayer.

Drives the continuity helpers with synthetic grids (no window, no engine):
a board that snaps back to the starting position must reset the session and
pick the side up from the frame itself, because ranked play swaps colours.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pikafishjj import auto as A
from pikafishjj import board as B

MID = "r1bakabnr/9/1cn2c3/p1p1p1p1p/9/2P6/P3P1P1P/1CN2C3/9/R1BAKABNR w - - 0 1"
OP = B.fen_to_grid(B.OPENING_FEN)   # new_grid() is the *empty* board
MIDG = B.fen_to_grid(MID)
MIDG2 = B.fen_to_grid("r1bakabnr/9/1cn2c3/p1p1p1p1p/9/2P6/P3P1P1P/1CN2C3/4K4/R1BA1ABNR w - - 0 1")
BAD = []


def check(name, got, want):
    ok = got == want
    if not ok:
        BAD.append(name)
    print("%-46s %-6s %s" % (name, "ok" if ok else "FAIL",
                             "" if ok else "got %r want %r" % (got, want)))


def player(flip=True, side="b", new_game=True, session=7, grid=None, scr=None):
    p = A.AutoPlayer.__new__(A.AutoPlayer)
    p.stats = {"games": 1, "moves": 9, "dialogs": 3}
    p.grid = MIDG if grid is None else grid
    p.session_ply = session
    p.hints = {(1, 2): (3, 4)}
    p.prev = ("frame", {"changed": 0})
    p._dlg_t = 9.0
    p._dlg_skip_t = 0.0
    p._dlg_seen = None
    p._rematch_t = 0.0
    p.auto_next = True
    p.dry = True
    p.request = "decline"
    p.flip = flip
    p.side_auto = True
    p.our_side = side
    p.new_game = new_game
    p.scr = scr
    p.verbose = True
    return p


# a screen grid drawn with red at the bottom (flip False) / at the top (True)
SCR_RED_BOTTOM = B.screen_to_internal(OP, False)
SCR_RED_TOP = B.screen_to_internal(OP, True)

# 1. an untouched opening is not a restart
p = player(session=0, grid=OP, scr=SCR_RED_BOTTOM)
check("opening with no ply played -> not a restart", p.is_new_game(OP), False)
check("...and an ordinary update stores it", p.set_grid(OP), None)
check("...without fabricating a round", p.stats["games"], 1)
check("is_new_game(None)", p.is_new_game(None), False)

# 2. the same position after any ply is a fresh round (colours swapped)
p = player(flip=True, side="b", scr=SCR_RED_BOTTOM)
check("opening after 7 plies -> restart", p.is_new_game(OP), True)
check("set_grid reports the new round", p.set_grid(OP), "new")
check("round counter", p.stats["games"], 2)
check("our-move counter cleared", p.stats["moves"], 0)
check("session counter cleared", p.session_ply, 0)
check("incremental chain dropped", p.prev, None)
check("click hints dropped", p.hints, {})
check("orientation taken from the frame", p.flip, False)
check("auto side re-derived", p.our_side, "w")
check("grid adopted", p.grid, OP)

# 3. the other way round: we are black again
p = player(flip=False, side="w", scr=SCR_RED_TOP)
check("set_grid reports the new round (black)", p.set_grid(OP), "new")
check("orientation flipped for black", p.flip, True)
check("auto side re-derived (black)", p.our_side, "b")

# 4. a fixed side is never overridden
p = player(flip=True, side="b", scr=SCR_RED_BOTTOM)
p.side_auto = False
p.set_grid(OP)
check("a manually chosen side survives", p.our_side, "b")

# 5. the feature can be switched off: adopt the board, stop the run
p = player(new_game=False, scr=SCR_RED_BOTTOM)
check("switched off -> stop", p.set_grid(OP), "stop")
check("...but the board is still adopted", p.grid, OP)
check("...and the round is not counted", p.stats["games"], 1)
check("...session counter reset", p.session_ply, 0)

# 6. ordinary plies just advance the session
p = player(session=1, scr=None)
check("an ordinary ply", p.set_grid(MIDG2), None)
check("session advanced", p.session_ply, 2)
check("grid adopted", p.grid, MIDG2)
check("a repeated reading does not advance it", p.set_grid(MIDG2), None)
check("session still", p.session_ply, 2)

# 7. ranked play swaps colours: the next round is read with the old flip
MIRROR_OP = B.screen_to_internal(SCR_RED_TOP, False)    # what a stale flip reads
p = player(flip=False, side="w", scr=SCR_RED_TOP)
check("an upside-down opening is a fresh round too", p.is_new_game(MIRROR_OP), True)
check("...set_grid reports it as new", p.set_grid(MIRROR_OP), "new")
check("...orientation corrected from the frame", p.flip, True)
check("...and the side re-derived (black)", p.our_side, "b")
check("...canonical opening adopted", p.grid, OP)
check("...the round is counted", p.stats["games"], 2)
check("...session reset", p.session_ply, 0)

# 8. a round we started ourselves is adopted even with a ply already played
OP1 = B.apply_move(B.clone(OP), ((7, 7), (4, 7), OP[7][7], OP[7][4]))
SCR1 = B.screen_to_internal(OP1, True)                  # now drawn red at the top
READ1 = B.screen_to_internal(SCR1, False)               # as the old flip reads it
p = player(flip=False, side="w", scr=SCR1)
p._rematch_t = time.time()
check("a pressed 再来一局 opens the window", p.waiting_new_round(), True)
check("...the board we get is not the opening", p.is_new_game(READ1), False)
check("...but it is adopted as the new round", p.set_grid(READ1), "new")
check("...orientation corrected", p.flip, True)
check("...the frame is the authority", p.grid, OP1)
check("...the window closes once adopted", p.waiting_new_round(), False)

# 9. a stale press must not swallow later boards
p = player(flip=False, side="w", scr=SCR1)
p._rematch_t = time.time() - (A.AutoPlayer.NEW_ROUND_WINDOW + 5.0)
check("an expired rematch window is shut", p.waiting_new_round(), False)
check("...and an ordinary board stays ordinary", p.set_grid(READ1), None)

# 10. the new-game option still wins over our own 再来一局
p = player(flip=False, side="w", scr=SCR1, new_game=False)
p._rematch_t = time.time()
check("a pressed 再来一局 still stops when asked", p.set_grid(READ1), "stop")

# 11. a request panel has to stay on screen for a whole second before it is
# answered - one transition frame after 再来一局 used to be clicked at (measured
# in the field twice: two frames in a row passed the old two-frame gate)
DLG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "fixtures", "dlg_fixture.png")
frame = None
try:
    import numpy as np
    from PIL import Image
    frame = np.asarray(Image.open(DLG).convert("RGB"))
except Exception as exc:
    BAD.append("dlg_fixture unreadable")
    print("%-46s %-6s %s" % ("a request panel fixture", "FAIL", exc))
if frame is not None:
    p = player(session=1)
    p.stats["dialogs"] = 0
    check("the first sighting of a request panel", p.handle_dialog(frame), True)
    check("...is not answered yet", p.stats["dialogs"], 0)
    check("a second sighting is still not enough", p.handle_dialog(frame), True)
    check("...and nothing is clicked", p.stats["dialogs"], 0)
    t0 = time.time()
    while time.time() - t0 < 6.0 and p.stats["dialogs"] == 0:
        time.sleep(0.3)
        p.handle_dialog(frame)
    check("a panel that stays put is confirmed (%.1fs)" % (time.time() - t0),
          p.stats["dialogs"], 1)
    check("...and the request is counted", p.stats["dialogs"], 1)
    p.handle_dialog(frame)
    check("...still one request handled", p.stats["dialogs"], 1)
    p._dlg_skip_t = time.time() + 5.0
    check("right after 再来一局 nothing is believed", p.handle_dialog(frame), False)
    p._dlg_skip_t = 0.0
    p._dlg_seen = None
    check("...and it is answered again afterwards", p.handle_dialog(frame), True)

print("")
if BAD:
    print("NEWGAME FAILED: " + ", ".join(BAD))
    sys.exit(1)
print("NEWGAME OK")
