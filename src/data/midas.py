"""MIDAS 攻击集的读取与生成。

输入可以是：
  - MIDAS 风格的 jsonl：每行 {"id", "instruction", "category"}
  - MIR-SafetyBench 解压后的 `*_final.json`（取 original_question）
  - MM-SafetyBench 的 json（取 question）
  - 一个目录：递归找上面三类文件

输出统一是 jsonl，每行一个样本，字段见 `src/attack/midas_offline.build_sample`。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

from ..attack.midas_offline import (
    build_sample,
    extract_keywords_llm,
    extract_keywords_rule,
    questioner_fixed,
    questioner_llm,
    write_jsonl,
)


def _records_from_obj(obj, source: Path) -> Iterator[dict]:
    if isinstance(obj, dict):
        if "data" in obj and isinstance(obj["data"], list):
            yield from _records_from_obj(obj["data"], source)
            return
        items = [obj]
    elif isinstance(obj, list):
        items = obj
    else:
        return
    category = source.parent.name if source.name.endswith("_final.json") else ""
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        instruction = (
            it.get("instruction")
            or it.get("original_question")
            or it.get("question")
            or it.get("prompt")
            or ""
        )
        if not instruction:
            continue
        sid = str(it.get("id") or it.get("sample_id") or f"{source.stem}_{i:04d}")
        cat = str(it.get("category") or it.get("safety_category") or category or "unknown")
        yield {"id": sid, "instruction": instruction, "category": cat, "source": str(source)}


def iter_instruction_records(path: str | Path) -> Iterator[dict]:
    p = Path(path)
    if p.is_dir():
        files = sorted(p.rglob("*.jsonl")) + sorted(p.rglob("*.json"))
        files = [f for f in files if not f.name.startswith(".")]
        for f in files:
            yield from iter_instruction_records(f)
        return
    if p.suffix == ".jsonl":
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield from _records_from_obj(json.loads(line), p)
        return
    if p.suffix == ".json":
        with p.open(encoding="utf-8") as f:
            yield from _records_from_obj(json.load(f), p)
        return
    raise ValueError(f"不认识的指令文件：{p}")


def export(
    *,
    input_path: str | Path,
    out_jsonl: str | Path,
    midas_dir: str | Path,
    out_dir: str | Path,
    limit: int | None = None,
    seed: int = 0,
    keyword_mode: str = "rule",
    llm=None,
    tokenizer=None,
    num_images: int = 6,
    resume: bool = True,
    game_dir: str | Path | None = None,
) -> list[dict]:
    """把指令集变成 MIDAS 多图攻击样本。已在 out_jsonl 里的 id 默认跳过。"""
    out_jsonl = Path(out_jsonl)
    midas_dir = Path(midas_dir)
    out_dir = Path(out_dir)
    done: set[str] = set()
    if resume and out_jsonl.exists():
        with out_jsonl.open(encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["id"])
                except Exception:
                    pass

    samples: list[dict] = []
    if out_jsonl.exists() and resume:
        with out_jsonl.open(encoding="utf-8") as f:
            samples = [json.loads(line) for line in f if line.strip()]

    n = 0
    for rec in iter_instruction_records(input_path):
        if rec["id"] in done:
            continue
        if limit is not None and n >= limit:
            break
        if keyword_mode == "llm":
            if llm is None or tokenizer is None:
                raise ValueError("keyword_mode=llm 需要传 llm 和 tokenizer")
            kws = extract_keywords_llm(llm, tokenizer, rec["instruction"])
            q = questioner_llm(llm, tokenizer, rec["instruction"])
        elif keyword_mode == "rule":
            kws = extract_keywords_rule(rec["instruction"])
            q = questioner_fixed(rec["instruction"])
        else:
            raise ValueError(f"keyword_mode={keyword_mode!r} 只允许 llm / rule")
        if not kws:
            print(f"跳过 {rec['id']}：抽不出关键词")
            continue
        sample = build_sample(
            sample_id=rec["id"],
            instruction=rec["instruction"],
            category=rec["category"],
            keywords=kws,
            questioner=q,
            midas_dir=midas_dir,
            out_dir=out_dir / rec["id"],
            seed=seed + n,
            num_images=num_images,
            game_dir=game_dir,
        )
        sample["source"] = rec["source"]
        samples.append(sample)
        n += 1
        print(f"[{n}] {rec['id']}: keywords={kws} images={len(sample['images'])}")

    write_jsonl(samples, out_jsonl)
    return samples


def load_samples(path: str | Path, require_mask: bool = True) -> list[dict]:
    out = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            s = json.loads(line)
            if require_mask and any(not im.get("mask_path") for im in s.get("images", [])):
                continue
            out.append(s)
    return out


def validate_sample(s: dict, min_images: int = 4) -> list[str]:
    """返回问题列表；空列表表示可用。"""
    issues = []
    if len(s.get("images", [])) < min_images:
        issues.append(f"只有 {len(s.get('images', []))} 张图（<{min_images}）")
    for im in s.get("images", []):
        for key in ("path", "mask_path"):
            if not Path(im.get(key, "")).exists():
                issues.append(f"缺文件 {key}={im.get(key)}")
        frac = im.get("mask_fraction", -1)
        if not (0.0002 <= frac <= 0.25):
            issues.append(
                f"图 {im.get('index')} 掩码占比 {frac:.4f} 超出 [0.0002, 0.25]；"
                "差图可能包含了非答案区域的布局变化"
            )
    return issues
