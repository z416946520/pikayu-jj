
# -*- coding: utf-8 -*-
"""Calibration fuzz: no frame may ever make calibrate() raise.

The user-visible failure was an IndexError escaping calibrate() while the game
sat on a transition screen, so every retry printed an error and the preview kept
the old board.  This walks a set of awkward frames - menu, result screen, crops,
resizes, flips, flat colours, noise - and checks that calibrate() always returns
(possibly without a board), never throws.

Run:  python tools\t_cal_fuzz.py
"""
import sys, time
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
import numpy as np
from PIL import Image
from pikafishjj import vision as V

ROOT = r"D:\BuildProject\pikayu-jj"
FIX = ["jj_orig.png", "lobby_now.png", "live_check.png", "user_shot.png",
       "skin_now.png", "live_probe.png", "skin2_now.png", "live10.png"]
BAD = []


def frames():
    for name in FIX:
        try:
            a = np.asarray(Image.open(ROOT + "\\fixtures\\" + name).convert("RGB"))
        except Exception as exc:
            print("skip %-18s %s" % (name, exc))
            continue
        yield name, a
        h, w = a.shape[:2]
        yield name + " top", a[:h // 2]
        yield name + " left", a[:, :w // 2]
        yield name + " corner", a[:300, :300]
        yield name + " small", np.asarray(Image.fromarray(a).resize((w // 2, h // 2)))
        yield name + " wide", np.asarray(Image.fromarray(a).resize((w, int(h * 0.6))))
        yield name + " mirror", a[:, ::-1]
        yield name + " dark", (a * 0.35).astype(np.uint8)
        yield name + " bright", np.clip(a.astype(np.int16) + 60, 0, 255).astype(np.uint8)
    rng = np.random.default_rng(7)
    yield "noise", rng.integers(0, 256, (1121, 601, 3), dtype=np.uint8)
    yield "flat gray", np.full((1121, 601, 3), 128, np.uint8)
    yield "black", np.zeros((1121, 601, 3), np.uint8)
    yield "white", np.full((1121, 601, 3), 255, np.uint8)
    g = np.linspace(0, 255, 1121, dtype=np.uint8)[:, None, None] * np.ones((1, 601, 3), np.uint8)
    yield "gradient", g


n = 0
boards = 0
t_all = time.perf_counter()
for tag, a in frames():
    n += 1
    t0 = time.perf_counter()
    try:
        cal = V.calibrate(a, verbose=False)
    except Exception as exc:
        print("%-24s CRASHED %s: %s" % (tag, type(exc).__name__, exc))
        BAD.append(tag + ":" + type(exc).__name__)
        continue
    dt = time.perf_counter() - t0
    m = None if cal is None else cal.get("model")
    if m:
        boards += 1
    print("%-24s %-7s %.2fs %s" % (tag, "board" if m else "none", dt,
          "" if cal is None else "discs %s used %s" % (cal.get("ndiscs"), cal.get("ndiscs_used"))))
print("")
print("%d frames, %d with a fitted board, %.1fs total" % (n, boards, time.perf_counter() - t_all))
if BAD:
    print("CALFUZZ FAILED: %s" % ", ".join(BAD))
    raise SystemExit(1)
print("CALFUZZ OK")
