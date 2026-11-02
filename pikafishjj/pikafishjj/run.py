# -*- coding: utf-8 -*-
"""pikafishjj - drive the JJ Xiangqi mini-program with the Pikafish engine."""
import argparse
import sys
import time

import numpy as np

from . import w32
from . import vision as V
from . import board as B
from .auto import AutoPlayer, DEFAULT_EXE, log
from .engine import Engine, last_info


def cmd_probe(args):
    w32.set_dpi_aware()
    hwnd, title = w32.find_window(args.title)
    if not hwnd:
        log("window not found")
        return 1
    x, y, w, h = w32.client_rect_screen(hwnd)
    log("hwnd %s title %s" % (hwnd, title))
    log("client rect on screen: %d,%d %dx%d" % (x, y, w, h))
    a = None
    if args.background:
        # PrintWindow still renders a window that other windows cover
        a = w32.WindowGrabber().grab(hwnd)
        if a is None:
            log("PrintWindow returned nothing (minimised?) - screen grab instead")
    if a is None:
        a = w32.ScreenGrabber().grab(x, y, w, h)
    cal = V.calibrate(a, verbose=True)
    if not cal:
        log("calibration FAILED")
        return 2
    # Always prefer the packed templates: building them from *this* frame only
    # works when the board still sits on the opening, and silently degrades into
    # reading red pieces as black ones once the game has moved on.
    tpl, half = V.load_templates(cal=cal)
    if tpl:
        log("template pack: " + ", ".join(
            "%s x%d" % (t, len(v)) for t, v in sorted(tpl.items())))
    else:
        log("no template pack - extracting from this frame")
        tpl, half = V.build_templates(a, cal, verbose=True), V.TPL_HALF
    scr, sc = V.recognize(a, cal, tpl, half=half)
    flip = B.detect_flip(scr)
    grid = B.screen_to_internal(scr, flip)
    log(V.draw_grid(grid))
    log("flip=%s" % flip)
    log("our side (auto): %s" % ("red" if not flip else "black"))
    log("FEN " + B.grid_to_fen(grid, "w"))
    return 0


def cmd_play(args):
    p = AutoPlayer(exe=args.exe, movetime=args.movetime, threads=args.threads,
                   hash_mb=args.hash, title=args.title, our_side=args.side,
                   dry=args.dry, background=args.background,
                   request=args.request, new_game=args.new_game,
                   retries=args.retries, auto_next=args.auto_next,
                   board=args.board, moves=args.moves, fallback=args.fallback)
    try:
        p.attach(wait=True)
        if not args.dry:
            p.start_engine()
        else:
            log("[dry] engine disabled; moves will be printed only")
        p.run(max_moves=args.max_moves, first=args.first)
    finally:
        p.close()
    return 0


def cmd_ui(args):
    from . import gui
    return gui.main()


