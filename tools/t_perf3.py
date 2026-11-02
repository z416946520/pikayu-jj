
import sys, time, numpy as np
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import w32, vision as V, board as B
from PIL import Image

h = 1119; w = 598
frames = [np.asarray(Image.open(r'D:\BuildProject\pikayu-jj\fixtures\skin_now.png').convert('RGB'))]
a = frames[0]
t0 = time.time(); cal = V.calibrate(a); tcal = time.time() - t0
tpl, half = V.load_templates(cal=cal)
info = {}
grid, sc = V.recognize(a, cal, tpl, half=half, info=info)
print('cal %.3fs lattice %s FEN %s' % (tcal, cal.get('lattice'), B.grid_to_fen(grid, 'w')))
N = 20
anchors = [a.copy() for _ in range(N)]
t0 = time.time()
for f in anchors: V.recognize(f, cal, tpl, half=half)
cold = (time.time() - t0) / N
hints = info['hints']
t0 = time.time()
for f in anchors: V.recognize(f, cal, tpl, half=half, hints=hints)
hinted = (time.time() - t0) / N
cent = info['centers']
xy = [(int(V.grid_xy(cal, i, j)[0]), int(V.grid_xy(cal, i, j)[1])) for j in range(10) for i in range(9)]
def sig(f):
    out = []
    for (cx, cy) in xy:
        p = f[cy - 16:cy + 16, cx - 16:cx + 16]
        out.append(int(p[:, :, 0].sum()) + 3 * int(p[:, :, 1].sum()) + 7 * int(p[:, :, 2].sum()))
    return out
t0 = time.time()
for f in anchors: sig(f)
sigt = (time.time() - t0) / N
gb = w32.ScreenGrabber()
t0 = time.time()
for _ in range(N): gb.grab(100, 100, w, h)
grabt = (time.time() - t0) / N
print('recognise cold %.2f ms  hinted %.2f ms  cell-signature %.2f ms  grab %dx%d %.2f ms' % (
    cold * 1e3, hinted * 1e3, sigt * 1e3, w, h, grabt * 1e3))
