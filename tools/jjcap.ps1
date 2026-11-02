param(
  [string]$Out = 'D:\BuildProject\pikayu-jj\jj.png',
  [int]$Width = 0, [int]$Height = 0, [int]$X = -99999, [int]$Y = -99999
)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class JJ {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern int GetSystemMetrics(int i);
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr hWnd, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  public static IntPtr FindByTitle(string match) {
    IntPtr found = IntPtr.Zero;
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      if (!IsWindowVisible(h)) return true;
      StringBuilder sb = new StringBuilder(512);
      GetWindowTextW(h, sb, 512);
      if (sb.ToString().IndexOf(match, StringComparison.OrdinalIgnoreCase) >= 0) { found = h; return false; }
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
"@
[void][JJ]::SetProcessDPIAware()
$h = [JJ]::FindByTitle('JJ')
if ($h -eq [IntPtr]::Zero) { Write-Error 'JJ window not found'; exit 1 }

if ($Width -gt 0) {
  $r0 = New-Object JJ+RECT
  [void][JJ]::GetWindowRect($h, [ref]$r0)
  $nx = $X; $ny = $Y
  if ($X -le -99999) { $nx = $r0.Left }
  if ($Y -le -99999) { $ny = $r0.Top }
  [void][JJ]::SetWindowPos($h, [IntPtr]::Zero, $nx, $ny, $Width, $Height, 0x0014)
  Start-Sleep -Milliseconds 2500
}

$r = New-Object JJ+RECT
[void][JJ]::GetWindowRect($h, [ref]$r)
$wd = $r.Right - $r.Left
$ht = $r.Bottom - $r.Top
$sw = [JJ]::GetSystemMetrics(0)
$sh = [JJ]::GetSystemMetrics(1)
"WINDOW: $($r.Left),$($r.Top) $($wd)x$($ht)   screen $($sw)x$($sh)"
$x0 = [Math]::Max(0, $r.Left); $y0 = [Math]::Max(0, $r.Top)
$x1 = [Math]::Min($sw, $r.Right); $y1 = [Math]::Min($sh, $r.Bottom)
$bmp = New-Object System.Drawing.Bitmap(($x1-$x0), ($y1-$y0))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($x0, $y0, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
"SAVED: $Out  ($($x1-$x0)x$($y1-$y0)) at $x0,$y0"
