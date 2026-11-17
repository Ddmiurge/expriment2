"""把剪枝逻辑注入 venv 里的 transformers/modeling_qwen3_vl.py。

为什么必须改文件、不能在外层包一层：
    AVTP 的剪枝发生在 `Qwen3VLTextModel.forward` 的层循环里，中间还要同步
    position_ids / attention_mask / deepstack 嵌入。这些变量都是 forward 的局部量，
    外层拿不到。官方发布方式也是 `cat patch > site-packages/...`。

两种模式：
  - `original`     ：逐字注入作者代码，用来做等价性校验（sm0_3）
  - `instrumented` ：同一个算法，但预算/层数/alpha 可配置，并记录每层每图保留了哪些块

注入内容集中在本文件的常量里，`scripts/apply_avtp_patch.py` 只负责找锚点、替换、校验。
"""

from __future__ import annotations

# 作者代码里的层内块（从 third_party/AVTP/... 抽出来，原样保留）
ORIGINAL_BLOCK = '''
            # modify begin
            if hidden_states.size(1) > 1 and layer_idx in reduce_layers:
                device = hidden_states.device
                current_hidden_states = hidden_states
                seq_len = hidden_states.size(1)
                keep_mask = torch.zeros(seq_len, dtype=torch.bool, device=device)
                base_ratio_list = [0.8, 0.8, 0.78] # total:0.5
                base_ratio = base_ratio_list[reduce_layers.index(layer_idx)]

                img_token_mask = torch.zeros(seq_len, dtype=torch.bool, device=device)
                img_token_len = 0
                for s, e in zip(img_start_pos, img_end_pos):
                    img_token_mask[s+1:e] = True
                    img_token_len += e-s-1
                keep_mask[~img_token_mask] = True
                img_mask = torch.zeros(img_token_len, dtype=torch.bool, device=device)

                img_cos_sim_list = []
                for img_start, img_end in zip(img_start_pos, img_end_pos):
                    candidate_indices = torch.arange(img_start, img_end, device=device)
                    current_candidates = current_hidden_states[:, candidate_indices, :]
                    prev_candidates = prev_hidden_states[:, candidate_indices, :]
                    cos_sim_candidate = F.cosine_similarity(current_candidates, prev_candidates, dim=-1)[0]
                    img_cos_sim_list.append(cos_sim_candidate)

                rank_list = [cos_sim[0] for cos_sim in img_cos_sim_list]
                avg = sum(rank_list) / len(rank_list)
                ratio_i = [avg - x for x in rank_list]

                new_img_start_pos, new_img_end_pos = [], []
                offset = 0
                img_token_count = 0
                for index, (img_start, img_end) in enumerate(zip(img_start_pos, img_end_pos)):
                    alpha = 1.0
                    keep_ratio = base_ratio + alpha * ratio_i[index]
                    keep_ratio = keep_ratio if keep_ratio < 1.0 else 1.0
                    keep_ratio = keep_ratio if keep_ratio > 0.0 else 0.0
                    k = max(1, int((img_end-img_start-1) * keep_ratio))
                    cos_sim_candidate = img_cos_sim_list[index][1:]
                    topk_indices = torch.topk(cos_sim_candidate, k=k, largest=False).indices
                    keep_mask[img_start+1:img_end][topk_indices] = True
                    img_mask[img_token_count:][topk_indices] = True
                    img_token_count += img_end-img_start-1

                    original_tokens = img_end - img_start - 1
                    removed_tokens = original_tokens - k
                    new_start = img_start - offset
                    new_end = new_start + k + 1
                    new_img_start_pos.append(new_start)
                    new_img_end_pos.append(new_end)
                    offset += removed_tokens

                img_start_pos, img_end_pos = new_img_start_pos, new_img_end_pos

                all_indices = torch.arange(seq_len, device=device)
                keep_indices = all_indices[keep_mask]

                hidden_states = hidden_states.index_select(1, keep_indices)
                position_ids = position_ids.index_select(2, keep_indices)
                text_position_ids = text_position_ids[:, keep_indices]
                position_embeddings = tuple(pe.index_select(1, keep_indices) for pe in position_embeddings)
                if attention_mask is not None:
                    attention_mask = attention_mask.index_select(2, keep_indices)
                    attention_mask = attention_mask.index_select(3, keep_indices)
                deepstack_visual_embeds = [vec[img_mask] for vec in deepstack_visual_embeds]
                visual_pos_masks = visual_pos_masks[:, keep_indices]

                prev_hidden_states = hidden_states
            # modify end
'''


