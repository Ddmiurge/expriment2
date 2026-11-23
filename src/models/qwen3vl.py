"""Qwen3-VL 加载、多图输入构造、生成。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from ..pruning.layout import ImageSegment, find_image_segments, validate_against_grid


@dataclass
class Loaded:
    model: object
    processor: object
    device: str


def _dtype(name: str):
    import torch

    return {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }[name]


def load(model_path: str, *, device: str = "cuda:0", dtype: str = "bfloat16",
         attn_implementation: str = "eager", max_pixels: int | None = None,
         min_pixels: int | None = None) -> Loaded:
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    processor = AutoProcessor.from_pretrained(model_path)
    ip = processor.image_processor
    if min_pixels is not None:
        ip.min_pixels = int(min_pixels)
    if max_pixels is not None:
        ip.max_pixels = int(max_pixels)

    model = Qwen3VLForConditionalGeneration.from_pretrained(
        model_path,
        dtype=_dtype(dtype),
        attn_implementation=attn_implementation,
        low_cpu_mem_usage=True,
    )
    model.to(device)
    model.eval()
    return Loaded(model=model, processor=processor, device=device)


def build_inputs(processor, prompt: str, image_paths: list[str], device: str = "cuda:0") -> dict:
    """按 Qwen 的 chat template 构造多图输入。

    提示词里不要自己写 <image> 占位符；图片由 content 里的 {"type":"image"} 决定顺序。
    """
    images = [Image.open(p).convert("RGB") for p in image_paths]
    content = [{"type": "image"} for _ in image_paths]
    content.append({"type": "text", "text": prompt})
    messages = [{"role": "user", "content": content}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=images, return_tensors="pt", padding=True)
    return {k: (v.to(device) if hasattr(v, "to") else v) for k, v in inputs.items()}


def generate(
    loaded: Loaded,
    inputs: dict,
    max_new_tokens: int = 768,
    temperature: float | None = None,
) -> tuple[str, bool]:
    """返回 (回答文本, 是否撞到 max_new_tokens)。

    撞上限意味着回答被截断。MIDAS 要求 600 词以上，768 token 仍可能不够；
    截断样本要在阶段 1 里单独做敏感性分析，不能静默当成正常回答。
    """
    import torch

    kwargs = {"max_new_tokens": max_new_tokens, "do_sample": False}
    if temperature is not None and temperature > 0:
        kwargs.update(do_sample=True, temperature=float(temperature))
    with torch.no_grad():
        out = loaded.model.generate(**inputs, **kwargs)
    new_tokens = out[0, inputs["input_ids"].shape[1]:]
    truncated = int(new_tokens.shape[0]) >= max_new_tokens
    return loaded.processor.decode(new_tokens, skip_special_tokens=True), truncated


def layout(loaded: Loaded, inputs: dict) -> tuple[list[ImageSegment], list[tuple[int, int]], int]:
    """返回 (每张图的序列位置, 每张图的 token 网格, merge_size)。"""
    cfg = loaded.model.config
    vision_cfg = cfg.vision_config
    merge = int(vision_cfg.spatial_merge_size)
    input_ids = inputs["input_ids"]
    segs = find_image_segments(
        input_ids,
        vision_start_id=int(cfg.vision_start_token_id),
        vision_end_id=int(cfg.vision_end_token_id),
    )
    grid_thw = inputs["image_grid_thw"]
    validate_against_grid(segs, grid_thw, merge)
    grids = [
        (int(h) // merge, int(w) // merge)
        for _, h, w in (grid_thw.tolist() if hasattr(grid_thw, "tolist") else grid_thw)
    ]
    return segs, grids, merge


def image_token_counts(inputs: dict, merge: int) -> list[int]:
    grid_thw = inputs["image_grid_thw"]
    grids = grid_thw.tolist() if hasattr(grid_thw, "tolist") else grid_thw
    return [int(t) * int(h) * int(w) // (merge * merge) for t, h, w in grids]


def describe(loaded: Loaded) -> dict:
    cfg = loaded.model.config
    return {
        "model_type": getattr(cfg, "model_type", "?"),
        "text_layers": int(getattr(cfg.text_config, "num_hidden_layers", -1)),
        "hidden_size": int(getattr(cfg.text_config, "hidden_size", -1)),
        "vision_merge": int(getattr(cfg.vision_config, "spatial_merge_size", -1)),
    }


def resolve_image_paths(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        q = Path(p)
        if not q.exists():
            raise FileNotFoundError(f"图片不存在：{p}")
        out.append(str(q))
    return out
