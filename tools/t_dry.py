import sys
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
import numpy as np
from PIL import Image
from pikafishjj import auto, board as B, vision as V

a = np.asarray(Image.open(r'D:\BuildProject\pikayu-jj\fixtures\jj_orig.png').convert('RGB'))
cal = V.calibrate(a, verbose=False)
print('cal discs %s model %s' % (cal['ndiscs'], bool(cal.get('model'))))


class E(object):
    name = 'stub'

    def bestmove(self, fen, movetime=2000, depth=None, extra=()):
        return 'h2e2', None, ['info depth 12 score cp 30 nodes 100000 nps 1000000 pv h2e2']

    def quit(self):
        pass


p = auto.AutoPlayer(dry=True, verbose=True)
p.cal = cal
p.hwnd = 0
p.grid = B.fen_to_grid(B.OPENING_FEN)
p.engine = E()
p.stable_grid = lambda timeout=8.0, need=3, interval=0.03: (B.fen_to_grid(B.OPENING_FEN), None)
g = p.run(max_moves=1, first='me')
print('RETURNED', B.grid_to_fen(g, 'w').split(' ')[0])
print('STATS moves=%s phase=%s best=%s depth=%s' % (
    p.stats['moves'], p.stats['phase'], p.stats['best'], p.stats['depth']))
print('DRY TEST OK')
