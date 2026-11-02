Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class WinEnum {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr hWnd, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr hWnd, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint procId);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

$rows = New-Object System.Collections.ArrayList
$cb = [WinEnum+EnumWindowsProc]{
  param([IntPtr]$h, [IntPtr]$l)
  if ([WinEnum]::IsWindowVisible($h)) {
    $sb = New-Object System.Text.StringBuilder 512
    [void][WinEnum]::GetWindowTextW($h, $sb, 512)
    $title = $sb.ToString()
    $cn = New-Object System.Text.StringBuilder 256
    [void][WinEnum]::GetClassNameW($h, $cn, 256)
    $cls = $cn.ToString()
    $r = New-Object WinEnum+RECT
    [void][WinEnum]::GetWindowRect($h, [ref]$r)
    $wd = $r.Right - $r.Left
    $ht = $r.Bottom - $r.Top
    if ($wd -gt 150 -and $ht -gt 150) {
      $procId = 0
      [void][WinEnum]::GetWindowThreadProcessId($h, [ref]$procId)
      $pname = ''
      try { $pname = (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch {}
      $line = ('{0} || {1} || {2} || {3}x{4} @ {5},{6} || pid={7}' -f $title, $cls, $pname, $wd, $ht, $r.Left, $r.Top, $procId)
      [void]$rows.Add($line)
    }
  }
  return $true
}
[void][WinEnum]::EnumWindows($cb, [IntPtr]::Zero)
$rows | Sort-Object | ForEach-Object { $_ }
