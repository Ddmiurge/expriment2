# multi-image-code · 多图剪枝安全实验

本仓库只做一件事：**测量多图越狱攻击在 token 剪枝下的表现，并解释为什么**。
研究计划在 `../ccfa-workfiles` 之外的论文目录里，单一入口是
`ccfa-workfiles/ideas/pruning-survivable-attack/多图方向_选题与实验计划_2026-11-16.md`。

它与单图复现仓库 `../code/` 是**两个独立仓库、两个独立 venv**，原因见文末「为什么不用一个仓库」。

> 目录名说明：Mac 上本地目录叫 `multi-image-code/`，远端仓库叫 `expriment2`
> （`git@github.com:Ddmiurge/expriment2.git`）。服务器 clone 后目录名是 `expriment2/`，
> 下面命令里的 `cd multi-image-code` 在服务器上换成 `cd expriment2`。
两仓库只共享三样东西：结果块的格式约定、服务器侧的操作纪律、出网边界检查脚本。

---

## 一、这台仓库的主模型与剪枝器

| 角色 | 选择 | 依据 |
|---|---|---|
| 受害者模型 | **Qwen3-VL-8B**（主） | AVTP 官方给了 Qwen3-VL 的 modeling patch；多图原生支持；8B 权重约 16 GB，单张 4090 可跑 |
| 新模型（本周预检） | **Qwen3.5-9B** | 开源、9B、原生视觉语言；先跑 `none`，AVTP 需移植；Qwen3.7 只查到 API |
| 剪枝器 A | **AVTP**（作者代码） | 唯一有真代码的多图剪枝器；**图级自适应预算**，图与图争预算 |
| 剪枝器 B | **RI-Prune（ours）** | 多图、attention-free、投影后/解码前 Top-K；论文无代码，按公式复现 |
| 剪枝器 C | **SIEVE-alloc**（本仓库实现） | SIEVE 官方代码未放；先复现最关键的“每图等额配额”（不是完整 SIEVE） |
| 攻击 A | **MIDAS**（作者代码，离线改造） | 多图越狱，载荷分散在多张图、每词至少 2 张，正好检验「备份抗删除」 |
| 攻击 B | **DMN**（复现 ours，非作者代码） | 组合式多图越狱：拆词图 + 5 证据图 + 5 number chain；原文无代码 |
| 攻击 C | **Sequential Comics / SCJ**（复现 ours） | 漫画分镜叙事越狱；四阶段、封面+6 分镜；原文无代码，Phase I/II prompt 也未公开 |
| 攻击 D | **SIVA-Direct**（复现 ours） | 把一张有害图按比例切块，固定 benign query；只做 Direct，不含 Adaptive/Transfer |
| 指令来源（主实验） | **MM-SafetyBench tiny + `Changed Question`** | MIDAS Table 2 同源；168 个 tiny ID + 自包含祈使句，图由 MIDAS 生成；按 13 类分层抽 40 |
| 泛化基准（单独表） | **MIR-SafetyBench** | 用自己的 `revised_prompt` + 图，不抽问题喂 MIDAS |
| 判官 | **Qwen3-8B + 论文 0–5 H-CoT** | ASR=score≥3；四档只在 `--judge-mode 4level` 时作对照 |

> **MM-SafetyBench tiny 是什么**：不是单独的数据目录，而是仓库根目录的
> `TinyVersion_ID_List.json`——13 个场景、共 168 条问题的 **ID 白名单**。
> 主实验取每题的 **`Changed Question`**（自包含祈使句；论文 Figure 16 的示例逐字等于它）。
> ```bash
> curl -L https://raw.githubusercontent.com/isXinLiu/MM-SafetyBench/main/TinyVersion_ID_List.json \
>   -o <MM-SafetyBench 根目录>/TinyVersion_ID_List.json
> python scripts/make_questions_tiny.py --mmsb-root <根目录> \
>   --field "Changed Question" --out data/midas/questions_tiny.jsonl
> ```
> 之后 `build_attack_set.py --input data/midas/questions_tiny.jsonl`。

**两个必须记住的版本事实**：

