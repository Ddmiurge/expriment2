# TASKS · 本轮：阶段 0 依赖核查（2026-11-16 发车）

> 服务器侧只做这一轮。**阶段 0 全过之前不要跑阶段 1。**
> 本轮不产出研究数字；产出的是「环境能不能跑、接线对不对、攻击输入合不合法」。

---

## 0 · 先做三件事

```bash
cd multi-image-code
source .venv/bin/activate          # 没建过就先 bash env/setup_venv.sh
cp env/paths.example.yaml env/paths.yaml
# 编辑 env/paths.yaml：qwen3vl_8b / judge_qwen3_8b / 数据路径

bash scripts/check_egress.sh
bash env/fetch_third_party.sh
```

`fetch_third_party.sh` 按 `third_party.lock` 检出三个仓库。若 lock 里的 SHA 拉不到，
**先报告，不要自己 --relock**——那会改变复现依据。

---

## 1 · 跑阶段 0

```bash
bash scripts/run_stage0.sh
```

六项检查，全过才继续。逐项判据见 `protocols/stage0_dependency_check.md`。

预期时间：模型加载三次（SM0.2 一次、SM0.3 原版与可配置版各一次），约 10–20 分钟；其余是 CPU/IO。

---

## 2 · 回传什么

把下面四样贴给用户（或按用户指定的方式）：

1. **`run_stage0.sh` 的完整输出**（含六项汇总表）。
2. `nvidia-smi` 的每卡可用显存（不是标称）。
3. SM0.2 的 `image_grid_thw` 与每图 token 数。
4. SM0.3 的 `n_after`、top5、logits 相对差。

**不要**贴模型权重路径以外的个人目录；不要贴 API key（本仓库不需要 API key）。

---

## 3 · 失败时怎么处理

| 失败项 | 先做什么 | 不要做什么 |
|---|---|---|
| SM0.1 版本不对 | `which python` 确认在 `.venv`；重跑 `env/setup_venv.sh` | 不要 `pip install -U transformers` |
| SM0.2 图片数/字母不对 | 先换更清楚的合成图；再检查 processor 版本 | 不要改 `src/models/qwen3vl.py` 的 chat template 去硬凑 |
| SM0.3 不等价 | 对照注入代码的层号/预算/排序方向 | 不要调 `sm0_3` 的容差让它过 |
| SM0.4 掩码越界 | 记录是哪张图、哪个游戏、占比多少 | 不要放宽 `validate_sample` 的阈值 |
| SM0.5 判官方向错 | 人工看 20 条 raw，再报告 | 不要改 rubric 让 smoke 过 |
| 任何需要改 `src/` 的 | 把补丁打印出来，交回 Mac | 不要在服务器上直接改 |

---

## 4 · 通过之后（下一轮，先不要做）

1. 准备指令来源（二选一）：
   - **MM-SafetyBench**（单图线已有，服务器上直接可用）：`--input <MM-SafetyBench 的 json>`
   - **MIR-SafetyBench**：先 `export HUGGINGFACE_TOKEN=...`，再
     `python third_party/mir-safetybench/extract_data.py --output /path/to/MIR-SafetyBench`
2. 生成正式攻击集：
   ```bash
   python scripts/build_attack_set.py \
       --input <MIR-SafetyBench 或 MM-SafetyBench 路径> \
       --out data/midas/attack_set.jsonl --limit 40 --keyword-mode llm
   ```
   关键词模式默认 `llm`（本地 Qwen3-8B，按 MIDAS 原文 prompt）；`rule` 只用于快速冒烟。
3. 跑阶段 1 基线：`python scripts/run_stage1.py --pruner none --limit 40 --out runs/base`。
4. 按 `protocols/stage1_measure_attribution_prereg.md` 跑其余条件。

---

## 5 · 本轮禁止

- 不要跑阶段 1（结果块会污染正式表）。
- 不要改 `third_party/`。
- 不要在服务器上写 `src/` 或 `scripts/`。
- 不要用 OpenAI API（包括判官、关键词抽取、问话人生成）。
