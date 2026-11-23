#!/usr/bin/env python3
"""新受害者模型兼容性探测（Qwen3.7 等）。

只做“能不能做多图 + 能不能套 AVTP”的预检，不跑正式实验。

用法：
    python scripts/probe_victim_model.py --model /path/to/Qwen3.7-VL
    python scripts/probe_victim_model.py --model /path/to/model --load

输出：
  - model_type / architectures / vision_config / text layers
  - transformers 版本
  - Qwen3VLForConditionalGeneration 是否可用
  - AVTP 补丁状态（如果装的是 Qwen3-VL 架构）
  - 可选：真正加载模型，跑一条 2 图前向，报告显存峰值

判读：
  - model_type 不是 qwen3_vl / 没有 vision_config → 不是多图 VL，不能做 DMN/SCJ；
  - 有 vision_config 但 model_type 不是 qwen3_vl → AVTP 补丁需要移植，不能直接跑；
  - `--load` OOM → 24GB 单卡不够，换大卡或 2 卡流水线（后者要改 AVTP 跨设备状态）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, help="模型目录或 HF repo id")
    p.add_argument("--load", action="store_true", help="真正加载并跑一条 2 图前向")
    p.add_argument("--device", default="cuda:0")
    p.add_argument("--dtype", default="bfloat16")
    p.add_argument("--max-pixels", type=int, default=640 * 640)
    p.add_argument("--trust-remote-code", action="store_true")
    a = p.parse_args()

    import transformers
    from transformers import AutoConfig

    info: dict = {"model": a.model, "transformers": transformers.__version__}
    cfg = AutoConfig.from_pretrained(
        a.model, trust_remote_code=a.trust_remote_code
    )
    info["model_type"] = getattr(cfg, "model_type", "?")
    info["architectures"] = list(getattr(cfg, "architectures", []) or [])
    info["has_vision_config"] = hasattr(cfg, "vision_config")
    if hasattr(cfg, "vision_config"):
        vc = cfg.vision_config
        info["vision"] = {
            "model_type": getattr(vc, "model_type", "?"),
            "spatial_merge_size": getattr(vc, "spatial_merge_size", None),
        }
    tc = getattr(cfg, "text_config", cfg)
    info["text_layers"] = getattr(tc, "num_hidden_layers", None)
    info["hidden_size"] = getattr(tc, "hidden_size", None)
    info["image_token_id"] = getattr(cfg, "image_token_id", None)
    info["vision_start_token_id"] = getattr(cfg, "vision_start_token_id", None)
    info["vision_end_token_id"] = getattr(cfg, "vision_end_token_id", None)

    try:
        from transformers import Qwen3VLForConditionalGeneration  # noqa: F401
        info["qwen3vl_class"] = True
    except Exception as e:  # noqa: BLE001
        info["qwen3vl_class"] = False
        info["qwen3vl_import_error"] = str(e)

    # AVTP 补丁只认 Qwen3-VL 的 modeling 文件；这里只看当前安装的 Qwen3-VL 文件状态，
    # 不表示新模型可直接套用。
    try:
        from src.pruning.avtp_patch import patch_state
        from transformers.models.qwen3_vl import modeling_qwen3_vl as qwen3vl_mod

        target = Path(qwen3vl_mod.__file__)
        info["avtp_target"] = str(target)
        info["avtp_patch_state"] = patch_state(target.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        info["avtp_patch_state"] = f"unavailable: {e}"

    print(json.dumps(info, ensure_ascii=False, indent=2))

    if not a.load:
        print("\n（未加载权重；加 --load 跑一条 2 图前向）")
        return 0

    if not info["has_vision_config"]:
        print("\n✗ 没有 vision_config：这不是多图 VL 模型，不能做 DMN/SCJ。")
        return 2

    import torch
    from PIL import Image
    from transformers import AutoProcessor

    try:
        from transformers import AutoModelForImageTextToText as AutoModel
    except ImportError:  # 老版本 transformers 的兜底
        from transformers import AutoModelForVision2Seq as AutoModel

    dtype = {"bfloat16": torch.bfloat16, "float16": torch.float16}[a.dtype]
    device = a.device
    processor = AutoProcessor.from_pretrained(
        a.model, trust_remote_code=a.trust_remote_code
    )
    if hasattr(processor, "image_processor"):
        processor.image_processor.max_pixels = int(a.max_pixels)
        processor.image_processor.min_pixels = int(224 * 224)
    model = AutoModel.from_pretrained(
        a.model, dtype=dtype, low_cpu_mem_usage=True,
        trust_remote_code=a.trust_remote_code,
    ).to(device)
    model.eval()

    tmp = Path("/tmp/probe_victim_model")
    tmp.mkdir(exist_ok=True)
    imgs = []
    for i, color in enumerate(("red", "blue")):
        pth = tmp / f"{i}.png"
        Image.new("RGB", (640, 640), color).save(pth)
        imgs.append(pth)
    content = [{"type": "image"} for _ in imgs]
    content.append({"type": "text", "text": "What are the two colors? Answer briefly."})
    messages = [{"role": "user", "content": content}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[Image.open(x).convert("RGB") for x in imgs],
                       return_tensors="pt", padding=True)
    inputs = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in inputs.items()}

    torch.cuda.reset_peak_memory_stats(device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=64, do_sample=False)
    peak = torch.cuda.max_memory_allocated(device) / 1024**3
    new = out[0, inputs["input_ids"].shape[1]:]
    text_out = processor.tokenizer.decode(new, skip_special_tokens=True)
    print(f"\n2 图前向 OK；峰值显存 {peak:.2f} GiB")
    print(f"输出：{text_out[:300]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
