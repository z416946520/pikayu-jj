
import sys, time
import numpy as np
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from PIL import Image
from pikafishjj import dialog as D

CASES = [
    (r'D:\BuildProject\pikayu-jj\fixtures\dlg_fixture.png', 'dialog(undo request)', True),
    (r'D:\BuildProject\pikayu-jj\fixtures\jj_orig.png', 'wood opening board', False),
    (r'D:\BuildProject\pikayu-jj\fixtures\skin_now.png', 'stone opening board', False),
]
for path, tag, want in CASES:
    a = np.asarray(Image.open(path).convert('RGB'))
    t0 = time.perf_counter()
    got = D.find_request(a)
    dt = (time.perf_counter() - t0) * 1000.0
    ok = (got is not None) == want
    print('%-24s %-8s %5.1f ms  %s' % (tag, 'FOUND' if got else 'none', dt, 'OK' if ok else 'WRONG'))
    if got:
        print('        buttons %d  decline %s  accept %s  box %s' % (
            got['buttons'], got.get('decline'), got.get('accept'), got['box']))
