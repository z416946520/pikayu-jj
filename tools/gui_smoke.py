import sys, os
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
os.chdir(r'D:\BuildProject\pikayu-jj\pikafishjj')
import tkinter as tk
from pikafishjj import gui, board as B


class P(object):
    pass


def main():
    root = tk.Tk()
    app = gui.App(root)
    root.update()
    print('PLACEHOLDER:', app.info.get('1.0', 'end').strip().replace(chr(10), ' | '))
    p = P()
    p.grid = B.fen_to_grid(B.OPENING_FEN)
    p.our_side = 'w'
    p.stats = {"moves": 3, "reads": 12, "recognitions": 9, "frames": 30, "hint_hits": 7,
               "recog_ms": 250.0, "grab_ms": 420.0, "think_ms": 1200.0,
               "fen": B.OPENING_FEN, "best": "h2e2", "depth": 18, "score": 30,
               "nodes": 1234567, "nps": 3400000, "phase": "thinking"}
    app._refresh_info(p)
    print('INFO:', app.info.get('1.0', 'end').strip().replace(chr(10), ' | '))
    app._draw_board(p.grid, (7, 7), (4, 7))
    print('canvas items:', len(app.canvas.find_all()))
    root.after(80, root.destroy)
    root.mainloop()
    print('SMOKE OK')


main()
