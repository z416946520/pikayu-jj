# -*- coding: utf-8 -*-
"""Which WeChatAppEx process runs the JJ象棋 mini-program, and what app-specific
state strings live in its memory?"""
import ctypes
import ctypes.wintypes as wt
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wt.DWORD), ("__a1", wt.DWORD),
                ("RegionSize", ctypes.c_ulonglong), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD), ("__a2", wt.DWORD)]


k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

APPID = b"wx0c852640e4324692"
PROBES = {
    "appid": [APPID],
    "title-utf8": ["JJ象棋".encode("utf-8"), "jj象棋".encode("utf-8")],
    "ui-utf8": ["再来一局".encode("utf-8"), "悔棋".encode("utf-8"), "认输".encode("utf-8"),
                "将军".encode("utf-8"), "和棋".encode("utf-8"), "超时".encode("utf-8"),
                "棋盘".encode("utf-8"), "棋子".encode("utf-8")],
    "ui-utf16": ["再来一局".encode("utf-16-le"), "悔棋".encode("utf-16-le"),
                 "认输".encode("utf-16-le"), "将军".encode("utf-16-le")],
    "fenlike": [b"rnbakabnr", b"RNBAKABNR", b"1c5c1", b"p1p1p1p1p"],
    "keys": [b'"pieces"', b'"board"', b'"fen"', b'"moveList"', b'"chessboard"',
             b'"qipu"', b'"pieceMap"', b'"boardData"', b'"squares"'],
    "wasm": [b"\x00asm", b"WebAssembly", b"emscripten"],
}


def procs():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process -Filter \"Name='WeChatAppEx.exe'\" | "
                          "Select-Object ProcessId,WorkingSetSize | ConvertTo-Json -Compress"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    data = json.loads(out.stdout or "[]")
    return data if isinstance(data, list) else [data]


def regions(h):
    addr = 0
    while True:
        mbi = MBI()
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        prot = mbi.Protect & 0xFF
        if (mbi.State == MEM_COMMIT and mbi.RegionSize and prot != PAGE_NOACCESS
                and not (mbi.Protect & PAGE_GUARD)):
            yield mbi.BaseAddress, mbi.RegionSize
        nxt = mbi.BaseAddress + mbi.RegionSize
        if nxt <= mbi.BaseAddress:
            break
        addr = nxt


def scan(h, needles, limit=3, cap=96 * 1024 * 1024):
    hits = []
    for base, size in regions(h):
        size = min(size, cap)
        buf = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size, ctypes.byref(read)):
            continue
        blob = buf.raw[:read.value]
        for nd in needles:
            i = blob.find(nd)
            while i >= 0:
                hits.append((base + i, nd))
                if len(hits) >= limit:
                    return hits
                i = blob.find(nd, i + 1)
    return hits


def main():
    rows = []
    for p in procs():
        pid = p["ProcessId"]
        h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not h:
            continue
        if not scan(h, [APPID], limit=1):
            k32.CloseHandle(h)
            continue
        counts = {}
        samples = {}
        for tag, needles in PROBES.items():
            if tag == "appid":
                continue
            hits = scan(h, needles, limit=3)
            counts[tag] = len(hits)
            if hits:
                samples[tag] = "%s@%s" % (hits[0][1].decode("utf-8", "replace")[:12], hex(hits[0][0]))
        rows.append((pid, (p.get("WorkingSetSize") or 0) / 1048576.0, counts, samples))
        k32.CloseHandle(h)
    rows.sort(key=lambda r: -(r[2].get("ui-utf8", 0) + r[2].get("fenlike", 0) + r[2].get("keys", 0)))
    for pid, mb, counts, samples in rows:
        print("PID %-6d %6.1f MB  " % (pid, mb)
              + "  ".join("%s=%d" % (k, v) for k, v in sorted(counts.items()) if v))
        for k, v in samples.items():
            print("        %-9s %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
