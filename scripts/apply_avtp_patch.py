#!/usr/bin/env python3
"""给当前 venv 里的 transformers 打/撤多图剪枝补丁。

补丁只改一个文件：`transformers/models/qwen3_vl/modeling_qwen3_vl.py`。
第一次打补丁时会在旁边留一个 `.multi_image_orig` 备份；`--revert` 用它恢复。

用法：
    python scripts/apply_avtp_patch.py --check
    python scripts/apply_avtp_patch.py --mode instrumented
    python scripts/apply_avtp_patch.py --mode original     # 只用于 sm0_3 等价性校验
    python scripts/apply_avtp_patch.py --revert
"""

from __future__ import annotations

import argparse
import ast
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pruning.avtp_patch import (  # noqa: E402
    PatchError,
    is_patched,
    patch_instrumented,
    patch_original,
)

TARGET_REL = Path("models") / "qwen3_vl" / "modeling_qwen3_vl.py"
BACKUP_SUFFIX = ".multi_image_orig"


def locate() -> Path:
    try:
        import transformers
    except ImportError as e:
        raise SystemExit(f"当前 python 没有 transformers：{e}")
    if transformers.__version__ != "4.57.1":
        print(
            f"⚠ transformers 版本是 {transformers.__version__}，不是 4.57.1。"
            "补丁锚点可能对不上；先确认 env/setup_venv.sh 跑过。",
            file=sys.stderr,
        )
    return Path(transformers.__file__).resolve().parent / TARGET_REL


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--revert", action="store_true")
    g.add_argument("--mode", choices=["instrumented", "original"])
    a = p.parse_args()

    f = locate()
    if not f.exists():
        raise SystemExit(f"找不到 {f}")
    backup = f.with_name(f.name + BACKUP_SUFFIX)
    text = f.read_text(encoding="utf-8")

    if a.check:
        print(f"文件：{f}")
        print(f"状态：{'已打补丁' if is_patched(text) else '未打补丁'}")
        print(f"备份：{'有' if backup.exists() else '无'}")
        return 0

    if a.revert:
        if not backup.exists():
            raise SystemExit(f"没有备份 {backup}，无法撤销")
        shutil.copy2(backup, f)
        print(f"已从 {backup} 恢复")
        return 0

    if is_patched(text):
        raise SystemExit("文件已经是注入状态。先 --revert，再选一个模式重打。")
    if not backup.exists():
        shutil.copy2(f, backup)
        print(f"已备份到 {backup}")

    try:
        patched = patch_original(text) if a.mode == "original" else patch_instrumented(text)
    except PatchError as e:
        raise SystemExit(f"打补丁失败：{e}")

    try:
        ast.parse(patched)
    except SyntaxError as e:
        raise SystemExit(f"打完不是合法 Python：{e}")

    f.write_text(patched, encoding="utf-8")
    print(f"已打 {a.mode} 补丁：{f}")
    print("回滚：python scripts/apply_avtp_patch.py --revert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
