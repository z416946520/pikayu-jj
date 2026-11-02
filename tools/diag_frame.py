
import sys, traceback, numpy as np
sys.path.insert(0, r'D:\BuildProject\pikayu-jj\pikafishjj')
from pikafishjj import vision as V
from PIL import Image

path = sys.argv[1]
a = np.asarray(Image.open(path).convert('RGB'))
print('== %s %s' % (path, a.shape))
try:
    cal = V.calibrate(a, verbose=True)
    if cal is None:
        print('   calibrate -> None')
    else:
        print('   calibrate -> lattice? discs %s used %s resid %s dev %s' % (
            cal.get('ndiscs'), cal.get('ndiscs_used'), cal.get('resid'), cal.get('model_dev')))
except Exception:
    traceback.print_exc()
for name, kind, con in (('colour', 0, 0.0), ('dark20', 1, 20.0), ('dark12', 1, 12.0),
                        ('bright20', -1, 20.0), ('bright12', -1, 12.0), ('pieces', 2, 0.0)):
    try:
        base = V._lattice_for(a, kind, con, verbose=(name == 'pieces'))
    except Exception as exc:
        print('   %-9s RAISED %s: %s' % (name, type(exc).__name__, exc)); continue
    if base is None:
        print('   %-9s base None' % name); continue
    cal = V._calibrate_with(a, base)
    print('   %-9s co %6.2f cp %5.2f ro %6.2f rp %5.2f -> discs %2d used %2d resid %s dev %s ok %s' % (
        name, base['co'], base['cpitch'], base['ro'], base['rpitch'],
        cal.get('ndiscs') or 0, cal.get('ndiscs_used') or 0, cal.get('resid'),
        cal.get('model_dev'), cal.get('model') is not None))
