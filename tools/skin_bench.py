
import sys, os, time, json
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
import numpy as np
from PIL import Image
from pikafishjj import vision as V, board as B

ROOT = r'D:\BuildProject\pikayu-jj'
OUT = os.path.join(ROOT, 'dbg', 'skins')
os.makedirs(OUT, exist_ok=True)
OPEN = B.OPENING_FEN.split()[0]
EGRID = B.fen_to_grid(B.OPENING_FEN)
FIXTURES = [('wood', os.path.join(ROOT, 'fixtures', 'jj_orig.png')),
            ('stone', os.path.join(ROOT, 'fixtures', 'skin_now.png'))]

# name, base rgb, line rgb, line width, decor
SKINS = [
    ('wood',          (205, 163, 101), (110, 80, 50),   2, 0),
    ('stone_bright',  (135, 142, 138), (225, 228, 224), 2, 0),
    ('navy',          (38, 58, 105),   (140, 175, 225), 2, 1),
    ('green',         (58, 105, 75),   (30, 55, 40),    2, 1),
    ('ivory',         (242, 236, 222), (205, 196, 180), 3, 0),
    ('charcoal',      (52, 52, 56),    (105, 105, 112), 2, 1),
    ('purple',        (105, 68, 140),  (62, 32, 92),    3, 0),
    ('sand_decor',    (198, 186, 158), (168, 148, 110), 2, 2),
    ('white_marble',  (238, 240, 242), (180, 185, 190), 2, 0),
    ('blue_thick',    (45, 70, 120),   (200, 215, 235), 6, 1),
    ('sepia_noline',  (188, 166, 128), (186, 164, 126), 2, 0),
]

