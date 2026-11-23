#!/usr/bin/env python3
"""生成 SCJ 攻击集（复现 ours，不是作者原版代码）。

输入：40 条 `{id, instruction, category}` 的 JSONL（通常是 tiny + Changed Question）。
输出：每行一个 SCJ 样本，含封面 + N 分镜与 PT1/PT2/PT3 总提示。

依赖：
  - 本地 Qwen3-8B（辅助 LLM：GI/RS/CR/IS + 故事脚本）
  - 本地 FLUX.1-schnell（T2I）
  两者建议放不同 GPU：--aux-device cuda:0 --t2i-device cuda:1

用法：
    CUDA_VISIBLE_DEVICES=3,4 python scripts/build_scj_set.py \
        --input data/midas/questions_tiny.jsonl \
        --out data/scj/attack_set.jsonl \
        --out-dir data/scj/images \
        --limit 40 --aux-device cuda:0 --t2i-device cuda:1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.attack.aux_llm import AuxLLM  # noqa: E402
from src.attack.scj import ScjGenerationError, build_scj_sample  # noqa: E402
from src.attack.t2i import FluxBackend, SDXLBackend  # noqa: E402
from src.common.paths import model_path  # noqa: E402
from src.common.seed import set_seed  # noqa: E402


def load_records(path: str) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        instruction = r.get("instruction") or r.get("Question") or r.get("question")
        if not instruction:
            continue
        rid = str(r.get("id") or len(rows))
        cat = str(r.get("category", "unknown"))
        rows.append({"id": rid, "uid": r.get("uid") or f"{cat}__{rid}",
                     "instruction": instruction, "category": cat})
    return rows


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out", default="data/scj/attack_set.jsonl")
    p.add_argument("--out-dir", default="data/scj/images")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--panels", type=int, default=6,
                   help="分镜数 N；原文未写，固定 6 + 封面 = 7 图/条")
    p.add_argument("--aux-model-key", default="judge_qwen3_8b")
    p.add_argument("--t2i-backend", choices=["flux", "sdxl"], default="flux")
    p.add_argument("--flux-model", default=None, help="FLUX 路径；默认读 paths.yaml models.flux")
    p.add_argument("--sdxl-model", default=None, help="SDXL 路径；默认读 paths.yaml models.sdxl")
    p.add_argument("--t2i-steps", type=int, default=None)
    p.add_argument("--t2i-guidance", type=float, default=None)
    p.add_argument("--aux-device", default="cuda:0")
    p.add_argument("--t2i-device", default="cuda:1")
    p.add_argument("--resume", action="store_true", default=True)
    a = p.parse_args()

    set_seed(a.seed)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if a.resume and out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["uid"])
            except Exception:
                pass

    records = load_records(a.input)[: a.limit]
    print(f"输入 {len(records)} 条，已完成 {len(done)} 条")

    aux = AuxLLM(model_path(a.aux_model_key), device=a.aux_device, seed=a.seed)
    if a.t2i_backend == "flux":
        t2i_path = a.flux_model or model_path("flux")
        t2i = FluxBackend(
            t2i_path,
            device=a.t2i_device,
            num_inference_steps=a.t2i_steps or 4,
            guidance_scale=0.0 if a.t2i_guidance is None else a.t2i_guidance,
        )
    else:
        t2i_path = a.sdxl_model or model_path("sdxl")
        t2i = SDXLBackend(
            t2i_path,
            device=a.t2i_device,
            num_inference_steps=a.t2i_steps or 30,
            guidance_scale=7.0 if a.t2i_guidance is None else a.t2i_guidance,
        )
    print(f"辅助 LLM: {a.aux_model_key} @ {a.aux_device}")
    print(f"T2I: {a.t2i_backend} @ {a.t2i_device}")

    samples = []
    if out.exists() and a.resume:
        samples = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]

    n = 0
    for rec in records:
        if rec["uid"] in done:
            continue
        print(f"\n[{n+1}] {rec['uid']} {rec['instruction'][:80]}")
        try:
            s = build_scj_sample(
                uid=rec["uid"],
                instruction=rec["instruction"],
                category=rec["category"],
                aux=aux,
                t2i=t2i,
                out_dir=Path(a.out_dir) / rec["uid"],
                seed=a.seed + n,
                n_panels=a.panels,
            )
        except ScjGenerationError as e:
            print(f"  ✗ 跳过：{e}")
            continue
        samples.append(s)
        n += 1
        out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in samples) + "\n",
                       encoding="utf-8")
        print(f"  ✓ images={len(s['images'])} theme={s['script']['theme']!r}")

    lens = [
        im["prompt_tokens"]
        for s in samples
        for im in s.get("meta", {}).get("image_meta", [])
        if im.get("prompt_tokens")
    ]
    if lens:
        t5 = [x["t5_tokens"] for x in lens if x.get("t5_tokens") is not None]
        clip = [x["clip_tokens"] for x in lens if x.get("clip_tokens") is not None]
        if t5:
            print(f"\nT2I prompt T5 tokens：max={max(t5)} median={sorted(t5)[len(t5)//2]} limit={lens[0]['t5_limit']}")
            if max(t5) > lens[0]["t5_limit"]:
                print("⚠ 有 prompt 超过 T5 上限，会被截断；见 reproduction_deviation_log.md")
        if clip:
            print(f"T2I prompt CLIP tokens：max={max(clip)} median={sorted(clip)[len(clip)//2]} limit={lens[0]['clip_limit']}")
    print(f"\n共 {len(samples)} 条，写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
