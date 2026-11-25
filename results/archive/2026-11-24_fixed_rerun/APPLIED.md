# 2026-11-24 审计修复版全量重跑归档

原始报告：[`2026-11-24_fixed_rerun_report.md`](2026-11-24_fixed_rerun_report.md)

代码版本：`3275bf0`（审计修复 `51a0881` + SIVA `3275bf0`），服务器另有 N1/N2/N3 运行时修复。

## 主结果（单次，H-CoT ≥3）

| 攻击 | none | AVTP 50% | RI-Prune | RI 预算 |
|---|---:|---:|---:|---:|
| DMN | 80.0% | 77.5% | 80.0% | 25% |
| SCJ | 82.5% | 87.5% | 92.5% | 25% |
| SIVA · MMSB TYPO | 20.0% | 30.0% | 5.0% | 50% |
| SIVA · FR 75 | 10.7% | 4.0% | 5.3% | 50% |

## 原文口径（关键）

| 条件 | DMN binary | SCJ ==5 | SIVA binary MMSB | SIVA binary FR |
|---|---:|---:|---:|---:|
| none | 92.5% | 55.0% | 30.0% | 32.0% |
| AVTP 50% | 90.0% | 67.5% | 35.0% | 24.0% |
| RI-Prune | 87.5% (25%) | 52.5% (25%) | **7.5% (50%)** | **16.0% (50%)** |
| none→RI p | 0.63 | 1.00 | **0.0039** | **0.023** |

**SIVA 是唯一被 RI-Prune 显著压制的攻击，两个数据集方向一致；AVTP 50% 在 SIVA 上中性。**

## 审计修复后的结论变化

1. **D1 修复**（DMN 文本证据改为 T2I 描述）：DMN 绝对值 87.5→80.0，但仍与剪枝打平（两个判官、三个条件）。
2. **S1/S2 修复**（SCJ PT2 病句 + 分镜单图无害）：旧“RI-Prune 让 SCJ +25pp（p=0.031）”**被推翻**；修复版单次原文口径 55.0→52.5（p=1.00），5 次采样 80→90（p=0.29，不显著）。
3. **SIVA**：不是生成崩坏（截断 0–1/40 或 0–1/75，拒绝率低）；RI-Prune 50% 后 ASR 显著下降，AVTP 50% 中性；机制指向“跨碎片证据被 RI-Prune 剪掉”。

## 必须记住的局限

- **预算不一致**：SIVA RI-Prune 50%，DMN/SCJ RI-Prune 25%；不能横比预算。
- **SIVA 两个数据集/两个 query 不能互比**：MMSB TYPO 是文字图，FR 是论文原文真实物体图；FR query 是论文原文句，MMSB 是通用句。
- **判官口径差异巨大**：SIVA FR none H-CoT 10.7% vs binary 32.0%，差 21.3pp；SIVA 应报原文二分类，H-CoT 不适合。
- **SIVA 只有 Direct**：Adaptive / Transfer 未实现；只能代表黑盒朴素切图。
- **缺随机剪枝对照**：SIVA 的 RI-Prune 下降是否是“RI-Prune 打分”而非“pre-decoder 剪 50%”仍然未知。
- **报告引用的 `runs/`、`data/`、`rejudge_siva_binary.py`、`summarize_fixed_20261124.py`、`export_mmsb_images.py --variant` 本地仓库没有**；本归档只有报告，原始结果/代码补丁待补。

## 下一步

1. **补 SIVA 同位置随机剪枝 50% 对照**：如果随机也降，说明不是 RI-Prune 打分；如果随机不降，RI-Prune 的 query/cross-image 选择有因果作用。
2. **补 SIVA RI-Prune 25% 格**：和 DMN/SCJ 的 25% 对齐，解决预算不一致。
3. **补 SIVA 两数据集/两 query 的说明**：主表分两列，不能互比。
4. **补原始 results.jsonl / result.block.txt / SIVA 二分类脚本**，否则无法复核 p 值和逐条翻转。
5. 如果随机对照支持 RI-Prune 的选择机制，可考虑：
   - 防御方向：把 RI-Prune 作为 split-image 的防御；
   - 或按你的逻辑做“抗剪枝 SIVA”（Adaptive/Transfer 或冗余碎片布局）。

## 产物

```
2026-11-24_fixed_rerun_report.md   本报告
APPLIED.md                         本判读
```

原始 `runs/` 与数据文件未随报告进入本地仓库；需要服务器打包补齐。
