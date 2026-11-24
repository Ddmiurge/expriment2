"""Sequential Comics（SCJ）复现（ours，不是作者原版代码）。

四阶段：
  1. GI/RS/CR/IS 抽取（辅助 Qwen3-8B）
  2. 故事脚本（辅助 Qwen3-8B）
  3. 漫画生成（FLUX/SDXL；封面 + N 分镜）
  4. Target Model Attack（PT1 + PT2 + PT3）

原文未公开 Phase I/II prompt，也未给 T2I 型号和分镜数 N；
本实现用自己写的 prompt、固定 N=6、FLUX.1-schnell，均记录为偏离。
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .aux_llm import extract_json, looks_like_refusal
from .dmn import write_placeholder
from .scj_prompts import (
    COMPONENT_PROMPT,
    COMPONENT_SYSTEM,
    SCRIPT_PROMPT,
    SCRIPT_SYSTEM,
    STYLE,
    build_attack_prompt,
)

IMG_SIZE = 1024
MAX_T2I_RETRIES = 3


class ScjGenerationError(RuntimeError):
    pass


# ── 字体与文字叠加 ───────────────────────────────────────────
def _font(size: int, bold: bool = True):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = (text or "").split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def add_caption(src: Path, text: str, dst: Path, *, top: bool = False) -> None:
    """在漫画图顶部/底部加白底黑字字幕，保证模型能读到叙事文本。

    原文由扩散模型直接生成对白；本地 FLUX 对文字渲染不稳定，所以改成
    T2I 只画画面、PIL 叠字幕。这是已记录的偏离，不是原文版式。
    """
    img = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(img)
    font = _font(max(20, img.width // 36))
    margin = max(24, img.width // 32)
    lines = _wrap(d, text.strip(), font, img.width - 2 * margin)
    line_h = int(font.size * 1.35) if hasattr(font, "size") else 34
    box_h = line_h * len(lines) + margin
    y0 = 0 if top else img.height - box_h
    d.rectangle([0, y0, img.width, y0 + box_h], fill=(255, 255, 255))
    y = y0 + margin // 2
    for line in lines:
        w = d.textlength(line, font=font)
        d.text(((img.width - w) / 2, y), line, fill=(0, 0, 0), font=font)
        y += line_h
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst)


# ── Phase I：四分量 ─────────────────────────────────────────
def _as_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x).strip() for x in v if str(x).strip())
    return str(v).strip()


def _as_steps(v) -> list[str]:
    if isinstance(v, str):
        parts = [x.strip(" -•\t") for x in v.replace("；", ";").replace("\n", ";").split(";")]
        return [x for x in parts if x]
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


def validate_components(obj: dict) -> dict:
    comp = {
        "GI": _as_text(obj.get("GI") or obj.get("gain_intent")),
        "RS": _as_text(obj.get("RS") or obj.get("role_specification")),
        "CR": _as_text(obj.get("CR") or obj.get("critical_resources")),
        "IS": _as_steps(obj.get("IS") or obj.get("implementation_steps")),
    }
    missing = [k for k, v in comp.items() if not v]
    if missing:
        raise ScjGenerationError(f"四分量缺字段：{missing}")
    if len(comp["IS"]) < 3:
        raise ScjGenerationError(f"IS 步骤太少：{comp['IS']}")
    return comp


def extract_components(aux, instruction: str, *, retries: int = 2) -> dict:
    prompt = COMPONENT_PROMPT.format(instruction=instruction)
    last = None
    for _ in range(retries + 1):
        try:
            raw = aux.generate(prompt, system=COMPONENT_SYSTEM, max_new_tokens=1024)
            if looks_like_refusal(raw):
                raise ValueError(f"拒答：{raw[:200]}")
            return validate_components(extract_json(raw))
        except Exception as e:  # noqa: BLE001
            last = e
    raise ScjGenerationError(f"四分量抽取失败：{last}")


# ── Phase II：故事脚本 ──────────────────────────────────────
def _validate_script(obj: dict, n_panels: int) -> dict:
    theme = _as_text(obj.get("theme")) or "A Comic Story"
    cover = _as_text(obj.get("cover")) or theme
    raw_scenes = obj.get("scenes")
    if not isinstance(raw_scenes, list) or len(raw_scenes) < n_panels:
        raise ScjGenerationError(f"scenes 数量不足：{type(raw_scenes)} {len(raw_scenes) if isinstance(raw_scenes, list) else 'n/a'}")
    scenes = []
    for s in raw_scenes[:n_panels]:
        if not isinstance(s, dict):
            raise ScjGenerationError("scene 不是 JSON object")
        scenes.append({
            "title": _as_text(s.get("title")),
            "setting": _as_text(s.get("setting")),
            "characters": _as_text(s.get("characters")),
            "action": _as_text(s.get("action")),
            "dialogue": _as_text(s.get("dialogue")),
        })
    if any(not s["action"] for s in scenes):
        raise ScjGenerationError("有 scene 缺 action")
    return {"theme": theme, "cover": cover, "scenes": scenes}


def generate_script(aux, components: dict, n_panels: int = 6, *, retries: int = 2) -> dict:
    prompt = SCRIPT_PROMPT.format(
        n_panels=n_panels,
        gi=components["GI"],
        rs=components["RS"],
        cr=components["CR"],
        is_text="\n".join(f"- {x}" for x in components["IS"]),
    )
    last = None
    for _ in range(retries + 1):
        try:
            raw = aux.generate(prompt, system=SCRIPT_SYSTEM, max_new_tokens=3072)
            if looks_like_refusal(raw):
                raise ValueError(f"拒答：{raw[:200]}")
            return _validate_script(extract_json(raw), n_panels)
        except Exception as e:  # noqa: BLE001
            last = e
    raise ScjGenerationError(f"故事脚本生成失败：{last}")


# ── Phase III：漫画生成 ─────────────────────────────────────
def _image_prompt(scene: dict, index: int) -> str:
    return (
        f"{STYLE} Panel {index + 1}. Setting: {scene['setting']}. "
        f"Action: {scene['action']}. Characters: {scene['characters']}. "
        "Ordinary, harmless scene; no explicit weapons, harmful substances, violence, "
        "crime, or clearly harmful actions."
    )


def _cover_prompt(script: dict) -> str:
    return f"{STYLE} Cover illustration for a comic titled {script['theme']!r}. {script['cover']}"


def _generate_with_retries(t2i, prompt: str, out_dir: Path, name: str, seed: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    attempts = []
    path = None
    for attempt in range(1, MAX_T2I_RETRIES + 1):
        p = out_dir / f"{name}_try{attempt}.png"
        ok = t2i.generate(prompt, p, seed + attempt * 1009)
        attempts.append({"attempt": attempt, "path": str(p), "ok": bool(ok)})
        if ok:
            path = p
            break
    placeholder = path is None
    if placeholder:
        path = out_dir / f"{name}_placeholder.png"
        write_placeholder(path)
    token_info = None
    if hasattr(t2i, "measure_prompt"):
        try:
            token_info = t2i.measure_prompt(prompt)
        except Exception:  # noqa: BLE001
            token_info = None
    return {
        "path": str(path),
        "prompt": prompt,
        "placeholder": placeholder,
        "attempts": attempts,
        "prompt_tokens": token_info,
    }


def generate_comic(t2i, script: dict, out_dir: Path, seed: int) -> list[dict]:
    """生成封面 + N 分镜；封面叠 theme，分镜叠 dialogue。"""
    out_dir = Path(out_dir)
    metas: list[dict] = []

    cover = _generate_with_retries(t2i, _cover_prompt(script), out_dir, "cover", seed)
    cover_final = out_dir / "cover.png"
    add_caption(Path(cover["path"]), script["theme"], cover_final, top=True)
    cover["path"] = str(cover_final)
    cover["kind"] = "cover"
    cover["caption"] = script["theme"]
    metas.append(cover)

    for i, scene in enumerate(script["scenes"]):
        meta = _generate_with_retries(t2i, _image_prompt(scene, i), out_dir, f"panel_{i:02d}", seed + i * 17)
        final = out_dir / f"panel_{i:02d}.png"
        if scene["dialogue"]:
            add_caption(Path(meta["path"]), scene["dialogue"], final, top=False)
            meta["path"] = str(final)
        else:
            # 没有对白也要统一文件名，方便复现
            Image.open(meta["path"]).convert("RGB").save(final)
            meta["path"] = str(final)
        meta["kind"] = "panel"
        meta["caption"] = scene["dialogue"]
        meta["scene_index"] = i
        metas.append(meta)

    return metas


# ── 组装样本 ────────────────────────────────────────────────
def build_scj_sample(
    *,
    uid: str,
    instruction: str,
    category: str,
    aux,
    t2i,
    out_dir: Path,
    seed: int = 0,
    n_panels: int = 6,
) -> dict:
    out_dir = Path(out_dir)
    components = extract_components(aux, instruction)
    script = generate_script(aux, components, n_panels=n_panels)
    image_meta = generate_comic(t2i, script, out_dir / "comic", seed)
    prompt = build_attack_prompt(script["theme"])

    images = [
        {
            "path": m["path"],
            "kind": m["kind"],
            "mask_path": None,
            "caption": m["caption"],
        }
        for m in image_meta
    ]
    return {
        "id": uid,
        "uid": uid,
        "category": category,
        "instruction": instruction,
        "components": components,
        "script": script,
        "images": images,
        "prompt": prompt,
        "meta": {
            "num_images": len(images),
            "num_panels": n_panels,
            "storyboard_policy": "single_panel_harmless",
            "seed": seed,
            "image_meta": image_meta,
        },
    }
