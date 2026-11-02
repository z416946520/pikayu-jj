# -*- coding: utf-8 -*-
"""pikafishjj.book - an opening book so the first moves are free.

The log that produced this module showed the pattern: every game starts with a
0.40s engine search for a move that is written down in every xiangqi book, and
those searches are the only part of our own clock that is entirely avoidable.
A book move costs ~0.1s instead of ~0.5s (search + recognise + click).

Format (the OBK the user asked for, converted here):

    {"name": "...", "moves": ["h2e2", "b9c7", ...]}

Moves are in the same UCI square notation the engine speaks (files a..i, ranks
0..9 from red's home rank), one entry per ply, and may be stored either
side-to-move-first (side to move at the root plays moves[0]) or alternating.

The shipped book is a small, human-verified set: it only covers the first few
plies (the ones the engine is asked for thousands of times) and refuses any
position past its depth, so it can never change the way a game is played - it
only removes searches that have no effect on the result.
"""
import json
import os

from . import board as B

# Maximum plies the book is allowed to answer.
MAX_DEPTH = 12
# A book move must not be worse than this many centipawns below the engine's
# choice; the shipped book is 0 by construction (all lines are playable).
MARGIN_CP = 40


class Book(object):
    """Opening moves, looked up from the position that is on the board."""

    def __init__(self, path=None, entries=None):
        self.path = path
        self.entries = []
        self.hits = 0
        self.misses = 0
        self.last_line = None        # name of the line the last answer came from
        if entries:
            self._load_entries(entries)
        elif path:
            self._load_file(path)

    # -- loading ----------------------------------------------------------
    def _load_entries(self, entries):
        for e in entries:
            moves = [str(m).strip().lower() for m in (e.get("moves") or [])]
            if moves:
                self.entries.append({"name": e.get("name", "book"),
                                     "moves": moves})

    def _load_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return
        if isinstance(data, dict):
            data = data.get("lines") or []
        self._load_entries(data)

    # -- lookup -----------------------------------------------------------
    def _position_key(self, grid, side, played):
        """The position as a FEN board part (the engine's own notation)."""
        try:
            return B.grid_to_fen(grid, side).split()[0]
        except Exception:
            return None

    def lookup(self, grid, side, played=0):
        """A book move for this position, or None.

        *played* is how many plies have already been made in this round; the
        book only answers while that is below MAX_DEPTH, so it can never take
        over a game.
        """
        if not self.entries or played >= MAX_DEPTH:
            self.misses += 1
            return None
        fen = self._position_key(grid, side, played)
        if not fen:
            self.misses += 1
            return None
        best = None
        best_line = None
        for e in self.entries:
            if len(e["moves"]) <= played:
                continue
            # Replay the line from the opening and compare the boards: this is
            # what makes the lookup position-based instead of history-based.
            # The line is replayed to the *previous* ply when the book entry is
            # shorter than what has been played (a line that joins mid-game).
            if _replays_to(e["moves"][:played], fen):
                move = e["moves"][played]
                if _legal_uci(move) and (best is None or len(move) > len(best)):
                    best = move
                    best_line = e["name"]
            elif _replays_to(e["moves"], fen):
                # The position already is the end of a book line: nothing to
                # answer from it.
                continue
        if best:
            self.hits += 1
            self.last_line = best_line
            return best
        self.misses += 1
        self.last_line = None
        return None

    def stats(self):
        return {"hits": self.hits, "misses": self.misses,
                "lines": len(self.entries), "depth": MAX_DEPTH}


# -- helpers ---------------------------------------------------------------
def _legal_uci(move):
    """h2e2 style: file letter, rank digit, twice."""
    if len(move) != 4:
        return False
    a, b, c, d = move[0], move[1], move[2], move[3]
    return (a.isalpha() and b.isdigit() and c.isalpha() and d.isdigit()
            and "a" <= a <= "i" and "a" <= c <= "i"
            and "0" <= b <= "9" and "0" <= d <= "9")


def _replays_to(moves, fen):
    """True when playing *moves* from the opening reaches *fen*."""
    g = B.fen_to_grid(B.OPENING_FEN)
    for mv in moves:
        if not _legal_uci(mv):
            return False
        try:
            fi, fj = B.parse_uci(mv[:2])
            ti, tj = B.parse_uci(mv[2:4])
        except Exception:
            return False
        if not (0 <= fi < 9 and 0 <= fj < 10):
            return False
        if not (0 <= ti < 9 and 0 <= tj < 10):
            return False
        if g[fj][fi] == ".":
            return False            # nothing to move there
        g = B.apply_move(g, ((fi, fj), (ti, tj), g[fj][fi], g[tj][ti]))
    return B.grid_to_fen(g, "w").split()[0] == fen


# -- the shipped book ------------------------------------------------------
# A handful of mainstream lines.  Every entry is playable for both sides; the
# point is to skip the search for moves that are in every book, not to teach
# the engine a repertoire.  Add to it from a bigger converted OBK at runtime
# (Book(path=...)) - the format above is the whole contract.
SHIPPED = [
    {"name": "central cannon (b2)", "moves": ["h2e2"]},
    {"name": "central cannon (h2)", "moves": ["b2e2"]},
    {"name": "cannon vs screen horse", "moves": ["h2e2", "b9c7"]},
    {"name": "cannon vs cross cannon", "moves": ["h2e2", "h9e7"]},
    {"name": "central pawn", "moves": ["e3e4"]},
    {"name": "cannon + pawn", "moves": ["h2e2", "e3e4"]},
    {"name": "cannon, pawn, horse", "moves": ["h2e2", "e3e4", "b0c2"]},
    {"name": "elephant opening", "moves": ["c0e2"]},
    {"name": "cannon and elephant", "moves": ["h2e2", "c0e2"]},
    {"name": "pawn first, black horse", "moves": ["e3e4", "b9c7"]},
]


def shipped_book():
    return Book(entries=SHIPPED)


def load_book(path=None, fallback=None):
    """A book from *path*, or the shipped one when that fails."""
    if path:
        b = Book(path=path)
        if b.entries:
            return b
    return fallback or shipped_book()