def cmd_selftest(args):
    """Check the pieces a packaged build must carry: templates, engine, vision."""
    ok = True
    tpl, half = V.load_templates()
    if tpl:
        log("[1/3] templates OK: %s" % V.find_templates())
        log("      %d classes, %d variants, patch half %d" % (
            len(tpl), sum(len(v) for v in tpl.values()), half))
    else:
        ok = False
        log("[1/3] templates MISSING - looked for %s" % V.find_templates())
    log("[2/3] engine %s" % args.exe)
    best = None
    eng = None
    for attempt in (1, 2):
        try:
            eng = Engine(args.exe, threads=args.threads, hash_mb=args.hash)
            log("      name: %s" % eng.name)
            best, ponder, info = eng.bestmove(B.OPENING_FEN, movetime=args.movetime)
            d = last_info(info)
            log("      bestmove %s (ponder %s) depth=%s score=%s nodes=%s nps=%s" % (
                best, ponder, d.get("depth"), d.get("score"), d.get("nodes"),
                d.get("nps")))
            eng.quit()
            break
        except Exception as exc:
            # First run after an extraction can be slowed down by the antivirus.
            log("      attempt %d failed: %s: %s" % (attempt, type(exc).__name__, exc))
            best = None
            try:
                eng.quit()
            except Exception:
                pass
            time.sleep(1.0)
    if not best or len(best) < 4:
        ok = False
        log("      engine FAILED - no usable move")
    else:
        log("      engine OK")
    a = None
    if args.frame:
        try:
            from PIL import Image
            a = np.asarray(Image.open(args.frame).convert("RGB"))
        except Exception as exc:
            log("[3/3] cannot read the frame %s: %s" % (args.frame, exc))
    if a is None and not args.frame:
        w32.set_dpi_aware()
        hwnd, title = w32.find_window(args.title)
        if hwnd:
            x, y, w, h = w32.client_rect_screen(hwnd)
            a = w32.ScreenGrabber().grab(x, y, w, h)
            log("[3/3] grabbed the live window %dx%d at (%d,%d)" % (w, h, x, y))
    if a is None:
        log("[3/3] vision skipped: no frame given and no window matching %r" % args.title)
    else:
        cal = V.calibrate(a)
        if not cal or not tpl:
            ok = False
            log("[3/3] vision FAILED: no board in this frame")
        else:
            # The pack is scaled to the board pitch, so it must be loaded with
            # *this* frame's calibration: the unscaled pack (half 23) only fits a
            # board at the reference pitch and misreads a smaller one (the 601px
            # result screen read 22 pieces with swapped colours instead of 27).
            tpl_c, half_c = V.load_templates(cal=cal)
            if not tpl_c:
                tpl_c, half_c = tpl, half
            g, sc = V.recognize(a, cal, tpl_c, half=half_c)
            flip = B.detect_flip(g)
            grid = B.screen_to_internal(g, flip)
            log("[3/3] board OK: %d pieces, red %s" % (
                sum(1 for row in grid for c in row if c != "."),
                "at the bottom" if not flip else "at the top"))
            log("      FEN " + B.grid_to_fen(grid, "w"))
            # The rules gate is part of what a build has to prove: a reader that
            # hands the engine an impossible position loses the engine (Pikafish
            # exits on one), so say here whether this frame's read obeys the rules.
            pos_ok, why = B.position_ok_read(grid)
            log("      the rules %s" % ("accept this position" if pos_ok
                                        else "REJECT it: " + why))
            if not pos_ok:
                ok = False
    log("SELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 3


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pikafishjj")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("ui", help="open the tkinter console").set_defaults(func=cmd_ui)
    pr = sub.add_parser("probe", help="capture + calibrate + recognise once")
    pr.add_argument("--title", default="JJ")
    pr.add_argument("--background", action="store_true",
                    help="read through PrintWindow so a covered window works")
    pr.set_defaults(func=cmd_probe)

    st = sub.add_parser("selftest", help="check templates + engine + vision")
    st.add_argument("--exe", default=DEFAULT_EXE)
    st.add_argument("--title", default="JJ")
    st.add_argument("--frame", default=None, help="use this PNG instead of the window")
    st.add_argument("--threads", type=int, default=2)
    st.add_argument("--hash", type=int, default=128)
    st.add_argument("--movetime", type=int, default=800)
    st.set_defaults(func=cmd_selftest)

    pl = sub.add_parser("play", help="play automatically")
    pl.add_argument("--exe", default=DEFAULT_EXE)
    pl.add_argument("--movetime", type=int, default=2000)
    pl.add_argument("--threads", type=int, default=8)
    pl.add_argument("--hash", type=int, default=1024)
    pl.add_argument("--title", default="JJ")
    pl.add_argument("--max-moves", type=int, default=200,
                    help="how many of our own plies to play at most")
    pl.add_argument("--first", choices=["me", "them"], default=None)
    pl.add_argument("--side", choices=["auto", "w", "b"], default="auto",
                    help="auto = the army on the lower half is ours")
    pl.add_argument("--dry", action="store_true")
    pl.add_argument("--background", action="store_true",
                    help="read the board while the window is covered"
                    " and click without taking the foreground")
    pl.add_argument("--no-new-game", dest="new_game", action="store_false",
                    help="stop when the board resets to the starting position "
                         "instead of playing the next round")
    pl.add_argument("--request", choices=["decline", "accept", "off"],
                    default="decline",
                    help="answer to the opponent's draw / undo request"
                    " (default: decline)")
    pl.add_argument("--no-auto-next", dest="auto_next", action="store_false",
                    help="never press the result screen's 再来一局 button")
    pl.add_argument("--board", choices=["vision", "backend"], default="vision",
                    help="where the position comes from: screenshot recognition (vision) "
                         "or the mini-program's own memory (backend)")
    pl.add_argument("--moves", choices=["physical", "backend"], default="physical",
                    help="how our move is delivered: mouse clicks (physical) or the "
                         "program's own channel (backend)")
    pl.add_argument("--no-fallback", dest="fallback", action="store_false",
                    help="fail instead of falling back when a backend half is not ready")
    pl.add_argument("--retries", type=int, default=3,
                    help="how often a failed ply (swallowed click, dead engine,"
                         " unreadable board) is retried before watching only")
    pl.set_defaults(func=cmd_play)

    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
