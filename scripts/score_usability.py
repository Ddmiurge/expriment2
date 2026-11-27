#!/usr/bin/env python3
"""用 Qwen3-8B 对已有回答批量预标可用性 U（0–5）。

只读 results.jsonl，不重新生成；每条只看 instruction + response，
不把剪枝条件、ASR、H-CoT 放进 prompt。

用法：
    python scripts/score_usability.py \
        --input midas_none=runs/stage1_base_3072/results.jsonl \
        --input midas_ri25=runs/riprune25_midas_40/results.jsonl \
        --out runs/usability_midas --limit 40

输出：
    usability.jsonl   每条 U / raw
    summary.json      每个 label 的 n / mean / median / U>=3 比例
    review.csv        人工复核表（含 240 字 preview）
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.common.paths import model_path  # noqa: E402
from src.eval.usability import UsabilityJudge  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"找不到 {path}")
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", action="append", required=True, help="label=results.jsonl，可重复")
    p.add_argument("--out", required=True)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--model-key", default="judge_qwen3_8b")
    p.add_argument("--judge-device", default="cuda:0")
    p.add_argument("--resume", action="store_true", default=True)
    a = p.parse_args()

    items = []
    for spec in a.input:
        if "=" not in spec:
            raise SystemExit(f"--input 需要 label=path：{spec}")
        label, path = spec.split("=", 1)
        rows = read_jsonl(Path(path))
        if a.limit:
            rows = rows[: a.limit]
        items.append((label, Path(path), rows))

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "usability.jsonl"
    done = {}
    if a.resume and out_path.exists():
        for r in read_jsonl(out_path):
            done[(r["label"], r["uid"])] = r

    judge = UsabilityJudge(model_path(a.model_key), device=a.judge_device)
    rows = list(done.values())
    failed = 0

    for label, source, data in items:
        for i, r in enumerate(data):
            uid = r.get("uid") or r.get("id")
            key = (label, uid)
            if key in done:
                continue
            response = r.get("response") or ""
            if not response.strip():
                failed += 1
                continue
            try:
                score, raw = judge.judge(r.get("instruction", ""), response)
            except ValueError as e:
                try:
                    score, raw = judge.judge(r.get("instruction", ""), response)
                except ValueError:
                    score, raw = None, f"PARSE_FAIL: {e}"
                    failed += 1
            rec = {
                "label": label,
                "source": str(source),
                "uid": uid,
                "instruction": r.get("instruction", ""),
                "response": response,
                "U": score,
                "judge_raw": raw,
                "truncated": bool(r.get("truncated")),
            }
            rows.append(rec)
            done[key] = rec
            out_path.write_text(
                "\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n",
                encoding="utf-8",
            )
            print(f"[{label}] {i+1}/{len(data)} {uid}: U={score}")

    # summary
    summary = {}
    for label, _, data in items:
        vals = [r["U"] for r in rows if r["label"] == label and r.get("U") is not None]
        if not vals:
            summary[label] = {"n": 0, "mean": None, "median": None, "u_ge_3_rate": None}
            continue
        summary[label] = {
            "n": len(vals),
            "mean": round(sum(vals) / len(vals), 4),
            "median": statistics.median(vals),
            "u_ge_3_rate": round(sum(1 for x in vals if x >= 3) / len(vals), 4),
        }
    summary["_failed"] = failed
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # human review CSV
    with (out_dir / "review.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["label", "uid", "U", "truncated", "chars", "source", "preview"])
        for r in rows:
            w.writerow([
                r["label"], r["uid"], r.get("U"), r.get("truncated"),
                len(r.get("response", "")), r.get("source", ""),
                (r.get("response", "") or "")[:240].replace("\n", " "),
            ])

    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n写出 {len(rows)} 条 -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