1. AVTP 的 Qwen3-VL patch 只在 `transformers==4.57.1` 上验过。本仓库的 venv 固定这个版本。
2. 单图仓库锁的是 `transformers==5.20.2`。**不要**把两个仓库装进同一个环境。

---

## 二、两台机器的分工

```
Mac（唯一写者）                          服务器（只读消费者）
  ├── 论文工作区                           ├── git pull（只能 pull）
  └── multi-image-code/  ← 代码只在这里写   ├── 跑实验
         │ git push                        ├── results/*.json 留在本地
         ▼                                 └── 打印结果块
    GitHub private ──────git pull──────►        │
         ▲                                      │
         └──────── 用户复制粘贴 ◄───────────────┘
```

服务器能 pull、不能 push。所以：

1. **服务器上不写正式代码。** 要改 `src/`，把补丁拿回 Mac 改、push、再 pull。
2. **`third_party/` 里的仓库不改。** 按 `third_party.lock` 检出；适配写在外层。
3. **每次实验必须打印结果块。** 没有结果块的读数等于没跑。

服务器侧的 Agent 读 `Agent.md`；本文件是给人看的。

---

## 三、起步（服务器上按顺序做）

```bash
cd multi-image-code

# 1. 建独立 venv（复用系统 CUDA torch，只覆盖 transformers 等纯 Python 包）
bash env/setup_venv.sh
source .venv/bin/activate

# 2. 路径配置
cp env/paths.example.yaml env/paths.yaml
#    填三个模型/数据路径：qwen3vl_8b、judge_qwen3_8b、数据目录

# 3. 出网边界（最先跑；确认 GitHub / HuggingFace 可达）
bash scripts/check_egress.sh https://github.com/zry13/AVTP

# 4. 第三方仓库
bash env/fetch_third_party.sh

# 5. 给 venv 里的 transformers 打 AVTP 补丁（可重复执行，自带备份）
python scripts/apply_avtp_patch.py --check
python scripts/apply_avtp_patch.py --mode instrumented
# 若 --check 报 original（SM0.3 中途崩溃会停在这个状态）：
#   python scripts/apply_avtp_patch.py --revert
#   再 --mode instrumented
# 两种补丁不能叠加，否则 img_start_pos 会重复，报 SyntaxError。

# 6. 纯 Python 自检（不占 GPU）
python -m unittest discover -s tests -v

# 7. 阶段 0 依赖核查（占 GPU；关卡没过不要开阶段 1）
bash scripts/run_stage0.sh
```

`run_stage0.sh` 结束后会打印一张通过/失败表。**六项全过**才进入阶段 1。

---

## 四、阶段 1 怎么跑

```bash
# 先跑无剪枝基线（每个攻击/样本集一次）
python scripts/run_stage1.py --attack midas --pruner none \
    --samples data/midas/attack_set.jsonl \
    --limit 40 --max-new-tokens 2048 --out runs/stage1_baseline

# 再跑剪枝条件（配对：同一批样本 id）
python scripts/run_stage1.py --attack midas --pruner avtp --budget 0.5 \
    --limit 40 --out runs/stage1_avtp50
python scripts/run_stage1.py --attack midas --pruner sieve --budget 0.5 \
    --limit 40 --out runs/stage1_sieve50
```

拆机制的两组对照（同打分换分配、同分配换打分）见协议 §2.1：

```bash
python scripts/run_stage1.py --pruner avtp_equal --budget 0.5 --limit 40 --out runs/avtp_equal50
python scripts/run_stage1.py --pruner sieve_random --budget 0.5 --limit 40 --out runs/sieve_random50
```

全条件顺序跑用 `bash scripts/run_all_stage1.sh`（`ONLY=avtp|sieve|ablation|none` 可选）。

MIR-SafetyBench 是**独立的泛化基准**，不是 MIDAS 的指令源：用它自己的多图 prompt + 图片，
没有显式载荷，只测 ASR。结果单独一张表，不混进 MM-SafetyBench 主表。

```bash
python scripts/run_stage1.py --attack mir --samples /path/to/MIR-SafetyBench \
    --pruner none --limit 40 --out runs/mir_base
python scripts/run_stage1.py --attack mir --samples /path/to/MIR-SafetyBench \
    --pruner avtp --budget 0.5 --limit 40 --out runs/mir_avtp50
```

