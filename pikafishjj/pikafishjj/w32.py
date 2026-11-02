# -*- coding: utf-8 -*-
"""pikafishjj.w32 - minimal ctypes Win32 layer (DPI aware screen capture + input).

Everything here is DPI-aware: a DPI-unaware process sees the 2560x1440 desktop as
2048x1152 (Windows is at 125% scaling), which silently crops screenshots to the
top-left 80% of the window and misplaces every click.
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
INPUT_MOUSE = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class RGBQUAD(ctypes.Structure):
    _fields_ = [("rgbBlue", ctypes.c_ubyte), ("rgbGreen", ctypes.c_ubyte),
                ("rgbRed", ctypes.c_ubyte), ("rgbReserved", ctypes.c_ubyte)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", RGBQUAD * 1)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def set_dpi_aware():
    """Must be called before any coordinate is read or written."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_AWARE_V2
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def find_window(substr):
    """Return the first visible top-level window whose title contains substr."""
    found = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if substr in buf.value:
            found.append((hwnd, buf.value))
            return False
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return found[0] if found else (None, None)


def client_rect_screen(hwnd):
    """Client area of hwnd in physical screen coordinates -> (x, y, w, h)."""
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, r.right - r.left, r.bottom - r.top



def list_windows():
    """Every visible top-level window, topmost first -> [(hwnd, title, cls, pid)]."""
    out = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append((int(hwnd), buf.value, cls.value, int(pid.value)))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return out



class ScreenGrabber(object):
    """Reusable GDI resources for fast repeated BitBlt grabs."""

    def __init__(self):
        self.hdc = None
        self.memdc = None
        self.bmp = None
        self.size = (0, 0)
        self.buf = None
        self.bi = BITMAPINFO()
        h = self.bi.bmiHeader
        h.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        h.biPlanes = 1
        h.biBitCount = 32
        h.biCompression = 0

    def _ensure(self, w, h):
        if self.hdc is None:
            self.hdc = user32.GetDC(0)
            self.memdc = gdi32.CreateCompatibleDC(self.hdc)
        if self.size != (w, h):
            if self.bmp:
                gdi32.DeleteObject(self.bmp)
            self.bmp = gdi32.CreateCompatibleBitmap(self.hdc, w, h)
            gdi32.SelectObject(self.memdc, self.bmp)
            self.size = (w, h)
            self.buf = ctypes.create_string_buffer(w * h * 4)
            self.bi.bmiHeader.biWidth = w
            self.bi.bmiHeader.biHeight = -h

    def grab(self, x, y, w, h):
        """Return an (h, w, 3) uint8 RGB array of the screen region."""
        import numpy as np
        self._ensure(w, h)
        gdi32.BitBlt(self.memdc, 0, 0, w, h, self.hdc, x, y, SRCCOPY | CAPTUREBLT)
        gdi32.GetDIBits(self.memdc, self.bmp, 0, h, self.buf,
                        ctypes.byref(self.bi), 0)
        arr = np.frombuffer(self.buf.raw, dtype=np.uint8, count=w * h * 4)
        arr = arr.reshape(h, w, 4)[:, :, 2::-1]
        return np.ascontiguousarray(arr)

    def close(self):
        if self.bmp:
            gdi32.DeleteObject(self.bmp)
            self.bmp = None
        if self.memdc:
            gdi32.DeleteDC(self.memdc)
            self.memdc = None
        if self.hdc:
            user32.ReleaseDC(0, self.hdc)
            self.hdc = None


def bring_to_front(hwnd):
    """Best-effort foreground activation so injected clicks land on the window."""
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        fg = user32.GetForegroundWindow()
        if fg == hwnd:
            return True
        tid_fg = user32.GetWindowThreadProcessId(fg, None)
        tid_me = ctypes.windll.kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(tid_me, tid_fg, True)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.AttachThreadInput(tid_me, tid_fg, False)
        return user32.GetForegroundWindow() == hwnd
    except Exception:
        return False


def screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _send(inp):
    n = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    return n == 1


def _mouse(dx, dy, flags):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.u.mi.dx = int(dx)
    inp.u.mi.dy = int(dy)
    inp.u.mi.mouseData = 0
    inp.u.mi.dwFlags = flags
    inp.u.mi.time = 0
    inp.u.mi.dwExtraInfo = None
    return _send(inp)


def click(x, y, hold=0.03):
    """Left click at physical screen coordinates (x, y)."""
    import time
    sw, sh = screen_size()
    for _ in range(2):
        _mouse(x * 65535 // (sw - 1), y * 65535 // (sh - 1),
               MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK)
        time.sleep(0.01)
    _mouse(x * 65535 // (sw - 1), y * 65535 // (sh - 1),
           MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK | MOUSEEVENTF_LEFTDOWN)
    time.sleep(hold)
    _mouse(x * 65535 // (sw - 1), y * 65535 // (sh - 1),
           MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK | MOUSEEVENTF_LEFTUP)
    return True


def click_client(hwnd, cx, cy, hold=0.03):
    """Left click at client-area coordinates of hwnd."""
    x, y, w, h = client_rect_screen(hwnd)
    return click(x + cx, y + cy, hold)

