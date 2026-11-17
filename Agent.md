# Agent.md · 服务器侧操作手册

> 读这份文件的是跑在服务器上的 Agent，不是人。人的手册是 `README.md`。
> 研究背景与完整判据在 Mac 上；服务器上只有本文件、`TASKS.md` 和 `protocols/`。

---

## 一、你的位置

服务器**能 pull、不能 push**。你写的任何东西都出不来。

代码从 Mac 经 git 下来；结果靠你打印成「结果块」，由用户复制回 Mac。
没有别的通道。不要试图建立别的通道。

---

## 二、硬规则

### 规则 1 · 不写正式代码

你只能写 `results/`、`runs/` 和 `/tmp/`。

要改 `src/` 或 `scripts/`，**把补丁打印出来交给用户**，让他在 Mac 上改、push、你再 pull。
不要直接改——你改的版本回不到 Mac，会和 Mac 上的版本静默分叉。

临时 debug 脚本放 `/tmp`，不要留在仓库里。

### 规则 2 · 不改 `third_party/`

那里是按 `third_party.lock` 检出的只读副本。所有适配写在外层。
如果某个仓库必须改才能跑通：**停下来，报告**。

### 规则 3 · 只通过 `apply_avtp_patch.py` 改 transformers

AVTP 的剪枝逻辑必须注入 venv 里的 `modeling_qwen3_vl.py`。这是唯一的例外，
但只能通过仓库脚本做：

```bash
python scripts/apply_avtp_patch.py --check
python scripts/apply_avtp_patch.py --mode instrumented
python scripts/apply_avtp_patch.py --revert
```

不要手改 site-packages，不要用 `cat` 直接覆盖。脚本会留备份、做语法检查。

**dtype 纪律**：注入代码里算预算时，不要把 bf16 张量转成 Python float。
作者原版全程 bf16；转 float64 会让 `int()` 截断翻转，三层累积差几个 token
（服务器实测 217 vs 213）。`tests/test_avtp_patch.py` 锁住了这条。

**两种补丁不能叠加**。`--check` 会报 `original` / `instrumented` / `both` / `未打补丁`。
如果 SM0.3 中途崩溃，文件会停在 `original` 状态；此时直接 `--mode instrumented`
会叠成两份 `img_start_pos`，报 `SyntaxError: keyword argument repeated`。
正确顺序永远是：

```bash
python scripts/apply_avtp_patch.py --revert
python scripts/apply_avtp_patch.py --mode instrumented
```

### 规则 3b · 卡号用逻辑编号

设了 `CUDA_VISIBLE_DEVICES=1` 后，物理 1 号卡是逻辑 `cuda:0`。
`env/paths.yaml` 的 `device` 一律写 `cuda:0`；写 `cuda:1` 会报
`CUDA error: invalid device ordinal`。

### 规则 3c · torchvision 单独装

Qwen3-VL 的 processor 依赖 torchvision。它必须和 torch 配套（服务器实测
`torchvision==0.29.2` / `torch==2.14.1`），并且必须 `--no-deps` 装，
否则 pip 会顺手换掉 CUDA torch。`env/setup_venv.sh` 已处理。

### 规则 4 · 每次实验必须打印结果块

用 `scripts/result_block.py emit` 或 `run_stage1.py` 自动打印。
没有结果块的读数等于没跑。

### 规则 5 · 阶段 0 没过，不跑阶段 1

`bash scripts/run_stage0.sh` 的汇总表必须全绿。灰区不算过。

---

## 三、环境

```bash
source .venv/bin/activate
python -c "import torch, transformers; print(torch.__version__, transformers.__version__, torch.cuda.is_available())"
```

必须是 `transformers==4.57.1` 且 CUDA 可用。不是就先跑 `bash env/setup_venv.sh`。

**不要升级 transformers。** 5.x 的 `modeling_qwen3_vl.py` 结构变了，补丁锚点会失效。

---

## 四、显存纪律

- 受害者模型 Qwen3-VL-8B 与判官 Qwen3-8B **不要同时驻留一张 24GB 卡**。
  `run_stage1.py` 会先跑完生成、卸掉受害者模型、再加载判官。
- 生成阶段用 `max_pixels=640²`。OOM 时降到 512²，并在报告里写明这是偏离。
- 每卡实际可用显存以 `nvidia-smi` 为准，不要按标称算。

---

## 五、本轮任务

看 `TASKS.md`。本轮只做阶段 0。

---

## 六、报告格式

跑完一轮，按这个顺序贴：

1. 命令（完整一行）
2. 环境指纹（`python -V`、torch/transformers 版本、卡号与可用显存）
3. 输出摘要（通过/失败、关键数字）
4. 结果块（若有）
5. `cat` 哪个文件能拿到完整记录

不要贴大段日志；日志留在 `runs/`，用户会按需来取。
