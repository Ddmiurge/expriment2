"""RI-Prune（ours reproduction）—— attention-free 的多图视觉 token 剪枝。

原论文：RI-Prune: Relation and Information Aware Visual Token Pruning for
Multi-Image Vision-Language Models（arXiv:2611.06047）。

原论文配置：
  - 在 projector 之后、decoder 之前做一次性选择；
  - P = 16 个 per-image prototypes；
  - 三个信号 query relevance / cross-image correspondence /
    intra-image representativeness，各自 z-score 后等权相加（λ=1）；
  - 每图等额 Top-K，K 尽量均分；
  - 不依赖 attention。

本实现是 Qwen3-VL 的 monkey patch：替换 `Qwen3VLModel.forward`，在 image embeds
scatter 后、进入 language_model 前剪 token；不改 site-packages。

已知近似（论文未写或实现细节不明确）：
  - 文本 query 取“最后一张图之后的文本段”（近似 user query，仍含少量模板尾 token）；
  - 图片 token 段用 `image_grid_thw` 还原；
  - deepstack 同步裁剪；
  - 论文未给官方代码，不能叫作者原版。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import torch
import torch.nn.functional as F

_CONFIG = {"enabled": False, "budget": 0.5, "prototypes": 16}
_STATE: dict = {}
_ORIGINAL_FORWARD = None


@dataclass
class RipruneResult:
    inputs_embeds: torch.Tensor
    position_ids: torch.Tensor
    attention_mask: torch.Tensor | None
    visual_pos_masks: torch.Tensor
    deepstack_visual_embeds: list[torch.Tensor] | None
    kept_local: list[list[int]] = field(default_factory=list)


def _zscore(x: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    return (x - x.mean()) / (x.std(unbiased=False) + eps)


def _prototypes(tokens: torch.Tensor, p: int) -> torch.Tensor:
    """把一张图的 token 按连续块平均成 P 个 prototype。"""
    n = tokens.shape[0]
    if n == 0:
        return tokens.new_zeros((0, tokens.shape[-1]))
    p = min(p, n)
    # 连续切块，尽量等长
    idx = torch.linspace(0, n, p + 1, device=tokens.device)
    bounds = [int(x) for x in idx.tolist()]
    protos = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b > a:
            protos.append(tokens[a:b].mean(dim=0))
    return torch.stack(protos, dim=0)


def score_tokens(
    image_embeds: torch.Tensor,
    image_lengths: list[int],
    text_embeds: torch.Tensor,
    *,
    prototypes: int = 16,
) -> torch.Tensor:
    """返回每个视觉 token 的最终分数（长度 = sum(image_lengths)）。

    image_embeds: [J, D]；image_lengths: 每图 token 数；text_embeds: [L, D]。
    """
    v = F.normalize(image_embeds.float(), dim=-1)
    q = F.normalize(text_embeds.float(), dim=-1) if text_embeds.numel() else None
    if q is not None and q.shape[0]:
        r = (v @ q.T).max(dim=1).values
    else:
        r = torch.zeros(v.shape[0], device=v.device)

    # 每图 prototype 与跨图 correspondence
    chunks = []
    start = 0
    for n in image_lengths:
        chunks.append(v[start:start + n])
        start += n
    protos = [_prototypes(c, prototypes) for c in chunks]

    c_parts = []
    u_parts = []
    for a, chunk in enumerate(chunks):
        # cross-image：与其他图的 prototype 的最大相似度
        other = [protos[b] for b in range(len(protos)) if b != a and protos[b].numel()]
        if other:
            op = torch.cat(other, dim=0)
            c = (chunk @ op.T).max(dim=1).values
        else:
            c = torch.zeros(chunk.shape[0], device=chunk.device)

        # intra-image：最近 prototype 的相似度 + 频率惩罚
        own = protos[a]
        if own.numel() == 0:
            u = torch.zeros(chunk.shape[0], device=chunk.device)
        else:
            sim = chunk @ own.T
            best_sim, assign = sim.max(dim=1)
            counts = torch.bincount(assign, minlength=own.shape[0]).float()
            s = best_sim.clamp(min=0.0)
            u = s * torch.log(torch.tensor(float(chunk.shape[0]), device=chunk.device) / counts[assign].clamp(min=1.0))
        c_parts.append(c)
        u_parts.append(u)

    c = torch.cat(c_parts, dim=0) if c_parts else torch.zeros_like(r)
    u = torch.cat(u_parts, dim=0) if u_parts else torch.zeros_like(r)
    return _zscore(r) + _zscore(c) + _zscore(u)


def quotas(total: int, n_images: int, lengths: list[int]) -> list[int]:
    """把 total 个 token 尽量均分到每张图；不超出每图容量。"""
    if n_images <= 0:
        return []
    base, rem = divmod(int(total), n_images)
    q = [base + (1 if i < rem else 0) for i in range(n_images)]
    q = [min(x, n) for x, n in zip(q, lengths)]
    # 容量不足时，把剩下的 token 再分给还有余量的图
    left = int(total) - sum(q)
    while left > 0:
        progressed = False
        for i in range(n_images):
            if left <= 0:
                break
            if q[i] < lengths[i]:
                q[i] += 1
                left -= 1
                progressed = True
        if not progressed:
            break
    return q


def query_positions_after_last_image(
    input_ids: torch.Tensor | None,
    visual_pos_masks: torch.Tensor,
) -> torch.Tensor:
    """取最后一张图之后的文本 token，作为 user query 的近似。

    Qwen 的 chat template 是：system/user + 图片 + prompt 文本 + generation prompt。
    我们只取最后一张图之后的文本段，排除图像 token；这样不会把 system/template
    前缀也算进 query relevance。剩余的特殊 token 很少，第一版保留。
    """
    if input_ids is None or input_ids.numel() == 0:
        return torch.empty(0, dtype=torch.long, device=visual_pos_masks.device)
    mask = visual_pos_masks[0].bool()
    pos = mask.nonzero(as_tuple=False).flatten()
    if pos.numel() == 0:
        return torch.empty(0, dtype=torch.long, device=visual_pos_masks.device)
    start = int(pos.max().item()) + 1
    if start >= input_ids.shape[1]:
        return torch.empty(0, dtype=torch.long, device=visual_pos_masks.device)
    idx = torch.arange(start, input_ids.shape[1], device=visual_pos_masks.device)
    # 防御：后面不应再有图像 token；若有，排除
    idx = idx[~mask[start:]]
    return idx


def prune_predecoder(
    *,
    inputs_embeds: torch.Tensor,
    image_embeds: torch.Tensor,
    image_token_positions: torch.Tensor,
    image_lengths: list[int],
    position_ids: torch.Tensor,
    attention_mask: torch.Tensor | None,
    visual_pos_masks: torch.Tensor,
    deepstack_visual_embeds: list[torch.Tensor] | None,
    budget: float,
    prototypes: int = 16,
    query_positions: torch.Tensor | None = None,
) -> RipruneResult:
    """在 decoder 前剪掉视觉 token；返回同步裁剪后的张量与每图 kept local。"""
    device = inputs_embeds.device
    j = image_embeds.shape[0]
    total = max(1, int(round(j * budget)))

    # 文本 query：优先用显式 query_positions（最后一张图之后的文本段）；
    # 没有时退回所有非图像 token（只用于兜底）。
    if query_positions is not None and query_positions.numel():
        text_embeds = inputs_embeds[0][query_positions]
    else:
        text_mask = ~visual_pos_masks[0].bool()
        text_embeds = inputs_embeds[0][text_mask]
    scores = score_tokens(image_embeds, image_lengths, text_embeds, prototypes=prototypes)

    qs = quotas(total, len(image_lengths), image_lengths)
    kept_local: list[list[int]] = []
    keep_global: set[int] = set()
    pos_list = image_token_positions.tolist()
    offset = 0
    for n, k in zip(image_lengths, qs):
        if n == 0:
            kept_local.append([])
            continue
        s = scores[offset:offset + n]
        idx = torch.topk(s, k=k, largest=True).indices.tolist()
        idx = sorted(idx)
        kept_local.append(idx)
        for i in idx:
            keep_global.add(pos_list[offset + i])
        offset += n

    non_image = [p for p in range(inputs_embeds.shape[1]) if p not in set(pos_list)]
    keep = sorted(non_image + list(keep_global))
    keep_t = torch.tensor(keep, dtype=torch.long, device=device)

    new_inputs = inputs_embeds.index_select(1, keep_t)
    new_pos = position_ids.index_select(2, keep_t)
    new_attn = attention_mask.index_select(1, keep_t) if attention_mask is not None else None
    new_vpm = visual_pos_masks.index_select(1, keep_t)

    new_deep = None
    if deepstack_visual_embeds is not None:
        # deepstack 按视觉 token 顺序排列；只保留 keep_global 里的视觉位置
        visual_keep = [i for i, p in enumerate(pos_list) if p in keep_global]
        vt = torch.tensor(visual_keep, dtype=torch.long, device=device)
        new_deep = [d.index_select(0, vt) for d in deepstack_visual_embeds]

    return RipruneResult(
        inputs_embeds=new_inputs,
        position_ids=new_pos,
        attention_mask=new_attn,
        visual_pos_masks=new_vpm,
        deepstack_visual_embeds=new_deep,
        kept_local=kept_local,
    )


def _cache_has_tokens(pkv) -> bool:
    """transformers 4.57+ 在 prefill 会传空 DynamicCache（不是 None）。"""
    if pkv is None:
        return False
    getter = getattr(pkv, "get_seq_length", None)
    if callable(getter):
        try:
            return int(getter()) > 0
        except Exception:  # noqa: BLE001
            return True
    if isinstance(pkv, (tuple, list)):
        return bool(pkv) and pkv[0] is not None
    return True


def _riprune_forward(self, *args, **kwargs):
    """替换 Qwen3VLModel.forward；只在 prefill 且 enabled 时剪枝。"""
    if (
        not _CONFIG["enabled"]
        or kwargs.get("pixel_values") is None
        or _cache_has_tokens(kwargs.get("past_key_values"))
    ):
        return _ORIGINAL_FORWARD(self, *args, **kwargs)
    _STATE.pop("error", None)

    # 延迟 import，避免没装 transformers 时导入失败
    from transformers.models.qwen3_vl.modeling_qwen3_vl import Qwen3VLModelOutputWithPast

    input_ids = kwargs.get("input_ids")
    attention_mask = kwargs.get("attention_mask")
    position_ids = kwargs.get("position_ids")
    inputs_embeds = kwargs.get("inputs_embeds")
    pixel_values = kwargs.get("pixel_values")
    image_grid_thw = kwargs.get("image_grid_thw")
    video_grid_thw = kwargs.get("video_grid_thw")
    mm_token_type_ids = kwargs.get("mm_token_type_ids")

    # 视频不走这条路径
    if kwargs.get("pixel_values_videos") is not None or video_grid_thw is not None:
        return _ORIGINAL_FORWARD(self, *args, **kwargs)

    if inputs_embeds is None:
        inputs_embeds = self.get_input_embeddings()(input_ids)

    # transformers 5.x: return_dict=True；4.57.1: 返回 tuple，不接受 return_dict。
    try:
        image_outputs = self.get_image_features(pixel_values, image_grid_thw, return_dict=True)
        image_list = image_outputs.pooler_output
        deepstack = image_outputs.deepstack_features
    except TypeError:
        image_list, deepstack = self.get_image_features(pixel_values, image_grid_thw)
    image_embeds = torch.cat(list(image_list), dim=0).to(inputs_embeds.device, inputs_embeds.dtype)
    image_mask, _ = self.get_placeholder_mask(input_ids, inputs_embeds=inputs_embeds, image_features=image_embeds)
    inputs_embeds = inputs_embeds.masked_scatter(image_mask, image_embeds)
    visual_pos_masks = image_mask[..., 0]

    if position_ids is None:
        if hasattr(self, "compute_3d_position_ids"):
            position_ids = self.compute_3d_position_ids(
                input_ids=input_ids,
                image_grid_thw=image_grid_thw,
                video_grid_thw=None,
                inputs_embeds=inputs_embeds,
                attention_mask=attention_mask,
                past_key_values=None,
                mm_token_type_ids=mm_token_type_ids,
            )
        else:
            # transformers 4.57.1 的旧 API
            position_ids, rope_deltas = self.get_rope_index(
                input_ids, image_grid_thw, None, attention_mask=attention_mask
            )
            self.rope_deltas = rope_deltas

    # 每图 token 数：t*h*w / merge^2
    merge = int(self.config.vision_config.spatial_merge_size)
    lengths = []
    for t, h, w in image_grid_thw.tolist():
        lengths.append(int(t) * int(h) * int(w) // (merge * merge))
    positions = visual_pos_masks[0].nonzero(as_tuple=False).flatten()
    if len(positions) != sum(lengths):
        # 布局不符合预期：退回原 forward，避免静默剪错
        _STATE["error"] = f"visual token 数 {len(positions)} != {sum(lengths)}"
        return _ORIGINAL_FORWARD(self, *args, **kwargs)

    out = prune_predecoder(
        inputs_embeds=inputs_embeds,
        image_embeds=image_embeds,
        image_token_positions=positions,
        image_lengths=lengths,
        position_ids=position_ids,
        attention_mask=attention_mask,
        visual_pos_masks=visual_pos_masks,
        deepstack_visual_embeds=deepstack,
        budget=float(_CONFIG["budget"]),
        prototypes=int(_CONFIG["prototypes"]),
        query_positions=query_positions_after_last_image(input_ids, visual_pos_masks),
    )
    _STATE["last_kept_local"] = out.kept_local
    _STATE["n_before"] = int(image_embeds.shape[0])
    _STATE["n_after"] = int(sum(len(x) for x in out.kept_local))

    outputs = self.language_model(
        input_ids=None,
        position_ids=out.position_ids,
        attention_mask=out.attention_mask,
        past_key_values=None,
        inputs_embeds=out.inputs_embeds,
        visual_pos_masks=out.visual_pos_masks,
        deepstack_visual_embeds=out.deepstack_visual_embeds,
        **{k: v for k, v in kwargs.items() if k not in {
            "input_ids", "attention_mask", "position_ids", "inputs_embeds",
            "pixel_values", "pixel_values_videos", "image_grid_thw", "video_grid_thw",
            "past_key_values", "mm_token_type_ids",
            # 剪枝后序列变短，cache_position 长度会与新 embeddings 对不齐。
            "cache_position",
        }},
    )
    return Qwen3VLModelOutputWithPast(**outputs, rope_deltas=self.rope_deltas)


def enable(*, budget: float = 0.5, prototypes: int = 16) -> None:
    global _ORIGINAL_FORWARD
    from transformers.models.qwen3_vl.modeling_qwen3_vl import Qwen3VLModel

    if _ORIGINAL_FORWARD is None:
        _ORIGINAL_FORWARD = Qwen3VLModel.forward
    _CONFIG.update(enabled=True, budget=float(budget), prototypes=int(prototypes))
    _STATE.clear()
    Qwen3VLModel.forward = _riprune_forward


def disable() -> None:
    global _ORIGINAL_FORWARD
    if _ORIGINAL_FORWARD is not None:
        from transformers.models.qwen3_vl.modeling_qwen3_vl import Qwen3VLModel
        Qwen3VLModel.forward = _ORIGINAL_FORWARD
    _CONFIG["enabled"] = False


def last_kept_local() -> list[list[int]]:
    return _STATE.get("last_kept_local", [])


def last_stats() -> dict:
    return dict(_STATE)
