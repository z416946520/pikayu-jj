# -*- coding: utf-8 -*-
"""Look at the record-like region that followed the board change."""
import ctypes
import ctypes.wintypes as wt
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PQ, VR = 0x0400, 0x0010

k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

PID = int(sys.argv[1]) if len(sys.argv) > 1 else 5604
BASE = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x37401000000
SIZE = int(sys.argv[3]) if len(sys.argv) > 3 else 0x60000

h = k32.OpenProcess(PQ | VR, False, PID)
buf = ctypes.create_string_buffer(SIZE)
got = ctypes.c_size_t(0)
ok = k32.ReadProcessMemory(h, ctypes.c_void_p(BASE), buf, SIZE, ctypes.byref(got))
blob = buf.raw[:got.value]
print("read %d bytes at %s (%s)" % (len(blob), hex(BASE), bool(ok)))
open(r"D:\BuildProject\pikayu-jj\logs\region.bin", "wb").write(blob)

# printable strings >= 6 chars
for m in re.finditer(rb"[\x20-\x7e]{6,}", blob):
    s = m.group().decode()
    if any(k in s.lower() for k in ("fen", "move", "chess", "board", "piece", "game",
                                    "local", "msg", "socket", "http", "room", "match")):
        print("  @+%-8d %s" % (m.start(), s[:110]))
print("--- first 40 records of 20 bytes")
for i in range(0, min(len(blob), 800), 20):
    row = blob[i:i + 20]
    if row == b"\0" * 20:
        continue
    print("  @+%-8d %s" % (i, row.hex(" ")))
