# Search the V1MMWX container for the right key/iv/mode, judged by the decrypted
# structure (a wxapkg v1 index, zlib, or plain text) - a self-verifying oracle.
$ErrorActionPreference = 'Stop'
$appid = 'wx0c852640e4324692'
$user = '8252c3d661a54b6213b8f4717c6ffa7e'
$src = "C:\Users\CARSER\AppData\Roaming\Tencent\xwechat\radium\users\$user\applet\packages\$appid\151\__WITHOUT_MULTI_PLUGINCODE__.wxapkg"
$all = [IO.File]::ReadAllBytes($src)
$payload = $all[6..($all.Length - 1)]
Write-Output ("payload {0} bytes (mod16 {1})" -f $payload.Length, ($payload.Length % 16))

function Pbkdf2([string]$pw, [string]$salt, [int]$iters, [int]$len) {
  $d = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($pw, [Text.Encoding]::ASCII.GetBytes($salt), $iters)
  return $d.GetBytes($len)
}
function Md5b([string]$s) { return ([System.Security.Cryptography.MD5]::Create()).ComputeHash([Text.Encoding]::ASCII.GetBytes($s)) }

function Decrypt($data, [byte[]]$key, [byte[]]$iv, [string]$mode) {
  $aes = [System.Security.Cryptography.Aes]::Create()
  $aes.Mode = $mode
  $aes.Padding = [System.Security.Cryptography.PaddingMode]::None
  $aes.Key = $key
  if ($iv -and $mode -ne 'ECB') { $aes.IV = $iv }
  return $aes.CreateDecryptor().TransformFinalBlock($data, 0, $data.Length)
}

function Score([byte[]]$pt) {
  if (-not $pt -or $pt.Length -lt 64) { return -1 }
  $s = 0
  if ($pt[0] -eq 0xBE) { $s += 50 }
  if ($pt[0] -eq 0x78) { $s += 40 }
  if ($pt[0] -eq 0x1F -and $pt[1] -eq 0x8B) { $s += 40 }
  $txt = 0
  for ($i = 0; $i -lt 512; $i++) {
    $b = $pt[$i]
    if (($b -ge 32 -and $b -lt 127) -or $b -eq 10 -or $b -eq 13 -or $b -eq 9 -or $b -ge 0xE0) { $txt++ }
  }
  $s += [int](30.0 * $txt / 512)
  if ($pt[0] -eq 0xBE) {
    $idxLen = ($pt[5] -shl 24) + ($pt[6] -shl 16) + ($pt[7] -shl 8) + $pt[8]
    if ($idxLen -gt 0 -and $idxLen -lt $pt.Length) {
      $off = 14; $names = 0; $good = 0
      while ($off -lt 14 + $idxLen -and $names -lt 5000) {
        if ($off + 4 -gt $pt.Length) { break }
        $nlen = ($pt[$off] -shl 24) + ($pt[$off+1] -shl 16) + ($pt[$off+2] -shl 8) + $pt[$off+3]
        if ($nlen -le 0 -or $nlen -gt 300 -or ($off + 4 + $nlen + 8) -gt $pt.Length) { break }
        $name = [Text.Encoding]::UTF8.GetString($pt, $off + 4, $nlen)
        if ($name -match '^[\x20-\x7e/\.\-_]+$') { $good++ }
        $names++
        $off += 4 + $nlen + 8
      }
      if ($names -ge 3) { $s += 60 + [int](60.0 * $good / $names) }
    }
  }
  return $s
}

$keys = @(
  @{ n = 'pbkdf2(appid,saltiest,1000,32)'; k = (Pbkdf2 $appid 'saltiest' 1000 32) },
  @{ n = 'pbkdf2(appid,saltiest,1000,16)'; k = (Pbkdf2 $appid 'saltiest' 1000 16) },
  @{ n = 'pbkdf2(appid,salt,1000,16)';     k = (Pbkdf2 $appid 'salt' 1000 16) },
  @{ n = 'md5(appid)';                     k = (Md5b $appid) },
  @{ n = 'md5(user)';                      k = (Md5b $user) }
)
$ivs = @(
  @{ n = 'key[16:32]'; iv = $null },
  @{ n = 'key[0:16]';  iv = $null },
  @{ n = 'text';       iv = [Text.Encoding]::ASCII.GetBytes('the iv: 16 bytes') },
  @{ n = 'zero';       iv = (New-Object byte[] 16) }
)
$modes = @('CBC', 'CFB', 'OFB', 'CTR', 'ECB')
$best = @()
foreach ($k in $keys) {
  $kb = $k.k
  $k16 = if ($kb.Length -ge 16) { $kb[0..15] } else { $kb }
  foreach ($ivc in $ivs) {
    $iv = switch ($ivc.n) { 'key[16:32]' { if ($kb.Length -ge 32) { $kb[16..31] } else { $k16 } } 'key[0:16]' { $k16 } default { $ivc.iv } }
    foreach ($m in $modes) {
      if ($m -eq 'ECB' -and $ivc.n -ne 'key[16:32]') { continue }
      try {
        $pt = Decrypt $payload $k16 $iv $m
        $s = Score $pt
        if ($s -gt 0) { $best += [PSCustomObject]@{ Key = $k.n; Iv = $ivc.n; Mode = $m; Score = $s; Pt = $pt } }
      } catch { }
    }
  }
}
if (-not $best) { Write-Output 'no candidate produced plausible plaintext'; exit 0 }
$best = $best | Sort-Object Score -Descending
foreach ($b in $best | Select-Object -First 8) { Write-Output ("score {0,4}  {1,-34} {2,-10} {3}" -f $b.Score, $b.Key, $b.Iv, $b.Mode) }
$top = $best[0]
Write-Output ("top: {0} / {1} / {2} score {3}  first bytes {4}" -f $top.Key, $top.Iv, $top.Mode, $top.Score, (($top.Pt[0..15] | ForEach-Object { $_.ToString('x2') }) -join ' '))
if ($top.Score -ge 100) {
  [IO.File]::WriteAllBytes('D:\BuildProject\pikayu-jj\logs\jj_code.dec', $top.Pt)
  Write-Output 'saved D:\BuildProject\pikayu-jj\logs\jj_code.dec'
}