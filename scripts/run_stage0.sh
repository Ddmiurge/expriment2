#!/usr/bin/env bash
# 阶段 0 五项检查。全过才开阶段 1。
#
# 用法：
#   bash scripts/run_stage0.sh
#   SKIP_MODEL=1 bash scripts/run_stage0.sh      # 只跑不占 GPU 的项

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python}"

pass=0
fail=0
declare -a RESULTS

run() {  # $1=名字 后面是命令
  local name="$1"; shift
  echo
  echo "════════ $name ════════"
  if "$@"; then
    RESULTS+=("✓ $name")
    pass=$((pass+1))
  else
    RESULTS+=("✗ $name")
    fail=$((fail+1))
  fi
}

run "SM0.1 环境盘点" "$PY" scripts/sm0_1_env_report.py
run "SM0.6 存活率口径" "$PY" scripts/sm0_6_survival_sanity.py
run "SM0.4 MIDAS 离线" "$PY" scripts/sm0_4_midas_offline.py --limit 1 --keyword-mode rule

if [ "${SKIP_MODEL:-0}" = "1" ]; then
  echo
  echo "SKIP_MODEL=1：跳过 SM0.2 / SM0.3 / SM0.5"
else
  run "SM0.2 模型冒烟" "$PY" scripts/sm0_2_model_smoke.py

  echo
  echo "════════ SM0.3 AVTP 等价性 ════════"
  TMP="$(mktemp -d)"
  "$PY" scripts/apply_avtp_patch.py --revert || true
  if "$PY" scripts/apply_avtp_patch.py --mode original \
      && "$PY" scripts/sm0_3_avtp_equivalence.py --mode original --out "$TMP/orig.json" \
      && "$PY" scripts/apply_avtp_patch.py --revert \
      && "$PY" scripts/apply_avtp_patch.py --mode instrumented \
      && "$PY" scripts/sm0_3_avtp_equivalence.py --mode instrumented --out "$TMP/inst.json" \
      && "$PY" scripts/sm0_3_avtp_equivalence.py --compare "$TMP/orig.json" "$TMP/inst.json"; then
    RESULTS+=("✓ SM0.3 AVTP 等价性")
    pass=$((pass+1))
  else
    RESULTS+=("✗ SM0.3 AVTP 等价性")
    fail=$((fail+1))
  fi

  run "SM0.5 判官冒烟" "$PY" scripts/sm0_5_judge_smoke.py
fi

echo
echo "════════ 阶段 0 汇总 ════════"
for r in "${RESULTS[@]}"; do echo "  $r"; done
echo
echo "通过 $pass 项，失败 $fail 项。"
[ "$fail" -eq 0 ] && echo "✅ 阶段 0 通过，可以开阶段 1。" || echo "❌ 先修失败的项，不要开阶段 1。"
exit "$fail"
