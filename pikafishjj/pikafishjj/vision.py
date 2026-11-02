# -*- coding: utf-8 -*-
"""pikafishjj.vision - board calibration and piece recognition for JJ Xiangqi.

Coordinate convention used everywhere in this project:
    i = column index 0..8  (left -> right on screen, file a..i)
    j = row index    0..9  (top -> bottom on screen)
    (i, j) = (0, 0) is the TOP-LEFT intersection = black left chariot in the
    standard opening position (black plays from the top).

The rendered pieces are 3-D sprites standing slightly ABOVE their
intersection, and that offset shrinks towards the bottom of the board, so the
sprite grid has a larger vertical pitch than the drawn line grid.  Calibration
therefore uses the line grid to seed disc detection and then fits a bilinear
sprite grid, which is what recognition and clicking must use.
"""
import os
import sys

import numpy as np

# Board skins can be swapped in the mini program, and the default colour test is
# skin specific.  These drive the colour-independent fallback that finds the grid
# lines by local contrast (see line_mask); measured thresholds on the wooden skin
# and on the grey-green stone skin are quoted in the module notes.
LINE_RAD = 15          # neighbourhood radius of the local-contrast filter
LINE_CONTRAST = 20.0   # a line pixel is this much darker than its neighbourhood
LINE_COL_FRAC = 0.22   # a grid line covers >= 22% of the frame height
LINE_ROW_FRAC = 0.55   # >= 55% of a 13px strip between two lines lies on it
BOARD_CY = 0.522       # board centre as a fraction of the client height
TPL_HALF = 23


PADV = 60

# --- disc detection -------------------------------------------------------
# The app paints a bright glow/halo around the piece that moved last. The halo
# sits OUTSIDE the 25px disc, so any metric that samples an annulus around the
# disc (mean(r<=18) - mean(28<=r<=37)) collapses on exactly the squares that
# matter most. Everything below therefore measures the INSIDE of the disc only:
# cream disc pixels have sum(RGB) 592..635 while board wood is 448..466, so
# S > 545 separates them cleanly.
BOX_HALF = 16      # half width of the inner sampling box (33x33, well inside r=25)
LOC_WIN = 16       # +- search window around the seeded centre
# A healthy fit sits 12..13px off the grid lines by construction (the sprites are
# painted above the intersections), so this gate only has to catch absurd fits -
# the disc search radius below is 16px, which bounds how far a fit can legally go.
MAX_MODEL_DEV = 22.0
# The sprite model is fitted as a *delta* off the lattice, so a disc blob that
# lands far from the lattice point it was assigned to is not evidence about the
# sprite offset - it is scenery.  A busy frame offers plenty of those: on the
# 601x1121 result screen the disc search returns 43 blobs for 27 pieces (status
# bar, banner text) and 26 of them sit 16..38px off the lines, which used to drag
# the model a third of a cell sideways and lose four real pieces.  Blobs outside
# this radius are dropped before the fit; if that leaves too few, the fit keeps
# them all and the gates below still have the last word.
FIT_NEAR_FRAC = 0.30
# ... but only for the lattices that the painted grid lines themselves vouch for
# (colour test, thin lines).  The comb and piece lattices are inferred *from* the
# blobs, so on a menu screen with a decorative board any garbage aligns with
# them; dropping the blobs that disagree would let that garbage fit (measured:
# the lobby's comb lattice fits 12 of its 42 blobs at dev 14px and would report
# a two-piece board).  Those lattices keep the strict fit, where a junk lattice
# ends up far enough off to fail the gates below.
NEAR_FIT_KINDS = (-1, 0, 1)
# The painted disc sprites sit on a slightly different lattice than the grid
# lines: measured over the 598x1119 client area the sprite pitch is -0.98% of the
# column pitch and +2.05% of the row pitch.  These priors carry a board with too
# few pieces to observe the pitch at all; enough discs overrule them.
SPRITE_KX = -0.0098
SPRITE_KY = 0.0205


# The least-squares grid model still lands a few pixels off the painted disc on
# some squares (the sprite rows are not perfectly linear in the render).  The
# glyph correlation is brutally sharp, so a 4px shift drops a true match from
# 0.87 to 0.37 - well below the wrong-class picks.  Every cell is therefore
# matched with a small translational search, which costs one matmul per cell.
MATCH_RAD = 8      # the fitted centre can be ~5px off a real disc, so search wide
INCR_MAX_CELLS = 20     # squares the incremental matcher will redo before falling back
CHG_TOL = 8             # per-pixel change that makes a square stale
CELL_SIG_HALF = 16      # half size of the square patch used for that test
WIDE_RAD = 16      # last-chance radius: some skins land the fit 10px off the sprite
FIT_GOOD_RESID = 4.5    # a sprite model this tight is trusted over a richer one
FIT_MIN_DISCS = 8       # a usable fit needs at least this many discs behind it
FIT_OK_RESID = 6.5      # ... and this is where a fit stops being comparable
FIT_REJECT_RESID = 12.0  # p80 of the disc residuals; above this the lattice is wrong

HINT_RAD = 3       # +- search once a square's offset is known
HINT_OK = 0.75     # a hinted match this good is not worth a wide re-search

# --- adaptive piece detection (skin independent) ---------------------------
SAMPLE_FRAC = 0.35   # permissive cut: floor + this much of the (top - floor) range
OCC_GAP_MIN = 18.0   # a board whose cells span less than this shows no pieces
NCC_MIN_OCC = 0.45   # a real piece always matches the pack this well
OCC_MAX_CAND = 34    # never run the matcher on more squares than a full board
COARSE_BLUR = 5      # box width of the structure-level (low pass) match
COARSE_MIN = 0.50    # a blurred match this good is a glyph, not board paint
COARSE_MARGIN = 0.02  # ... and this far ahead of the next best class
COARSE_GAIN = 0.08   # ... and this much better than the sharp match managed
COARSE_RAD = 3       # offsets tried around the sharp match's best offset
TILE_BAND = (0.28, 0.78, 0.04, 0.96)   # rows/cols of the frame used to guess tiles

# --- colour: the side a glyph belongs to -----------------------------------
# The disc artwork carries a red rim ring on BOTH sides (measured on the shipped
# skin: the ring's R-B is around +70 while the glyph ink reads +104 on a red
# piece and +7 on a black one), so the side can only be read from the glyph ink
# itself: pixels clearly darker than the face of the disc, sampled inside a
# radius that keeps the ring and the drop shadow out.
INK_RED_MIN = 40.0     # median ink (R-B) above this: red ink
INK_DARK_MAX = 25.0    # ... below this: dark (black) ink
INK_MIN_PIX = 12       # fewer ink pixels than this: no opinion
INK_DARK_FRAC = 0.55   # ink is this much darker than the patch's median
INK_SAMPLE_R = 0.62    # ink sample radius, as a fraction of the patch half
SIDE_CHECK = 0.70      # hinted/wide scores below this get the colour check

# --- the lifted piece ------------------------------------------------------
# The app draws the piece it is highlighting lifted and enlarged (measured on
# the corner rook of a timed-out board: 22px above its intersection, 1.2x the
# usual disc, over the background behind the board).  Such a piece is outside
# the sharp and wide offset windows AND below every template's scale, so it gets
# one last look: the disc is located by the tile-distance map, the templates are
# tried at a few scales, and only the side the ink proves is allowed to answer.
FAR_SCALES = (1.0, 1.15, 1.30)
FAR_RAD = 7          # +- offsets (in the resampled window) around the disc centre
FAR_STEP = 2
FAR_MIN = 0.50       # a far match this good may name a piece
FAR_MARGIN = 0.08    # ... and must lead its own class by this much
DISC_WIN = 32        # the disc is looked for this far around the model centre
DISC_BOX = 16        # box half of the tile-distance mean used to find it


TPL_PACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates.npz")


def find_templates():
    """Locate templates.npz; a one-file build ships it inside the archive."""
    cands = [TPL_PACK]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        cands.append(os.path.join(bundle, "pikafishjj", "templates.npz"))
        cands.append(os.path.join(bundle, "templates.npz"))
    if getattr(sys, "frozen", False):
        cands.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                                  "templates.npz"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return TPL_PACK


def luminance(a):
    """HxWx3 array -> int32 luminance (int32; int16 overflows to negatives)."""
    a = a.astype(np.int32, copy=False)
    return (a[:, :, 0] * 299 + a[:, :, 1] * 587 + a[:, :, 2] * 114) // 1000


def _longest_run(frac, th):
    best = (0, 0, 0)
    cur = None
    for k in range(len(frac)):
        if frac[k] > th:
            if cur is None:
                cur = k
        elif cur is not None:
            if k - cur > best[0]:
                best = (k - cur, cur, k - 1)
            cur = None
    if cur is not None and len(frac) - cur > best[0]:
        best = (len(frac) - cur, cur, len(frac) - 1)
    return best


def _groups(profile, th, maxgap=6):
    idx = np.nonzero(profile >= th)[0]
    out = []
    for k in idx:
        if out and k - out[-1][-1] <= maxgap:
            out[-1].append(int(k))
        else:
            out.append([int(k)])
    return out


def _fit_progression(cands, n, pitch, center, os_step=0.5):
    """Fit n evenly spaced lines; center disambiguates the phase. Vectorised."""
    if not cands or pitch <= 1:
        return None
    c = np.asarray(sorted(cands), dtype=np.float64)
    offs = np.arange(min(cands) - pitch * 2.0, min(cands) + pitch * 2.0, os_step)
    idx = np.arange(n, dtype=np.float64)
    best = None
    for pp in np.arange(pitch * 0.90, pitch * 1.10, 0.02):
        allines = offs[:, None] + pp * idx[None, :]
        keep = np.abs((allines[:, 0] + allines[:, -1]) / 2.0 - center) <= 0.35 * pp
        if not keep.any():
            continue
        lines = allines[keep]
        ouse = offs[keep]
        d = np.abs(lines[:, :, None] - c[None, None, :])
        dmin = d.min(axis=2)
        used = (dmin < 9.0).sum(axis=1)
        ok = used >= n - 3
        if not ok.any():
            continue
        err = np.where(dmin < 9.0, dmin * dmin, 0.0).sum(axis=1) + (n - used) * 81.0
        err = np.where(ok, err, np.inf)
        k = int(err.argmin())
        if best is None or err[k] < best[0]:
            best = (float(err[k]), float(ouse[k]), float(pp))
    if best is None:
        return None
    return best[1], best[2]


def _uniform_window(cands, n):
    """The *n* consecutive coordinates whose spacing is the most uniform.

    A board is the one place in a frame that carries n evenly spaced lines;
    banners, buttons and scene decoration add lines above and below it, and the
    longest run happily swallows them (observed: a spurious line 36px above the
    real first rank).  Scoring every window by the relative spread of its gaps
    isolates the board without assuming where in the frame it sits - which a
    fixed centre fraction cannot do for a result screen whose board is pushed
    up by a banner.
    """
    c = np.asarray(sorted(cands), dtype=np.float64)
    if c.size < n:
        return None
    best = None
    for s in range(0, c.size - n + 1):
        w = c[s:s + n]
        d = np.diff(w)
        if d.min() <= 1.0:
            continue
        cv = float(d.std() / d.mean())
        if best is None or cv < best[0]:
            best = (cv, s)
    if best is None:
        return None
    return c[best[1]:best[1] + n], best[0]


