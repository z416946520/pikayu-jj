param(
  [string]$TitleMatch = 'JJ',
  [int]$Width = 760,
  [int]$Height = 1000,
  [int]$X = 1272,
  [int]$Y = 60,
  [string]$Out = 'D:\BuildProject\pikayu-jj\shot_jj2.png'
)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class WinOp {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr hWnd, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
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

$h = [WinOp]::FindByTitle($TitleMatch)
if ($h -eq [IntPtr]::Zero) { Write-Error "not found: $TitleMatch"; exit 1 }
$r = New-Object WinOp+RECT
[void][WinOp]::GetWindowRect($h, [ref]$r)
"BEFORE: $($r.Left),$($r.Top) $($r.Right-$r.Left)x$($r.Bottom-$r.Top)"

# SWP_NOZORDER(0x0004) | SWP_NOACTIVATE(0x0010)
[void][WinOp]::SetWindowPos($h, [IntPtr]::Zero, $X, $Y, $Width, $Height, 0x0014)
Start-Sleep -Milliseconds 2500

$r2 = New-Object WinOp+RECT
[void][WinOp]::GetWindowRect($h, [ref]$r2)
$wd = $r2.Right - $r2.Left
$ht = $r2.Bottom - $r2.Top
"AFTER: $($r2.Left),$($r2.Top) $($wd)x$($ht)"

$bmp = New-Object System.Drawing.Bitmap($wd, $ht)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[void][WinOp]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
"saved: $Out"
