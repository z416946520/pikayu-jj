
"""Screenshot the dev GUI through PrintWindow (works even when covered).

The GUI is started with stdout/stderr on DEVNULL on purpose: a grandchild that
inherits the console pipe keeps PowerShell's pipeline open until it exits.
"""
import os, subprocess, sys, time
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import w32
PY = sys.executable
OUT = r'D:\BuildProject\pikayu-jj\gui_new.png'
w32.set_dpi_aware()
print('python ok', os.path.isfile(PY), 'cwd ok', os.path.isdir(r'D:\BuildProject\pikayu-jj\pikafishjj'))
before = set(h for h, t, c, p in w32.list_windows())
proc = subprocess.Popen([PY, '-m', 'pikafishjj.run', 'ui'],
                        cwd=r'D:\BuildProject\pikayu-jj\pikafishjj',
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                        env=dict(os.environ, PIKAFISHJJ_LAYOUT=r'D:\BuildProject\pikayu-jj\gui_layout2.json'))
hwnd = None
for i in range(30):
    time.sleep(0.5)
    for h, t, c, p in w32.list_windows():
        if h not in before and 'pikafishjj' in t.lower():
            hwnd = h
            break
    if hwnd:
        break
print('window %s after %.1fs  exit=%s' % (hwnd, 0.5 * (i + 1), proc.poll()))
time.sleep(1.0)
if hwnd:
    time.sleep(3.0)
    x, y, w, h = w32.client_rect_screen(hwnd)
    print('client', x, y, w, h)
    g = w32.WindowGrabber()
    a = g.grab(hwnd)
    print('frame', None if a is None else a.shape)
    if a is not None:
        from PIL import Image
        Image.fromarray(a).save(OUT)
        print('saved', OUT, os.path.getsize(OUT))
    g.close()
    import ctypes
    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
    time.sleep(2.5)
    print('remaining', [t for hh, t, c, p in w32.list_windows() if 'pikafishjj' in t.lower()])
if proc.poll() is None and hwnd is None:
    proc.kill()
print('done')
