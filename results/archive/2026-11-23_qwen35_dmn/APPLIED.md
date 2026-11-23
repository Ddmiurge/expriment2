# 2026-11-23 Qwen3.5-9B DMN 归档与判读

原始报告：[`2026-11-23_qwen35_dmn_report.md`](2026-11-23_qwen35_dmn_report.md)

## 读数

| 模型 | ASR（≥3） | ≥4 | 平均分 | 截断 |
|---|---:|---:|---:|---:|
| Qwen3.5-9B | 80.0%（32/40） | 45.0%（18/40） | 3.33 | 2/40 |
| Qwen3-VL-8B | 87.5%（35/40） | 62.5%（25/40） | 3.88 | 1/40 |

配对：2 条 Qwen3.5 过/Qwen3-VL 不过，5 条反向；McNemar **p=0.453，不显著**。
分数差：16 条下降、6 条上升、14 条持平；符号检验 **p≈0.052，边界性**。
因此只能写“数值更低、有向下趋势”，不能写“显著更弱”。

## 判读

- Qwen3.5 是原生多模态 VLM（`has_vision_config=true`，32 层，hidden 4096）；
- 同 40 条 uid、同一批图、同一 prompt、同一 Qwen3-8B H-CoT 判官；
- 2/40 截断判 0；报告中的 82.5% 只能作为敏感性分析，不进主结果；
- number chain 数字命中 50.0%（Qwen3-VL 85.5%），顺序均 0/40；不改变“chain 退化”的结论。

## 决策：这条线收口

1. **不移植 AVTP**：Qwen3.5 没有 `img_start_pos/img_end_pos`，是 linear + full attention 混合结构；需要独立重写 hybrid attention 剪枝，成本高、结果也不能与 AVTP 直接比。
2. **不再跑 Qwen3.5 SCJ**：除非只需要多一个 `none` 数字，优先级低。
3. **作为论文的第二个 `none` 对照**：DMN 在两个架构上都有效（87.5% / 80.0%，p=0.453），说明不是单模型伪影；但 Qwen3.5 不提供剪枝列。

## 代码偏离

- `enable_thinking=False` patch 未合入 `run_none_vlm.py`；必须合入，否则 3072 预算会被 thinking 吃掉。
- 独立 venv：transformers 5.20.2；主 venv 4.57.1 保持不动。
- 未装 `flash-linear-attention` / `causal_conv1d`，走参考实现；单条 22s。

## 产物

```
runs/results.jsonl            Qwen3.5 DMN none，40 条
runs/result.block.txt         ASR 80.0%
runs/dmn_40_none_qwenvl.jsonl Qwen3-VL 对照
qwen35_dmn_40.log             运行日志
qwen35_probe_load2.log        2 图前向 17.84 GiB
2026-11-23_qwen35_nothink.patch
```
