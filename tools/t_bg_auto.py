
import sys, time
import numpy as np
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from PIL import Image
from pikafishjj import w32
from pikafishjj.auto import AutoPlayer

w32.set_dpi_aware()
hwnd, t = w32.find_window('JJ')
p = AutoPlayer(background=True, dry=True)
p.hwnd = hwnd
x, y, w, h = w32.client_rect_screen(hwnd)
p.origin = (x, y)
p.grabber = w32.ScreenGrabber()
p.wgrab = w32.WindowGrabber()
p.fp_band = (0, 0)
print('client', x, y, w, h, 'point_owner(centre) == hwnd:', w32.point_owner(x + w // 2, y + h // 2) == hwnd)
a = p.frame()
print('AutoPlayer.frame shape %s  bg_fallback %s  frames %s' % (
    a.shape, p.stats['bg_fallback'], p.stats['frames']))
ref = w32.WindowGrabber().grab(hwnd)
scr = w32.ScreenGrabber().grab(x, y, w, h)
d1 = np.abs(a.astype(np.int32) - ref.astype(np.int32)).mean()
d2 = np.abs(a.astype(np.int32) - scr.astype(np.int32)).mean()
print('frame vs PrintWindow ref: mean|d| %.2f   (should be ~0)' % d1)
print('frame vs screen grab:     mean|d| %.2f   (large => the game is covered)' % d2)
Image.fromarray(a).save(r'D:\BuildProject\pikayu-jj\bg_auto.png')
print('quiet %s  bg_ok %s  background %s' % (p.quiet, p.bg_ok, p.background))
p.close()
print('closed: wgrab %s engine %s' % (p.wgrab, p.engine))
