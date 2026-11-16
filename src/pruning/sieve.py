"""SIEVE 的分配规则：每图等额配额 + 注意力选择。

SIEVE 没有公开代码。这里复现的是它最关键的实验变量——**每张图分到相同名额**，
而不是像 AVTP 那样按图的重要性浮动。两处刻意偏离（写论文时必须说明）：

  1. **不做解码器前的平均池化。** 我们用「第 0 层剪枝」近似前置压缩：
     进入第一层之前就把每张图砍到目标名额。区别是第一层仍看到全量 token，
     但分配规则本身不变。
  2. **不做图内合并。** 被丢的块直接丢，不并进同图最相似的幸存者。
     SIEVE 自己的消融里，合并只贡献 +2.27 点，分配规则贡献更大；
     阶段 1 先测分配规则。

注意力从哪来：完整跑一遍**未剪枝**的前向，在指定层抓「最后一个 prompt token
对所有视觉 token 的注意力」，按头取平均。这是两遍法，不是层内渐进法。

调用方式：
    scores = capture_last_token_attention(model, inputs, layer_idx)
    keep = equal_quota_keep(scores, segments, grids, budget)
    avtp.configure(method="precomputed", layers=(0,), keep_local=keep)
    out = model.generate(**inputs)
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np

from .layout import ImageSegment


@dataclass
class Captured:
    scores: dict[int, "object"]  # layer_idx -> torch.Tensor [heads, seq_len]


@contextmanager
def _capture_attention(layer_idxs: set[int]):
    """临时替换 modeling 文件里的 eager_attention_forward。"""
    try:
        from transformers.models.qwen3_vl import modeling_qwen3_vl as m
    except ImportError as e:
        raise RuntimeError(f"import transformers 失败：{e}") from e

    original = m.eager_attention_forward
    captured: dict[int, object] = {}

    def wrapper(module, query, key, value, attention_mask, scaling, dropout=0.0, **kwargs):
        attn_output, attn_weights = original(
            module, query, key, value, attention_mask, scaling, dropout, **kwargs
        )
        layer_idx = getattr(module, "layer_idx", None)
        if layer_idx in layer_idxs and attn_weights is not None:
            # [B, H, S, S] → 最后一行 [H, S]
            captured[layer_idx] = attn_weights[0, :, -1, :].detach().float().cpu()
        return attn_output, attn_weights

    m.eager_attention_forward = wrapper
    try:
        yield captured
    finally:
        m.eager_attention_forward = original


def num_layers(model) -> int:
    cfg = getattr(model.config, "text_config", None) or model.config
    return int(getattr(cfg, "num_hidden_layers"))


def default_layer(model) -> int:
    """靠后但留几层：SIEVE 实测早期层的注意力与查询几乎无关。"""
    return max(0, num_layers(model) - 4)


def capture_last_token_attention(model, inputs: dict, layer_idx: int):
    """跑一遍未剪枝前向，返回该层最后一行的注意力 [heads, seq_len]。"""
    import torch

    with torch.no_grad():
        with _capture_attention({layer_idx}) as cap:
            model(**inputs, use_cache=False)
    if layer_idx not in cap:
        raise RuntimeError(
            f"没有抓到第 {layer_idx} 层的注意力。检查 attn_implementation 是否为 eager，"
            "以及该层是否真的执行了。"
        )
    return cap[layer_idx]


def head_mean_scores(scores) -> np.ndarray:
    """按头取平均。返回 numpy，长度等于序列长度。"""
    s = scores
    if hasattr(s, "numpy"):
        s = s.numpy()
    return np.asarray(s, dtype=np.float64).mean(axis=0)


def equal_quota_keep(
    scores,
    segments: list[ImageSegment],
    grids: list[tuple[int, int]],
    budget: float,
) -> tuple[list[list[int]], int]:
    """每张图保留相同数量 k 的块，按注意力从大到小选。

    返回 (每图保留的图内局部编号, k)。
    k 用**所有图里最小的 token 数**乘预算，保证每张图分到同样多的名额——
    这正是 SIEVE 与 AVTP 的分水岭。
    """
    if not (len(segments) == len(grids)):
        raise ValueError("图数与 grid 数不一致")
    for seg, (gh, gw) in zip(segments, grids):
        if seg.n_tokens != gh * gw:
            raise ValueError(
                f"第 {seg.image_index} 张图序列里有 {seg.n_tokens} 个 token，"
                f"网格是 {gh}x{gw}={gh*gw}"
            )
    # 每图等额，但配额按**总预算**定：budget × 总视觉 token / 图数。
    # 若按最小图定，图大小不同时会系统性少用预算，和自适应版不可比。
    total_visual = sum(gh * gw for gh, gw in grids)
    k = max(1, int(round(budget * total_visual / len(segments))))
    arr = head_mean_scores(scores)

    keep: list[list[int]] = []
    for seg in segments:
        s = arr[seg.start + 1 : seg.end]
        if len(s) != seg.n_tokens:
            raise ValueError(
                f"第 {seg.image_index} 张图注意力长度 {len(s)} 与 token 数 {seg.n_tokens} 不一致"
            )
        # 从大到小取 k 个；并列时编号小的优先，保证可复现
        k_i = min(k, len(s))
        order = np.lexsort((np.arange(len(s)), -s))[:k_i]
        keep.append(sorted(int(i) for i in order))
    return keep, k


def random_equal_quota(
    segments: list[ImageSegment],
    grids: list[tuple[int, int]],
    budget: float,
    seed: int,
) -> tuple[list[list[int]], int]:
    """每图等额、图内随机选。用来把「等额分配」与「注意力打分」拆开。

    对照逻辑：
      sieve        = 注意力打分 + 等额分配
      sieve_random = 随机打分   + 等额分配   → 两者之差 = 打分信号的贡献
      avtp         = 变化量打分 + 自适应分配
      avtp_equal   = 变化量打分 + 等额分配   → 两者之差 = 分配规则的贡献
    """
    if not (len(segments) == len(grids)):
        raise ValueError("图数与 grid 数不一致")
    total_visual = sum(gh * gw for gh, gw in grids)
    k = max(1, int(round(budget * total_visual / len(segments))))
    rng = np.random.default_rng(seed)
    keep = [
        sorted(int(x) for x in rng.choice(seg.n_tokens, size=min(k, seg.n_tokens), replace=False))
        for seg in segments
    ]
    return keep, k


def effective_budget(keep: list[list[int]], grids: list[tuple[int, int]]) -> float:
    total = sum(gh * gw for gh, gw in grids)
    return sum(len(x) for x in keep) / total if total else 0.0
