
import sys, time, numpy as np
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import vision as V, board as B
from PIL import Image

a = np.asarray(Image.open(r'D:\BuildProject\pikayu-jj\fixtures\skin_now.png').convert('RGB'))
cal = V.calibrate(a)
tpl, half = V.load_templates(cal=cal)
info0 = {}
g0, s0 = V.recognize(a, cal, tpl, half=half, info=info0)
print('cold  FEN', B.grid_to_fen(g0, 'w'))
# --- synthesise one move: red cannon (1,7) -> (4,7), source refilled from an
#     empty square of the same row so the patch looks like a played board
R = 38
def centre(i, j):
    x, y = V.grid_xy(cal, i, j)
    return int(round(x)), int(round(y))
sx, sy = centre(1, 7)
ex, ey = centre(3, 7)
dx, dy = centre(4, 7)
b = a.copy()
b[sy - R:sy + R, sx - R:sx + R] = a[ey - R:ey + R, ex - R:ex + R]
b[dy - R:dy + R, dx - R:dx + R] = a[sy - R:sy + R, sx - R:sx + R]
Image.fromarray(b).save(r'D:\BuildProject\pikayu-jj\incr_frame.png')
ch = V._changed_cells(b, a, cal)
print('changed cells', len(ch), sorted(ch)[:12])
info1 = {}
g1, s1 = V.recognize(b, cal, tpl, half=half, info=info1)
info2 = {}
g2, s2 = V.recognize(b, cal, tpl, half=half, info=info2, prev=(a, info0))
print('cold  after FEN', B.grid_to_fen(g1, 'w'))
print('incr  after FEN', B.grid_to_fen(g2, 'w'))
print('EQUAL', g1 == g2, ' changed flag', info2.get('changed'))
# timings on a settled repeat
t0 = time.time()
for _ in range(20): V.recognize(a, cal, tpl, half=half)
full = (time.time() - t0) / 20
i_prev = {}
V.recognize(a, cal, tpl, half=half, info=i_prev)
t0 = time.time()
for _ in range(20): V.recognize(a, cal, tpl, half=half, prev=(a, i_prev))
incr = (time.time() - t0) / 20
# per-square score agreement between the two metrics
sc_full, ctx, ref = V.cell_box_scores3(a, cal)
worst = 0.0
for (i, j), v in sc_full.items():
    q = V._square_score(a, cal, i, j, ref)
    worst = max(worst, abs(q - v))
print('full %.2f ms  incremental %.2f ms  max |square_score - piece_scores| %.3f  ref %s' % (
    full * 1e3, incr * 1e3, worst, ref))
