# -*- coding: utf-8 -*-
"""Locate the JJ象棋 mini-program inside WeChatAppEx without any vision:
which renderer holds the app, and can we see its own state strings?"""
import ctypes
import ctypes.wintypes as wt
import json
import subprocess
import sys

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong),
                ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wt.DWORD),
                ("__alignment1", wt.DWORD),
                ("RegionSize", ctypes.c_ulonglong),
                ("State", wt.DWORD),
                ("Protect", wt.DWORD),
                ("Type", wt.DWORD),
                ("__alignment2", wt.DWORD)]


k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p,
                               ctypes.POINTER(MEMORY_BASIC_INFORMATION64),
                               ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.ReadProcessMemory.restype = wt.BOOL

PATTERNS = {
    "appid": [b"wx0c852640e4324692"],
    "name-utf8": ["jj象棋".encode("utf-8"), "JJ象棋".encode("utf-8")],
    "name-utf16": ["jj象棋".encode("utf-16-le"), "JJ象棋".encode("utf-16-le")],
    "fen-open": [b"rnbakabnr", b"RNBAKABNR", b"1c5c1"],
    "pieces": [b'"pieces"', b'"board"', b'"fen"', b"chessboard", b"pieceMap"],
    "ui-cn": ["再来一局".encode("utf-8"), "悔棋".encode("utf-8"),
              "将军".encode("utf-8"), "认输".encode("utf-8"),
              "和棋".encode("utf-8"), "超时".encode("utf-8")],
    "ui-cn16": ["再来一局".encode("utf-16-le"), "悔棋".encode("utf-16-le"),
                "将军".encode("utf-16-le"), "认输".encode("utf-16-le")],
    "wasm": [b"\x00asm", b"WebAssembly", b"emscripten", b"unity"],
}


def procs():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='WeChatAppEx.exe'\" | "
         "Select-Object ProcessId,WorkingSetSize | ConvertTo-Json -Compress"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    data = json.loads(out.stdout or "[]")
    return data if isinstance(data, list) else [data]


def regions(h):
    addr = 0
    while True:
        mbi = MEMORY_BASIC_INFORMATION64()
        got = k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                 ctypes.sizeof(mbi))
        if not got:
            break
        prot = mbi.Protect & 0xFF
        if (mbi.State == MEM_COMMIT and mbi.RegionSize
                and prot not in (PAGE_NOACCESS,)
                and not (mbi.Protect & PAGE_GUARD)):
            yield mbi.BaseAddress, mbi.RegionSize
        addr = mbi.BaseAddress + mbi.RegionSize
        if addr <= mbi.BaseAddress:
            break


def scan(h, needles, limit=6, max_region=64 * 1024 * 1024):
    """Search committed regions for byte patterns; returns [(addr, pattern)]."""
    hits = []
    for base, size in regions(h):
        if size > max_region:
            size = max_region
        chunk = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(base), chunk, size,
                                     ctypes.byref(read)):
            continue
        blob = chunk.raw[:read.value]
        for needle in needles:
            start = 0
            while True:
                i = blob.find(needle, start)
                if i < 0:
                    break
                hits.append((base + i, needle))
                start = i + 1
                if len(hits) >= limit:
                    return hits
    return hits


def main():
    targets = []
    for p in procs():
        pid = p["ProcessId"]
        h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not h:
            continue
        found = scan(h, PATTERNS["appid"])
        if found:
            targets.append(pid)
            print("=== PID %d holds the appid at %s" % (pid, [hex(a) for a, _ in found]))
        k32.CloseHandle(h)
    if not targets:
        print("no WeChatAppEx process holds the appid string")
        return 1
    for pid in targets:
        h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        print("\n--- PID %d" % pid)
        for tag, needles in PATTERNS.items():
            if tag == "appid":
                continue
            hits = scan(h, needles, limit=4)
            if hits:
                print("  %-10s %3d+ hits, first: %s" % (
                    tag, len(hits),
                    ", ".join("%s@%s" % (n.decode("utf-8", "replace")[:14], hex(a))
                              for a, n in hits[:3])))
        k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
