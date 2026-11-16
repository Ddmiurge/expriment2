"""多图 token 布局。

Qwen3-VL 把一张图变成序列里的：

    <vision_start>  v v v ... v  <vision_end>

中间 v 的个数 = grid_t * grid_h * grid_w / spatial_merge_size²，
顺序是行优先（先第一行从左到右，再第二行）。

这个模块只做三件事，全部是纯函数，不碰模型：
  1. 从 input_ids 找出每张图的 start/end 位置；
  2. 把「序列位置」翻译成「第几张图、图内第几行第几列」；
  3. 把图像空间里的载荷掩码降到 token 网格，算保留比例。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ImageSegment:
    """一张图在序列里的位置。视觉 token 是 [start+1, end)。"""

    image_index: int
    start: int  # vision_start 的位置
    end: int  # vision_end 的位置
    n_tokens: int  # end - start - 1

    @property
    def positions(self) -> range:
        return range(self.start + 1, self.end)


def _tolist(x) -> list[int]:
    if hasattr(x, "tolist"):
        x = x.tolist()
    if x and isinstance(x[0], list):  # batch 维
        if len(x) != 1:
            raise ValueError("本仓库所有跑格都按 batch=1；收到 batch>1")
        x = x[0]
    return [int(v) for v in x]


def find_image_segments(
    input_ids,
    vision_start_id: int,
    vision_end_id: int,
) -> list[ImageSegment]:
    """按出现顺序给每张图配对 vision_start / vision_end。"""
    ids = _tolist(input_ids)
    starts = [i for i, v in enumerate(ids) if v == vision_start_id]
    ends = [i for i, v in enumerate(ids) if v == vision_end_id]
    if len(starts) != len(ends):
        raise ValueError(
            f"vision_start {len(starts)} 个、vision_end {len(ends)} 个，对不上"
        )
    segs: list[ImageSegment] = []
    for k, (s, e) in enumerate(zip(starts, ends)):
        if e <= s:
            raise ValueError(f"第 {k} 张图的 vision_end({e}) 在 vision_start({s}) 前面")
        segs.append(ImageSegment(k, s, e, e - s - 1))
    return segs


def validate_against_grid(segments: list[ImageSegment], grid_thw, merge_size: int) -> None:
    """检查每张图的视觉 token 数是否等于 grid 乘积。"""
    grids = grid_thw.tolist() if hasattr(grid_thw, "tolist") else grid_thw
    if len(grids) != len(segments):
        raise ValueError(f"grid 有 {len(grids)} 张图，序列里有 {len(segments)} 张")
    for seg, (t, h, w) in zip(segments, grids):
        expect = int(t) * int(h) * int(w) // (merge_size * merge_size)
        if seg.n_tokens != expect:
            raise ValueError(
                f"第 {seg.image_index} 张图：序列里 {seg.n_tokens} 个视觉 token，"
                f"grid {t}x{h}x{w} / merge² 应为 {expect}"
            )


def grid_shape(grid_thw, image_index: int, merge_size: int) -> tuple[int, int]:
    grids = grid_thw.tolist() if hasattr(grid_thw, "tolist") else grid_thw
    t, h, w = grids[image_index]
    return int(h) // merge_size, int(w) // merge_size


def local_to_rowcol(local_ids, grid_h: int, grid_w: int) -> tuple[np.ndarray, np.ndarray]:
    """图内局部编号 → (行, 列)。越界会报错，不静默截断。"""
    ids = np.asarray(local_ids, dtype=np.int64)
    if ids.size and (ids.min() < 0 or ids.max() >= grid_h * grid_w):
        raise ValueError(
            f"局部编号越界：范围 [{ids.min()}, {ids.max()}]，网格 {grid_h}x{grid_w}"
        )
    return ids // grid_w, ids % grid_w


def mask_to_grid(mask: np.ndarray, grid_h: int, grid_w: int, threshold: float = 0.30) -> np.ndarray:
    """把 H×W 的 0/1 掩码降到 grid_h×grid_w。

    每个网格单元取平均值，> threshold 算「这个 token 承载载荷」。
    用平均值而不是最大值，是为了避免边缘抗锯齿把太多单元算进来。

    原图尺寸通常不能被 token 网格整除（例如 1000×1000 对 20×20 可以，
    但 1000×750 对 18×18 不行）。不能整除时先把掩码重采样到
    (grid_h*8, grid_w*8)，再做平均池化。Qwen 的 smart resize 保持长宽比，
    所以均匀重采样与模型看到的图是对齐的；若将来发现 padding，这里要改成带 padding 的映射。
    """
    m = np.asarray(mask)
    if m.ndim != 2:
        raise ValueError(f"mask 应为二维，实际 shape={m.shape}")
    h, w = m.shape
    if h % grid_h or w % grid_w:
        from PIL import Image

        m = (
            np.asarray(
                Image.fromarray((m > 0).astype(np.uint8) * 255).resize(
                    (grid_w * 8, grid_h * 8), Image.BILINEAR
                )
            )
            > 127
        )
        h, w = m.shape
    sh, sw = h // grid_h, w // grid_w
    pooled = m.reshape(grid_h, sh, grid_w, sw).mean(axis=(1, 3))
    return pooled > threshold


def survival_rate(kept_local, grid_h: int, grid_w: int, payload_grid: np.ndarray) -> float | None:
    """载荷保留比例 = 被保留的载荷网格单元 / 全部载荷网格单元。

    返回 None 表示这张图没有载荷（掩码全 0），不参与平均。
    """
    total = int(payload_grid.sum())
    if total == 0:
        return None
    rows, cols = local_to_rowcol(kept_local, grid_h, grid_w)
    kept = int(payload_grid[rows, cols].sum())
    return kept / total


def kept_fraction(kept_local, grid_h: int, grid_w: int) -> float:
    n = grid_h * grid_w
    return len(kept_local) / n if n else 0.0
