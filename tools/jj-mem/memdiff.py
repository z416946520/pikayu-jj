# -*- coding: utf-8 -*-
"""Page-hash memory differ: find what changes in the renderer when the board does.

usage: python memdiff.py <pid> <phase> [<tag>]
   phase 'hash'  -> write logs\mem_<tag>.npz   (page hashes)
   phase 'diff'  -> compare against that file and dump changed pages
"""
import ctypes
import ctypes.wintypes as wt
import hashlib
import os
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PQ, VR = 0x0400, 0x0010
MEM_COMMIT, MEM_PRIVATE, GUARD, NOACCESS = 0x1000, 0x20000, 0x100, 0x01
PAGE = 64 * 1024
OUT = r"D:\BuildProject\pikayu-jj\logs"

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

def hashes(h):
    addrs, digs = [], []
    for base, size in regions(h):
        off = 0
        while off < size:
            blob = read(h, base + off, min(PAGE, size - off))
            if blob is not None:
                addrs.append(base + off)
                digs.append(hashlib.blake2b(blob, digest_size=8).digest())
            off += PAGE
    return np.array(addrs, dtype=np.uint64), b"".join(digs)

def main():
    if len(sys.argv) < 3:
        print(__doc__); return 2
    pid = int(sys.argv[1]); phase = sys.argv[2]
    tag = sys.argv[3] if len(sys.argv) > 3 else "a"
    path = os.path.join(OUT, "mem_%s" % tag)
    h = k32.OpenProcess(PQ | VR, False, pid)
    if not h:
        print("cannot open", pid); return 1
    addrs, digs = hashes(h)
    print("pid %d: %d pages hashed (%.0f MB scanned)" % (
        pid, len(addrs), sum(r[1] for r in regions(h)) / 1048576.0))
    if phase == "hash":
        np.savez_compressed(path + ".npz", addrs=addrs,
                            digs=np.frombuffer(digs, dtype=np.uint8))
        print("saved", path + ".npz")
        return 0
    old = np.load(path + ".npz")
    o_addrs, o_digs = old["addrs"], old["digs"].tobytes()
    o_map = {int(a): o_digs[i * 8:(i + 1) * 8] for i, a in enumerate(o_addrs)}
    changed = []
    for i, a in enumerate(addrs):
        d = digs[i * 8:(i + 1) * 8]
        if o_map.get(int(a)) != d:
            changed.append(int(a))
    print("changed pages: %d" % len(changed))
    np.savez_compressed(path + "_diff.npz", changed=np.array(changed, dtype=np.uint64))
    dump = []
    for a in changed[:12]:
        before = read(h, a, PAGE)          # current content (after the change)
        dump.append((a, before[:64] if before else b""))
    for a, blob in dump:
        print("  @%s  %s" % (hex(a), blob[:48].hex()))
    return 0

sys.exit(main())
