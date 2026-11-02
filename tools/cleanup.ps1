# Tidy the working directory.  Dry run by default; pass -Apply to delete.
#
# Keeps everything the project needs (package sources, tests, fixtures, docs,
# engine + nnue, the build venv, the shipped dist) and removes what can be
# regenerated: PyInstaller scratch, obsolete build outputs, debug dumps, python
# caches, stale logs and stray scratch files from the root.
#
#   pwsh -File tools\cleanup.ps1              # show what would go
#   pwsh -File tools\cleanup.ps1 -Apply       # remove it
#
# It never touches .dsh-* (other tools keep their scratch there) and aborts if a
# target somehow sits outside the project root.
param([switch]$Apply)

$root = 'D:\BuildProject\pikayu-jj'
if (-not (Test-Path -LiteralPath $root)) { throw "root not found: $root" }
$targets = New-Object System.Collections.ArrayList
$add = { param($p) if (Test-Path -LiteralPath $p) { [void]$targets.Add($p) } }

# -- 1. build scratch and obsolete outputs ---------------------------------
& $add "$root\pikafishjj\build"          # PyInstaller work dir (--clean wipes it anyway)
& $add "$root\pikafishjj\dist_icon"      # the old icon candidate build
& $add "$root\pikafishjj\dist\dbg"       # failure-frame dumps
& $add "$root\pikafishjj\dist\pikafish"  # engine copy for the frozen exe (re-released on first run)
& $add "$root\dbg"                       # skin-bench / diagnostic pictures
& $add "$root\dist_lean"                 # a lean build from an earlier experiment

# -- 2. engine binaries we never use on Windows ----------------------------
foreach ($f in 'Pikafish-Linux-x86-64-universal', 'Pikafish-MacOS-universal',
               'Pikafish-Android-arm64-universal') {
  & $add "$root\pikafish\$f"
}

# -- 3. python caches outside the build venv -------------------------------
foreach ($p in (Get-ChildItem $root -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue)) {
  if ($p.FullName -notlike '*\.venv-build\*') { [void]$targets.Add($p.FullName) }
}

# -- 4. logs: keep the current test evidence and the last build log --------
Get-ChildItem "$root\logs" -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -notlike 'suite_*' -and $_.Name -ne 'build.log' } |
  ForEach-Object { [void]$targets.Add($_.FullName) }

# -- 5. stray scratch files in the root (never other tools' .dsh-*) --------
$patterns = @('*.log', '*.txt', '*.tmp', '*.bak', '*.old', '*.zip', '*.png', '*.jpg',
              '_*.py', '_*.ps1', '_*.mjs', '*.spec.bak')
foreach ($pat in $patterns) {
  Get-ChildItem $root -File -Filter $pat -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notlike '.dsh-*' } |
    ForEach-Object { [void]$targets.Add($_.FullName) }
}

# -- report ---------------------------------------------------------------
$bad = $targets | Where-Object { -not $_.StartsWith($root) }
if ($bad) { Write-Output 'ABORT - outside root:'; $bad; exit 1 }
$bytes = 0
foreach ($t in $targets) {
  $it = Get-Item -LiteralPath $t -Force
  $sz = if ($it.PSIsContainer) {
    (Get-ChildItem -LiteralPath $t -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  } else { $it.Length }
  if (-not $sz) { $sz = 0 }
  $bytes += [int64]$sz
  Write-Output ("{0,12:N0}  {1}" -f $sz, $t.Replace($root + '\', ''))
}
Write-Output ('--- to remove: {0:N1} MB in {1} items' -f ($bytes / 1MB), $targets.Count)
$before = (Get-ChildItem $root -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
if (-not $Apply) {
  Write-Output ('--- working directory now: {0:N1} MB (dry run, nothing removed)' -f ($before / 1MB))
  exit 0
}
foreach ($t in $targets) { Remove-Item -LiteralPath $t -Recurse -Force -ErrorAction Continue }
$after = (Get-ChildItem $root -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
Write-Output ('--- removed: {0:N1} MB, working directory: {1:N1} MB -> {2:N1} MB' -f (
  ($before - $after) / 1MB), ($before / 1MB), ($after / 1MB))
