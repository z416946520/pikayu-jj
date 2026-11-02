import ctypes
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import w32          # noqa: E402
from PIL import Image               # noqa: E402

SRC = r'D:\BuildProject\pikayu-jj\pikafishjj\dist\pikafishjj.exe'
LEAN = r'D:\BuildProject\pikayu-jj\dist_lean'
FRAME = r'D:\BuildProject\pikayu-jj\fixtures\jj_orig.png'

if os.path.isdir(LEAN):
    shutil.rmtree(LEAN)
os.makedirs(LEAN)
exe = os.path.join(LEAN, 'pikafishjj.exe')
shutil.copy2(SRC, exe)
print('lean copy:', exe, os.path.getsize(exe), 'bytes; folder holds', os.listdir(LEAN))

out = os.path.join(LEAN, 'selftest.out')
env = dict(os.environ)
env['PIKAFISHJJ_LOGFILE'] = os.path.join(LEAN, 'selftest.log')
t0 = time.time()
with open(out, 'w', encoding='utf-8') as fh:
    rc = subprocess.call([exe, 'selftest', '--frame', FRAME], stdout=fh, stderr=subprocess.STDOUT, env=env)
print('=== selftest rc = %d  (%.1fs) ===' % (rc, time.time() - t0))
print(open(out, encoding='utf-8').read().strip())
pk = os.path.join(LEAN, 'pikafish')
print('engine extracted next to the exe:', os.path.isdir(pk), sorted(os.listdir(pk)) if os.path.isdir(pk) else '')
print('folder now holds', sorted(os.listdir(LEAN)))

w32.set_dpi_aware()
before = set(h for h, t, c, pp in w32.list_windows() if 'pikafish' in (t or '').lower())
p = subprocess.Popen([exe])
t0 = time.time()
hwnd = None
while time.time() - t0 < 90:
    now = [w for w in w32.list_windows()
           if 'pikafish' in (w[1] or '').lower() and w[0] not in before]
    if now:
        hwnd, title, cls, pid = now[0]
        break
    time.sleep(0.4)
print('gui window after %.1fs: %s %r pid=%s' % (time.time() - t0, hwnd, title, (pid if hwnd else None)))
if hwnd:
    w32.bring_to_front(hwnd)
    time.sleep(2.0)
    x, y, w, h = w32.client_rect_screen(hwnd)
    g = w32.ScreenGrabber()
    a = g.grab(x, y, w, h)
    Image.fromarray(a).save(r'D:\BuildProject\pikayu-jj\gui_lean.png')
    print('client', x, y, w, h, '-> saved gui_lean.png', a.shape)
    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
    for _ in range(20):
        time.sleep(0.5)
        if not [w2 for w2 in w32.list_windows() if w2[0] == hwnd]:
            print('closed gracefully')
            break
    else:
        print('STILL OPEN')
time.sleep(0.5)
cfg = os.path.join(LEAN, 'gui_config.json')
print('gui_config.json next to the exe:', os.path.isfile(cfg))
if os.path.isfile(cfg):
    print(open(cfg, encoding='utf-8').read().strip())
print('folder finally holds', sorted(os.listdir(LEAN)))
print('DONE')
