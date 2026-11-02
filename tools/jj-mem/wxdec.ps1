# Try the known V1MMWX (PC WeChat mini-program) container schemes and validate
# each candidate by the structure of the decrypted wxapkg v1 index.
$ErrorActionPreference = 'Stop'
$appid = 'wx0c852640e4324692'
$src = 'C:\Users\CARSER\AppData\Roaming\Tencent\xwechat\radium\users\8252c3d661a54b6213b8f4717c6ffa7e\applet\packages\wx0c852640e4324692\151\__WITHOUT_MULTI_PLUGINCODE__.wxapkg'
$all = [IO.File]::ReadAllBytes($src)
Write-Output ("file {0} bytes, magic {1}" -f $all.Length, [Text.Encoding]::ASCII.GetString($all[0..5]))
$payload = $all[6..($all.Length - 1)]

function Pbkdf2([string]$pw, [string]$salt, [int]$iters, [int]$len) {
  $d = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($pw, [Text.Encoding]::ASCII.GetBytes($salt), $iters)
  return $d.GetBytes($len)
}
function Md5b([string]$s) {
  $m = [System.Security.Cryptography.MD5]::Create()
  return $m.ComputeHash([Text.Encoding]::ASCII.GetBytes($s))
}
function TryAes($data, [byte[]]$key, [byte[]]$iv, [string]$mode) {
  $aes = [System.Security.Cryptography.Aes]::Create()
  $aes.Mode = $mode
  $aes.Padding = [System.Security.Cryptography.PaddingMode]::None
  $aes.Key = $key
  if ($iv) { $aes.IV = $iv }
  $dec = $aes.CreateDecryptor()
  return $dec.TransformFinalBlock($data, 0, $data.Length)
}
function Score([byte[]]$pt) {
  if (-not $pt -or $pt.Length -lt 16) { return -1 }
  if ($pt[0] -ne 0xBE) { return 0 }
  $idxLen = [BitConverter]::ToUInt32(($pt[5..8] | ForEach-Object { $_ })[3..0] + (,0)[0..0], 0)
  # big endian index length at offset 5
  $idxLen = ($pt[5] -shl 24) + ($pt[6] -shl 16) + ($pt[7] -shl 8) + $pt[8]
  if ($idxLen -le 0 -or $idxLen -gt $pt.Length) { return 1 }
  $off = 14; $names = 0; $good = 0
  while ($off -lt 14 + $idxLen) {
    if ($off + 4 -gt $pt.Length) { break }
    $nlen = ($pt[$off] -shl 24) + ($pt[$off+1] -shl 16) + ($pt[$off+2] -shl 8) + $pt[$off+3]
    if ($nlen -le 0 -or $nlen -gt 300 -or ($off + 4 + $nlen + 8) -gt $pt.Length) { break }
    $name = [Text.Encoding]::UTF8.GetString($pt, $off + 4, $nlen)
    $names++
    if ($name -match '\.(js|json|wxml|wxss|wxs|wasm|png|html|ttf)$' -or $name -eq 'app-config.json') { $good++ }
    $off += 4 + $nlen + 8
    if ($names -gt 5000) { break }
  }
  if ($names -lt 3) { return 1 }
  return 100 + [int](100.0 * $good / $names)
}

$k32 = Pbkdf2 $appid 'saltiest' 1000 32
$k16 = Pbkdf2 $appid 'saltiest' 1000 16
$md5 = Md5b $appid
$iv0 = New-Object byte[] 16
$ivText = [Text.Encoding]::ASCII.GetBytes('the iv: 16 bytes')
$cands = @(
  @{ n = 'pbkdf2-32 key/iv';      k = $k32[0..15]; iv = $k32[16..31]; m = 'CBC' },
  @{ n = 'pbkdf2-32 key/iv ECB';  k = $k32[0..15]; iv = $null;        m = 'ECB' },
  @{ n = 'pbkdf2-16 + text iv';   k = $k16;        iv = $ivText;      m = 'CBC' },
  @{ n = 'pbkdf2-16 + zero iv';   k = $k16;        iv = $iv0;         m = 'CBC' },
  @{ n = 'md5(appid) + zero iv';  k = $md5;        iv = $iv0;         m = 'CBC' },
  @{ n = 'md5(appid) + text iv';  k = $md5;        iv = $ivText;      m = 'CBC' },
  @{ n = 'pbkdf2-16 ECB';         k = $k16;        iv = $null;        m = 'ECB' }
)
foreach ($c in $cands) {
  try {
    $pt = TryAes $payload $c.k $c.iv $c.m
    $s = Score $pt
    Write-Output ("{0,-24} first={1:x2} {2:x2} {3:x2} {4:x2}  score={5}" -f $c.n, $pt[0], $pt[1], $pt[2], $pt[3], $s)
    if ($s -ge 100) {
      Write-Output ("    MATCH -> {0}" -f $c.n)
      [IO.File]::WriteAllBytes('D:\BuildProject\pikayu-jj\logs\jj_code.dec', $pt)
      break
    }
  } catch { Write-Output ("{0,-24} error {1}" -f $c.n, $_.Exception.Message) }
}