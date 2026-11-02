import sys
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import w32, vision as V
from PIL import Image

w32.set_dpi_aware()
hwnd, title = w32.find_window('JJ')
print('hwnd', hwnd, 'title', repr(title))
if not hwnd:
    raise SystemExit('no window')
x, y, w, h = w32.client_rect_screen(hwnd)
print('client', w, h, 'at', x, y)
g = w32.ScreenGrabber()
a = g.grab(x, y, w, h)
print('frame', a.shape, a.dtype)
Image.fromarray(a).save(r'D:\BuildProject\pikayu-jj\probe_now.png')
cal = V.calibrate(a, verbose=True)
if cal is None:
    print('CALIBRATE RETURNED None')
else:
    print('band', cal['band'], 'cpitch', cal['cpitch'], 'rpitch', cal['rpitch'],
          'discs', cal['ndiscs'], 'used', cal.get('ndiscs_used'), 'resid', cal.get('resid'),
          'model', 'yes' if cal.get('model') else 'NO')
