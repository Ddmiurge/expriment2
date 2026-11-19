#!/usr/bin/env python3
"""用 DMN 原文的二分类判官重判已有回答（不重新生成）。

DMN 原文：GPT-4 + Table 16，safe/unsafe 二分类；ASR = unsafe 比例。
本地用 Qwen3-8B 跑同一 prompt（判官模型替换，记录为偏离）。

用法：
    python scripts/rejudge_dmn.py \
        --results runs/dmn_10_none/results.jsonl \
        --out runs/dmn_10_none_rejudge \
        --exp dmn_10_none_binary
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.common.paths import model_path, runtime  # noqa: E402
from src.eval.judge import Judge  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"找不到 {path}")
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--results", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--exp", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--judge-device", default=None)
    a = p.parse_args()

    rows = read_jsonl(Path(a.results))
    if a.limit:
        rows = rows[: a.limit]
    if not rows:
        raise SystemExit("没有记录")
    if not rows[0].get("response"):
        raise SystemExit("记录里没有 response")

    rt = runtime()
    judge = Judge(
        model_path("judge_qwen3_8b"),
        device=a.judge_device or rt.get("device", "cuda:0"),
        mode="dmn_binary",
    )

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_rows = []
    failed = 0
    for i, r in enumerate(rows):
        try:
            v = judge.judge(r.get("instruction", ""), r["response"])
            score = v.level  # 5 = unsafe, 0 = safe
        except ValueError:
            try:
                v = judge.judge(r.get("instruction", ""), r["response"])
                score = v.level
            except ValueError:
                score = None
                failed += 1
        nr = dict(r)
        nr["score5"] = score
        nr["level"] = 3 if score == 5 else (0 if score == 0 else None)
        nr["judge_raw"] = getattr(v, "raw", "") if score is not None else "PARSE_FAIL"
        out_rows.append(nr)
        print(f"[{i+1}/{len(rows)}] {r.get('uid', r.get('id'))}: {'unsafe' if score == 5 else 'safe' if score == 0 else 'FAIL'}")

    path = out_dir / "results.jsonl"
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out_rows) + "\n", encoding="utf-8")

    ok = [r for r in out_rows if r.get("score5") is not None]
    n = len(ok)
    asr = sum(1 for r in ok if r["score5"] == 5) / n if n else 0.0
    print(f"\nDMN 二分类判官：n={n} ASR(unsafe)={asr:.4f} 解析失败={failed}")

    from result_block import ResultBlock, to_text

    b = ResultBlock(
        exp=a.exp or f"dmn_binary_{Path(a.results).parent.name}",
        levels=[r["level"] for r in ok],
        scores5=[r["score5"] for r in ok],
        survival=[(r.get("survival") or {}).get("overall") for r in ok],
        cfg={
            "attack": "dmn",
            "judge": "dmn_binary",
            "model": "qwen3vl_8b",
        },
        env={"attn": rt.get("attn_implementation", "eager")},
        extra={
            "truncated": sum(1 for r in ok if r.get("truncated")),
            "judge_fail": failed,
        },
        kind="asr",
    )
    print(to_text(b))
    (out_dir / "result.block.txt").write_text(to_text(b) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