PREAMBLE = '''
# ─────────────────────────────────────────────────────────────────────────────
# 多图剪枝实验 · 注入层（由 multi-image-code/scripts/apply_avtp_patch.py 写入）
#
# 这个模块级状态只服务单样本前向（batch=1）。跑格在每次前向前调用
# _prune_reset()，前向结束后读 _PRUNE_RECORD。
# ─────────────────────────────────────────────────────────────────────────────

_PRUNE_CONFIG = {
    "enabled": False,
    "method": "avtp",          # avtp | equal | precomputed
    "reduce_layers": [1, 19, 22],
    "base_ratios": [0.8, 0.8, 0.78],
    "alpha": 1.0,
    "keep_local": None,        # method=precomputed 时：每图保留的图内局部编号
    "record_scores": False,
}
_PRUNE_STATE = {}
_PRUNE_RECORD = []


def _prune_reset():
    _PRUNE_STATE.clear()
    _PRUNE_RECORD.clear()


def _prune_begin(hidden_states, kwargs):
    """在层循环前登记：每张图的位置、token 原始身份、上一剪枝层的隐藏状态。"""
    starts = list(kwargs.get("img_start_pos") or [])
    ends = list(kwargs.get("img_end_pos") or [])
    if not starts:
        # 生成阶段的 decode 步 input_ids 只有一个新 token，没有视觉段。
        # 这一步不需要剪枝，也不能清掉 prefill 留下的状态。
        _PRUNE_STATE["skip"] = True
        return
    _PRUNE_STATE.pop("skip", None)
    seq_len = hidden_states.size(1)
    origin = torch.full((seq_len,), -1, dtype=torch.long, device=hidden_states.device)
    for idx, (s, e) in enumerate(zip(starts, ends)):
        n = e - s - 1
        origin[s + 1:e] = idx * 1_000_000 + torch.arange(n, device=hidden_states.device)
    _PRUNE_STATE.update(
        img_start_pos=starts,
        img_end_pos=ends,
        origin=origin,
        prev_hidden=hidden_states,
    )


def _prune_step(layer_idx, hidden_states, position_ids, text_position_ids,
                position_embeddings, attention_mask, deepstack_visual_embeds,
                visual_pos_masks):
    """在进入第 layer_idx 层之前，按配置剪一次。返回同步后的全部张量。"""
    if not _PRUNE_CONFIG.get("enabled", False):
        return (hidden_states, position_ids, text_position_ids, position_embeddings,
                attention_mask, deepstack_visual_embeds, visual_pos_masks)
    if _PRUNE_STATE.get("skip", False):
        return (hidden_states, position_ids, text_position_ids, position_embeddings,
                attention_mask, deepstack_visual_embeds, visual_pos_masks)
    layers = _PRUNE_CONFIG["reduce_layers"]
    if layer_idx not in layers or hidden_states.size(1) <= 1:
        return (hidden_states, position_ids, text_position_ids, position_embeddings,
                attention_mask, deepstack_visual_embeds, visual_pos_masks)

    device = hidden_states.device
    seq_len = hidden_states.size(1)
    starts = _PRUNE_STATE["img_start_pos"]
    ends = _PRUNE_STATE["img_end_pos"]
    origin = _PRUNE_STATE["origin"]
    prev_hidden = _PRUNE_STATE["prev_hidden"]
    n_layers = len(layers)
    layer_pos = layers.index(layer_idx)

    keep_mask = torch.ones(seq_len, dtype=torch.bool, device=device)
    for s, e in zip(starts, ends):
        keep_mask[s + 1:e] = False

    method = _PRUNE_CONFIG["method"]
    per_image_kept = []
    per_image_counts = []
    per_image_scores = []

    if method in ("avtp", "equal"):
        full_cos = []
        for s, e in zip(starts, ends):
            candidate = torch.arange(s, e, device=device)
            cur = hidden_states[:, candidate, :]
            prev = prev_hidden[:, candidate, :]
            # 第 0 位是 vision_start；作者代码用它作为图级重要性，
            # 第 1 位起才是真正的视觉 token。
            full_cos.append(F.cosine_similarity(cur, prev, dim=-1)[0])
        token_scores = [c[1:] for c in full_cos]
        if method == "avtp":
            # 与作者代码一致：图级重要性取 vision_start 那一格的相似度
            fig_imp = [c[0].item() for c in full_cos]
            avg = sum(fig_imp) / len(fig_imp)
            alpha = float(_PRUNE_CONFIG["alpha"])
            base = float(_PRUNE_CONFIG["base_ratios"][layer_pos])
            ratios = [base + alpha * (avg - x) for x in fig_imp]
            k_same = None
        else:
            # 等额配额：每张图分到**同样多的 token**，不是同样的比例。
            # 图大小不同时这两种不一样；SIEVE 用的是同样多的 token。
            # 为了与自适应版预算可比，按「总视觉 token × 本层比例 / 图数」定配额，
            # 而不是按最小图定（后者会系统性地少用预算）。
            base = min(1.0, max(0.0, float(_PRUNE_CONFIG["base_ratios"][layer_pos])))
            total_vis = sum(e - s - 1 for s, e in zip(starts, ends))
            k_same = max(1, int(round(base * total_vis / len(starts))))

        for idx, (s, e) in enumerate(zip(starts, ends)):
            n = e - s - 1
            k = k_same if method == "equal" else max(
                1, int(n * min(1.0, max(0.0, ratios[idx])))
            )
            k = min(k, n)
            order = torch.topk(token_scores[idx], k=k, largest=False).indices
            keep_mask[s + 1:e][order] = True
            per_image_counts.append(k)
            if _PRUNE_CONFIG.get("record_scores", False):
                per_image_scores.append(token_scores[idx].detach().float().cpu().tolist())
            else:
                per_image_scores.append(None)
    elif method == "precomputed":
        keep_local = _PRUNE_CONFIG["keep_local"]
        if keep_local is None or len(keep_local) != len(starts):
            raise RuntimeError("method=precomputed 需要 keep_local，且图数要一致")
        for idx, (s, e) in enumerate(zip(starts, ends)):
            idxs = torch.as_tensor(keep_local[idx], dtype=torch.long, device=device)
            keep_mask[s + 1:e][idxs] = True
            per_image_counts.append(len(keep_local[idx]))
            per_image_scores.append(None)
    else:
        raise ValueError(f"未知剪枝方法：{method}")

    # 记录「剪枝前这一层每张图保住了哪些原始块」
    for idx, (s, e) in enumerate(zip(starts, ends)):
        loc = origin[s + 1:e]
        loc = loc[keep_mask[s + 1:e]]
        loc = loc - idx * 1_000_000
        per_image_kept.append(loc.detach().cpu().tolist())

    all_indices = torch.arange(seq_len, device=device)
    keep_indices = all_indices[keep_mask]

    _PRUNE_RECORD.append({
        "layer": layer_idx,
        "n_before": int(seq_len),
        "n_after": int(keep_indices.numel()),
        "per_image_kept_local": per_image_kept,
        "per_image_keep_count": per_image_counts,
        "per_image_scores": per_image_scores,
        "keep_indices": keep_indices.detach().cpu().tolist() if _PRUNE_CONFIG.get("record_indices", False) else None,
    })

    hidden_states = hidden_states.index_select(1, keep_indices)
    position_ids = position_ids.index_select(2, keep_indices)
    text_position_ids = text_position_ids[:, keep_indices]
    position_embeddings = tuple(pe.index_select(1, keep_indices) for pe in position_embeddings)
    if attention_mask is not None:
        attention_mask = attention_mask.index_select(2, keep_indices)
        attention_mask = attention_mask.index_select(3, keep_indices)
    if deepstack_visual_embeds is not None:
        # deepstack 的每个 vec 按「视觉 token 出现顺序」排列（不含文本），
        # 所以掩码也要按同样顺序拼：每张图 [s+1, e) 的保留位。
        vis_keep = torch.cat([keep_mask[s + 1:e] for s, e in zip(starts, ends)])
        deepstack_visual_embeds = [vec[vis_keep] for vec in deepstack_visual_embeds]
    visual_pos_masks = visual_pos_masks[:, keep_indices]

    # 更新位置表与原始身份表，供下一剪枝层用
    new_starts, new_ends = [], []
    offset = 0
    for idx, (s, e) in enumerate(zip(starts, ends)):
        kept = per_image_counts[idx]
        new_starts.append(s - offset)
        new_ends.append(s - offset + kept + 1)
        offset += (e - s - 1) - kept
    _PRUNE_STATE["img_start_pos"] = new_starts
    _PRUNE_STATE["img_end_pos"] = new_ends
    _PRUNE_STATE["origin"] = origin.index_select(0, keep_indices)
    _PRUNE_STATE["prev_hidden"] = hidden_states

    return (hidden_states, position_ids, text_position_ids, position_embeddings,
            attention_mask, deepstack_visual_embeds, visual_pos_masks)
'''


