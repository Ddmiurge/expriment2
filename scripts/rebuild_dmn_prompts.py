#!/usr/bin/env python3
"""用 Table 11 的图像描述重建 DMN 总提示（不重新出图）。

审计 D1：旧 prompt 用 `evidence_list.description/details`（原始案件记录），
不是 Table 17 要求的、与图像配对的 T2I 描述。本脚本只改 `prompt` 字段，
images / mask / meta 全部保留，因此可以直接拿旧图重跑 none / AVTP / RI-Prune。

用法：
    python scripts/rebuild_dmn_prompts.py \
        --input data/dmn/attack_set_40.jsonl \
        --out data/dmn/attack_set_40_fixed.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.attack.dmn import build_overall_prompt  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()

    rows = []
    changed = 0
    for line in Path(a.input).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        s = json.loads(line)
        meta = (s.get("meta") or {}).get("evidence_meta") or []
        if len(meta) != len(s.get("evidence") or []):
            raise SystemExit(
                f"{s.get('uid')}: evidence={len(s.get('evidence') or [])} "
                f"evidence_meta={len(meta)}，无法配对"
            )
        old = s.get("prompt", "")
        s["prompt"] = build_overall_prompt(s["evidence"], meta)
        if s["prompt"] != old:
            changed += 1
        rows.append(s)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n",
        encoding="utf-8",
    )
    print(f"重建 {len(rows)} 条，prompt 有变化 {changed} 条 -> {out}")
    print("图片未改；可直接用 run_stage1.py 重跑 none / AVTP / RI-Prune。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
