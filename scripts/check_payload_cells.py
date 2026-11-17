#!/usr/bin/env python3
"""检查载荷掩码降到视觉 token 网格后还剩多少个单元。

问题：游戏图里的答案字形只占 0.1%–0.7% 像素；一个视觉 token 约覆盖 32×32 像素。
如果一个小字形摊在两个单元里都不到平均阈值 0.30，`payload_grid.sum()` 会是 0，
存活率就变成 `None`，第二层的剂量-反应会是空的。

用法：
    python scripts/check_payload_cells.py runs/stage1_base/results.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("results", help="run_stage1.py 产出的 results.jsonl")
    a = p.parse_args()

    path = Path(a.results)
    if path.is_dir():
        path = path / "results.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cells = [
        c
        for r in rows
        for c, has in zip(r.get("payload_cells", []), r.get("mask_present", []))
        if has
    ]
    if not cells:
        print("没有带掩码的图片（MIR 样本？）。")
        return 1

    zero = sum(1 for c in cells if c == 0)
    dist = Counter(min(c, 4) for c in cells)
    print(f"文件：{path}")
    print(f"带掩码图片：{len(cells)}")
    print(f"载荷单元数：median={statistics.median(cells):.1f} mean={statistics.mean(cells):.2f}")
    print(f"0 个载荷单元：{zero}/{len(cells)} = {zero/len(cells):.1%}")
    print("分布：", dict(sorted(dist.items())), "（4 表示 ≥4）")

    if zero / len(cells) > 0.20:
        print(
            "\n⚠ 超过 20% 的图在 token 网格上没有载荷单元。"
            "建议把 mask_to_grid 的平均池化改成 max-pooling / 任意重叠即算载荷，"
            "并在主实验前冻结口径。"
        )
        return 2
    print("\n✓ 载荷单元数足够，不需要改映射。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
