# -*- coding: utf-8 -*-
"""pikafishjj.bridge - the two pluggable axes of the bot.

    board  = "vision"  | "backend"     where the position comes from
    moves  = "physical"| "backend"     how our move is delivered

vision   : screenshots + template matching (what the project ships today)
backend  : the running mini-program's own state (its process memory)
physical : a real mouse click on the board
backend  : hand the move to the program through its own channel, no mouse

The backend halves are being built in tools/jj-mem: the board field in the app's
memory has not been located yet, and no injection channel into the sandboxed
applet is verified.  Until one is, they report themselves **unavailable with a
reason** instead of pretending, and AutoPlayer(fallback=True) - the default -
keeps running on the vision/physical pair so a game is never blocked by
half-finished plumbing.
"""
import json
import os
import re
import subprocess

APPID = "wx0c852640e4324692"          # JJ象棋 (微信小程序)
BOARDS = ("vision", "backend")
MOVES = ("physical", "backend")
LAYOUT_NAME = "jj_board_layout.json"


def layout_path():
    """Where the located board layout is cached (next to the config)."""
    from .auto import user_dir
    return os.path.join(user_dir(), LAYOUT_NAME)


class BridgeUnavailable(RuntimeError):
    """A backend half was asked for, but its channel is not ready."""


# -- board sources ---------------------------------------------------------
class BoardSource(object):
    name = "?"
    is_backend = False

    def available(self, player):
        """(ok, reason). False means: do not use me."""
        return True, ""

    def start(self, player):
        return True

    def read(self, player, timeout=8.0, need=3, interval=0.03):
        """(internal grid, frame) or (None, None)."""
        raise NotImplementedError

    def describe(self):
        return self.name


class VisionSource(BoardSource):
    """The shipped reading path: screenshot, fit the lattice, match templates."""
    name = "vision"

    def read(self, player, timeout=8.0, need=3, interval=0.03):
        return player._vision_stable_grid(timeout=timeout, need=need, interval=interval)

    def describe(self):
        return "vision (screenshot + template match)"


