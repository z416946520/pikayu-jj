# -*- coding: utf-8 -*-
"""Recon: which WeChatAppEx process could hold the mini-program's game state, and
can we read its memory without vision?"""
import ctypes
import ctypes.wintypes as wt
import subprocess

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

ps = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='WeChatAppEx.exe'\" | "
     "Select-Object ProcessId,ParentProcessId,WorkingSetSize,CommandLine | "
     "ConvertTo-Json -Compress"],
    capture_output=True, text=True, encoding="utf-8", errors="replace")
import json
procs = json.loads(ps.stdout or "[]")
if isinstance(procs, dict):
    procs = [procs]
print("%-8s %-8s %10s  %-6s %s" % ("pid", "ppid", "wset MB", "read?", "role"))
for p in procs:
    pid = p["ProcessId"]
    cmd = (p.get("CommandLine") or "")
    role = "browser/main"
    for flag in ("--type=renderer", "--type=gpu-process", "--type=utility", "--type=applet",
                 "--type=worker", "--type=ppapi", "--type=crashpad"):
        if flag in cmd:
            role = flag.split("=", 1)[1]
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    ok = "yes"
    if not h:
        ok = "no(%d)" % ctypes.get_last_error()
    else:
        # read the first 64 bytes of the image base as a smoke test
        buf = ctypes.create_string_buffer(64)
        got = ctypes.c_size_t(0)
        base = ctypes.c_void_p(0)
        psapi = ctypes.WinDLL("psapi")
        mod = (ctypes.c_void_p * 1024)()
        need = wt.DWORD(0)
        if psapi.EnumProcessModules(h, mod, ctypes.sizeof(mod), ctypes.byref(need)):
            base = ctypes.c_void_p(mod[0])
        read_ok = k32.ReadProcessMemory(h, base, buf, 64, ctypes.byref(got))
        ok = "yes" if read_ok and got.value else "open-ok,read-fail(%d)" % ctypes.get_last_error()
        k32.CloseHandle(h)
    extra = ""
    if "--applet" in cmd or "applet" in cmd.lower():
        extra = "applet-flag"
    print("%-8s %-8s %10.1f  %-6s %s %s" % (
        pid, p.get("ParentProcessId"), (p.get("WorkingSetSize") or 0) / 1048576.0, ok, role, extra))
