
import sys, numpy as np
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import vision as V
from PIL import Image

path = sys.argv[1]
a = np.asarray(Image.open(path).convert('RGB'))
H, W, _ = a.shape
for sign in (-1, 1):
    for con in (V.LINE_CONTRAST, 12.0):
        lm = V.line_mask(a, sign=sign, contrast=con)
        prof = lm.sum(axis=0)
        cands = V._group_centres(prof, max(30.0, H * V.LINE_COL_FRAC))
        narrow = [c for c, w in cands if w <= 16] or [c for c, w in cands]
        print('sign %d con %.0f  lm frac %.4f  groups %d (narrow %d)' % (
            sign, con, lm.mean(), len(cands), len(narrow)))
        print('    groups:', [(round(c, 1), w) for c, w in cands][:14])
        if len(narrow) >= 4:
            mp = V._median_pitch(narrow)
            fit = V._fit_progression(narrow, 9, mp, W / 2.0)
            print('    median pitch %s  fit %s' % (mp, fit))
