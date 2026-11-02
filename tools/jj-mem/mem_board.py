# -*- coding: utf-8 -*-
"""Structure-first hunt for the live xiangqi board array (encoding-agnostic).

We know the position on screen (3k5/6R1C/3c5/6N2/6b2/9/9/9/2r1p1p2/5K3 = 10 pieces on
78 empty squares), so any 90-cell array whose 'unusual' entries sit exactly on those
cells is a candidate - whatever the piece codes are.
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PQ, VR = 0x0400, 0x0010
MEM_COMMIT, MEM_PRIVATE, GUARD, NOACCESS = 0x1000, 0x20000, 0x100, 0x01

# screen grid as the app draws it (row 0 top). 1 = occupied.
SCREEN = [
    "...k.....",
    "......R.C",
    "...c.....",
    "......N..",
    "......b..",
    ".........",
    ".........",
    ".........",
    "..r.p.p..",
    "....K....",
]

def cell_sets():
    """All index sets the board could use, under row/col major and flips."""
    out = {}
    for order in ("row", "col"):
        for fr in (0, 1):
            for fc in (0, 1):
                idx = []
                for r in range(10):
                    for c in range(9):
                        if SCREEN[r][c] == ".":
                            continue
                        rr, cc = (9 - r if fr else r), (8 - c if fc else c)
                        idx.append(rr * 9 + cc if order == "row" else cc * 10 + rr)
                out["%s%s%s" % (order, "-fr" if fr else "", "-fc" if fc else "")] = frozenset(idx)
    return out

SETS = cell_sets()

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wt.DWORD), ("__a1", wt.DWORD),
                ("RegionSize", ctypes.c_ulonglong), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD), ("__a2", wt.DWORD)]

k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

def pids():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='WeChatAppEx.exe'\" | "
        "Select-Object -ExpandProperty ProcessId"], capture_output=True, text=True)
    return [int(x) for x in out.stdout.split() if x.strip().isdigit()]

def regions(h):
    addr = 0
    while True:
        mbi = MBI()
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if (mbi.State == MEM_COMMIT and mbi.RegionSize and mbi.Type == MEM_PRIVATE
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
        return b""
    return buf.raw[:got.value]

def hits_in(blob, limit=8):
    """90-cell windows whose minority entries sit exactly on the occupied cells."""
    out = []
    n = len(blob)
    for stride in (1, 2, 4):
        span = 90 * stride
        if n < span:
            continue
        i = 0
        while i + span <= n:
            win = blob[i:i + span]
            if stride == 1:
                vals = list(win)
            else:
                vals = [int.from_bytes(win[k * stride:(k + 1) * stride], "little")
                        for k in range(90)]
            mode, mc = Counter(vals).most_common(1)[0]
            if mc < 80:                     # need ~78 empties
                i += 1
                continue
            odd = frozenset(k for k, v in enumerate(vals) if v != mode)
            for tag, want in SETS.items():
                if odd == want:
                    out.append((i, stride, tag, mode, vals))
                    break
            if len(out) >= limit:
                return out
            i += 1
    return out

total = 0
for pid in pids():
    h = k32.OpenProcess(PQ | VR, False, pid)
    if not h:
        continue
    for base, size in regions(h):
        blob = read(h, base, min(size, 320 * 1024 * 1024))
        if len(blob) < 360:
            continue
        found = hits_in(blob)
        for off, stride, tag, mode, vals in found:
            total += 1
            occupied = {k: vals[k] for k in sorted(SETS[tag])}
            print("pid %-6d @%s stride=%d %-10s empty=0x%02x  %s" % (
                pid, hex(base + off), stride, tag, mode,
                " ".join("%d:%d" % (k, v) for k, v in list(occupied.items())[:12])))
    k32.CloseHandle(h)
print("total hits", total)
