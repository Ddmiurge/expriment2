"""载荷存活率。

定义（与计划 §5.1 一致）：
    载荷 token 存活率 = 剪枝后仍被保留的、承载有害关键词的图像块 / 全部承载块

单图线用的是「读出率」口径；这里换成「块是否被保留」，因为多图线的剪枝器
直接删块，不经过判据读出这一步。

载荷块从哪来：
    MIDAS 的每张图有一个 target_answer（该图承载的关键词片段）。生成图时用
    **同 seed、同参数、只换答案**再画一张，两张做差 → 只有答案字形所在的像素
    会变。这个差图就是载荷掩码，不依赖 OCR，也不依赖游戏内部实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..pruning.layout import grid_shape, mask_to_grid, survival_rate


@dataclass
class SampleSurvival:
    per_image: list[float | None] = field(default_factory=list)
    per_image_kept_fraction: list[float] = field(default_factory=list)
    per_image_kept_count: list[int] = field(default_factory=list)
    per_image_total: list[int] = field(default_factory=list)
    payload_counts: list[int] = field(default_factory=list)

    @property
    def overall(self) -> float | None:
        """按载荷块数加权的总存活率；没有任何载荷时返回 None。"""
        vals = [
            (r, n)
            for r, n in zip(self.per_image, self.payload_counts)
            if r is not None and n > 0
        ]
        if not vals:
            return None
        num = sum(r * n for r, n in vals)
        den = sum(n for _, n in vals)
        return num / den if den else None


def compute_survival(
    kept_local_by_image: list[list[int]],
    grids: list[tuple[int, int]],
    payload_masks: list[np.ndarray | None],
    threshold: float = 0.30,
) -> SampleSurvival:
    """kept_local_by_image：每张图剪枝后保留的**图内局部编号**（0..h*w-1）。"""
    if not (len(kept_local_by_image) == len(grids) == len(payload_masks)):
        raise ValueError("kept / grids / masks 的图数不一致")

    out = SampleSurvival()
    payload_n: list[int] = []
    for kept, (gh, gw), mask in zip(kept_local_by_image, grids, payload_masks):
        total = gh * gw
        out.per_image_kept_count.append(len(kept))
        out.per_image_total.append(total)
        out.per_image_kept_fraction.append(len(kept) / total if total else 0.0)
        if mask is None:
            out.per_image.append(None)
            payload_n.append(0)
            continue
        pg = mask_to_grid(mask, gh, gw, threshold=threshold)
        payload_n.append(int(pg.sum()))
        out.per_image.append(survival_rate(kept, gh, gw, pg))
    out.payload_counts = payload_n
    return out


def kept_fraction_by_image_index(samples: list[SampleSurvival]) -> dict[int, float]:
    """跨样本、按图序号求平均保留比例——这就是「图间分配剖面」。"""
    acc: dict[int, list[float]] = {}
    for s in samples:
        for idx, f in enumerate(s.per_image_kept_fraction):
            acc.setdefault(idx, []).append(f)
    return {k: sum(v) / len(v) for k, v in sorted(acc.items())}


def grids_from_thw(grid_thw, merge_size: int) -> list[tuple[int, int]]:
    grids = grid_thw.tolist() if hasattr(grid_thw, "tolist") else grid_thw
    return [grid_shape(grids, i, merge_size) for i in range(len(grids))]
