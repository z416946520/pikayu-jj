
import sys, numpy as np
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import vision as V
from PIL import Image
for name in sys.argv[1:]:
    p = r'D:\BuildProject\pikayu-jj\dbg\skins\%s.png' % name
    a = np.asarray(Image.open(p).convert('RGB'))
    H, W, _ = a.shape
    half = V.BOX_HALF
    ref = V.tile_colour(a)
    non = (V.dist_map(a, ref) > V.TILE_DIST).astype(np.float32)
    tb = V._tile_band(a, ref)
    print('== %s %s ref %s band %s' % (name, a.shape, ref, tb))
    if tb is None:
        y0, y1, x0, x1 = int(0.18*H), int(0.88*H), int(0.02*W), int(0.98*W)
    else:
        y0, y1, x0, x1 = tb
    m = V._box_mean(non, half)
    B = 8
    h = (m.shape[0]//B)*B; w = (m.shape[1]//B)*B
    blk = m[:h, :w].reshape(h//B, B, w//B, B).max(axis=(1,3))
    ry0 = max(0, y0-half); rx0 = max(0, x0-half)
    sub = m[ry0:y1-half+1, rx0:x1-half+1]
    lo = float(np.median(sub)); top = float(np.percentile(sub, 99.5))
    thr = lo + 0.45*(top-lo)
    ys, xs = np.nonzero(blk >= thr)
    order = np.argsort(-blk[ys, xs])
    pts = []
    for k in order:
        cy = (ys[k]+0.5)*B + half; cx = (xs[k]+0.5)*B + half
        if cy < y0-24 or cy > y1+24 or cx < x0-24 or cx > x1+24: continue
        if all((cx-q[0])**2 + (cy-q[1])**2 > V.PIECE_SEP**2 for q in pts): pts.append((cx, cy))
        if len(pts) >= 40: break
    seen = []
    for cx, cy in pts:
        gx, gy = V._mask_centroid(non, int(round(cx)), int(round(cy)), 0.5, rad=22)
        if all((gx-q[0])**2 + (gy-q[1])**2 > 0.25*V.PIECE_SEP**2 for q in seen): seen.append((gx, gy))
    hh, ww = float(y1-y0+1), float(x1-x0+1)
    cxr = (0.72*ww/8.0, 1.35*ww/8.0); ryr = (0.72*hh/9.0, 1.35*hh/9.0)
    cf = V._fit_comb([q[0] for q in seen], 9, 0.5*(x0+x1), prange=cxr)
    rf = V._fit_comb([q[1] for q in seen], 10, 0.5*(y0+y1), prange=ryr)
    print('   peaks %d centroids %d  cfit %s  rfit %s' % (len(pts), len(seen), cf, rf))
    print('   y coords', sorted(round(q[1], 1) for q in seen))
    lat = V._lattice_pieces(a, verbose=True)
    print('   lattice_pieces ->', None if lat is None else (round(lat['co'],2), round(lat['cpitch'],2), round(lat['ro'],2), round(lat['rpitch'],2)))
