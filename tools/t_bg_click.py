
import sys, time
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import w32

w32.set_dpi_aware()
jj, t = w32.find_window('JJ')
u = w32.user32
cx, cy, cw, ch = w32.client_rect_screen(jj)
fg0 = u.GetForegroundWindow()
print('JJ hwnd %d  client %s' % (jj, (cx, cy, cw, ch)))
print('foreground before  %d' % fg0)
print('WS_EX_NOACTIVATE before: %s' % w32.has_no_activate(jj))
w32.set_no_activate(jj, True)
print('WS_EX_NOACTIVATE after set: %s' % w32.has_no_activate(jj))
x, y = cx + int(cw * 0.08), cy + int(ch * 0.30)      # plain background of the menu page
cur0 = w32.cursor_pos()
print('cursor %s -> click %s' % (cur0, (x, y)))
t0 = time.perf_counter()
w32.click_silent(x, y)
dt = (time.perf_counter() - t0) * 1000.0
time.sleep(0.5)
fg1 = u.GetForegroundWindow()
cur1 = w32.cursor_pos()
print('click_silent took %.0f ms' % dt)
print('foreground after   %d   unchanged: %s' % (fg1, fg1 == fg0))
print('cursor after %s   restored: %s' % (cur1, abs(cur1[0] - cur0[0]) <= 2 and abs(cur1[1] - cur0[1]) <= 2))
w32.set_no_activate(jj, False)
print('WS_EX_NOACTIVATE restored: %s' % (not w32.has_no_activate(jj)))