每个条件结束会打印一个 `=== RESULT BLOCK v2 ===`。把整块（含 `=== END ===`）
粘到 Mac 的 `results/inbox/`，然后：

```bash
python scripts/result_block.py parse results/inbox/
```

解析器会校验样本数、档位字符、载荷存活率长度，并打印汇总表。
**粘贴截断会被直接抓住，不会静默算错。**

完整条件表与预注册判读在 `protocols/stage1_measure_attribution_prereg.md`。

---

## 五、目录

```
multi-image-code/
├── Agent.md                 服务器侧 Agent 常驻手册
├── TASKS.md                 当前一轮任务（每轮更新）
├── protocols/
│   ├── stage0_dependency_check.md      阶段 0 的通过判据
│   ├── stage1_measure_attribution_prereg.md  阶段 1 预注册
│   └── result_tables.md                结果表与图的空模板（TBD）
├── env/
│   ├── paths.example.yaml   路径模板（复制成 paths.yaml，不进 git）
│   ├── requirements.txt     版本锁定（transformers==4.57.1）
│   ├── setup_venv.sh        建 venv + 安装 + 打补丁
│   └── fetch_third_party.sh 按 lock 检出
├── scripts/
│   ├── check_egress.sh      出网边界探测
│   ├── result_block.py      结果块 emit / parse / summarize
│   ├── apply_avtp_patch.py  给 venv 里的 transformers 打/撤补丁
│   ├── make_questions_tiny.py  tiny ID + Changed Question → 168 条指令
│   ├── build_attack_set.py  生成 MIDAS 攻击集（图 + 掩码 + 提示词）
│   ├── check_payload_cells.py  检查载荷掩码在 token 网格上的单元数
│   ├── run_stage0.sh        阶段 0 六项检查的总入口
│   ├── sm0_1_env_report.py
│   ├── sm0_2_model_smoke.py
│   ├── sm0_3_avtp_equivalence.py
│   ├── sm0_4_midas_offline.py
│   ├── sm0_5_judge_smoke.py
│   ├── sm0_6_survival_sanity.py
│   ├── run_stage1.py        阶段 1 单条件主跑格
│   ├── run_all_stage1.sh    阶段 1 全条件顺序跑
│   └── analyze_stage1.py    Mac 侧：配对差 + 剂量-反应
├── src/
│   ├── common/              路径、随机种子、统一 no-think chat template
│   ├── models/              Qwen3-VL 加载与多图输入构造
│   ├── pruning/             图像布局、AVTP 注入与配置、SIEVE-alloc
│   ├── attack/              MIDAS 离线化、DMN、SCJ、差图载荷掩码
│   ├── eval/                0–5 H-CoT 判官、载荷存活率、回答诊断、配对统计
│   └── data/                MIDAS / MM-SafetyBench / MIR-SafetyBench 读取
├── tests/                   纯 Python 单测（不占 GPU）
│   └── fixtures/            阶段 0 用的 smoke 指令
├── third_party.lock         复现依据（进 git）
└── results/
    ├── inbox/               从服务器粘回来的结果块（进 git）
    └── archive/             阶段报告（进 git）
```

---

## 六、本仓库与论文计划的三处刻意偏离

写论文时必须如实写这三条，不要当成实现细节藏起来。

| 偏离 | 原因 | 影响 |
|---|---|---|
| **MIDAS 的关键词抽取与问话人由 API 改为本地 Qwen3-8B** | 服务器境内不能稳定直连 OpenAI，实验必须离线可复现 | 攻击样本的措辞会与原文不同；攻击强度可能略低。阶段 0 会报每次抽出的关键词 |
| **SIEVE 只复现「每图等额配额 + 注意力选择」，不做解码器前的平均池化（用第 0 层剪枝近似前置压缩）和图内合并** | SIEVE 无代码；本阶段要检验的是**分配规则**，不是它的效率收益 | 结果只能说是 SIEVE 的分配规则，不能说是 SIEVE 全方法。协议里单独标 `sieve-alloc` |
| **AVTP 的预算表是我们校准的** | 原文只报 50% / 20% / 5% 三档；我们要 25% 与 50% 对照 | 25% 档的 `[0.8, 0.6, 0.52]` 是乘出 0.2496 的近似，不是原文数字；协议里写明 |

