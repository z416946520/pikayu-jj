
import sys, time
import numpy as np
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import w32

w32.set_dpi_aware()
hwnd, t = w32.find_window('JJ')
wg = w32.WindowGrabber()
print('covered check: point_owner(centre) is JJ ->', end=' ')
x, y, w, h = w32.client_rect_screen(hwnd)
print(w32.point_owner(x + w // 2, y + h // 2) == hwnd)
prev = None
diffs = []
t0 = time.time()
for k in range(12):
    a = wg.grab(hwnd)
    if a is None:
        print('grab None at', k); break
    if prev is not None:
        d = np.abs(a.astype(np.int32) - prev.astype(np.int32))
        diffs.append(d.mean())
    prev = a
    time.sleep(0.3)
print('12 PrintWindow frames over %.1fs while completely covered' % (time.time() - t0))
print('  inter-frame mean|d|: min %.3f max %.3f' % (min(diffs), max(diffs)))
print('  renderer keeps updating while covered:', max(diffs) > 0.5)
