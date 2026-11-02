# -*- coding: utf-8 -*-
"""Locate the board field in the JJ象棋 mini-program and cache the layout.

The live position is not a FEN string and not a plain 90-cell array, so it is
found by a REVERSIBLE differential instead of by guessing the encoding:

    python find_board.py snap a      # with the game showing a position
    (play one move in the game)
    python find_board.py snap b
    (press 悔棋 / undo in the game)
    python find_board.py snap c
    python find_board.py diff a b c  # addresses where a == c != b

Pages that come back to exactly their old content after the undo are the ones
that hold the position: timers, GC metadata and allocator state do not revert.
The tool prints the surviving addresses with the before/after bytes, and the
write-layout subcommand stores a verified one in jj_board_layout.json so
bridge.py can read the board from memory.

Run it while a game is on screen and the mini-program is open.
"""
import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))            # the working directory
sys.path.insert(0, os.path.join(ROOT, "pikafishjj"))     # parent of the package
from pikafishjj import bridge as BR        # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dumps")
PAGE = 64 * 1024
MEM_COMMIT, MEM_PRIVATE, GUARD, NOACCESS = 0x1000, 0x20000, 0x100, 0x01

k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wt.DWORD), ("__a1", wt.DWORD),
                ("RegionSize", ctypes.c_ulonglong), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD), ("__a2", wt.DWORD)]


k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]


def procs():
    """[(pid, working set)] for WeChatAppEx, biggest first."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='WeChatAppEx.exe'\" | "
             "Select-Object ProcessId,WorkingSetSize | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        data = json.loads(out.stdout or "[]")
    except Exception:
        return []
    data = data if isinstance(data, list) else [data]
    return sorted(((d["ProcessId"], d.get("WorkingSetSize") or 0) for d in data),
                  key=lambda t: -t[1])


def app_pid(appid=BR.APPID):
    """The process that carries this mini-program (its appid string is in it)."""
    for pid, _ws in procs():
        blob = BR.read_process_memory(pid, 0x1000000, 4 * 1024 * 1024)
        if blob and appid.encode() in blob:
            return pid
    return None


def regions(pid, min_size=64 * 1024):
    """Committed private ranges of the process: [(base, size)]."""
    import ctypes
    k32.OpenProcess.restype = wt.HANDLE
    h = k32.OpenProcess(0x0410, False, int(pid))
    if not h:
        return []
    out = []
    addr = 0
    mbi = MBI()
    while k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        if (mbi.State == MEM_COMMIT and mbi.RegionSize >= min_size
                and mbi.Type == MEM_PRIVATE and (mbi.Protect & 0xFF) != NOACCESS
                and not (mbi.Protect & GUARD)):
            out.append((mbi.BaseAddress, mbi.RegionSize))
        nxt = mbi.BaseAddress + mbi.RegionSize
        if nxt <= mbi.BaseAddress:
            break
        addr = nxt
    k32.CloseHandle(h)
    return out


def snap(tag, pid=None):
    """Hash every page; keep the bytes of the pages that changed since the last
    snapshot (that is all the diff needs, and it stays small)."""
    pid = pid or app_pid()
    if not pid:
        print("no WeChatAppEx process carries %s - open the mini-program first" % BR.APPID)
        return 1
    os.makedirs(OUT, exist_ok=True)
    prev = None
    for other in ("c", "b", "a"):
        if other != tag and os.path.isfile(os.path.join(OUT, other + ".json")):
            with open(os.path.join(OUT, other + ".json"), "r", encoding="utf-8") as fh:
                cand = json.load(fh)
            if cand.get("pid") == pid:
                prev = cand
                break
    hashes = {}
    changed = {}
    for base, size in regions(pid):
        off = 0
        while off < size:
            blob = BR.read_process_memory(pid, base + off, min(PAGE, size - off))
            if blob:
                addr = base + off
                hashes[str(addr)] = hashlib.blake2b(blob, digest_size=8).hexdigest()
                if prev is not None and prev["hashes"].get(str(addr)) != hashes[str(addr)]:
                    changed[str(addr)] = blob.hex()
            off += PAGE
    path = os.path.join(OUT, tag + ".json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"pid": pid, "hashes": hashes, "changed": changed}, fh)
    print("snap %s: pid %d, %d pages hashed, %d pages changed vs the previous snapshot"
          % (tag, pid, len(hashes), len(changed)))
    print("        saved %s" % path)
    return 0


def load(tag):
    with open(os.path.join(OUT, tag + ".json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def diff(tags=("a", "b", "c"), limit=25):
    """Addresses whose page came back to exactly its old content but changed in
    between: that is the board, not the allocator."""
    a, b, c = (load(t) for t in tags)
    if not (a["pid"] == b["pid"] == c["pid"]):
        print("the three snapshots came from different processes - redo them")
        return 1
    rev = []
    for addr, h in a["hashes"].items():
        if c["hashes"].get(addr) == h and b["hashes"].get(addr) != h:
            rev.append(addr)
    print("reversible pages (a == c != b): %d of %d" % (len(rev), len(a["hashes"])))
    rows = []
    for addr in rev:
        cb = b["changed"].get(addr)
        cc = c["changed"].get(addr)
        if cb and cc:
            before = bytes.fromhex(cc)          # c == a, the restored content
            after = bytes.fromhex(cb)           # b, the changed content
            offs = [i for i in range(min(len(before), len(after))) if before[i] != after[i]]
            if 0 < len(offs) <= 64:
                rows.append((len(offs), addr, before, after, offs))
    rows.sort()
    print("candidates with 1..64 changed bytes: %d" % len(rows))
    for n, addr, before, after, offs in rows[:limit]:
        print("  @%s  %d bytes differ (%s ...)" % (addr, n, offs[:8]))
        for i in offs[:4]:
            lo = max(0, i - 8)
            print("     A %s" % before[lo:i + 12].hex(" "))
            print("     B %s" % after[lo:i + 12].hex(" "))
    return 0


def write_layout(addr, base=None, note=""):
    """Cache a verified address so bridge.py can read the board from memory."""
    lay = {"appid": BR.APPID, "pid": app_pid(), "base": int(addr, 0),
           "stride": 1, "order": "row", "flip_rows": False, "flip_cols": False,
           "empty": 0, "codes": {}, "note": note}
    path = BR.layout_path()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(lay, fh, ensure_ascii=False, indent=2)
    print("wrote %s" % path)
    print("the codes table is still empty: fill it in from a known position before "
          "trusting the reader")
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] == "snap":
        return snap(argv[1])
    if len(argv) >= 1 and argv[0] == "diff":
        return diff(tuple(argv[1:4]) if len(argv) >= 4 else ("a", "b", "c"))
    if len(argv) >= 2 and argv[0] == "write-layout":
        return write_layout(argv[1], note=" ".join(argv[2:]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

