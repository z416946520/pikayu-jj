# -*- coding: utf-8 -*-
"""Controlled board-change experiment, narrowed to the renderer's small private
regions, with the click verified against a second recognition."""
import ctypes
import ctypes.wintypes as wt
import hashlib
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
from pikafishjj import w32, vision as V, board as B

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PQ, VR = 0x0400, 0x0010
MEM_COMMIT, MEM_PRIVATE, GUARD, NOACCESS = 0x1000, 0x20000, 0x100, 0x01
PAGE = 64 * 1024

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wt.DWORD), ("__a1", wt.DWORD),
                ("RegionSize", ctypes.c_ulonglong), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD), ("__a2", wt.DWORD)]

k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

def ws_pids():
    import json, subprocess
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='WeChatAppEx.exe'\" | "
        "Select-Object ProcessId,WorkingSetSize | ConvertTo-Json -Compress"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.loads(out.stdout or "[]")
    d = d if isinstance(d, list) else [d]
    return sorted(((x["ProcessId"], x.get("WorkingSetSize") or 0) for x in d), key=lambda t: -t[1])

def regions(h, lo=1 << 20, hi=200 << 20):
    addr = 0
    while True:
        mbi = MBI()
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if (mbi.State == MEM_COMMIT and lo <= mbi.RegionSize <= hi and mbi.Type == MEM_PRIVATE
                and (mbi.Protect & 0xFF) != NOACCESS and not (mbi.Protect & GUARD)):
            yield mbi.BaseAddress, mbi.RegionSize
        nxt = mbi.BaseAddress + mbi.RegionSize
        if nxt <= mbi.BaseAddress:
            break
        addr = nxt

def read(h, base, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t(0)
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]

def frame_and_cal():
    a = w32.WindowGrabber().grab(hwnd)
    cal = V.calibrate(a, verbose=False)
    tpl, half = V.load_templates(cal=cal)
    info = {}
    scr, _s = V.recognize(a, cal, tpl, half=half, info=info)
    return a, cal, scr

def cells_of(scr, want_upper=True):
    for j in range(10):
        for i in range(9):
            c = scr[j][i]
            if c == "." or (c.isupper() != want_upper):
                continue
            yield i, j, c

def pick_move(scr):
    """A simple legal-looking red move: pawn one step forward, else a rook slide."""
    for i, j, c in cells_of(scr):
        if c != "P":
            continue
        if j - 1 >= 0 and scr[j - 1][i] == ".":        # screen rows grow downward
            return (i, j), (i, j - 1), "pawn"
    for i, j, c in cells_of(scr):
        if c not in "RC":
            continue
        for dj, di in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nj, ni = j + dj, i + di
            if 0 <= nj < 10 and 0 <= ni < 9 and scr[nj][ni] == ".":
                return (i, j), (ni, nj), "step"
    return None

w32.set_dpi_aware()
hwnd, title = w32.find_window("JJ")
x0, y0, cw, ch = w32.client_rect_screen(hwnd)
print("window %s client (%d,%d,%d,%d)" % (hwnd, x0, y0, cw, ch))

a, cal, scr0 = frame_and_cal()
print("cal cpitch=%.2f rpitch=%.2f model=%s" % (
    cal.get("cpitch") or 0, cal.get("rpitch") or 0, bool(cal.get("model"))))
print("position 0:", B.grid_to_fen(B.screen_to_internal(scr0, False), "w"))

def pt(i, j):
    gx, gy = V.grid_xy(cal, i, j)
    return int(round(x0 + gx)), int(round(y0 + gy))

mv = pick_move(scr0)
print("move:", mv)
if not mv:
    print("no simple move found"); sys.exit(1)
(src, dst, kind) = mv

# narrow the scan to small private regions of the app renderer
pid = None
for p, wset in ws_pids():
    h = k32.OpenProcess(PQ | VR, False, p)
    if not h:
        continue
    if any(True for _b, _s in regions(h)):
        pid = p
        break
# prefer the process that has the appid
for p, wset in ws_pids():
    hh = k32.OpenProcess(PQ | VR, False, p)
    if hh and read(hh, 0, 0) is not None:
        pass
print("scanning pid", pid)

def snap():
    pages = {}
    for base, size in regions(h):
        off = 0
        while off < size:
            blob = read(h, base + off, min(PAGE, size - off))
            if blob is not None:
                pages[base + off] = (hashlib.blake2b(blob, digest_size=8).digest(), blob)
            off += PAGE
    return pages

A = snap()
print("snapshot A: %d pages (%.0f MB)" % (len(A), sum(len(v[1]) for v in A.values()) / 1048576.0))
w32.click(*pt(*src)); time.sleep(0.45); w32.click(*pt(*dst)); time.sleep(1.3)
a2, cal2, scr1 = frame_and_cal()
fen1 = B.grid_to_fen(B.screen_to_internal(scr1, False), "w")
print("position 1:", fen1)
if scr1 == scr0:
    print("the click did not change the board")
    sys.exit(2)
Bs = snap()
A0 = {k: v[0] for k, v in A.items()}
B0 = {k: v[0] for k, v in Bs.items()}
chg = [k for k in A0 if A0.get(k) != B0.get(k)]
print("small-region pages changed: %d of %d" % (len(chg), len(A0)))
for k in sorted(chg)[:8]:
    A1, B1 = A[k][1], Bs[k][1]
    offs = [i for i in range(min(len(A1), len(B1))) if A1[i] != B1[i]]
    print("  @%s  %d bytes, first %s" % (hex(k), len(offs), offs[:8]))
    for i in offs[:3]:
        lo = max(0, i - 16)
        print("     @+%-6d A %s" % (i, A1[lo:i + 20].hex()))
        print("              B %s" % Bs[k][1][lo:i + 20].hex())
sys.exit(0)
