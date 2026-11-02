# -*- coding: utf-8 -*-
"""pikafishjj.board - grid <-> FEN, move diffing, board orientation."""

OPENING_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"


def new_grid():
    return [["."] * 9 for _ in range(10)]


def clone(grid):
    return [row[:] for row in grid]


def grid_to_fen(grid, side="w", halfmove=0, fullmove=1):
    """internal grid (row 0 = black back rank) -> xiangqi FEN."""
    parts = []
    for j in range(10):
        empty = 0
        s = ""
        for i in range(9):
            c = grid[j][i]
            if c == ".":
                empty += 1
            else:
                if empty:
                    s += str(empty)
                    empty = 0
                s += c
        if empty:
            s += str(empty)
        parts.append(s)
    return "/".join(parts) + " %s - - %d %d" % (side, halfmove, fullmove)


def fen_to_grid(fen):
    g = new_grid()
    rows = fen.split()[0].split("/")
    for j, row in enumerate(rows[:10]):
        i = 0
        for ch in row:
            if ch.isdigit():
                i += int(ch)
            else:
                if i < 9:
                    g[j][i] = ch
                i += 1
    return g


def uci_square(i, j):
    """internal grid coords -> UCI square. rank 0 = red back rank = internal row 9."""
    return chr(ord("a") + i) + str(9 - j)


def parse_uci(sq):
    return ord(sq[0]) - ord("a"), 9 - int(sq[1:])


def detect_flip(grid):
    """Return True if the board is displayed with red at the top."""
    if grid[9][4] == "K":
        return False
    if grid[0][4] == "K":
        return True
    for j in range(10):
        for i in range(9):
            if grid[j][i] == "K":
                return j < 5
    return None


def screen_to_internal(scr, flip):
    """Convert the on-screen 10x9 grid to the canonical internal grid."""
    if not flip:
        return clone(scr)
    g = new_grid()
    for j in range(10):
        for i in range(9):
            g[j][i] = scr[9 - j][8 - i]
    return g


def internal_to_screen(flip, i, j):
    """internal cell -> screen cell."""
    if flip:
        return 8 - i, 9 - j
    return i, j


def diff_moves(old, new):
    """Cells that differ between two internal grids -> list of (from, to, piece).

    Each entry is ((fi, fj), (ti, tj), moving_piece, captured_piece) where the
    moving piece is what stood on the FROM square in *old* and the captured
    piece is what stood on the TO square in *old* ("." for a quiet move).  When
    more than two squares differ the entry is ("?", (i, j), old, new) instead of
    a guess, because a guessed move is worse than an admitted unknown.
    """
    changed = []
    for j in range(10):
        for i in range(9):
            if old[j][i] != new[j][i]:
                changed.append((i, j, old[j][i], new[j][i]))
    if not changed:
        return []
    if len(changed) == 2:
        empt = [c for c in changed if c[3] == "."]
        gain = [c for c in changed if c[3] != "."]
        if len(empt) == 1 and len(gain) == 1:
            e, g = empt[0], gain[0]
            return [((e[0], e[1]), (g[0], g[1]), e[2], g[2])]
        # a piece that changed letter without emptying its square (promotion is
        # impossible in xiangqi, so this means a misread) - report it honestly
        return [("?", (c[0], c[1]), c[2], c[3]) for c in changed]
    return [("?", (c[0], c[1]), c[2], c[3]) for c in changed]


