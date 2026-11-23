# RI-Prune 复现说明（ours）

论文：RI-Prune: Relation and Information Aware Visual Token Pruning for Multi-Image
Vision-Language Models，arXiv:2611.06047（CIKM 2026）。

## 原论文配置（按论文正文）

- **位置**：projector 之后、decoder 之前，一次性选择；
- **P = 16** 个 per-image prototypes（连续等分块平均）；
- **三个信号**：
  - query relevance：`max_l cos(v_i, q_l)`；
  - cross-image correspondence：`max_{b≠a,m} cos(v_i, p_m^(b))`；
  - intra-image representativeness：`s_i * log(|V(a)| / n_{m_i})`；
- 每个信号在样本内做 z-score，**λ_r=λ_c=λ_u=1** 等权相加；
- 每图等额 Top-K，K 尽量均分；
- 保留 token 按原序列顺序进入 decoder；
- **attention-free**。

## 本仓库实现

- `src/pruning/riprune.py`：monkey patch `Qwen3VLModel.forward`；
- 在 image embeds scatter 后、`language_model` 前剪 token；
- 同步裁剪 `inputs_embeds`、`position_ids`、`attention_mask`、
  `visual_pos_masks`、`deepstack_visual_embeds`；
- `run_stage1.py --pruner riprune` 已接入；
- 单测：`tests/test_riprune.py`。

## 与原论文配置的摩擦

| # | 项 | 原论文 | 我们 | 影响 |
|---|---|---|---|---|
| 1 | 代码 | 未公开 | 按公式重写 | 只能叫 RI-Prune (ours) |
| 2 | 文本 query | textual query tokens | **最后一张图之后的文本段**（近似 user query；仍含少量 `im_end`/assistant 模板尾 token） | 已基本对齐；残余模板 token 很少，记录为近似 |
| 3 | 图像布局 | 论文模型无关 | 用 Qwen3-VL 的 `image_grid_thw` / `visual_pos_masks` | 只适配 Qwen3-VL |
| 4 | deepstack | 论文未提 | Qwen3-VL 有 deepstack，必须同步裁 | 不裁会 shape mismatch；属架构适配 |
| 5 | position/mask | 论文未写 | 同步 index_select | 必需 |
| 6 | 每图配额 | 差不超过 1 | 容量不足时会把剩余配额分给其他图 | 常规 640² 图不会触发 |
| 7 | 预算 | 论文主打 4.6%–12.5% | 安全表先用 50% 与 AVTP 对齐 | 50% 比论文的激进档更温和 |
| 8 | 评测 | 准确率/FLOPs | 攻击 ASR | 目的不同，只做列内 Δ |
| 9 | batch | 未写 | batch=1 | 与现有跑格一致 |

## 首次运行建议

```bash
# 1 条 MIDAS smoke
python scripts/run_stage1.py --attack midas \
    --samples data/midas/attack_set.jsonl --pruner riprune --budget 0.5 \
    --out runs/riprune_midas_smoke --limit 1 \
    --max-new-tokens 3072 --judge-mode hcot

# 10 条
python scripts/run_stage1.py --attack midas \
    --samples data/midas/attack_set.jsonl --pruner riprune --budget 0.5 \
    --out runs/riprune_midas_10 --limit 10 \
    --max-new-tokens 3072 --judge-mode hcot
```

看三样：输出非空、`keepfrac` 约 0.5、显存不炸。若布局断言失败，
`riprune.last_stats()["error"]` 会记录 visual token 数与 grid 不一致。