def _group_centres(profile, th):
    """(centre, width) of every run of *profile* above *th*."""
    out = []
    for g in _groups(profile, th):
        w = profile[g].astype(float)
        out.append((float((np.array(g, float) * w).sum() / w.sum()), len(g)))
    return out


def _median_pitch(cands):
    d = np.diff(sorted(cands))
    d = d[d > 30]
    return float(np.median(d)) if len(d) else 0.0


def _mid_strips(cx):
    """Columns halfway between the grid lines - no piece ever covers them."""
    return [int(round((cx[k] + cx[k + 1]) / 2.0)) for k in range(8)]


def _rows_from_strips(mask, H, cx, th):
    strip = np.zeros(H, np.int32)
    for m in _mid_strips(cx):
        strip += mask[:, max(0, m - 6):m + 7].sum(axis=1)
    return [c for c, w in _group_centres(strip / float(8 * 13), th)]


def _lattice_colour(a):
    """Grid lattice of the default wooden skin: the board is the big warm region."""
    H, W, _ = a.shape
    lum = luminance(a)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    dark = lum < 138
    green = (G > R + 6) & (G > 50)
    boardish = (~green) & (lum >= 55)

    rowf = boardish.mean(axis=1).copy()
    rowf[:60] = 0.0
    _, y0, y1 = _longest_run(rowf, 0.55)
    if y1 - y0 < 100:
        return None
    colf = boardish[y0:y1 + 1].mean(axis=0)
    _, x0, x1 = _longest_run(colf, 0.55)
    if x1 - x0 < 100:
        x0, x1 = 0, W - 1

    cands = _group_centres(dark[y0:y1 + 1, :].sum(axis=0), (y1 - y0) * 0.33)
    narrow = [c for c, w in cands if w <= 12] or [c for c, w in cands]
    cfit = _fit_progression(narrow, 9, _median_pitch(narrow), (x0 + x1) / 2.0)
    if cfit is None:
        return None
    co, cp = cfit
    cx = [co + cp * k for k in range(9)]

    rc = [c for c in _rows_from_strips(dark, H, cx, 0.55) if y0 - 5 <= c <= y1 + 5]
    rfit = _fit_progression(rc, 10, _median_pitch(rc), (y0 + y1) / 2.0)
    if rfit is None:
        return None
    ro, rp = rfit
    return {"band": (int(y0), int(y1), int(x0), int(x1)), "cx": cx,
            "cy": [ro + rp * j for j in range(10)], "cpitch": cp, "rpitch": rp,
            "co": co, "ro": ro}


def _lattice_lines(a, sign=1, contrast=LINE_CONTRAST):
    """Grid lattice of ANY board skin, found by local contrast, not by colour.

    Feeding the sprite fit a lattice that sits a few pixels off the painted discs
    is harmless: the disc search window is wider than any offset measured so far
    and the model is refitted from the discs themselves.
    """
    H, W, _ = a.shape
    lm = line_mask(a, sign=sign, contrast=contrast)
    cands = _group_centres(lm.sum(axis=0), max(30.0, H * LINE_COL_FRAC))
    narrow = [c for c, w in cands if w <= 16] or [c for c, w in cands]
    if len(narrow) < 4:
        return None
    cfit = _fit_progression(narrow, 9, _median_pitch(narrow), W / 2.0)
    if cfit is None:
        return None
    co, cp = cfit
    if not 40.0 <= cp <= 100.0 or co < -6.0 or co + cp * 8 > W + 6.0:
        return None
    cx = [co + cp * k for k in range(9)]

    # _fit_progression anchors its offset search on min(cands), so the candidate
    # list must not carry the dark rows of the war-scene decoration far above (or
    # below) the board: with a 0.0 in the list the search range never reaches the
    # real first row line and the fit collapses to None.
    cyc = BOARD_CY * H
    rows = _rows_from_strips(lm, H, cx, LINE_ROW_FRAC)
    if len(rows) < 6:
        return None
    # The board is not always centred in the frame: a result banner or a taller
    # header pushes it up, the fixed fraction then keeps only its lower rows,
    # and the fit lands a few ranks low (observed on a 601x1121 result screen:
    # ro 361 where the board really starts at 208, so every reading was shifted
    # down and the bottom rank fell off the board).  Prefer the ten consecutive
    # candidates whose gaps are the most uniform - that is the board, wherever
    # it sits - and keep the centred window as the fallback for the sparse
    # candidate lists where no full window exists.
    rfit = None
    win = _uniform_window(rows, 10)
    if win is not None:
        w = win[0]
        rfit = _fit_progression(list(w), 10, float((w[-1] - w[0]) / 9.0),
                                float((w[0] + w[-1]) / 2.0))
    if rfit is None:
        rc = [c for c in rows if abs(c - cyc) <= 5.2 * cp]
        if len(rc) < 6:
            return None
        rfit = _fit_progression(rc, 10, _median_pitch(rc), cyc)
    if rfit is None:
        return None
    ro, rp = rfit
    if not 40.0 <= rp <= 100.0:
        return None
    cy = [ro + rp * j for j in range(10)]
    if cy[0] < 0.10 * H or cy[9] > 1.02 * H:
        return None
    return {"band": (int(cy[0] - 38), int(cy[9] + 38), 0, W - 1), "cx": cx,
            "cy": cy, "cpitch": cp, "rpitch": rp, "co": co, "ro": ro}


def _fit_comb(coords, n, center, prange=(40.0, 100.0), step=0.25, win=0.09,
              min_in=0.55):
    """Fit x = off + p * k to scattered coordinates, ignoring the outliers.

    The scene around the board contributes blobs of its own, and their
    coordinates smear a plain circular mean.  Counting the
    points that share one narrow phase window instead, then refitting on those
    inliers alone, keeps the true lattice even when a third of the blobs are
    scenery.
    """
    c = np.asarray(coords, dtype=float)
    if c.size < 6:
        return None
    need = max(6, int(round(min_in * float(c.size))))
    best = None
    for p in np.arange(prange[0], prange[1] + 1e-9, step):
        q = np.sort(np.mod(c, p) / p)
        q2 = np.concatenate((q, q + 1.0))
        j = 0
        for i2 in range(q.size):
            while q2[i2] - q2[j] > win:
                j += 1
            cnt = i2 - j + 1
            if best is None or cnt > best[0]:
                best = (cnt, float(p), float(q2[j]))
    if best is None or best[0] < need:
        return None
    _cnt, p, ph = best
    q = np.mod(c, p) / p
    keep = np.mod(q - ph, 1.0) <= win
    if int(keep.sum()) < 6:
        return None
    mid = (n - 1) / 2.0
    off = ph * p + p * float(np.round((center - ph * p) / p - mid))
    k = np.round((c[keep] - off) / p)
    if k.min() < -1 or k.max() > n:
        return None
    A = np.polyfit(k, c[keep], 1)
    p2, off2 = float(A[0]), float(A[1])
    if not prange[0] <= p2 <= prange[1]:
        return None
    k2 = np.round((c - off2) / p2)
    if k2.min() < -1 or k2.max() > n:
        return None
    return off2, p2


TILE_MIN_FRAC = 0.28   # floor for the bare-tile fraction of a board row/column
TILE_K = 0.55           # ... and the share of that profile peak it must reach
TILE_Q = 85.0
TILE_DIST = 90.0


def _smooth1d(v, k):
    if k <= 1:
        return v
    return np.convolve(v, np.ones(k, np.float32) / k, mode='same')


def _tile_frac(prof, frac):
    """Tile-fraction cut for one row/column profile.

    A board whose bare tiles are only a slim majority - wide painted grid
    lines, big discs - never reaches a fixed 0.45 cut, so the cut follows the
    profile itself and is only floored at TILE_MIN_FRAC.
    """
    if frac is not None:
        return float(frac)
    return max(TILE_MIN_FRAC, TILE_K * float(np.percentile(prof, TILE_Q)))


def _tile_band(a, ref, frac=None, k=None):
    """Rows and columns of the board, told apart by how much of them is bare tile.

    A skin can hide the grid lines completely and the scene around the board is
    full of colourful props, so the piece lattice bootstrap would otherwise pick
    peaks from the scenery.  Bare tiles are the one structure the scene does not
    have, so the band they fill is the board.
    """
    d = np.abs(a.astype(np.int16) - np.asarray(ref, np.int16)).sum(axis=2)
    tileish = (d < TILE_DIST).astype(np.float32)
    H, W = tileish.shape
    if not k:
        # The bare-tile share of a board row dips at every painted grid line
        # and at every disc sitting on one, so the profile is a comb.  Smoothing
        # over a slice of a grid cell turns it into a plateau the run detector
        # can follow; a fixed k=9 leaves the comb and the run collapses.
        k = max(9, int(round(H / 24.0)))
    prof = _smooth1d(tileish.mean(axis=1), k)
    r = _longest_run(prof, _tile_frac(prof, frac))
    if r[0] < 0.30 * H:
        return None
    y0, y1 = r[1], r[2]
    cprof = _smooth1d(tileish[y0:y1 + 1].mean(axis=0), k)
    c = _longest_run(cprof, _tile_frac(cprof, frac))
    if c[0] < 0.30 * W:
        return None
    x0, x1 = c[1], c[2]
    r2prof = _smooth1d(tileish[:, x0:x1 + 1].mean(axis=1), k)
    r2 = _longest_run(r2prof, _tile_frac(r2prof, frac))
    if r2[0] >= 0.30 * H:
        y0, y1 = r2[1], r2[2]
    if y1 - y0 + 1 < 0.30 * H:
        return None
    if x1 - x0 + 1 < 0.55 * W:
        # Brightness-varying tiles can collapse the column run onto a slice of
        # the board.  The rows still carry it, so keep those and take the full
        # width instead of discarding the whole band (which would hand the peak
        # search a window full of scenery blobs).
        x0, x1 = 0, W - 1
    return y0, y1, x0, x1


PIECE_SEP = 40.0
PIECE_BAND_W = 0.70     # how much of the window width the board spans at least
PIECE_BAND_H = 0.55     # ... and of its height