# --- background operation -------------------------------------------------
# A window that is covered by other windows still renders through PrintWindow,
# so the board can be read without bringing the game to the front.  Clicks have
# to go through the real input queue (posted mouse messages are ignored by the
# mini-program's Chromium renderer - measured), so the pointer is moved, the
# click is delivered, and the pointer is put straight back; WS_EX_NOACTIVATE
# keeps the game from stealing the foreground while that happens.

PW_RENDERFULLCONTENT = 0x00000002
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
HWND_TOP = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020


def is_minimized(hwnd):
    return bool(user32.IsIconic(hwnd))


def window_rect(hwnd):
    """Whole window (frame included) in screen coordinates -> (x, y, w, h)."""
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def point_owner(x, y):
    """Top-level window that owns screen point (x, y) - 0 when none."""
    h = user32.WindowFromPoint(_POINT(int(x), int(y)))
    if not h:
        return 0
    return user32.GetAncestor(h, 2)          # GA_ROOT


def title_of(hwnd):
    """Window title of hwnd ('' when it has none or is gone)."""
    try:
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
    except Exception:
        return ""


class WindowGrabber(object):
    """PrintWindow capture of a window's client area.

    Verified on the WeChat mini-program window: while a topmost cover window hid
    it completely the screen grab returned the cover, while this returned pixels
    identical to the uncovered screen grab.  A minimised window renders black -
    grab() returns None then so the caller can fall back to a screen grab.
    """

    def __init__(self):
        self.hwnd = None
        self.memdc = None
        self.bmp = None
        self.size = (0, 0)
        self.buf = None
        self.bi = BITMAPINFO()
        h = self.bi.bmiHeader
        h.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        h.biPlanes = 1
        h.biBitCount = 32
        h.biCompression = 0

    def _ensure(self, hwnd, w, h):
        if self.memdc is None:
            self.memdc = gdi32.CreateCompatibleDC(user32.GetDC(0))
        if self.size != (w, h):
            if self.bmp:
                gdi32.DeleteObject(self.bmp)
            self.bmp = gdi32.CreateCompatibleBitmap(user32.GetDC(0), w, h)
            gdi32.SelectObject(self.memdc, self.bmp)
            self.size = (w, h)
            self.buf = ctypes.create_string_buffer(w * h * 4)
            self.bi.bmiHeader.biWidth = w
            self.bi.bmiHeader.biHeight = -h
        self.hwnd = hwnd

    def grab(self, hwnd, min_bright=3.0):
        """(h, w, 3) uint8 RGB client-area image, or None when unusable."""
        import numpy as np
        if not hwnd or is_minimized(hwnd) or not user32.IsWindowVisible(hwnd):
            return None
        wx, wy, ww, wh = window_rect(hwnd)
        cx, cy, cw, ch = client_rect_screen(hwnd)
        if ww <= 0 or wh <= 0 or cw <= 0 or ch <= 0:
            return None
        self._ensure(hwnd, ww, wh)
        hdc = user32.GetWindowDC(hwnd)
        ok = user32.PrintWindow(hwnd, self.memdc, PW_RENDERFULLCONTENT)
        gdi32.GetDIBits(self.memdc, self.bmp, 0, wh, self.buf,
                        ctypes.byref(self.bi), 0)
        user32.ReleaseDC(hwnd, hdc)
        if not ok:
            return None
        arr = np.frombuffer(self.buf.raw, dtype=np.uint8, count=ww * wh * 4)
        arr = arr.reshape(wh, ww, 4)[:, :, 2::-1]
        ox, oy = cx - wx, cy - wy
        crop = np.ascontiguousarray(arr[oy:oy + ch, ox:ox + cw])
        if crop.size == 0 or float(crop.astype(np.int32).sum(axis=2).mean()) < min_bright * 3.0:
            return None                      # minimised / not rendered yet
        return crop

    def close(self):
        if self.bmp:
            gdi32.DeleteObject(self.bmp)
            self.bmp = None
        if self.memdc:
            gdi32.DeleteDC(self.memdc)
            self.memdc = None
        self.size = (0, 0)


def set_no_activate(hwnd, on=True):
    """WS_EX_NOACTIVATE on/off: clicks on this window stop taking the foreground."""
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    want = (ex | WS_EX_NOACTIVATE) if on else (ex & ~WS_EX_NOACTIVATE)
    if want == ex:
        return False
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, want)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER |
                        SWP_NOACTIVATE | SWP_FRAMECHANGED)
    return True


def has_no_activate(hwnd):
    return bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_NOACTIVATE)


def set_topmost(hwnd, on=True):
    """Keep the game above other windows (or stop doing that)."""
    return bool(user32.SetWindowPos(hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST,
                                    0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE))


def raise_window(hwnd):
    """Put hwnd at the top of the ordinary (non-topmost) z-order, unactivated.

    Lowering a raised window with HWND_NOTOPMOST drops it at the top of the
    ordinary group, which leaves it in front of whatever the user was doing -
    the reason a background-mode run could end up showing the game window in
    front after a click that had to raise it.
    """
    return bool(user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0,
                                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE))


def set_cursor(x, y):
    return bool(user32.SetCursorPos(int(x), int(y)))


def click_silent(x, y, hold=0.03):
    """Click at screen (x, y) and put the pointer back where it was."""
    sx, sy = cursor_pos()
    click(x, y, hold)
    set_cursor(sx, sy)
    return True
