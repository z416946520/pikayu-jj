import ctypes
import subprocess
import sys
import time

sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import w32          # noqa: E402
from PIL import Image               # noqa: E402

EXE = r'D:\BuildProject\pikayu-jj\pikafishjj\dist\pikafishjj.exe'
OUT = r'D:\BuildProject\pikayu-jj\docs\gui_frozen.png'

w32.set_dpi_aware()


def pk_windows():
    out = []
    for hwnd, title, cls, pid in w32.list_windows():
        if 'pikafish' in (title or '').lower():
            out.append((hwnd, title, pid))
    return out


before = pk_windows()
print('before:', before)
print('launching', EXE)
p = subprocess.Popen([EXE])
t0 = time.time()
found = None
while time.time() - t0 < 90:
    now = pk_windows()
    new = [w for w in now if w[0] not in [b[0] for b in before]]
    if new:
        found = new[0]
        break
    time.sleep(0.4)
print('new window after %.1fs: %r' % (time.time() - t0, found))
if not found:
    print('NO WINDOW APPEARED')
    p.terminate()
    raise SystemExit(1)
hwnd, title, pid = found
w32.bring_to_front(hwnd)
time.sleep(2.0)
x, y, w, h = w32.client_rect_screen(hwnd)
print('client', x, y, w, h)
# PrintWindow renders the window even while another window covers it
a = w32.WindowGrabber().grab(hwnd)
if a is None:
    a = w32.ScreenGrabber().grab(x, y, w, h)
Image.fromarray(a).save(OUT)
print('saved', OUT, a.shape)
print('posting WM_CLOSE')
ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
for _ in range(20):
    time.sleep(0.5)
    if not [w for w in pk_windows() if w[0] == hwnd]:
        print('window closed gracefully')
        break
else:
    print('WINDOW STILL OPEN')
print('remaining:', pk_windows())
p.poll()
print('proc rc', p.returncode)
print('DONE')
