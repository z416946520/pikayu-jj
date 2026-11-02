# -*- coding: utf-8 -*-
"""Find the renderer that hosts the current screen (残局第1关) and dump the state
objects around its own UI strings."""
import ctypes
import ctypes.wintypes as wt
import json
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PQ, VR = 0x0400, 0x0010
MEM_COMMIT, MEM_PRIVATE, PAGE_GUARD, PAGE_NOACCESS = 0x1000, 0x20000, 0x100, 0x01

MARKERS = ["步数".encode("utf-8"), "锦囊".encode("utf-8"), "求助".encode("utf-8"),
           "重来".encode("utf-8"), "第".encode("utf-8"), "关卡".encode("utf-8"),
           "残局".encode("utf-8"), "闯关".encode("utf-8")]

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

def clean(b, n=420):
    return re.sub(r"[\x00-\x08\x0b-\x1f]+", "|", b.decode("utf-8", "replace"))[:n]

hits = {}
for pid in pids():
    h = k32.OpenProcess(PQ | VR, False, pid)
    if not h:
        continue
    for base, size in regions(h):
        blob = read(h, base, min(size, 256 * 1024 * 1024))
        if not blob:
            continue
        for mk in MARKERS:
            i = blob.find(mk)
            if i >= 0:
                hits.setdefault(mk.decode(), []).append((pid, base + i, clean(blob[max(0, i-260):i+420])))
    k32.CloseHandle(h)
for mk, lst in hits.items():
    print("\n===== %s : %d hits" % (mk, len(lst)))
    seen = set()
    for pid, addr, ctx in lst[:3]:
        if ctx[:60] in seen:
            continue
        seen.add(ctx[:60])
        print("  pid %-6d @%s  %s" % (pid, hex(addr), ctx))