另外两条**代码与原文不一致**的事实，已记在协议里，写论文时按代码说，不按公式说：

1. AVTP 的图级重要性用的是**每张图的 vision_start token 的隐藏状态变化**，不是论文公式里的「图内所有 token 的平均」。代码见 `third_party/AVTP/qwen3vl/modeling_qwen3vl_avtp.py` 的 `rank_list = [cos_sim[0] for cos_sim in img_cos_sim_list]`。
2. AVTP 的 forward 假设 **batch=1**（`cos_sim_candidate = ... [0]`）。本仓库所有跑格都按单样本跑。

---

## 七、为什么不用一个仓库 / 一个分支

三条理由，按重要性排：

1. **环境冲突是硬的。** AVTP 要 `transformers==4.57.1`，单图仓库锁 `5.20.2`。同一个 venv 只能留一个；分 venv 就必须在文档和脚本里明确分开，而分仓库是最不容易搞混的分法。
2. **两条线会同时跑。** 单图线的待办「第二模型重描核心曲线」还没做，随时要回服务器跑。一个 clone 一次只能 checkout 一个分支、只有一份 `TASKS.md`；服务器侧 Agent 读到错的任务表就会跑错实验。
3. **单图复现包要能独立引用。** 五轮实验的报告和归档都在旧仓库；往里塞一个新方向会让「这个仓库对应哪批结果」变得含糊。

分支唯一的好处是省一次建仓库。代价是上面三条；不划算。

---

## 八、当前状态

- **2026-11-16**：仓库建立，代码骨架、协议、阶段 0 检查落地。
- **2026-11-17**：阶段 0 **六项在服务器全过**。期间修了三处：判官思考模式、torchvision 依赖、
  AVTP original/instrumented 补丁叠加；SM0.3 首跑 `217 vs 213`，根因是 bf16 被转成
  Python float 后舍入翻转，改为保留张量运算后逐位一致。补丁与记录归档在
  `results/archive/2026-11-17_server_patches/`。
- **2026-11-17 下午**：768 那批 ASR 5.0%、40/40 截断，作废；改用官方 tiny +
  `Changed Question`、2048 后 ASR **45.0%**、12/40 截断（30%）。该批仍不是最终口径：
  判官还是四档，且 tiny 题号跨类目重复。报告归档在
  `results/archive/2026-11-17_stage1_baseline/` 与 `..._2048/`。
  处置：判官改为 **论文 0–5 H-CoT**（ASR≥3）；预算 **3072**；未截断的 28 条复用、
  只重跑 12 条截断样本；样本键改用 `category__id` 的 uid。
- **2026-11-18**：基线 **60.0%**（24/40），AVTP 50% **27.5%**（11/40），
  配对 **−32.5pp**、95% CI [−50,−15]、McNemar **p=0.0023** → 关卡 1「剪枝杀伤成立」。
  载荷存活率 1.00→0.193，关键词复原率 0.492→0.292。报告归档在
  `results/archive/2026-11-18_stage1_avtp50/`。
- **2026-11-18 归因报告**：四个剪枝条件相对基线都下降；但 `sieve`/`sieve_random`
  是**我们自己写的等额配额实现，不是 SIEVE**。已归档到
  `results/archive/2026-11-18_stage1_attribution/`，并加 `ERRATUM.md`；
  命名口径见 `protocols/condition_naming.md`。旧结果只作探索性对照，不作 SIEVE 引用。
- 远端：`git@github.com:Ddmiurge/expriment2.git`，分支 `main`。
- **下一步（本轮 4 个格）**：MIDAS `none`/`avtp` 4096 重跑；MIR-SafetyBench
  `none`/`avtp` 4096（40 条，按类目分层）。两个数据集各自配对，不跨数据集合并。
  4096 的依据是论文 Table 6 的 MIDAS 平均推理长度 3195 token。详见 `TASKS.md`。

服务器只读（能 pull、不能 push）；代码改动一律在 Mac 上做、push、服务器再 pull。
