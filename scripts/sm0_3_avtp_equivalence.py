#!/usr/bin/env python3
"""SM0.3 AVTP 接线等价性：作者原版 vs 我们的可配置版，输出必须一致。

流程（由 run_stage0.sh 驱动）：
    apply_avtp_patch.py --mode original
    sm0_3_avtp_equivalence.py --mode original --out /tmp/avtp_orig.json
    apply_avtp_patch.py --revert
    apply_avtp_patch.py --mode instrumented
    sm0_3_avtp_equivalence.py --mode instrumented --out /tmp/avtp_inst.json
    sm0_3_avtp_equivalence.py --compare /tmp/avtp_orig.json /tmp/avtp_inst.json

只跑一次**前向**（不 generate）：decode 阶段没有视觉段，作者原版没有跳过逻辑，
generate 会暴露一个与本检查无关的崩溃。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.paths import model_path, runtime  # noqa: E402
from src.models.qwen3vl import build_inputs, layout, load  # noqa: E402
from src.pruning import avtp  # noqa: E402
from sm0_2_model_smoke import letter_image  # noqa: E402


def run(mode: str, out_path: Path) -> int:
    import torch

    rt = runtime()
    tmp = Path(tempfile.mkdtemp(prefix="sm0_3_"))
    a, b = tmp / "a.png", tmp / "b.png"
    letter_image("A", a)
    letter_image("B", b)

    loaded = load(
        model_path("qwen3vl_8b"),
        device=rt.get("device", "cuda:0"),
        dtype=rt.get("dtype", "bfloat16"),
        attn_implementation="eager",
        max_pixels=640 * 640,
        min_pixels=224 * 224,
    )
    inputs = build_inputs(
        loaded.processor,
        "Describe the two images in one short sentence.",
        [str(a), str(b)],
        loaded.device,
    )
    layout(loaded, inputs)

    if mode == "instrumented":
        if not avtp.available():
            raise SystemExit("当前 transformers 没有 instrumented 补丁")
        avtp.configure(method="avtp", budget=0.5, layers=(1, 19, 22), alpha=1.0)
    else:
        if avtp.available():
            raise SystemExit("当前 transformers 是 instrumented 版；先 --revert 再打 original")

    with torch.no_grad():
        out = loaded.model(**inputs, use_cache=False)

    logits = out.logits[0, -1].float()
    fp = {
        "mode": mode,
        "n_after": int(out.logits.shape[1]),
        "top5": torch.topk(logits, 5).indices.tolist(),
        "logit_sum": float(logits.sum().item()),
        "logit_absmax": float(logits.abs().max().item()),
    }
    if mode == "instrumented":
        recs = avtp.records()
        fp["records"] = [
            {
                "layer": r["layer"],
                "n_after": r["n_after"],
                "per_image_keep_count": r["per_image_keep_count"],
            }
            for r in recs
        ]
    out_path.write_text(json.dumps(fp, indent=2), encoding="utf-8")
    print(json.dumps(fp, indent=2))
    return 0


def compare(a: Path, b: Path) -> int:
    fa = json.loads(a.read_text())
    fb = json.loads(b.read_text())
    ok = True
    if fa["n_after"] != fb["n_after"]:
        print(f"✗ 剪枝后序列长度不同：{fa['n_after']} vs {fb['n_after']}")
        ok = False
    if fa["top5"] != fb["top5"]:
        print(f"✗ top5 不同：{fa['top5']} vs {fb['top5']}")
        ok = False
    denom = max(abs(fa["logit_sum"]), 1.0)
    rel = abs(fa["logit_sum"] - fb["logit_sum"]) / denom
    if rel > 1e-3:
        print(f"✗ logits 和相对差 {rel:.2e} > 1e-3")
        ok = False
    print(f"n_after={fa['n_after']} 相对差={rel:.2e} top5一致={fa['top5'] == fb['top5']}")
    print("SM0.3", "通过" if ok else "失败")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["original", "instrumented"])
    p.add_argument("--out", type=Path)
    p.add_argument("--compare", nargs=2, type=Path)
    a = p.parse_args()
    if a.compare:
        return compare(*a.compare)
    if not (a.mode and a.out):
        raise SystemExit("需要 --mode 和 --out，或者 --compare a b")
    return run(a.mode, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