class MemorySource(BoardSource):
    """Backend: read the board straight out of the mini-program's process memory.

    The layout is whatever tools/jj-mem/find_board.py discovered and cached:

        {"appid": "wx...", "pid": 5604, "base": 12345678, "stride": 1,
         "order": "row", "flip_rows": false, "flip_cols": false, "empty": 0,
         "codes": {"K": 1, "A": 2, "B": 3, "N": 4, "R": 5, "C": 6, "P": 7},
         "case": "red-upper"}

    Until that file exists the source is unavailable, with the reason kept so the
    run log says exactly what is missing.
    """
    name = "backend(memory)"
    is_backend = True
    PIECES = "KABNRCPkabnrcp"

    def __init__(self, reader=None, path=None, pid=None):
        self.reader = reader or read_process_memory
        self.path = path or layout_path()
        self.forced_pid = pid
        self.layout = None
        self.reason = ("no board layout cached yet - run tools/jj-mem/find_board.py "
                       "against a live game to locate it")
        self.pid = None

    def layout_problem(self, lay):
        """Why this cached layout cannot read a board, or None.

        A layout that only has an address is not usable: find_board.py writes the
        address first and leaves the code table empty until a known position fills
        it, and a reader without codes turns every square into an empty one - the
        run would simply never see a board instead of falling back.
        """
        if not isinstance(lay, dict):
            return "the cached board layout is not readable"
        codes = lay.get("codes") or {}
        missing = [c for c in self.PIECES if str(c) not in codes]
        if missing:
            return ("the cached board layout has no code for %s - fill the codes table "
                    "from a known position (tools/jj-mem/find_board.py write-layout)"
                    % "".join(missing))
        try:
            empty = int(lay.get("empty"))
        except (TypeError, ValueError):
            return "the cached board layout has no empty-square value"
        if str(empty) in codes:
            return "the cached board layout uses the same value for empty and a piece"
        try:
            base, stride = int(lay.get("base") or 0), int(lay.get("stride", 1))
        except (TypeError, ValueError):
            return "the cached board layout has a bad address or stride"
        if base <= 0:
            return "the cached board layout has no address"
        if stride not in (1, 2, 4, 8):
            return "the cached board layout has a stride of %d - not a cell array" % stride
        return None

    def _load_layout(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            self.reason = "cannot read %s: %s" % (self.path, exc)
            return None

    def available(self, player):
        if not os.path.isfile(self.path):
            return False, self.reason
        lay = self._load_layout()
        if lay is None:
            return False, self.reason
        bad = self.layout_problem(lay)
        if bad:
            self.reason = bad
            return False, bad
        self.layout = lay
        return True, ""

    def start(self, player):
        if self.layout is None:
            self.layout = self._load_layout()
            if self.layout is None:
                return False
            bad = self.layout_problem(self.layout)
            if bad:
                self.reason = bad
                self.layout = None
                return False
        appid = self.layout.get("appid") or APPID
        if self.forced_pid is not None:
            self.pid = int(self.forced_pid)
        else:
            cached = int(self.layout.get("pid") or 0)
            self.pid = cached if (cached and process_has_appid(cached, appid)) else None
            if self.pid is None:
                self.pid = find_app_process(appid)
        if not self.pid:
            self.reason = ("no WeChatAppEx process holds %s - is the mini-program open?"
                           % appid)
            return False
        return True

    def read(self, player, timeout=8.0, need=3, interval=0.03):
        if not self.layout:
            if not self.start(player):
                return None, None
        if not self.pid:
            return None, None
        lay = self.layout
        base = int(lay["base"])
        stride = int(lay.get("stride", 1))
        span = 90 * stride
        import time
        t0 = time.time()
        tries = 0
        while time.time() - t0 < max(0.5, timeout):
            blob = self.reader(self.pid, base, span)
            if blob is None or len(blob) < span:
                time.sleep(interval)
                continue
            tries += 1
            if stride == 1:
                vals = list(blob[:90])
            else:
                vals = [int.from_bytes(blob[k * stride:(k + 1) * stride], "little")
                        for k in range(90)]
            g = self._to_grid(vals, lay)
            if player.plausible(g):
                return g, None
            time.sleep(interval)
        if tries and player is not None:
            # Say it out loud: the address is cached, so a board that stops reading
            # as a position means the layout went stale (the mini-program was
            # restarted and the field moved), not that the game is unreadable.
            player.warn("[bridge] the board at %s (pid %s) does not read as a position "
                        "any more - the cached layout may be stale, re-run "
                        "tools/jj-mem/find_board.py" % (hex(base), self.pid), gap=15.0)
        return None, None

    def _to_grid(self, vals, lay):
        """90 raw cells -> the internal 10x9 grid (row 0 = black back rank)."""
        codes = dict((int(v), k) for k, v in (lay.get("codes") or {}).items())
        empty = int(lay.get("empty", 0))
        order = lay.get("order", "row")
        fr = bool(lay.get("flip_rows"))
        fc = bool(lay.get("flip_cols"))
        g = [["."] * 9 for _ in range(10)]
        for k in range(90):
            if order == "row":
                r, c = divmod(k, 9)
            else:
                c, r = divmod(k, 10)
            if fr:
                r = 9 - r
            if fc:
                c = 8 - c
            v = vals[k]
            if v == empty:
                continue
            g[r][c] = codes.get(v, ".")
        return g

    def describe(self):
        if not self.layout:
            return "backend (memory, not located)"
        return "backend (memory @%s of pid %s)" % (hex(int(self.layout.get("base", 0))),
                                                   self.pid)


class NullSource(BoardSource):
    """A source that never reads anything - used by tests."""
    name = "null"
    is_backend = True

    def __init__(self, grid=None, ok=True, reason=""):
        self.grid = grid
        self.ok = ok
        self.reason = reason
        self.reads = 0

    def available(self, player):
        return self.ok, self.reason

    def read(self, player, timeout=8.0, need=3, interval=0.03):
        self.reads += 1
        return self.grid, None

    def describe(self):
        return "null"


# -- move sinks ------------------------------------------------------------
class MoveSink(object):
    name = "?"
    is_backend = False

    def available(self, player):
        return True, ""

    def start(self, player):
        return True

    def play(self, player, fi, fj, ti, tj):
        raise NotImplementedError

    def describe(self):
        return self.name


class PhysicalSink(MoveSink):
    """The shipped path: click the source square, then the target square."""
    name = "physical"

    def play(self, player, fi, fj, ti, tj):
        return player._physical_play(fi, fj, ti, tj)

    def describe(self):
        return "physical (mouse click on the board)"


class BackendSink(MoveSink):
    """Backend: make the move without touching the mouse.

    Three channels are planned, in order of preference; none is verified yet:

      applet-js   evaluate inside the applet's JS context (needs the runtime's
                  debug channel - the renderer refuses injection today)
      protocol    send the applet's own move message (needs the game protocol and
                  its transport, which is WeChat's own sealed stack)
      state-write write the move into the applet's own board field (only safe in
                  local modes such as 残局/人机, where no server owns the state)
    """
    name = "backend"
    is_backend = True
    CHANNELS = ("applet-js", "protocol", "state-write")

    def __init__(self, channel="applet-js"):
        self.channel = channel
        self.reason = ("no backend move channel is ready yet (tried: %s); the applet's JS "
                       "context refuses injection and its protocol is TLS-sealed"
                       % ", ".join(self.CHANNELS))

    def available(self, player):
        return False, self.reason

    def play(self, player, fi, fj, ti, tj):
        ok, why = self.available(player)
        raise BridgeUnavailable(why)

    def describe(self):
        return "backend (%s)" % self.channel


class NullSink(MoveSink):
    """A sink that records moves instead of playing them - used by tests."""
    name = "null"
    is_backend = True

    def __init__(self, ok=True, reason=""):
        self.ok = ok
        self.reason = reason
        self.moves = []

    def available(self, player):
        return self.ok, self.reason

    def play(self, player, fi, fj, ti, tj):
        self.moves.append((fi, fj, ti, tj))
        return True

    def describe(self):
        return "null"


# -- factories -------------------------------------------------------------
def make_source(name):
    if name == "backend":
        return MemorySource()
    if name == "null":
        return NullSource()
    return VisionSource()


def make_sink(name):
    if name == "backend":
        return BackendSink()
    if name == "null":
        return NullSink()
    return PhysicalSink()


# -- the process side of the backend --------------------------------------
def wechat_pids():
    """PIDs of the WeChatAppEx processes (the mini-program runtime)."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='WeChatAppEx.exe'\" | "
             "Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=20)
        return [int(x) for x in (out.stdout or "").split() if x.strip().isdigit()]
    except Exception:
        return []


def read_process_memory(pid, base, size):
    """Raw bytes at (base, size) of another process - None when unreadable."""
    try:
        import ctypes
        import ctypes.wintypes as wt
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        h = k32.OpenProcess(0x0410, False, int(pid))       # QUERY_INFORMATION | VM_READ
        if not h:
            return None
        try:
            buf = ctypes.create_string_buffer(size)
            got = ctypes.c_size_t(0)
            if not k32.ReadProcessMemory(h, ctypes.c_void_p(int(base)), buf, size,
                                         ctypes.byref(got)):
                return None
            return buf.raw[:got.value]
        finally:
            k32.CloseHandle(h)
    except Exception:
        return None


def process_has_appid(pid, appid=APPID):
    """True when *pid* is a live WeChatAppEx process carrying this mini-program."""
    try:
        import ctypes
        import ctypes.wintypes as wt
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        h = k32.OpenProcess(0x1000, False, int(pid))       # QUERY_LIMITED_INFORMATION
        if not h:
            return False
        k32.CloseHandle(h)
    except Exception:
        return False
    blob = read_process_memory(pid, 0x1000000, 4 * 1024 * 1024)
    return bool(blob and str(appid).encode() in blob)


def find_app_process(appid=APPID):
    """The WeChatAppEx process that has this mini-program loaded, or None."""
    marker = str(appid).encode()
    for pid in wechat_pids():
        blob = read_process_memory(pid, 0x1000000, 64 * 1024)
        # cheap probe first: the appid shows up in the runtime's own tables; the
        # caller (find_board.py) does the thorough scan once and caches the pid.
        if blob and marker in blob:
            return pid
    return None


def probe_processes(appid=APPID):
    """[(pid, has_appid)] for the WeChatAppEx processes - used by the finder."""
    out = []
    for pid in wechat_pids():
        blob = read_process_memory(pid, 0x1000000, 4 * 1024 * 1024)
        out.append((pid, bool(blob and str(appid).encode() in blob)))
    return out


def strip_nonprintable(text):
    return re.sub(r"[\x00-\x08\x0b-\x1f]+", "|", text)
