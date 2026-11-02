
import sys, ctypes
from ctypes import wintypes
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import w32

w32.set_dpi_aware()
u = w32.user32
jj, t = w32.find_window('JJ')
print('JJ root %d  no_activate %s' % (jj, w32.has_no_activate(jj)))
print('--- visible top level windows (z order) ---')
for hwnd, title, cls, pid in w32.list_windows()[:12]:
    r = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
    print('%10d  %-28s %-24s pid %-6d %s' % (hwnd, (title or '')[:28], (cls or '')[:24], pid,
          (r.left, r.top, r.right - r.left, r.bottom - r.top)))

class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

cx, cy, cw, ch = w32.client_rect_screen(jj)
for fx, fy, tag in ((0.08, 0.30, 'left margin'), (0.50, 0.12, 'menu header'), (0.50, 0.90, 'lower card')):
    x, y = cx + int(cw * fx), cy + int(ch * fy)
    pt = POINT(x, y)
    h = u.WindowFromPoint(pt)
    root = u.GetAncestor(h, 2)
    print('point %-12s (%d,%d) -> window %d root %d  is JJ root: %s' % (tag, x, y, h, root, root == jj))
print('foreground now %d' % u.GetForegroundWindow())
