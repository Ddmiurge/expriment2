#!/usr/bin/env python3
"""SM0.4 MIDAS 离线化：不调 OpenAI，能生成图 + 载荷掩码 + 提示词。

通过判据：
  - 第三方 MIDAS 仓库在；
  - 至少 4 张图，每张有 mask；
  - 掩码占比在 [0.0002, 0.25]；
  - 进程里没有 import openai；
  - 提示词里有关键词的占位符。
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.attack.midas_offline import (
    GAMES_NEED_ASSETS,
    build_sample,
    extract_keywords_llm,
    extract_keywords_rule,
    questioner_fixed,
    questioner_llm,
)
from src.common.paths import model_path, runtime  # noqa: E402
from src.data.midas import validate_sample  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="tests/fixtures/smoke_instructions.jsonl")
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--keyword-mode", choices=["rule", "llm"], default="rule")
    p.add_argument("--midas-dir", default=None)
    p.add_argument("--asset-dir", default=None)
    p.add_argument("--out", default=None)
    a = p.parse_args()

    midas_dir = Path(a.midas_dir or (Path("third_party") / "midas"))
    if not (midas_dir / "game").exists():
        print(f"✗ 找不到 {midas_dir}/game。先跑 bash env/fetch_third_party.sh")
        return 1
    missing = [g for g in GAMES_NEED_ASSETS if not (midas_dir / "game" / g).exists()]
    print(f"MIDAS 目录：{midas_dir}")
    print(f"需要素材的游戏：{GAMES_NEED_ASSETS}（默认不用；补充材料里才有家居照片）")

    import json

    rows = [json.loads(l) for l in Path(a.input).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = rows[: a.limit]

    llm = tok = None
    if a.keyword_mode == "llm":
        from transformers import AutoModelForCausalLM, AutoTokenizer

        rt = runtime()
        mp = model_path("judge_qwen3_8b")
        tok = AutoTokenizer.from_pretrained(mp)
        llm = AutoModelForCausalLM.from_pretrained(mp, dtype="auto").to(rt.get("device", "cuda:0"))
        llm.eval()

    out = Path(a.out or tempfile.mkdtemp(prefix="sm0_4_"))
    ok = True
    for i, rec in enumerate(rows):
        if a.keyword_mode == "llm":
            kws = extract_keywords_llm(llm, tok, rec["instruction"])
            q = questioner_llm(llm, tok, rec["instruction"])
        else:
            kws = extract_keywords_rule(rec["instruction"])
            q = questioner_fixed(rec["instruction"])
        print(f"\n[{i+1}] {rec['id']} keywords={kws}")
        s = build_sample(
            sample_id=rec["id"],
            instruction=rec["instruction"],
            category=rec.get("category", ""),
            keywords=kws,
            questioner=q,
            midas_dir=midas_dir,
            out_dir=out / rec["id"],
            seed=i,
            asset_dir=Path(a.asset_dir) if a.asset_dir else None,
        )
        for im in s["images"]:
            print(f"  {im['game']:20s} answer={im['answer']!r} mask={im['mask_fraction']:.4f}")
        issues = validate_sample(s)
        if issues:
            ok = False
            for x in issues:
                print("  ✗", x)
        else:
            print(f"  ✓ {len(s['images'])} 张图、掩码与提示词齐全")

    if "openai" in sys.modules:
        print("✗ 进程里 import 了 openai，违反离线设计")
        ok = False
    else:
        print("\n✓ 没有 import openai")

    print("\nSM0.4", "通过" if ok else "失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