def explain_change(old, new, max_plies=4):
    """Read a multi-cell difference as a series of whole plies, or give up.

    Every ply takes one piece off a square and puts the very same piece (the same
    letter - a piece never changes colour) down on another square: either an
    empty one, or one holding an enemy piece, which is captured and disappears.
    So a board that is a series of whole plies always has as many squares gaining
    a piece as there were plies, every gain can be traced back to a square that
    lost a piece of the same letter, and any square that lost a piece without a
    ply leaving it can only be a square where an enemy piece was captured.

    A piece that simply vanished, two that appeared out of nowhere, a letter that
    changed in place: none of those can be reached by playing, so the frame is
    torn or misread and nothing should be decided from it.

    Returns the plies as ((fi, fj), (ti, tj), moving_piece, captured) tuples
    (empty when both boards are equal), or None when no series of at most
    *max_plies* whole plies accounts for the difference.
    """
    lost = []      # (cell, piece) squares a piece left
    gained = []    # (cell, piece) squares a piece arrived on
    for j in range(10):
        for i in range(9):
            o, n = old[j][i], new[j][i]
            if o == n:
                continue
            if o != ".":
                lost.append(((i, j), o))
            if n != ".":
                gained.append(((i, j), n))
    if not lost and not gained:
        return []
    if not gained or len(gained) > max_plies or len(lost) < len(gained):
        return None
    used = [False] * len(lost)
    plies = []

    def walk(k):
        if k == len(gained):
            return True
        (ti, tj), piece = gained[k]
        for m in range(len(lost)):
            if used[m] or lost[m][1] != piece:
                continue
            used[m] = True
            plies.append((lost[m][0], (ti, tj), piece, old[tj][ti]))
            if walk(k + 1):
                return True
            plies.pop()
            used[m] = False
        return False

    if not walk(0):
        return None
    arrived = set(g[0] for g in gained)
    for m in range(len(lost)):
        # every square that lost a piece is either one a ply left (it fed a gain)
        # or one where an enemy piece was captured in place
        if not used[m] and lost[m][0] not in arrived:
            return None
    plies.sort(key=lambda m: (m[1][1], m[1][0]))
    return plies


def apply_move(grid, mv):
    (fi, fj), (ti, tj), piece = mv[0], mv[1], mv[2]
    if fi == "?" or ti == "?":
        return grid
    g = clone(grid)
    # grids are indexed g[row][col] while squares are (col, row), so the target
    # must be written g[tj][ti].  Writing g[ti][tj] silently teleports the piece
    # to the transposed square and makes every diff against the real board lie.
    g[tj][ti] = piece
    g[fj][fi] = "."
    return g


def move_visible(old, new, fi, fj, ti, tj):
    """True when *new* looks like the piece standing on (fi,fj) went to (ti,tj).

    This is deliberately weaker than diff_moves: it only asks whether our own ply
    is on the board, so a frame that also carries later changes (or that repairs an
    earlier misread somewhere else) still counts as "the click landed".
    """
    if old[fj][fi] == ".":
        return False
    if new[fj][fi] != ".":
        return False
    return new[tj][ti] != "."


def side_of(piece):
    return "w" if piece.isupper() else "b"


def find_king(grid, upper=True):
    target = "K" if upper else "k"
    for j in range(10):
        for i in range(9):
            if grid[j][i] == target:
                return i, j
    return None


# Xiangqi has no promotion, so these are hard per-side limits.  They catch the
# characteristic recognition failure of inventing a third cannon or a sixth pawn.
MAX_COUNT = {"R": 2, "N": 2, "B": 2, "A": 2, "C": 2, "P": 5, "K": 1}


def counts_ok(grid):
    """True when no side has more of a piece type than the rules allow."""
    n = {}
    for j in range(10):
        for i in range(9):
            c = grid[j][i]
            if c != ".":
                n[c] = n.get(c, 0) + 1
    for c, k in n.items():
        lim = MAX_COUNT.get(c.upper())
        if lim is None or k > lim:
            return False
    return n.get("K", 0) == 1 and n.get("k", 0) == 1


def is_opening(grid):
    return grid == fen_to_grid(OPENING_FEN)


