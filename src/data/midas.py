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
import random
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
    # 大类名优先取条目里的字段；没有就取文件所在目录名。
    # MM-SafetyBench 的 question.json 通常放在 13 个类目目录下，没有 category 字段；
    # MIR-SafetyBench 的 *_final.json 同理。
    category = source.parent.name
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


def stratified_records(records: list[dict], limit: int | None, seed: int = 0) -> list[dict]:
    """按 category 分层抽 limit 条，尽量让每个类目数量相同。

    MM-SafetyBench tiny 是跨 13 个安全类目的分层集；随手取前 N 条会偏向
    文件枚举顺序里的前几个类目。这里按类目等额分配，余数给排序后的前几类。
    """
    if limit is None or len(records) <= limit:
        return list(records)
    groups: dict[str, list[dict]] = {}
    for r in records:
        groups.setdefault(r.get("category") or "unknown", []).append(r)
    cats = sorted(groups)
    base, extra = divmod(limit, len(cats))
    rng = random.Random(seed)
    picked: list[dict] = []
    leftovers: list[dict] = []
    for i, cat in enumerate(cats):
        items = sorted(groups[cat], key=lambda r: r["id"])
        rng.shuffle(items)
        m = base + (1 if i < extra else 0)
        picked.extend(items[:m])
        leftovers.extend(items[m:])
    # 某些类目不够时，用其他类目的剩余补齐
    if len(picked) < limit:
        rng.shuffle(leftovers)
        picked.extend(leftovers[: limit - len(picked)])
    rng.shuffle(picked)
    return picked


def _record_seed(seed: int, rid: str) -> int:
    """由 id 决定图片生成 seed：resume/切片顺序变了也不改已定样本。"""
    import hashlib

    return seed + int(hashlib.sha256(str(rid).encode()).hexdigest()[:8], 16) % 1_000_000


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
    stratify: bool = False,
) -> list[dict]:
    """把指令集变成 MIDAS 多图攻击样本。已在 out_jsonl 里的 id 默认跳过。"""
    records = list(iter_instruction_records(input_path))
    if stratify:
        records = stratified_records(records, limit, seed)
    return export_from_records(
        records,
        out_jsonl=out_jsonl,
        midas_dir=midas_dir,
        out_dir=out_dir,
        limit=limit,
        seed=seed,
        keyword_mode=keyword_mode,
        llm=llm,
        tokenizer=tokenizer,
        num_images=num_images,
        resume=resume,
        game_dir=game_dir,
    )


def export_from_records(
    records: Iterable[dict],
    *,
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

    # limit 是「总样本数」，不是「本轮新增数」：resume 时已有样本要占额度
    remaining = None if limit is None else max(0, limit - len(samples))
    n = 0
    for rec in records:
        if rec["id"] in done:
            continue
        if remaining is not None and n >= remaining:
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
            seed=_record_seed(seed, rec["id"]),
            num_images=num_images,
            game_dir=game_dir,
        )
        sample["source"] = rec["source"]
        samples.append(sample)
        n += 1
        print(f"[{n}] {rec['id']} ({rec['category']}): keywords={kws} images={len(sample['images'])}")

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
