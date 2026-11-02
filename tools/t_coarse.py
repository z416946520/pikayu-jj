
# -*- coding: utf-8 -*-
"""Structure-level fallback of recognize(): a stylised skin must come out whole.

The red horse 傌 of the porcelain skin reaches only 0.37 against the template
pack (thick brush) while its own empty squares stay at 0.46, so the sharp pass
has to drop it.  Blurring both sides removes stroke weight and names it, so
recognize() retries such a square low passed.  These three checks pin that down:
the stylised skin reads 32/32, the fallback is what found the two horses, and a
skin the pack already carries is left completely alone.

Run:  python tools\t_coarse.py     (exits non-zero on failure)
"""
import sys
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V

ROOT = r"D:\BuildProject\pikayu-jj"
BAD = []


def read(fixture, fallback=True):
    a = np.asarray(Image.open(ROOT + "\\fixtures\\" + fixture).convert("RGB"))
    cal = V.calibrate(a)
    tpl, half = V.load_templates(cal=cal)
    info = {}
    keep = V._match_coarse
    if not fallback:
        V._match_coarse = lambda *x, **k: None
    try:
        g, sc = V.recognize(a, cal, tpl, half=half, info=info)
    finally:
        V._match_coarse = keep
    return g, info, tpl


def pieces(g):
    return sum(1 for row in g for c in row if c != ".")


g, info, _tpl = read("blue_now.png")
n = pieces(g)
print("blue_now    pieces %d  coarse %s" % (n, info.get("coarse")))
print("            row0 %s" % "".join(g[0]))
if n != 32:
    BAD.append("blue:pieces=%d" % n)
if "".join(g[0]) != "RNBAKABNR":
    BAD.append("blue:row0=" + "".join(g[0]))
if sorted(info.get("coarse") or []) != [(1, 0), (7, 0)]:
    BAD.append("blue:coarse=%s" % (info.get("coarse"),))

g2, _info2, _t2 = read("blue_now.png", fallback=False)
print("blue_now    without the fallback: pieces %d" % pieces(g2))
if pieces(g2) >= n:
    BAD.append("blue:fallback-not-needed")

g3, info3, _t3 = read("jj_orig.png")
print("jj_orig     pieces %d  coarse %s" % (pieces(g3), info3.get("coarse")))
if pieces(g3) != 32:
    BAD.append("jj_orig:pieces=%d" % pieces(g3))
if info3.get("coarse"):
    BAD.append("jj_orig:coarse=%s" % (info3.get("coarse"),))

print("")
if BAD:
    print("COARSE FAILED: %s" % ", ".join(BAD))
    raise SystemExit(1)
print("COARSE OK")
