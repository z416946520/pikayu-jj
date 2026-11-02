# -*- coding: utf-8 -*-
"""Reconnaissance of the WeChat mini-program package container (wxapkg)."""
import os
import struct

BASE = r"C:\Users\CARSER\AppData\Roaming\Tencent\xwechat\radium\users\8252c3d661a54b6213b8f4717c6ffa7e\applet\packages\wx0c852640e4324692\151"
PKGS = ["__WITHOUT_MULTI_PLUGINCODE__.wxapkg", "_data-package_.wxapkg",
        "_wasmcode_.wxapkg", "_wasmcode1_.wxapkg"]


def head(path, n=32):
    with open(path, "rb") as fh:
        return fh.read(n)


for name in PKGS:
    p = os.path.join(BASE, name)
    if not os.path.isfile(p):
        print("%-34s missing" % name)
        continue
    h = head(p)
    print("%-34s %10d bytes  head=%s" % (name, os.path.getsize(p), h[:16].hex()))
    if h[0] == 0xBE:
        info1, idx_len, body_len = struct.unpack(">III", h[1:13])
        print("    wxapkg v1: info1=%d index_len=%d body_len=%d last=%02x" % (
            info1, idx_len, body_len, h[13]))
        # walk the file index
        off = 14
        n = 0
        names = []
        while off < 14 + idx_len - 4:
            (nlen,) = struct.unpack(">I", open(p, "rb").read(0) or b"\0\0\0\0") if False else (0,)
            with open(p, "rb") as fh:
                fh.seek(off)
                raw = fh.read(4)
                if len(raw) < 4:
                    break
                (nlen,) = struct.unpack(">I", raw)
                if nlen <= 0 or nlen > 512:
                    break
                nm = fh.read(nlen).decode("utf-8", "replace")
                raw = fh.read(8)
                if len(raw) < 8:
                    break
                o, sz = struct.unpack(">II", raw)
            names.append((nm, o, sz))
            off += 4 + nlen + 8
            n += 1
            if n > 4000:
                break
        print("    %d entries; first 25:" % len(names))
        for nm, o, sz in names[:25]:
            print("       %8d  %s" % (sz, nm))
    else:
        print("    not a v1 wxapkg header (first byte %02x)" % h[0])
