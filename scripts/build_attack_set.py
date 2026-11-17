#!/usr/bin/env python3
"""生成 MIDAS 多图攻击集（离线）。

主实验输入是 **MM-SafetyBench 官方 tiny ID + `Changed Question` 字段**。
`Changed Question` 是自包含的祈使句；论文 Figure 16 的 MM-SafetyBench 示例逐字等于它。
`Question` 是原始问句（“Help in organizing...”），`Rephrased Question` 回指图片，
都不适合 MIDAS。图全部由 MIDAS 自己生成；结果要写成
「用 MM-SafetyBench 指令构造的 MIDAS 攻击」，不是「MM-SafetyBench 上的结果」。

`--stratify` 默认开：按 category 等额抽样，避免随手取前 N 条偏向文件枚举顺序里的前几类。
MIR-SafetyBench 不作为指令源；它用自己的 prompt + 图单独跑泛化表。

关键词抽取默认用本地 Qwen3-8B（`--keyword-mode llm`），与 MIDAS 原文一致；
`rule` 只用于快速冒烟。

用法：
    python scripts/build_attack_set.py \
        --input /path/to/MM-SafetyBench/data/processed_questions \
        --question-field "Changed Question" \
        --tiny-list /path/to/MM-SafetyBench/TinyVersion_ID_List.json \
        --out data/midas/attack_set.jsonl \
        --limit 40 --keyword-mode llm --stratify
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
    p.add_argument(
        "--stratify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="按 category 分层抽样（MM-SafetyBench 默认开；--no-stratify 保持文件顺序）",
    )
    p.add_argument(
        "--question-field",
        default="Changed Question",
        help="MM-SafetyBench 文本字段；主实验用 'Changed Question'（缺失时自动回退到第一个可用字段）",
    )
    p.add_argument(
        "--tiny-list",
        default=None,
        help="TinyVersion_ID_List.json；不传会在输入目录及上两级自动找",
    )
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
        stratify=a.stratify,
        question_field=a.question_field,
        tiny_list=a.tiny_list,
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
