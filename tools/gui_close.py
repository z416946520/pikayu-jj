
import ctypes, sys, time
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import w32
w32.set_dpi_aware()
u = ctypes.windll.user32
for h, t, c, p in w32.list_windows():
    if 'pikafishjj' in t.lower():
        print('closing', h, t)
        u.PostMessageW(h, 0x0010, 0, 0)
time.sleep(2.0)
print('remaining', [t for h, t, c, p in w32.list_windows() if 'pikafishjj' in t.lower()])
