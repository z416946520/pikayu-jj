# -*- coding: utf-8 -*-
"""Dump the context around the app-state strings found in the JJ象棋 renderer."""
import ctypes
import ctypes.wintypes as wt
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 5604

NEEDLES = [b"rnbakabnr", b'"fen"', b'"pieces"', b'"board"', b'"moveList"',
           b'"turn"', b'"side"', b'"result"', b'"chessboard"', b'"pieceMap"']

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wt.DWORD), ("__a1", wt.DWORD),
                ("RegionSize", ctypes.c_ulonglong), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD), ("__a2", wt.DWORD)]

k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

def regions(h):
    addr = 0
    while True:
        mbi = MBI()
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if (mbi.State == MEM_COMMIT and mbi.RegionSize
                and (mbi.Protect & 0xFF) != PAGE_NOACCESS and not (mbi.Protect & PAGE_GUARD)):
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

def clean(b):
    return re.sub(r"[\x00-\x08\x0b-\x1f]+", "|", b.decode("utf-8", "replace"))

def main():
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, PID)
    if not h:
        print("cannot open", PID); return 1
    seen = {}
    for base, size in regions(h):
        blob = read(h, base, min(size, 128 * 1024 * 1024))
        if not blob:
            continue
        for nd in NEEDLES:
            start = 0
            while len(seen.get(nd, [])) < 4:
                i = blob.find(nd, start)
                if i < 0:
                    break
                start = i + 1
                lo = max(0, i - 220)
                hi = min(len(blob), i + 260)
                seen.setdefault(nd, []).append((base + i, clean(blob[lo:hi])))
    for nd, hits in seen.items():
        print("\n===== %s (%d shown)" % (nd.decode(), len(hits)))
        for addr, ctx in hits:
            print("  @%s  %s" % (hex(addr), ctx[:420]))
    return 0

sys.exit(main())
