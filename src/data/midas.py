"""MIDAS 攻击集的读取与生成。

输入可以是：
  - MIDAS 风格的 jsonl：每行 {"id", "instruction", "category"}
  - MM-SafetyBench 官方 `data/processed_questions/{scenario}.json`（ID 为键）
  - MIR-SafetyBench 解压后的 `*_final.json`
  - 一个目录：递归找上面几类文件

MM-SafetyBench 每条有五段文字：`Question`（原始问题）、`Changed Question`
（改写成自包含祈使句）、`Rephrased Question` / `(SD)`（回指图片）。
MIDAS 要的是能独立成立的有害指令，论文 Figure 16 的示例逐字等于
`Changed Question`；所以主实验默认用这一列，而不是 `Question`。

输出统一是 jsonl，每行一个样本，字段见 `src/attack/midas_offline.build_sample`。
"""

from __future__ import annotations

import json
import random
import re
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

_QUESTION_KEYS = (
    "instruction",
    "original_question",
    "question",
    "Question",
    "Changed Question",
    "prompt",
)

# 允许用户用短名；最终都落到 MM-SafetyBench 的字段名
FIELD_ALIASES = {
    "question": "Question",
    "changed": "Changed Question",
    "changed_question": "Changed Question",
    "rephrased": "Rephrased Question",
    "rephrased_sd": "Rephrased Question(SD)",
    "rephrased_question": "Rephrased Question",
    "rephrased_question_sd": "Rephrased Question(SD)",
}


def normalize_field(field: str | None) -> str | None:
    if field is None:
        return None
    f = field.strip()
    for key in _QUESTION_KEYS + ("Rephrased Question", "Rephrased Question(SD)"):
        if f.lower() == key.lower():
            return key
    if f.lower() in FIELD_ALIASES:
        return FIELD_ALIASES[f.lower()]
    raise ValueError(
        f"不认识的 question field：{field!r}。可选：Question / Changed Question / "
        "Rephrased Question / Rephrased Question(SD)"
    )


def _pick_instruction(it: dict, question_field: str | None) -> str:
    if question_field:
        val = it.get(question_field)
        if val:
            return str(val)
    for key in _QUESTION_KEYS:
        val = it.get(key)
        if val:
            return str(val)
    return ""


def _records_from_obj(
    obj, source: Path, question_field: str | None = None
) -> Iterator[dict]:
    if isinstance(obj, dict):
        if any(k in obj for k in _QUESTION_KEYS):
            items = [obj]  # 单条问题
        elif "data" in obj and isinstance(obj["data"], list):
            yield from _records_from_obj(obj["data"], source, question_field)
            return
        elif obj and all(isinstance(v, dict) for v in obj.values()):
            # MM-SafetyBench processed_questions/{scenario}.json 的格式：
            # {"0": {"Question": ...}, "1": {...}}，id 是键，不在条目里。
            items = [{"id": k, **v} for k, v in obj.items()]
        else:
            items = [obj]
    elif isinstance(obj, list):
        items = obj
    else:
        return

    # 大类名优先级：条目字段 > 文件名（01-Illegal_Activitiy.json）
    # > 文件所在目录（MIR 的 Hate_Speech/Analogy_final.json）。
    stem = source.stem
    category = stem if re.match(r"^\d{2}-", stem) else source.parent.name
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        instruction = _pick_instruction(it, question_field)
        if not instruction:
            continue
        sid = str(it.get("id") or it.get("sample_id") or f"{source.stem}_{i:04d}")
        cat = str(it.get("category") or it.get("safety_category") or category or "unknown")
        # tiny 题号只在类目内唯一（168 条只有 110 个全局唯一 id），
        # 所以另给一个类目前缀的 uid；id 仍保留给 tiny 白名单比对。
        uid = f"{cat}__{sid}"
        yield {
            "id": sid,
            "uid": uid,
            "instruction": instruction,
            "category": cat,
            "source": str(source),
        }


def _keep(rec: dict, tiny: dict[str, set[str]] | None) -> bool:
    if tiny is None:
        return True
    allowed = tiny.get(rec["category"])
    return allowed is not None and str(rec["id"]) in allowed


def iter_instruction_records(
    path: str | Path,
    tiny: dict[str, set[str]] | None = None,
    question_field: str | None = None,
) -> Iterator[dict]:
    p = Path(path)
    field = normalize_field(question_field)
    if p.is_dir():
        files = sorted(p.rglob("*.jsonl")) + sorted(p.rglob("*.json"))
        files = [
            f
            for f in files
            if not f.name.startswith(".") and f.name != "TinyVersion_ID_List.json"
        ]
        for f in files:
            yield from iter_instruction_records(f, tiny, field)
        return
    if p.suffix == ".jsonl":
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                for rec in _records_from_obj(json.loads(line), p, field):
                    if _keep(rec, tiny):
                        yield rec
        return
    if p.suffix == ".json":
        with p.open(encoding="utf-8") as f:
            for rec in _records_from_obj(json.load(f), p, field):
                if _keep(rec, tiny):
                    yield rec
        return
    raise ValueError(f"不认识的指令文件：{p}")