def build(a, cal, base, line, w, decor, tile):
    f = a.copy()
    H, W = f.shape[:2]
    cx, cy = cal['cx'], cal['cy']
    x0 = max(0, int(cx[0] - 34)); x1 = min(W, int(cx[8] + 34))
    y0 = max(0, int(cy[0] - 36)); y1 = min(H, int(cy[9] + 36))
    f[y0:y1, x0:x1] = np.array(base, np.uint8)
    for c in cx:
        c = int(round(c)); f[y0:y1, max(0, c - w // 2):c - w // 2 + w] = line
    for r in cy:
        r = int(round(r)); f[max(0, r - w // 2):r - w // 2 + w, x0:x1] = line
    if decor >= 1:                      # palace diagonals + river band, like a decorated skin
        for (c0, c1, r0, r1) in ((3, 5, 0, 2), (3, 5, 7, 9)):
            for t in range(0, 61):
                cc = int(round(cx[c0] + (cx[c1] - cx[c0]) * t / 60.0))
                rr = int(round(cy[r0] + (cy[r1] - cy[r0]) * t / 60.0))
                f[max(0, rr - 1):rr + 1, max(0, cc - 1):cc + 1] = line
                rr2 = int(round(cy[r1] + (cy[r0] - cy[r1]) * t / 60.0))
                f[max(0, rr2 - 1):rr2 + 1, max(0, cc - 1):cc + 1] = line
        r4, r5 = int(cy[4]), int(cy[5])
        f[r4:r5, x0:x1] = np.minimum(f[r4:r5, x0:x1].astype(np.int16) + 12, 255).astype(np.uint8)
    if decor >= 2:                      # noisy decorations outside the board rectangle
        rng = np.random.RandomState(7)
        for _ in range(40):
            bw = rng.randint(8, 40); bh = rng.randint(8, 40)
            bx = rng.randint(0, W - bw); by = rng.randint(0, H - bh)
            if x0 - 20 <= bx <= x1 + 20 and y0 - 20 <= by <= y1 + 20:
                continue
            col = tuple(int(v) for v in rng.randint(0, 255, 3))
            f[by:by + bh, bx:bx + bw] = np.array(col, np.uint8)
    R = 34
    ref = np.asarray(tile, np.int16)
    for j in range(10):
        for i in range(9):
            if EGRID[j][i] == '.':
                continue
            x, y = V.grid_xy(cal, i, j)
            xi, yi = int(round(x)), int(round(y))
            # Clip at the frame edge instead of skipping the piece: the corner
            # pieces sit close enough to the border that a slightly different
            # calibration model would silently drop them and the frame would
            # then disagree with the expected grid for no real reason.
            x_lo, x_hi = max(0, xi - R), min(W, xi + R + 1)
            y_lo, y_hi = max(0, yi - R), min(H, yi + R + 1)
            if x_hi <= x_lo or y_hi <= y_lo:
                continue
            ya, xa = np.mgrid[y_lo:y_hi, x_lo:x_hi]
            my = ya - yi
            mx = xa - xi
            s = a[y_lo:y_hi, x_lo:x_hi]
            # The disc, plus the piece's own drop shadow under it.  A plain big
            # circle would also copy the old tiles around the piece, which no real
            # skin swap leaves behind - the game repaints the whole board.
            m = (my * my + mx * mx) <= 27 * 27
            d = np.abs(s.astype(np.int16) - ref).sum(axis=2)
            m |= (d > 70) & (my > 6) & (my * my + mx * mx <= 34 * 34)
            dst = f[y_lo:y_hi, x_lo:x_hi]
            dst[m] = s[m]
    return f

def stats(info, grid):
    occ = [info['loc'][k] for k in info['loc'] if grid[k[1]][k[0]] != '.']
    emp = [info['loc'][k] for k in info['loc'] if grid[k[1]][k[0]] == '.']
    return (min(occ) if occ else -1), (max(emp) if emp else -1)

rows = []
for fx, path in FIXTURES:
    a = np.asarray(Image.open(path).convert('RGB'))
    t0 = time.time()
    cal = V.calibrate(a)
    tc = time.time() - t0
    if not cal:
        print('BASE %s: calibrate FAILED' % fx); continue
    tpl, half = V.load_templates(cal=cal)
    info = {}
    grid, sc = V.recognize(a, cal, tpl, info=info, half=half)
    base_ok = B.grid_to_fen(grid).split()[0] == OPEN
    print('BASE %s cal %.3fs discs %s resid %.2f dev %.2f  model %s  opening=%s'
          % (fx, tc, cal.get('ndiscs'), cal.get('resid') or -1, cal.get('resid') or -1, bool(cal.get('model')), base_ok))
    band = (int(cal['cy'][0] - 30), int(cal['cy'][9] + 30), int(cal['cx'][0] - 20), int(cal['cx'][8] + 20))
    tile = V.tile_colour(a, band)
    for name, base, line, w, decor in SKINS:
        f = build(a, cal, base, line, w, decor, tile)
        Image.fromarray(f).save(os.path.join(OUT, '%s_%s.png' % (fx, name)))
        t0 = time.time(); c2 = V.calibrate(f); dt = time.time() - t0
        if not c2:
            rows.append((fx, name, 'CAL-FAIL', '', '', '', '')); print('%-15s %-14s CAL-FAIL' % (fx, name)); continue
        tpl2, half2 = V.load_templates(cal=c2)
        info2 = {}
        g2, s2 = V.recognize(f, c2, tpl2, info=info2, half=half2)
        fen = B.grid_to_fen(g2).split()[0]
        om, em = stats(info2, g2)
        ok = (fen == OPEN)
        ncc = min([s2[j][i] for j in range(10) for i in range(9) if g2[j][i] != '.'] or [0])
        dev = max(max(abs(V.grid_xy(c2, i, j)[0] - V.grid_xy(cal, i, j)[0]),
                      abs(V.grid_xy(c2, i, j)[1] - V.grid_xy(cal, i, j)[1]))
                  for j in range(10) for i in range(9))
        rows.append((fx, name, 'OK' if ok else 'WRONG', '%.2f' % (c2.get('resid') or -1),
                     '%s' % (c2.get('ndiscs')), '%.2f/%.2f' % (om, em), '%.2f' % ncc))
        print('%-15s %-14s %-6s %-13s discs %-3s resid %-6s dev %5.1f loc %.2f/%.2f ncc %.2f'
              % (fx, name, 'OK' if ok else 'WRONG', c2.get('lattice'), c2.get('ndiscs'),
                 '%.2f' % (c2.get('resid') or -1), dev, om, em, ncc))
        if not ok:
            print('    got  ' + fen)
            print('    want ' + OPEN)
print('PASS %d / %d' % (sum(1 for r in rows if r[2] == 'OK'), len(rows)))
