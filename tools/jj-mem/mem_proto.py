# -*- coding: utf-8 -*-
"""Escaped protocol names (the mini-program's own message catalog) and any other
game-state strings in the JJ象棋 renderer heap."""
import ctypes
import ctypes.wintypes as wt
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PQ, VR = 0x0400, 0x0010
MEM_COMMIT, MEM_PRIVATE, PAGE_GUARD, PAGE_NOACCESS = 0x1000, 0x20000, 0x100, 0x01
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 5604
NAME = re.compile(rb'\\"name\\":\\"([a-z_0-9]{3,40})\\"')
PLAIN = re.compile(rb'"name":"([a-z_0-9]{3,40})"')

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

names, plain = {}, {}
for base, size in regions(h := k32.OpenProcess(PQ | VR, False, PID)):
    blob = read(h, base, min(size, 256 * 1024 * 1024))
    if not blob:
        continue
    for m in NAME.finditer(blob):
        names[m.group(1).decode()] = names.get(m.group(1).decode(), 0) + 1
    for m in PLAIN.finditer(blob):
        plain[m.group(1).decode()] = plain.get(m.group(1).decode(), 0) + 1
print("== escaped \\\"name\\\": catalog (%d distinct) ==" % len(names))
for nm, c in sorted(names.items(), key=lambda kv: -kv[1])[:60]:
    print("   %-38s x%d" % (nm, c))
print("\n== plain \"name\": (%d distinct) ==" % len(plain))
for nm, c in sorted(plain.items(), key=lambda kv: -kv[1])[:25]:
    print("   %-38s x%d" % (nm, c))
