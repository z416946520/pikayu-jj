# -*- coding: utf-8 -*-
"""pikafishjj.gui - the tkinter client console.

Layout
    header      title, state dot and the target-window picker
    body/left   cards: engine parameters and game options (scrollable)
    body/right  board preview (with file numbers) and live statistics
    log         coloured stream with a small toolbar
    action bar  read / start / pause / stop / apply / save / snapshot / self-test / help
    status bar  current state plus the keyboard shortcuts

Shortcuts: F1 help, F5 read, F9 start, F10 pause, F11 stop, Ctrl+S save, Ctrl+L clear log.
Run it with:   python -m pikafishjj.run ui
"""
import json
import os
import queue
import sys
import re
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from . import board as B
from . import w32
from . import vision as V
from .auto import AutoPlayer, DEFAULT_EXE, app_dir, user_dir
from .engine import last_info


def _cfg_path():
    """Where the console keeps its settings.

    Frozen builds must not use the package directory: that is the temporary
    _MEIxxxx extraction folder and it disappears with the process.  Next to
    the exe is the natural place (portable), falling back to %LOCALAPPDATA%.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(user_dir(), "gui_config.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_config.json")


ICON_NAME = "pikafishjj.ico"
APP_ID = "pikafishjj.console.1"


def _icon_candidates():
    """Where the window icon may live, most specific first."""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        cands.append(os.path.join(bundle, "assets", ICON_NAME))
        cands.append(os.path.join(bundle, ICON_NAME))
    if getattr(sys, "frozen", False):
        cands.append(os.path.join(app_dir(), ICON_NAME))
        cands.append(os.path.join(app_dir(), "assets", ICON_NAME))
        cands.append(os.path.join(user_dir(), ICON_NAME))
    cands.append(os.path.join(here, os.pardir, os.pardir, "assets", ICON_NAME))
    return [os.path.normpath(p) for p in cands]


def find_icon():
    """The .ico the title bar and the taskbar should show, or None."""
    for p in _icon_candidates():
        if os.path.isfile(p):
            return p
    return None


def set_app_id(app_id=APP_ID):
    """Windows groups taskbar buttons by AppUserModelID.

    Without an explicit id the console inherits the host process icon
    (python.exe while developing), so the taskbar keeps showing Python no
    matter what the window icon says.  Call before the window exists.
    """
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        return True
    except Exception:
        return False


def set_window_icon(root):
    """Give the console the application icon: title bar, taskbar, dialogs.

    default= is what makes the message boxes and every later Toplevel pick
    the same icon up; the plain call covers the root window itself.
    """
    p = find_icon()
    if not p:
        return None
    ok = False
    for call in (lambda: root.iconbitmap(default=p), lambda: root.iconbitmap(p)):
        try:
            call()
            ok = True
        except Exception:
            pass
    return p if ok else None


CFG_PATH = _cfg_path()
LAYOUT_DUMP = os.environ.get("PIKAFISHJJ_LAYOUT")

GLYPH = {"r": "\u8eca", "n": "\u99ac", "b": "\u8c61", "a": "\u58eb", "k": "\u5c07",
         "c": "\u7832", "p": "\u5352",
         "R": "\u4fe5", "N": "\u5104", "B": "\u76f8", "A": "\u4ed5", "K": "\u5e25",
         "C": "\u70ae", "P": "\u5175"}
SIDES = {"自动识别 (下方为我方)": "auto", "红方 (先手)": "w", "黑方 (后手)": "b"}
FIRSTS = {"\u81ea\u52a8\u5224\u65ad": None, "\u6211\u65b9\u5148\u8d70": "me",
          "\u7b49\u5bf9\u624b\u8d70": "them"}
REQUESTS = {"拒绝 (默认)": "decline", "同意": "accept", "忽略 (不处理)": "off"}
# 棋盘获取：视觉 = 截图识别；后端 = 直接读小程序的进程内存
BOARDS = {"视觉识别 (截图)": "vision", "后端读取 (小程序内存)": "backend"}
# 操作方式：物理 = 鼠标点棋盘；后端 = 走小程序自己的通道，不点鼠标
MOVES = {"物理点击 (鼠标)": "physical", "后端操作 (不点鼠标)": "backend"}
PRESETS = {"\u81ea\u5b9a\u4e49": None,
           "\u5feb\u901f (\u7701\u7535)": {"threads": 4, "hash_mb": 256, "movetime": 400},
           "\u5747\u8861 (\u63a8\u8350)": {"threads": 8, "hash_mb": 1024, "movetime": 1200},
           "\u5f3a\u529b (\u6700\u5f3a)": {"threads": 16, "hash_mb": 3072, "movetime": 3000}}
PRESET_ORDER = ("\u5feb\u901f (\u7701\u7535)", "\u5747\u8861 (\u63a8\u8350)", "\u5f3a\u529b (\u6700\u5f3a)")
PRESET_SHORT = {"\u5feb\u901f (\u7701\u7535)": "\u5feb\u901f",
                "\u5747\u8861 (\u63a8\u8350)": "\u5747\u8861",
                "\u5f3a\u529b (\u6700\u5f3a)": "\u5f3a\u529b"}

# --- palette --------------------------------------------------------------
C = {"bg": "#0f1419", "card": "#1b232d", "field": "#111922", "line": "#2c3a49",
     "fg": "#e7eef6", "muted": "#93a3b5", "dim": "#6b7d91", "gold": "#d9b45b",
     "green": "#41b07c", "red": "#e0664f", "blue": "#4d94c8", "log": "#0a0f14"}
FONT = "Microsoft YaHei UI"
MONO = "Consolas"
CELL = 34
MARGIN = 20
FILE_CN = ("\u4e00", "\u4e8c", "\u4e09", "\u56db", "\u4e94", "\u516d", "\u4e03", "\u516b", "\u4e5d")


def lighten(colour, t=0.18):
    """Mix a #rrggbb colour towards white by t (0..1)."""
    try:
        a = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02x%02x%02x" % tuple(int(v + (255 - v) * t) for v in a)
    except Exception:
        return colour


def _label(mapping, value, default):
    """Map a stored config value back to the label its widget shows."""
    for lab, val in mapping.items():
        if val == value:
            return lab
    for lab, val in mapping.items():
        if val == default:
            return lab
    return list(mapping)[0]


DEFAULTS = {"title": "JJ", "exe": DEFAULT_EXE, "threads": 8, "hash_mb": 1024,
            "movetime": 1200, "side": "auto", "first": None,
            "max_moves": 200, "opp_timeout": 60.0, "probe_wait": 3.0,
            "click_delay": 0.18, "dry": False, "background": False,
            "request": "decline", "new_game": True, "retries": 3, "auto_next": True,
            "engine": True, "board": "vision", "moves": "physical", "fallback": True,
            "geometry": "",
            "preset": "\u5747\u8861 (\u63a8\u8350)"}