def load_tiny_list(path: str | Path) -> dict[str, set[str]]:
    """读 MM-SafetyBench 的 TinyVersion_ID_List.json。

    格式是 [{"Scenario": "01-Illegal_Activitiy", "Sampled_ID_List": [5, 7, ...]}, ...]，
    一共 168 条、13 个场景。它不是单独的目录，而是**ID 白名单**。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for item in data:
        scenario = str(item["Scenario"])
        out[scenario] = {str(x) for x in item["Sampled_ID_List"]}
    return out


def _find_mmsb_question_dir(root: str | Path) -> Path:
    root = Path(root)
    for cand in (root / "data" / "processed_questions", root / "processed_questions", root):
        if cand.is_dir() and any(cand.glob("*.json")):
            return cand
    raise FileNotFoundError(
        f"{root} 下找不到 processed_questions；传 MM-SafetyBench 根目录或 data/processed_questions"
    )


def load_tiny_questions(
    mmsb_root: str | Path,
    tiny_list: str | Path,
    question_field: str = "Changed Question",
) -> list[dict]:
    """官方 tiny ID 白名单 + 指定字段 → 168 条自包含指令。

    会核对每条 Scenario 的 ID 是否都能找到；缺任何一条就报错并列出缺口。
    """
    tiny = load_tiny_list(tiny_list)
    qdir = _find_mmsb_question_dir(mmsb_root)
    recs = list(iter_instruction_records(qdir, tiny, question_field))
    got = {(r["category"], r["id"]) for r in recs}
    missing = [
        (scenario, sid)
        for scenario, ids in tiny.items()
        for sid in sorted(ids)
        if (scenario, sid) not in got
    ]
    if missing:
        preview = ", ".join(f"{s}#{i}" for s, i in missing[:10])
        raise ValueError(
            f"tiny 有 {sum(len(v) for v in tiny.values())} 条，只找到 {len(recs)} 条；"
            f"缺 {len(missing)} 条（前 10：{preview}）。"
            "检查 question_field 是否写错，或本地 JSON 是否完整。"
        )
    return recs


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
    question_field: str | None = None,
    tiny_list: str | Path | None = None,
) -> list[dict]:
    """把指令集变成 MIDAS 多图攻击样本。已在 out_jsonl 里的 id 默认跳过。

    `question_field` 对 MM-SafetyBench 官方 JSON 生效；`tiny_list` 不传时会在
    input 目录及上两级自动找 `TinyVersion_ID_List.json`。
    """
    tiny = None
    if tiny_list is not None:
        tiny = load_tiny_list(tiny_list)
    else:
        base = Path(input_path)
        for cand in (
            base / "TinyVersion_ID_List.json",
            base.parent / "TinyVersion_ID_List.json",
            base.parent.parent / "TinyVersion_ID_List.json",
        ):
            if cand.exists():
                tiny = load_tiny_list(cand)
                print(f"使用 tiny split：{cand}（{sum(len(v) for v in tiny.values())} 条）")
                break
    records = list(iter_instruction_records(input_path, tiny, question_field))
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
        uid = rec.get("uid") or f"{rec['category']}__{rec['id']}"
        sample = build_sample(
            sample_id=uid,
            instruction=rec["instruction"],
            category=rec["category"],
            keywords=kws,
            questioner=q,
            midas_dir=midas_dir,
            out_dir=out_dir / uid,
            seed=_record_seed(seed, rec["id"]),
            num_images=num_images,
            game_dir=game_dir,
        )
        sample["orig_id"] = rec["id"]
        sample["source"] = rec["source"]
        samples.append(sample)
        n += 1
        print(f"[{n}] {rec['id']} ({rec['category']}): keywords={kws} images={len(sample['images'])}")

    write_jsonl(samples, out_jsonl)
    return samples


def sample_uid(s: dict) -> str:
    """样本的唯一标识。旧攻击集只有 id 时，用 类目__id 补出来。"""
    uid = s.get("uid")
    if uid:
        return str(uid)
    sid = str(s.get("id", ""))
    cat = str(s.get("category", ""))
    if "__" in sid or "#" in sid:
        return sid
    return f"{cat}__{sid}" if cat else sid


def load_samples(path: str | Path, require_mask: bool = True) -> list[dict]:
    out = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            s = json.loads(line)
            if require_mask and any(not im.get("mask_path") for im in s.get("images", [])):
                continue
            s["uid"] = sample_uid(s)
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
