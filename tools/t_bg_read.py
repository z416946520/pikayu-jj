
import sys, time, os
import numpy as np
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import w32, vision as V, board as B
from PIL import Image

w32.set_dpi_aware()
hwnd, title = w32.find_window('JJ')
print('hwnd', hwnd)
cx, cy, cw, ch = w32.client_rect_screen(hwnd)
print('client', cx, cy, cw, ch, 'minimized', w32.is_minimized(hwnd))
g = w32.ScreenGrabber()
wg = w32.WindowGrabber()

tpl, half = V.load_templates()

def read(tag, img):
    if img is None:
        print('%-10s NONE' % tag)
        return None, None
    d = np.abs(img.astype(np.int32) - img.astype(np.int32))
    t0 = time.perf_counter()
    cal = V.calibrate(img, verbose=False)
    if not cal:
        print('%-10s shape %s  cal FAILED' % (tag, img.shape))
        return None, None
    t1 = time.perf_counter()
    gr, sc = V.recognize(img, cal, tpl, half=half)
    t2 = time.perf_counter()
    flip = B.detect_flip(gr)
    grid = B.screen_to_internal(gr, flip)
    fen = B.grid_to_fen(grid, 'w')
    model = 'yes' if cal.get('model') else 'no'
    print('%-10s shape %s  cal %.3fs discs %s resid %s model %s  recog %.3fs  flip %s  FEN %s' % (
        tag, img.shape, t1 - t0, cal.get('ndiscs'), cal.get('resid'), model, t2 - t1, flip, fen))
    return fen, img

scr = g.grab(cx, cy, cw, ch)
pw = wg.grab(hwnd)
print('screen shape', scr.shape, 'printwindow', None if pw is None else pw.shape)
if pw is not None:
    n = min(pw.shape[0], scr.shape[0]); m = min(pw.shape[1], scr.shape[1])
    d = np.abs(pw[:n, :m].astype(np.int32) - scr[:n, :m].astype(np.int32))
    print('pw vs screen: mean|d| %.2f  max %d  (same frame => both should match)' % (d.mean(), d.max()))
Image.fromarray(pw).save(r'D:\BuildProject\pikayu-jj\bg_pw.png')
Image.fromarray(scr).save(r'D:\BuildProject\pikayu-jj\bg_scr.png')
f1, _ = read('printwindow', pw)
f2, _ = read('screen', scr)
print('PASS1 same board:', f1 is not None and f1 == f2)
print('phase1 done')
