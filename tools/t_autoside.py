import sys

import numpy as np

sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import board as B          # noqa: E402
from pikafishjj import vision as V         # noqa: E402
from PIL import Image                      # noqa: E402

a = np.array(Image.open(r'D:\BuildProject\pikayu-jj\fixtures\jj_orig.png').convert('RGB'))
print('frame', a.shape)

for name, img in (('as is (red at the bottom)', a), ('rotated 180 (red at the top)', a[::-1, ::-1].copy())):
    try:
        cal = V.calibrate(img)
    except Exception as exc:
        print('%-28s calibrate FAILED: %s' % (name, exc))
        continue
    tpl, half = V.load_templates(cal=cal)
    scr, sc = V.recognize(img, cal, tpl, half=half)
    flip = B.detect_flip(scr)
    side = 'b' if flip else 'w'
    grid = B.screen_to_internal(scr, flip)
    print('%-28s flip=%s -> our_side(auto)=%s' % (name, flip, side))
    print('    FEN', B.grid_to_fen(grid, side))
    print('    pieces', sum(1 for row in grid for c in row if c != '.'))

upright = B.fen_to_grid(B.OPENING_FEN)
print('detect_flip(upright grid) =', B.detect_flip(upright))
print('detect_flip(flipped grid) =', B.detect_flip(upright[::-1]))
