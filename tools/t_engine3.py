import sys
import time
import traceback

sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import board as B          # noqa: E402
from pikafishjj.engine import Engine       # noqa: E402

EXE = r'D:\BuildProject\pikayu-jj\pikafish\Pikafish-Windows-x86-64-universal.exe'
for i in range(3):
    t0 = time.time()
    try:
        e = Engine(EXE, threads=2, hash_mb=128)
        t1 = time.time()
        best = e.bestmove(B.OPENING_FEN, movetime=400)
        t2 = time.time()
        e.quit()
        print('run %d: handshake %.2fs  think %.2fs  best=%s' % (i, t1 - t0, t2 - t1, best[0]))
    except Exception as exc:
        print('run %d FAILED after %.2fs: %s: %s' % (i, time.time() - t0, type(exc).__name__, exc))
        traceback.print_exc()
    time.sleep(0.5)
