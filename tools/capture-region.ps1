param(
  [int]$X, [int]$Y, [int]$W, [int]$H, [string]$Out
)
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap($W, $H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($X, $Y, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
"saved $Out ($($W)x$($H) at $X,$Y)"
