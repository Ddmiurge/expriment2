#!/usr/bin/env python3
"""从 MIR-SafetyBench 按 9 种多图关系分层，导出扩展评测集 JSONL。

当前主实验只用了 40 条、按 6 个类目分层，基线 17.5%（地板）。
MIR 本身有 2,676 条、9 种关系；本脚本按 relation 分层抽 N 条，写成 JSONL，
供 `run_stage1.py --attack mir --samples ...jsonl` 使用。

用法：
    python scripts/build_mir_expanded.py \
        --root ~/data/MIR-SafetyBench \
        --out data/mir/attack_set_180.jsonl \
        --per-relation 20
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data.mir import _iter_json  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--per-relation", type=int, default=20)
    p.add_argument("--limit", type=int, default=None, help="总上限；默认 per_relation × 关系数")
    a = p.parse_args()

    groups: dict[str, list[dict]] = defaultdict(list)
    for s in _iter_json(Path(a.root)):
        if not s.get("prompt") or not s.get("images"):
            continue
        if any(not Path(im["path"]).exists() for im in s["images"]):
            continue
        groups[s.get("relation", "unknown")].append(s)

    if not groups:
        raise SystemExit(f"{a.root} 没有读到 MIR 样本")

    rows: list[dict] = []
    for rel in sorted(groups):
        take = groups[rel][: a.per_relation]
        rows.extend(take)
        print(f"{rel}: {len(take)}/{len(groups[rel])}")
    if a.limit:
        rows = rows[: a.limit]

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n",
        encoding="utf-8",
    )
    print(f"写出 {len(rows)} 条 -> {out}")
    print("关系数：", len(groups))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