def _lattice_pieces(a, half=BOX_HALF, verbose=False):
    """Bootstrap the lattice from the pieces alone - for a skin with no lines.

    A skin may hide or omit the grid lines altogether (sepia tiles painted the
    line colour), but the discs still sit on the same 9 x 10 lattice.  With no
    lines to measure, the bare tiles become the reference: every pixel far from
    the tile colour is piece material and the blobs of that mask are the pieces.
    Each blob is measured by its own centre of mass - the shaded side of a disc
    pulls a plain box-mean peak 10..20px down the board.
    """
    H, W, _ = a.shape
    ref = tile_colour(a)
    non = (dist_map(a, ref) > TILE_DIST).astype(np.float32)
    tb = _tile_band(a, ref)
    if tb is None:
        y0, y1, x0, x1 = int(0.18 * H), int(0.88 * H), int(0.02 * W), int(0.98 * W)
    else:
        y0, y1, x0, x1 = tb
    m = _box_mean(non, half)
    B = 8
    h = (m.shape[0] // B) * B
    w = (m.shape[1] // B) * B
    if h < 4 * B or w < 4 * B:
        return None
    blk = m[:h, :w].reshape(h // B, B, w // B, B).max(axis=(1, 3))
    # the scene outside the board is far from the tile colour as well, so the
    # range that sets the threshold is read inside the band only
    ry0 = max(0, y0 - half)
    rx0 = max(0, x0 - half)
    sub = m[ry0:y1 - half + 1, rx0:x1 - half + 1]
    lo = float(np.median(sub))
    top = float(np.percentile(sub, 99.5))
    if top - lo < 0.25:             # the map is a fraction, not a distance
        return None
    thr = lo + 0.45 * (top - lo)
    ys, xs = np.nonzero(blk >= thr)
    if len(xs) < 8:
        return None
    order = np.argsort(-blk[ys, xs])
    pts = []
    for k in order:
        cy = (ys[k] + 0.5) * B + half
        cx = (xs[k] + 0.5) * B + half
        if cy < y0 - 24 or cy > y1 + 24 or cx < x0 - 24 or cx > x1 + 24:
            continue
        if all((cx - q[0]) ** 2 + (cy - q[1]) ** 2 > PIECE_SEP * PIECE_SEP for q in pts):
            pts.append((cx, cy))
        if len(pts) >= 40:
            break
    if len(pts) < 8:
        return None
    seen = []
    for cx, cy in pts:
        gx, gy = _mask_centroid(non, int(round(cx)), int(round(cy)), 0.5, rad=22)
        if all((gx - q[0]) ** 2 + (gy - q[1]) ** 2 > 0.25 * PIECE_SEP * PIECE_SEP
               for q in seen):
            seen.append((gx, gy))
    if len(seen) < 8:
        return None
    # A skin whose tiles vary in brightness can shrink the band well inside the
    # board, and a prior built from that shrunken width lands under the real
    # pitch (observed: band 239px wide -> prior 21..40px, real pitch 65px, no
    # comb fit at all).  The board always fills most of this window, so the
    # pitch prior leans on the frame instead of on the band.
    hh = max(float(y1 - y0 + 1), PIECE_BAND_H * H)
    ww = max(float(x1 - x0 + 1), PIECE_BAND_W * W)
    cfit = _fit_comb([q[0] for q in seen], 9, 0.5 * (x0 + x1),
                      prange=(0.72 * ww / 8.0, 1.35 * ww / 8.0))
    rfit = _fit_comb([q[1] for q in seen], 10, 0.5 * (y0 + y1),
                      prange=(0.72 * hh / 9.0, 1.35 * hh / 9.0))
    if cfit is None or rfit is None:
        return None
    co, cp = cfit
    ro, rp = rfit
    if not 40.0 <= cp <= 100.0 or not 40.0 <= rp <= 100.0:
        return None
    if co < -6.0 or co + cp * 8 > W + 6.0:
        return None
    if ro < 0.10 * H or ro + rp * 9 > 1.02 * H:
        return None
    cx = [co + cp * k for k in range(9)]
    cy = [ro + rp * j for j in range(10)]
    if verbose:
        print("grid lattice bootstrapped from %d piece centres (cp %.2f, rp %.2f)"
              % (len(seen), cp, rp))
    return {"band": (int(cy[0] - 38), int(cy[9] + 38), 0, W - 1), "cx": cx,
            "cy": cy, "cpitch": cp, "rpitch": rp, "co": co, "ro": ro}


COMB_PITCH_MIN = 50.0     # column pitch search range for the projection comb
COMB_PITCH_MAX = 105.0
COMB_SCORE_MIN = 6.0       # mean |lum - median| at the comb teeth, in levels
COMB_STEP = 0.25


def _comb_fit(prof, n, prange, step=COMB_STEP, win=3):
    """Best (score, offset, pitch) for n evenly spaced deviations of a profile.

    A painted grid line dips the mean luminance of its whole column, so the
    projection profile carries the lattice even when per-pixel line masks drown
    in glyphs, rims and scenery.  Pieces sit on the same columns, which is why
    the teeth can be read straight off the profile.
    """
    med = float(np.median(prof))
    dev = np.abs(prof - med).astype(np.float32)
    if win > 1:
        dev = np.convolve(dev, np.ones(win, np.float32) / win, mode='same')
    W = int(dev.size)
    best = None
    teeth = np.arange(n, dtype=np.float64)
    for p in np.arange(prange[0], prange[1] + 1e-9, step):
        span = p * (n - 1)
        last = W - int(np.ceil(span)) - 1
        if last <= 0:
            continue
        starts = np.arange(last + 1, dtype=np.float64)
        xs = starts[:, None] + (teeth * p)[None, :]
        sc = dev[np.rint(xs).astype(np.int64)].mean(axis=1)
        j = int(np.argmax(sc))
        if best is None or sc[j] > best[0]:
            best = (float(sc[j]), float(starts[j]), float(p))
    return best


def _lattice_comb(a, verbose=False):
    """Read the lattice off the row/column projection profiles.

    Needed by skins whose tiles vary in brightness (the tile-run band detector
    then collapses and the piece lattice gets no usable prior) and by skins
    whose lines are neither clearly darker nor clearly brighter than the tiles.
    """
    H, W, _ = a.shape
    lum = luminance(a).astype(np.float64)
    ref = tile_colour(a)
    tb = _tile_band(a, ref)
    if tb is None:
        y0, y1 = int(0.18 * H), int(0.88 * H)
    else:
        y0, y1 = max(0, tb[0]), min(H - 1, tb[1])
    col = lum[y0:y1 + 1].mean(axis=0)
    # A phone bezel is a flat dark strip.  Its |lum-median| dwarfs the painted
    # files, so the comb locks onto the frame (observed: co=2 on a 601px shot
    # whose board starts near x=70).  Drop columns that sit far below the
    # interior brightness before fitting.
    interior = col[int(0.15 * W):int(0.85 * W)]
    floor = float(np.median(interior)) - 40.0
    usable = np.flatnonzero(col >= floor)
    if usable.size < 9:
        return None
    lo, hi = int(usable[0]), int(usable[-1]) + 1
    cf = _comb_fit(col[lo:hi], 9, (COMB_PITCH_MIN, COMB_PITCH_MAX))
    if cf is None or cf[0] < COMB_SCORE_MIN:
        return None
    co, cp = cf[1] + lo, cf[2]
    if not 40.0 <= cp <= 110.0 or co < -4.0 or co + cp * 8 > W + 4.0:
        return None
    # A dark phone bezel or a side panel can outscore the painted files.  The
    # discs still sit on the real files, so slide the comb by up to one pitch
    # and keep the phase whose nine files collect the most tile distance.
    # The left bezel is farther from the tile colour than the pieces are, so a
    # raw distance sum prefers the frame.  Restrict the vote to the interior
    # span the comb already claims, and require every file to land inside it.
    span0 = max(0, int(co))
    span1 = min(W, int(co + cp * 8) + 1)
    col_d = dist_map(a[y0:y1 + 1, span0:span1], ref).mean(axis=0)
    best_c = None
    for shift in np.arange(-cp, cp + 1e-9, 1.0):
        tot = 0.0
        ok = True
        for k in range(9):
            x = int(round(co + shift + cp * k)) - span0
            if x < 0 or x >= col_d.size:
                ok = False
                break
            tot += float(col_d[x])
        if ok and (best_c is None or tot > best_c[0]):
            best_c = (tot, shift)
    if best_c is not None:
        trial = co + best_c[1]
        if -4.0 <= trial and trial + cp * 8 <= W + 4.0:
            co = trial
    # Rows: sample narrow strips halfway between columns, where no disc ever
    # sits, so the profile carries the painted lines and almost nothing else.
    # Two windows: the tile band alone, and the band grown past the board.  A
    # result banner or the red "play again" slab outscores the grid when the
    # window reaches it (observed: ro jumped a whole rank).  The band-only window
    # misses boards whose tile run stops short of the outer ranks, so both are
    # kept and the piece vote below picks the one that actually lands on discs.
    grown_lo = max(0, int(y0 - 1.2 * cp))
    grown_hi = min(H, int(y1 + 1.2 * cp))
    if grown_hi - grown_lo < 0.5 * H:
        return None
    strips = []
    xs = []
    for k in range(8):
        xc = int(round(co + cp * (k + 0.5)))
        if xc - 6 < 0 or xc + 7 > W:
            continue
        strips.append(lum[grown_lo:grown_hi, xc - 6:xc + 7].mean(axis=1))
        xs.append(xc)
    if len(strips) < 4:
        return None
    full = np.mean(np.array(strips), axis=0)
    cands = []
    rf = _comb_fit(full, 10, (0.92 * cp, 1.08 * cp))
    if rf is not None and rf[0] >= COMB_SCORE_MIN:
        cands.append((rf[1] + grown_lo, rf[2], rf[0]))
    band_lo = max(0, int(y0) - grown_lo)
    band_hi = min(full.size - 1, int(y1) - grown_lo)
    if band_hi - band_lo >= int(0.45 * H):
        rb = _comb_fit(full[band_lo:band_hi + 1], 10, (0.92 * cp, 1.08 * cp))
        if rb is not None and rb[0] >= COMB_SCORE_MIN:
            cands.append((rb[1] + grown_lo + band_lo, rb[2], rb[0]))
    if not cands:
        return None
    # Seed with the stronger comb; the piece vote may replace it.
    ro, rp = max(cands, key=lambda t: t[2])[:2]
    # A comb is blind to which rank it starts on, so phasing it one rank off is
    # easy.  Pick the phase that keeps all ten rows inside the tile band *and*
    # puts them on pieces: a row through the discs collects far more tile
    # distance than one through the gaps.
    # _box_mean(x, half)[p, q] is the box centred on (q + half, p + half), so the
    # map is inset by half on every side: build it from a window that is grown by
    # half so that every row of the phase vote is inside it (indexing the inset
    # map with raw frame coordinates used to raise IndexError on menu screens).
    half = 6
    ry0 = max(half, int(min(ro, y0) - 2.2 * rp))
    ry1 = min(H - half, int(max(ro + 9 * rp, y1) + 2.2 * rp))
    if ry1 - ry0 < 3 * half:
        return None
    ev = _box_mean(dist_map(a[ry0 - half:ry1 + half], ref), half)
    eh, ew = ev.shape
    lo_b, hi_b = y0 - 0.6 * rp, y1 + 0.6 * rp
    best = None
    phases = []
    for cro, crp, _sc in cands:
        for mp in range(-3, 4):
            phases.append((cro + mp * crp, crp))
    for r, crp in phases:
        if r < lo_b or r + 9 * crp > hi_b:
            continue
        if r < 0.05 * H or r + 9 * crp > 1.05 * H:
            continue
        tot = 0.0
        n = 0
        for j in range(10):
            y = int(round(r + crp * j))
            for k in range(9):
                x = int(round(co + cp * k))
                ey, ex = y - ry0, x - half
                if 0 <= ey < eh and 0 <= ex < ew:
                    tot += float(ev[ey, ex])
                    n += 1
        if n < 70:
            continue
        if best is None or tot > best[0]:
            best = (tot, r, crp)
    if best is None:
        return None
    ro, rp = best[1], best[2]
    if not 40.0 <= rp <= 110.0 or ro < 0.05 * H or ro + rp * 9 > 1.05 * H:
        return None
    if verbose:
        print("grid lattice from projection combs (cp %.2f, rp %.2f, teeth %.1f/%.1f)"
              % (cp, rp, cf[0], rf[0]))
    return {"band": (int(ro - 38), int(ro + rp * 9 + 38), 0, W - 1),
            "cx": [co + cp * k for k in range(9)],
            "cy": [ro + rp * j for j in range(10)],
            "cpitch": cp, "rpitch": rp, "co": co, "ro": ro}


LATTICES = (("colour", 0, 0.0),
            ("dark lines", 1, LINE_CONTRAST),
            ("bright lines", -1, LINE_CONTRAST),
            ("dark lines", 1, 12.0),
            ("bright lines", -1, 12.0),
            ("comb lines", 3, 0.0),
            ("piece lattice", 2, 0.0))


def _lattice_for(a, kind, contrast, verbose=False):
    if kind == 0:
        return _lattice_colour(a)
    if kind == 2:
        return _lattice_pieces(a, verbose=verbose)
    if kind == 3:
        return _lattice_comb(a, verbose=verbose)
    return _lattice_lines(a, sign=kind, contrast=contrast)


def _fit_rank(cal):
    """Sort key for the competing lattice hypotheses.

    Painted grid lines outrank the piece lattice even when the latter fits its
    discs a little tighter: a piece lattice that also swallowed scenery blobs
    still fits, but its lattice can sit 17px off, and the model it seeds is then
    off by a whole column at the far edge.  Among the line lattices the winner is
    the one whose model had to move least away from the lines it was seeded from.
    """
    r = cal.get("resid")
    used = int(cal.get("ndiscs_used", 0))
    dev = float(cal.get("model_dev", 99.0))
    lines = int(cal.get("kind", 2)) in (-1, 0, 1, 3)
    fine = r is not None and r <= FIT_OK_RESID and used >= FIT_MIN_DISCS
    tier = 0 if (fine and lines) else (1 if fine else 2)
    return (-tier, -(dev if fine else 99.0), -(r if r is not None else 99.0), used)


def calibrate(a, verbose=False):
    """Return a calibration dict for an RGB frame of the JJ window.

    Board skins can repaint everything on the board, so six lattices are on
    offer: the colour test of the default wooden skin, thin lines found by local
    contrast in either polarity (and at a weaker contrast for skins whose lines
    barely differ from the tiles), and finally the lattice of the pieces
    themselves, which answers for a skin with no lines at all.  The first
    lattice a sprite model can be fitted to wins; a convincing fit (8+ discs at
    under 4.5px residual) stops the search immediately, so the usual skins cost
    one pass.
    """
    best = None
    for name, kind, contrast in LATTICES:
        # One hypothesis blowing up must not take the whole calibration with it:
        # the screens between rounds (lobby, result, animations) are exactly the
        # frames where a lattice can run into a shape it did not expect, and the
        # callers keep re-reading them until the board is back.
        try:
            base = _lattice_for(a, kind, contrast, verbose)
            if base is None:
                continue
            cal = _calibrate_with(a, base, verbose, kind)
        except Exception as exc:
            if verbose:
                print("lattice %s failed: %s: %s" % (name, type(exc).__name__, exc))
            continue
        if cal is None:
            continue
        cal["lattice"] = name
        cal["kind"] = kind
        if cal.get("model") is None:
            if best is None:
                best = cal
            continue
        if verbose:
            print("lattice: %s" % name)
        if best is None or best.get("model") is None or _fit_rank(cal) > _fit_rank(best):
            best = cal
        # A convincing fit of a *painted* lattice ends the search; the piece
        # lattice never shortcuts it, because a line lattice found later may
        # still be the better seed for the very same discs.
        if (kind in (-1, 0, 1, 3) and cal.get("ndiscs_used", 0) >= FIT_MIN_DISCS
                and (cal.get("resid") or 99.0) <= FIT_GOOD_RESID):
            return cal
    return best


def _calibrate_with(a, base, verbose=False, kind=2):
    """Fit the sprite model against one lattice."""
    co, cp = base["co"], base["cpitch"]
    ro, rp = base["ro"], base["rpitch"]
    cx, cy = base["cx"], base["cy"]
    cal = {"band": base["band"], "cx": cx, "cy": cy,
           "cpitch": cp, "rpitch": rp, "model": None, "ndiscs": 0}

    # One integral image of the tile distance serves the disc search; its median
    # is the bare-tile reference, and the distance between the median and the top
    # cell says how clearly the pieces stand out on this skin.
    band = (int(cy[0] - 30), int(cy[9] + 30), int(cx[0] - 20), int(cx[8] + 20))
    ref = tile_colour(a, band)
    ctx = piece_roi(a, cal, BOX_HALF, ref=ref)
    scores, _, _r = piece_scores(a, cal, BOX_HALF, ctx=ctx)
    lv = occ_level(scores)
    pts = []
    if lv is not None:
        cut, lo, top = lv
        pts = _disc_points(a, cal, lo + 0.32 * (top - lo), ctx=ctx)
        if len(pts) < 10:
            loose = _disc_points(a, cal, lo + 0.20 * (top - lo), ctx=ctx)
            if len(loose) > len(pts):
                pts = loose
    cal["ndiscs"] = len(pts)
    cal["occ"] = (None if lv is None else (round(lv[1], 1), round(lv[2], 1)))
    if kind in NEAR_FIT_KINDS:
        near_r = FIT_NEAR_FRAC * min(cp, rp)
        near = [p for p in pts
                if float(np.hypot(p[2] - cal["cx"][p[0]], p[3] - cal["cy"][p[1]])) <= near_r]
        if len(near) >= 2:
            pts = near
    if len(pts) >= 2:
        # Fit the *delta* from the line lattice rather than absolute positions:
        # the delta is a few pixels, so the fit degenerates gracefully to a mean
        # shift when only a couple of discs are visible (sparse endgame) instead
        # of swinging the whole model off the board.
        P = np.array([[1.0, i, j, i * j] for i, j, x, y in pts], dtype=float)
        DX = np.array([p[2] - cal["cx"][p[0]] for p in pts], dtype=float)
        DY = np.array([p[3] - cal["cy"][p[1]] for p in pts], dtype=float)
        n = len(pts)
        lam = max(0.0, 30.0 - 2.0 * n)
        prior_x = np.array([0.0, SPRITE_KX * cp, 0.0, 0.0])
        prior_y = np.array([0.0, 0.0, SPRITE_KY * rp, 0.0])
        W = np.diag([0.0, lam, lam, lam])
        keep = np.ones(n, dtype=bool)
        CX = CY = None
        for _ in range(5):
            A = P[keep]
            if A.shape[0] < 2:
                break
            M = A.T.dot(A) + W
            CX = np.linalg.solve(M, A.T.dot(DX[keep]) + lam * prior_x)
            CY = np.linalg.solve(M, A.T.dot(DY[keep]) + lam * prior_y)
            e = np.sqrt((P.dot(CX) - DX) ** 2 + (P.dot(CY) - DY) ** 2)
            thr = max(1.5, float(np.median(e[keep])) * 3.0)
            nk = e <= thr
            if nk.sum() < 2 or bool((nk == keep).all()):
                break
            keep = nk
        if CX is not None:
            CXa = [co + float(CX[0]), cp + float(CX[1]), float(CX[2]), float(CX[3])]
            CYa = [ro + float(CY[0]), float(CY[1]), rp + float(CY[2]), float(CY[3])]
            dev = _model_deviation(CXa, CYa, cal["cx"], cal["cy"])
            if dev <= MAX_MODEL_DEV and _pitch_ok(CXa, CYa, cp, rp):
                cal["model"] = (CXa, CYa)
                cal["ndiscs_used"] = int(keep.sum())
                ex = P[keep].dot(CX) - DX[keep]
                ey = P[keep].dot(CY) - DY[keep]
                err = np.sqrt(ex ** 2 + ey ** 2)
                cal["resid"] = float(err.max())
                cal["resid_p80"] = float(np.percentile(err, 80.0))
                cal["model_dev"] = float(dev)
                if cal["resid_p80"] > FIT_REJECT_RESID:
                    # Most discs sit far off the lines, so the LATTICE is wrong and
                    # the fit merely follows it.  The plain maximum would reject a
                    # good lattice over the one disc that happens to be animating.
                    if verbose:
                        print("model rejected: p80 residual %.1fpx" % cal["resid_p80"])
                    cal["model"] = None
                    cal.pop("ndiscs_used", None)
            elif verbose:
                print("model rejected: %.1fpx off the grid-line lattice" % dev)
    if verbose:
        print("band", cal["band"], "cpitch %.2f rpitch %.2f" % (cp, rp),
              "discs", len(pts), "resid", cal.get("resid"), "occ", cal["occ"])
    return cal


def _disc_points(a, cal, occ_min, ctx=None):
    """Disc centres of every cell whose tile distance clears *occ_min*."""
    loc = locate(a, cal, occ_min=occ_min, ctx=ctx)
    return [(i, j, v[1], v[2]) for (i, j), v in loc.items() if v[0] >= occ_min]


def _pitch_ok(CX, CY, cp, rp):
    """Reject a fit whose perspective pitch is absurd for the lattice it came from."""
    return 0.85 * cp <= CX[1] <= 1.15 * cp and 0.85 * rp <= CY[2] <= 1.15 * rp


def _model_deviation(CX, CY, cx, cy):
    """Largest distance between the fitted perspective model and the line lattice.

    A fit that disagrees with the grid lines it was seeded from is garbage (the
    line lattice is crude but never absurd), so this is the sanity gate that keeps
    a bad endgame fit from silently replacing a usable geometry.
    """
    worst = 0.0
    for j in range(10):
        for i in range(9):
            x = CX[0] + CX[1] * i + CX[2] * j + CX[3] * i * j
            y = CY[0] + CY[1] * i + CY[2] * j + CY[3] * i * j
            d = max(abs(x - cx[i]), abs(y - cy[j]))
            if d > worst:
                worst = d
    return worst


def grid_xy(cal, i, j):
    if cal.get("model"):
        CX, CY = cal["model"]
        x = CX[0] + CX[1] * i + CX[2] * j + CX[3] * i * j
        y = CY[0] + CY[1] * i + CY[2] * j + CY[3] * i * j
    else:
        x = cal["cx"][i]
        y = cal["cy"][j]
    return float(x), float(y)


TPL_SOURCES = {
    "r": [(0, 0), (8, 0)], "n": [(1, 0), (7, 0)], "b": [(2, 0), (6, 0)],
    "a": [(3, 0), (5, 0)], "k": [(4, 0)],
    "c": [(1, 2), (7, 2)],
    "p": [(0, 3), (2, 3), (4, 3), (6, 3), (8, 3)],
    "R": [(0, 9), (8, 9)], "N": [(1, 9), (7, 9)], "B": [(2, 9), (6, 9)],
    "A": [(3, 9), (5, 9)], "K": [(4, 9)],
    "C": [(1, 7), (7, 7)],
    "P": [(0, 6), (2, 6), (4, 6), (6, 6), (8, 6)],
}
PIECE_NAME = {"r": "\u8eca", "n": "\u99ac", "b": "\u8c61", "a": "\u58eb", "k": "\u5c07",
              "c": "\u7832", "p": "\u5352", "R": "\u4fe5", "N": "\u5098", "B": "\u76f8",
              "A": "\u4ed5", "K": "\u5e25", "C": "\u70ae", "P": "\u5175", ".": "."}


def _box_mean(x, half):
    """Box mean of a 2-D array: m[p, q] is the box centred on (q+half, p+half).

    The running sums stay in float32.  Peak values are below 2^20 and the
    differences that matter are in the hundreds, so the cancellation error is
    around 0.02% - far below the 0.37 vs 0.15 separation the caller relies on.
    """
    ii = np.zeros((x.shape[0] + 1, x.shape[1] + 1), np.float32)
    ii[1:, 1:] = x
    np.cumsum(ii, 0, out=ii)
    np.cumsum(ii, 1, out=ii)
    k = 2 * half + 1
    return (ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]) * np.float32(1.0 / (k * k))


def tile_colour(a, band=None):
    """Median colour of the board tiles - what every piece has to differ from.

    The median is safe: at most 32 of the 90 intersections hold a piece, so bare
    tile always dominates the sample even in a crowded middlegame.  Nothing here
    assumes WHICH colour the skin uses, so any repaint is fine.
    """
    H, W, _ = a.shape
    if band is None:
        r0, r1 = int(TILE_BAND[0] * H), int(TILE_BAND[1] * H)
        c0, c1 = int(TILE_BAND[2] * W), int(TILE_BAND[3] * W)
    else:
        r0, r1, c0, c1 = band[0], band[1], band[2], band[3]
    r0 = max(0, min(H - 1, int(r0)))
    r1 = max(r0 + 1, min(H, int(r1)))
    c0 = max(0, min(W - 1, int(c0)))
    c1 = max(c0 + 1, min(W, int(c1)))
    sub = a[r0:r1, c0:c1].reshape(-1, 3)[::7]
    return np.median(sub, axis=0).astype(np.float32)


def dist_map(a, ref):
    """Per pixel ||pixel - tile colour||_1: bare tile reads ~0, a piece reads big.

    Unlike the old "fraction of pixels brighter than 545" test this has no
    polarity: a cream disc on an ivory board scores as high as a cream disc on a
    wooden one, which is exactly the case that used to collapse.
    """
    d = a.astype(np.int16) - np.rint(ref).astype(np.int16).reshape(1, 1, 3)
    return np.abs(d).sum(axis=2).astype(np.float32)


def piece_roi(a, cal, half=BOX_HALF, ref=None, band=None):
    """(map, origin, ref): box mean of the tile distance over the board ROI.

    Only the board rectangle is integrated, so this stays around 3ms even
    though it walks three colour channels: the distance is summed into one
    float plane before the integral image is built.
    """
    if ref is None:
        ref = tile_colour(a, band)
    H, W = a.shape[0], a.shape[1]
    x0, y0, x1, y1 = _roi_bounds(cal, half)
    cx0, cy0 = max(0, x0 - half), max(0, y0 - half)
    cx1, cy1 = min(W, x1 + half + 1), min(H, y1 + half + 1)
    m = _box_mean(dist_map(a[cy0:cy1, cx0:cx1], ref), half)
    return m, (cy0, cx0), ref


def piece_map_full(a, half=BOX_HALF, ref=None, band=None):
    """The same map over the whole frame, for a board whose lattice is unknown."""
    if ref is None:
        ref = tile_colour(a, band)
    return _box_mean(dist_map(a, ref), half), ref


def piece_scores(a, cal, half=BOX_HALF, ctx=None, band=None):
    """{(i, j): tile distance inside the box at the MODEL centre of the cell}."""
    if ctx is None:
        ctx = piece_roi(a, cal, half, band=band)
    m, (oy, ox), ref = ctx
    h, w = m.shape
    out = {}
    for j in range(10):
        for i in range(9):
            x, y = grid_xy(cal, i, j)
            p = min(max(int(round(y)) - oy - half, 0), h - 1)
            q = min(max(int(round(x)) - ox - half, 0), w - 1)
            out[(i, j)] = float(m[p, q])
    return out, (m, oy, ox), ref


def occ_level(scores, frac=SAMPLE_FRAC, gap_min=OCC_GAP_MIN):
    """Piece/empty cut of the 90 cell scores: (cut, floor, top) or None.

    The floor is the MEDIAN score.  Empty intersections always outnumber the
    pieces (at most 32 of 90), so the median is bare tile by construction and
    needs no prior about the skin.  The cut is deliberately permissive - the NCC
    pass afterwards throws decorated squares out again - because missing a real
    piece is far worse than looking at one square too many.
    """
    v = np.sort(np.asarray(list(scores.values()), dtype=np.float64))
    if v.size < 8:
        return None
    lo = float(np.median(v))
    top = float(v[-1])
    if top - lo < gap_min:
        return None
    return lo + frac * (top - lo), lo, top


def _mask_centroid(m, x, y, thr, rad=22):
    """Sub-pixel centre of the pixels of *m* above *thr* within radius *rad*.

    The disc is cut at its own radius so the drop shadow below it cannot pull the
    centre down, and the mask is symmetric so a heavy glyph cannot pull it side-
    ways either - both effects were measured at 6..12px with a plain weighted
    centroid.
    """
    r0, c0 = max(0, y - rad), max(0, x - rad)
    sub = m[r0:y + rad + 1, c0:x + rad + 1]
    if sub.size == 0:
        return float(x), float(y)
    yy, xx = np.mgrid[0:sub.shape[0], 0:sub.shape[1]]
    sel = (sub > thr) & (((yy + r0 - y) ** 2 + (xx + c0 - x) ** 2) <= rad * rad)
    n = int(sel.sum())
    if n < 12:
        return float(x), float(y)
    return float(c0 + xx[sel].mean()), float(r0 + yy[sel].mean())


def line_mask(a, rad=LINE_RAD, contrast=LINE_CONTRAST, sign=1):
    """Skin-independent mask of thin straight structures: grid lines, glyph ink.

    The wooden skin can be found by colour ("not green and not dark"), but a
    swapped-in skin repaints the tiles completely - the stone skin is grey-green,
    so that test reports "no board" and calibration dies.  A pixel therefore
    counts when its luminance differs from its neighbourhood mean by *contrast*:
    thin lines survive on a dark or on a bright skin (sign +1 for dark lines, -1
    for lines lighter than the tiles) while large flat props do not.
    """
    H, W, _ = a.shape
    ap = pad_frame(a)
    lp = luminance(ap).astype(np.float32)
    core = _box_mean(lp, rad) - lp[rad:lp.shape[0] - rad, rad:lp.shape[1] - rad]
    m = np.zeros(lp.shape, bool)
    if sign >= 0:
        m[rad:lp.shape[0] - rad, rad:lp.shape[1] - rad] = core > contrast
    else:
        m[rad:lp.shape[0] - rad, rad:lp.shape[1] - rad] = core < -contrast
    return m[PADV:PADV + H, PADV:PADV + W]


def _roi_bounds(cal, half, extra=0):
    """Frame rectangle holding every box centre the 90 cells can ask for."""
    xs, ys = [], []
    for i in (0, 8):
        for j in (0, 9):
            x, y = grid_xy(cal, i, j)
            xs.append(x)
            ys.append(y)
    pad = half + extra + 4
    return (int(np.floor(min(xs))) - pad, int(np.floor(min(ys))) - pad,
            int(np.ceil(max(xs))) + pad + 1, int(np.ceil(max(ys))) + pad + 1)


def locate(a, cal, win=LOC_WIN, half=BOX_HALF, occ_min=0.0, ctx=None):
    """Find the disc centre of every cell of the board.

    Returns {(i, j): (score, x, y)} with x, y in ORIGINAL frame coordinates.
    The score is the mean tile distance inside a 33x33 box: near the tile colour
    (a few tens) on an empty intersection, far away (a hundred and up) on a
    piece.  That holds on a dark and on a bright skin alike, which the old
    cream-fraction score could not promise.
    """
    if ctx is None:
        ctx = piece_roi(a, cal, half)
    m, (oy, ox), ref = ctx
    lo = float(np.median(m))
    h, w = m.shape
    out = {}
    for j in range(10):
        for i in range(9):
            x, y = grid_xy(cal, i, j)
            sx = int(round(x)) - ox - half
            sy = int(round(y)) - oy - half
            r0 = max(0, sy - win)
            c0 = max(0, sx - win)
            r1 = min(h, sy + win + 1)
            c1 = min(w, sx + win + 1)
            if r1 <= r0 or c1 <= c0:
                continue
            sub = m[r0:r1, c0:c1]
            k = int(np.argmax(sub))
            dy, dx = divmod(k, sub.shape[1])
            sc = float(sub[dy, dx])
            if sc < occ_min:
                continue
            mx = c0 + dx + half
            my = r0 + dy + half
            xc, yc = _mask_centroid(m, mx, my, 0.5 * (sc + lo), rad=22)
            out[(i, j)] = (sc, xc + ox, yc + oy)
    return out


FP_BLOCK = 8       # block edge used by frame_changed
FP_HOT = 24        # changed pixels inside a block that mark it as moving
FP_BLOCKS = 8      # hot blocks above this mean the board is still animating


def frame_changed(a, b, band):
    """True when the board band really moved.

    The mini-program UI shimmers on its own (the river label, the top bar):
    a few hundred scattered pixels change every frame even on a still board.
    Counting *whole* blocks that changed tells a piece-sized move (20+ blocks)
    apart from that shimmer (0-3 blocks) for about 3ms.
    """
    y0, y1 = band
    p = a[y0:y1]
    q = b[y0:y1]
    d = np.maximum(p, q) - np.minimum(p, q)
    if d.ndim == 3:
        d = d.max(axis=2)
    h = (d.shape[0] // FP_BLOCK) * FP_BLOCK
    w = (d.shape[1] // FP_BLOCK) * FP_BLOCK
    blk = (d[:h, :w] > 8).reshape(h // FP_BLOCK, FP_BLOCK, w // FP_BLOCK, FP_BLOCK)
    return int((blk.sum(axis=(1, 3)) > FP_HOT).sum()) > FP_BLOCKS


def fingerprint_band(cal, H):
    """Rows of the frame that carry the board, used for cheap change detection."""
    band = cal.get("band")
    if not band:
        return 0, H
    return max(0, int(band[0]) - 6), min(H, int(band[1]) + 6)


def pad_frame(a):
    """Pad with edge pixels so squares near the board border stay legal."""
    return np.pad(a, ((PADV, PADV), (PADV, PADV), (0, 0)), mode="edge")


def _patch_gray(a, xi, yi, h, pad=0):
    H, W, _ = a.shape
    xi += pad
    yi += pad
    if xi - h < 0 or yi - h < 0 or xi + h > W or yi + h > H:
        return None
    return a[yi - h:yi + h, xi - h:xi + h].astype(np.float32).mean(axis=2)


def cell_box_scores(a, cal, half=BOX_HALF, ref=None, ctx=None):
    """Tile distance of an inner box at the MODEL centre of every cell.

    Evaluated at the model centre (not at a local optimum) so that the value is
    directly comparable with the patch recognition feeds to the NCC matcher, and
    so that a last-move halo painted around a neighbouring square cannot move the
    measurement.  Returns (scores, context) where the context is the integrated
    board rectangle - the old full-frame bright mask was the dominant cost of
    every read and it inverted on a bright board skin.
    """
    if ctx is None:
        band = (int(cal["cy"][0] - 30), int(cal["cy"][9] + 30),
                int(cal["cx"][0] - 20), int(cal["cx"][8] + 20))
        ctx = piece_roi(a, cal, half, ref=ref, band=band)
    out, ctx, ref = piece_scores(a, cal, half, ctx=ctx)
    return out, ctx


def cell_box_scores3(a, cal, half=BOX_HALF, ref=None, ctx=None):
    """cell_box_scores, but also handing back the tiles it measured against."""
    if ctx is None:
        band = (int(cal["cy"][0] - 30), int(cal["cy"][9] + 30),
                int(cal["cx"][0] - 20), int(cal["cx"][8] + 20))
        ctx = piece_roi(a, cal, half, ref=ref, band=band)
    out, ctx, ref = piece_scores(a, cal, half, ctx=ctx)
    return out, ctx, ref

def _class_of(P, tpl, skip_id=None):
    """Best matching class of patch P over a template dict."""
    best, bt = -2.0, None
    for t, lst in tpl.items():
        for T in lst:
            if skip_id is not None and T is skip_id:
                continue
            s = _ncc(_fit(P, T), T)
            if s > best:
                best, bt = s, t
    return bt, best


def build_templates(a, cal, validate=True, verbose=False):
    """Extract piece templates from a frame, rejecting anything that is not a piece.

    Two gates, both essential:
      1. the source square must actually hold a piece (its distance score must clear the
      2. leave-one-out check - the patch must match its OWN class better than any
         other class.  Without gate 2 a home square that was vacated earlier in the
         game silently becomes an "empty square template", which then wins every
         later comparison with a score of 1.0 on empty intersections.
    Centers come from the fitted model, exactly as in recognize(), so that a
    template matches itself with score 1.0 on the frame it came from.
    """
    ap = pad_frame(a)
    sc, _ = cell_box_scores(a, cal)
    lv = occ_level(sc)
    floor = lv[0] if lv is not None else float('inf')
    cand = {}
    for t, sources in TPL_SOURCES.items():
        for (i, j) in sources:
            if sc.get((i, j), 0.0) < floor:
                continue
            x, y = grid_xy(cal, i, j)
            p = _patch_gray(ap, int(round(x)), int(round(y)), TPL_HALF, pad=PADV)
            if p is not None:
                cand.setdefault(t, []).append(((i, j), p))
    tpl = dict((t, [p for _, p in v]) for t, v in cand.items())
    if not validate:
        return tpl
    out = {}
    for t, items in cand.items():
        others = dict((c, v) for c, v in tpl.items() if c != t)
        own = tpl[t]
        good = []
        for ij, p in items:
            # best score against any OTHER class, and best score against a
            # DIFFERENT variant of the same class (leave-one-out).
            bo = _class_of(p, others)[1] if others else -2.0
            bw = -2.0
            for T in own:
                if T is not p:
                    s = _ncc(_fit(p, T), T)
                    if s > bw:
                        bw = s
            # keep it when the same class explains it at least as well as any
            # other class, or when no other class explains it convincingly at
            # all - the latter is the only option for a class that appears
            # exactly once on the board (the two generals).
            keep = (bo < 0.55) or (bw > -2.0 and bw >= bo)
            if keep:
                good.append(p)
            elif verbose:
                print("    reject template %s from %s (own %.3f other %.3f)" % (t, ij, bw, bo))
        if good:
            out[t] = good
    return out


def _fit(P, T):
    """Resample a patch to the template resolution when the window scale changed."""
    if P.shape == T.shape:
        return P
    from PIL import Image
    n = int(T.shape[0])
    q = np.clip(P, 0, 255).astype(np.uint8)
    return np.asarray(Image.fromarray(q).resize((n, n), Image.BILINEAR), dtype=np.float32)


def save_templates(tpl, path=TPL_PACK, cpitch=0.0, rpitch=0.0):
    d = {"_meta": np.asarray([cpitch, rpitch, TPL_HALF], dtype=np.float64)}
    for t, lst in tpl.items():
        d["c_" + t] = np.asarray(lst, dtype=np.float32)
    np.savez_compressed(path, **d)
    return path


def load_templates(path=None, cal=None):
    """Load a template pack -> (tpl, patch_half); (None, TPL_HALF) when absent."""
    if path is None:
        path = find_templates()
    if not path or not os.path.isfile(path):
        return None, TPL_HALF
    z = np.load(path, allow_pickle=False)
    meta = z["_meta"]
    ref_c, ref_r = float(meta[0]), float(meta[1])
    out = {}
    for k in z.files:
        if k.startswith("c_"):
            out[k[2:]] = [np.asarray(x, dtype=np.float32) for x in z[k]]
    half = TPL_HALF
    if cal is not None and ref_c > 0 and ref_r > 0:
        cs, rs = cal.get("cpitch"), cal.get("rpitch")
        if cs and rs:
            s = 0.5 * (cs / ref_c + rs / ref_r)
            if abs(s - 1.0) > 0.02:
                n = int(round((2 * TPL_HALF) * s)) // 2 * 2
                n = max(16, min(96, n))
                out = dict((t, [_resize2d(P, n) for P in lst]) for t, lst in out.items())
                half = n // 2
    return out, half


def _resize2d(P, n):
    if P.shape[0] == n and P.shape[1] == n:
        return P
    from PIL import Image
    q = np.clip(P, 0, 255).astype(np.uint8)
    return np.asarray(Image.fromarray(q).resize((n, n), Image.BILINEAR), dtype=np.float32)


def _ncc(P, T):
    p = P - P.mean()
    t = T - T.mean()
    d = np.sqrt(float((p * p).sum()) * float((t * t).sum()))
    return float((p * t).sum() / d) if d > 1e-9 else -1.0


_MATCH_CACHE = {}


def _occ_masks(R=46):
    m = _MASK_CACHE.get(R)
    if m is None:
        yy, xx = np.mgrid[-R:R, -R:R]
        rr = np.sqrt(xx * xx + yy * yy)
        m = (rr <= 18, (rr >= 28) & (rr <= 37))
        _MASK_CACHE[R] = m
    return m


def sum_image(a):
    """Per pixel R + G + B as int32 (765 max, so float64 buys nothing).

    The old float64 upcast made this the single most expensive call in the
    pipeline: 18.6ms of a 52.7ms recognise.
    """
    return a.sum(axis=2, dtype=np.int32)

def _match_prep(tpl, half):
    """Stack every template into one zero-mean float32 matrix (K, n*n)."""
    key = (id(tpl), half)
    c = _MATCH_CACHE.get(key)
    if c is not None and c[0] is tpl:
        return c[1]
    n = 2 * half
    rows = []
    cls = []
    for t in sorted(tpl):
        for T in tpl[t]:
            q = _resize2d(np.asarray(T, np.float32), n)
            q = q - q.mean()
            rows.append(q.ravel())
            cls.append(t)
    T0 = np.asarray(rows, np.float32)
    nt = np.sqrt((T0 * T0).sum(axis=1)).astype(np.float32)
    prep = (cls, T0, nt)
    _MATCH_CACHE.clear()
    _MATCH_CACHE[key] = (tpl, prep)
    return prep


def _match_cell(ap, cx, cy, prep, half, rad=MATCH_RAD, per=None):
    """Best normalised correlation over every template and every +-rad offset.

    Returns (score, piece, runner_up_score, dx, dy) or None.  The inner box mean
    and variance for all offsets come from integral images, and the dot products
    for all offsets come from a single matrix multiply, so the whole two
    dimensional search costs about as much as 32 plain correlations.

    When *per* is a dict it receives the best score of every class at the winning
    offset, which is what a caller needs to re-decide the square inside one side
    without paying for another search.
    """
    cls, T0, nt = prep
    n = 2 * half
    m = n + 2 * rad
    x0 = int(round(cx)) + PADV - half - rad
    y0 = int(round(cy)) + PADV - half - rad
    H, W = ap.shape[0], ap.shape[1]
    if x0 < 0 or y0 < 0 or y0 + m > H or x0 + m > W:
        return None
    reg = ap[y0:y0 + m, x0:x0 + m].astype(np.float32).mean(axis=2)
    ii = np.zeros((m + 1, m + 1), np.float64)
    sq = np.zeros((m + 1, m + 1), np.float64)
    ii[1:, 1:] = reg
    sq[1:, 1:] = reg * reg
    np.cumsum(ii, 0, out=ii)
    np.cumsum(ii, 1, out=ii)
    np.cumsum(sq, 0, out=sq)
    np.cumsum(sq, 1, out=sq)
    s1 = ii[n:, n:] - ii[:-n, n:] - ii[n:, :-n] + ii[:-n, :-n]
    s2 = sq[n:, n:] - sq[:-n, n:] - sq[n:, :-n] + sq[:-n, :-n]
    npx = float(n * n)
    mean = s1 / npx
    sd = np.sqrt(np.maximum(s2 / npx - mean * mean, 1e-9) * npx).reshape(-1, 1)
    win = np.lib.stride_tricks.sliding_window_view(reg, (n, n)).reshape(-1, n * n)
    ncc = (win @ T0.T) / (sd * nt.reshape(1, -1))
    wi, ki = divmod(int(np.argmax(ncc)), ncc.shape[1])
    dy, dx = divmod(wi, 2 * rad + 1)
    best = float(ncc[wi, ki])
    bc = cls[ki]
    second = -2.0
    for j in range(ncc.shape[1]):
        v = float(ncc[wi, j])
        if per is not None:
            if v > per.get(cls[j], -2.0):
                per[cls[j]] = v
        if cls[j] != bc and v > second:
            second = v
    return best, bc, second, dx - rad, dy - rad


_MAX_COUNT = {}
for _c in "KABNRCP":
    _MAX_COUNT[_c] = 1 if _c == "K" else (5 if _c == "P" else 2)
    _MAX_COUNT[_c.lower()] = _MAX_COUNT[_c]


def _box_blur(img, k=COARSE_BLUR):
    """Separable box blur through cumulative sums (float32, edges replicated).

    Low passing both the patch and the templates throws away stroke weight and
    paper texture while keeping the shape of the glyph, which is what separates
    two art styles of the same character.
    """
    a = np.asarray(img, np.float32)
    if k <= 1:
        return a
    r = k // 2
    p = np.pad(a, ((r, r), (r, r)), mode="edge")
    c = np.cumsum(p, axis=0)
    c = np.vstack([np.zeros((1, c.shape[1]), np.float32), c])
    o = (c[k:, :] - c[:-k, :]) / np.float32(k)
    c = np.cumsum(o, axis=1)
    c = np.hstack([np.zeros((c.shape[0], 1), np.float32), c])
    return (c[:, k:] - c[:, :-k]) / np.float32(k)


_COARSE_CACHE = {}


def _match_prep_coarse(tpl, half):
    """Like _match_prep, but every template is blurred first."""
    key = (id(tpl), half, COARSE_BLUR)
    c = _COARSE_CACHE.get(key)
    if c is not None and c[0] is tpl:
        return c[1]
    n = 2 * half
    rows = []
    cls = []
    for t in sorted(tpl):
        for T in tpl[t]:
            q = _box_blur(_resize2d(np.asarray(T, np.float32), n))
            q = q - q.mean()
            rows.append(q.ravel())
            cls.append(t)
    T0 = np.asarray(rows, np.float32)
    nt = np.sqrt((T0 * T0).sum(axis=1)).astype(np.float32)
    prep = (cls, T0, nt)
    if len(_COARSE_CACHE) > 4:
        _COARSE_CACHE.clear()
    _COARSE_CACHE[key] = (tpl, prep)
    return prep


def _match_coarse(ap, cx, cy, prep, half, ox, oy, rad=COARSE_RAD):
    """Structure-level match on a blurred patch around a known offset.

    The sharp matcher is the right tool for most skins, but a stylised one (thin
    calligraphic glyphs on porcelain, painted on a moving background) can leave
    its hardest glyphs 0.10 below NCC_MIN_OCC - the red horse 傌 against a thick
    brush 傌 template reaches only 0.37.  Blurred, the same square scores 0.59
    while the emptiest squares of that board stay under 0.46, so the second look
    names a piece the first one had to throw away.

    Returns (score, piece, runner_up_score, dx, dy) or None.
    """
    cls, T0, nt = prep
    n = 2 * half
    m = n + 2 * rad
    x0 = int(round(cx + ox)) + PADV - half - rad
    y0 = int(round(cy + oy)) + PADV - half - rad
    H, W = ap.shape[0], ap.shape[1]
    if x0 < 0 or y0 < 0 or y0 + m > H or x0 + m > W:
        return None
    reg = _box_blur(ap[y0:y0 + m, x0:x0 + m].astype(np.float32).mean(axis=2))
    ii = np.zeros((m + 1, m + 1), np.float64)
    sq = np.zeros((m + 1, m + 1), np.float64)
    ii[1:, 1:] = reg
    sq[1:, 1:] = reg * reg
    np.cumsum(ii, 0, out=ii)
    np.cumsum(ii, 1, out=ii)
    np.cumsum(sq, 0, out=sq)
    np.cumsum(sq, 1, out=sq)
    s1 = ii[n:, n:] - ii[:-n, n:] - ii[n:, :-n] + ii[:-n, :-n]
    s2 = sq[n:, n:] - sq[:-n, n:] - sq[n:, :-n] + sq[:-n, :-n]
    npx = float(n * n)
    mean = s1 / npx
    sd = np.sqrt(np.maximum(s2 / npx - mean * mean, 1e-9) * npx).reshape(-1, 1)
    win = np.lib.stride_tricks.sliding_window_view(reg, (n, n)).reshape(-1, n * n)
    ncc = (win @ T0.T) / (sd * nt.reshape(1, -1))
    wi, ki = divmod(int(np.argmax(ncc)), ncc.shape[1])
    dy, dx = divmod(wi, 2 * rad + 1)
    best = float(ncc[wi, ki])
    bc = cls[ki]
    second = -2.0
    for j in range(ncc.shape[1]):
        if cls[j] != bc and float(ncc[wi, j]) > second:
            second = float(ncc[wi, j])
    return best, bc, second, ox + dx - rad, oy + dy - rad


def patch_ink(p, half):
    """Median red-minus-blue of a patch's glyph ink -> (value, npixels).

    None means "no opinion".  The ink is the darkest part of a disc's face, but
    the disc's own rim ring is dark and red too, so the sample is limited to the
    radius where the glyph lives and judged by the MEDIAN: the ring and the drop
    shadow are minorities there and a median ignores them.
    """
    lum = p.mean(axis=2) if p.ndim == 3 else p
    n = int(p.shape[0])
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(yy - n / 2.0, xx - n / 2.0)
    sel = (lum < INK_DARK_FRAC * float(np.median(lum))) & (r < INK_SAMPLE_R * half)
    k = int(sel.sum())
    if k < INK_MIN_PIX:
        return None, k
    rb = p[:, :, 0].astype(np.float32) - p[:, :, 2].astype(np.float32)
    return float(np.median(rb[sel])), k


def ink_side(p, half):
    """'w' (red ink), 'b' (dark ink) or None when the patch has no opinion."""
    val, _k = patch_ink(p, half)
    if val is None:
        return None
    if val >= INK_RED_MIN:
        return "w"
    if val <= INK_DARK_MAX:
        return "b"
    return None


def side_of(piece):
    return "w" if piece.isupper() else "b"


def _frame_patch(a, x, y, half):
    """(2*half)^2 RGB patch of the frame, edge-clipped like _square_patch."""
    H, W, _ = a.shape
    xi, yi = int(round(x)), int(round(y))
    y0, y1 = max(0, yi - half), min(H, yi + half)
    x0, x1 = max(0, xi - half), min(W, xi + half)
    p = a[y0:y1, x0:x1]
    if p.shape[0] != 2 * half or p.shape[1] != 2 * half:
        pad = ((0, 2 * half - p.shape[0]), (0, 2 * half - p.shape[1]), (0, 0))
        p = np.pad(p, pad, mode="edge")
    return p.astype(np.float32)


def _disc_near(a, x, y, ref, win=DISC_WIN, half=DISC_BOX):
    """(score, x, y) of the most disc-like blob within *win* of (x, y).

    The highlighted piece is drawn away from its intersection, so the offset
    windows of the matcher cannot be trusted to cover it.  The tile-distance
    mean peaks inside the disc whatever the glyph does, which is the same signal
    the occupancy cut uses - the caller compares the score against occ_min to
    tell a disc from a decorated empty square.
    """
    H, W, _ = a.shape
    x0, y0 = max(0, int(round(x)) - win), max(0, int(round(y)) - win)
    x1, y1 = min(W, int(round(x)) + win), min(H, int(round(y)) + win)
    sub = a[y0:y1, x0:x1]
    if (sub.shape[0] < 2 * half + 3 or sub.shape[1] < 2 * half + 3):
        return None
    m = _box_mean(dist_map(sub, ref), half)
    k = int(np.argmax(m))
    dy, dx = divmod(k, m.shape[1])
    return float(m[dy, dx]), float(x0 + dx + half), float(y0 + dy + half)


_SIDE_PREP = {}


def _side_prep(tpl, half, side):
    """One side's templates (or every template when *side* is None) as a prep."""
    key = (id(tpl), half, side)
    c = _SIDE_PREP.get(key)
    if c is not None and c[0] is tpl:
        return c[1]
    n = 2 * half
    rows, cls = [], []
    for t in sorted(tpl):
        if side is not None and (t.isupper() != (side == "w")):
            continue
        for T in tpl[t]:
            q = _resize2d(np.asarray(T, np.float32), n)
            rows.append((q - q.mean()).ravel())
            cls.append(t)
    T0 = np.asarray(rows, np.float32)
    nt = np.sqrt((T0 * T0).sum(axis=1)).astype(np.float32)
    prep = (cls, T0, nt)
    if len(_SIDE_PREP) > 6:
        _SIDE_PREP.clear()
    _SIDE_PREP[key] = (tpl, prep)
    return prep


def _match_far(a, x, y, tpl, half, side=None, scales=FAR_SCALES, rad=FAR_RAD,
               per=None):
    """Last-resort match for a piece drawn off-centre and/or enlarged.

    One window per scale is resampled so the templates keep their own size (a
    1.2x disc is squeezed back to the pack's scale) and searched over a small
    offset grid; the winner is only used when its class leads the others, which
    is the caller's gate.  Returns (score, piece, runner_up, dx, dy) with dx/dy
    in FRAME pixels, or None.
    """
    sup = _side_prep(tpl, half, side)
    if not sup[0]:
        return None
    H, W, _ = a.shape
    m = 2 * (half + rad)
    out = None
    for s in scales:
        h = int(np.ceil(half * s)) + int(np.ceil(rad * s))
        xi, yi = int(round(x)), int(round(y))
        x0, x1 = max(0, xi - h), min(W, xi + h)
        y0, y1 = max(0, yi - h), min(H, yi + h)
        if x1 - x0 < 12 or y1 - y0 < 12:
            continue
        reg = a[y0:y1, x0:x1].astype(np.float32)
        q = np.stack([_resize2d(reg[:, :, c], m) for c in range(3)], -1)
        # The resampled centre sits (0.5, 0.5) off a pixel centre when the window
        # is even sized; the matcher's own +-rad grid absorbs that.
        ap = np.pad(q, ((PADV, PADV), (PADV, PADV), (0, 0)), mode="edge")
        r = _match_cell(ap, half + rad, half + rad, sup, half, rad, per=per)
        if r is None:
            continue
        # the window was resampled by (x1-x0) -> m, so the offsets scale back
        fac = (float(x1 - x0) / m + float(y1 - y0) / m) * 0.5
        cand = (r[0], r[1], r[2], r[3] * fac, r[4] * fac, s)
        if out is None or cand[0] > out[0]:
            out = cand
    return out


def _match_with_hint(ap, x, y, prep, half, hint, rad, hint_rad, hint_ok):
    """Match one cell, reusing a known offset and widening only when it fails.

    The fitted model lands 0..5px off the painted sprite and the offset is a
    property of the square, not of the frame, so the wide 81-offset search only
    has to run once per square (or after a piece changes hands there).
    """
    if hint is None:
        return _match_cell(ap, x, y, prep, half, rad)
    r = _match_cell(ap, x + hint[0], y + hint[1], prep, half, hint_rad)
    r2 = None
    if r is None or r[0] < hint_ok:
        r2 = _match_cell(ap, x, y, prep, half, rad)
    if r is None:
        return r2
    if r2 is None or r[0] > r2[0]:
        return (r[0], r[1], r[2], r[3] + hint[0], r[4] + hint[1])
    return r2

def _square_patch(a, cal, i, j, half):
    """Frame pixels of one square, clipped to the frame."""
    H, W, _ = a.shape
    x, y = grid_xy(cal, i, j)
    xi, yi = int(round(x)), int(round(y))
    y0, y1 = max(0, yi - half), min(H, yi + half + 1)
    x0, x1 = max(0, xi - half), min(W, xi + half + 1)
    return a[y0:y1, x0:x1]


def _changed_cells(a, b, cal, half=CELL_SIG_HALF, tol=CHG_TOL):
    """Squares whose pixels moved since the previous frame.

    Scoring a square costs the same whether it changed or not, so the cheap
    test here is what makes the incremental read worth doing at all: a move
    touches a handful of squares, the rest can keep the piece they had.
    """
    out = []
    for j in range(10):
        for i in range(9):
            pa = _square_patch(a, cal, i, j, half)
            pb = _square_patch(b, cal, i, j, half)
            if pa.shape != pb.shape:
                out.append((i, j))
                continue
            d = np.maximum(pa, pb) - np.minimum(pa, pb)
            if int(d.max()) > tol:
                out.append((i, j))
    return out


def _square_score(a, cal, i, j, ref, half=BOX_HALF):
    """Tile distance of one square, measured the way piece_scores measures it."""
    p = _square_patch(a, cal, i, j, half)
    if p.size == 0:
        return 0.0
    d = np.abs(p.astype(np.int16) - np.asarray(ref, np.int16)).sum(axis=2)
    return float(d.mean())

def recognize(a, cal, tpl, loc=None, info=None, half=TPL_HALF, rad=MATCH_RAD,
              hints=None, hint_rad=HINT_RAD, hint_ok=HINT_OK, occ_min=None,
              prev=None):
    """Return (grid, scores); grid is 10 rows x 9 cols of piece chars.

    Occupancy is adaptive: the 90 cells are ranked by their distance from the
    skin tile colour and the cut sits a fixed fraction above the median, so a
    board painted in any colours still separates pieces from empty
    intersections.  A cell that clears the cut must ALSO match a piece template
    (NCC >= NCC_MIN_OCC) to be reported, which is what keeps decorated squares -
    river text, palace diagonals, the printed board marks - empty.

    If *info* is a dict it receives the per-cell disc centres under "centers" so
    that clicking can use the corrected sprite position instead of the raw model,
    plus the scores under "loc" and "margins", the offsets "offsets"/"hints",
    the scale "ref" the distances were measured against, and the cut that was
    used under "occ_min".

    *prev* is the optional (frame, info) pair of the previous read.  When it is
    given and no more than INCR_MAX_CELLS squares changed, only those squares are
    scored and matched again and the rest keep the piece the previous read found:
    a frame that follows a move costs a few milliseconds instead of a full pass.
    """
    grid = [["."] * 9 for _ in range(10)]
    scores = [[0.0] * 9 for _ in range(10)]
    margins = [[0.0] * 9 for _ in range(10)]
    offsets = [[(0, 0)] * 9 for _ in range(10)]
    centers = {}
    used = {}
    ref = None
    old = None
    changed = None
    if prev is not None and len(prev) == 2:
        pf, pi = prev
        if (pi and pi.get("loc") and pi.get("ref") is not None
                and getattr(pf, "shape", None) == a.shape):
            cand = _changed_cells(a, pf, cal)
            if len(cand) <= INCR_MAX_CELLS:
                old = pi
                changed = set(cand)
    if old is not None:
        # an incremental read: keep every square the move did not touch
        loc = dict(old["loc"])
        ref = old["ref"]
        grid = [list(r) for r in old["grid"]]
        scores = [list(r) for r in old["scores"]]
        margins = [list(r) for r in old["margins"]]
        for j in range(10):
            for i in range(9):
                offsets[j][i] = old["offsets"][j][i]
        centers = dict(old["centers"])
        used = dict(old["hints"])
        for (i, j) in changed:
            loc[(i, j)] = _square_score(a, cal, i, j, ref)
            grid[j][i] = "."
            scores[j][i] = 0.0
            margins[j][i] = 0.0
            offsets[j][i] = (0, 0)
            centers.pop((i, j), None)
            used.pop((i, j), None)
        if occ_min is None:
            lv = occ_level(loc)
            occ_min = lv[0] if lv is not None else None
        todo = []
        for (i, j) in changed:
            sc = loc.get((i, j), 0.0)
            if occ_min is not None and sc < occ_min:
                continue
            todo.append(((i, j), sc))
    else:
        if loc is None:
            scores90, _ctx, ref = cell_box_scores3(a, cal)
            loc = scores90
        if occ_min is None:
            lv = occ_level(loc)
            occ_min = lv[0] if lv is not None else None
        todo = []
        for k, v in loc.items():
            sc = v if isinstance(v, float) else v[0]
            if occ_min is not None and sc < occ_min:
                continue
            todo.append((k, sc))
    todo.sort(key=lambda kv: -kv[1])
    todo = todo[:OCC_MAX_CAND]
    ap = pad_frame(a)
    prep = _match_prep(tpl, half)
    cprep = None
    coarse = []
    far = []
    counts = {}
    for _j in range(10):
        for _i in range(9):
            if grid[_j][_i] != ".":
                counts[grid[_j][_i]] = counts.get(grid[_j][_i], 0) + 1
    for (i, j), _sc in todo:
        x, y = grid_xy(cal, i, j)
        h = hints.get((i, j)) if hints else None
        r = _match_with_hint(ap, x, y, prep, half, h, rad, hint_rad, hint_ok)
        if r is None:
            continue
        best, piece, second, dx, dy = r
        if best < hint_ok and rad < WIDE_RAD:
            # A skin whose tiles confuse the disc search can land the sprite model
            # a dozen pixels off; the glyph is still there, so give the matcher one
            # last, wider look before declaring the square empty.
            r2 = _match_cell(ap, x, y, prep, half, WIDE_RAD)
            if r2 is not None and r2[0] > best:
                best, piece, second, dx, dy = r2
        # Colour is the one cue that survives a stylised glyph, a colour-inverted
        # ink or a piece painted half off its square: the ink of a red piece is
        # red and the ink of a black one is not (measured +104 vs +7 on the
        # shipped skin), whatever the shape scores say.  It is only read when a
        # match is unconvincing - on a healthy board the shape already decided.
        want = None
        if best < SIDE_CHECK:
            want = ink_side(_frame_patch(a, x + dx, y + dy, half), half)
        wrong = want is not None and side_of(piece) != want
        disc = None
        if (want is not None or best < NCC_MIN_OCC) and ref is not None:
            # The square needs a second opinion, and the piece may be *lifted*
            # there (the app draws the one it is highlighting 20px off its
            # intersection and 1.2x big): locate the disc by the same
            # tile-distance the occupancy cut uses.  No disc, no second opinion -
            # an empty square crossed by the river text has ink-looking paint on
            # it too, so the disc is what tells the two apart.
            disc = _disc_near(a, x, y, ref)
            if disc is not None and occ_min is not None and disc[0] < occ_min:
                disc = None
        if best < NCC_MIN_OCC:
            # The square reads as occupied but no template explains it.  On a
            # stylised skin that is usually an art style the pack does not carry,
            # so retry blurred before throwing the piece away.
            if cprep is None:
                cprep = _match_prep_coarse(tpl, half)
            cr = _match_coarse(ap, x, y, cprep, half, dx, dy)
            if (cr is not None and cr[0] >= COARSE_MIN
                    and cr[0] - cr[2] >= COARSE_MARGIN
                    and cr[0] - best >= COARSE_GAIN
                    and counts.get(cr[1], 0) < _MAX_COUNT.get(cr[1], 2)
                    and (want is None or side_of(cr[1]) == want)):
                best, piece, second, dx, dy = cr[0], cr[1], cr[2], cr[3], cr[4]
                coarse.append((i, j))
        if disc is not None:
            # Search around the disc centre with the side the ink proves (or with
            # every class when the ink has no opinion) and at a few scales.
            fb = _far_look(a, disc, tpl, half, want, counts)
            if fb is not None:
                best, piece, second, dx, dy = fb
                far.append((i, j))
            elif wrong or best < NCC_MIN_OCC:
                continue
        elif wrong:
            # The ink proves the other side and there is no disc to overturn it:
            # a colour-flipped piece is worse than a missing one.  The rules check
            # downstream cannot tell a misread rook-as-rook from a real one, while
            # a square that reads empty is simply re-read.
            continue
        if best < NCC_MIN_OCC:
            continue
        counts[piece] = counts.get(piece, 0) + 1
        grid[j][i] = piece
        scores[j][i] = round(best, 3)
        margins[j][i] = round(best - second, 3)
        offsets[j][i] = (dx, dy)
        centers[(i, j)] = (x + dx, y + dy)
        used[(i, j)] = (dx, dy)
    if info is not None:
        info["centers"] = centers
        info["loc"] = loc
        info["margins"] = margins
        info["offsets"] = offsets
        info["hints"] = used
        info["occ_min"] = occ_min
        info["ref"] = ref
        info["grid"] = [list(r) for r in grid]
        info["scores"] = [list(r) for r in scores]
        info["changed"] = len(changed) if changed is not None else -1
        info["coarse"] = coarse
        info["far"] = far
    return grid, scores


def _far_look(a, disc, tpl, half, want, counts):
    """One last look for a lifted piece -> (score, piece, second, dx, dy) or None.

    *disc* is the located disc (score, x, y) from the caller - the lifted piece is
    not where the model says, so the match runs around the disc instead of the
    intersection.  The ink decides which side may answer (re-read at the disc when
    the first read had no opinion) and the match runs at a few scales because the
    lift also enlarges the sprite.  Returns None when nothing clears the gates.
    """
    _dsc, px, py = disc
    if want is None:
        want = ink_side(_frame_patch(a, px, py, half), half)
    per = {}
    r = _match_far(a, px, py, tpl, half, want, per=per)
    if r is None:
        return None
    score, piece = r[0], r[1]
    if score < FAR_MIN or counts.get(piece, 0) >= _MAX_COUNT.get(piece, 2):
        return None
    second = -2.0
    for c, v in per.items():
        if c != piece and v > second:
            second = v
    if score - second < FAR_MARGIN:
        return None
    return score, piece, second, r[3], r[4]

def grid_to_fen(grid):
    return "/".join("".join(r) for r in grid)


def fen_to_grid(fen):
    grid = []
    for part in fen.split("/")[:10]:
        row = []
        for ch in part:
            row.extend(["."] * int(ch) if ch.isdigit() else [ch])
        grid.append(row[:9] + ["."] * max(0, 9 - len(row)))
    return grid


def draw_grid(grid):
    out = []
    for j, row in enumerate(grid):
        out.append("row%d  %s" % (j, " ".join(PIECE_NAME.get(c, c) for c in row)))
    return "\n".join(out)