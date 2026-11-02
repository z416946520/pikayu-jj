
"""Render the console with a real position and capture it (PrintWindow)."""
import io, os, sys, tkinter as tk
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import gui, board as B, w32
from PIL import Image
w32.set_dpi_aware()
root = tk.Tk()
app = gui.App(root)
FEN = 'r1bakab1r/9/1cn3c1n/p1p1p1p1p/9/2P3P2/P3P3P/1CN4C1/9/R1BAKABNR w - - 0 1'
class Stub(object):
    our_side = 'w'; flip = False; background = True; quiet = True; request = 'decline'
    cal = {'ndiscs': 20}; tpl = dict((c, [1]) for c in 'rnbakcpRNBAKCP')
    grid = B.fen_to_grid(FEN); engine = None
    stats = {"moves": 6, "reads": 41, "recognitions": 41, "frames": 41, "hint_hits": 38,
             "incr": 35, "dialogs": 1, "bg_fallback": 0, "grab_ms": 430.0, "recog_ms": 690.0,
             "think_ms": 0.0, "fen": FEN, "best": "c3c4", "depth": 24,
             "score": 137, "nodes": 4827764, "nps": 3300000, "phase": "playing", "turn": "轮到红方"}
app.player = Stub()
app.v["tpl"].set("模板包：14 类")
app.v["win"].set("598x1119 @ (1913,95) hwnd=1052916")
app.l_win.configure(style="Chip.TLabel")
app._draw_board(*app._view(app.player, Stub.grid, (7, 7), (4, 7)))
app._refresh_info(app.player)
app._tick(app.player)
app._append("[attach] client 598x1119 at (1913,95) flip=False discs 20/20 resid 3.15")
app._append("[engine] Pikafish 2026-09-06")
app._append("[best] c3c4  depth=24 cp=137 nodes=4827764  1.20s")
app._append("    click (2,6)->(2,5) screen (2106,742)->(2106,681)")
app._append("[play] confirmed c3 -> c4")
app._append("    [wait] the opponent replied before we could read")
app._append("[dialog] the opponent sent a request (2 button(s) on screen)")
app._append("[dialog] decline -> click screen (2123,683)")
root.geometry('1150x880+80+40')   # keep the whole window on screen: PrintWindow
root.update_idletasks(); root.update()   # only renders what the desktop shows
for i in range(30):
    root.update()
    root.after(20)
    import time; time.sleep(0.02)
app.player = None
for i in range(10):
    root.update(); time.sleep(0.02)
w32.set_dpi_aware()
hwnd = None
for h, t, c, p in w32.list_windows():
    if 'pikafishjj' in t.lower():
        hwnd = h
print('hwnd', hwnd)
g = w32.WindowGrabber()
a = g.grab(hwnd)
print('frame', None if a is None else a.shape)
if a is not None:
    Image.fromarray(a).save(r'D:\BuildProject\pikayu-jj\gui_board.png')
    print('saved', os.path.getsize(r'D:\BuildProject\pikayu-jj\gui_board.png'))
g.close()
root.destroy()
print('done')
