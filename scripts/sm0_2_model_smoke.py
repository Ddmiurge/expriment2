#!/usr/bin/env python3
"""SM0.2 模型冒烟：Qwen3-VL-8B 能读多图、网格对得上、输出非退化。

用两张合成图（白底黑字 A / B），避免依赖 MIDAS 素材。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.paths import model_path, runtime  # noqa: E402
from src.models.qwen3vl import build_inputs, describe, generate, layout, load  # noqa: E402


def letter_image(ch: str, path: Path) -> None:
    im = Image.new("RGB", (448, 448), "white")
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 260)
    except Exception:
        font = ImageFont.load_default()
    d.text((120, 70), ch, fill="black", font=font)
    im.save(path)


def main() -> int:
    rt = runtime()
    tmp = Path(tempfile.mkdtemp(prefix="sm0_2_"))
    a, b = tmp / "a.png", tmp / "b.png"
    letter_image("A", a)
    letter_image("B", b)

    loaded = load(
        model_path("qwen3vl_8b"),
        device=rt.get("device", "cuda:0"),
        dtype=rt.get("dtype", "bfloat16"),
        attn_implementation=rt.get("attn_implementation", "eager"),
        max_pixels=640 * 640,
        min_pixels=224 * 224,
    )
    print("模型描述：", describe(loaded))

    prompt = "The two images each contain one capital letter. Reply with the two letters in order, separated by a comma. Nothing else."
    inputs = build_inputs(loaded.processor, prompt, [str(a), str(b)], loaded.device)
    segs, grids, merge = layout(loaded, inputs)
    print(f"图数={len(segs)} 每图 token={[s.n_tokens for s in segs]} 网格={grids} merge={merge}")
    print(f"image_grid_thw={inputs['image_grid_thw'].tolist()}")

    out, truncated = generate(loaded, inputs, max_new_tokens=24)
    print("撞到上限：", truncated)
    print("回答：", repr(out))

    ok = True
    if len(segs) != 2:
        print("✗ 图片数不是 2"); ok = False
    if any(s.n_tokens < 16 for s in segs):
        print("✗ 每图视觉 token 少于 16，预处理可能没生效"); ok = False
    letters = {c for c in out.upper() if c in "AB"}
    if letters != {"A", "B"}:
        print(f"✗ 回答里没有同时出现 A 和 B：{out!r}"); ok = False
    print("\nSM0.2", "通过" if ok else "失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
