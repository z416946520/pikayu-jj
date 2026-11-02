# -*- coding: utf-8 -*-
"""pikafishjj one-file entry point.

No arguments                        -> the tkinter console.
ui / probe / play / selftest ...    -> the matching command line tool.
"""
import os
import sys


class _Tee(object):
    """Write every line to several streams (console, pipe and/or log file)."""

    def __init__(self, streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
            except Exception:
                pass
        return len(s)

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def _cli_console():
    """A --windowed build has no console of its own: borrow the parent one.

    PIKAFISHJJ_LOGFILE additionally mirrors everything into a text file, which
    is the only reliable way to see the output when nothing else captures it.
    """
    streams = []
    if sys.stdout is not None:
        try:
            sys.stdout.write("")
            streams.append(sys.stdout)
        except Exception:
            pass
    if os.name == "nt" and not streams:
        try:
            import ctypes
            k = ctypes.windll.kernel32
            if not k.AttachConsole(-1):      # ATTACH_PARENT_PROCESS
                k.AllocConsole()
            streams.append(open("CONOUT$", "w", encoding="utf-8", buffering=1))
        except Exception:
            pass
    path = os.environ.get("PIKAFISHJJ_LOGFILE")
    if path:
        try:
            streams.append(open(path, "w", encoding="utf-8", buffering=1))
        except Exception:
            pass
    if streams:
        sys.stdout = _Tee(streams)
        sys.stderr = sys.stdout


def main():
    argv = list(sys.argv[1:])
    if argv:
        _cli_console()
        try:
            sys.stdout.write("[pikafishjj] pid %d frozen=%s argv=%r\n" % (
                os.getpid(), getattr(sys, "frozen", False), argv))
        except Exception:
            pass
        from pikafishjj.run import main as cli
        return cli(argv)
    from pikafishjj import gui
    return gui.main()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        sys.exit(main() or 0)
    except SystemExit:
        raise
    except Exception:
        import traceback
        tb = traceback.format_exc()
        try:
            d = os.path.dirname(os.path.abspath(sys.executable))
            with open(os.path.join(d, "pikafishjj-error.log"), "a", encoding="utf-8") as fh:
                fh.write(tb + "\n")
        except Exception:
            pass
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, tb[-1600:], "pikafishjj \u9519\u8bef", 0x10)
        except Exception:
            pass
        sys.exit(1)
