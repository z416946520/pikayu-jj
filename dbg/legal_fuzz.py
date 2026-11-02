# -*- coding: utf-8 -*-
"""Fuzz the legality gate against Pikafish: every board the gate accepts must be
a board Pikafish accepts, or the engine dies mid-game."""
import sys, random, subprocess, time
sys.path.insert(0, r"D:\BuildProject\pikayu-jj\pikafishjj")
from pikafishjj import board as B

EXE = r"D:\BuildProject\pikayu-jj\pikafish\Pikafish-Windows-x86-64-universal.exe"
BASE = [
    # real positions quoted in the field log (pikafishjj-log(4).txt)
    "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
    "rnbakab1r/9/1c4nc1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR w - - 0 1",
    "4ka1n1/4a4/2n1b3c/pr6p/2b1P1p2/9/P5P1P/2R1C1N2/6cC1/1NBAKAB2 w - - 0 1",
    "4ka1n1/n3a4/4N4/p7p/2RP2p2/9/c5P2/1r2C4/6cC1/2BAKAB2 w - - 0 1",
    "5k3/4R2C1/9/p3n3p/5Np2/9/6P2/1r2C4/4A1c2/2BAK1B2 w - - 0 1",
    "C1bak4/R1R1a4/4b4/2nr3rp/4p1c2/9/P7P/4BN3/9/3AKAB2 w - - 0 1",
    "4k4/R8/3ab4/8p/9/1c4r2/9/9/2nCA4/3K2B2 w - - 0 1",
    "R8/4k4/3ab4/8p/9/1c6r/9/4B4/2nCA4/3K5 w - - 0 1",
    "r8/4k4/3ab4/8p/9/1c6r/9/4B4/2nCA4/3K5 w - - 0 1",
    "1Cbak1b2/R3a4/n8/7rp/3rp1c2/9/P7P/4BN3/9/2RAKAB2 w - - 0 1",
]
BOGUS = [
    ("p8/4k4/3ab4/8p/9/1c6r/9/4B4/2nCA4/3K5 w - - 0 1", "the log's pawn-read"),
    ("A8/4k4/3ab4/8p/9/1c6r/9/4B4/2nCA4/3K5 w - - 0 1", "the log's advisor-read"),
    ("4k4/4a4/9/9/9/9/9/9/9/4K4 w - - 0 1", "generals facing"),
    ("3k5/9/9/9/9/9/9/9/9/3K5 w - - 0 1", "generals facing, adjacent files"),
    ("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1", "generals on the same file"),
    ("4k4/9/9/9/9/9/9/9/9/3K5 w - - 0 1", "generals, black in check by a rook"),
]


def probe(fen):
    p = subprocess.Popen([EXE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    try:
        p.stdin.write("uci\n"); p.stdin.flush(); time.sleep(0.1)
        p.stdin.write("position fen " + fen + "\ngo movetime 10\n"); p.stdin.flush()
        time.sleep(0.25)
        p.stdin.write("quit\n"); p.stdin.flush()
        out = p.communicate(timeout=3)[0]
    except (BrokenPipeError, OSError):
        p.kill(); out = p.communicate()[0]
    return p.returncode == 0


def gate(fen):
    g = B.fen_to_grid(fen)
    side = fen.split()[1] if len(fen.split()) > 1 else "w"
    return B.position_ok(g, side)[0], B.position_ok_any_side(g)[0]


print("== real positions (must be accepted by the gate) ==")
bad = 0
for fen in BASE:
    mine, any_ = gate(fen)
    pk = probe(fen)
    flag = "" if (mine and pk) else "   <-- MISMATCH"
    if not (mine and pk):
        bad += 1
    print("  gate %-5s (any %-5s) pikafish %-5s %s %s" % (mine, any_, pk, fen[:44], flag))
    # the gate found nothing wrong only if it agrees with Pikafish about the move
    B.position_ok(B.fen_to_grid(fen), "w")

print("== the field log's bogus reads (must be rejected) ==")
for fen, label in BOGUS:
    mine, any_ = gate(fen)
    pk = probe(fen)
    flag = "" if (not mine and not pk) else "   <-- check"
    print("  gate %-5s (any %-5s) pikafish %-5s %-28s %s" % (mine, any_, pk, label, flag))

print("== fuzz: single-piece mutations of a real position ==")
random.seed(7)
base = B.fen_to_grid(BASE[0])
cells = [(i, j) for j in range(10) for i in range(9)]
mism = acc = rej = 0
tried = 0
for _ in range(120):
    g = [row[:] for row in base]
    (fi, fj) = random.choice([c for c in cells if g[c[1]][c[0]] != "."])
    (ti, tj) = random.choice([c for c in cells if g[c[1]][c[0]] == "."])
    g[tj][ti] = g[fj][fi]
    g[fj][fi] = "."
    fen = B.grid_to_fen(g, "w")
    mine = B.position_ok(g, "w")[0]
    if not mine:
        rej += 1
        continue
    acc += 1
    tried += 1
    if not probe(fen):
        mism += 1
        print("   gate accepted, pikafish refused: %s" % B.grid_to_fen(g, "w")[:52])
print("  accepted by the gate %d, rejected %d; of the accepted, pikafish refused %d"
      % (acc, rej, mism))
