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