BEGIN_CALL = '''        if _PRUNE_CONFIG.get("enabled", False):
            _prune_begin(hidden_states, kwargs)

'''

STEP_CALL = '''            if _PRUNE_CONFIG.get("enabled", False):
                (hidden_states, position_ids, text_position_ids, position_embeddings,
                 attention_mask, deepstack_visual_embeds, visual_pos_masks) = _prune_step(
                    layer_idx, hidden_states, position_ids, text_position_ids,
                    position_embeddings, attention_mask, deepstack_visual_embeds,
                    visual_pos_masks)

'''


CALLSITE_ORIGINAL = '''        img_start_pos = (input_ids == self.config.vision_start_token_id).squeeze(0).nonzero(as_tuple=False).squeeze(1).tolist()
        img_end_pos = (input_ids == self.config.vision_end_token_id).squeeze(0).nonzero(as_tuple=False).squeeze(1).tolist()

'''

CALLSITE_GUARDED = '''        if input_ids is not None:
            img_start_pos = (input_ids == self.config.vision_start_token_id).squeeze(0).nonzero(as_tuple=False).squeeze(1).tolist()
            img_end_pos = (input_ids == self.config.vision_end_token_id).squeeze(0).nonzero(as_tuple=False).squeeze(1).tolist()
        else:
            img_start_pos, img_end_pos = [], []

'''

