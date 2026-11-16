#!/usr/bin/env python3
"""生成 MIDAS 多图攻击集（离线）。

输入可以是 MIR-SafetyBench 解压目录、MM-SafetyBench 的 json、或自建 jsonl。
输出每行一个样本，含图、载荷掩码、提示词。

关键词抽取默认用本地 Qwen3-8B（`--keyword-mode llm`），与 MIDAS 原文一致；
`rule` 只用于快速冒烟。

用法：
    python scripts/build_attack_set.py \
        --input /path/to/MIR-SafetyBench \
        --out data/midas/attack_set.jsonl \
        --limit 40 --keyword-mode llm
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.paths import model_path, runtime  # noqa: E402
from src.common.seed import set_seed  # noqa: E402
from src.data.midas import export, load_samples, validate_sample  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="MIR-SafetyBench 目录 / MM-SafetyBench json / jsonl")
    p.add_argument("--out", default="data/midas/attack_set.jsonl")
    p.add_argument("--out-dir", default="data/midas/images", help="图片与掩码的落盘根目录")
    p.add_argument("--midas-dir", default="third_party/midas")
    p.add_argument("--asset-dir", default=None, help="MIDAS 补充材料里的 discracted/ 目录")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--num-images", type=int, default=6)
    p.add_argument("--keyword-mode", choices=["llm", "rule"], default="llm")
    p.add_argument("--model-key", default="judge_qwen3_8b")
    p.add_argument("--resume", action="store_true", default=True)
    a = p.parse_args()

    set_seed(a.seed)
    midas_dir = Path(a.midas_dir)
    if not (midas_dir / "game").exists():
        raise SystemExit(f"找不到 {midas_dir}/game；先跑 bash env/fetch_third_party.sh")

    from src.attack.midas_offline import prepare_game_dir

    game_dir = prepare_game_dir(midas_dir, Path(a.asset_dir) if a.asset_dir else None)

    llm = tok = None
    if a.keyword_mode == "llm":
        from transformers import AutoModelForCausalLM, AutoTokenizer

        rt = runtime()
        mp = model_path(a.model_key)
        print(f"加载关键词模型：{mp}")
        tok = AutoTokenizer.from_pretrained(mp)
        llm = AutoModelForCausalLM.from_pretrained(mp, dtype="auto").to(rt.get("device", "cuda:0"))
        llm.eval()

    samples = export(
        input_path=a.input,
        out_jsonl=a.out,
        midas_dir=midas_dir,
        out_dir=a.out_dir,
        limit=a.limit,
        seed=a.seed,
        keyword_mode=a.keyword_mode,
        llm=llm,
        tokenizer=tok,
        num_images=a.num_images,
        resume=a.resume,
        game_dir=game_dir,
    )

    print(f"\n共 {len(samples)} 个样本，写入 {a.out}")
    bad = 0
    for s in load_samples(a.out, require_mask=False):
        issues = validate_sample(s)
        if issues:
            bad += 1
            print(f"✗ {s['id']}: {issues}")
    print(f"可用 {len(samples) - bad} / {len(samples)}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
