# -*- coding: utf-8 -*-
"""Known-plaintext hunt: does the renderer keep the CURRENT puzzle position, and
what does the object around it look like?"""
import ctypes
import ctypes.wintypes as wt
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PQ, VR = 0x0400, 0x0010
MEM_COMMIT, MEM_GUARD, NOACCESS = 0x1000, 0x100, 0x01

BOARD = "3k5/6R1C/3c5/6N2/6b2/9/9/9/2r1p1p2/5K3"
NEEDLES = [BOARD.encode(), (BOARD + " w").encode(), b"6R1C", b"2r1p1p2", b"6N2"]

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
        if (mbi.State == MEM_COMMIT and mbi.RegionSize
                and (mbi.Protect & 0xFF) != NOACCESS and not (mbi.Protect & MEM_GUARD)):
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

def clean(b, n=500):
    return re.sub(r"[\x00-\x08\x0b-\x1f]+", "|", b.decode("utf-8", "replace"))[:n]

for pid in pids():
    h = k32.OpenProcess(PQ | VR, False, pid)
    if not h:
        continue
    found = {}
    for base, size in regions(h):
        blob = read(h, base, min(size, 256 * 1024 * 1024))
        if not blob:
            continue
        for nd in NEEDLES:
            i = blob.find(nd)
            if i >= 0:
                found.setdefault(nd.decode(), []).append((base + i, clean(blob[max(0, i-420):i+300])))
    if found:
        print("===== PID %d" % pid)
        for nd, lst in found.items():
            print("  -- %-46s x%d  @%s" % (nd[:46], len(lst), hex(lst[0][0])))
            print("     %s" % lst[0][1])
    k32.CloseHandle(h)
