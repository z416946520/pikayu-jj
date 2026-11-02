"""The request panel on a real fixture: nothing is pressed until the panel has
stayed on screen for a whole second (three sightings spanning 1.0s when both
buttons are there, four spanning 2.5s when only one is visible).  The two-frame
gate this replaces was measured being passed by the transition screen that
follows 再来一局 - a stray 拒绝 click landed a second after the press."""

import sys
import time

import numpy as np
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from PIL import Image
from pikafishjj.auto import AutoPlayer

FX = np.asarray(Image.open(r'D:\BuildProject\pikayu-jj\fixtures\dlg_fixture.png').convert('RGB'))
BOARD = np.asarray(Image.open(r'D:\BuildProject\pikayu-jj\fixtures\skin_now.png').convert('RGB'))
ORIGIN = (1913, 95)


class P(AutoPlayer):
    def __init__(self, **kw):
        AutoPlayer.__init__(self, **kw)
        self.clicked = []

    def click_point(self, x, y):
        self.clicked.append((x, y))
        return True


def player(request, dry):
    p = P(request=request, dry=dry)
    p.hwnd = 1
    p.origin = ORIGIN
    return p


def sight(p, img, tries=14, gap=0.3):
    """Show the panel until it is answered; returns the seconds that took."""
    t0 = time.time()
    for _k in range(tries):
        p.handle_dialog(img)
        if p.clicked or p.stats['dialogs']:
            break
        time.sleep(gap)
    return time.time() - t0


def run(request, dry, img, tag, tries=14):
    p = player(request, dry)
    took = sight(p, img, tries=tries)
    print('%-28s -> clicks=%-24s dialogs=%d  %.1fs' % (
        tag, p.clicked, p.stats['dialogs'], took))
    return p


p = run('decline', False, FX, 'decline / dialog up')
assert p.clicked == [(ORIGIN[0] + 210, ORIGIN[1] + 588)], p.clicked
assert p.stats['dialogs'] == 1, p.stats['dialogs']
p2 = run('accept', False, FX, 'accept / dialog up')
assert p2.clicked == [(ORIGIN[0] + 388, ORIGIN[1] + 588)], p2.clicked
p3 = run('off', False, FX, 'off / dialog up', tries=4)
assert p3.clicked == []
p4 = run('decline', True, FX, 'decline but dry')
assert p4.clicked == []
p5 = run('decline', False, BOARD, 'decline / plain board', tries=4)
assert p5.clicked == []
# the first sightings of a panel are never answered, however many arrive at once
p6 = player('decline', False)
assert p6.handle_dialog(FX) is True and p6.clicked == []
assert p6.handle_dialog(FX) is True and p6.clicked == []
print('%-28s -> clicks=%s' % ('two sightings in a row', p6.clicked))
# ... and once it has been pressed, the fading panel is not pressed again
sight(p6, FX)
assert len(p6.clicked) == 1, p6.clicked
p6.handle_dialog(FX)
assert len(p6.clicked) == 1, p6.clicked
print('rate limited clicks: %s' % (p6.clicked,))
print('DIALOG TEST OK')