CALLSITE_KWARGS = '''            img_start_pos=img_start_pos,
            img_end_pos=img_end_pos,
'''

# 锚点
ANCHOR_EMBED = "        position_embeddings = self.rotary_emb(hidden_states, position_ids)\n"
ANCHOR_LOOP = "        # decoder layers\n        for layer_idx, decoder_layer in enumerate(self.layers):\n"
ANCHOR_LANGUAGE_CALL = "        outputs = self.language_model(\n"
ANCHOR_LANG_KWARGS = "            deepstack_visual_embeds=deepstack_visual_embeds,\n"
ANCHOR_IMPORT_END = "from .configuration_qwen3_vl import Qwen3VLConfig, Qwen3VLTextConfig, Qwen3VLVisionConfig\n"


class PatchError(RuntimeError):
    pass


# 两种补丁各自的标记。original 模式没有模块级配置，只能靠作者代码里的硬编码行认出来。
INSTRUMENTED_MARKER = "_PRUNE_CONFIG"
ORIGINAL_MARKERS = ("reduce_layers = [1 ,19, 22]", "# modify begin")


def patch_state(text: str) -> str:
    """返回 none / instrumented / original / both（叠加损坏）。"""
    inst = INSTRUMENTED_MARKER in text
    orig = any(m in text for m in ORIGINAL_MARKERS)
    if inst and orig:
        return "both"
    if inst:
        return "instrumented"
    if orig:
        return "original"
    return "none"


def is_patched(text: str) -> bool:
    return patch_state(text) != "none"


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise PatchError(
            f"锚点「{label}」出现 {n} 次（应为 1）。transformers 版本可能不是 4.57.1，"
            f"或文件已经被别的补丁改过。"
        )
    return text.replace(old, new, 1)


def patch_instrumented(text: str) -> str:
    state = patch_state(text)
    if state != "none":
        raise PatchError(
            f"文件已经是 {state} 状态；直接叠加会产生重复的 img_start_pos。"
            "先 --revert，再选一个模式重打。"
        )
    text = _replace_once(text, ANCHOR_IMPORT_END, ANCHOR_IMPORT_END + PREAMBLE, "import 段末尾")
    text = _replace_once(text, ANCHOR_EMBED, ANCHOR_EMBED + BEGIN_CALL, "rotary_emb 之后")
    text = _replace_once(
        text,
        ANCHOR_LOOP,
        ANCHOR_LOOP + STEP_CALL,
        "decoder layers 循环开头",
    )
    text = _replace_once(
        text,
        ANCHOR_LANGUAGE_CALL,
        CALLSITE_GUARDED + ANCHOR_LANGUAGE_CALL,
        "language_model 调用前",
    )
    text = _replace_once(
        text,
        ANCHOR_LANG_KWARGS,
        ANCHOR_LANG_KWARGS + CALLSITE_KWARGS,
        "language_model kwargs",
    )
    return text


def patch_original(text: str) -> str:
    """作者原版：硬编码层/预算，用来做等价性校验。"""
    state = patch_state(text)
    if state != "none":
        raise PatchError(
            f"文件已经是 {state} 状态；直接叠加会产生重复的 img_start_pos。"
            "先 --revert，再选一个模式重打。"
        )
    text = _replace_once(
        text,
        ANCHOR_EMBED,
        ANCHOR_EMBED
        + "        reduce_layers = [1 ,19, 22]\n"
        + "        img_start_pos = kwargs['img_start_pos']\n"
        + "        img_end_pos = kwargs['img_end_pos']\n"
        + "        prev_hidden_states = hidden_states\n",
        "作者版：层表与位置",
    )
    text = _replace_once(text, ANCHOR_LOOP, ANCHOR_LOOP + ORIGINAL_BLOCK, "作者版：层循环")
    text = _replace_once(
        text,
        ANCHOR_LANGUAGE_CALL,
        CALLSITE_ORIGINAL + ANCHOR_LANGUAGE_CALL,
        "作者版：language_model 前",
    )
    text = _replace_once(
        text,
        ANCHOR_LANG_KWARGS,
        ANCHOR_LANG_KWARGS + CALLSITE_KWARGS,
        "作者版：kwargs",
    )
    return text
