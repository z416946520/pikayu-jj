import os
import sys
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
import tkinter as tk
from pikafishjj import gui as G

root = tk.Tk()
root.withdraw()
app = G.App(root)
print('loaded from cfg :', repr(app.v['side'].get()), '->', G.SIDES.get(app.v['side'].get()))
app.cfg = dict(G.DEFAULTS)
app._apply_cfg_to_widgets()
print('DEFAULTS label  :', repr(app.v['side'].get()), '->', G.SIDES.get(app.v['side'].get()))
cfg = app._collect()
print('collect         :', cfg['side'], cfg['first'])
for val, fir in (('b', 'them'), ('w', 'me'), ('auto', None)):
    app.cfg['side'] = val
    app.cfg['first'] = fir
    app._apply_cfg_to_widgets()
    c = app._collect()
    print('  set %-4s -> label %-18r  collect %s / %s' % (val, app.v['side'].get(), c['side'], c['first']))
print('buttons:', [b for b in ('b_read','b_start','b_pause','b_stop','b_apply','b_self') if hasattr(app, b)])
print('selftest btn text:', app.b_self.cget('text'))
root.destroy()
print('SIDE TEST OK')