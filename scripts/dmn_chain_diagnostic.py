#!/usr/bin/env python3
"""给已有 DMN 样本重建带 `Frame N` 角标的 number chain（诊断用，不重新生成图）。

只替换 chain 帧：用样本 JSON 里保存的 seed / num_chain 重建同样的
positions、digits、jump，然后在每张 chain 帧左上角写 `Frame N`
（N = 该帧在整条序列里的位置）。distributed / evidence 图原样保留，
overall prompt 也不动。

用途：主 40 条里 number chain 顺序 0/40，模型按物理顺序读数字。
先拿 1 条加角标重跑，判断是“版式没给位置”还是“模型不会跳转”。

用法：
    python scripts/dmn_chain_diagnostic.py \
        --input data/dmn/attack_set.jsonl \
        --out data/dmn/attack_set_chain_labels.jsonl \
        --out-dir data/dmn/images_chain_labels \
        --limit 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.attack.dmn import build_number_chain  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"找不到 {path}")
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def rebuild(sample: dict, out_root: Path) -> dict:
    meta = sample["meta"]
    old = meta["chain"]
    base = [
        im["path"]
        for im in sample["images"]
        if im["kind"] in ("distributed", "evidence")
    ]
    expected = meta["num_distributed"] + meta["num_evidence"]
    if len(base) != expected:
        raise SystemExit(
            f"{sample['uid']}: 基础图 {len(base)} != {expected}，样本结构不对"
        )

    seq, chain = build_number_chain(
        base,
        out_root / sample["uid"] / "chain_labeled",
        k=meta["num_chain"],
        seed=meta["seed"],
        label_frames=True,
    )
    # 必须和原 chain 完全同位置、同数字、同跳转，否则不是同一个攻击
    for key in ("positions", "digits", "jump"):
        if chain[key] != old[key]:
            raise SystemExit(f"{sample['uid']}: 重建 chain 的 {key} 与原样本不一致")

    by_path = {im["path"]: im for im in sample["images"]}
    new_images = []
    for p in seq:
        if p in by_path:
            new_images.append(dict(by_path[p]))
        else:
            new_images.append({"path": p, "kind": "chain", "mask_path": None})

    out = dict(sample)
    out["images"] = new_images
    out_meta = dict(meta)
    out_meta["chain"] = chain
    out_meta["chain_labels"] = True
    out["meta"] = out_meta
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--uid", default=None)
    a = p.parse_args()

    rows = read_jsonl(Path(a.input))
    if a.uid:
        rows = [r for r in rows if r.get("uid") == a.uid]
        if not rows:
            raise SystemExit(f"没有 uid={a.uid}")
    rows = rows[: a.limit]
    if not rows:
        raise SystemExit("没有样本")

    out_rows = []
    for s in rows:
        labeled = rebuild(s, Path(a.out_dir))
        chain = labeled["meta"]["chain"]
        labels = [f["label"] for f in chain["frames"]]
        physical = [d for _, d in sorted(zip(chain["jump"], chain["digits"]))]
        print(f"{s['uid']}: {len(s['images'])} 图 -> {len(labeled['images'])} 图；chain 角标 {labels}")
        print(f"  按指针顺序应读: {chain['digits']}（jump={chain['jump']}）")
        print(f"  按物理顺序会读: {physical}")
        out_rows.append(labeled)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in out_rows) + "\n",
        encoding="utf-8",
    )
    print(f"\n写出 {len(out_rows)} 条 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
