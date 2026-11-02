# -*- coding: utf-8 -*-
"""Experiment: change the board once (play a move), snapshot, undo, snapshot, and
report exactly which memory pages followed the board."""
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

def regions(h, min_size=64 * 1024):
    addr = 0
    while True:
        mbi = MBI()
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if (mbi.State == MEM_COMMIT and mbi.RegionSize >= min_size and mbi.Type == MEM_PRIVATE
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

def snap(h):
    pages = {}
    for base, size in regions(h):
        off = 0
        while off < size:
            blob = read(h, base + off, min(PAGE, size - off))
            if blob is not None:
                pages[base + off] = (hashlib.blake2b(blob, digest_size=8).digest(), blob)
            off += PAGE
    return pages

def diff(a, b, label):
    changed = [k for k in a if a[k][0] != b.get(k, (None, None))[0]]
    changed += [k for k in b if k not in a]
    print("%s: %d pages changed" % (label, len(changed)))
    for k in sorted(changed)[:10]:
        A = a.get(k, (None, b""))[1]
        Bb = b.get(k, (None, b""))[1]
        offs = [i for i in range(min(len(A), len(Bb))) if A[i] != Bb[i]]
        print("   @%s  %d bytes differ, first at %s" % (
            hex(k), len(offs), offs[:6]))
        for i in offs[:4]:
            lo = max(0, i - 24)
            print("       @+%d  A=%s" % (i, A[lo:i + 24].hex()))
            print("             B=%s" % Bb[lo:i + 24].hex())
    return changed

def main():
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 5604
    w32.set_dpi_aware()
    hwnd, title = w32.find_window("JJ")
    x0, y0, cw, ch = w32.client_rect_screen(hwnd)
    frame = w32.WindowGrabber().grab(hwnd)
    cal = V.calibrate(frame, verbose=False)
    print("window %s client (%d,%d,%d,%d) cal cpitch=%.2f rpitch=%.2f" % (
        hwnd, x0, y0, cw, ch, cal.get("cpitch") or 0, cal.get("rpitch") or 0))
    orient = B.screen_to_internal  # identity helper for the geometry
    def pt(scr_i, scr_j, flip=False):
        si, sj = (8 - scr_i, 9 - scr_j) if flip else (scr_i, scr_j)
        gx, gy = V.grid_xy(cal, si, sj)
        return int(round(x0 + gx)), int(round(y0 + gy))

    h = k32.OpenProcess(PQ | VR, False, pid)
    if not h:
        print("cannot open", pid); return 1
    t0 = time.time()
    A = snap(h)
    print("snapshot A: %d pages (%.0fs)" % (len(A), time.time() - t0))

    # the red chariot on screen row 1 col 6 slides to row 1 col 0
    src, dst = pt(6, 1), pt(0, 1)
    print("click source %s -> target %s" % (src, dst))
    w32.click(*src)
    time.sleep(0.35)
    w32.click(*dst)
    time.sleep(1.4)
    Bs = snap(h)
    diff(A, Bs, "A -> after the move")

    # undo (悔棋) - the button row under the board
    undo = (x0 + int(0.30 * cw), y0 + int(0.815 * ch))
    print("click undo at %s" % (undo,))
    w32.click(*undo)
    time.sleep(1.4)
    Cs = snap(h)
    diff(A, Cs, "A -> after undo (should be near empty)")
    diff(Bs, Cs, "after the move -> after undo (the board)")
    return 0

sys.exit(main())
