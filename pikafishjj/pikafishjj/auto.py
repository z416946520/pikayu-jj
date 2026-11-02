# -*- coding: utf-8 -*-
"""pikafishjj.auto - the automation loop: capture, recognise, think, click.

The loop is deliberately RESYNC-BASED: every state transition is decided by
re-reading the board from the screen and diffing it against the last known
position, never by trusting that a click did what it was supposed to do.  The
game itself enforces turn order, so a stray click while it is the opponent's
turn is harmless - which makes "just try the move and see if the board moved"
both simpler and more robust than maintaining a predicted position.
"""
import os
import shutil
import sys
import threading
import time

import numpy as np

from . import w32
from . import vision as V
from . import board as B
from . import dialog as D
from . import bridge as BR
from . import book as BK
from .engine import Engine, EngineRefusal, last_info

APP_NAME = "pikafishjj"
ENGINE_EXE = "Pikafish-Windows-x86-64-universal.exe"
ENGINE_NET = "pikafish.nnue"


def _here():
    return os.path.dirname(os.path.abspath(__file__))


def app_dir():
    """Folder the program lives in: beside the exe once frozen."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.normpath(os.path.join(_here(), os.pardir, os.pardir))


def _writable(d):
    try:
        if not os.path.isdir(d):
            os.makedirs(d)
        t = os.path.join(d, ".write-test")
        with open(t, "w") as fh:
            fh.write("x")
        os.remove(t)
        return True
    except Exception:
        return False


def user_dir():
    """A folder we are allowed to write to (config, dbg dumps, cache)."""
    d = app_dir()
    if _writable(d):
        return d
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    _writable(d)
    return d


def _install_engine(src, dst):
    """Copy the bundled engine out of the one-file archive (once)."""
    if not os.path.isdir(dst):
        os.makedirs(dst)
    for name in (ENGINE_EXE, ENGINE_NET):
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isfile(d) and os.path.getsize(d) == os.path.getsize(s):
            continue
        shutil.copy2(s, d)
    return dst


def find_engine():
    """Locate the Pikafish binary, unpacking the bundled copy on first use."""
    env = os.environ.get("PIKAFISHJJ_EXE")
    if env and os.path.isfile(env):
        return env
    dev = os.path.normpath(os.path.join(_here(), os.pardir, os.pardir, "pikafish"))
    cands = []
    if getattr(sys, "frozen", False):
        cands.append(os.path.join(app_dir(), "pikafish"))
        cands.append(os.path.join(user_dir(), "pikafish"))
    cands.append(dev)
    for c in cands:
        p = os.path.join(c, ENGINE_EXE)
        if os.path.isfile(p):
            return p
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        src = os.path.join(bundle, "pikafish")
        if os.path.isfile(os.path.join(src, ENGINE_EXE)):
            dst = os.path.join(user_dir(), "pikafish")
            try:
                _install_engine(src, dst)
            except Exception:
                return os.path.join(src, ENGINE_EXE)
            return os.path.join(dst, ENGINE_EXE)
    return os.path.join(dev, ENGINE_EXE)


DEFAULT_EXE = find_engine()
DBG_DIR = os.path.join(user_dir(), "dbg")
_last_saved = [0.0]
_SINK = [None]


def log(*a):
    """Print and, when a GUI is attached, hand the line to its log pane."""
    msg = " ".join(str(x) for x in a)
    sink = _SINK[0]
    if sink is not None:
        try:
            sink(msg)
        except Exception:
            pass
    try:
        print(msg)
        sys.stdout.flush()
    except Exception:
        pass

def save_dbg(a, tag):
    """Dump an unexpected frame (rate limited) so failures can be inspected."""
    now = time.time()
    if now - _last_saved[0] < 1.0:
        return None
    _last_saved[0] = now
    try:
        from PIL import Image
        if not os.path.isdir(DBG_DIR):
            os.makedirs(DBG_DIR, exist_ok=True)
        p = os.path.join(DBG_DIR, "%s_%s.png" % (tag, time.strftime("%H%M%S")))
        Image.fromarray(a).save(p)
        log("    [dbg] saved " + p)
        return p
    except Exception:
        return None


class AutoPlayer(object):
    def __init__(self, exe=DEFAULT_EXE, movetime=2000, threads=8, hash_mb=1024,
                 title="JJ", our_side="auto", click_delay=0.18, verbose=True,
                 dry=False, background=False, raise_click=True,
                 request="decline", new_game=True, retries=3, auto_next=True,
                 board="vision", moves="physical", fallback=True,
                 use_book=True, book_path=None,
                 log_sink=None, stop_event=None, pause_event=None):
        self.exe = exe
        self.movetime = movetime
        self.threads = threads
        self.hash_mb = hash_mb
        self.title = title
        self.our_side = our_side
        self.side_auto = (our_side == "auto")
        self.new_game = bool(new_game)   # keep playing when a round restarts
        self.session_ply = 0             # plies seen since the last fresh round
        self.click_delay = click_delay
        self.verbose = verbose
        self.dry = dry
        self.background = background
        self.raise_click = raise_click
        self._warn_t = 0.0
        self.request = request          # decline / accept / off
        # How many times a failed step is retried before the loop falls back to
        # watching the board instead of clicking.  Nothing aborts the run on the
        # first failure: a swallowed click used to end the game silently, which
        # from the outside looked exactly like the program freezing.
        self.retries = max(1, int(retries))
        # Press the result screen's 再来一局 so the next round starts by itself.
        self.auto_next = bool(auto_next)
        # The two axes of the bot: where the position comes from and how the move
        # is delivered.  "backend" halves live in bridge.py; while one of them is
        # not ready the fallback keeps the vision/physical pair running.
        self.board_mode = board if board in BR.BOARDS else "vision"
        self.moves_mode = moves if moves in BR.MOVES else "physical"
        self.fallback = bool(fallback)
        self.source = BR.make_source(self.board_mode)
        self.sink = BR.make_sink(self.moves_mode)
        # An opening book answers the first plies from the position instead of
        # searching: 0.4s of our own clock per move is pure waste at the start of
        # a round, and the log showed it being paid thousands of times.
        self.book = BK.load_book(book_path, BK.shipped_book())
        self.book_on = bool(use_book)
        self._bridge_ready = False
        self._dlg_t = 0.0
        self._next_t = 0.0
        # The transition that follows 再来一局 is not a request panel: the next
        # round is drawn for the other side and repaints for a moment, which
        # used to look like one (a stray 拒绝 click landed one second later).
        self._dlg_skip_t = 0.0           # ignore request panels until this time
        self._dlg_seen = None            # first sighting of a panel, awaiting a second
        self._rematch_t = 0.0            # when 再来一局 was pressed (0.0 = never)
        # Background clicks are the default in background mode, but a single
        # failure (someone put a window over the board, the game was minimised)
        # used to switch them off for the rest of the run - which looked exactly
        # like the program jumping to the front by itself mid-game.  Now a
        # failure suspends them for BG_RETRY_GAP seconds only.
        self.bg_ok = True
        self.bg_fail = 0
        self.bg_probe_t = 0.0
        self.quiet = False
        # Mid-run control: a small watcher aborts the engine search as soon as
        # 暂停/停止 is pressed (otherwise a stop waits out the whole think time),
        # and every sleep in the loop is sliced so the buttons answer in ~50ms.
        self._watch = None
        self._watching = False
        self._closed = False
        self.watch_buttons = True
        self._pause_abort = False
        self.wgrab = None
        self.hwnd = None
        self.origin = (0, 0)
        self.grabber = None
        self.cal = None
        self.tpl = None
        self.tpl_half = V.TPL_HALF
        self.flip = False
        self.grid = None
        self.engine = None
        self.nread = 0
        self.stop_event = stop_event
        self.pause_event = pause_event
        self.hints = {}
        self.prev = None
        self.scr = None                  # screen grid of the newest reading
        self.fp_band = (0, 0)
        self._client_size = (0, 0)          # client rect the fit was made for
        # The lattice pitch of the board we are playing on.  The result screen
        # draws the same board about 20% smaller and the fit locks onto that
        # lattice quite happily (model good, position nonsense), so a frame whose
        # board size has drifted away from ours is not read at all.
        self.pitch = None
        self._pitch_bad_since = 0.0
        self._refit_t = 0.0              # when the board fit was last refitted
        self.stats = {"moves": 0, "games": 1, "reads": 0, "recognitions": 0, "frames": 0,
                      "hint_hits": 0, "incr": 0,
                      "attempts": 0, "recover": 0, "fails": 0, "idle_waits": 0,
                      "rematch": 0, "stalls": 0,
                      "turn_s": 0.0, "turn_max": 0.0, "slow": 0,
                      "grab_ms": 0.0, "recog_ms": 0.0, "think_ms": 0.0,
                      "fen": "", "best": "", "depth": None, "score": None,
                      "nodes": None, "nps": None, "phase": "idle",
                      "bg_fallback": 0, "dialogs": 0}
        if log_sink is not None:
            _SINK[0] = log_sink

    def warn(self, msg, gap=5.0):
        """Log a repeated problem at most once every *gap* seconds."""
        now = time.time()
        if now - self._warn_t >= gap:
            self._warn_t = now
            log(msg)

    def _ensure_bridge(self):
        """Resolve the selected board source and move sink once per run.

        A backend half that is not ready is either replaced by its vision or
        physical counterpart (fallback, the default) or reported as an error, so
        the log always says which pair the bot is actually using.
        """
        if self._bridge_ready:
            return
        self._bridge_ready = True
        ok, why = self.source.available(self)
        if ok and not self.source.start(self):
            # "available" only means the channel looks usable (a cached layout, a
            # live process).  If it cannot actually start, it must fall back like
            # any other unfinished half instead of reading nothing forever.
            ok = False
            why = getattr(self.source, "reason", "the source could not start")
        if ok:
            log("[bridge] board: " + self.source.describe())
        elif self.fallback:
            log("[bridge] the %s board source is not ready (%s) - reading the board "
                "from the screen instead" % (self.board_mode, why))
            self.source = BR.VisionSource()
            self.board_mode = "vision"
        else:
            raise BR.BridgeUnavailable("board source %r is not ready: %s"
                                       % (self.board_mode, why))
        ok, why = self.sink.available(self)
        if ok and not self.sink.start(self):
            ok = False
            why = getattr(self.sink, "reason", "the channel could not start")
        if ok:
            log("[bridge] moves: " + self.sink.describe())
        elif self.fallback:
            log("[bridge] the %s move channel is not ready (%s) - clicking the board "
                "instead" % (self.moves_mode, why))
            self.sink = BR.PhysicalSink()
            self.moves_mode = "physical"
        else:
            raise BR.BridgeUnavailable("move sink %r is not ready: %s"
                                       % (self.moves_mode, why))
        if self.board_mode == "backend" or self.moves_mode == "backend":
            log("[bridge] this run uses board=%s / moves=%s - the backend half that is "
                "not ready keeps its reason in the lines above" % (self.board_mode,
                                                                   self.moves_mode))
        # A backend half must not cost the background mode: re-apply the quiet
        # window style in case attach() ran before the fallback resolved.
        self._ensure_quiet()

    # -- setup -------------------------------------------------------------
    def read_candidate(self, a, cal):
        """The internal grid *cal* reads out of *a*; None when it cannot be read.

        The calibration gate must not go through self.cal / self.tpl: the
        caller still holds the *previous* fit (attach clears both before asking),
        so recognising that way raised "TypeError: 'NoneType' object is not
        subscriptable" - which the read path logged as a vision failure and then
        reported as "no position" for a board it could read perfectly.
        """
        try:
            tpl, half = V.load_templates(cal=cal)
            if not tpl:
                tpl, half = V.build_templates(a, cal), V.TPL_HALF
            if not tpl:
                return None
            scr, _sc = V.recognize(a, cal, tpl, half=half)
        except Exception as exc:
            log("[attach] the candidate fit could not be read: %s: %s"
                % (type(exc).__name__, exc))
            return None
        flip = B.detect_flip(scr)
        if flip is None:
            flip = self.flip
        return B.screen_to_internal(scr, bool(flip))

    def readable_frame(self, a, cal):
        """True when *a* read with *cal* is a playable position (see plausible)."""
        g = self.read_candidate(a, cal)
        return g is not None and self.plausible(g)

    def _adopt_fit(self, cal, a):
        """Take *cal* as the geometry and drop everything derived from the old one."""
        self.cal = cal
        self.fp_band = V.fingerprint_band(cal, a.shape[0])
        self.prev = None        # the old chain describes the old fit
        self.hints = {}
        self.tpl = None         # the pack is scaled to the pitch: reload

    def _adopt_templates(self, a, force=False):
        """Load the template pack scaled to self.cal (rebuild it when absent).

        The pack's patch size follows the lattice pitch, so it must be reloaded
        whenever the fit changes - a pack kept from a larger board makes every
        square match a sub-sprite of the piece.
        """
        if self.tpl is not None and not force:
            return self.tpl
        tpl, half = V.load_templates(cal=self.cal)
        if not tpl:
            log("[attach] no template pack - extracting from this frame")
            tpl, half = V.build_templates(a, self.cal, verbose=True), V.TPL_HALF
        self.tpl, self.tpl_half = tpl, half
        if self.tpl:
            log("[attach] template pack: " + ", ".join(
                "%s x%d" % (t, len(v)) for t, v in sorted(self.tpl.items())))
        return self.tpl

    def _ensure_cal(self, tries=6, gap=0.35, require_readable=False):
        """(Re)fit the board geometry from a fresh frame; returns that frame.

        A *fit* is not a *reading*: on the menu / result / lobby screens the
        lattice fits perfectly (the app still draws grid lines) while the
        position is not a chess position at all.  When the caller says it needs a
        readable board, only a fit whose own frame reads as one counts.

        Calibration is what every reading and every click depends on, and it is
        also the first thing that breaks on its own: a result screen, an
        animating or torn frame, a skin change, a resized window.  Recovery
        re-derives it instead of ending the run.  None means no frame in
        *tries* attempts showed a board that could be fitted.
        """
        a = None
        soft = None             # a real board whose piece counts read wrong
        for k in range(max(1, int(tries))):
            if self._stop():
                return None
            a = self.frame()
            if a is not None:
                try:
                    cal = V.calibrate(a, verbose=False)
                except Exception as exc:
                    cal = None
                    log("[attach] calibration attempt %d/%d crashed: %s: %s" % (
                        k + 1, tries, type(exc).__name__, exc))
                if cal and not require_readable:
                    self._adopt_fit(cal, a)
                    return a
                if cal and require_readable:
                    # A fit on a menu screen reads as nothing: keep looking
                    # instead of handing the loop a board it cannot play from.
                    # The frame is tested through read_candidate(), which brings
                    # its own pack for *this* fit - recognising through the
                    # player's state instead read the frame with self.cal = None
                    # and threw, so every attach reported "no position".
                    g = self.read_candidate(a, cal)
                    if g is not None and self.plausible(g):
                        self._adopt_fit(cal, a)
                        return a
                    if g is not None and self.board_like(g):
                        # Both generals and a board-sized army, but the piece
                        # counts do not add up: that is a real position the pack
                        # matches poorly, not a menu (a menu shows no generals).
                        # Holding it in reserve beats refusing to start at all.
                        soft = (a, cal)
                        log("[attach] the fit reads as a board but its piece counts are "
                            "off (attempt %d/%d) - kept in reserve" % (k + 1, tries))
                    else:
                        log("[attach] the board fit reads as no position (attempt %d/%d)"
                            % (k + 1, tries))
            log("[attach] calibration failed on attempt %d/%d - retrying" % (k + 1, tries))
            self._sleep(gap)
        if soft is not None:
            a, cal = soft
            log("[attach] no clean reading in %d tries - starting from the board whose "
                "piece counts are off; the read loop refits it" % tries)
            self._adopt_fit(cal, a)
            return a
        return None

    def attach(self, tries=6, gap=0.35, wait=False):
        w32.set_dpi_aware()
        hwnd, title = w32.find_window(self.title)
        if not hwnd:
            raise RuntimeError("window containing %r not found" % self.title)
        self.hwnd = hwnd
        x, y, w, h = w32.client_rect_screen(hwnd)
        self.origin = (x, y)
        self.grabber = w32.ScreenGrabber()
        if self.background:
            self.wgrab = w32.WindowGrabber()
            log("[background] reading through PrintWindow: a covered "
                "window still renders (a minimised one does not)")
            self.set_quiet(True)
        self.cal = None
        # A frame grabbed while the board is animating (or while an overlay covers
        # it) can fail the grid-line fit, so give calibration a few chances.
        # attach() is the start of a run: a fit that reads as no position
        # (menu / result screen) must not count as "the board is here".
        #
        # When *wait* is set, a screen that does not show a board is NOT an error:
        # the run has not started yet, so there is nothing to fail.  The caller
        # gets a player that is attached to the window and keeps looking, which is
        # what the run loop does anyway (its first act is to read the board).  The
        # alternative - raising here - is what made the program die on a customer's
        # machine: six unreadable frames, an exception out of the worker thread,
        # three attempts, then "giving up" and a dead console (field log
        # 2026-10-14: the last round of a quiet endgame read as three pieces,
        # every attach failed, and the process exited with a traceback).
        a = self._ensure_cal(tries=tries, gap=gap, require_readable=True)
        if a is None:
            save_dbg(self.frame(), "calibration_failed")
            if not wait:
                raise RuntimeError("board calibration failed after %d tries - the window "
                                   "does not show a recognisable board (results/menu screen, or "
                                   "animating). frame saved to %s" % (tries, DBG_DIR))
            # Nothing to read yet.  Leave the player in a state the console can
            # show and the run loop can work from: the window is attached, the
            # geometry is deliberately empty (so the next read refits it), and the
            # template pack is loaded unscaled - it is only used for the "N classes"
            # line in the console until a fit adopts its own.
            log("[attach] no board on screen yet - keeping the window and reading it "
                "as soon as one appears (frame saved to %s)" % DBG_DIR)
            self.tpl, self.tpl_half = V.load_templates()
            self.scr = None
            return self
        self._adopt_templates(a)
        scr, sc = V.recognize(a, self.cal, self.tpl, half=self.tpl_half)
        self.scr = scr
        self.flip = bool(B.detect_flip(scr))
        self.grid = B.screen_to_internal(scr, self.flip)
        # Joined mid-game already counts as a round in progress, so the first
        # starting position seen afterwards is a restart, not a re-read.
        self.session_ply = 0 if B.is_opening(self.grid) else 1
        if self.side_auto:
            # The mini-program always draws the player's own army on the lower
            # half of the board, so whoever sits at the bottom is us.
            self.our_side = "b" if self.flip else "w"
            log("[attach] our side: %s (auto - the army on the lower half)" %
                ("red" if self.our_side == "w" else "black"))
        CX, CY = self.cal.get("model") or ([], [])
        log("[attach] client %dx%d at (%d,%d) flip=%s discs=%d/%d resid=%s model=%s" % (
            w, h, x, y, self.flip, self.cal.get("ndiscs_used", self.cal["ndiscs"]),
            self.cal["ndiscs"], self.cal.get("resid"),
            "fitted" if CX else "grid-lines only"))
        if CX:
            log("[attach] CX " + " ".join("%.4f" % v for v in CX))
            log("[attach] CY " + " ".join("%.4f" % v for v in CY))
        else:
            log("[attach] WARNING: too few pieces to fit a sprite model; "
                "clicking on grid-line centres")
        log("[attach] FEN " + B.grid_to_fen(self.grid, self.our_side))
        return self

    def start_engine(self):
        last = None
        for attempt in (1, 2):
            try:
                self.engine = Engine(self.exe, threads=self.threads,
                                     hash_mb=self.hash_mb)
                log("[engine] " + self.engine.name)
                return self
            except Exception as exc:
                # A freshly extracted engine is scanned by the antivirus on its
                # very first run, which can make the UCI handshake time out.
                last = exc
                log("[engine] start attempt %d failed: %s: %s" % (
                    attempt, type(exc).__name__, exc))
                try:
                    self.engine.quit()
                except Exception:
                    pass
                time.sleep(1.0)
        raise RuntimeError("cannot start the engine %s: %s" % (self.exe, last))

    def restart_engine(self):
        """Throw the engine away and start a fresh process.

        The engine can die on its own (it is a separate process) and a dead one
        answers nothing but timeouts.  Returns True when a new engine is up.
        """
        old = self.engine
        self.engine = None
        if old is not None:
            try:
                old.quit()
            except Exception:
                pass
        try:
            self.start_engine()
            log("[engine] restarted")
            return True
        except Exception as exc:
            log("[engine] cannot restart it yet: %s: %s" % (type(exc).__name__, exc))
            return False

    # -- mid-run control ---------------------------------------------------
    ABORT_POLL = 0.05

    def _sleep(self, seconds):
        """Sleep in slices so stop/pause are honoured within ~50ms.

        The old loop slept in one go (click delays, repairs, round waits), so a
        stop waited for that sleep to finish.
        """
        end = time.time() + max(0.0, float(seconds))
        while time.time() < end:
            if self._stop():
                return False
            if self.pause_event is not None and self.pause_event.is_set():
                return self._pause_gate()
            time.sleep(min(0.05, max(0.0, end - time.time())))
        return True

    def _start_watch(self):
        """Watch the pause/stop buttons while the engine is thinking."""
        if self._watch is not None or not self.watch_buttons:
            return
        self._watching = True
        self._watch = threading.Thread(target=self._watch_buttons, name="pikafishjj-ctl")
        self._watch.daemon = True
        self._watch.start()

    def _watch_buttons(self):
        while self._watching and not self._closed:
            busy = self._stop() or (self.pause_event is not None
                                    and self.pause_event.is_set())
            if busy and self.engine is not None:
                if self.engine.stop():
                    time.sleep(0.2)          # one abort per search is enough
                    continue
            time.sleep(self.ABORT_POLL)

    def _stop_watch(self):
        self._watching = False

    # -- pacing ------------------------------------------------------------
    # How long the bot may spend while its own clock runs.  The game clock keeps
    # ticking while we wait, and a per-move limit can end the round outright, so
    # nothing on our own turn blocks for long: waiting for a ply to appear, for a
    # board to settle, and for the opponent are all capped, and a ply that never
    # lands is re-thought and re-clicked instead of being handed back to the
    # opponent - that handover used to idle for the whole opp_timeout (60s by
    # default), which is how a round was lost on time without a single mistake.
    SETTLE_TIMEOUT = 3.5         # s to wait for our own ply to show up
    STALL_WATCH = 4.0            # s to watch the board after a ply did not land
    UNCERTAIN_WAIT = 25.0        # s to wait for a move when the turn is not sure
    SLOW_MOVE_WARN = 8.0         # s after which a turn is called slow

    def _turn_time(self, t0):
        """Account the clock time one of our turns cost, and complain when slow."""
        dt = time.time() - t0
        self.stats["turn_s"] = self.stats.get("turn_s", 0.0) + dt
        self.stats["turn_max"] = max(self.stats.get("turn_max", 0.0), dt)
        if dt >= self.SLOW_MOVE_WARN:
            self.stats["slow"] = self.stats.get("slow", 0) + 1
            log("[time] that turn cost %.1fs of our clock (app busy, ply retried or "
                "screen hard to read) - lower 思考(ms) or 重试次数 if the clock is "
                "running out" % dt)
        return dt

    def _stop(self):
        return self.stop_event is not None and self.stop_event.is_set()

    def _pause_gate(self):
        """Block while paused; False means the run was stopped instead.

        The engine search is aborted on the first pass so a pause takes effect
        while it is thinking instead of after the whole think time.
        """
        while self.pause_event is not None and self.pause_event.is_set():
            if self._stop():
                return False
            if not self._pause_abort and self.engine is not None:
                self._pause_abort = True
                self.engine.stop()
            time.sleep(0.05)
        self._pause_abort = False
        return not self._stop()

    # -- perception --------------------------------------------------------
    def frame(self):
        """One frame of the client area; None when the window cannot be read.

        Every Win32 call here fails once the game window is gone, so nothing is
        allowed to raise: a missing frame is an ordinary event that the wait
        loops retry and the recovery path repairs.
        """
        a = None
        try:
            x, y, w, h = w32.client_rect_screen(self.hwnd)
            if (x, y) != self.origin:
                self.origin = (x, y)
            if (w, h) != self._client_size:
                if self._client_size != (0, 0) and self.cal is not None:
                    # The app redraws the board at another size in another game
                    # mode (and on a window resize): every square would be read and
                    # clicked at the wrong place, so drop the fit and refit.
                    log("[read] the game window is now %dx%d (was %dx%d) - the board "
                        "fit is being refitted" % (w, h, self._client_size[0],
                                                   self._client_size[1]))
                    self.cal = None
                    self.prev = None
                    self.hints = {}
                self._client_size = (w, h)
            t0 = time.perf_counter()
            if self.wgrab is not None:
                # PrintWindow renders the window even while another window covers
                # it; a minimised window comes back blank, so fall back then.
                a = self.wgrab.grab(self.hwnd)
                if a is None:
                    self.stats["bg_fallback"] = self.stats.get("bg_fallback", 0) + 1
            if a is None:
                a = self.grabber.grab(x, y, w, h)
            self.stats["grab_ms"] += (time.perf_counter() - t0) * 1000.0
            self.stats["frames"] += 1
        except Exception as exc:
            self.warn("[frame] cannot read the game window: %s: %s" % (
                type(exc).__name__, exc))
            # The incremental chain belongs to the frame we could not read; keeping
            # it makes the next read start from a frame that no longer exists.
            self.prev = None
            return None
        return a

    def band_changed(self, prev, a):
        """Did the board itself move between two frames?"""
        try:
            return V.frame_changed(prev, a, self.fp_band)
        except Exception as exc:
            # Different frame sizes mean the window was resized: treat it as
            # motion so the caller re-reads instead of comparing stale bands.
            self.warn("[read] cannot compare frames: %s: %s" % (type(exc).__name__, exc))
            return True

    # How far the fitted lattice may drift from the one we are playing on before
    # the frame counts as another screen, and how long a drift may last before the
    # board size is re-learned (a resized window really is a different board).
    PITCH_TOL = 0.12
    PITCH_RELEARN = 12.0

    def _pitch_off(self):
        """True when the fitted board is not drawn at the size we are playing at.

        Ranked play shrinks the board once a round is decided (measured: a 51.4px
        pitch against 65.4px during the game).  The fit finds a lattice there and
        can call the model good, and the pieces land on believable squares, so
        neither the residual gate nor plausible() catches it - the only reliable
        tell is that the whole board is drawn smaller.  Reporting "no board"
        instead of a plausible-looking nonsense position is also what makes the
        caller press 再来一局.
        """
        want = self.pitch
        if not want or not self.cal:
            return False
        cp = float(self.cal.get("cpitch") or 0.0)
        rp = float(self.cal.get("rpitch") or 0.0)
        if cp <= 0.0 or rp <= 0.0 or want[0] <= 0.0 or want[1] <= 0.0:
            return False
        if (abs(cp - want[0]) / want[0] <= self.PITCH_TOL
                and abs(rp - want[1]) / want[1] <= self.PITCH_TOL):
            self._pitch_bad_since = 0.0
            return False
        now = time.time()
        if not self._pitch_bad_since:
            self._pitch_bad_since = now
        elif now - self._pitch_bad_since >= self.PITCH_RELEARN:
            log("[read] the board has been drawn at %.0fpx/%.0fpx for %.0fs - adopting "
                "that size instead of %.0fpx/%.0fpx" % (
                    cp, rp, now - self._pitch_bad_since, want[0], want[1]))
            self.pitch = (cp, rp)
            self._pitch_bad_since = 0.0
            return False
        return True

    def _recognize(self, a):
        """Recognise one frame, reusing the per-square offsets found last time."""
        if a is None:
            return None
        if self.cal is None or self.tpl is None:
            # Recognition is defined against a fit and a template pack; without
            # them there is no board to report.  Saying so here keeps a missing
            # fit from surfacing as a template-matching exception instead.
            return None
        cp = float(self.cal.get("cpitch") or 0.0) if self.cal else 0.0
        rp = float(self.cal.get("rpitch") or 0.0) if self.cal else 0.0
        if self._pitch_off():
            self.warn("[read] the board on screen is drawn at %.0fpx across a file, ours "
                      "is %.0fpx - that is the result/menu screen, not the game board" % (
                          cp, self.pitch[0]), gap=4.0)
            self.prev = None
            return None
        info = {}
        t0 = time.perf_counter()
        try:
            scr, sc = V.recognize(a, self.cal, self.tpl, half=self.tpl_half,
                                  info=info, hints=self.hints, prev=self.prev)
        except Exception as exc:
            # A torn or resized frame must not end the run: drop the incremental
            # chain and report "no board" so the caller re-reads or recalibrates.
            self.warn("[read] recognition failed: %s: %s" % (type(exc).__name__, exc))
            self.prev = None
            return None
        self.stats["recog_ms"] += (time.perf_counter() - t0) * 1000.0
        self.stats["recognitions"] += 1
        if info.get("changed", -1) >= 0:
            self.stats["incr"] = self.stats.get("incr", 0) + 1
        self.scr = scr
        grid = B.screen_to_internal(scr, self.flip)
        ok = self.plausible(grid)
        if ok and self.pitch is None and cp > 0.0 and rp > 0.0:
            # A board we believe in tells us how big the board we play on is.
            self.pitch = (cp, rp)
        # Only chain from a frame we believed in: after a rejected read the next
        # recognition must start from scratch instead of inheriting a bad board.
        self.prev = (a, info) if ok else None
        self.hints.update(info["hints"])
        self.nread += 1
        self.stats["reads"] += 1
        return grid

    def read(self):
        """One reading, through whichever board source is selected."""
        self._start_watch()
        self._ensure_bridge()
        if self.source.is_backend:
            g, a = self.source.read(self, timeout=3.0, need=1)
            return g, a
        a = self.frame()
        if a is None:
            return None, None
        if self.handle_dialog(a):
            self._sleep(0.4)                 # let the panel close
            a = self.frame()
        return self._recognize(a), a

    @staticmethod
    def plausible(g):
        """A frame is usable only if it is a position the rules can reach.

        Two generals, sane piece counts *and* placings the pieces can actually
        stand on: a square read one off (a rook on the general's file, an advisor
        out of its palace, a pawn behind its start) is a misread, and adopting it
        costs more than re-reading - the engine answers an impossible board by
        exiting, and the move loop used to send one straight through.  The gate
        allows the board turned around as well: the frame that follows our own
        再来一局 arrives rotated (ranked play swaps the colours), so a read that
        only makes sense turned is still a real position - start_new_game
        re-derives the orientation from that same frame.
        """
        if g is None:
            return False
        if B.find_king(g, True) is None or B.find_king(g, False) is None:
            return False
        n = sum(1 for j in range(10) for i in range(9) if g[j][i] != ".")
        if not (8 <= n <= 32):
            return False
        return B.position_ok_read(g)[0]

    @staticmethod
    def board_like(g):
        """True when *g* holds both generals and a board-sized army.

        Deliberately weaker than plausible(): it drops the piece-count check,
        which a skin the stored template pack matches poorly gets wrong while the
        position itself is real.  A menu / lobby / result screen fails it anyway -
        measured, lobby_now reads 2 lone black bishops and live10 reads empty.
        """
        if g is None:
            return False
        if B.find_king(g, True) is None or B.find_king(g, False) is None:
            return False
        n = sum(1 for j in range(10) for i in range(9) if g[j][i] != ".")
        return 8 <= n <= 32

    # -- continuity across rounds ------------------------------------------
    def is_new_game(self, g):
        """True when *g* is the starting position of a fresh round.

        In xiangqi nothing is reversible (soldiers never move backwards), so the
        exact starting position can never come back in the middle of a game:
        seeing it again means the app reset the board and began a new round.

        *g* was mapped with the flip of the round that just ended, and ranked
        play swaps the colours between rounds - that frame arrives upside down,
        so the starting position is also accepted mirrored.  The orientation is
        re-derived from the same frame in start_new_game, so nothing is adopted
        on a wrong reading: the check only decides *that* a round began.
        """
        if g is None or self.session_ply <= 0:
            return False
        if B.is_opening(g):
            return True
        if self.scr is not None and B.is_opening(
                B.screen_to_internal(self.scr, not self.flip)):
            return True
        return False

    # How long a pressed 再来一局 keeps the next readable board ours to adopt.
    NEW_ROUND_WINDOW = 60.0

    def waiting_new_round(self):
        """True while the board that follows our own 再来一局 was not adopted yet.

        Recognising the starting position is not enough there: ranked play swaps
        the colours (so the frame arrives mirrored) and the opponent may already
        have moved before we read it (so it is the opening plus a ply or two).
        Once *we* have pressed the button, the first plausible board that differs
        from the finished one *is* the new round.
        """
        return bool(self.auto_next and self._rematch_t > 0.0
                    and time.time() - self._rematch_t <= self.NEW_ROUND_WINDOW)

    def start_new_game(self, g=None, why="the board is back at the starting position"):
        """Drop every per-game counter and re-derive our side for a new round.

        *why* only names the trigger in the log ("the board is back at the
        starting position" / "the 再来一局 button was pressed").

        The app always draws the player's own army on the lower half, so a round
        that swaps the colours (ranked play does) also turns the screenshot
        around.  The orientation is taken from the frame that was just read
        rather than trusted from the game that ended, and the incremental
        recognition chain and the click hints are dropped because they describe
        the old board.
        """
        self.stats["games"] = self.stats.get("games", 0) + 1
        self.stats["moves"] = 0
        self.session_ply = 0
        self.prev = None
        self.hints = {}
        self._dlg_t = 0.0
        self._rematch_t = 0.0
        self._dlg_seen = None
        # The first seconds of a round are an animation, not a request panel.
        self._dlg_skip_t = max(self._dlg_skip_t, time.time() + 3.0)
        if self.scr is not None:
            flip = B.detect_flip(self.scr)
            if flip is not None and bool(flip) != bool(self.flip):
                self.flip = bool(flip)
                log("[new] the colours were swapped - the board is drawn the "
                    "other way round now")
            g = B.screen_to_internal(self.scr, self.flip)
        if g is None:
            return False
        if self.side_auto:
            self.our_side = "b" if self.flip else "w"
        self.grid = g
        log("[new] game %d starts (%s): we play %s%s" % (
            self.stats["games"], why, "red" if self.our_side == "w" else "black",
            " (auto - the army on the lower half)" if self.side_auto else ""))
        return True

    def set_grid(self, g):
        """Adopt *g* as the current position.

        Returns "new" when a fresh round just began (the caller resets its own
        move counters), "stop" when that happened with the feature switched off,
        and None for an ordinary update.
        """
        if g is None:
            return None
        # A rematch is only adopted once a board that differs from the finished
        # one is readable: the result screen itself is still the old position.
        rematch = self.waiting_new_round() and g != self.grid
        if rematch or self.is_new_game(g):
            if not self.new_game:
                log("[new] %s - stopping here (tick the new-game option to keep "
                    "playing)" % ("再来一局 was pressed" if rematch
                                  else "the board is back at the starting position"))
                self.session_ply = 0
                self.grid = g
                return "stop"
            self.start_new_game(g, why=(
                "the 再来一局 button was pressed" if rematch
                else "the board is back at the starting position"))
            return "new"
        if self.grid is None or g != self.grid:
            self.session_ply += 1
        self.grid = g
        return None

    def stable_grid(self, timeout=8.0, need=3, interval=0.03):
        """Read a settled board through whichever source is selected.

        The vision source is the shipped screenshot path; the backend source
        answers from the mini-program's own state.  Every wait loop in this file
        goes through here, so the two axes switch the whole loop at once.
        """
        self._ensure_bridge()
        if self.source.is_backend:
            return self.source.read(self, timeout=timeout, need=need, interval=interval)
        return self._vision_stable_grid(timeout=timeout, need=need, interval=interval)

    # The board repaints for a while after every move (a slide plus a highlight
    # that keeps fading), and during that time three still frames in a row never
    # happen: the cheap fingerprint gate keeps reporting motion, so the bot used
    # to be blind for seconds after every move - long enough for a reply, or for
    # a move made by hand, to land on top of the one we were waiting for.  Once
    # the stillness gate has had no luck for REPAINT_PATIENCE seconds, two
    # readings that agree exactly are taken instead: a torn frame does not repeat
    # itself, a real board does.
    REPAINT_PATIENCE = 1.2
    AGREE_INTERVAL = 0.35
    READ_HEARTBEAT = 4.0

    def _vision_stable_grid(self, timeout=8.0, need=3, interval=0.03):
        """Wait for a readable board on screen, then read it once.

        Polling costs a grab plus a 3ms block compare; the 28ms recognise runs
        only after the motion stops. A settle therefore costs ~1 recognise
        instead of one per animation frame (85 for eight plies before).
        Returns (None, None) on timeout, on stop, or after repeated bad reads -
        never a mid-animation frame.
        """
        t0 = time.time()
        prev = None
        run = 0
        bad = 0
        t_log = t0
        repaint = False
        t_read = 0.0
        last = None
        while time.time() - t0 < timeout:
            if not self._pause_gate():
                return None, None
            a = self.frame()
            if a is None:
                # The window cannot be read at all right now: keep trying, but
                # say so, otherwise a covered/missing window looks like a freeze.
                prev = None
                run = 0
                if time.time() - t_log >= self.READ_HEARTBEAT:
                    t_log = time.time()
                    log("[read] still nothing from the game window (%.0fs of %.0fs)" % (
                        time.time() - t0, timeout))
                time.sleep(interval)
                continue
            if self.handle_dialog(a):
                prev = None                  # the panel is not board motion
                run = 0
                time.sleep(interval)
                continue
            if prev is not None and not self.band_changed(prev, a):
                run += 1
            else:
                run = 0
            prev = a
            if run >= need:
                run = 0
                g = self._recognize(a)
                if self.plausible(g):
                    return g, a
                bad += 1
                if time.time() - t_log >= self.READ_HEARTBEAT:
                    t_log = time.time()
                    _ok, why = (B.position_ok_read(g) if g is not None
                                else (False, "no board"))
                    log("[read] this frame is not a chess position (bad read %d: %s) - "
                        "the game may be on a menu or result screen" % (bad, why))
                if bad >= 2:
                    # Two unreadable frames in a row usually means the result
                    # screen is up: press 再来一局 instead of just sitting there.
                    self.handle_continue(a)
                if bad >= 2 and time.time() - self._refit_t >= 3.0:
                    # Two settled frames in a row that are not a chess position.
                    # Either the app is on another screen, or our fit belongs to
                    # one (the result screen draws the same board 20% smaller and
                    # fits perfectly).  Refit, but only believe the new fit if the
                    # very frame it was made from now reads as a board - otherwise
                    # the old one was right and the window is simply covered.
                    # 3.0s between refits (was 10s): the log shows a full 12s read
                    # burning three of them while the app is on a menu screen.
                    self._refit_t = time.time()
                    log("[read] %d unreadable frames in a row - refitting the board"
                        % bad)
                    old_cal, old_band = self.cal, self.fp_band
                    self.cal = None
                    self.prev = None
                    self.hints = {}
                    fresh = self._ensure_cal(tries=2, gap=0.25)
                    if fresh is not None:
                        # A refit usually comes with another pitch (a resized
                        # window, the smaller board of a decided round), and the
                        # pack is scaled to the pitch.
                        self._adopt_templates(fresh, force=True)
                    g_new = self._recognize(fresh) if fresh is not None else None
                    if self.plausible(g_new):
                        log("[read] the board was refitted (%.0fpx/%.0fpx across the "
                            "files, median tile %s)" % (
                                float(self.cal.get("cpitch") or 0.0),
                                float(self.cal.get("rpitch") or 0.0),
                                V.tile_colour(fresh, self.cal.get("band"))))
                        bad = 0
                        run = 0
                        repaint = False
                        last = None
                        prev = None
                    else:
                        self.cal, self.fp_band = old_cal, old_band
                        self.prev = None
                        log("[read] the refit does not read either - keeping the fit "
                            "we had")
                if bad >= 5:
                    return None, None
            elif not repaint and time.time() - t0 >= self.REPAINT_PATIENCE:
                repaint = True
                log("[read] the board keeps repainting - falling back to two agreeing "
                    "readings (%.0fs of %.0fs)" % (time.time() - t0, timeout))
            if repaint and time.time() - t_read >= self.AGREE_INTERVAL:
                t_read = time.time()
                g2 = self._recognize(a)
                if self.plausible(g2):
                    if g2 == last:
                        log("[read] two readings agree on the same board - taking it")
                        return g2, a
                    last = g2
                else:
                    last = None
            time.sleep(interval)
        return None, None

    # How often the wait says what it is waiting for, and how long a many-ply
    # change has to stay put before it is believed.
    WAIT_HEARTBEAT = 10.0
    MULTI_PLY_CONFIRM = 1.5

    def wait_change(self, prev, timeout=8.0, strict=True):
        """Block until a settled board that differs from *prev* like a real ply.

        Three identical reads are not enough on their own: while the game is
        repainting after a move it hands out torn frames, and the same tear can
        repeat often enough to look settled (measured: two of our pieces missing
        and the enemy cannon drawn on the wrong square, four times in a row).  A
        genuine single ply always shows up as exactly one emptying cell plus one
        gaining cell, so anything else has to prove itself: it is taken once the
        very same board has been read again MULTI_PLY_CONFIRM seconds later and
        the difference reads as a series of whole plies (board.explain_change) -
        that is two moves landing while we were not looking, which is what a
        repaint after the opponent's move plus a move made by hand looks like.
        Anything that fits neither shape is held as a fallback while the wait
        carries on looking for a frame that does look like one move.

        Waiting is how the bot spends most of a game, so the heartbeat says which
        of the two states it is in: a board that reads the same (the opponent has
        not moved yet) or a board that cannot be read (the app is repainting or
        showing another screen).  Saying nothing at all used to look like a freeze.
        """
        t0 = time.time()
        fallback = None
        t_log = t0
        t_same = t0
        while time.time() - t0 < timeout and not self._stop():
            g, a = self.stable_grid(timeout=min(2.5, timeout), need=3)
            if g is None:
                if time.time() - t_log >= self.WAIT_HEARTBEAT:
                    t_log = time.time()
                    log("[wait] the board cannot be read yet (%.0fs of %.0fs) - the app "
                        "is repainting or showing another screen" % (
                            time.time() - t0, timeout))
                continue
            if self.is_new_game(g):
                log("[new] the board is back at the starting position")
                return g, a
            if g == prev:
                if time.time() - t_same >= self.WAIT_HEARTBEAT:
                    t_same = time.time()
                    log("[wait] the position is the same as our last reading (%.0fs of "
                        "%.0fs) - the opponent has not moved yet" % (
                            time.time() - t0, timeout))
                continue
            t_same = time.time()
            if self.waiting_new_round():
                # We pressed 再来一局 ourselves, so whatever plausible board is
                # there now belongs to the new round - even when it is drawn for
                # the other side and already carries the opponent's first ply.
                log("[new] the board changed after 再来一局 was pressed")
                return g, a
            mv = B.diff_moves(prev, g)
            if not strict or (len(mv) == 1 and mv[0][0] != "?"):
                return g, a
            plies = B.explain_change(prev, g)
            if plies is None:
                # No series of plies accounts for these cells: a tear, or a board
                # the app has not finished drawing.  Keep it, keep looking.
                if fallback is None or fallback[0] != g:
                    fallback = (g, a, time.time())
                    log("[wait] ignoring a %d-cell change that is not a series of "
                        "moves: %s" % (len(mv), describe(prev, g)))
                if time.time() - t_log >= self.WAIT_HEARTBEAT:
                    t_log = time.time()
                    log("[wait] the board keeps changing without a clean ply (%.0fs "
                        "of %.0fs) - watching it, nothing is fed to the engine yet" % (
                            time.time() - t0, timeout))
                time.sleep(0.12)
                continue
            if (fallback is not None and fallback[0] == g
                    and time.time() - fallback[2] >= self.MULTI_PLY_CONFIRM):
                log("[wait] %d moves landed while we were not looking (%s) - taking the "
                    "board as it is" % (len(plies), moves_text(plies)))
                return g, a
            if fallback is None or fallback[0] != g:
                fallback = (g, a, time.time())
                log("[wait] the board is %d moves ahead of our last reading (%s) - "
                    "waiting for it to stay put" % (len(plies), moves_text(plies)))
            time.sleep(0.12)
        if fallback is not None:
            log("[wait] sticking with the board we kept reading after %.0fs" % timeout)
            return fallback[0], fallback[1]
        return None, None

    def settle_after(self, prev, want, timeout=6.0):
        """Wait for a settled board that accounts for our intended move.

        The bot opponent often answers before we have finished reading the
        screen, so the settled board may already hold two plies.  Accept either
        exactly the expected position, or a board that becomes it once the
        opponent single reply is taken off.  Nothing is ever assumed: the
        caller re-derives both plies from the returned board.
        Returns (grid, frame, opponent_already_replied); replied is None when
        the timeout expired on a board that fits neither shape.
        """
        t0 = time.time()
        last = None
        while time.time() - t0 < timeout:
            if not self._pause_gate():
                break
            g, a = self.stable_grid(timeout=min(3.0, timeout), need=3)
            if g is None:
                continue
            if self.is_new_game(g):
                return g, a, False
            if g == prev:
                continue
            if g == want:
                return g, a, False
            mv = B.diff_moves(want, g)
            if len(mv) == 1 and mv[0][0] != "?":
                log("[play] the opponent replied before we could read: " +
                    describe(want, g))
                return g, a, True
            last = (g, a)
        if last:
            return last[0], last[1], None
        return None, None, False

    def wait_still(self, prev, quiet=1.0, timeout=25.0):
        """Block while the board keeps changing; return the settled board."""
        t0 = time.time()
        cur = prev
        while time.time() - t0 < timeout:
            if not self._pause_gate():
                break
            g, a = self.stable_grid(timeout=3.0, need=3)
            if g is None:
                continue
            if g != cur:
                cur = g
                t0 = time.time() - max(0.0, timeout - quiet - 3.0)
                continue
            if time.time() - t0 >= quiet:
                return cur, a
        return cur, None

    def cell_xy(self, i, j):
        si, sj = B.internal_to_screen(self.flip, i, j)
        x, y = V.grid_xy(self.cal, si, sj)
        return self.origin[0] + int(round(x)), self.origin[1] + int(round(y))

    # -- action ------------------------------------------------------------
    def play_move(self, fi, fj, ti, tj):
        """Play one ply through whichever sink is selected."""
        self._ensure_bridge()
        if self.sink.is_backend:
            return self.sink.play(self, fi, fj, ti, tj)
        if self.background:
            # Clicks must stay quiet even if the window lost the style (a new
            # window after a game-mode switch, or a previous foreground episode).
            self._ensure_quiet()
        return self._physical_play(fi, fj, ti, tj)

    def _physical_play(self, fi, fj, ti, tj):
        x1, y1 = self.cell_xy(fi, fj)
        x2, y2 = self.cell_xy(ti, tj)
        if self.verbose:
            log("    click (%d,%d)->(%d,%d) screen (%d,%d)->(%d,%d)" %
                (fi, fj, ti, tj, x1, y1, x2, y2))
        if self.dry:
            return
        if self._quiet_now():
            # No bring_to_front: the window carries WS_EX_NOACTIVATE and the
            # pointer is put back where the user left it after every click.
            ok = self._click_at(x1, y1)
            self._sleep(self.click_delay)
            ok = self._click_at(x2, y2) and ok
            self._sleep(self.click_delay)
            if ok:
                self._quiet_ok()
            else:
                self._quiet_failed("a quiet click could not be delivered")
            return
        self.click_point(x1, y1)
        self._sleep(self.click_delay)
        self.click_point(x2, y2)
        self._sleep(self.click_delay)

    # -- opponent requests --------------------------------------------------
    # A panel has to be seen several times, in the same place, over a whole
    # second before it is answered: one transition or animation frame can pass
    # through the detector, and the screen that follows 再来一局 was measured
    # doing exactly that (a stray 拒绝 click landed one second after the press
    # even with a two-frame gate).  A single visible button is the weaker shape
    # of the panel, so it is given an even longer look.
    DIALOG_CONFIRM_GAP = 1.5    # seconds without a sighting before the run breaks
    DIALOG_CONFIRM_DIST = 30    # px the sightings may differ by
    DIALOG_CONFIRM_HITS = 3     # sightings needed when both buttons are there
    DIALOG_CONFIRM_SPAN = 1.0   # ... and how long they have to span
    DIALOG_CONFIRM_HITS_1 = 4   # sightings needed for a single-button panel
    DIALOG_CONFIRM_SPAN_1 = 2.5 # ... and how long they have to span

    def _request_target(self, d):
        """Which button of a request panel would be pressed (decline by default)."""
        if self.request == "accept" and "accept" in d:
            return "accept", d["accept"]
        if "decline" in d:
            return "decline", d["decline"]
        return "accept", d["accept"]

    def handle_dialog(self, a):
        """Answer the opponent's request panel (draw offer / undo request).

        Every request reuses one panel and only the text changes, so it is
        found by its two buttons (dialog.find_request).  self.request decides
        what happens: decline (default), accept, or off to leave it alone.
        Returns True whenever a panel looks like it is on screen - including the
        first, still unconfirmed sighting, so the caller skips that frame.
        """
        if a is None or self.request == "off":
            return False
        now = time.time()
        if now < self._dlg_skip_t:
            return False                     # just pressed 再来一局 / a round began
        d = D.find_request(a)
        if d is None:
            self._dlg_seen = None
            return False
        what, pt = self._request_target(d)
        seen = self._dlg_seen
        if (seen is None or now - seen[4] > self.DIALOG_CONFIRM_GAP
                or abs(seen[1][0] - pt[0]) > self.DIALOG_CONFIRM_DIST
                or abs(seen[1][1] - pt[1]) > self.DIALOG_CONFIRM_DIST):
            self._dlg_seen = (now, pt, what, 1, now)
            return True                      # a first sighting is never answered
        hits = seen[3] + 1
        span = now - seen[0]
        if d["buttons"] >= 2:
            need_hits, need_span = self.DIALOG_CONFIRM_HITS, self.DIALOG_CONFIRM_SPAN
        else:
            need_hits, need_span = (self.DIALOG_CONFIRM_HITS_1,
                                    self.DIALOG_CONFIRM_SPAN_1)
        if hits < need_hits or span < need_span:
            self._dlg_seen = (seen[0], pt, what, hits, now)
            return True                      # still not sure it is really there
        self._dlg_seen = None
        if now - self._dlg_t < 2.0:
            return True                      # already answered this panel
        self._dlg_t = now
        self.stats["dialogs"] = self.stats.get("dialogs", 0) + 1
        log("[dialog] the opponent sent a request (%d button(s) on screen)" %
            d["buttons"])
        if self.dry:
            log("[dry] not clicking the request panel")
            return True
        x, y = self.origin[0] + pt[0], self.origin[1] + pt[1]
        log("[dialog] %s -> click screen (%d,%d)" % (what, x, y))
        self.click_point(x, y)
        return True

    # -- the next round ----------------------------------------------------
    def handle_continue(self, a):
        """Press the result screen's 再来一局 button when it is on screen.

        Once a round is decided the app shrinks and dims the board and waits for
        that button, so the screen is unreadable until it is pressed - which is
        exactly the state that used to leave the run watching nothing.  The
        press is rate limited (the button needs a moment to react) and only ever
        made from paths that have already failed to read a board.
        """
        if not self.auto_next or a is None:
            return False
        try:
            hit = D.find_continue(a)
        except Exception as exc:
            self.warn("[next] cannot look for the rematch button: %s: %s" % (
                type(exc).__name__, exc))
            return False
        if not hit:
            return False
        now = time.time()
        if now - self._next_t < 3.0:
            return True                      # that screen was already pressed
        self._next_t = now
        self.stats["rematch"] = self.stats.get("rematch", 0) + 1
        x = self.origin[0] + hit["point"][0]
        y = self.origin[1] + hit["point"][1]
        log("[next] the round looks finished - clicking 再来一局 at screen (%d,%d)" % (
            x, y))
        if self.dry:
            log("[dry] not clicking the rematch button")
            return True
        self.click_point(x, y)
        # From here on the next round is ours to adopt: the board that appears
        # is drawn for whichever side the app gave us, so it is picked up from
        # the frame itself instead of being compared with the finished one.
        self._rematch_t = time.time()
        # Nothing on the transition screen is a request panel, and the repaint
        # can look like one (measured: a stray 拒绝 click one second later, and
        # again two frames in a row on the way to the next round).
        self._dlg_skip_t = self._rematch_t + 8.0
        self._dlg_seen = None
        return True

    def wait_for_board(self, timeout=0.0):
        """Watch the window until it shows a board we can read.

        Returns (grid, frame) or (None, None) on stop.  Unlike wait_next_round
        this does not press anything and does not compare against the previous
        position - it is for "the app is showing something we cannot parse", where
        the only right answer is to keep looking.  The window may also be gone;
        that is reported, and the loop retries the whole search rather than
        giving up, so a minimised or closed game costs a wait and not a crash.

        *timeout* 0 means no deadline: the user asked to play, so the run stays
        alive until a board appears or 停止 is pressed.
        """
        t0 = time.time()
        t_log = t0
        t_refit = 0.0
        while not self._stop():
            if not self._pause_gate():
                return None, None
            if time.time() - t0 >= timeout and timeout > 0:
                return None, None
            if self.hwnd is None:
                try:
                    hwnd, _t = w32.find_window(self.title)
                except Exception:
                    hwnd = None
                if hwnd:
                    self.warn("[watch] the game window is back - reattaching", gap=3.0)
                    try:
                        self.attach(tries=2, gap=0.3)
                    except Exception as exc:
                        self.warn("[watch] reattach failed: %s: %s" % (
                            type(exc).__name__, exc), gap=5.0)
                else:
                    if time.time() - t_log >= 10.0:
                        t_log = time.time()
                        self.warn("[watch] the game window is not on screen - "
                                  "waiting for it", gap=10.0)
                    self._sleep(0.7)
                    continue
            g, a = self.stable_grid(timeout=2.5, need=2)
            if g is not None:
                log("[watch] the board is readable again")
                return g, a
            # The fit itself can be what is wrong (a result screen draws the same
            # board smaller, a game mode redraws it at another size).  Refit now
            # and then, but never in a tight loop: each refit is a full scan.
            if time.time() - t_refit >= 8.0:
                t_refit = time.time()
                self.cal = None
                self.prev = None
                self.hints = {}
                fresh = self._ensure_cal(tries=2, gap=0.25)
                if fresh is not None:
                    self._adopt_templates(fresh, force=True)
            if time.time() - t_log >= 20.0:
                t_log = time.time()
                self.warn("[watch] still no readable board (%.0fs) - the app is on "
                          "another screen, animating, or the board reads wrong; "
                          "press 停止 to quit" % (time.time() - t0), gap=20.0)
            self._sleep(0.5)
        return None, None

    def wait_next_round(self, timeout=60.0):
        """Wait for the next round to start, pressing 再来一局 when it is shown.

        Returns (grid, frame) of the new board or (None, None) on timeout.  Both
        shapes are handled: the result screen (button to press) and a board that
        simply resets to the starting position.
        """
        t0 = time.time()
        while time.time() - t0 < timeout and not self._stop():
            if not self._pause_gate():
                break
            a = self.frame()
            if a is None:
                self._sleep(0.5)
                continue
            if self.handle_dialog(a):
                time.sleep(0.4)
                continue
            g = self._recognize(a)
            if g is not None and self.plausible(g) and (g != self.grid or B.is_opening(g)):
                return g, a
            self.handle_continue(a)
            self._sleep(0.7)
        return None, None

    def click_point(self, x, y):
        """Click a screen point: quietly in background mode, in front otherwise."""
        if self._quiet_now():
            ok = self._click_at(x, y)
            if ok:
                self._quiet_ok()
            else:
                self._quiet_failed("a quiet click could not be delivered")
            return ok
        if self.quiet:
            self.set_quiet(False)
        w32.bring_to_front(self.hwnd)
        self._sleep(0.05)
        w32.click(x, y)
        return True

    # -- background operation ----------------------------------------------
    # How long a failed quiet click keeps using ordinary (foreground) clicks
    # before trying the background again.
    BG_RETRY_GAP = 6.0

    def _ensure_quiet(self):
        """Keep WS_EX_NOACTIVATE on while the run is supposed to be quiet.

        The style is per window: a new window (the app rebuilding its window
        after a game-mode switch) or one failed quiet click used to leave the
        game activatable, and from then on every ordinary click brought it to the
        front - which looked like "the background mode fell back to foreground".
        """
        if not self.background or not self.hwnd:
            return False
        try:
            if self.quiet and w32.has_no_activate(self.hwnd):
                return True
            self.set_quiet(True)
            return True
        except Exception as exc:
            self.warn("[background] cannot restore the quiet window style: %s: %s"
                      % (type(exc).__name__, exc))
            return False

    def _quiet_now(self):
        """Should this click be delivered quietly, in the background?"""
        if not self.background:
            return False
        if self.bg_ok:
            self._ensure_quiet()
            return True
        if time.time() < self.bg_probe_t:
            return False
        log("[background] trying quiet clicking again")
        self._ensure_quiet()
        return True

    def _quiet_ok(self):
        """A quiet click was delivered: stay in (or go back to) the background."""
        self.bg_fail = 0
        self.bg_probe_t = 0.0
        if not self.bg_ok:
            self.bg_ok = True
            log("[background] quiet clicking works again - staying in the background")
        if self.background:
            self.set_quiet(True)

    def _quiet_failed(self, why):
        """Suspend quiet clicking for a moment instead of giving it up for good.

        One covered click used to disable background mode for the rest of the
        session, so the game window was brought to the front from then on -
        measured in the field as "it switches to the foreground by itself in the
        middle of a game".  The mode now comes back by itself: every click after
        BG_RETRY_GAP seconds tries the quiet way first again.
        """
        self.bg_fail += 1
        self.bg_probe_t = time.time() + self.BG_RETRY_GAP
        if self.bg_ok:
            self.bg_ok = False
            log("[background] %s - using ordinary clicks for %.0fs, then trying "
                "the background again" % (why, self.BG_RETRY_GAP))

    def _covering(self, x, y):
        """What is standing in the way of a click at (x, y), for the log."""
        try:
            if w32.is_minimized(self.hwnd):
                return "the game window is minimised - restore it to click"
            owner = w32.point_owner(x, y)
            if not owner:
                return "nothing is at that point"
            if owner == self.hwnd:
                return "the game window"
            return "\u201c%s\u201d" % (w32.title_of(owner) or "another window")
        except Exception:
            return "another window"

    def _click_at(self, x, y):
        """Click without taking the foreground.

        Real input only reaches a window that is on top at that point, so if
        something covers the board the game is raised to the top of the
        z-order for the moment of the click; WS_EX_NOACTIVATE keeps the
        keyboard focus where the user left it.
        """
        if w32.is_minimized(self.hwnd):
            # Nothing to raise: the window is not on the desktop at all, and the
            # caller's ordinary click path restores it.
            log("[background] the game window is minimised - cannot click it")
            return False
        if w32.point_owner(x, y) == self.hwnd:
            w32.click_silent(x, y)
            return True
        if not self.raise_click:
            log("[background] the board is covered by %s" % self._covering(x, y))
            return False
        cover = w32.point_owner(x, y)        # what is in the way right now
        w32.set_topmost(self.hwnd, True)
        time.sleep(0.06)
        ok = w32.point_owner(x, y) == self.hwnd
        if ok:
            w32.click_silent(x, y)
        w32.set_topmost(self.hwnd, False)
        if cover and cover != self.hwnd:
            # Lowering the game leaves it at the top of the ordinary z-order, in
            # front of the window that was covering it - put that one back so a
            # click never ends with the game sitting in front of the user.
            w32.raise_window(cover)
            self.warn("[background] the game had to be raised for a click - "
                      "it is behind %s again" % self._covering(x, y))
        if not ok:
            log("[background] the board stays covered - cannot click (%s)" % (
                self._covering(x, y)))
        return ok

    def set_quiet(self, on=True):
        """WS_EX_NOACTIVATE: clicking the game must not take the foreground."""
        if not self.hwnd or self.quiet == bool(on):
            return self.quiet
        try:
            w32.set_no_activate(self.hwnd, on)
            self.quiet = bool(on)
            log("[background] window activation %s" %
                ("suppressed (WS_EX_NOACTIVATE)" if on else "restored"))
        except Exception as exc:
            log("[background] cannot change the window style: %s" % exc)
        return self.quiet

    # -- recovery ----------------------------------------------------------
    def reset_link(self, keep_engine=True):
        """Drop the window handle, the grabbers and the calibration.

        Used between session attempts: the GDI caches must be released before a
        new attach, and a stale calibration must never survive into it.
        """
        for g in (self.wgrab, self.grabber):
            if g is not None:
                try:
                    g.close()
                except Exception:
                    pass
        self.wgrab = self.grabber = None
        self.hwnd = None
        self.origin = (0, 0)
        self.cal = None
        self.tpl = None
        self.prev = None
        self.scr = None
        self.hints = {}
        self.quiet = False
        if not keep_engine:
            self.engine = None
        return self

    def reattach(self, tries=4, gap=0.4):
        """Make sure the game window and the board geometry are still usable."""
        try:
            hwnd, _title = w32.find_window(self.title)
        except Exception as exc:
            self.warn("[retry] cannot look for the game window: %s: %s" % (
                type(exc).__name__, exc))
            hwnd = None
        if not hwnd:
            self.warn("[retry] the game window is not on screen - waiting for it")
            return False
        if hwnd != self.hwnd:
            log("[retry] the game window changed (%s -> %s)" % (self.hwnd, hwnd))
            self.hwnd = hwnd
            self.cal = None
            self.prev = None
        try:
            x, y, _w, _h = w32.client_rect_screen(self.hwnd)
            self.origin = (x, y)
        except Exception as exc:
            self.warn("[retry] cannot locate the client area: %s: %s" % (
                type(exc).__name__, exc))
            return False
        if self.grabber is None:
            self.grabber = w32.ScreenGrabber()
        if self.background and self.wgrab is None:
            self.wgrab = w32.WindowGrabber()
            self.set_quiet(True)
        if self.cal is None or self.tpl is None:
            a = self._ensure_cal(tries=tries, gap=gap, require_readable=True)
            if a is None:
                self.warn("[retry] the window still does not show a readable board")
                return False
            self._adopt_templates(a)
        self._ensure_quiet()
        return True

    def recover(self, reason):
        """Repair whatever a failed step depends on, then let the loop retry.

        Every part of this loop can break on its own: the engine is a separate
        process, the window can be closed, resized or covered, the board can
        stop calibrating (result screen, skin change, torn frames) and a click
        can simply be swallowed.  Each of those used to end the round - which is
        indistinguishable from a freeze, because the board just stopped being
        played.  Returns True when the loop is fit to try the step again.
        """
        if self._stop():
            return False
        n = self.stats.get("recover", 0) + 1
        self.stats["recover"] = n
        self.stats["phase"] = "recovering"
        log("[retry] %s - recovery #%d" % (reason, n))
        ok = self.reattach()
        if ok and self.engine is None and not self._stop():
            ok = self.restart_engine()
        if ok:
            self.stats["phase"] = "playing"
        self._sleep(0.4)
        return ok

    def close(self):
        """Release the engine, the injected window style and the GDI caches."""
        self._closed = True
        self._stop_watch()
        if self.engine is not None:
            try:
                self.engine.quit()
            except Exception:
                pass
            self.engine = None
        self.set_quiet(False)
        self.reset_link()

    def summary(self):
        """One compact line per run: what the loop actually did.

        This is the feedback the program is meant to improve from - printed at the
        end of every run so a bad session can be compared with a good one without
        reading the whole log: our own clock time (average and worst move), how
        often a ply was retried or never landed, how often a repair ran, and how
        much of the reading was incremental.
        """
        st = self.stats
        moves = max(1, int(st.get("moves", 0)))
        turn = float(st.get("turn_s", 0.0))
        log("[sum] games=%d moves=%d  clock=%.0fs (avg %.1fs, worst %.1fs, slow %d)  "
            "stalls=%d repairs=%d retries=%d dialogs=%d rematch=%d  reads=%d recog=%d "
            "incr=%d  engine fails=%d  bg_fallback=%d" % (
                int(st.get("games", 1)), int(st.get("moves", 0)), turn, turn / moves,
                float(st.get("turn_max", 0.0)), int(st.get("slow", 0)),
                int(st.get("stalls", 0)), int(st.get("recover", 0)),
                int(st.get("attempts", 0)), int(st.get("dialogs", 0)),
                int(st.get("rematch", 0)), int(st.get("reads", 0)),
                int(st.get("recognitions", 0)), int(st.get("incr", 0)),
                int(st.get("fails", 0)), int(st.get("bg_fallback", 0))))
        return st

    # -- main loop ---------------------------------------------------------
    def run(self, max_moves=200, first=None, opp_timeout=60.0, probe_wait=3.0):
        if self.engine is None:
            self.start_engine()
        self._start_watch()
        g = a = None
        for attempt in range(1, self.retries + 1):
            if self._stop():
                return self.grid
            g, a = self.stable_grid(timeout=12.0)
            if g is not None:
                break
            log("[start] no readable board yet (attempt %d/%d)" % (attempt, self.retries))
            if attempt < self.retries and not self.recover(
                    "no stable board reading at the start"):
                time.sleep(1.0)
        if g is None:
            # Nothing readable, and every quick retry has been spent.  This is NOT
            # a reason to end the run: the window is still there, the app is simply
            # showing something we cannot read (a menu, an animation, a lattice
            # that reads a quiet endgame wrong).  Watch the window until a board
            # appears - the user asked for a game, and a screen we cannot parse yet
            # is not the game being over.  The old behaviour (raise here) is what
            # killed the program in the field: the worker thread died with a
            # traceback, the console gave up, and the user had to start again.
            log("[start] no board to read yet - watching the window for one "
                "(press 停止 to quit)")
            g, a = self.wait_for_board(timeout=0.0)
            if g is None:
                return self.grid
        self.set_grid(g)
        self.stats["phase"] = "playing"
        log("[start] pos " + B.grid_to_fen(g, self.our_side))

        if first is None:
            if B.is_opening(g) and self.our_side == "w":
                our_turn = True
            else:
                log("[start] unknown turn; watching the board for %.1fs" % probe_wait)
                g2, a2 = self.wait_change(g, timeout=probe_wait)
                if g2 is not None:
                    log("[opp] " + describe(g, g2))
                    self.grid = g2
                our_turn = True
        else:
            our_turn = (first == "me")
            if B.is_opening(g):
                # At the starting position red moves first, so "the opponent moves
                # first" is exactly "we play black" - trust the rules over the
                # setting when the two disagree.
                want = (self.our_side == "w")
                if want != our_turn:
                    log("[start] the board is at the starting position and we play %s, "
                        "so the first move is %s - the first-move setting says otherwise"
                        % ("red" if self.our_side == "w" else "black",
                           "ours" if want else "the opponent's"))
                our_turn = want
            elif not our_turn:
                # "The opponent moves first" with a board that is already off the
                # starting position: do NOT fake a ply (our clock runs while we
                # sit there), but neither pretend the setting outranks the game.
                # Wait for the opponent like the setting asks; if nothing happens
                # the existing timeout path hands the turn back and we play.
                log("[start] the board is not at the starting position and the "
                    "first-move setting says the opponent plays first - waiting "
                    "for their move, then playing on our turn")
        log("[start] our_turn=%s" % our_turn)

        played = 0
        ours = 0
        stall = 0
        idle = 0
        nobest = 0
        illegal = 0
        # Do we KNOW the opponent has to move?  Waiting the full opp_timeout for a
        # move is only worth it when we do; when the turn was merely inferred (a
        # resync, a misread) the wait is capped so a wrong guess cannot burn a
        # minute of our own clock.
        sure = True
        while played < max_moves and not self._stop():
            if not our_turn:
                idle += 1
                log("[wait] opponent ... (idle wait %d)" % idle)
                wait = opp_timeout if sure else min(opp_timeout, self.UNCERTAIN_WAIT)
                if wait < opp_timeout:
                    log("[wait] not sure the opponent is to move - waiting at most "
                        "%.0fs, then playing on (our clock may be running)" % wait)
                g2, a2 = self.wait_change(self.grid, timeout=wait)
                if g2 is None:
                    # Nothing came from the opponent.  Either the game is really
                    # waiting for us (a misread turn) or the app sits on a screen
                    # we cannot read.  Never stop here - look at the board, and
                    # take the turn ourselves when it is plainly unchanged: a
                    # stray click during the opponent's turn is harmless, the
                    # game itself enforces the order.
                    log("[wait] no opponent move in %.0fs (idle %d) - checking the board"
                        % (wait, idle))
                    g3, _a3 = self.stable_grid(timeout=6.0)
                    if g3 is not None:
                        r = self.set_grid(g3)
                        if r == "stop":
                            break
                        if r:
                            played = ours = stall = idle = 0
                            our_turn = (self.our_side == "w")
                            continue
                        if g3 != self.grid:
                            log("[opp] " + describe(self.grid, g3))
                            idle = 0
                            our_turn = True
                            continue
                        log("[wait] the position is unchanged - taking the turn ourselves")
                        idle = 0
                        our_turn = True
                        continue
                    # Nothing readable: the round may just be over, in which
                    # case the app is waiting for 再来一局 to be pressed.
                    self.handle_continue(self.frame())
                    if idle >= 2:
                        log("[wait] still nothing readable - the game looks idle or is "
                            "showing another screen; keeping the watch (press 停止 to quit)")
                    if idle >= max(2, self.retries) * 2:
                        self.recover("the opponent has not moved for a long time")
                        idle = 1
                    continue
                idle = 0
                log("[opp] " + describe(self.grid, g2))
                r = self.set_grid(g2)
                if r == "stop":
                    break
                if r:
                    played = ours = stall = 0
                    our_turn = (self.our_side == "w")
                    continue
                if not self.plausible(g2):
                    save_dbg(a2, "implausible")
                sure = True                  # they moved: they are the ones playing
                our_turn = True
                stall = 0
                continue

            fen = B.grid_to_fen(self.grid, self.our_side)
            log("[think] " + fen)
            # A board the rules cannot reach is a misread, not a position: this
            # engine answers such a board by exiting ("CRITICAL ERROR ...
            # Unsupported position"), which used to cost the engine, the
            # remaining retries and - once every attempt had failed - the whole
            # run.  Never ask; re-read and, if it persists, refit instead.
            ok, why = B.position_ok(self.grid, self.our_side)
            if not ok:
                illegal += 1
                log("[think] the read board is not a position the rules allow (%s) - "
                    "not asking the engine, re-reading instead (bad read %d/%d)"
                    % (why, illegal, self.retries * 2))
                save_dbg(a2 or self.frame(), "illegal_position")
                if illegal >= self.retries * 2:
                    # Nothing readable for a while: the app may be on another
                    # screen.  Stop burning our own clock on it and watch the
                    # board instead - the watch loops recover and answer panels.
                    illegal = 0
                    sure = False
                    our_turn = False
                    continue
                if illegal >= self.retries:
                    if not self.recover("the board keeps reading as a position "
                                        "the rules cannot reach"):
                        self._sleep(0.5)
                g8, _a8 = self.stable_grid(timeout=4.0)
                if g8 is not None:
                    r = self.set_grid(g8)
                    if r == "stop":
                        break
                    if r:
                        played = ours = stall = idle = nobest = 0
                        illegal = 0
                        our_turn = (self.our_side == "w")
                        continue
                    if g8 != self.grid:
                        log("[opp] " + describe(self.grid, g8))
                    illegal = 0
                    continue
                our_turn = True
                self._sleep(0.2)
                continue
            illegal = 0
            t_turn = time.time()             # our clock starts here
            # The opening book answers from the position: a search here costs
            # ~0.5s of our own clock for a move every book already knows, and
            # the log showed that being paid at the start of every round.
            bm, d = None, {}
            if self.book_on and self.book is not None:
                try:
                    bm = self.book.lookup(self.grid, self.our_side,
                                          getattr(self, "session_ply", 0))
                except Exception as exc:
                    bm = None
                    self.warn("[book] lookup failed: %s: %s" % (
                        type(exc).__name__, exc))
                if bm:
                    log("[book] %s (line %r, ply %d) - no search needed" % (
                        bm, self.book.last_line, getattr(self, "session_ply", 0)))
                    d = {"depth": 0, "score_kind": "book", "score": 0,
                         "nodes": 0, "nps": None}
            if not bm:
                for attempt in range(1, self.retries + 1):
                    if not self._pause_gate():
                        break
                    t0 = time.time()
                    try:
                        bm, _pd, info = self.engine.bestmove(fen, movetime=self.movetime)
                    except EngineRefusal as exc:
                        # The engine does not merely die here: it says the position
                        # itself is impossible.  Retrying it would kill the fresh
                        # engine too, so stop and let the no-move path re-read the
                        # board (the read is the thing that is wrong).
                        bm = None
                        self.stats["fails"] = self.stats.get("fails", 0) + 1
                        log("[think] %s" % exc)
                        self.restart_engine()
                        break
                    except Exception as exc:
                        # The engine is a separate process and can die mid-game; a
                        # dead one only ever answers with timeouts, so replace it.
                        bm = None
                        self.stats["fails"] = self.stats.get("fails", 0) + 1
                        log("[think] the engine failed on attempt %d/%d: %s: %s" % (
                            attempt, self.retries, type(exc).__name__, exc))
                        if not self.restart_engine():
                            self.recover("the engine will not start")
                            time.sleep(1.0)
                        continue
                    d = last_info(info)
                    log("[best] %s  depth=%s %s=%s nodes=%s  %.2fs" % (
                        bm, d.get("depth"), d.get("score_kind", "score"), d.get("score"),
                        d.get("nodes"), time.time() - t0))
                    if bm and len(bm) >= 4:
                        break
                    log("[think] the engine returned no move on attempt %d/%d" % (
                        attempt, self.retries))
                    time.sleep(0.3)
            self.stats.update(fen=fen, best=bm or "", depth=d.get("depth"),
                              score=d.get("score"), nodes=d.get("nodes"),
                              nps=d.get("nps"), phase="thinking")
            if not bm or len(bm) < 4:
                nobest += 1
                dt = self._turn_time(t_turn)
                log("[best] the engine has no move for this position (attempt %d/%d, "
                    "%.1fs spent) - a confused engine is replaced before we believe "
                    "the round is over" % (nobest, self.retries, dt))
                # A wedged or confused engine answers "no move" instead of dying:
                # replace it once before concluding that we are mated (the round
                # being over is the only other reason it has no move).
                if nobest == 1 and self.engine is not None:
                    self.restart_engine()
                g5, _a5 = self.stable_grid(timeout=6.0)
                if g5 is not None and g5 != self.grid:
                    log("[opp] " + describe(self.grid, g5))
                    r = self.set_grid(g5)
                    if r == "stop":
                        break
                    if r:
                        played = ours = stall = nobest = 0
                        our_turn = (self.our_side == "w")
                        continue
                    nobest = 0
                    our_turn = False
                    continue
                if nobest < self.retries:
                    if not self.recover("the engine has no move for this position"):
                        if not self._pause_gate():
                            break
                    our_turn = True
                    continue
                # No legal move and the board is not changing: the round is over.
                # Wait for the app to start the next one instead of quitting, so
                # a tournament round that restarts is picked up automatically.
                log("[end] no legal move for us and the board is not changing - the "
                    "round looks finished")
                g6, _a6 = self.stable_grid(timeout=8.0)
                if g6 is None:
                    log("[end] the board is not readable any more (result screen?) - "
                        "waiting up to 60s for the next round")
                    g6, _a6 = self.wait_next_round(timeout=60.0)
                if g6 is None:
                    log("[end] no next round seen - stopping (press 开始对局 to resume)")
                    break
                r = self.set_grid(g6)
                if r == "stop":
                    break
                if r:
                    played = ours = stall = nobest = idle = 0
                    our_turn = (self.our_side == "w")
                    continue
                nobest = 0
                our_turn = False
                continue
            fi, fj = B.parse_uci(bm[:2])
            ti, tj = B.parse_uci(bm[2:4])
            before = self.grid
            # apply_move returns a fresh grid; forgetting the assignment here is
            # what made the loop believe the opponent had answered every time.
            want = B.apply_move(B.clone(before),
                                ((fi, fj), (ti, tj), before[fj][fi], before[tj][ti]))
            if self.dry:
                log("[dry] rehearsal only - not clicking: %s -> %s  (screen %s -> %s)" % (
                    bm[:2], bm[2:4], self.cell_xy(fi, fj), self.cell_xy(ti, tj)))
                break
            self.play_move(fi, fj, ti, tj)

            g2 = a2 = None
            already = False
            seen = False
            for attempt in range(1, self.retries + 1):
                if not self._pause_gate():
                    break
                g2, a2, already = self.settle_after(before, want,
                                                     timeout=self.SETTLE_TIMEOUT)
                if g2 is not None:
                    seen = (g2 == want) or bool(already) or \
                        B.move_visible(before, g2, fi, fj, ti, tj)
                    if seen:
                        break
                    log("[play] our ply is not on the board after attempt %d/%d" % (
                        attempt, self.retries))
                else:
                    log("[play] no settled board after attempt %d/%d" % (
                        attempt, self.retries))
                if attempt >= self.retries:
                    break
                # The click was swallowed (or the app was busy repainting):
                # repair the link and click the very same move again.
                self.stats["attempts"] = self.stats.get("attempts", 0) + 1
                if self.background:
                    self._quiet_failed("the quiet click did not land - retrying this "
                                       "move with an ordinary click")
                if not self.recover("our move %s -> %s was not confirmed" % (
                        bm[:2], bm[2:4])):
                    time.sleep(0.4)
                self.play_move(fi, fj, ti, tj)

            if g2 is not None and self.is_new_game(g2):
                # The round restarted while we were waiting for our own ply:
                # begin the new game with a clean slate instead of feeding the
                # engine the position of the game that just ended.
                if self.set_grid(g2) == "stop":
                    break
                played = ours = stall = 0
                our_turn = (self.our_side == "w")
                continue
            if seen:
                dt = self._turn_time(t_turn)
                if g2 == want:
                    log("[play] confirmed %s -> %s in %.1fs" % (bm[:2], bm[2:4], dt))
                    already = False
                elif already:
                    log("[play] confirmed %s -> %s in %.1fs, opponent already answered" %
                        (bm[:2], bm[2:4], dt))
                else:
                    log("[play] our ply landed but the board carries more: " +
                        B.grid_to_fen(g2, self.our_side))
                    for m in B.diff_moves(before, g2):
                        log("[play]   %s" % (m,))
                    # Our ply *is* visible, so the remaining delta can only be a
                    # reply (or a repaired earlier misread).  Either way the board
                    # we just read is authoritative, so think again from it.
                    already = True
                if not self.plausible(g2):
                    log("[play] implausible board - refusing to feed the engine")
                    save_dbg(a2, "implausible_after_play")
                    # Keep the last board we trusted and wait for the screen to
                    # show something sane again instead of ending the round.
                    if not self.recover("the board read was implausible"):
                        time.sleep(1.0)
                    sure = False
                    our_turn = False
                    continue
                self.set_grid(g2)
                played += 1
                ours += 1
                self.stats["moves"] = ours
                stall = 0
                sure = True                  # we just moved: their turn to answer
                our_turn = bool(already)
                continue

            # Our ply is nowhere on the board: the click was swallowed, the app
            # ignored it (not our turn after all) or the screen is mid-repaint.
            # Resync and play again - quickly, because our own clock is running the
            # whole time.  The old code watched for up to 8s here, then spent a 6s
            # resync read plus another repair per stall, and finally handed the turn
            # back to the opponent for a full opp_timeout: a minute of silence, and
            # that is how a round was lost on time without a single mistake.
            #
            # One bounded episode now: watch the board for a few seconds (the watch
            # grows slowly, so a round that really is waiting for the opponent is
            # not click-spammed), take their ply if it arrived, and otherwise think
            # again and play - never wait for a move that cannot come.
            stall += 1
            self.stats["fails"] = self.stats.get("fails", 0) + 1
            self.stats["stalls"] = self.stats.get("stalls", 0) + 1
            if stall >= 2 and time.time() - self._refit_t >= 10.0:
                # The ply lands nowhere while the board reads fine: the clicks are
                # most likely aimed with a stale fit (another game mode draws the
                # board at a different size).  Refit instead of hammering squares.
                self._refit_t = time.time()
                self.cal = None
                self.prev = None
                self.hints = {}
                log("[play] %d plies in a row landed nowhere - refitting the board "
                    "(a new game mode or a resized window changes it)" % stall)
                fresh = self._ensure_cal(tries=3, gap=0.3)
                if fresh is not None:
                    # The pack is scaled to the lattice pitch: a refit at another
                    # size needs its own.
                    self._adopt_templates(fresh, force=True)
                    log("[play] the board was refitted (%.0fpx/%.0fpx across the files)"
                        % (float(self.cal.get("cpitch") or 0.0),
                           float(self.cal.get("rpitch") or 0.0)))
                    stall = 0
                else:
                    self.warn("[play] the screen still does not show a readable board")
            dt = self._turn_time(t_turn)
            watch = min(self.STALL_WATCH + 3.0 * (self.stats["stalls"] // 3), 15.0)
            log("[play] %s -> %s is still not on the board (fail %d/%d, %.1fs spent) - "
                "watching the board for %.0fs" % (
                    bm[:2], bm[2:4], stall, self.retries, dt, watch))
            if not self.recover("our move %s -> %s did not land" % (bm[:2], bm[2:4])):
                time.sleep(0.4)
            g3, _a3 = self.wait_change(self.grid, timeout=watch)
            if g3 is not None:
                log("[opp] " + describe(self.grid, g3))
                r = self.set_grid(g3)
                if r == "stop":
                    break
                if r:
                    played = ours = stall = idle = 0
                    sure = True
                    our_turn = (self.our_side == "w")
                    continue
                played += 1
                stall = 0
                idle = 0
                sure = True
                our_turn = True
                continue
            log("[stall] nothing moved and it is our turn - thinking again (our clock "
                "is running)")
            stall = 0
            sure = False
            our_turn = True
            continue

        self.stats["moves"] = ours
        self.stats["phase"] = "idle"
        log("[done] played %d of our moves" % ours)
        self.summary()
        return self.grid


def moves_text(plies, limit=4):
    """One readable line for a series of plies (see board.explain_change)."""
    out = []
    for fc, tc, piece, cap in plies[:limit]:
        out.append("%s%d-%s%d(%s%s)" % (
            chr(ord("a") + fc[0]), 9 - fc[1], chr(ord("a") + tc[0]), 9 - tc[1],
            piece, ("x" + cap) if cap != "." else ""))
    if len(plies) > limit:
        out.append("+%d more" % (len(plies) - limit))
    return " ".join(out)


def describe(a, b, limit=8):
    """Human readable summary of what changed between two boards.

    A board that is not one ply away from the previous one (a rejected jump, a
    round that restarted) can differ in every cell; only the first *limit* of
    them are spelled out so one log line stays readable.
    """
    mvs = B.diff_moves(a, b)
    if not mvs:
        return "no change"
    out = []
    for m in mvs[:limit]:
        if m[0] == "?":
            out.append("cell %s: %s -> %s" % (m[1], m[2], m[3]))
        else:
            out.append("%s%s -> %s%s (%s%s)" % (
                chr(ord("a") + m[0][0]), 9 - m[0][1],
                chr(ord("a") + m[1][0]), 9 - m[1][1], m[2],
                ("x" + m[3]) if m[3] != "." else ""))
    if len(mvs) > limit:
        out.append("(+%d more)" % (len(mvs) - limit))
    return ", ".join(out)
