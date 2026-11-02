# -*- coding: utf-8 -*-
"""Is the DECRYPTED mini-program bundle (wxapkg index with real file names) in
memory anywhere?  That would hand us the app's own JS/wasm."""
import ctypes
import ctypes.wintypes as wt
import json
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PQ, VR = 0x0400, 0x0010
MEM_COMMIT, GUARD, NOACCESS = 0x1000, 0x100, 0x01

NEEDLES = [b"app-service.js", b"app-config.json", b"WAService.js", b"page-frame.html",
           b".wxml", b".wxss", b"__APP__", b"app.js", b"worker.js", b"wasmcode"]

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

def regions(h, min_size=1 << 16):
    addr = 0
    while True:
        mbi = MBI()
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if (mbi.State == MEM_COMMIT and mbi.RegionSize >= min_size
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

for pid in pids():
    h = k32.OpenProcess(PQ | VR, False, pid)
    if not h:
        continue
    found = {}
    for base, size in regions(h):
        blob = read(h, base, min(size, 192 * 1024 * 1024))
        if not blob:
            continue
        for nd in NEEDLES:
            i = blob.find(nd)
            if i >= 0:
                found.setdefault(nd.decode(), []).append((base + i, blob[max(0, i - 40):i + 80]))
    if found:
        print("===== PID %d" % pid)
        for nd, lst in found.items():
            print("   %-18s x%-4d @%s   ctx %s" % (
                nd, len(lst), hex(lst[0][0]),
                re.sub(rb"[^\x20-\x7e]", b".", lst[0][1])[:70].decode()))
    k32.CloseHandle(h)
print("done")
