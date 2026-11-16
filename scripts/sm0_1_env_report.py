#!/usr/bin/env python3
"""SM0.1 环境盘点：版本、显存、磁盘、模型路径、补丁状态。"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.paths import load_paths, model_path  # noqa: E402


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as e:
        return f"<失败: {e}>"


def main() -> int:
    print("== 版本 ==")
    import torch
    import transformers

    print(f"torch         {torch.__version__}")
    print(f"transformers  {transformers.__version__}")
    print(f"cuda available {torch.cuda.is_available()}")
    if transformers.__version__ != "4.57.1":
        print("✗ transformers 不是 4.57.1（AVTP patch 的实测版本）")

    print("\n== GPU ==")
    print(sh(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free",
              "--format=csv,noheader"]) or "<nvidia-smi 不可用>")

    print("\n== 磁盘 ==")
    for p in ("/", "/root", str(Path.cwd())):
        try:
            u = shutil.disk_usage(p)
            print(f"{p:12s} {u.free/2**30:.1f} GiB free / {u.total/2**30:.1f} GiB")
        except Exception as e:
            print(f"{p}: {e}")

    print("\n== 路径 ==")
    cfg = load_paths()
    for k, v in cfg.get("models", {}).items():
        p = Path(v)
        print(f"model {k:16s} {'✓' if p.exists() else '✗'} {v}")
    for k, v in cfg.get("data", {}).items():
        p = Path(v)
        print(f"data  {k:16s} {'✓' if p.exists() else '✗'} {v}")

    print("\n== 第三方 ==")
    for name in ("avtp", "midas", "mir-safetybench"):
        p = Path(cfg.get("third_party", "third_party")) / name
        print(f"{name:16s} {'✓' if p.exists() else '✗'} {p}")

    print("\n== AVTP 补丁 ==")
    try:
        from transformers.models.qwen3_vl import modeling_qwen3_vl as m

        patched = hasattr(m, "_PRUNE_CONFIG")
        print("instrumented" if patched else "未打")
        if patched:
            print("config:", json.dumps(m._PRUNE_CONFIG, ensure_ascii=False))
    except Exception as e:
        print(f"检查失败：{e}")

    print("\n== 出网 ==")
    print("GitHub:", "✓" if sh(["git", "ls-remote", "--heads", "https://github.com/zry13/AVTP"]) else "✗")
    print("HuggingFace:", "✓" if sh(["curl", "-sS", "-m", "15", "-o", "/dev/null",
                                      "-w", "%{http_code}", "https://huggingface.co"]) == "200" else "✗")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
