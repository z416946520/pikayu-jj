Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class DpiProbe {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern int GetSystemMetrics(int i);
  [DllImport("shcore.dll")] public static extern int GetDpiForMonitor(IntPtr h, int t, out uint x, out uint y);
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr hWnd, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hWnd, ref POINT p);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
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
[void][DpiProbe]::SetProcessDPIAware()
$sw = [DpiProbe]::GetSystemMetrics(0)
$sh = [DpiProbe]::GetSystemMetrics(1)
"DPI-AWARE screen: $($sw) x $($sh)"

$h = [DpiProbe]::FindByTitle('JJ')
if ($h -eq [IntPtr]::Zero) { "JJ window NOT FOUND"; exit 1 }
$r = New-Object DpiProbe+RECT
[void][DpiProbe]::GetWindowRect($h, [ref]$r)
$wd = $r.Right - $r.Left; $ht = $r.Bottom - $r.Top
"JJ WINDOW RECT (physical): $($r.Left),$($r.Top) $($wd)x$($ht)"

$cr = New-Object DpiProbe+RECT
[void][DpiProbe]::GetClientRect($h, [ref]$cr)
$pt = New-Object DpiProbe+POINT
[void][DpiProbe]::ClientToScreen($h, [ref]$pt)
"JJ CLIENT (physical): origin $($pt.X),$($pt.Y)  size $($cr.Right-$cr.Left)x$($cr.Bottom-$cr.Top)"

$x0 = [Math]::Max(0, $r.Left); $y0 = [Math]::Max(0, $r.Top)
$x1 = [Math]::Min($sw, $r.Right); $y1 = [Math]::Min($sh, $r.Bottom)
"CAPTURE REGION: $x0,$y0 -> $x1,$y1  ($($x1-$x0)x$($y1-$y0))"
$bmp = New-Object System.Drawing.Bitmap(($x1-$x0), ($y1-$y0))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($x0, $y0, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save('D:\BuildProject\pikayu-jj\jj_dpi.png', [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
"saved jj_dpi.png"
