#!/usr/bin/env python3
"""构建 SIVA-Direct 攻击集（ours，仅 Direct/naive splitting）。

输入 JSONL：`{uid, image_path, instruction, category?}`
输出：每行一个样本，images 为按比例切出的多块图，prompt 为固定文本 query。

原文 split ratio：1:1、1:2、1:3、1:1:1、1:1:1:1；主实验最强 1:1:1。
默认 vertical、normal；horizontal/reversed 作为消融。

用法：
    python scripts/build_siva_set.py \
        --input data/siva/mmsb_40.jsonl \
        --out data/siva/attack_set_40_111.jsonl \
        --out-dir data/siva/images_111 --ratio 1:1:1 --limit 40
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.attack.siva import SivaGenerationError, build_siva_sample  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--ratio", default="1:1:1",
                   choices=["1:1", "1:2", "1:3", "1:1:1", "1:1:1:1"])
    p.add_argument("--axis", default="vertical", choices=["vertical", "horizontal"])
    p.add_argument("--order", default="normal", choices=["normal", "reversed"])
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--resume", action="store_true", default=True)
    a = p.parse_args()

    src = [json.loads(x) for x in Path(a.input).read_text(encoding="utf-8").splitlines() if x.strip()]
    src = src[: a.limit]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if a.resume and out.exists():
        done = {json.loads(x).get("uid") for x in out.read_text(encoding="utf-8").splitlines() if x.strip()}
    samples = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()] if out.exists() else []

    n = 0
    for r in src:
        uid = r.get("uid")
        if uid in done:
            continue
        try:
            s = build_siva_sample(
                uid=uid,
                image_path=r["image_path"],
                instruction=r["instruction"],
                out_dir=Path(a.out_dir) / uid,
                ratio=a.ratio,
                axis=a.axis,
                order=a.order,
            )
        except (SivaGenerationError, KeyError) as e:
            print(f"✗ {uid}: {e}")
            continue
        samples.append(s)
        n += 1
        out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in samples) + "\n", encoding="utf-8")
        print(f"[{n}/{len(src)}] {uid} pieces={len(s['images'])}")

    print(f"\n共 {len(samples)} 条，ratio={a.ratio} axis={a.axis} order={a.order} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
