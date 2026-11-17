# TASKS · 下一轮：建攻击集 + 阶段 1 基线（阶段 0 已通过 2026-11-17）

> 阶段 0 六项已在服务器全过。本轮开始产出第一批研究数字，但**只到关卡 1 为止**：
> 先跑 `none` 基线，确认攻击本身有下降空间，再跑 `avtp` / `sieve` 的 50% 档。
> 不要在关卡 1 出结果前把 9 个条件全跑完。

---

## 0 · 拉代码 + 重打 AVTP 补丁（必须做）

本轮合入了 bf16 精度对齐补丁（`src/pruning/avtp_patch.py`）。服务器上已安装的
transformers 文件里还是旧代码，**拉完代码必须重打**：

```bash
cd expriment2
git pull
source .venv/bin/activate

python scripts/apply_avtp_patch.py --revert
python scripts/apply_avtp_patch.py --mode instrumented
python scripts/apply_avtp_patch.py --check      # 应显示：已打 instrumented
```

如果 `--check` 显示 `original`，说明上次 SM0.3 停在原版；先 `--revert` 再重打。
**不要**直接 `--mode instrumented`，会叠成两份 `img_start_pos`。

重打后建议快速重跑一次 SM0.3：

```bash
python scripts/apply_avtp_patch.py --revert
python scripts/apply_avtp_patch.py --mode original
python scripts/sm0_3_avtp_equivalence.py --mode original --out /tmp/orig.json

python scripts/apply_avtp_patch.py --revert
python scripts/apply_avtp_patch.py --mode instrumented
python scripts/sm0_3_avtp_equivalence.py --mode instrumented --out /tmp/inst.json
python scripts/sm0_3_avtp_equivalence.py --compare /tmp/orig.json /tmp/inst.json
```

**通过判据新增一条**：每层每图的保留数逐项相等，不只总长度相等。

---

## 1 · 准备指令集（主实验：MM-SafetyBench tiny）

**为什么是 MM-SafetyBench**：MIDAS 论文的 Table 2 就是在 **MM-SafetyBench (tiny)**
上评的；这是三个官方评测集之一（Table 1 HADES、Table 2 MM-SafetyBench、Table 3 AdvBench）。
服务器上单图线已经有一份，零准备成本。

**必须注意的三点**：

1. **只借问题，不借图**。我们取 MM-SafetyBench 的 harmful question，图全部由 MIDAS 自己生成。
   论文里要写「用 MM-SafetyBench 问题构造的 MIDAS 攻击」，不能写成「MM-SafetyBench 上的结果」。
2. **优先用官方 tiny split**。如果服务器副本里有 tiny 划分，就用它；没有的话用现有 split
   按 13 个类目分层抽 40 条（`build_attack_set.py` 默认 `--stratify`），并在报告里写明
   「不是官方 tiny」。
3. **判官口径不同**：MIDAS 用 0–5 分、阈值 ≥3、GPT-5-nano；我们用四档、Qwen3-8B。
   所以绝对 ASR 不能和 Table 2 对表，只能看同一批条件下开/关剪枝的差。

**路径**：服务器上 MM-SafetyBench 的根目录（单图线的 `env/paths.yaml` 里有）。
`--input` 传它的目录或对应 json。

MIR-SafetyBench **不当指令源**；它是独立的多图攻击基准，放在阶段 1 的单独泛化表里，
用它自己的 `revised_prompt` + 图片。

先跑 40 条试点。指令集要**固定下来**，后面所有条件都用同一批 id。

---

## 2 · 生成攻击集

```bash
python scripts/build_attack_set.py \
    --input <MM-SafetyBench 路径> \
    --out data/midas/attack_set.jsonl \
    --limit 40 --keyword-mode llm --stratify
```

- `--keyword-mode llm` 用本地 Qwen3-8B 按 MIDAS 原文 prompt 抽词；`rule` 只用于快速冒烟。
- 生成后会打印每张图的掩码占比。占比在 `[0.0002, 0.25]` 之外会标 ✗，按协议处理。
- 这一步只用 CPU + 一次 Qwen3-8B 加载，不占受害者模型。

生成完先空跑校验：

```bash
python scripts/run_stage1.py --attack midas \
    --samples data/midas/attack_set.jsonl --pruner none \
    --out runs/stage1_base --limit 40 --dry-run
```

---

## 3 · 跑基线（关卡 1 的前半）

```bash
python scripts/run_stage1.py --attack midas \
    --samples data/midas/attack_set.jsonl --pruner none \
    --out runs/stage1_base --limit 40
```

跑完看两样：

1. 结果块里的 ASR；
2. 控制台是否打出「基线 ASR <20%」或「>95%」的警告。

**基线健全性闸**（协议 §5.1）：
- 20–90% → 正常，继续；
- <20% → 攻击太弱，先换 DMN/MIR，不要直接判「不杀」；
- >95% → 天花板，解释要收窄。

---

## 4 · 跑主条件（关卡 1 的后半）

```bash
python scripts/run_stage1.py --attack midas \
    --samples data/midas/attack_set.jsonl --pruner avtp --budget 0.5 \
    --out runs/stage1_avtp50 --limit 40 --compare runs/stage1_base/results.jsonl

python scripts/run_stage1.py --attack midas \
    --samples data/midas/attack_set.jsonl --pruner sieve --budget 0.5 \
    --out runs/stage1_sieve50 --limit 40 --compare runs/stage1_base/results.jsonl
```

跑完把三个结果块（`runs/*/result.block.txt`）粘回 Mac。**先看关卡 1 判定**：
跌幅 >10pp 且区间上界 <0 → 杀成立；<5pp 或跨 0 → 不杀；5–10 → 灰区扩容。

**不要**在这一步之前跑 25% 档和拆机制对照。

---

## 5 · 已知的坑（阶段 0 踩过的）

| 坑 | 处理 |
|---|---|
| 判官 raw 以 `<think>` 开头 | `judge.py` 已传 `enable_thinking=False`；确认拉到了最新代码 |
| `--check` 报 `original` / `both` | 先 `--revert`，再选模式重打；不要叠加 |
| `CUDA error: invalid device ordinal` | `device` 写逻辑编号 `cuda:0`；`CUDA_VISIBLE_DEVICES` 会重排卡号 |
| 缺 torchvision | `bash env/setup_venv.sh` 会 `--no-deps` 装 0.29.2 |
| 长度差几个 token、top-5 一致 | dtype 问题：不要把 bf16 转 Python float 算预算；本轮已修 |
| OOM | 把 `--max-pixels` 从 640² 降到 512²，并在报告里写明这是偏离 |

---

## 6 · 本轮禁止

- 不要跑 25% 档与拆机制对照（等关卡 1 结果）。
- 不要改 `third_party/`。
- 不要在服务器上写 `src/` 或 `scripts/`；要改就打印补丁交回 Mac。
- 不要用 OpenAI API。
- 不要为了让 SM0.5 通过而改判官 rubric。