# -- is this a position the rules can reach? --------------------------------
# The reader can misread a square, and a position the rules cannot reach kills
# the engine: Pikafish answers an impossible board with "CRITICAL ERROR: ...
# Unsupported position" and exits, so the run loses the engine and - before this
# check existed - the move loop on top of it.  The point sets below are the ones
# the pieces can actually be on (they were verified against Pikafish itself:
# advisor points are the palace X, elephant points the seven squares reachable
# from c1/g1, and a pawn still on its own half has never moved sideways, so it
# can only be on a start file).
ADVISOR_PTS = {(3, 9), (5, 9), (4, 8), (3, 7), (5, 7)}          # red
ADVISOR_PTS_B = {(3, 0), (5, 0), (4, 1), (3, 2), (5, 2)}        # black
ELEPHANT_PTS = {(2, 9), (6, 9), (0, 7), (4, 7), (8, 7), (2, 5), (6, 5)}
ELEPHANT_PTS_B = {(2, 0), (6, 0), (0, 2), (4, 2), (8, 2), (2, 4), (6, 4)}
PALACE_ROWS = (3, 4, 5)
PAWN_FILES = (0, 2, 4, 6, 8)     # both sides' pawns start on a, c, e, g, i

def _in_palace(i, j, upper):
    return (3 <= i <= 5) and (7 <= j <= 9 if upper else 0 <= j <= 2)


PIECE_CN = {"K": "帥", "k": "將", "A": "仕", "a": "士", "B": "相", "b": "象",
            "R": "俥", "r": "車", "N": "傌", "n": "馬", "C": "炮", "c": "砲",
            "P": "兵", "p": "卒"}


def _where(i, j):
    return "%s%d" % (chr(ord("a") + i), 9 - j)


def _placement_bad(grid):
    """Reason the piece placement is impossible, or None."""
    for j in range(10):
        for i in range(9):
            c = grid[j][i]
            if c == ".":
                continue
            if c in "KA" and not _in_palace(i, j, True):
                return "%s outside its palace at %s" % (PIECE_CN[c], _where(i, j))
            if c in "ka" and not _in_palace(i, j, False):
                return "%s outside its palace at %s" % (PIECE_CN[c], _where(i, j))
            if c == "A" and (i, j) not in ADVISOR_PTS:
                return "red advisor off its points at %s" % _where(i, j)
            if c == "a" and (i, j) not in ADVISOR_PTS_B:
                return "black advisor off its points at %s" % _where(i, j)
            if c == "B" and (i, j) not in ELEPHANT_PTS:
                return "red elephant off its points at %s" % _where(i, j)
            if c == "b" and (i, j) not in ELEPHANT_PTS_B:
                return "black elephant off its points at %s" % _where(i, j)
            if c == "P":
                if j > 6:
                    return "red pawn behind its start at %s" % _where(i, j)
                if j >= 5 and i not in PAWN_FILES:
                    return "red pawn off a start file at %s" % _where(i, j)
            if c == "p":
                if j < 3:
                    return "black pawn behind its start at %s" % _where(i, j)
                if j <= 4 and i not in PAWN_FILES:
                    return "black pawn off a start file at %s" % _where(i, j)
    return None


def _king_attack(grid, i, j, by_red):
    """True when a red/black piece attacks square (i, j).

    Only the pieces that can ever reach an enemy general are generated: rooks and
    kings along a file (the flying-general rule), cannons over exactly one
    screen, knights with their leg, and pawns one step forward (sideways once
    they are across the river).
    """
    def at(x, y):
        if 0 <= x < 9 and 0 <= y < 10:
            return grid[y][x]
        return "#"

    # rook and the enemy general (the two generals attack each other down a file)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        x, y = i + dx, j + dy
        while True:
            c = at(x, y)
            if c == "#":
                break
            if c != ".":
                if (by_red and c in "RK") or (not by_red and c in "rk"):
                    return True
                break
            x, y = x + dx, y + dy
    # cannon: the first piece found is the screen, the next one has to be one
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        x, y = i + dx, j + dy
        screen = False
        while True:
            c = at(x, y)
            if c == "#":
                break
            if c != ".":
                if not screen:
                    screen = True
                else:
                    if (by_red and c == "C") or (not by_red and c == "c"):
                        return True
                    break
            x, y = x + dx, y + dy
    # knight: the target square sits 2-and-1 away, and the leg beside the knight
    # (not beside the target) has to be empty
    want = "N" if by_red else "n"
    for dx, dy in ((1, 2), (-1, 2), (1, -2), (-1, -2), (2, 1), (2, -1), (-2, 1), (-2, -1)):
        kx, ky = i + dx, j + dy
        if at(kx, ky) != want:
            continue
        if abs(dx) == 1:
            lx, ly = kx, ky - (1 if dy > 0 else -1)
        else:
            lx, ly = kx - (1 if dx > 0 else -1), ky
        if at(lx, ly) == ".":
            return True
    # pawn: red pawns move up the board (row - 1), black ones down; a pawn may
    # also strike sideways once it is across the river
    if by_red:
        if at(i, j + 1) == "P":
            return True
        if j <= 4 and (at(i - 1, j) == "P" or at(i + 1, j) == "P"):
            return True
    else:
        if at(i, j - 1) == "p":
            return True
        if j >= 5 and (at(i - 1, j) == "p" or at(i + 1, j) == "p"):
            return True
    return False


