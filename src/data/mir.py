"""MIR-SafetyBench 读取（补充基准）。

MIR 的样本是「多图关系」攻击：`revised_prompt` 是攻击提示词，`images` 是相对
JSON 所在目录的图片路径。它没有 MIDAS 那种「关键词散到多张图」的显式载荷，
所以**没有载荷存活率**（survival=None）；只测 ASR，用来检验结论是否只在
MIDAS 上成立。

数据准备（服务器上）：
    export HUGGINGFACE_TOKEN=...
    python third_party/mir-safetybench/extract_data.py --output /path/to/MIR-SafetyBench
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator


def _iter_json(path: Path) -> Iterator[dict]:
    if path.is_dir():
        for f in sorted(path.rglob("*_final.json")):
            yield from _iter_json(f)
        return
    obj = json.loads(path.read_text(encoding="utf-8"))
    items = obj if isinstance(obj, list) else [obj]
    category = path.parent.name
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        images = [path.parent / p for p in it.get("images", [])]
        if not images:
            continue
        yield {
            "id": str(it.get("id") or f"{path.stem}_{i:04d}"),
            "category": category,
            "instruction": it.get("original_question") or it.get("revised_prompt") or "",
            "prompt": it.get("revised_prompt") or it.get("original_question") or "",
            "images": [{"path": str(p), "mask_path": None} for p in images],
            "keywords": [],
        }


def load_mir_samples(root: str, limit: int | None = None, require_files: bool = True) -> list[dict]:
    out: list[dict] = []
    for s in _iter_json(Path(root)):
        if not s["prompt"] or not s["instruction"]:
            continue
        if require_files and any(not Path(im["path"]).exists() for im in s["images"]):
            continue
        out.append(s)
        if limit is not None and len(out) >= limit:
            break
    if not out:
        raise RuntimeError(
            f"{root} 里没有读到可用的 MIR 样本。"
            "先跑 extract_data.py 解压；或检查 JSON 里的 images 路径是否相对于 JSON 所在目录。"
        )
    return out
