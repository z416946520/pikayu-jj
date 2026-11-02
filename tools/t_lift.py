# -*- coding: utf-8 -*-
"""The lifted red rook, and the gate that keeps impossible boards off the engine.

Field log 2026-10-14 (pikafishjj-log(4).txt): the last round ended with the app
drawing the red rook on a9 *lifted* - 22px above its intersection, about 1.2x the
usual disc, over the background behind the board, ringed as the highlighted
piece.  The matcher is grayscale and searches +-16px, so that square read as a
black pawn, then a black rook, then a red advisor; the position left for the
engine was impossible, Pikafish answered "CRITICAL ERROR ... Unsupported
position" and exited three times, and the loop died on top of it with
AttributeError: 'NoneType' object has no attribute 'get' (auto.py:1807).

Three things are pinned here:

  * the corner rook still reads as a RED rook (its ink is red even at 1.2x),
  * a board the rules cannot reach is refused before it is ever sent,
  * and the engine's own refusal comes back as EngineRefusal, not a dead process.

Run:  python tools\\t_lift.py      (exits non-zero on any mismatch)
"""
import os
import sys

sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402
from pikafishjj import board as B, engine as E, vision as V   # noqa: E402

ROOT = r"D:\BuildProject\pikayu-jj"
FIX = os.path.join(ROOT, "fixtures")
EXE = os.path.join(ROOT, "pikafish", "Pikafish-Windows-x86-64-universal.exe")

# the position the screenshot shows, read by a human: the red rook sits on a9
CORRECT = "R8/4k4/3ab4/8p/9/1c6r/9/4B4/2nCA4/3K5 w - - 0 1"
# what the reader produced for the same frame before the fix, in the two variants
# that are impossible for the rules: a black pawn behind its start, and a red
# advisor outside its palace.  (A third variant read a *black* rook there, which
# is a legal board - only the colour is wrong - so the rules cannot catch it; the
# read itself has to, and that is what the checks below pin.)
IMPOSSIBLE = ("p8/4k4/3ab4/8p/9/1c6r/9/4B4/2nCA4/3K5 w - - 0 1",
              "A8/4k4/3ab4/8p/9/1c6r/9/4B4/2nCA4/3K5 w - - 0 1")
# ...written with both flips still held from the finished round
COLOUR_WRONG = "r8/4k4/3ab4/8p/9/1c6r/9/4B4/2nCA4/3K5 w - - 0 1"

BAD = []
CHECKS = 0


def check(name, got, want):
    global CHECKS
    CHECKS += 1
    ok = (got == want)
    if not ok:
        BAD.append(name)
    print("%-58s %-4s %r" % (name, "ok" if ok else "FAIL", got))
    if not ok:
        print("%-58s want %r" % ("", want))
    return ok


def frame(name):
    return np.asarray(Image.open(os.path.join(FIX, name)).convert("RGB"))


def read(name):
    a = frame(name)
    cal = V.calibrate(a, verbose=False)
    tpl, half = V.load_templates(cal=cal)
    g, _sc = V.recognize(a, cal, tpl, half=half)
    return a, cal, tpl, half, g


def main():
    # 1. the lifted red rook reads as a red rook -----------------------------
    a, cal, tpl, half, g = read("jj_endgame1.png")
    fen = B.grid_to_fen(g, "w")
    check("the endgame frame reads as the position on screen", fen, CORRECT)
    check("...with a RED rook on a9", g[0][0], "R")
    check("...and every other square right",
          B.grid_to_fen(g, "w") == CORRECT, True)
    # and the piece is genuinely lifted: the model centre is not on the disc
    x, y = V.grid_xy(cal, 0, 0)
    ref = V.tile_colour(a, cal.get("band"))
    dsc, px, py = V._disc_near(a, x, y, ref)
    check("...the disc really is drawn away from its intersection",
          round(py - y) < -12, True)
    # the ink measure: red piece red, black piece dark, at the disc and off it
    p_red = V._frame_patch(a, px, py, half)
    p_black = V._frame_patch(a, *V.grid_xy(cal, 8, 5), half)
    check("the lifted rook's ink reads red", V.ink_side(p_red, half), "w")
    check("a black rook's ink reads dark", V.ink_side(p_black, half), "b")

    # 2. the wrong reads are refused, the right one is not -------------------
    for fen_wrong in IMPOSSIBLE:
        gr = B.fen_to_grid(fen_wrong)
        check("refused: %s" % fen_wrong[:20], B.position_ok(gr, "w")[0], False)
        check("...for whichever side is to move",
              B.position_ok_any_side(gr)[0], False)
        check("...and with the board turned round",
              B.position_ok_read(gr)[0], False)
    gr = B.fen_to_grid(CORRECT)
    check("the position on screen is accepted", B.position_ok(gr, "w")[0], True)
    check("...and by the side-less read gate", B.position_ok_any_side(gr)[0], True)
    check("...and by the orientation-tolerant read gate",
          B.position_ok_read(gr)[0], True)
    opening = B.fen_to_grid(B.OPENING_FEN)
    check("the opening position is accepted", B.position_ok(opening, "w")[0], True)
    # the colour-flipped variant is legal, so the gate must NOT claim otherwise:
    # the reader has to get the colour right, and it does (checked above)
    check("a colour-flipped but legal board is not the gate's business",
          B.position_ok(B.fen_to_grid(COLOUR_WRONG), "w")[0], True)
    # a rules check the reader used to walk straight into: generals facing
    facing = B.fen_to_grid("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1")
    check("facing generals are refused", B.position_ok(facing, "w")[0], False)
    check("...even without a side", B.position_ok_any_side(facing)[0], False)
    # the round that follows a colour swap arrives turned, and must be accepted
    turned_new = B.turned(opening)
    check("a turned real board still reads as a board",
          B.position_ok_read(turned_new)[0], True)
    check("...while the strict move gate refuses it as it stands",
          B.position_ok(turned_new, "w")[0], False)

    # 3. the engine's refusal is told apart from a dead engine ---------------
    if os.path.isfile(EXE):
        eng = E.Engine(EXE, threads=1, hash_mb=16)
        try:
            refused = None
            try:
                eng.bestmove(IMPOSSIBLE[0], movetime=60)
            except E.EngineRefusal as exc:
                refused = str(exc)
            except Exception as exc:                   # a plain EngineError is a miss
                refused = None
                print("    (engine raised %s: %s)" % (type(exc).__name__, exc))
            check("Pikafish's refusal comes back as EngineRefusal",
                  bool(refused and "refused the position" in refused), True)
        finally:
            try:
                eng.quit()
            except Exception:
                pass
        eng2 = E.Engine(EXE, threads=1, hash_mb=16)
        try:
            bm = eng2.bestmove(CORRECT, movetime=200)[0]
            check("...and a legal position still searches", bool(bm and len(bm) >= 4), True)
        finally:
            try:
                eng2.quit()
            except Exception:
                pass
    else:
        print("engine not found at %s - skipping the refusal checks" % EXE)

    print()
    print("checks: %d, failed: %d - %s" % (CHECKS, len(BAD), ", ".join(BAD) or "none"))
    print("LIFT OK" if not BAD else "LIFT FAILED")
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
