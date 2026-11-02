import sys
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import w32
w32.set_dpi_aware()
ws = w32.list_windows()
print('z-order top 12:')
for i, (h, t, c, p) in enumerate(ws[:12]):
    try:
        r = w32.client_rect_screen(h)
    except Exception as e:
        r = str(e)
    print(' %2d pid=%-6d cls=%-24s rect=%s title=%r' % (i, p, c[:24], r, t[:40]))
for i, (h, t, c, p) in enumerate(ws):
    if 'JJ' in (t or '') or '\u8c61\u68cb' in (t or ''):
        print('MATCH idx=%d hwnd=%s title=%r client=%s' % (i, h, t, w32.client_rect_screen(h)))
