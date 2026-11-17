# 2026-11-17 服务器补丁归档

**来源**：服务器侧（只读消费者）在阶段 0 实测中发现的必须改代码的问题。
本目录保存服务器带回来的原始补丁与说明；正式代码已在 Mac 上合入并推送。

## 合入记录

| 项 | 内容 |
|---|---|
| 合入提交 | `6396b8a`（代码与文档） |
| 归档提交 | 本目录所在提交 |
| 判官补丁 | `2026-11-17_judge_nothink.patch` → `src/eval/judge.py` |
| 原始说明 | `补丁说明.md`（保留服务器原文，含服务器临时路径，仅作追溯） |

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

## 本轮同时改动的文件

| 文件 | 改动 |
|---|---|
| `src/eval/judge.py` | 合入 judge patch；补注释说明为什么关 thinking |
| `src/pruning/avtp_patch.py` | 新增 `patch_state()` 四态检测；两种补丁互斥，禁止叠加 |
| `scripts/apply_avtp_patch.py` | `--check` 报四态；`--revert` 在本来就未打补丁时正常退出；禁止叠加 |
| `tests/test_avtp_patch.py` | 新增 3 个测试：四态识别、标记变体、禁止叠加 |
| `env/setup_venv.sh` | 缺 torchvision 时 `--no-deps` 安装 0.29.2 |
| `env/requirements.txt` | 说明 torchvision 为何不放进 requirements |
| `env/paths.example.yaml` | 写明 device 用逻辑编号 |
| `Agent.md` / `README.md` / `TASKS.md` / `protocols/stage0_dependency_check.md` | 记录补丁叠加、卡号、判官思考模式三个坑 |

## 状态

- 本地：21 个单元测试全过；编译与 shell 语法检查通过。
- 服务器：阶段 0 **尚未报全过**；本轮只合入补丁，等下一轮 `run_stage0.sh` 结果。
- 判官补丁未在本地跑过模型（本机无 Qwen3-8B）；服务器侧 SM0.5 是它的验收点。
