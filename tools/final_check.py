
import io, ast, os
P = r'D:\BuildProject\pikayu-jj\pikafishjj\pikafishjj'
for n in sorted(os.listdir(P)):
    if not n.endswith('.py'):
        continue
    src = io.open(os.path.join(P, n), encoding='utf-8').read()
    t = ast.parse(src)
    names = [x.name for x in t.body if isinstance(x, (ast.FunctionDef, ast.ClassDef))]
    dups = [x for x in set(names) if names.count(x) > 1]
    print('%-12s %6d lines  %3d defs  dups=%s  %s' % (
        n, src.count(chr(10)) + 1, len(names), dups, 'AST OK'))
l = io.open(r'D:\BuildProject\pikayu-jj\pikafishjj\launcher.py', encoding='utf-8').read()
ast.parse(l)
print('%-12s %6d lines  AST OK' % ('launcher.py', l.count(chr(10)) + 1))
