#!/usr/bin/env bash
# Scratch runner for the project's own test set (see logs/suite_all.txt).
# pkg_*  -> pikafishjj/tools/t_*.py   (cwd = pikafishjj)
# tools_*-> tools/t_*.py + skin_bench.py (cwd = root)
set -u
ROOT=/d/BuildProject/pikayu-jj
PY=$ROOT/.venv-build/Scripts/python.exe
OUT=$ROOT/logs/suite_new.txt
: > "$OUT"
fail=0
run() {  # name dir script
  local name=$1 dir=$2 script=$3
  local log=$ROOT/logs/new_$name.log
  ( cd "$dir" && "$PY" "$script" ) > "$log" 2>&1
  local rc=$?
  local tail=$(tail -n 1 "$log" | tr -d '\r')
  if [ $rc -ne 0 ]; then fail=$((fail+1)); fi
  printf '%-18s exit=%-3s %s :: %s\n' "$name" "$rc" "$([ $rc -eq 0 ] && echo PASS || echo FAIL)" "$tail" | tee -a "$OUT"
}
for f in t_time t_bg t_wait t_rematch t_newgame t_retry t_gui t_bridge t_audit t_stop t_book; do
  [ -f "$ROOT/pikafishjj/tools/$f.py" ] && run "pkg_$f" "$ROOT/pikafishjj" "tools/$f.py"
done
for f in t_gate t_noboard t_regress t_lift t_cal_fuzz t_incr2 t_dialog t_dialog2 t_coarse; do
  [ -f "$ROOT/tools/$f.py" ] && run "tools_$f" "$ROOT" "tools/$f.py"
done
[ -f "$ROOT/tools/skin_bench.py" ] && run "tools_skin_bench" "$ROOT" "tools/skin_bench.py"
echo "SUITE_FAILURES=$fail" | tee -a "$OUT"
