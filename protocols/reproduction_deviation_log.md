# 复现偏离日志

> 目的：记录与原文不同、且**可能影响结果**的选择。
> 如果某个攻击的 ASR 明显偏低，先按本日志逐条回看，不要先怀疑“攻击本身不行”。

---

## 2026-11-19 · DMN · T2I 的 prompt 长度

**原文**：T2I 用 **GPT Image 1**；Table 11 生成的是一段很长的场景描述（人物、环境、光线、视角、物体细节）。

**我们的选择**：本地 **FLUX.1-schnell**（Apache 2.0，4 步）。

**已核实**：

- diffusers `FluxPipeline._get_t5_prompt_embeds` 的 `max_sequence_length=512`，`truncation=True`；
- FLUX 的 CLIP 分支仍是 77 token；
- SDXL 的 CLIP 文本编码器只有 77 token。

**未核实**：

- Qwen3-8B 实际生成的 T2I prompt 有多少 token；
- 是否超过 FLUX 的 512。

**风险**：

- 如果实际 prompt >512，T5 会截断，证据图可能丢细节；
- 如果 ASR 偏低，**先看这个**：在 D0/D1 里打印每个 T2I prompt 的 T5/CLIP token 数；
- 若截断严重：让辅助 LLM 把 prompt 压到 512 内（记录为退化），或换 GPT Image 1 API 做保真度对照。

**决策**：先用 FLUX；SDXL 不作为主方案（77 token 一定截）。D0 必须打印 token 长度。

---

## 同批 DMN 的其他偏离

| 项 | 原文 | 我们 | 影响 |
|---|---|---|---|
| 辅助 LLM | Gemini-2.5-flash | 本地 Qwen3-8B | 案件证据质量/拒答率可能不同 |
| 辅助 system prompt | 原文未单列 | 加“公共安全训练材料、不要拒答” | 为降低本地模型拒答；属 LLM 替代的一部分 |
| 拆词图版式 | Figure 1，无精确坐标 | 白底、红词置顶、3 个空编号 | 视觉细节可能不同 |
| number chain 序数 | 正文示例有 “12nd” 笔误 | 标准英文序数（12th） | 排版细节 |
| 受害者 | GPT/Claude/Gemini/Qwen3-VL-plus 等 | Qwen3-VL-8B | 实验设计，不是方法复现 |
| 判官 | GPT-4 二分类 | Qwen3-8B 0–5 H-CoT，≥3 | 度量口径不同，绝对值不可比 |

## 记录纪律

- 每加一个与原文不同的选择，先在这里加一行，再写代码；
- 结果不佳时，按“原文 → 我们 → 影响”逐条排查；
- 不要把这里记录的退化写成“原文方法”。

---

## 2026-11-19 · DMN · 图像分辨率与图片数

**原文**：受害者按原生图像分辨率处理；单样本图片数 = 指令词数 + 5 证据 + 5 number chain，常见 15–30 张。

**我们**：`run_stage1.py` 默认 `max_pixels=640²`（为 MIDAS/AVTP 的显存设的）。

**风险**：

- DMN 依赖模型读图上的**红词、编号、number chain 数字**；640² 下小字可能糊掉；
- 15–30 张图 × 640²，视觉 token 数远高于 MIDAS 的 6 张，eager 注意力可能 OOM；
- 如果模型读不到数字/词，ASR 低不能归因于“攻击弱”。

**D0 必查**：

1. 1 条样本在 640² 下，模型能否复述 number chain 数字；
2. 显存峰值；OOM 就降 `max_pixels` 或减少图片数（后者是退化，必须记录）；
3. 若 640² 读不到、1024² 能读到，记录分辨率是影响因素，并评估显存。

**决策**：先 640² 跑 D0；读不到再升，不静默降级。

---

## 2026-11-19 · DMN · 辅助 LLM 的 T2I prompt 长度

**已核实**：FLUX T5 上限 512；CLIP 分支 77；SDXL CLIP 77。

**未核实**：Qwen3-8B 实际输出长度。

**D0/D1 必查**：`build_dmn_set.py` 已打印每个证据 prompt 的 T5/CLIP token 数；
若 T5 max >512，按本日志首条处理。


---

## 2026-11-19 · DMN · number chain `Frame N` 角标（诊断）

**原文**：number chain 帧只有数字和“next number from the Y-th frame”，没有显式帧号。

**我们**：新增 `--chain-labels` / `scripts/dmn_chain_diagnostic.py`，在 chain 帧左上角写 `Frame N`（N = 整条序列位置）。默认关闭，主 40 条不受影响。

**原因**：主 40 条数字命中 85.5%，链顺序 0/40；需要区分“版式没给位置”与“模型不会跳转”。

**影响**：

- 只作 1 条诊断，不进入主结果；
- 若诊断有效并决定采用，必须 none / AVTP 0.5 / 0.25 全条件重跑，并在论文中明确这是版式偏离；
- 角标不是原文方法的一部分，不能写成“完整复现 DMN”。
