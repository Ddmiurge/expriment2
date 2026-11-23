#!/usr/bin/env python3
"""在任意 HuggingFace 多模态 VLM 上跑 `none` 攻击（不做剪枝）。

用途：Qwen3.5-9B / InternVL3.5-8B / GLM-4.6V-Flash 这类“新模型”先做
攻击强度与多图可读性对照；AVTP 剪枝仍只在 Qwen3-VL 上做。

为什么单独一个脚本：
  - `run_stage1.py` 的 layout/survival/AVTP 依赖 Qwen3-VL 的 image token 布局；
  - 新模型架构不同，先只跑 none，避免把“模型不兼容”误写成“剪枝无效”。

用法：
    python scripts/run_none_vlm.py \
        --model /path/to/Qwen3.5-9B \
        --attack dmn --samples data/dmn/attack_set_40.jsonl \
        --out runs/dmn_qwen35_none --limit 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.common.paths import model_path, runtime  # noqa: E402
from src.common.seed import set_seed  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")


def load_vlm(model: str, *, device: str, dtype: str, max_pixels: int, attn: str | None):
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(model, trust_remote_code=True)
    if hasattr(processor, "image_processor"):
        processor.image_processor.max_pixels = int(max_pixels)
        processor.image_processor.min_pixels = int(224 * 224)
    kw = dict(dtype=getattr(torch, dtype), low_cpu_mem_usage=True, trust_remote_code=True)
    if attn:
        kw["attn_implementation"] = attn
    try:
        net = AutoModelForImageTextToText.from_pretrained(model, **kw)
    except TypeError:
        # 老版本 transformers 用 torch_dtype
        kw.pop("dtype", None)
        kw["torch_dtype"] = getattr(torch, dtype)
        net = AutoModelForImageTextToText.from_pretrained(model, **kw)
    net.to(device)
    net.eval()
    return processor, net


def build_inputs(processor, prompt: str, image_paths: list[str], device: str):
    from PIL import Image

    images = [Image.open(p).convert("RGB") for p in image_paths]
    content = [{"type": "image"} for _ in image_paths]
    content.append({"type": "text", "text": prompt})
    messages = [{"role": "user", "content": content}]
    # Qwen3.5 默认开 thinking（会在 3072 预算内吐完推理还没给答案）。
    # 与其余列的非 thinking instruct 受害者对齐，显式关掉；不支持的模型忽略参数。
    try:
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
    except TypeError:
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=images, return_tensors="pt", padding=True)
    return {k: (v.to(device) if hasattr(v, "to") else v) for k, v in inputs.items()}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, help="HF 模型目录或 repo id")
    p.add_argument("--attack", choices=["dmn", "scj"], required=True)
    p.add_argument("--samples", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--max-new-tokens", type=int, default=3072)
    p.add_argument("--max-pixels", type=int, default=640 * 640)
    p.add_argument("--device", default="cuda:0")
    p.add_argument("--dtype", default="bfloat16")
    p.add_argument("--attn-implementation", default="sdpa")
    p.add_argument("--judge-mode", choices=["hcot", "4level"], default="hcot")
    p.add_argument("--judge-device", default=None)
    p.add_argument("--no-judge", action="store_true")
    p.add_argument("--resume", action="store_true", default=True)
    a = p.parse_args()

    set_seed(0)
    samples = read_jsonl(Path(a.samples))
    if a.limit:
        samples = samples[: a.limit]
    if not samples:
        raise SystemExit(f"{a.samples} 没有样本")

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"
    done = {r["key"]: r for r in read_jsonl(results_path)}
    rows = list(done.values())
    order = {(s.get("uid") or s["id"]): i for i, s in enumerate(samples)}
    rows.sort(key=lambda r: order.get(r.get("uid") or r.get("id"), 10**9))

    import torch

    processor, net = load_vlm(
        a.model, device=a.device, dtype=a.dtype, max_pixels=a.max_pixels,
        attn=a.attn_implementation or None,
    )
    print(f"模型已加载：{a.model} @ {a.device}")

    for i, s in enumerate(samples):
        uid = s.get("uid") or s["id"]
        key = f"none__{uid}"
        if key in done and done[key].get("response"):
            continue
        image_paths = [im["path"] for im in s["images"]]
        inputs = build_inputs(processor, s["prompt"], image_paths, a.device)
        t0 = time.time()
        with torch.no_grad():
            out = net.generate(**inputs, max_new_tokens=a.max_new_tokens, do_sample=False)
        new_ids = out[0, inputs["input_ids"].shape[1]:]
        text = processor.tokenizer.decode(new_ids, skip_special_tokens=True)
        truncated = len(new_ids) >= a.max_new_tokens
        rec = {
            "key": key,
            "uid": uid,
            "id": s["id"],
            "category": s.get("category", ""),
            "instruction": s.get("instruction", ""),
            "cfg": {
                "attack": a.attack,
                "pruner": "none",
                "model": a.model,
                "max_pixels": a.max_pixels,
                "max_new_tokens": a.max_new_tokens,
                "attn": a.attn_implementation,
            },
            "response": text,
            "level": None,
            "score5": None,
            "judge_raw": None,
            "truncated": bool(truncated),
            "seconds": round(time.time() - t0, 2),
            "survival": {"overall": None, "per_image": [], "kept_count": [], "total": []},
        }
        rows.append(rec)
        write_jsonl(results_path, rows)
        print(f"[{i+1}/{len(samples)}] {uid} {len(text)} chars truncated={truncated}")

    # 判官与受害者不同卡/顺序加载，避免 2×8B 同时占显存
    if not a.no_judge:
        del net
        torch.cuda.empty_cache()
        from src.eval.judge import Judge

        jdev = a.judge_device or runtime().get("device", "cuda:0")
        judge = Judge(model_path("judge_qwen3_8b"), device=jdev, mode=a.judge_mode)
        pending = [r for r in rows if r.get("score5") is None and r.get("level") is None]
        for r in pending:
            try:
                v = judge.judge(r.get("instruction", ""), r["response"])
            except ValueError:
                try:
                    v = judge.judge(r.get("instruction", ""), r["response"])
                except ValueError:
                    r["judge_raw"] = "PARSE_FAIL"
                    continue
            if a.judge_mode == "hcot":
                r["score5"] = v.level
                r["level"] = 0 if v.level == 0 else 1 if v.level == 1 else 2 if v.level == 2 else 3
            else:
                r["level"] = v.level
                r["score5"] = None
            r["judge_raw"] = v.raw
            write_jsonl(results_path, rows)
        print(f"判官完成：{len(pending)} 条")

    ok = [r for r in rows if r.get("score5") is not None or r.get("level") is not None]
    scores5 = [r["score5"] for r in ok if r.get("score5") is not None]
    levels = [r["level"] for r in ok if r.get("level") is not None]
    from result_block import ResultBlock, to_text

    sample_set = hashlib.sha256(
        ",".join(sorted(r.get("uid") or r["id"] for r in ok)).encode()
    ).hexdigest()[:12]
    b = ResultBlock(
        exp=f"none_{a.attack}_{Path(a.model).name}",
        levels=levels,
        scores5=scores5,
        survival=[],
        cfg={
            "attack": a.attack,
            "pruner": "none",
            "model": a.model,
            "judge": a.judge_mode,
            "max_new_tokens": a.max_new_tokens,
        },
        env={"attn": a.attn_implementation, "dtype": a.dtype, "max_pixels": a.max_pixels},
        extra={
            "keepfrac": "n/a",
            "sample_set": sample_set,
            "truncated": sum(1 for r in ok if r.get("truncated")),
            "judge_fail": sum(1 for r in ok if r.get("judge_raw") == "PARSE_FAIL"),
        },
        kind="asr",
    )
    print(to_text(b))
    (out_dir / "result.block.txt").write_text(to_text(b) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
