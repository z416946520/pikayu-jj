
import sys
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
import tkinter as tk
from pikafishjj import board as B
from pikafishjj import gui

class P(object):
    def __init__(self, side):
        self.grid = B.fen_to_grid(B.OPENING_FEN)
        self.our_side = side
        self.stats = {}

root = tk.Tk()
root.withdraw()
app = gui.App(root)
g0 = B.fen_to_grid(B.OPENING_FEN)
for side in ('w', 'b'):
    p = P(side)
    v, f, t = app._view(p, p.grid, (0, 9), (1, 7))
    if side == 'w':
        ok = v is p.grid and f == (0, 9) and t == (1, 7)
    else:
        ok = (v[0][0] == g0[9][8] and v[9][8] == g0[0][0] and f == (8, 0) and t == (7, 2))
    print('side %s view ok %s  view row0 %s  row9 %s  from %s to %s' % (side, ok, ''.join(v[0]), ''.join(v[9]), f, t))
    app._draw_board(v, f, t)
    print('   canvas items', len(app.canvas.find_all()))
root.destroy()
print('GUIVIEW OK')
