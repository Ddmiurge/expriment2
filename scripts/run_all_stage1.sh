#!/usr/bin/env bash
# 阶段 1 全条件顺序跑。默认 40 条试点。
#
# 用法：
#   bash scripts/run_all_stage1.sh
#   LIMIT=120 bash scripts/run_all_stage1.sh      # 灰区扩容
#   ONLY=avtp bash scripts/run_all_stage1.sh      # 只跑某个剪枝器
#
# 注意：每个条件都会重新加载模型。顺序跑是为了不把显存打爆；
# 判官在每个条件内部是「先卸受害者、再加载判官」。

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python}"
LIMIT="${LIMIT:-40}"
ATTACK="${ATTACK:-midas}"
if [ "$ATTACK" = "mir" ]; then
  SAMPLES="${SAMPLES:-data/mir}"
else
  SAMPLES="${SAMPLES:-data/midas/attack_set.jsonl}"
fi
ONLY="${ONLY:-all}"

if [ ! -e "$SAMPLES" ]; then
  echo "✗ 找不到攻击集 $SAMPLES"
  if [ "$ATTACK" = "midas" ]; then
    echo "  先跑：python scripts/build_attack_set.py --input ... --out $SAMPLES --limit $LIMIT --keyword-mode llm"
  else
    echo "  先解压 MIR-SafetyBench：python third_party/mir-safetybench/extract_data.py --output $SAMPLES"
  fi
  exit 1
fi

run() {
  local name="$1"; shift
  echo
  echo "════════ $name ════════"
  "$PY" scripts/run_stage1.py --attack "$ATTACK" "$@" --samples "$SAMPLES" --limit "$LIMIT" \
       --out "runs/${ATTACK}_$name" --resume
}

# 基线
if [ "$ONLY" = "all" ] || [ "$ONLY" = "none" ]; then
  run stage1_base --pruner none
fi

BASE="runs/${ATTACK}_stage1_base/results.jsonl"

if [ "$ONLY" = "all" ] || [ "$ONLY" = "avtp" ]; then
  run stage1_avtp50 --pruner avtp --budget 0.5 --compare "$BASE"
  run stage1_avtp25 --pruner avtp --budget 0.25 --compare "$BASE"
fi

if [ "$ONLY" = "all" ] || [ "$ONLY" = "sieve" ]; then
  run stage1_sieve50 --pruner sieve --budget 0.5 --compare "$BASE"
  run stage1_sieve25 --pruner sieve --budget 0.25 --compare "$BASE"
fi

# 拆机制的两组对照：
#   avtp_equal   = AVTP 打分 + 等额分配  → 与 avtp 比，差的是「分配规则」
#   sieve_random = 随机打分 + 等额分配  → 与 sieve 比，差的是「打分信号」
if [ "$ONLY" = "all" ] || [ "$ONLY" = "ablation" ]; then
  run stage1_avtp_equal50 --pruner avtp_equal --budget 0.5 --compare "$BASE"
  run stage1_avtp_equal25 --pruner avtp_equal --budget 0.25 --compare "$BASE"
  run stage1_sieve_random50 --pruner sieve_random --budget 0.5 --compare "$BASE"
  run stage1_sieve_random25 --pruner sieve_random --budget 0.25 --compare "$BASE"
fi

echo
echo "全部完成。每个条件的结果块在 runs/${ATTACK}_<条件>/result.block.txt。"
echo "把块粘到 results/inbox/，然后在 Mac 上："
echo "  python scripts/result_block.py parse results/inbox/"
echo "  python scripts/analyze_stage1.py results/parsed/"
