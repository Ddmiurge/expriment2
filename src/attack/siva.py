"""SIVA-Direct（ours）——split-image visual jailbreak。

原文：*Robustness of Vision Language Models Against Split-Image Harmful Input
Attacks*（arXiv:2602.08136）。Direct-SIVA 是黑盒、无视觉过滤的设置：

  - 保留固定/通用的文本 query，不改写；
  - 把一张有害图按比例切成多块；
  - 把这些块作为多图输入一起送给 VLM。

本文件只实现 Direct（naive splitting），不实现 Adaptive / Transfer
（后者需要白盒优化或 Adv-KD，是独立工作量）。

原文的 split ratio：1:1、1:2、1:3、1:1:1、1:1:1:1；主实验最强的是 1:1:1。
默认 vertical、按原图顺序；horizontal / out-of-order 作为消融开关。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

SPLIT_RATIOS = {
    "1:1": [1, 1],
    "1:2": [1, 2],
    "1:3": [1, 3],
    "1:1:1": [1, 1, 1],
    "1:1:1:1": [1, 1, 1, 1],
}


class SivaGenerationError(RuntimeError):
    pass


@dataclass
class SplitMeta:
    path: str
    index: int
    box: tuple[int, int, int, int]


def split_image(
    src: str | Path,
    out_dir: str | Path,
    *,
    ratio: str = "1:1:1",
    axis: str = "vertical",
    order: str = "normal",
) -> list[SplitMeta]:
    """按比例切图；返回每块路径与 crop box。

    ratio：`1:1`/`1:2`/`1:3`/`1:1:1`/`1:1:1:1`，表示各块边长比例。
    axis：vertical（左右切）或 horizontal（上下切）。
    order：normal / reversed（只影响落盘顺序，不改变块内容）。
    """
    if ratio not in SPLIT_RATIOS:
        raise SivaGenerationError(f"不支持的 split ratio：{ratio}")
    if axis not in ("vertical", "horizontal"):
        raise SivaGenerationError(f"axis 只允许 vertical/horizontal：{axis}")
    if order not in ("normal", "reversed"):
        raise SivaGenerationError(f"order 只允许 normal/reversed：{order}")

    src = Path(src)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    w, h = img.size
    parts = SPLIT_RATIOS[ratio]
    total = sum(parts)
    if axis == "vertical":
        sizes = [max(1, int(w * p / total)) for p in parts]
        sizes[-1] = w - sum(sizes[:-1])
        boxes = []
        x = 0
        for s in sizes:
            boxes.append((x, 0, x + s, h))
            x += s
    else:
        sizes = [max(1, int(h * p / total)) for p in parts]
        sizes[-1] = h - sum(sizes[:-1])
        boxes = []
        y = 0
        for s in sizes:
            boxes.append((0, y, w, y + s))
            y += s

    if order == "reversed":
        boxes = list(reversed(boxes))

    metas: list[SplitMeta] = []
    for i, box in enumerate(boxes):
        p = out_dir / f"piece_{i:02d}.png"
        img.crop(box).save(p)
        metas.append(SplitMeta(path=str(p), index=i, box=tuple(int(x) for x in box)))
    return metas


def build_siva_sample(
    *,
    uid: str,
    image_path: str,
    instruction: str,
    out_dir: str | Path,
    ratio: str = "1:1:1",
    axis: str = "vertical",
    order: str = "normal",
) -> dict:
    """把一个有害图样本切成多块，组装成 run_stage1 可读的样本。"""
    if not Path(image_path).exists():
        raise SivaGenerationError(f"图片不存在：{image_path}")
    if not instruction.strip():
        raise SivaGenerationError("instruction 为空")
    out_dir = Path(out_dir)
    pieces = split_image(
        image_path, out_dir, ratio=ratio, axis=axis, order=order
    )
    images = [
        {
            "path": p.path,
            "kind": "split",
            "mask_path": None,
            "split_index": p.index,
            "split_box": list(p.box),
        }
        for p in pieces
    ]
    return {
        "id": uid,
        "uid": uid,
        "instruction": instruction,
        "prompt": instruction,
        "images": images,
        "meta": {
            "attack": "siva_direct",
            "ratio": ratio,
            "axis": axis,
            "order": order,
            "num_pieces": len(images),
            "source_image": str(image_path),
        },
    }