def _idle_general(grid, side):
    """(i, j) of the general of the side NOT to move."""
    idle = "k" if side == "w" else "K"
    for j in range(10):
        for i in range(9):
            if grid[j][i] == idle:
                return i, j
    return None


def position_ok(grid, side="w"):
    """(ok, reason) - can this board be a real position with *side* to move?

    The placings are checked against the rules and the side NOT to move must not
    be in check (that is where the flying generals, a rook on an open file and a
    knight that just "landed" on the general all show up).  A misread square is
    caught by one of these far more often than not, and catching it here keeps an
    impossible position from ever reaching the engine.
    """
    if grid is None:
        return False, "no board"
    if not counts_ok(grid):
        return False, "piece counts are off"
    bad = _placement_bad(grid)
    if bad:
        return False, bad
    pos = _idle_general(grid, side)
    if pos is None:
        return False, "the %s general is missing" % ("black" if side == "w" else "red")
    if _king_attack(grid, pos[0], pos[1], by_red=(side == "w")):
        return False, "the side not to move is in check (%s general at %s)" % (
            "black" if side == "w" else "red", _where(pos[0], pos[1]))
    return True, ""


def turned(grid):
    """The same board drawn the other way round (180 degrees).

    Ranked play swaps the colours between rounds, so the frame that follows our
    own 再来一局 arrives rotated: the reader still holds the finished round's
    orientation, and the position it produces is the new one turned.  The rules
    cannot tell the two apart as *managements* of a real position, so the read
    gate below accepts either - the round proper re-derives the orientation.
    """
    return [[grid[9 - j][8 - i] for i in range(9)] for j in range(10)]


def position_ok_any_side(grid):
    """(ok, reason) - a real position for whichever side happens to be to move.

    Reading a frame does not say whose turn it is, so a board is accepted when it
    is legal for at least one of the two: a placing that breaks the rules fails
    for both, and two generals that face each other leave both kings attacked.
    """
    if grid is None:
        return False, "no board"
    if not counts_ok(grid):
        return False, "piece counts are off"
    bad = _placement_bad(grid)
    if bad:
        return False, bad
    rk = find_king(grid, True)
    bk = find_king(grid, False)
    if rk is None or bk is None:
        return False, "a general is missing"
    # red may move when black's general is not under attack, and the other way round
    if not _king_attack(grid, bk[0], bk[1], by_red=True):
        return True, ""
    if not _king_attack(grid, rk[0], rk[1], by_red=False):
        return True, ""
    return False, "both generals are attacked (do they face each other?)"


def position_ok_read(grid):
    """(ok, reason) - a real position, read either way round.

    This is the gate for a *reading*: it may hold the last round's orientation, so
    a board that is only legal when turned is still a real board.  The stricter
    position_ok is the gate for a *move* - what is sent to the engine has to be
    legal exactly as it stands.
    """
    ok, why = position_ok_any_side(grid)
    if ok:
        return True, ""
    ok2, _why2 = position_ok_any_side(turned(grid))
    if ok2:
        return True, ""
    return False, why
