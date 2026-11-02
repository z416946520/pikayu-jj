# -*- coding: utf-8 -*-
"""Find the mini-program's request dialog (opponent asks for a draw or an undo).

Every request reuses the same panel and only the text changes, so the dialog is
recognised by its buttons rather than by its wording: a large solid red
rectangle on the left (拒绝 / decline) next to a large solid olive-green
rectangle on the right (同意 / accept).  Measured fills on a real capture:
red rgb(223, 85, 66), green rgb(143, 162, 63); the panel behind them is beige
rgb(~222, 203, 172) and the board never contains a solid block of either shade.
"""
import numpy as np

MIN_ROW_FRAC = 0.075       # matching pixels in one row before it counts
MIN_RUN_FRAC = 0.020       # shortest button, as a fraction of the frame height
WIDTH_FRAC = (0.07, 0.55)  # button width span, as a fraction of the frame width
FILL_MIN = 0.55            # solidity inside the button's bounding box
MID_FRAC = (0.20, 0.80)    # the panel lives in the middle of the screen


def _masks(a):
    R = a[:, :, 0].astype(np.int16)
    G = a[:, :, 1].astype(np.int16)
    B = a[:, :, 2].astype(np.int16)
    red = (R > 170) & (G < 115) & (B < 115) & ((R - G) > 80)
    grn = (G > 120) & ((G - B) > 55) & ((G - R) > 8)
    return red, grn


def _blob(m, W, H):
    """Largest solid bar in a boolean mask -> (x0, y0, x1, y1) or None."""
    rows = m.sum(axis=1)
    need = max(24, int(MIN_ROW_FRAC * W))
    min_h = max(12, int(MIN_RUN_FRAC * H))
    lo, hi = WIDTH_FRAC[0] * W, WIDTH_FRAC[1] * W
    best = None
    y = 0
    n = rows.size
    while y < n:
        if rows[y] < need:
            y += 1
            continue
        y2 = y
        while y2 + 1 < n and rows[y2 + 1] >= need:
            y2 += 1
        h = y2 - y + 1
        if h >= min_h:
            cols = m[y:y2 + 1].sum(axis=0)
            cs = np.where(cols >= 0.4 * h)[0]
            if cs.size:
                x0, x1 = int(cs.min()), int(cs.max())
                w = x1 - x0 + 1
                if lo <= w <= hi and m[y:y2 + 1, x0:x1 + 1].mean() >= FILL_MIN:
                    cand = (x0, y, x1, y2)
                    if best is None or (x1 - x0) * h > (best[2] - best[0]) * (best[3] - best[1]):
                        best = cand
        y = y2 + 1
    return best


def _centre(b):
    return ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


CONT_FRAC = 0.84           # the rematch button lives in the bottom eighth
CONT_W_FRAC = (0.22, 0.80)  # ... as a wide capsule
CONT_MIN_H_FRAC = 0.025    # shortest rematch button, as a fraction of the height
CONT_FILL_MIN = 0.55       # solidity inside its bounding box


def find_continue(a):
    """Locate the result screen's 再来一局 (play again) button.

    The board's own button row (沙盘 / 悔棋 / 支招 ...) is gold and sits higher
    up, and the request panel's 同意 is olive but lives in the middle of the
    screen next to a red 拒绝, so a large solid green capsule low in the frame
    with no red button beside it is the rematch button.  Measured on a real
    capture (601x1121): box x 190..412, y 1003..1068, fill 0.63, centre
    (301, 1035).

    Returns {'point': (x, y), 'box': (x0, y0, x1, y1)} or None.
    """
    H, W = a.shape[:2]
    y0 = int(H * CONT_FRAC)
    sub = a[y0:]
    red, grn = _masks(sub)
    rows = grn.sum(axis=1)
    need = max(24, int(MIN_ROW_FRAC * W))
    min_h = max(12, int(CONT_MIN_H_FRAC * H))
    lo, hi = CONT_W_FRAC[0] * W, CONT_W_FRAC[1] * W
    best = None
    y = 0
    n = rows.size
    while y < n:
        if rows[y] < need:
            y += 1
            continue
        y2 = y
        while y2 + 1 < n and rows[y2 + 1] >= need:
            y2 += 1
        h = y2 - y + 1
        if h >= min_h:
            cols = grn[y:y2 + 1].sum(axis=0)
            cs = np.where(cols >= 0.4 * h)[0]
            if cs.size:
                x0, x1 = int(cs.min()), int(cs.max())
                w = x1 - x0 + 1
                if lo <= w <= hi and grn[y:y2 + 1, x0:x1 + 1].mean() >= CONT_FILL_MIN:
                    # A red button on the same rows means this is the request
                    # panel (拒绝 / 同意), never the rematch button.
                    band = red[y:y2 + 1]
                    if band.any():
                        rc = np.where(band.sum(axis=0) >= 0.4 * h)[0]
                        if rc.size and (int(rc.max()) - int(rc.min()) + 1) >= 0.4 * w:
                            y = y2 + 1
                            continue
                    area = w * h
                    if best is None or area > best[0]:
                        best = (area, (x0, y + y0, x1, y2 + y0))
        y = y2 + 1
    if best is None:
        return None
    box = best[1]
    return {"point": _centre(box), "box": box}


def find_request(a):
    """Locate the request panel.

    Returns a dict with 'decline' and/or 'accept' screen points (frame pixels),
    a 'box' around the buttons and 'buttons' (1 or 2), or None when no panel is
    on screen.
    """
    H, W = a.shape[:2]
    y0 = int(H * 0.12)          # the panel never reaches the edges
    sub = a[y0:int(H * 0.88)]
    red, grn = _masks(sub)
    rb = _blob(red, W, H)
    gb = _blob(grn, W, H)
    if rb is not None and gb is not None:
        cr, cg = _centre(rb), _centre(gb)
        AH = sub.shape[0]
        if abs(cr[1] - cg[1]) > 0.06 * AH:
            return None                      # not side by side - not this panel
        if gb[0] < rb[2] - 0.02 * W:
            return None                      # overlapping: one is not a button
        lo, hi = MID_FRAC[0] * AH, MID_FRAC[1] * AH
        if not (lo <= cr[1] <= hi and lo <= cg[1] <= hi):
            return None
        box = (min(rb[0], gb[0]), min(rb[1], gb[1]) + y0,
               max(rb[2], gb[2]), max(rb[3], gb[3]) + y0)
        return {"decline": (cr[0], cr[1] + y0), "accept": (cg[0], cg[1] + y0),
                "box": box, "buttons": 2}
    one = rb if rb is not None else gb
    if one is None:
        return None
    cy = _centre(one)[1]
    if not (MID_FRAC[0] * sub.shape[0] <= cy <= MID_FRAC[1] * sub.shape[0]):
        return None                          # a red piece is not a dialog
    key = "decline" if rb is not None else "accept"
    c = _centre(one)
    return {key: (c[0], c[1] + y0), "box": (one[0], one[1] + y0, one[2], one[3] + y0),
            "buttons": 1}
