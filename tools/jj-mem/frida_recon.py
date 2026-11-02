# -*- coding: utf-8 -*-
"""Frida recon: which WeChatAppEx process holds the big wasm memory, and does any
of them own the mini-program's sockets?"""
import sys

import frida

JS = r"""
var out = { arch: Process.arch, ptr: Process.pointerSize };
var ranges = Process.enumerateRanges('rw-').filter(function (r) {
  return r.size >= 4 * 1024 * 1024 && r.file === undefined;
}).sort(function (a, b) { return b.size - a.size; });
out.bigRanges = ranges.slice(0, 6).map(function (r) { return [r.base.toString(), r.size]; });
out.modules = Process.enumerateModules().length;
out.hasWs2 = Process.findModuleByName('ws2_32.dll') !== null;
out.wasmish = ranges.filter(function (r) {
  var n = Math.min(r.size, 4096);
  try { var b = r.base.readByteArray(n); } catch (e) { return false; }
  return r.size >= 16 * 1024 * 1024;
}).length;
send(out);
"""

def main():
    dev = frida.get_local_device()
    procs = [p for p in dev.enumerate_processes() if p.name == "WeChatAppEx.exe"]
    print("WeChatAppEx processes:", len(procs))
    for p in procs:
        try:
            s = dev.attach(p.pid)
        except Exception as exc:
            print("  pid %-6d attach failed: %s" % (p.pid, exc))
            continue
        got = {}
        def on_msg(msg, data):
            if msg.get("type") == "send":
                got.update(msg["payload"])
        sc = s.create_script(JS)
        sc.on("message", on_msg)
        sc.load()
        import time
        for _ in range(50):
            if got:
                break
            time.sleep(0.1)
        big = ", ".join("%s:%.0fMB" % (b[0], b[1] / 1048576.0) for b in got.get("bigRanges", [])[:3])
        print("  pid %-6d mods=%-4s ws2=%-5s big rw: %s" % (
            p.pid, got.get("modules"), got.get("hasWs2"), big or "-"))
        s.detach()
    return 0

sys.exit(main())
