# 主表与待跑清单（2026-11-25）

> 行 = 剪枝条件，列 = 攻击/基准。  
> 每列用该攻击自己的论文口径：MIDAS H-CoT、DMN 二分类、SCJ pass@5、SIVA 二分类、MIR H-CoT（MIR 是基准，不是攻击）。

## 状态图例

- ✅ 已有、可用（最新 fixed 版）
- ⚠ 已有，但该格有截断/口径问题，只作敏感性
- 🟡 已有 40 条旧结果，但本轮要扩到 MIR-180，不能直接当主表
- ⬜ **需要跑**
- — 不适用

## 主表

| 条件 | MIDAS（H-CoT） | DMN（二分类） | SCJ（pass@5） | SIVA·MMSB（二分类） | SIVA·FR（二分类） | MIR-180（H-CoT） |
|---|---:|---:|---:|---:|---:|---:|
| none | ✅ 60.0%（24/40） | ✅ 92.5%（37/40） | ✅ 80.0%（32/40） | ✅ 30.0%（12/40） | ✅ 32.0%（24/75） | 🟡 17.5%（40）→ 180 |
| AVTP 25% | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| AVTP 50% | ✅ 27.5%（11/40） | ✅ 90.0%（36/40） | ✅ 85.0%（34/40） | ✅ 35.0%（14/40） | ✅ 24.0%（18/75） | 🟡 22.5%（40）→ 180 |
| RI-Prune 25% | ⚠ 25.0%（10/40，28 截断） | ✅ 87.5%（35/40） | ✅ 90.0%（36/40） | ⬜ | ⬜ | ⬜ |
| RI-Prune 50% | ⬜ | ⬜ | ⬜ | ✅ 7.5%（3/40） | ✅ 16.0%（12/75） | ⬜ |

## 必须补的格

### MIR-180（先建集，再跑 5 格）

```bash
python scripts/build_mir_expanded.py \
    --root ~/data/MIR-SafetyBench \
    --out data/mir/attack_set_180.jsonl \
    --per-relation 20

for pr in "none 0" "avtp 0.25" "avtp 0.5" "riprune 0.25" "riprune 0.5"; do
  set -- $pr
  python scripts/run_stage1.py --attack mir \
    --samples data/mir/attack_set_180.jsonl --pruner $1 \
    ${1:+$( [ "$1" != none ] && echo "--budget $2")} \
    --out runs/mir180_$1 --limit 180 \
    --max-new-tokens 3072 --judge-mode hcot
done
```

### MIDAS

- ⬜ AVTP 25%
- ⬜ RI-Prune 50%

### DMN

- ⬜ AVTP 25%
- ⬜ RI-Prune 50%
- 两格都要补二分类重判

### SCJ

- ⬜ AVTP 25%
- ⬜ RI-Prune 50%
- 两格都要补 `pass@5`（`run_scj_attempts.py`）

### SIVA·MMSB

- ⬜ AVTP 25%
- ⬜ RI-Prune 25%
- 两格都要补原文二分类重判

### SIVA·FR

- ⬜ AVTP 25%
- ⬜ RI-Prune 25%
- 两格都要补原文二分类重判

## 主表补齐后的读法

1. **25% 和 25% 比，50% 和 50% 比**；不要 RI25 对 AVTP50。
2. **MIDAS RI25 仍要标 28/40 截断**；RI50 看截断是否下降。
3. **MIR-180 如果仍地板**，主表保留 MIR 列但注“地板，不可判定”；不要删。
4. **跨列不平均、不横比绝对值**；每列只看自己的 Δ。
