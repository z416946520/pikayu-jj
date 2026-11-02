
import os, zipfile
D = r'D:\BuildProject\pikayu-jj\pikafishjj\dist'
out = os.path.join(D, 'pikafishjj-win64.zip')
if os.path.exists(out):
    os.remove(out)
names = ['pikafishjj.exe', '使用说明.txt']
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for n in names:
        z.write(os.path.join(D, n), n)
print('zip bytes %d  ->  %s' % (os.path.getsize(out), out))
with zipfile.ZipFile(out) as z:
    for i in z.infolist():
        print('   %-18s %d' % (i.filename, i.file_size))
