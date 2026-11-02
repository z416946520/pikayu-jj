# -*- coding: utf-8 -*-
"""Vectorised hunt for the live board array (numpy, chunked)."""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PQ, VR = 0x0400, 0x0010
MEM_COMMIT, MEM_PRIVATE, GUARD, NOACCESS = 0x1000, 0x20000, 0x100, 0x01
CHUNK = 48 * 1024 * 1024
OVER = 8 * 90

SCREEN = ["...k.....", "......R.C", "...c.....", "......N..", "......b..",
          ".........", ".........", ".........", "..r.p.p..", "....K...."]

def cell_sets():
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
                out["%s%s%s" % (order, "-fr" if fr else "", "-fc" if fc else "")] = set(idx)
    return out

SETS = cell_sets()
EMPTIES = [0x00, 0x20, 0xFF, 0x10, 0x0A, 0x2E, 0x37]

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
        "Select-Object ProcessId,WorkingSetSize | ConvertTo-Json -Compress"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    import json
    data = json.loads(out.stdout or "[]")
    data = data if isinstance(data, list) else [data]
    return sorted(((d["ProcessId"], d.get("WorkingSetSize") or 0) for d in data),
                  key=lambda t: -t[1])

def regions(h):
    addr = 0
    while True:
        mbi = MBI()
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if (mbi.State == MEM_COMMIT and mbi.RegionSize and mbi.Type == MEM_PRIVATE
                and (mbi.Protect & 0xFF) != NOACCESS and not (mbi.Protect & GUARD)
                and mbi.RegionSize >= 360):
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

def scan_chunk(arr, base, hits):
    for stride in (1, 2, 4):
        v = arr[::stride]
        if len(v) < 90:
            continue
        for X in EMPTIES:
            nz = (v != np.uint8(X))
            cs = np.concatenate(([0], np.cumsum(nz, dtype=np.int32)))
            sums = cs[90:] - cs[:-90]
            for i in np.nonzero(sums == 10)[0]:
                win = v[i:i + 90]
                odd = set(np.nonzero(win != np.uint8(X))[0].tolist())
                for tag, want in SETS.items():
                    if odd == want:
                        vals = {k: int(win[k]) for k in sorted(want)}
                        hits.append((base + i * stride, stride, tag, X, vals))
                        print("  HIT %s stride=%d %-10s empty=0x%02x  %s" % (
                            hex(base + i * stride), stride, tag, X,
                            " ".join("%d:%d" % kv for kv in list(vals.items())[:12])))
                        break
    return hits

def main():
    for pid, wset in pids():
        h = k32.OpenProcess(PQ | VR, False, pid)
        if not h:
            continue
        hits = []
        done = 0
        for base, size in regions(h):
            size = min(size, 320 * 1024 * 1024)
            off = 0
            while off < size and len(hits) < 12:
                take = min(CHUNK, size - off)
                blob = read(h, base + off, take + OVER)
                if blob:
                    arr = np.frombuffer(blob, dtype=np.uint8)
                    scan_chunk(arr, base + off, hits)
                off += take
                done += take
            if len(hits) >= 12:
                break
        if hits:
            print("PID %d: %d hits (scanned %.0f MB)" % (pid, len(hits), done / 1048576.0))
        k32.CloseHandle(h)
    return 0

sys.exit(main())
