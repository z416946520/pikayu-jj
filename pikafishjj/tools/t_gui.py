# -*- coding: utf-8 -*-
"""Console plumbing: the new retry / rematch options must reach the player.

Builds the real tkinter console (hidden), reads the widgets back and renders the
info panel with a player that has counters, so a broken grid row or a forgotten
_collect() key fails here instead of in a game.

Run:  python pikafishjj\tools\t_gui.py
"""
import os
import sys
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)

from pikafishjj import gui, auto as A, board as B

FAILED = []
NCHECK = [0]
ENGINE = os.path.join(os.path.dirname(PKG), "pikafish",
                      "Pikafish-Windows-x86-64-universal.exe")


def check(name, got, want):
    NCHECK[0] += 1
    ok = (got == want)
    if not ok:
        FAILED.append(name)
    print("%-46s %-4s %r" % (name, "ok" if ok else "FAIL", got))
    if not ok:
        print("%-46s want %r" % ("", want))
    return ok


def main():
    root = tk.Tk()
    root.withdraw()
    app = gui.App(root)
    root.update_idletasks()

    check("the console built", bool(app.v), True)
    check("retries widget", "retries" in app.v, True)
    check("auto_next widget", "auto_next" in app.v, True)
    check("retries default", app.v["retries"].get(), str(gui.DEFAULTS["retries"]))
    check("auto_next default", app.v["auto_next"].get(),
          str(gui.DEFAULTS["auto_next"]))

    if os.path.isfile(ENGINE):
        app.v["exe"].set(ENGINE)
    app.v["retries"].set("5")
    app.v["auto_next"].set("False")
    cfg = app._collect()
    check("_collect returned a config", cfg is not None, True)
    if cfg:
        check("retries are collected", cfg["retries"], 5)
        check("auto_next is collected", cfg["auto_next"], False)
    app.v["retries"].set("99")
    check("retries clamp high", app._collect()["retries"], 10)
    app.v["retries"].set("0")
    check("retries clamp low", app._collect()["retries"], 1)

    # the worker must hand both options over untouched
    p = A.AutoPlayer(retries=5, auto_next=False)
    check("the player takes the options", (p.retries, p.auto_next), (5, False))
    app.player = p
    app.v["retries"].set("7")
    app.v["auto_next"].set("True")
    try:
        app.on_apply()
    except Exception as exc:                       # noqa: BLE001
        check("on_apply()", "%s: %s" % (type(exc).__name__, exc), "no exception")
    check("on_apply set retries", p.retries, 7)
    check("on_apply set auto_next", p.auto_next, True)

    # info panel: the counters must be visible where the retry logic lives
    p = A.AutoPlayer(our_side="w")
    p.grid = B.new_grid()
    p.stats.update(moves=7, games=2, reads=5, recognitions=5, frames=5,
                   attempts=2, recover=1, fails=3, rematch=4, dialogs=1)
    app._refresh_info(p)
    root.update_idletasks()
    text = app.info.get("1.0", "end")
    check("info shows the ply retries", "落子重试 2" in text, True)
    check("info shows the recoveries", "恢复 1" in text, True)
    check("info shows the failures", "失败 3" in text, True)
    check("info shows the rematch count", "已点 4 次" in text, True)
    check("info shows the round counter", "第 2 局" in text, True)

    # the background row must say which kind of click is in use right now
    p.background = True
    p.quiet = True
    p.bg_ok = True
    app._refresh_info(p)
    root.update_idletasks()
    text = app.info.get("1.0", "end")
    check("info shows the quiet click mode", "\u9759\u9ed8\u70b9\u51fb" in text, True)
    check("...and that focus is not stolen", "\u4e0d\u62a2\u7126\u70b9 \u5f00" in text, True)

    # the two new dropdowns must round-trip label -> value -> label -----------
    app.v["board"].set("\u540e\u7aef\u8bfb\u53d6 (\u5c0f\u7a0b\u5e8f\u5185\u5b58)")
    app.v["moves"].set("\u540e\u7aef\u64cd\u4f5c (\u4e0d\u70b9\u9f20\u6807)")
    cfg2 = app._collect()
    check("the board mode is collected", cfg2.get("board"), "backend")
    check("the move mode is collected", cfg2.get("moves"), "backend")
    app.cfg.update(cfg2)
    app._apply_cfg_to_widgets()               # what the next launch does
    check("...and comes back as its label, not English",
          app.v["board"].get().startswith("\u540e\u7aef"), True)
    check("...for the move mode too",
          app.v["moves"].get().startswith("\u540e\u7aef"), True)
    app.cfg["board"] = "vision"               # a config written by the old build
    app.cfg["moves"] = "physical"
    app._apply_cfg_to_widgets()
    check("a raw English value still loads",
          (app.v["board"].get().startswith("\u89c6\u89c9"),
           app.v["moves"].get().startswith("\u7269\u7406")), (True, True))
    check("...and is saved back unchanged", app._collect().get("board"), "vision")
    p.bg_ok = False
    app._refresh_info(p)
    root.update_idletasks()
    text = app.info.get("1.0", "end")
    check("info shows the temporary foreground mode",
          "\u6682\u7528\u524d\u53f0" in text, True)

    # the game card must wrap: two toggles per row, otherwise the card clips
    def walk(w):
        for ch in w.winfo_children():
            yield ch
            for sub in walk(ch):
                yield sub

    boxes = {}
    for w in walk(getattr(app, "root", app)):
        if w.winfo_class() == "TCheckbutton":
            boxes[str(w.cget("text"))] = (w.grid_info().get("row"), w.grid_info().get("column"))
    check("all four game toggles exist",
          all(k in boxes for k in ("后台模式（免打扰）", "演练模式（只算不点）",
                                   "新局自动开始", "结算自动再来一局")), True)
    check("后台模式 on the first row", boxes.get("后台模式（免打扰）"), (0, 0))
    check("演练模式 on the first row", boxes.get("演练模式（只算不点）"), (0, 1))
    check("新局自动开始 on the second row", boxes.get("新局自动开始"), (1, 0))
    check("结算自动再来一局 on the second row", boxes.get("结算自动再来一局"), (1, 1))

    # the preview draws flat discs: outer ring + inner ring, never a drop shadow
    app._draw_board(B.fen_to_grid(B.OPENING_FEN))
    root.update_idletasks()
    ovals = [i for i in app.canvas.find_all() if app.canvas.type(i) == "oval"]
    check("32 pieces draw 64 ovals (no shadow)", len(ovals), 64)
    fills = [str(app.canvas.itemcget(i, "fill")) for i in ovals]
    check("no shadow colour on the canvas", "#c19a63" in fills, False)
    app._draw_board(B.fen_to_grid(B.OPENING_FEN), from_cell=(7, 7), to_cell=(4, 7))
    root.update_idletasks()
    ovals = [i for i in app.canvas.find_all() if app.canvas.type(i) == "oval"]
    check("the move rings add two more ovals", len(ovals), 66)

    # the window must wear the shipped icon, in the title bar and the taskbar
    icon = gui.find_icon()
    check("the app icon file is found", bool(icon), True)
    check("the icon is the shipped .ico", bool(icon) and icon.endswith("pikafishjj.ico"), True)
    # Tk answers wm iconbitmap with '' for .ico resources and it puts the icon
    # on the frame window (the parent of root.winfo_id()), so ask Windows for
    # the real handle and compare its pixels with the shipped .ico.
    import ctypes
    from ctypes import wintypes
    root.deiconify()
    root.update()
    user32 = ctypes.windll.user32
    user32.SendMessageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    user32.GetClassLongPtrW.restype = ctypes.c_void_p
    user32.GetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetParent.restype = wintypes.HWND
    user32.GetParent.argtypes = [wintypes.HWND]
    frame = int(user32.GetParent(int(root.winfo_id())))
    check("set_window_icon reports success", gui.set_window_icon(root), icon)
    root.update()
    big = user32.SendMessageW(frame, 0x7F, 1, None)                    # WM_GETICON, ICON_BIG
    small = user32.SendMessageW(frame, 0x7F, 0, None)                  # ICON_SMALL
    cls = user32.GetClassLongPtrW(frame, -14)                          # GCLP_HICON
    check("the window carries an icon", bool(big and small and cls), True)

    class ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", ctypes.c_int), ("xHotspot", ctypes.c_uint),
                    ("yHotspot", ctypes.c_uint), ("hbmMask", ctypes.c_void_p),
                    ("hbmColor", ctypes.c_void_p)]

    class BITMAP(ctypes.Structure):
        _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long),
                    ("bmHeight", ctypes.c_long), ("bmWidthBytes", ctypes.c_long),
                    ("bmPlanes", ctypes.c_ushort), ("bmBitsPixel", ctypes.c_ushort),
                    ("bmBits", ctypes.c_void_p)]

    class BMIH(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint), ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long), ("biPlanes", ctypes.c_ushort),
                    ("biBitCount", ctypes.c_ushort), ("biCompression", ctypes.c_uint),
                    ("biSizeImage", ctypes.c_uint), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", ctypes.c_uint),
                    ("biClrImportant", ctypes.c_uint)]

    def icon_stats(handle):
        """(width, height, opaque share, mean RGB of the opaque pixels) of an HICON."""
        info = ICONINFO()
        if not handle or not user32.GetIconInfo(ctypes.c_void_p(handle), ctypes.byref(info)):
            return None
        bm = BITMAP()
        ctypes.windll.gdi32.GetObjectW(ctypes.c_void_p(info.hbmColor), ctypes.sizeof(bm),
                                       ctypes.byref(bm))
        w, h = int(bm.bmWidth), int(bm.bmHeight)
        hdr = BMIH(ctypes.sizeof(BMIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = (ctypes.c_ubyte * (w * h * 4))()
        dc = user32.GetDC(None)
        ctypes.windll.gdi32.GetDIBits(ctypes.c_void_p(dc), ctypes.c_void_p(info.hbmColor), 0, h,
                                      buf, ctypes.byref(hdr), 0)
        user32.ReleaseDC(None, ctypes.c_void_p(dc))
        px = bytes(buf)
        solid = [(px[i + 2], px[i + 1], px[i]) for i in range(0, len(px), 4) if px[i + 3] > 128]
        if not solid:
            return None
        mean = tuple(sum(p[c] for p in solid) / float(len(solid)) for c in range(3))
        return (w, h, len(solid) / float(w * h), mean)

    live = icon_stats(big)
    want = None
    try:
        from PIL import Image
        import numpy as np
        sheet = Image.open(icon).convert("RGBA")
        sheet.load()
        arr = np.asarray(sheet).astype("float32")
        alpha = arr[:, :, 3]
        solid = arr[alpha > 128][:, :3]
        want = (sheet.size[0], sheet.size[1], float((alpha > 128).mean()),
                tuple(solid.mean(axis=0)))
    except Exception as exc:                                      # pragma: no cover
        print("ico stats unavailable: %s: %s" % (type(exc).__name__, exc))
    if live is None or want is None:
        check("the window icon can be read back", bool(live), True)
    else:
        check("the window icon is square", live[0] == live[1], True)
        check("the window icon is in the shipped size range",
              live[0] in (16, 32, 48, 64, 128, 256), True)
        check("the window icon has the shipped coverage",
              abs(live[2] - want[2]) < 0.30, True)
        drift = max(abs(live[3][c] - want[3][c]) for c in range(3))
        check("the window icon has the shipped colours", bool(drift < 60.0), True)
    print("      live icon %s / shipped %s" % (
        None if live is None else (live[0], live[1], round(live[2], 3),
                                   tuple(int(v) for v in live[3])),
        None if want is None else (want[0], want[1], round(want[2], 3),
                                   tuple(int(v) for v in want[3]))))
    check("the app id can be set", gui.set_app_id("pikafishjj.gui.test"), True)
    buf = ctypes.c_wchar_p()
    hr = ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(buf))
    check("the app id is what the taskbar sees", (hr, buf.value), (0, "pikafishjj.gui.test"))

    app.player = None
    root.destroy()

    print("")
    if FAILED:
        print("checks: %d, failed: %d - %s" % (NCHECK[0], len(FAILED), ", ".join(FAILED)))
        print("GUI FAILED")
        return 1
    print("checks: %d, all passed" % NCHECK[0])
    print("GUI OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
