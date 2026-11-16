# 阶段 1 结果表模板（TBD）

> 这是**空表**，只定结构，不填数。所有数字从 `results.jsonl` 与结果块重算后填入。
> 不允许用估计值、四舍五入的中间量或「差不多」的手抄数字。

---

## 表 1 · 主结果：ASR 与配对差

| 剪枝器 | 预算 | n | ASR | Δ vs none (pp) | 95% CI | McNemar p | 判定 |
|---|---:|---:|---:|---:|---|---:|---|
| none | — | TBD | TBD | — | — | — | 基线 |
| avtp | 0.50 | TBD | TBD | TBD | [TBD, TBD] | TBD | TBD |
| avtp | 0.25 | TBD | TBD | TBD | [TBD, TBD] | TBD | TBD |
| sieve-alloc | 0.50 | TBD | TBD | TBD | [TBD, TBD] | TBD | TBD |
| sieve-alloc | 0.25 | TBD | TBD | TBD | [TBD, TBD] | TBD | TBD |

**表注（写论文时用）**：四档判官，2/3 计为成功；同一批样本配对；区间为 10,000 次配对 bootstrap；
McNemar 为双侧精确检验。`sieve-alloc` 是本仓库对 SIEVE 分配规则的复现，不是 SIEVE 全方法。

---

## 表 2 · 拆机制对照

| 条件 | 打分 | 分配 | ASR | Δ vs 对应主条件 (pp) | 解释 |
|---|---|---|---:|---:|---|
| avtp | 变化量 | 自适应 | TBD | — | 主条件 |
| avtp_equal | 变化量 | 等额 | TBD | TBD | 差 = 分配规则 |
| sieve-alloc | 注意力 | 等额 | TBD | — | 主条件 |
| sieve_random | 随机 | 等额 | TBD | TBD | 差 = 打分信号 |

**判读**：分配差 >10pp → 分配规则有因果作用；打分差 <5pp → 打分信号没有因果作用。

---

## 表 3 · 归因

| 条件 | 载荷存活率（均值） | 图 0 保留比 | 图 1 | 图 2 | 图 3 | 图 4 | 图 5 | 备份数 r（均值） |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| none | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| avtp 0.50 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| sieve 0.50 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

**表注**：载荷存活率 = 保留的载荷块 / 全部载荷块；图序号按输入顺序；备份数 r 是每个关键词分到的图数。

---

## 表 4 · 排除与敏感性

| 项 | 数量 | 处理 |
|---|---:|---|
| 判官解析失败 | TBD | 从 ASR 排除 |
| 回答撞 768 token 上限 | TBD | 排除后重算一次 ASR |
| 掩码占比越界 | TBD | 该图 survival=None，ASR 保留 |
| 样本图数 <4 | TBD | 不进主表 |

---

## 图 1 · 剂量-反应（证据规格）

- 横轴：载荷存活率（0–1）
- 纵轴：ASR（0–1）
- 每个点：一个「攻击 × 剪枝器 × 预算」条件
- 标注：条件名、n
- 不画拟合曲线，除非 n≥120；n=40 时只画点和 Spearman ρ
- **缺失值**：MIR 条件没有 survival，不进这张图

## 图 2 · 图间分配剖面（证据规格）

- 横轴：图序号（0–5）
- 纵轴：平均保留比例（0–1）
- 两条线：avtp / sieve-alloc（同预算）
- 预期：avtp 有起伏，sieve 接近水平线；若两条都平，归因结论收窄
- 误差：按样本的 95% bootstrap 区间（若画）

---

## 缺失值标记

- `TBD`：尚未跑或尚未判分
- `n/a`：该条件不定义（例如 MIR 的 survival）
- `—`：该列不适用

**任何 `TBD` 都不能在投稿稿里出现；要么补跑，要么删掉该行并在正文说明未做。**