class Tip(object):
    """Small hover help: the console packs a lot of parameters."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        self.after = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")

    def _enter(self, _e=None):
        self._cancel()
        self.after = self.widget.after(500, self._show)

    def _leave(self, _e=None):
        self._cancel()
        self._hide()

    def _cancel(self):
        if self.after is not None:
            try:
                self.widget.after_cancel(self.after)
            except Exception:
                pass
            self.after = None

    def _show(self):
        if self.tip is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 14
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry("+%d+%d" % (x, y))
        tk.Label(self.tip, text=self.text, justify="left", bg="#2b3644", fg=C["fg"],
                 relief="solid", bd=1, padx=9, pady=5,
                 font=(FONT, 9)).pack()

    def _hide(self):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


class App(object):
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.player = None
        self.worker = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.mode = ""
        self.cfg_run = dict(DEFAULTS)
        self.cfg = dict(DEFAULTS)
        self._load_cfg()
        self._last_draw = None
        self._last_moves = -1
        self.last_from = None
        self.last_to = None
        self._blink = 0
        self._thinking = ""
        self._tips = []
        self._build()
        self._apply_cfg_to_widgets()
        self._set_info("\u5c1a\u672a\u8fde\u63a5\n\n"
                       "1. \u70b9\u3010\u68c0\u6d4b\u3011\u786e\u8ba4\u6e38\u620f\u7a97\u53e3\n"
                       "2. \u70b9\u3010\u8bfb\u53d6\u68cb\u76d8\u3011\u9884\u89c8\u5f53\u524d\u5c40\u9762\n"
                       "3. \u70b9\u3010\u5f00\u59cb\u5bf9\u5c40\u3011\u81ea\u52a8\u8d70\u5b50\n\n"
                       "\u53c2\u6570\u81ea\u52a8\u4fdd\u5b58\u5728 gui_config.json\n"
                       "\u6309 F1 \u770b\u5e2e\u52a9\u4e0e\u5feb\u6377\u952e")
        self._set_running(False)
        self._set_status("\u5c31\u7eea", "idle")
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(120, self._pump)

    # -- config ------------------------------------------------------------
    def _load_cfg(self):
        try:
            with open(CFG_PATH, "r", encoding="utf-8") as fh:
                got = json.load(fh)
            for k, v in got.items():
                if k in DEFAULTS:
                    self.cfg[k] = v
        except Exception:
            pass

    def _save_cfg(self):
        try:
            with open(CFG_PATH, "w", encoding="utf-8") as fh:
                json.dump(self.cfg, fh, ensure_ascii=False, indent=2)
        except Exception as exc:
            self._log("[gui] could not save settings: %s" % exc)

    # -- theme -------------------------------------------------------------
    def _style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        base = (FONT, 10)
        st.configure(".", background=C["bg"], foreground=C["fg"], font=base,
                     fieldbackground=C["field"], bordercolor=C["line"],
                     lightcolor=C["card"], darkcolor=C["card"], focuscolor=C["gold"])
        st.configure("App.TFrame", background=C["bg"])
        st.configure("Card.TFrame", background=C["card"])
        st.configure("Card.TLabelframe", background=C["card"], bordercolor=C["line"],
                     relief="solid", borderwidth=1)
        st.configure("Card.TLabelframe.Label", background=C["card"], foreground=C["gold"],
                     font=(FONT, 10, "bold"))
        st.configure("Card.TLabel", background=C["card"], foreground=C["fg"], font=base)
        st.configure("Hint.TLabel", background=C["card"], foreground=C["dim"], font=(FONT, 9))
        st.configure("Head.TLabel", background=C["bg"], foreground=C["fg"],
                     font=(FONT, 13, "bold"))
        st.configure("Sub.TLabel", background=C["bg"], foreground=C["dim"], font=(FONT, 9))
        st.configure("Dim.TLabel", background=C["bg"], foreground=C["dim"], font=(FONT, 9))
        st.configure("Chip.TLabel", background=C["bg"], foreground=C["green"], font=(FONT, 9))
        st.configure("Run.TLabel", background=C["bg"], foreground=C["gold"], font=(FONT, 9))
        st.configure("Stop.TLabel", background=C["bg"], foreground=C["red"], font=(FONT, 9))
        st.configure("Status.TLabel", background=C["bg"], foreground=C["muted"], font=(FONT, 9))
        st.configure("Card.TCheckbutton", background=C["card"], foreground=C["fg"], font=base)
        st.map("Card.TCheckbutton", background=[("active", C["card"])],
               foreground=[("disabled", C["dim"])])
        st.configure("TEntry", fieldbackground=C["field"], foreground=C["fg"],
                     insertcolor=C["fg"], bordercolor=C["line"], padding=3)
        st.configure("TSpinbox", fieldbackground=C["field"], foreground=C["fg"],
                     insertcolor=C["fg"], arrowcolor=C["muted"], bordercolor=C["line"],
                     padding=2)
        st.configure("TCombobox", fieldbackground=C["field"], background=C["card"],
                     foreground=C["fg"], arrowcolor=C["muted"], bordercolor=C["line"],
                     padding=2)
        st.map("TCombobox", fieldbackground=[("readonly", C["field"])],
               foreground=[("readonly", C["fg"])])
        self.root.option_add("*TCombobox*Listbox.background", C["card"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["gold"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#141008")
        for name, bg, fg in (("Primary.TButton", C["green"], "#06140d"),
                             ("Danger.TButton", C["red"], "#180806"),
                             ("Ghost.TButton", C["card"], C["fg"]),
                             ("Chip.TButton", C["field"], C["muted"]),
                             ("ChipOn.TButton", C["gold"], "#181204")):
            st.configure(name, background=bg, foreground=fg, font=base,
                         bordercolor=C["line"], focusthickness=0, padding=(11, 5))
            st.map(name, background=[("active", lighten(bg)), ("disabled", C["card"])],
                   foreground=[("disabled", C["dim"])])
        st.configure("Vertical.TScrollbar", background=C["card"], troughcolor=C["bg"],
                     bordercolor=C["bg"], arrowcolor=C["muted"])
        st.configure("Treeview", background=C["field"], fieldbackground=C["field"],
                     foreground=C["fg"], bordercolor=C["line"], rowheight=22)
        st.configure("Treeview.Heading", background=C["card"], foreground=C["gold"],
                     font=(FONT, 9, "bold"))

    # -- widgets -----------------------------------------------------------
    def _build(self):
        root = self.root
        root.title("pikafishjj \u63a7\u5236\u53f0 \u00b7 \u76ae\u5361\u9c7c\u8c61\u68cb\u52a9\u624b")
        self.icon = set_window_icon(root)
        root.configure(bg=C["bg"])
        # 760 is the shortest window that still shows the whole board preview:
        # the canvas is 386 px tall and the log card starts 179 px above the
        # bottom edge, so anything under ~740 pushes the last rank out of sight.
        root.minsize(1000, 760)
        geo = self.cfg.get("geometry")
        root.geometry(geo if isinstance(geo, str) and "x" in geo else "1150x880")
        self._style()

        self.v = {}
        for k, val in self.cfg.items():
            self.v[k] = tk.StringVar(value=str(val))
        self.v["win"] = tk.StringVar(value="\u672a\u68c0\u6d4b")
        self.v["status"] = tk.StringVar(value="\u5c31\u7eea")
        self.v["info"] = tk.StringVar(value="")
        self.v["tpl"] = tk.StringVar(value="")
        self.v["caption"] = tk.StringVar(value="\u5c1a\u672a\u8fde\u63a5")
        self.v["autoscroll"] = tk.StringVar(value="True")

        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        root.rowconfigure(3, weight=0)

        self._build_header()
        self._build_target()

        body = ttk.Frame(root, style="App.TFrame")
        body.grid(row=2, column=0, sticky="nsew", padx=10, pady=(2, 2))
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        outer, left = self._scrollable(body, 384)
        outer.grid(row=0, column=0, sticky="nsw")
        self._build_engine(left)
        self._build_game(left)
        self._build_right(body)
        self._build_log()
        self._build_actions()
        self._build_statusbar()

    def _build_header(self):
        head = ttk.Frame(self.root, style="App.TFrame")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))
        head.columnconfigure(1, weight=1)
        ttk.Label(head, text="\u76ae\u5361\u9c7c\u8c61\u68cb\u52a9\u624b", style="Head.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(head, text="pikafishjj", style="Sub.TLabel").grid(
            row=0, column=1, sticky="w", padx=8)
        self.l_status = ttk.Label(head, textvariable=self.v["status"], style="Status.TLabel")
        self.l_status.grid(row=0, column=2, sticky="e")

    def _build_target(self):
        f = ttk.LabelFrame(self.root, text="  \u76ee\u6807\u7a97\u53e3  ", style="Card.TLabelframe")
        f.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 4))
        f.columnconfigure(5, weight=1)
        ttk.Label(f, text="\u6807\u9898\u5305\u542b", style="Card.TLabel").grid(
            row=0, column=0, padx=(10, 6), pady=7)
        e = ttk.Entry(f, textvariable=self.v["title"], width=16)
        e.grid(row=0, column=1, pady=7)
        self._tip(e, "\u6e38\u620f\u7a97\u53e3\u6807\u9898\u91cc\u7684\u5173\u952e\u5b57\uff08\u9ed8\u8ba4 JJ\uff09")
        b1 = ttk.Button(f, text="\u68c0\u6d4b", style="Ghost.TButton", width=8, command=self.on_detect)
        b1.grid(row=0, column=2, padx=6)
        self._tip(b1, "\u627e\u5230\u7a97\u53e3\u5e76\u6253\u5370\u5ba2\u6237\u533a\u5c3a\u5bf8\uff08F5 \u4e4b\u524d\u5efa\u8bae\u5148\u68c0\u6d4b\uff09")
        b2 = ttk.Button(f, text="\u679a\u4e3e\u7a97\u53e3\u2026", style="Ghost.TButton", width=12,
                        command=self.on_enum)
        b2.grid(row=0, column=3, padx=2)
        self._tip(b2, "\u4ece\u5f53\u524d\u6240\u6709\u53ef\u89c1\u7a97\u53e3\u91cc\u6311\u4e00\u4e2a\u4f5c\u4e3a\u76ee\u6807")
        self.l_win = ttk.Label(f, textvariable=self.v["win"], style="Dim.TLabel")
        self.l_win.grid(row=0, column=4, columnspan=2, sticky="w", padx=10, pady=7)

    def _scrollable(self, parent, width):
        outer = ttk.Frame(parent, style="App.TFrame")
        canvas = tk.Canvas(outer, bg=C["bg"], highlightthickness=0, width=width)
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, style="App.TFrame")
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

        def _region(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _width(e):
            canvas.itemconfigure(win, width=e.width)

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120.0)), "units")
            return "break"

        inner.bind("<Configure>", _region)
        canvas.bind("<Configure>", _width)
        outer.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
        outer.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        inner.columnconfigure(0, weight=1)
        self.side_canvas = canvas
        return outer, inner

    def _card(self, parent, title, row):
        f = ttk.LabelFrame(parent, text="  " + title + "  ", style="Card.TLabelframe")
        f.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        f.columnconfigure(1, weight=1)
        f.columnconfigure(3, weight=0)
        return f

    def _tip(self, widget, text):
        self._tips.append(Tip(widget, text))
        return widget

    def _build_engine(self, parent):
        f = self._card(parent, "\u5f15\u64ce", 0)
        ttk.Label(f, text="\u5f15\u64ce exe", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=(10, 6), pady=6)
        e = ttk.Entry(f, textvariable=self.v["exe"])
        e.grid(row=0, column=1, columnspan=2, sticky="ew", pady=6)
        b = ttk.Button(f, text="\u6d4f\u89c8", style="Ghost.TButton", width=6, command=self.on_browse)
        b.grid(row=0, column=3, padx=(6, 10), pady=6)
        self._tip(e, "\u76ae\u5361\u9c7c\u5f15\u64ce\u7684 exe \u8def\u5f84\uff08\u540c\u76ee\u5f55\u9700\u8981 pikafish.nnue\uff09")
        self._spin(f, 1, "\u7ebf\u7a0b\u6570", "threads", 1, 64, 1,
                   "\u5f15\u64ce\u641c\u7d22\u7ebf\u7a0b\u6570\uff0c\u5efa\u8bae = CPU \u7269\u7406\u6838\u5fc3\u6570")
        self._spin(f, 2, "Hash (MB)", "hash_mb", 16, 65536, 128,
                   "\u5f15\u64ce\u7f6e\u6362\u8868\u5927\u5c0f\uff1b\u9996\u6b21\u5206\u914d\u9700\u8981 1\uff5e2 \u79d2")
        self._spin(f, 3, "\u601d\u8003 (ms)", "movetime", 50, 60000, 100,
                   "\u6bcf\u6b65\u601d\u8003\u65f6\u95f4\u3002\u7f51\u7edc\u68cb\u6709\u9650\u65f6\uff0c600\uff5e1500 ms \u5df2\u7ecf\u5f88\u5f3a")
        ttk.Label(f, text="\u9884\u8bbe", style="Card.TLabel").grid(
            row=4, column=0, sticky="w", padx=(10, 6), pady=(2, 8))
        chips = ttk.Frame(f, style="Card.TFrame")
        chips.grid(row=4, column=1, columnspan=3, sticky="w", pady=(2, 8))
        self.b_preset = {}
        for k, name in enumerate(PRESET_ORDER):
            b = ttk.Button(chips, text=PRESET_SHORT[name], style="Chip.TButton", width=6,
                           command=lambda n=name: self.on_preset(n))
            b.grid(row=0, column=k, padx=(0, 6))
            self.b_preset[name] = b
            t = PRESETS[name]
            self._tip(b, "\u7ebf\u7a0b %d / Hash %d MB / \u601d\u8003 %d ms" % (
                t["threads"], t["hash_mb"], t["movetime"]))
        cb = ttk.Checkbutton(f, text="\u542f\u7528\u5f15\u64ce\uff08\u5173\u95ed\u540e\u53ea\u8bfb\u68cb\u76d8\u4e0d\u8ba1\u7b97\uff09",
                             variable=self.v["engine"], onvalue="True", offvalue="False",
                             style="Card.TCheckbutton")
        cb.grid(row=5, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 8))
        self._tip(cb, "\u53ea\u60f3\u9884\u89c8\u8bc6\u522b\u6548\u679c\u65f6\u53ef\u4ee5\u5173\u6389\uff0c\u80fd\u7701\u51e0\u767e MB \u5185\u5b58")

    def _build_game(self, parent):
        f = self._card(parent, "\u5bf9\u5c40", 1)
        ttk.Label(f, text="\u6211\u65b9\u9635\u8425", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=(10, 6), pady=5)
        c1 = ttk.Combobox(f, textvariable=self.v["side"], values=list(SIDES.keys()),
                          state="readonly", width=17)
        c1.grid(row=0, column=1, columnspan=3, sticky="w", pady=5)
        self._tip(c1, "\u9ed8\u8ba4\u81ea\u52a8\u8bc6\u522b\uff1a\u68cb\u76d8\u4e0b\u534a\u90e8\u5206\u90a3\u4e00\u65b9\u5c31\u662f\u6211\u4eec")
        ttk.Label(f, text="\u5bf9\u65b9\u8bf7\u6c42", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", padx=(10, 6), pady=5)
        c3 = ttk.Combobox(f, textvariable=self.v["request"], values=list(REQUESTS.keys()),
                          state="readonly", width=17)
        c3.grid(row=1, column=1, columnspan=3, sticky="w", pady=5)
        self._tip(c3, "\u5bf9\u624b\u6c42\u548c / \u6094\u68cb\u5f39\u7a97\u600e\u4e48\u7b54\uff1a\u9ed8\u8ba4\u70b9\u3010\u62d2\u7edd\u3011")
        ttk.Label(f, text="\u9996\u624b", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", padx=(10, 6), pady=5)
        c2 = ttk.Combobox(f, textvariable=self.v["first"], values=list(FIRSTS.keys()),
                          state="readonly", width=17)
        c2.grid(row=2, column=1, columnspan=3, sticky="w", pady=5)
        self._tip(c2, "\u81ea\u52a8\u5224\u65ad\uff1a\u5f00\u5c40\u4e14\u6211\u4eec\u6267\u7ea2\u5c31\u76f4\u63a5\u8d70\uff0c\u5426\u5219\u5148\u89c2\u671b")
        self._spin(f, 3, "\u6700\u591a\u6b65\u6570", "max_moves", 1, 999, 1,
                   "\u8d70\u591a\u5c11\u6b65\u540e\u81ea\u52a8\u505c\u6b62")
        self._spin(f, 4, "\u7b49\u5bf9\u624b (s)", "opp_timeout", 3, 600, 5,
                   "\u7b49\u5bf9\u624b\u8d70\u5b50\u7684\u8d85\u65f6\uff0c\u8d85\u65f6\u540e\u505c\u6b62")
        self._spin(f, 5, "\u70b9\u51fb\u95f4\u9694 (s)", "click_delay", 0.03, 1.0, 0.01, "%.2f",
                   "\u70b9\u8d77\u70b9\u4e0e\u7ec8\u70b9\u4e4b\u95f4\u7684\u505c\u987f\uff0c\u592a\u5c0f\u4f1a\u4e22\u6389\u7b2c\u4e8c\u4e0b")
        self._spin(f, 6, "\u5f00\u5c40\u89c2\u671b (s)", "probe_wait", 0, 30, 0.5, "%.1f",
                   "\u521a\u8fde\u4e0a\u65f6\u5148\u770b\u770b\u662f\u4e0d\u662f\u8f6e\u5230\u5bf9\u624b\u8d70")
        self._spin(f, 7, "重试次数", "retries", 1, 10, 1, None,
                   "走棋失败（点击没落子 / 引擎挂了 / 读不到棋盘）时自动重新重试几次，"
                   "超过后转为只观察，不会硬点")
        ttk.Label(f, text="棋盘获取", style="Card.TLabel").grid(
            row=8, column=0, sticky="w", padx=(10, 6), pady=5)
        cb_board = ttk.Combobox(f, textvariable=self.v["board"], values=list(BOARDS.keys()),
                                state="readonly", width=17)
        cb_board.grid(row=8, column=1, columnspan=3, sticky="w", pady=5)
        self._tip(cb_board, "视觉识别＝截图＋模板匹配（现在用的）；后端读取＝直接从小程序进程内存里读盘面，"
                            "不受皮肤/动画/遮挡影响（通道还在 tools/jj-mem 里做，未就绪时会自动回退到视觉）")
        ttk.Label(f, text="操作方式", style="Card.TLabel").grid(
            row=9, column=0, sticky="w", padx=(10, 6), pady=5)
        cb_moves = ttk.Combobox(f, textvariable=self.v["moves"], values=list(MOVES.keys()),
                                state="readonly", width=17)
        cb_moves.grid(row=9, column=1, columnspan=3, sticky="w", pady=5)
        self._tip(cb_moves, "物理点击＝移动鼠标点棋盘；后端操作＝不走鼠标，直接把着法交给小程序（通道未就绪时会回退）")
        row = ttk.Frame(f, style="Card.TFrame")
        row.grid(row=10, column=0, columnspan=4, sticky="we", padx=8, pady=(2, 8))
        row.columnconfigure(0, weight=1, uniform="cb")
        row.columnconfigure(1, weight=1, uniform="cb")
        cb1 = ttk.Checkbutton(row, text="\u540e\u53f0\u6a21\u5f0f\uff08\u514d\u6253\u6270\uff09",
                              variable=self.v["background"], onvalue="True", offvalue="False",
                              style="Card.TCheckbutton")
        cb1.grid(row=0, column=0, sticky="w", padx=(2, 6))
        self._tip(cb1, "\u7a97\u53e3\u88ab\u6321\u4f4f\u4e5f\u80fd\u8bfb\u68cb\u76d8\uff1b\u70b9\u51fb\u4e0d\u62a2\u7126\u70b9\u3001\u6307\u9488\u81ea\u52a8\u5f52\u4f4d\uff08\u4e0d\u80fd\u6700\u5c0f\u5316\uff09")
        cb2 = ttk.Checkbutton(row, text="\u6f14\u7ec3\u6a21\u5f0f\uff08\u53ea\u7b97\u4e0d\u70b9\uff09",
                              variable=self.v["dry"], onvalue="True", offvalue="False",
                              style="Card.TCheckbutton")
        cb2.grid(row=0, column=1, sticky="w", padx=(6, 2))
        self._tip(cb2, "\u53ea\u8ba1\u7b97\u5e76\u6253\u5370\u843d\u70b9\uff0c\u4e0d\u70b9\u9f20\u6807\uff0c\u9002\u5408\u5148\u770b\u770b\u6548\u679c")
        cb3 = ttk.Checkbutton(row, text="\u65b0\u5c40\u81ea\u52a8\u5f00\u59cb",
                              variable=self.v["new_game"], onvalue="True", offvalue="False",
                              style="Card.TCheckbutton")
        cb3.grid(row=1, column=0, sticky="w", padx=(2, 6), pady=(4, 0))
        self._tip(cb3, "\u68cb\u76d8\u56de\u5230\u521d\u59cb\u5c40\u9762\u65f6\u81ea\u52a8\u590d\u4f4d\u5e76\u63a5\u7740\u6253\u4e0b\u4e00\u5c40\uff08\u6392\u4f4d / \u9526\u6807\u8d5b\u8fde\u6253\uff09\uff1b\u53d6\u6d88\u5219\u505c\u4e0b")
        cb4 = ttk.Checkbutton(row, text="\u7ed3\u7b97\u81ea\u52a8\u518d\u6765\u4e00\u5c40",
                              variable=self.v["auto_next"], onvalue="True", offvalue="False",
                              style="Card.TCheckbutton")
        cb4.grid(row=1, column=1, sticky="w", padx=(6, 2), pady=(4, 0))
        self._tip(cb4, "\u5bf9\u5c40\u7ed3\u675f\u540e\u81ea\u52a8\u70b9\u51fb\u7ed3\u7b97\u5c4f\u7684\u3010\u518d\u6765\u4e00\u5c40\u3011"
                       "\u5e76\u7ee7\u7eed\u8bc6\u522b\u65b0\u5c40")
        cb5 = ttk.Checkbutton(row, text="后端不可用时回退",
                              variable=self.v["fallback"], onvalue="True", offvalue="False",
                              style="Card.TCheckbutton")
        cb5.grid(row=2, column=0, sticky="w", padx=(2, 6), pady=(4, 0))
        self._tip(cb5, "勾上：后端通道没就绪时自动用视觉/物理继续下（不会卡住）；取消：直接报错，方便确认后端是否真的在用")

    def _build_right(self, body):
        right = ttk.Frame(body, style="App.TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=0)

        pv = ttk.LabelFrame(right, text="  \u68cb\u76d8\u9884\u89c8  ", style="Card.TLabelframe")
        pv.grid(row=0, column=0, sticky="new")
        pv.columnconfigure(1, weight=1)
        W = MARGIN * 2 + 8 * CELL
        H = MARGIN * 2 + 9 * CELL + 40
        self.canvas = tk.Canvas(pv, width=W, height=H, bg=C["card"], highlightthickness=0)
        cap = ttk.Frame(pv, style="Card.TFrame")
        cap.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 0))
        ttk.Label(cap, textvariable=self.v["caption"], style="Card.TLabel",
                  justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(cap, textvariable=self.v["tpl"], style="Hint.TLabel",
                  justify="left").grid(row=0, column=1, sticky="w", padx=(14, 0))
        self.canvas.grid(row=1, column=0, padx=(10, 6), pady=(4, 10))

        info = tk.Text(pv, height=24, width=33, relief="flat", bg=C["field"], fg=C["fg"],
                       font=(MONO, 9), wrap="char", padx=8, pady=6,
                       insertbackground=C["fg"], highlightthickness=1,
                       highlightbackground=C["line"])
        info.grid(row=1, column=1, sticky="nsew", padx=(0, 10), pady=(4, 10))
        info.tag_configure("key", foreground=C["muted"])
        info.tag_configure("val", foreground=C["fg"])
        info.tag_configure("head", foreground=C["gold"])
        info.tag_configure("good", foreground=C["green"])
        info.tag_configure("bad", foreground=C["red"])
        info.tag_configure("dim", foreground=C["dim"])
        info.configure(state="disabled")
        self.info = info
        self._draw_board(None)

    def _build_log(self):
        f = ttk.LabelFrame(self.root, text="  \u65e5\u5fd7  ", style="Card.TLabelframe")
        f.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 4))
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        bar = ttk.Frame(f, style="Card.TFrame")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 2))
        b_clear = ttk.Button(bar, text="\u6e05\u7a7a", style="Ghost.TButton", width=6,
                             command=self.on_clear_log)
        b_clear.grid(row=0, column=0, padx=(0, 6))
        b_slog = ttk.Button(bar, text="\u4fdd\u5b58\u65e5\u5fd7", style="Ghost.TButton", width=9,
                            command=self.on_save_log)
        b_slog.grid(row=0, column=1, padx=(0, 6))
        b_snap = ttk.Button(bar, text="\u4fdd\u5b58\u622a\u56fe", style="Ghost.TButton", width=9,
                            command=self.on_snap)
        b_snap.grid(row=0, column=2, padx=(0, 10))
        cb = ttk.Checkbutton(bar, text="\u81ea\u52a8\u6eda\u52a8", variable=self.v["autoscroll"],
                             onvalue="True", offvalue="False", style="Card.TCheckbutton")
        cb.grid(row=0, column=3)
        self.log = tk.Text(f, height=6, wrap="none", font=(MONO, 9), bg=C["log"],
                           fg="#d3dde8", insertbackground=C["fg"], relief="flat",
                           padx=8, pady=4, highlightthickness=1, highlightbackground=C["line"])
        self.log.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 8))
        sb = ttk.Scrollbar(f, orient="vertical", command=self.log.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=(0, 8), padx=(0, 8))
        self.log.configure(yscrollcommand=sb.set)
        self.log.tag_configure("err", foreground="#ff7b6b")
        self.log.tag_configure("good", foreground="#63d492")
        self.log.tag_configure("warn", foreground="#ffcc66")
        self.log.tag_configure("dim", foreground="#7c8ea1")
        self.log.tag_configure("gui", foreground="#5fa8d8")

    def _build_actions(self):
        bar = ttk.Frame(self.root, style="App.TFrame")
        bar.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 2))
        for i in range(9):
            bar.columnconfigure(i, weight=1)
        self.b_read = ttk.Button(bar, text="\u8bfb\u53d6\u68cb\u76d8  F5", style="Ghost.TButton",
                                 command=self.on_read)
        self.b_start = ttk.Button(bar, text="\u5f00\u59cb\u5bf9\u5c40  F9", style="Primary.TButton",
                                  command=self.on_start)
        self.b_pause = ttk.Button(bar, text="\u6682\u505c  F10", style="Ghost.TButton",
                                  command=self.on_pause, state="disabled")
        self.b_stop = ttk.Button(bar, text="\u505c\u6b62  F11", style="Danger.TButton",
                                 command=self.on_stop, state="disabled")
        self.b_apply = ttk.Button(bar, text="\u5e94\u7528\u53c2\u6570", style="Ghost.TButton",
                                  command=self.on_apply)
        self.b_save = ttk.Button(bar, text="\u4fdd\u5b58\u8bbe\u7f6e", style="Ghost.TButton",
                                 command=self.on_save)
        self.b_self = ttk.Button(bar, text="\u81ea\u68c0", style="Ghost.TButton",
                                 command=self.on_selftest)
        self.b_help = ttk.Button(bar, text="\u5e2e\u52a9  F1", style="Ghost.TButton",
                                 command=self.on_help)
        for i, b in enumerate((self.b_read, self.b_start, self.b_pause, self.b_stop,
                               self.b_apply, self.b_save, self.b_self, self.b_help)):
            b.grid(row=0, column=i, sticky="ew", padx=3, pady=4)
        self._tip(self.b_read, "\u6293\u4e00\u5e27\u3001\u6807\u5b9a\u3001\u8bc6\u522b\uff0c\u53ea\u9884\u89c8\u4e0d\u70b9\u9f20\u6807")
        self._tip(self.b_start, "\u81ea\u52a8\u8bfb\u68cb\u76d8\u3001\u601d\u8003\u3001\u70b9\u5b50")
        self._tip(self.b_pause, "\u6682\u505c\u540e\u4e0d\u518d\u70b9\u51fb\uff0c\u9002\u5408\u4e2d\u9014\u63a5\u7ba1")
        self._tip(self.b_stop, "\u505c\u6b62\u5f53\u524d\u4efb\u52a1\u5e76\u91ca\u653e\u5f15\u64ce")
        self._tip(self.b_apply, "\u4e0d\u91cd\u542f\u4efb\u52a1\uff0c\u7acb\u5373\u751f\u6548\uff08\u601d\u8003\u65f6\u95f4 / \u70b9\u51fb\u95f4\u9694\uff09")
        self._tip(self.b_save, "Ctrl+S")
        self._tip(self.b_self, "\u68c0\u67e5\u6a21\u677f\u5305\u3001\u5f15\u64ce\u3001\u8bc6\u522b\u662f\u5426\u6b63\u5e38")
        self._tip(self.b_help, "F1\uff1a\u5feb\u901f\u4e0a\u624b\u3001\u5feb\u6377\u952e\u4e0e\u53c2\u6570\u8bf4\u660e")

    def _build_statusbar(self):
        bar = ttk.Frame(self.root, style="App.TFrame")
        bar.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 6))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, textvariable=self.v["status"], style="Status.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(bar, style="Sub.TLabel",
                  text="F1 \u5e2e\u52a9 \u00b7 F5 \u8bfb\u76d8 \u00b7 F9 \u5f00\u59cb \u00b7 F10 \u6682\u505c/\u7ee7\u7eed "
                       "\u00b7 F11 \u505c\u6b62 \u00b7 Ctrl+S \u4fdd\u5b58 \u00b7 Ctrl+L \u6e05\u7a7a\u65e5\u5fd7").grid(
            row=0, column=1, sticky="e")

    def _spin(self, parent, r, label, key, lo, hi, step, fmt=None, tip=None):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(
            row=r, column=0, sticky="w", padx=(10, 6), pady=4)
        sp = ttk.Spinbox(parent, textvariable=self.v[key], from_=lo, to=hi,
                         increment=step, width=11)
        if fmt:
            sp.configure(format=fmt)
        sp.grid(row=r, column=1, columnspan=3, sticky="w", pady=4)
        if tip:
            self._tip(sp, tip)
        return sp

    # -- config plumbing ---------------------------------------------------
    def _apply_cfg_to_widgets(self):
        for k, var in self.v.items():
            if k in self.cfg and k not in ("side", "first", "request", "board", "moves"):
                var.set(str(self.cfg[k]))
        self.v["side"].set(_label(SIDES, self.cfg.get("side"), "auto"))
        self.v["first"].set(_label(FIRSTS, self.cfg.get("first"), None))
        self.v["request"].set(_label(REQUESTS, self.cfg.get("request"), "decline"))
        # 这两个下拉框存的是值（vision/physical…），显示的是中文标签：少了这层
        # 还原，配置读回来就是英文原文（2026-10-13 用户报告）。
        self.v["board"].set(_label(BOARDS, self.cfg.get("board"), "vision"))
        self.v["moves"].set(_label(MOVES, self.cfg.get("moves"), "physical"))
        self._mark_preset()

    def _mark_preset(self):
        cur = self.v["preset"].get() if "preset" in self.v else ""
        for name, b in getattr(self, "b_preset", {}).items():
            b.configure(style="ChipOn.TButton" if name == cur else "Chip.TButton")

    def _collect(self):
        cfg = {}
        try:
            # Accept both the label and the stored value, so a config written by
            # an older/newer build always parses.
            for key, table in (("board", BOARDS), ("moves", MOVES)):
                raw = self.v[key].get()
                cfg[key] = table.get(raw, raw if raw in table.values() else
                                     (BOARDS if key == "board" else MOVES)[
                                         list(table)[0]])
            cfg["fallback"] = self.v["fallback"].get() == "True"
            cfg["title"] = self.v["title"].get().strip() or "JJ"
            cfg["exe"] = self.v["exe"].get().strip()
            cfg["threads"] = max(1, min(64, int(float(self.v["threads"].get()))))
            cfg["hash_mb"] = max(16, min(65536, int(float(self.v["hash_mb"].get()))))
            cfg["movetime"] = max(50, min(60000, int(float(self.v["movetime"].get()))))
            cfg["max_moves"] = max(1, min(999, int(float(self.v["max_moves"].get()))))
            cfg["opp_timeout"] = max(3.0, min(600.0, float(self.v["opp_timeout"].get())))
            cfg["probe_wait"] = max(0.0, min(30.0, float(self.v["probe_wait"].get())))
            cfg["click_delay"] = max(0.03, min(1.0, float(self.v["click_delay"].get())))
            cfg["retries"] = max(1, min(10, int(float(self.v["retries"].get()))))
        except ValueError as exc:
            messagebox.showerror("pikafishjj", "\u53c2\u6570\u683c\u5f0f\u9519\u8bef\uff1a%s" % exc)
            return None
        cfg["side"] = SIDES.get(self.v["side"].get(), "auto")
        cfg["first"] = FIRSTS.get(self.v["first"].get(), None)
        cfg["dry"] = self.v["dry"].get() == "True"
        cfg["background"] = self.v["background"].get() == "True"
        cfg["request"] = REQUESTS.get(self.v["request"].get(), "decline")
        cfg["new_game"] = self.v["new_game"].get() == "True"
        cfg["auto_next"] = self.v["auto_next"].get() == "True"
        cfg["engine"] = self.v["engine"].get() == "True"
        cfg["preset"] = self.v["preset"].get()
        cfg["geometry"] = self.cfg.get("geometry", "")
        if not os.path.isfile(cfg["exe"]):
            # a stale path in gui_config.json must not brick a packaged build
            if os.path.isfile(DEFAULT_EXE):
                cfg["exe"] = DEFAULT_EXE
                self.v["exe"].set(DEFAULT_EXE)
            else:
                messagebox.showerror("pikafishjj", "\u627e\u4e0d\u5230\u5f15\u64ce\uff1a\n%s" % cfg["exe"])
                return None
        return cfg

    def on_preset(self, name=None, _evt=None):
        name = name or self.v["preset"].get()
        p = PRESETS.get(name)
        if not p:
            return
        self.v["preset"].set(name)
        for k, val in p.items():
            self.v[k].set(str(val))
        self._mark_preset()
        self._log("[gui] \u9884\u8bbe\u5df2\u5207\u6362\uff1a%s  \u7ebf\u7a0b %d / Hash %d MB / \u601d\u8003 %d ms" % (
            PRESET_SHORT.get(name, name), p["threads"], p["hash_mb"], p["movetime"]))

    def on_browse(self):
        p = filedialog.askopenfilename(title="\u9009\u62e9 Pikafish \u5f15\u64ce",
                                       initialdir=os.path.dirname(self.v["exe"].get()),
                                       filetypes=[("executable", "*.exe"), ("all", "*.*")])
        if p:
            self.v["exe"].set(p)

    def on_save(self):
        cfg = self._collect()
        if cfg:
            cfg["geometry"] = self.root.geometry()
            self.cfg = cfg
            self._save_cfg()
            self._log("[gui] \u8bbe\u7f6e\u5df2\u4fdd\u5b58\u5230 %s" % CFG_PATH)
            self._set_status("\u8bbe\u7f6e\u5df2\u4fdd\u5b58", "ok")

    def on_apply(self):
        p = self.player
        if p is None:
            self._log("[gui] \u5c1a\u672a\u8fde\u63a5\uff0c\u5148\u70b9\u201c\u8bfb\u53d6\u68cb\u76d8\u201d\u6216\u201c\u5f00\u59cb\u5bf9\u5c40\u201d")
            return
        try:
            p.movetime = max(50, min(60000, int(float(self.v["movetime"].get()))))
            p.click_delay = max(0.03, min(1.0, float(self.v["click_delay"].get())))
            p.retries = max(1, min(10, int(float(self.v["retries"].get()))))
            p.auto_next = self.v["auto_next"].get() == "True"
        except ValueError:
            return
        self._log("[gui] \u5df2\u5e94\u7528\uff1a\u601d\u8003 %d ms\uff0c\u70b9\u51fb\u95f4\u9694 %.2f s\uff0c"
                  "\u91cd\u8bd5 %d \u6b21" % (p.movetime, p.click_delay, getattr(p, "retries", 3)))

    # -- window helpers ----------------------------------------------------
    def on_detect(self):
        w32.set_dpi_aware()
        hwnd, title = w32.find_window(self.v["title"].get().strip() or "JJ")
        if not hwnd:
            self.v["win"].set("\u672a\u627e\u5230")
            self.l_win.configure(style="Stop.TLabel")
            self._log("[gui] \u672a\u627e\u5230\u6807\u9898\u542b %r \u7684\u7a97\u53e3" % self.v["title"].get())
            return
        x, y, w, h = w32.client_rect_screen(hwnd)
        self.v["win"].set("%dx%d @ (%d,%d) hwnd=%d" % (w, h, x, y, hwnd))
        self.l_win.configure(style="Chip.TLabel")
        self._log("[gui] \u7a97\u53e3 %r \u5ba2\u6237\u533a %dx%d @ (%d,%d)" % (title, w, h, x, y))
        if w < 560:
            self._log("[gui] \u63d0\u9192\uff1a\u7a97\u53e3\u53ea\u6709 %d px \u5bbd\uff0c\u68cb\u76d8\u53f3\u4fa7\u4f1a\u88ab\u88c1\u6389\uff0c"
                             "\u8bf7\u62c9\u5bbd\u5230\u81f3\u5c11 560 px" % w)

    def on_enum(self):
        w32.set_dpi_aware()
        wins = w32.list_windows()
        key = self.v["title"].get().strip()
        wins.sort(key=lambda t: (0 if key and key in t[1] else 1, t[1]))
        top = tk.Toplevel(self.root)
        top.configure(bg=C["bg"])
        top.title("\u9009\u62e9\u76ee\u6807\u7a97\u53e3")
        top.geometry("620x460")
        top.transient(self.root)
        ttk.Label(top, text="\u53cc\u51fb\u4e00\u884c\u9009\u7528\uff08\u5217\uff1a\u6807\u9898 / \u7c7b\u540d / PID\uff09",
                  style="Sub.TLabel").pack(anchor="w", padx=10, pady=8)
        wrap = ttk.Frame(top, style="App.TFrame")
        wrap.pack(fill="both", expand=True, padx=10)
        tv = ttk.Treeview(wrap, columns=("t", "c", "p"), show="headings")
        for c, w, txt in (("t", 330, "\u6807\u9898"), ("c", 180, "\u7c7b\u540d"), ("p", 80, "PID")):
            tv.heading(c, text=txt)
            tv.column(c, width=w)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for hwnd, title, cls, pid in wins:
            tv.insert("", "end", values=(title, cls, pid), tags=(str(hwnd),))

        def use(_e=None):
            sel = tv.selection()
            if not sel:
                return
            hwnd = int(tv.item(sel[0], "tags")[0])
            title = tv.item(sel[0], "values")[0]
            self.v["title"].set(title)
            x, y, w, h = w32.client_rect_screen(hwnd)
            self.v["win"].set("%dx%d @ (%d,%d) hwnd=%d" % (w, h, x, y, hwnd))
            self.l_win.configure(style="Chip.TLabel")
            self._log("[gui] \u9009\u4e2d\u7a97\u53e3 %r (%dx%d)" % (title, w, h))
            top.destroy()

        tv.bind("<Double-1>", use)
        ttk.Button(top, text="\u4f7f\u7528\u9009\u4e2d", style="Primary.TButton",
                   command=use).pack(pady=10)

    # -- help --------------------------------------------------------------
    def on_help(self):
        top = tk.Toplevel(self.root)
        top.configure(bg=C["bg"])
        top.title("\u5e2e\u52a9 \u00b7 pikafishjj")
        top.geometry("660x560")
        top.transient(self.root)
        txt = tk.Text(top, wrap="word", bg=C["field"], fg=C["fg"], relief="flat",
                      font=(FONT, 10), padx=14, pady=12, highlightthickness=1,
                      highlightbackground=C["line"])
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.tag_configure("h", foreground=C["gold"], font=(FONT, 11, "bold"),
                          spacing1=8, spacing3=4)
        txt.tag_configure("k", foreground=C["green"], font=(MONO, 10, "bold"))

        def put(s, tag=None):
            txt.insert("end", s + "\n", tag or "")

        put("\u5feb\u901f\u4e0a\u624b", "h")
        put("1. \u5728\u6e38\u620f\u91cc\u8fdb\u5165\u68cb\u76d8\u754c\u9762\uff08\u4eba\u673a\u6216\u5bf9\u6218\u90fd\u884c\uff09")
        put("2. \u70b9\u3010\u68c0\u6d4b\u3011\u786e\u8ba4\u627e\u5230\u7a97\u53e3\uff08\u5ba2\u6237\u533a\u5bbd\u5ea6\u5efa\u8bae \u2265 560 px\uff09")
        put("3. \u70b9\u3010\u5f00\u59cb\u5bf9\u5c40\u3011\uff0c\u5269\u4e0b\u7684\u4ea4\u7ed9\u7a0b\u5e8f\uff1b\u60f3\u5148\u770b\u770b\u5c31\u5148\u70b9\u3010\u8bfb\u53d6\u68cb\u76d8\u3011")
        put("\u5feb\u6377\u952e", "h")
        for k, v in (("F1", "\u672c\u5e2e\u52a9"), ("F5", "\u8bfb\u53d6\u68cb\u76d8"),
                     ("F9", "\u5f00\u59cb\u5bf9\u5c40"), ("F10", "\u6682\u505c / \u7ee7\u7eed"),
                     ("F11", "\u505c\u6b62"), ("Ctrl+S", "\u4fdd\u5b58\u8bbe\u7f6e"),
                     ("Ctrl+L", "\u6e05\u7a7a\u65e5\u5fd7")):
            txt.insert("end", "  %-7s %s\n" % (k, v))
        put("\u5173\u952e\u53c2\u6570", "h")
        for k, v in (("\u6211\u65b9\u9635\u8425", "\u9ed8\u8ba4\u81ea\u52a8\uff1a\u68cb\u76d8\u4e0b\u534a\u90e8\u5206\u90a3\u4e00\u65b9\u5c31\u662f\u6211\u4eec"),
                     ("\u5bf9\u65b9\u8bf7\u6c42", "\u5bf9\u624b\u6c42\u548c / \u6094\u68cb\u5f39\u7a97\uff0c\u9ed8\u8ba4\u70b9\u3010\u62d2\u7edd\u3011"),
                     ("\u540e\u53f0\u6a21\u5f0f", "\u7a97\u53e3\u88ab\u6321\u4f4f\u4e5f\u80fd\u8bfb\u68cb\u76d8\uff1b\u4e0d\u80fd\u6700\u5c0f\u5316"),
                     ("\u601d\u8003 (ms)", "\u6bcf\u6b65\u601d\u8003\u65f6\u95f4\uff1b600\uff5e1500 ms \u5df2\u7ecf\u5f88\u5f3a"),
                     ("\u70b9\u51fb\u95f4\u9694", "\u70b9\u8d77\u70b9\u4e0e\u7ec8\u70b9\u4e4b\u95f4\u7684\u505c\u987f\uff0c0.15\uff5e0.25 s \u6bd4\u8f83\u7a33"),
                     ("\u9884\u8bbe", "\u5feb\u901f / \u5747\u8861 / \u5f3a\u529b \u4e00\u952e\u586b\u597d\u4e0a\u9762\u4e09\u4e2a\u503c")):
            txt.insert("end", "  ")
            txt.insert("end", k, "k")
            txt.insert("end", "  " + v + "\n")
        put("\u5e38\u89c1\u95ee\u9898", "h")
        for q, a in (("\u70b9\u5f00\u59cb\u6ca1\u53cd\u5e94", "\u5148\u770b\u65e5\u5fd7\uff1b\u82e5\u63d0\u793a\u6807\u5b9a\u5931\u8d25\uff0c\u8bf4\u660e\u5c4f\u5e55\u4e0a\u6ca1\u6709\u68cb\u76d8\uff08\u5927\u5385 / \u7ed3\u7b97\u9875\uff09"),
                    ("\u8bc6\u522b\u6570\u636e\u4e0d\u52a8", "\u6e38\u620f\u7a97\u53e3\u88ab\u522b\u7684\u7a0b\u5e8f\u5b8c\u5168\u76d6\u4f4f\u65f6\u8bf7\u52fe\u9009\u540e\u53f0\u6a21\u5f0f"),
                    ("\u5361\u5728\u7b49\u5bf9\u624b", "\u628a\u3010\u7b49\u5bf9\u624b\u3011\u8c03\u5927\uff0c\u6216\u628a\u3010\u9996\u624b\u3011\u6539\u6210\u81ea\u52a8\u5224\u65ad"),
                    ("\u60f3\u770b\u770b\u6548\u679c", "\u52fe\u9009\u3010\u6f14\u7ec3\u6a21\u5f0f\u3011\uff1a\u53ea\u8ba1\u7b97\u5e76\u6253\u5370\u843d\u70b9\uff0c\u4e0d\u70b9\u9f20\u6807")):
            txt.insert("end", "  \u00b7 ")
            txt.insert("end", q, "k")
            txt.insert("end", "\uff1a" + a + "\n")
        txt.configure(state="disabled")
        ttk.Button(top, text="\u77e5\u9053\u4e86", style="Primary.TButton",
                   command=top.destroy).pack(pady=(0, 10))

    # -- keyboard ----------------------------------------------------------
    def _bind_keys(self):
        b = self.root.bind
        b("<F1>", lambda e: self.on_help())
        b("<F5>", lambda e: self.on_read())
        b("<F9>", lambda e: self.on_start())
        b("<F10>", lambda e: self.on_pause())
        b("<F11>", lambda e: self.on_stop())
        b("<Control-s>", lambda e: self.on_save())
        b("<Control-l>", lambda e: self.on_clear_log())

    # -- actions -----------------------------------------------------------
    def on_read(self):
        cfg = self._collect()
        if not cfg:
            return
        self.cfg = cfg
        self._save_cfg()
        self.mode = "read"
        self._launch(cfg)

    def on_start(self):
        cfg = self._collect()
        if not cfg:
            return
        self.cfg = cfg
        self._save_cfg()
        self.mode = "play"
        self._launch(cfg)

    def on_selftest(self):
        cfg = self._collect()
        if not cfg:
            return
        self.cfg = cfg
        self._save_cfg()
        self.mode = "selftest"
        self._launch(cfg)

    def _launch(self, cfg):
        if self.worker is not None and self.worker.is_alive():
            messagebox.showinfo("pikafishjj", "\u5df2\u6709\u4efb\u52a1\u5728\u8fd0\u884c")
            return
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.cfg_run = dict(cfg)
        self.last_from = self.last_to = None
        self.worker = threading.Thread(target=self._worker, name="pikafishjj", daemon=True)
        self.worker.start()
        self._set_running(True)
        self._set_status("\u542f\u52a8\u4e2d\u2026", "run")

    def _worker(self):
        cfg = self.cfg_run
        try:
            p = AutoPlayer(exe=cfg["exe"], movetime=cfg["movetime"], threads=cfg["threads"],
                           hash_mb=cfg["hash_mb"], title=cfg["title"], our_side=cfg["side"],
                           click_delay=cfg["click_delay"], verbose=True, dry=cfg["dry"],
                           background=cfg.get("background", False),
                           request=cfg.get("request", "decline"),
                           new_game=cfg.get("new_game", True),
                           auto_next=cfg.get("auto_next", True),
                           board=cfg.get("board", "vision"),
                           moves=cfg.get("moves", "physical"),
                           fallback=cfg.get("fallback", True),
                           log_sink=lambda m: self.q.put(("log", m)),
                           stop_event=self.stop_event, pause_event=self.pause_event)
            self.player = p
            if self.mode == "selftest":
                self._selftest(p)
                return
            tries = max(1, int(cfg.get("retries", 3)))
            for attempt in range(1, tries + 1):
                if self.stop_event is not None and self.stop_event.is_set():
                    break
                try:
                    self.q.put(("status", "\u6807\u5b9a\u68cb\u76d8\u4e2d\u2026"))
                    # wait=True: a screen that shows no board is not an error, the
                    # run loop watches for one instead of dying (field log
                    # 2026-10-14: six unreadable frames, an exception out of this
                    # worker, and a dead console at the end of a quiet endgame).
                    p.attach(wait=True)
                    _x, _y, cw, ch = w32.client_rect_screen(p.hwnd)
                    if cw < 560:
                        self.q.put(("log", "[gui] \u7a97\u53e3\u592a\u7a84\uff08%d px \u5bbd\uff09\uff1a\u68cb\u76d8\u53f3\u4fa7\u4f1a\u88ab\u88c1\u6389\uff0c"
                                           "\u8bf7\u628a\u6e38\u620f\u7a97\u53e3\u62c9\u5bbd\u5230\u81f3\u5c11 560 px" % cw))
                    if cfg.get("background"):
                        self.q.put(("log", "[gui] \u540e\u53f0\u6a21\u5f0f\uff1a\u7a97\u53e3\u88ab\u6321\u4f4f\u4e5f\u80fd\u8bfb\u68cb\u76d8\uff1b"
                                           "\u70b9\u51fb\u65f6\u6307\u9488\u4f1a\u88ab\u77ed\u6682\u501f\u7528\u5e76\u7acb\u523b\u590d\u4f4d"))
                    self.q.put(("status", "\u5df2\u8fde\u63a5\uff1a%s" % (
                        "\u7ea2\u65b9\u5728\u4e0b" if not p.flip else "\u7ea2\u65b9\u5728\u4e0a")))
                    self.q.put(("tpl", "\u6a21\u677f\u5305\uff1a%d \u7c7b" % len(p.tpl)))
                    if cfg.get("background"):
                        self.q.put(("status", "\u5df2\u8fde\u63a5\uff1a%s\uff08\u540e\u53f0\u6a21\u5f0f\uff09" % (
                            "\u7ea2\u65b9\u5728\u4e0b" if not p.flip else "\u7ea2\u65b9\u5728\u4e0a")))
                    if cfg["engine"]:
                        p.start_engine()
                    self.q.put(("redraw", None))
                    if self.mode == "read":
                        g, _a = p.read()
                        if g is None:
                            self.q.put(("log", "[gui] \u8bfb\u53d6\u5931\u8d25\uff1a\u68cb\u76d8\u672a\u7a33\u5b9a\u6216\u8bc6\u522b\u4e0d\u5408\u7406"))
                        else:
                            self.q.put(("redraw", None))
                            self.q.put(("log", "[gui] \u8bfb\u53d6\u5b8c\u6210"))
                        return
                    p.run(max_moves=cfg["max_moves"], first=cfg["first"],
                          opp_timeout=cfg["opp_timeout"], probe_wait=cfg["probe_wait"])
                    self.q.put(("log", "[gui] \u5bf9\u5c40\u7ed3\u675f"))
                    break
                except Exception as exc:
                    # Anything at all (window closed, calibration lost, engine
                    # dead) is recovered here: the link is rebuilt and the run is
                    # started over instead of leaving the console sitting idle.
                    self.q.put(("log", "[gui] attempt %d/%d failed: %s: %s" % (
                        attempt, tries, type(exc).__name__, exc)))
                    for line in traceback.format_exc().strip().splitlines():
                        self.q.put(("log", "    " + line))
                    if attempt >= tries:
                        # The retries are spent, but the game window is still
                        # open: that is not the end of the session.  Fall back to
                        # the watch loop, which keeps looking for a board (and
                        # re-attaches when the window comes back) until 停止 is
                        # pressed.  Giving up here is what made the program die on
                        # a customer's machine: three failed attempts, a wall of
                        # traceback, and a console that had to be restarted by
                        # hand - while the game was still on screen.
                        self.q.put(("log", "[gui] the run could not be started yet - "
                                           "watching the game window for a board "
                                           "(press \u505c\u6b62 to quit)"))
                        g, _a = p.wait_for_board(timeout=0.0)
                        if g is not None:
                            self.q.put(("log", "[gui] the board is readable again - "
                                               "starting the run"))
                            try:
                                p.run(max_moves=cfg["max_moves"], first=cfg["first"],
                                      opp_timeout=cfg["opp_timeout"],
                                      probe_wait=cfg["probe_wait"])
                                self.q.put(("log", "[gui] \u5bf9\u5c40\u7ed3\u675f"))
                            except Exception as exc2:
                                self.q.put(("log", "[gui] the run ended with %s: %s"
                                                   % (type(exc2).__name__, exc2)))
                        else:
                            self.q.put(("log", "[gui] stopped - press "
                                               "\u5f00\u59cb\u5bf9\u5c40 to try again"))
                        break
                    self.q.put(("log", "[gui] reconnecting and trying again in 2s ..."))
                    time.sleep(2.0)
                    try:
                        p.close()
                    except Exception:
                        pass
                    p.reset_link(keep_engine=False)
        except Exception as exc:
            self.q.put(("log", "[gui] ERROR %s: %s" % (type(exc).__name__, exc)))
            for line in traceback.format_exc().strip().splitlines():
                self.q.put(("log", "    " + line))
        finally:
            p = self.player
            if p is not None:
                try:
                    p.close()
                except Exception:
                    pass
            self.q.put(("done", None))

    def _selftest(self, p):
        """Check templates + engine + recognition; needs no running game."""
        put = self.q.put
        ok = True
        put(("status", "\u81ea\u68c0\u4e2d\u2026"))
        put(("log", "[\u81ea\u68c0] ===== pikafishjj \u81ea\u68c0 ====="))
        tpl, half = V.load_templates()
        if tpl:
            put(("log", "[\u81ea\u68c0] 1/3 \u6a21\u677f\u5305 OK  %s" % V.find_templates()))
            put(("log", "        %d \u7c7b / %d \u53d8\u4f53 / patch half %d" % (
                len(tpl), sum(len(v) for v in tpl.values()), half)))
            put(("tpl", "\u6a21\u677f\u5305\uff1a%d \u7c7b" % len(tpl)))
        else:
            ok = False
            put(("log", "[\u81ea\u68c0] 1/3 \u6a21\u677f\u5305\u7f3a\u5931  %s" % V.find_templates()))
        put(("log", "[\u81ea\u68c0] 2/3 \u5f15\u64ce %s" % p.exe))
        try:
            p.start_engine()
            mt = max(200, min(2000, p.movetime))
            best, _ponder, info = p.engine.bestmove(B.OPENING_FEN, movetime=mt)
            d = last_info(info)
            put(("log", "[\u81ea\u68c0]        \u5f15\u64ce OK  %s  bestmove %s depth=%s score=%s" % (
                p.engine.name, best, d.get("depth"), d.get("score"))))
        except Exception as exc:
            ok = False
            put(("log", "[\u81ea\u68c0]        \u5f15\u64ce\u5931\u8d25\uff1a%s: %s" % (type(exc).__name__, exc)))
        put(("log", "[\u81ea\u68c0] 3/3 \u8bc6\u522b\uff08\u7a97\u53e3\u672a\u6253\u5f00\u65f6\u81ea\u52a8\u8df3\u8fc7\uff09"))
        try:
            p.attach()
            n = sum(1 for row in p.grid for c in row if c != ".")
            put(("log", "[\u81ea\u68c0]        \u68cb\u76d8 OK  %d \u5b50  \u6211\u65b9=%s" % (
                n, "\u7ea2\u65b9" if p.our_side == "w" else "\u9ed1\u65b9")))
            put(("log", "        FEN " + B.grid_to_fen(p.grid, p.our_side).split(" ")[0]))
            put(("redraw", None))
        except Exception as exc:
            put(("log", "[\u81ea\u68c0]        \u8df3\u8fc7\uff1a%s" % exc))
        put(("log", "[\u81ea\u68c0] ===== %s =====" % ("\u901a\u8fc7" if ok else "\u5b58\u5728\u95ee\u9898\uff08\u89c1\u4e0a\uff09")))
        put(("status", "\u81ea\u68c0\u5b8c\u6210"))

    def on_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.b_pause.configure(text="\u6682\u505c  F10")
            self._log("[gui] \u7ee7\u7eed")
            self._set_status("\u5df2\u7ee7\u7eed", "run")
        else:
            self.pause_event.set()
            self.b_pause.configure(text="\u7ee7\u7eed  F10")
            self._log("[gui] \u5df2\u6682\u505c\uff08\u4e0d\u4f1a\u518d\u70b9\u51fb\uff09")
            self._set_status("\u5df2\u6682\u505c", "idle")

    def on_stop(self):
        self.stop_event.set()
        self.pause_event.clear()
        self.b_pause.configure(text="\u6682\u505c  F10")
        self._log("[gui] \u505c\u6b62\u8bf7\u6c42\u5df2\u53d1\u51fa")
        self._set_status("\u6b63\u5728\u505c\u6b62\u2026", "err")

    def on_close(self):
        self.stop_event.set()
        self.pause_event.clear()
        try:
            cfg = self._collect()
            if cfg:
                cfg["geometry"] = self.root.geometry()
                self.cfg = cfg
                self._save_cfg()
        except Exception:
            pass
        self.root.destroy()

    # -- log / preview -----------------------------------------------------
    def _log(self, msg):
        self.q.put(("log", msg))

    def _append(self, msg):
        tag = "gui"
        if "[gui] ERROR" in msg or "Traceback" in msg or "Error" in msg:
            tag = "err"
        elif msg.startswith("[play]") or msg.startswith("[best]") or msg.startswith("[engine]"):
            tag = "good"
        elif msg.startswith("[wait]") or "implausible" in msg or "WARNING" in msg:
            tag = "warn"
        elif msg.startswith("[attach]") or msg.startswith("    "):
            tag = "dim"
        if msg.startswith("[play] confirmed"):
            sq = re.findall(r"\b([a-i][0-9])\b", msg)
            if len(sq) >= 2:
                self.last_from = B.parse_uci(sq[0])
                self.last_to = B.parse_uci(sq[1])
        self.log.insert("end", msg + "\n", tag)
        if int(self.log.index("end-1c").split(".")[0]) > 1200:
            self.log.delete("1.0", "200.0")
        if self.v["autoscroll"].get() != "False":
            self.log.see("end")

    def _draw_board(self, grid, from_cell=None, to_cell=None):
        c = self.canvas
        c.delete("all")
        W = MARGIN * 2 + 8 * CELL
        H = MARGIN * 2 + 9 * CELL + 40
        x0, y0 = MARGIN, MARGIN + 6
        bw, bh = 8 * CELL, 9 * CELL
        r_out = int(CELL * 0.44)
        r_in = int(CELL * 0.33)
        c.create_rectangle(0, 0, W, H, fill=C["card"], outline="")
        c.create_rectangle(x0 - 16, y0 - 14, x0 + bw + 16, y0 + bh + 10, fill="#c8a877", outline="")
        c.create_rectangle(x0 - 13, y0 - 11, x0 + bw + 13, y0 + bh + 11,
                           fill="#e9cd97", outline="#a9784a", width=2)
        line = "#8a6134"
        for i in range(9):
            x = x0 + i * CELL
            c.create_line(x, y0, x, y0 + bh, fill=line)
        for j in range(10):
            y = y0 + j * CELL
            c.create_line(x0, y, x0 + bw, y, fill=line)
        for i in range(1, 8):
            x = x0 + i * CELL
            c.create_line(x, y0 + 4 * CELL, x, y0 + 5 * CELL, fill="#e9cd97")
        for (a, b, d, e) in ((3, 0, 5, 2), (5, 0, 3, 2), (3, 7, 5, 9), (5, 7, 3, 9)):
            c.create_line(x0 + a * CELL, y0 + b * CELL, x0 + d * CELL, y0 + e * CELL, fill=line)
        for i, cn in enumerate(FILE_CN):
            c.create_text(x0 + i * CELL, y0 + bh + 21, text=cn, fill="#a8895c", font=(FONT, 9))
        if not grid:
            c.create_text(x0 + bw / 2.0, y0 + 4.1 * CELL, text="尚未连接",
                          fill="#9c7b4c", font=(FONT, 12))
            c.create_text(x0 + bw / 2.0, y0 + 5.0 * CELL,
                          text="点【读取棋盘】预览当前局面",
                          fill="#a8895c", font=(FONT, 9))
            return
        c.create_text(x0 + 1.7 * CELL, y0 + 4.5 * CELL, text="楚河",
                      fill="#a5814c", font=(FONT, 11))
        c.create_text(x0 + 6.3 * CELL, y0 + 4.5 * CELL, text="漢界",
                      fill="#a5814c", font=(FONT, 11))
        for j in range(10):
            for i in range(9):
                ch = grid[j][i]
                cx = x0 + i * CELL
                cy = y0 + j * CELL
                # the rings mark the ply even when the target square is empty
                if from_cell == (i, j):
                    c.create_oval(cx - r_out - 3, cy - r_out - 3, cx + r_out + 3, cy + r_out + 3,
                                  outline="#4fd07a", width=3)
                if to_cell == (i, j):
                    c.create_oval(cx - r_out - 3, cy - r_out - 3, cx + r_out + 3, cy + r_out + 3,
                                  outline="#ff6b5a", width=3)
                if ch == ".":
                    continue
                c.create_oval(cx - r_out, cy - r_out, cx + r_out, cy + r_out, fill="#f7e7bf",
                              outline="#b98f52", width=2)
                c.create_oval(cx - r_in, cy - r_in, cx + r_in, cy + r_in, outline="#dcb877")
                red = ch.isupper()
                c.create_text(cx, cy + 1, text=GLYPH.get(ch, ch),
                              fill=("#b01d1d" if red else "#22201c"),
                              font=(FONT, 14, "bold"))
    def _set_info(self, text):
        """Show plain text, or a list of (tag, chunk) pieces for a coloured panel."""
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        if isinstance(text, (list, tuple)):
            for tag, chunk in text:
                self.info.insert("end", chunk, tag or "")
        else:
            self.info.insert("1.0", text)
        self.info.configure(state="disabled")

    def _set_status(self, text, kind="idle"):
        self.v["status"].set(text)
        style = {"idle": "Status.TLabel", "run": "Run.TLabel",
                 "err": "Stop.TLabel", "ok": "Chip.TLabel"}.get(kind, "Status.TLabel")
        try:
            self.l_status.configure(style=style)
        except Exception:
            pass

    def _set_running(self, on):
        state = "disabled" if on else "normal"
        self.b_start.configure(state=state)
        self.b_read.configure(state=state)
        self.b_self.configure(state=state)
        self.b_stop.configure(state="normal" if on else "disabled")
        self.b_pause.configure(state="normal" if on else "disabled")

    def on_clear_log(self):
        self.log.delete("1.0", "end")
        self._log("[gui] \u65e5\u5fd7\u5df2\u6e05\u7a7a")

    # -- main-thread pump --------------------------------------------------
    def _view(self, p, grid, from_cell, to_cell):
        """Draw the board with our own army at the bottom, like the game window.

        The internal grid always keeps red at the bottom; when the auto side
        detection says we play black the preview is rotated with it.
        """
        if grid is None or getattr(p, "our_side", "w") != "b":
            return grid, from_cell, to_cell
        v = [list(reversed(row)) for row in reversed(grid)]

        def m(c):
            return None if c is None else (8 - c[0], 9 - c[1])
        return v, m(from_cell), m(to_cell)

    def _pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append(payload)
                elif kind == "status":
                    self._set_status(payload, "run" if self.worker else "idle")
                elif kind == "tpl":
                    self.v["tpl"].set(payload)
                elif kind == "done":
                    self._set_running(False)
                    self._set_status("\u5df2\u505c\u6b62", "idle")
                    self._drain_jobs()
        except queue.Empty:
            pass
        p = self.player
        if p is not None:
            key = None
            if p.grid is not None:
                key = "".join("".join(row) for row in p.grid) + "|" + str(self.last_to)
            if key != self._last_draw:
                self._last_draw = key
                g, f, t = self._view(p, p.grid, self.last_from, self.last_to)
                self._draw_board(g, f, t)
            self._refresh_info(p)
            self._tick(p)
        self.root.after(150, self._pump)

    def _tick(self, p):
        """Caption under the board: who we are, whose turn it is, thinking dot."""
        st = p.stats
        who = "\u7ea2\u65b9" if p.our_side == "w" else "\u9ed1\u65b9"
        pos = "\u4e0b" if p.our_side == "w" else "\u4e0a"
        turn = st.get("turn") or ""
        phase = str(st.get("phase", "-"))
        self._blink = (self._blink + 1) % 2
        dot = "\u25cf" if (phase == "thinking" and self._blink) else "\u25cb"
        parts = ["\u6211\u65b9  %s\uff08%s\uff09" % (who, pos)]
        if turn:
            parts.append(turn)
        if phase == "thinking":
            parts.append("%s \u601d\u8003\u4e2d" % dot)
        else:
            parts.append("\u9636\u6bb5 %s" % phase)
        self.v["caption"].set("\n".join(parts))

    def _drain_jobs(self):
        self.worker = None

    def _refresh_info(self, p):
        st = p.stats
        fen = B.grid_to_fen(p.grid, p.our_side) if p.grid else ""
        rec = max(1, st["recognitions"])
        frames = max(1, int(st.get("frames") or st["reads"]))
        place = fen.split(" ")[0] if fen else "-"
        who = "\u7ea2\u65b9 (\u4e0b)" if p.our_side == "w" else "\u9ed1\u65b9 (\u4e0a)"
        if str(self.cfg.get("side")) == "auto":
            who += "  \u81ea\u52a8"
        out = []

        def row(k, v, tag="val"):
            out.append(("key", "%-6s" % k))
            out.append((tag, str(v) + "\n"))

        row("\u5c40\u9762", place)
        row("\u6211\u65b9", who)
        row("\u9636\u6bb5", st.get("phase", "-"))
        out.append(("dim", "\n"))
        row("\u8bfb\u5e27", "%d     \u8bc6\u522b %d     \u589e\u91cf %d" % (
            st["reads"], st["recognitions"], st.get("incr", 0)))
        row("\u8017\u65f6", "\u8bc6\u522b %.1f ms/\u5e27   \u6293\u5c4f %.1f ms/\u5e27" % (
            st["recog_ms"] / rec, st["grab_ms"] / frames))
        row("\u6211\u65b9\u6b65", "%d     \u63d0\u793a\u547d\u4e2d %d" % (st["moves"], st["hint_hits"]))
        row("\u5bf9\u5c40", "\u7b2c %d \u5c40     \u65b0\u5c40\u81ea\u52a8 %s" % (
            int(st.get("games", 1)),
            "\u5f00" if getattr(p, "new_game", True) else "\u5173"))
        row("\u5bf9\u65b9\u8bf7\u6c42", "%s   \u5df2\u5904\u7406 %d \u6b21" % (
            _label(REQUESTS, getattr(p, "request", "decline"), "decline"),
            int(st.get("dialogs", 0))))
        row("\u91cd\u8bd5", "\u843d\u5b50\u91cd\u8bd5 %d   \u6062\u590d %d   \u5931\u8d25 %d   "
            "\u5361\u4f4f %d" % (
                int(st.get("attempts", 0)), int(st.get("recover", 0)),
                int(st.get("fails", 0)), int(st.get("stalls", 0))))
        row("\u7528\u65f6", "\u6211\u65b9\u7d2f\u8ba1 %.0fs   \u6700\u6162\u4e00\u6b65 %.1fs   "
            "\u6162\u6b65 %d" % (
                float(st.get("turn_s", 0.0)), float(st.get("turn_max", 0.0)),
                int(st.get("slow", 0))))
        row("感知/操作", "%s / %s" % (
            "\u540e\u7aef" if getattr(p, "board_mode", "vision") == "backend" else "\u89c6\u89c9",
            "\u540e\u7aef" if getattr(p, "moves_mode", "physical") == "backend" else "\u7269\u7406"))
        row("\u518d\u6765\u4e00\u5c40", "%s   \u5df2\u70b9 %d \u6b21" % (
            "\u81ea\u52a8" if getattr(p, "auto_next", True) else "\u5173",
            int(st.get("rematch", 0))))
        if getattr(p, "background", False):
            row("\u540e\u53f0\u6a21\u5f0f",
                "\u662f   \u56de\u9000 %d \u5e27   \u4e0d\u62a2\u7126\u70b9 %s   %s" % (
                    int(st.get("bg_fallback", 0)),
                    "\u5f00" if getattr(p, "quiet", False) else "\u5173",
                    "\u9759\u9ed8\u70b9\u51fb" if getattr(p, "bg_ok", True)
                    else "\u6682\u7528\u524d\u53f0"))
        out.append(("dim", "\n"))
        if st.get("best"):
            score = st.get("score")
            tag = "val"
            try:
                tag = "good" if float(score) >= 0 else "bad"
            except (TypeError, ValueError):
                tag = "val"
            row("\u6700\u4f18", "%s   depth %s" % (st["best"], st.get("depth")))
            out.append(("key", "%-6s" % "\u8bc4\u5206"))
            out.append((tag, "%-8s" % score))
            out.append(("key", "nodes %s" % st.get("nodes")))
            nps = st.get("nps")
            out.append(("dim", "   %.2fM nps\n" % (nps / 1e6) if nps else "\n"))
        else:
            out.append(("dim", "\u5f15\u64ce\uff1a\u5f85\u547d\n"))
        self._set_info(out)

    def dump_layout(self, path):
        """Debug hook: write widget rectangles and field values for UI tests."""
        out = {"client": [self.root.winfo_rootx(), self.root.winfo_rooty(),
                          self.root.winfo_width(), self.root.winfo_height()],
               "vars": dict((k, v.get()) for k, v in self.v.items())}
        for name in sorted(dir(self)):
            if not name.startswith("b_"):
                continue
            wdg = getattr(self, name, None)
            if isinstance(wdg, dict):
                for sub, w in wdg.items():
                    try:
                        out["%s[%s]" % (name, sub)] = [w.winfo_rootx(), w.winfo_rooty(),
                                                       w.winfo_width(), w.winfo_height()]
                    except Exception:
                        pass
                continue
            try:
                out[name] = [wdg.winfo_rootx(), wdg.winfo_rooty(),
                             wdg.winfo_width(), wdg.winfo_height()]
            except Exception:
                pass
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(out, fh, ensure_ascii=False, indent=1)
        except Exception as exc:
            self._log("[gui] layout dump failed: %s" % exc)

    # -- misc buttons ------------------------------------------------------
    def on_save_log(self):
        p = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="pikafishjj-log.txt",
                                         filetypes=[("text", "*.txt")])
        if not p:
            return
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(self.log.get("1.0", "end"))
        self._log("[gui] \u65e5\u5fd7\u5df2\u4fdd\u5b58 " + p)

    def on_snap(self):
        p = self.player
        if p is None or p.grabber is None:
            self._log("[gui] \u5c1a\u672a\u8fde\u63a5\u7a97\u53e3")
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", initialfile="jj-frame.png",
                                           filetypes=[("png", "*.png")])
        if not path:
            return
        a = p.frame()
        try:
            from PIL import Image
            Image.fromarray(a).save(path)
            self._log("[gui] \u622a\u56fe\u5df2\u4fdd\u5b58 " + path)
        except Exception as exc:
            self._log("[gui] \u622a\u56fe\u4fdd\u5b58\u5931\u8d25\uff1a%s" % exc)


def main(argv=None):
    w32.set_dpi_aware()
    set_app_id()                    # must precede the window, see its docstring
    root = tk.Tk()
    try:
        scale = 1.0
        try:
            import ctypes
            scale = ctypes.windll.user32.GetDpiForSystem() / 96.0
        except Exception:
            scale = 1.0
        root.tk.call("tk", "scaling", 1.05 * max(1.0, scale))
    except Exception:
        pass
    try:
        app = App(root)
    except Exception as exc:                     # noqa: BLE001 - report, do not die mute
        import traceback
        tb = traceback.format_exc()
        try:
            import sys as _sys
            base = (os.path.dirname(os.path.abspath(_sys.executable))
                    if getattr(_sys, "frozen", False) else os.getcwd())
            with open(os.path.join(base, "pikafishjj-startup-error.log"), "w",
                      encoding="utf-8") as fh:
                fh.write(tb)
        except Exception:
            pass
        try:
            messagebox.showerror("pikafishjj",
                                 "启动失败：%s\n\n详情见 pikafishjj-startup-error.log" % exc)
        except Exception:
            pass
        raise
    app._log("[gui] 棋盘获取=%s   操作方式=%s   后端回退=%s" % (
        app.v["board"].get(), app.v["moves"].get(), app.v["fallback"].get()))
    if LAYOUT_DUMP:
        root.after(1200, lambda: app.dump_layout(LAYOUT_DUMP))
    app._log("[gui] pikafishjj \u63a7\u5236\u53f0\u5df2\u542f\u52a8")
    app._log("[gui] \u5148\u70b9\u201c\u68c0\u6d4b\u201d\u786e\u8ba4\u7a97\u53e3\uff0c\u518d\u70b9\u201c\u8bfb\u53d6\u68cb\u76d8\u201d\u6216\u201c\u5f00\u59cb\u5bf9\u5c40\u201d")
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
