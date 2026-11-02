
import ast, io
P = r'D:\BuildProject\pikayu-jj\pikafishjj\pikafishjj\gui.py'
s = io.open(P, encoding='utf-8').read()
t = ast.parse(s)
names = [x.name for x in t.body if isinstance(x, (ast.FunctionDef, ast.ClassDef))]
print('lines %d  toplevel %d  AST OK' % (s.count(chr(10)) + 1, len(names)))
cls = [n for n in t.body if isinstance(n, ast.ClassDef) and n.name == 'App'][0]
ms = [n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
print('App methods %d' % len(ms))
print('dups', [m for m in set(ms) if ms.count(m) > 1])
need = ['_build', '_build_header', '_build_target', '_scrollable', '_card', '_tip',
        '_build_engine', '_build_game', '_build_right', '_build_log', '_build_actions',
        '_build_statusbar', '_spin', '_apply_cfg_to_widgets', '_mark_preset', '_collect',
        'on_preset', 'on_browse', 'on_save', 'on_apply', 'on_detect', 'on_enum', 'on_help',
        '_bind_keys', 'on_read', 'on_start', 'on_selftest', '_launch', '_worker', '_selftest',
        'on_pause', 'on_stop', 'on_close', '_log', '_append', '_draw_board', '_set_info',
        '_set_status', '_set_running', 'on_clear_log', '_view', '_pump', '_tick', '_drain_jobs',
        '_refresh_info', 'dump_layout', 'on_save_log', 'on_snap']
print('missing', [m for m in need if m not in ms])
