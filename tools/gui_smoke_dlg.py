
import sys, tkinter as tk
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import gui, board as B

root = tk.Tk()
app = gui.App(root)
root.update()
print('request var:', app.v['request'].get(), '| DEFAULTS', gui.DEFAULTS['request'])
for lab in list(gui.REQUESTS):
    app.v['request'].set(lab)
    c = app._collect()
    print('  %-14s -> %s' % (lab, c.get('request') if c else None))
app.v['request'].set('拒绝 (默认)')

class Stub(object):
    our_side = 'w'
    flip = False
    background = True
    quiet = True
    request = 'decline'
    cal = {'ndiscs': 20}
    tpl = {'a': [1]}
    grid = B.fen_to_grid(B.OPENING_FEN)
    engine = None
    stats = {"moves": 3, "reads": 9, "recognitions": 9, "frames": 9, "hint_hits": 4,
             "incr": 8, "dialogs": 2, "bg_fallback": 1, "grab_ms": 90.0, "recog_ms": 100.0,
             "think_ms": 0.0, "fen": B.OPENING_FEN, "best": "h2e2", "depth": 20,
             "score": 30, "nodes": 1000, "nps": 2000000, "phase": "playing"}
app.player = Stub()
app._refresh_info(app.player)
txt = app.info.get('1.0', 'end')
root.update()
print('---- info panel ----')
print(txt)
ok = ('后台模式' in txt) and ('对方请求' in txt) and ('拒绝' in txt)
print('SMOKE OK' if ok else 'SMOKE FAIL')
root.destroy()
