# -*- coding: utf-8 -*-
"""Where does the JJ象棋 renderer keep (a) the engine bridge log, (b) the protocol
message names, (c) live game state keys?"""
import ctypes
import ctypes.wintypes as wt
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PQ, VR = 0x0400, 0x0010
MEM_COMMIT, MEM_PRIVATE, PAGE_GUARD, PAGE_NOACCESS = 0x1000, 0x20000, 0x100, 0x01
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 5604

NEEDLES = [b"localmove", b"bestmove", b"ucinewgame", b"uciok", b"evaluate", b"pv ",
           b'"myTurn"', b'"turn"', b'"gameInfo"', b'"roomId"', b'"chesses"',
           b'"boardData"', b'"moveList"', b'"currentFen"', b'"battleInfo"',
           b'"matchInfo"', b'"gameState"', b'"startFen"', b'"moves"', b'"selfInfo"',
           b'"oppInfo"', b'"chessBoard"', b'"pieces"', b'"walk"', b'"eat"']
NAME = re.compile(rb'"name":"([a-z_0-9]{3,32})"')

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
        if (mbi.State == MEM_COMMIT and mbi.RegionSize and mbi.Type == MEM_PRIVATE
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

def clean(b, n=300):
    return re.sub(r"[\x00-\x08\x0b-\x1f]+", "|", b.decode("utf-8", "replace"))[:n]

def main():
    h = k32.OpenProcess(PQ | VR, False, PID)
    if not h:
        print("cannot open", PID); return 1
    counts, samples = {}, {}
    names = {}
    for base, size in regions(h):
        blob = read(h, base, min(size, 256 * 1024 * 1024))
        if not blob:
            continue
        for nd in NEEDLES:
            i = blob.find(nd)
            if i >= 0:
                counts[nd] = counts.get(nd, 0) + blob.count(nd)
                if nd not in samples:
                    lo, hi = max(0, i - 150), min(len(blob), i + 320)
                    samples[nd] = (base + i, clean(blob[lo:hi]))
        for m in NAME.finditer(blob):
            nm = m.group(1).decode()
            names[nm] = names.get(nm, 0) + 1
    print("== state keys / engine markers ==")
    for nd in NEEDLES:
        if nd in counts:
            addr, ctx = samples[nd]
            print("  %-14s x%-5d @%s  %s" % (nd.decode(), counts[nd], hex(addr), ctx))
    print("\n== protocol message names in heap (%d distinct) ==" % len(names))
    for nm, c in sorted(names.items(), key=lambda kv: -kv[1])[:40]:
        print("  %-34s x%d" % (nm, c))
    return 0

sys.exit(main())
