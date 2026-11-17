#!/usr/bin/env python3
"""把 MM-SafetyBench 的官方 tiny split 归一化成一份可复用的指令集。

tiny split 不是目录，而是仓库根目录的 `TinyVersion_ID_List.json`：
13 个场景、共 168 个题号。每道题在 `processed_questions/{scenario}.json`
里有多个文本字段；MIDAS 需要自包含的有害指令，论文 Figure 16 的示例逐字等于
`Changed Question`，所以默认取这一列。

输出是 jsonl，每行 {"id", "category", "instruction", "source"}，
供 `build_attack_set.py --input <输出>` 直接使用。

用法：
    python scripts/make_questions_tiny.py \
        --mmsb-root /path/to/MM-SafetyBench \
        --field "Changed Question" \
        --out data/midas/questions_tiny.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data.midas import load_tiny_questions, load_tiny_list, write_jsonl  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mmsb-root", required=True, help="MM-SafetyBench 根目录")
    p.add_argument(
        "--tiny-list",
        default=None,
        help="TinyVersion_ID_List.json；默认取 <mmsb-root>/TinyVersion_ID_List.json",
    )
    p.add_argument(
        "--field",
        default="Changed Question",
        help="文本字段：Changed Question / Question / Rephrased Question / Rephrased Question(SD)",
    )
    p.add_argument("--out", default="data/midas/questions_tiny.jsonl")
    p.add_argument("--show", type=int, default=3, help="打印前 N 条预览")
    a = p.parse_args()

    root = Path(a.mmsb_root)
    tiny_path = Path(a.tiny_list) if a.tiny_list else root / "TinyVersion_ID_List.json"
    if not tiny_path.exists():
        raise SystemExit(
            f"找不到 {tiny_path}。它是 MM-SafetyBench 仓库根目录的 ID 白名单，"
            "不在 data/ 下；下载地址见 README。"
        )

    tiny = load_tiny_list(tiny_path)
    expected = sum(len(v) for v in tiny.values())
    print(f"tiny 白名单：{len(tiny)} 个场景、{expected} 条")
    print(f"文本字段：{a.field}")

    recs = load_tiny_questions(root, tiny_path, a.field)
    if len(recs) != expected:
        print(f"✗ 期望 {expected} 条，实际 {len(recs)} 条")
        return 1

    write_jsonl(recs, Path(a.out))
    counts = Counter(r["category"] for r in recs)
    print(f"\n写入 {a.out}（{len(recs)} 条）")
    for cat in sorted(counts):
        print(f"  {cat:28s} {counts[cat]:3d}")
    print()
    for r in recs[: a.show]:
        print(f"  [{r['category']}#{r['id']}] {r['instruction'][:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
