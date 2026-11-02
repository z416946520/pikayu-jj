# -*- coding: utf-8 -*-
"""Enumerate xiangqi FEN strings in the JJ象棋 renderer and say which look like a
live game state rather than shipped lesson data."""
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

FEN = re.compile(rb"[rnbakcpRNBAKCP1-9]{1,9}(?:/[rnbakcpRNBAKCP1-9]{1,9}){9}\s+[wb]")
LESSON = [b"courseName", b"courseType", b"tips", b"aiuse", b"progressNum", b"order"]

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
                and (mbi.Protect & 0xFF) != PAGE_NOACCESS and not (mbi.Protect & PAGE_GUARD)
                and mbi.Type == 0x20000):          # MEM_PRIVATE: heaps only
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

def main():
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, PID)
    if not h:
        print("cannot open", PID); return 1
    total = 0
    live = []
    lesson = 0
    for base, size in regions(h):
        blob = read(h, base, min(size, 256 * 1024 * 1024))
        if not blob:
            continue
        for m in FEN.finditer(blob):
            total += 1
            is_lesson = any(k in blob[max(0, m.start() - 600):m.end() + 600] for k in LESSON)
            if is_lesson:
                lesson += 1
                continue
            live.append((base + m.start(), m.group().decode()))
    print("FEN-shaped strings: %d (lesson context: %d, other: %d)" % (total, lesson, len(live)))
    seen = {}
    for addr, fen in live:
        seen.setdefault(fen, []).append(addr)
    for fen, addrs in sorted(seen.items(), key=lambda kv: -len(kv[1]))[:25]:
        print("  x%-3d %s   first@%s" % (len(addrs), fen[:80], hex(addrs[0])))
    return 0

sys.exit(main())
