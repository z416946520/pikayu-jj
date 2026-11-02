# -*- coding: utf-8 -*-
"""pikafishjj.engine - persistent Pikafish UCI subprocess.

Note: this Pikafish build does NOT honour "go nodes N" (it returns immediately
with bestmove). Use "go movetime N" or "go depth N" instead.
"""
import os
import queue
import subprocess
import threading
import time


class EngineError(RuntimeError):
    pass


class EngineRefusal(EngineError):
    """The engine refused the position and exited (Pikafish: "Unsupported position").

    A refused position is *our* problem - the board read does not obey the rules -
    so it is worth telling apart from a dead engine: retrying the same position
    only kills the fresh engine too.
    """


class Engine(object):
    def __init__(self, exe, threads=8, hash_mb=1024, nnue=None, verbose=False):
        self.exe = exe
        self.verbose = verbose
        self.lock = threading.Lock()          # held for the whole search
        self._wlock = threading.Lock()        # serialises writes to the engine
        cwd = os.path.dirname(os.path.abspath(exe))
        if nnue is None:
            cand = os.path.join(cwd, "pikafish.nnue")
            nnue = cand if os.path.exists(cand) else None
        creation = 0
        if os.name == "nt":
            creation = 0x08000000  # CREATE_NO_WINDOW
        self.p = subprocess.Popen(
            [exe], cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True,
            creationflags=creation)
        # One reader thread owns stdout for the whole session: a thread per
        # readline() left zombies behind whenever a line was slow, and two live
        # readers on the same buffered stream silently swallow each other's
        # lines - which is exactly how a cold first start (antivirus scanning
        # the freshly extracted engine) turned into "timeout waiting for
        # readyok" after a full 30 s.
        self._lines = queue.Queue()
        self._reader = threading.Thread(target=self._pump)
        self._reader.daemon = True
        self._reader.start()
        self.name = "?"
        try:
            self._send("uci")
            self._wait("uciok", 10.0)
            self._send("setoption name Threads value %d" % threads)
            self._send("setoption name Hash value %d" % hash_mb)
            if nnue:
                self._send("setoption name EvalFile value %s" % nnue)
            self.sync()
        except Exception:
            # Never leave a half-initialised engine behind: it would keep its
            # Hash allocation (up to gigabytes) alive for the whole session.
            try:
                self.p.kill()
                self.p.wait(timeout=3)
            except Exception:
                pass
            raise

    # -- low level ---------------------------------------------------------
    def _send(self, line):
        with self._wlock:
            if self.verbose:
                print(">>", line)
            self.p.stdin.write(line + "\n")
            self.p.stdin.flush()

    def stop(self):
        """Abort the search in progress - safe from another thread.

        bestmove() holds the search lock for the whole search, so a watcher that
        wants to honour 暂停/停止 while the engine is thinking cannot wait for it:
        it writes UCI stop through the write lock instead, and Pikafish answers
        with a bestmove right away, which lets the loop check its buttons.
        """
        try:
            self._send("stop")
            return True
        except Exception:
            return False

    def _pump(self):
        try:
            for ln in self.p.stdout:
                self._lines.put(ln)
        except Exception:
            pass
        self._lines.put(None)          # sentinel: the engine is gone

    def _readline(self, timeout):
        """Next output line, or None when nothing arrived in time."""
        try:
            ln = self._lines.get(timeout=max(0.05, timeout))
        except queue.Empty:
            return None
        if ln is None:
            raise EngineError("the engine process exited unexpectedly (no output left)")
        if "CRITICAL ERROR" in ln:
            # Pikafish reports an impossible position this way and then exits, so
            # say what it said before the process is gone: the reason is the only
            # clue that the *board* was wrong rather than the engine.
            why = ln.split("Reason:", 1)[-1].strip() or ln.strip()
            raise EngineRefusal("the engine refused the position: " + why)
        return ln

    def _wait(self, token, timeout):
        t0 = time.time()
        while time.time() - t0 < timeout:
            ln = self._readline(max(0.2, timeout - (time.time() - t0)))
            if ln is None:
                continue
            ln = ln.strip()
            if self.verbose:
                print("<<", ln)
            if ln.startswith("id name"):
                self.name = ln[7:].strip()
            if ln.startswith(token):
                return ln
        raise EngineError("timeout waiting for %r" % token)

    def sync(self, timeout=30.0):
        self._send("isready")
        self._wait("readyok", timeout)
        return True

    # -- public ------------------------------------------------------------
    def bestmove(self, fen, movetime=2000, depth=None, extra=()):
        """Return (bestmove, ponder, info_lines). fen is a xiangqi FEN string."""
        with self.lock:
            self._send("position fen " + fen)
            if depth:
                go = "go depth %d" % depth
            else:
                go = "go movetime %d" % int(movetime)
            for e in extra:
                go += " " + e
            self._send(go)
            info = []
            # A dead or wedged engine only ever answers with timeouts, and every
            # second of that is spent on OUR clock: the wait is therefore kept
            # proportional to the time we asked it to think for (400 ms asked ->
            # 4.6 s tolerated, 3 s asked -> 15 s tolerated) instead of a flat 10 s
            # that, with the retries behind it, could cost half a minute a move.
            deadline = time.time() + max(4.0, movetime / 1000.0 * 4.0 + 3.0)
            best, ponder = None, None
            while time.time() < deadline:
                ln = self._readline(deadline - time.time())
                if ln is None:
                    continue
                ln = ln.strip()
                if self.verbose:
                    print("<<", ln)
                if ln.startswith("info"):
                    info.append(ln)
                elif ln.startswith("bestmove"):
                    parts = ln.split()
                    best = parts[1] if len(parts) > 1 else None
                    if "ponder" in parts:
                        ponder = parts[parts.index("ponder") + 1]
                    break
            if best is None:
                self._send("stop")
                t1 = time.time()
                while time.time() - t1 < 3.0:
                    ln = self._readline(0.5)
                    if ln and ln.strip().startswith("bestmove"):
                        parts = ln.split()
                        return (parts[1] if len(parts) > 1 else None), None, info
                raise EngineError("no bestmove returned for " + fen)
            return best, ponder, info

    def quit(self):
        try:
            self._send("quit")
            self.p.wait(timeout=3)
        except Exception:
            try:
                self.p.kill()
            except Exception:
                pass


def last_info(info_lines):
    """Parse the final info line into a dict of pv/score/depth/nodes."""
    d = {}
    for ln in reversed(info_lines):
        if " pv " in ln:
            toks = ln.split()
            d["depth"] = int(toks[toks.index("depth") + 1]) if "depth" in toks else None
            if "score" in toks:
                i = toks.index("score")
                d["score_kind"] = toks[i + 1]
                d["score"] = int(toks[i + 2])
            if "nodes" in toks:
                d["nodes"] = int(toks[toks.index("nodes") + 1])
            if "nps" in toks:
                d["nps"] = int(toks[toks.index("nps") + 1])
            if "time" in toks:
                d["time"] = int(toks[toks.index("time") + 1])
            d["pv"] = toks[toks.index("pv") + 1:]
            return d
    return d
