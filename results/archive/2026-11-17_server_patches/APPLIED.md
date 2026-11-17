# 2026-11-17 服务器补丁归档

**来源**：服务器侧（只读消费者）在阶段 0 实测中发现的必须改代码的问题。
本目录保存服务器带回来的原始补丁与说明；正式代码已在 Mac 上合入并推送。

## 合入记录

| 项 | 内容 |
|---|---|
| 合入提交（第一批） | `6396b8a`（判官思考模式、补丁状态检测、torchvision） |
| 合入提交（第二批） | `576bfc7`（AVTP bf16 精度对齐、逐图保留数校验） |
| 归档提交 | 本目录所在提交 |
| 判官补丁 | `2026-11-17_judge_nothink.patch` → `src/eval/judge.py` |
| 精度补丁 | `2026-11-17_avtp_bf16_parity.patch` → `src/pruning/avtp_patch.py` |
| 原始说明 | `补丁说明.md`、`补丁说明2.md`（保留服务器原文，含服务器临时路径，仅作追溯） |

## 服务器实测发现（按影响排序）

1. **Qwen3-8B 默认开 thinking，判官 8 个 token 全被思考前缀吃掉**
   - 报错：`ValueError: 判官没输出 0–3："<think>\nOkay, let's see."`
   - 改法：`apply_chat_template(..., enable_thinking=False)`，用 `try/except TypeError` 兼容不支持的模型。
2. **torchvision 缺失**
   - Qwen3-VL 的 processor 会构造 `AutoVideoProcessor`，硬依赖 torchvision；缺它 SM0.3 直接 `ImportError`。
   - 服务器实测配套版本：`torchvision==0.29.2` / `torch==2.14.1`；必须 `--no-deps` 装，否则 pip 会换掉 CUDA torch。
   - 已写入 `env/setup_venv.sh`。
3. **AVTP 两种补丁会叠加**
   - `--check` 原先只认 instrumented；SM0.3 中途崩溃停在 original 时显示「未打补丁」，
     再打 instrumented 会产生两份 `img_start_pos` → `SyntaxError: keyword argument repeated`。
   - 已改为识别 `none / original / instrumented / both` 四态；非 `none` 时拒绝叠加，并提示先 `--revert`。
4. **`CUDA_VISIBLE_DEVICES` 会重排卡号**
   - 设 `CUDA_VISIBLE_DEVICES=1` 后，物理 1 号卡是逻辑 `cuda:0`。
   - `env/paths.yaml` 的 `device` 一律写 `cuda:0`；写 `cuda:1` 会报 `invalid device ordinal`。
   - 已写入 `env/paths.example.yaml` 与 `Agent.md`。
5. **SM0.3 长度差 4 个 token（217 vs 213）：bf16 被转成 Python float**
   - instrumented 版用 `.item()` / `float()` 把图级重要性转成 float64 再算预算；
     作者原版全程 bf16 张量。bf16 只有 8 位尾数，逐层舍入让 `int()` 截断翻转。
   - 改法：保留张量运算，夹取改成作者那样的 `if` 比较。
   - 结果（服务器实测）：`n_after=217` 两边一致、logits 相对差 `0.00e+00`、top-5 一致；
     **阶段 0 六项全过**。
   - 回归：`sm0_3` 现在逐层逐图比较保留数；`tests/test_avtp_patch.py` 锁住张量路径，
     防止以后又加回 `.item()`。

## 本轮同时改动的文件

| 文件 | 改动 |
|---|---|
| `src/eval/judge.py` | 合入 judge patch；补注释说明为什么关 thinking |
| `src/pruning/avtp_patch.py` | 新增 `patch_state()` 四态检测、禁止叠加；bf16 预算路径、作者原版加只读记录器 |
| `src/pruning/avtp.py` | 新增 `original_records()`，供 SM0.3 读作者原版的逐图保留数 |
| `scripts/apply_avtp_patch.py` | `--check` 报四态；`--revert` 在本来就未打补丁时正常退出；禁止叠加 |
| `scripts/sm0_3_avtp_equivalence.py` | 新增逐层逐图保留数比较，不再只比总长度 |
| `tests/test_avtp_patch.py` | 四态识别、禁止叠加、bf16 张量路径回归，共 4 个测试 |
| `env/setup_venv.sh` | 缺 torchvision 时 `--no-deps` 安装 0.29.2 |
| `env/requirements.txt` | 说明 torchvision 为何不放进 requirements |
| `env/paths.example.yaml` | 写明 device 用逻辑编号 |
| `Agent.md` / `README.md` / `TASKS.md` / `protocols/stage0_dependency_check.md` | 记录补丁叠加、卡号、判官思考模式、bf16 精度四个坑；TASKS 换成下一轮 |

## 状态

- 本地：22 个单元测试全过；编译与 shell 语法检查通过；tiny Qwen3-VL（CPU）上
  original vs instrumented 的 `n_after`、top-5、每图保留数逐项一致。
- 服务器：**阶段 0 六项全过**（服务器报告）。原始六项输出尚未回传；拿到后放到
  本目录的 `stage0_run_2026-11-17.txt`，作为阶段 0 的正式记录。
- 判官补丁未在本地跑过模型（本机无 Qwen3-8B）；服务器侧 SM0.5 是它的验收点，
  已随阶段 0 全过。
- 下一步：建攻击集 + 阶段 1 基线（`TASKS.md`）。关卡 1 之前不跑 25% 档与拆机制对照。
