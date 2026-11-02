
import sys, time, numpy as np
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import vision as V, board as B
from pikafishjj.auto import AutoPlayer
from PIL import Image

a = np.asarray(Image.open(r'D:\BuildProject\pikayu-jj\fixtures\skin_now.png').convert('RGB'))

p = AutoPlayer(dry=True, verbose=False)
p.cal = V.calibrate(a)
p.tpl, p.tpl_half = V.load_templates(cal=p.cal)
p.flip = False

# synthesise one move: red cannon (1,7) -> (4,7); the source square is refilled
# from an empty square of the same row so the frame looks like a played board
R = 38
def centre(i, j):
    x, y = V.grid_xy(p.cal, i, j)
    return int(round(x)), int(round(y))
sx, sy = centre(1, 7)
ex, ey = centre(3, 7)
dx, dy = centre(4, 7)
b = a.copy()
b[sy - R:sy + R, sx - R:sx + R] = a[ey - R:ey + R, ex - R:ex + R]
b[dy - R:dy + R, dx - R:dx + R] = a[sy - R:sy + R, sx - R:sx + R]
ch = V._changed_cells(b, a, p.cal)
print('changed cells', len(ch), sorted(ch)[:12])

def call(f):
    t0 = time.perf_counter()
    g = p._recognize(f)
    return g, (time.perf_counter() - t0) * 1000.0

g1, t1 = call(a)
g2, t2 = call(b)
g3, t3 = call(a)
g4, t4 = call(b)
print('1st (cold)  %.1f ms  FEN %s' % (t1, B.grid_to_fen(g1, 'w')))
print('2nd (incr)  %.1f ms  FEN %s' % (t2, B.grid_to_fen(g2, 'w')))
print('3rd (incr)  %.1f ms  FEN %s' % (t3, B.grid_to_fen(g3, 'w')))
print('4th (incr)  %.1f ms  FEN %s' % (t4, B.grid_to_fen(g4, 'w')))
print('grids repeat: a==a', g1 == g3, ' b==b', g2 == g4)

# reference: a cold (no prev) read of the moved frame
info = {}
gc, _ = V.recognize(b, p.cal, p.tpl, half=p.tpl_half, info=info)
print('cold reference equals incremental:', gc == g2)
print('stats', p.stats['recognitions'], 'recognitions,', p.stats['incr'], 'incremental,',
      'total %.1f ms' % p.stats['recog_ms'])
print('INCR2 ' + ('OK' if (g1 == g3 and g2 == g4 and gc == g2) else 'FAIL'))
