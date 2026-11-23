# 新受害者模型候选（2026-11-23，cc-web 查证）

> 目标：在 Qwen3-VL-8B 之外，找一个**开源、本地可跑、支持多图**的新 8–9B 模型。
> 硬门槛：能本地加载 + 24GB 单卡实测 + AVTP 可移植；三者缺一，就只能做 `none`。

## 候选表

| 模型 | 参数 | 开源 | 多图 | 24GB bf16 | AVTP | 备注 |
|---|---:|---|---|---|---|---|
| **Qwen3.5-9B** | 9B | ✅ | ✅ | 需实测 | ❌ 需移植 | 首选新 Qwen；Qwen3.5 是统一视觉语言系列 |
| **InternVL3.5-8B** | 8.5B | ✅ | ✅ | 需实测 | ❌ 需移植 | 非 Qwen 首选；InternViT + LLM |
| **GLM-4.6V-Flash** | 9B | ✅ | ✅ | 需实测 | ❌ 需移植 | 较新，MoE/GLM4V 架构 |
| Qwen3.8-27B | 27B | ✅ | 可能 | ❌ | ❌ | 太大，不优先 |
| Qwen3.6-27B | 27B | ✅ | 可能 | ❌ | ❌ | 同上 |
| Qwen3-VL-8B | 8B | ✅ | ✅ | ✅ | ✅ 官方补丁 | 当前主模型 |
| Qwen3.7-Flash / Plus | API | ❌ | ✅ | — | ❌ | 只能 API `none` |
| Qwen3.7-Max | API | ❌ | ❌ | — | ❌ | 纯文本 |

## 关键判断

1. **Qwen3.5-9B 的 AVTP 移植难度高**：`Qwen3_5TextModel.forward` 混合
   `linear_attention` 与 full attention，层循环里没有 Qwen3-VL 的
   `img_start_pos/img_end_pos`，也没有 deepstack 的同步点。AVTP 的
   “层间 hidden-state cosine 剪枝”不能直接照搬；要先确认剪枝后 linear attention
   的 recurrent state 是否仍一致。
2. **InternVL3.5-8B 更接近常规 Transformer LLM**：视觉 token 注入后由语言模型
   继续前向，移植 AVTP 的层间剪枝相对直接；但仍需改 image segment 识别。
3. **Qwen3.7 只有 API**：不能拿 hidden states，不能跑 AVTP；只能做 `none`。
4. **Qwen3.8-27B 太大**：24GB bf16 放不下；量化会改变攻击/剪枝，不作为首选。

## 运行环境

Qwen3.5 需要 **transformers 5.x**；本仓库主 venv 固定 `transformers==4.57.1`
（AVTP 的 Qwen3-VL 补丁只在该版本验过）。因此：

- Qwen3.5 的 `probe_victim_model.py` / `run_none_vlm.py` 放在**独立 venv**；
- 不要升级主 venv，否则 Qwen3-VL + AVTP 的补丁会坏；
- 两个 venv 共享模型目录与数据目录，不共享 site-packages。

## 建议顺序

1. Qwen3.5-9B：先 `none`，验证 24GB 和多图可读性；再评估 AVTP 移植。
2. InternVL3.5-8B：如果 Qwen3.5 移植不可行，作为剪枝移植候选。
3. GLM-4.6V-Flash：备选；MoE 移植风险最高。
4. 剪枝主实验暂时仍用 Qwen3-VL-8B，不因新模型阻塞。

## 来源

- Qwen3.8 / Qwen3.5 开源仓库：https://github.com/QwenLM/Qwen3.8
- InternVL 仓库与模型表：https://github.com/OpenGVLab/InternVL
- GLM-V 仓库：https://github.com/zai-org/GLM-V
- Qwen3.7-Flash：https://www.qianwenai.com/models/qwen3.7-flash
- Qwen3.7-Plus：https://www.qianwenai.com/models/qwen3.7-plus
- Qwen3.7-Max：https://www.qianwenai.com/models/qwen3.7-max
