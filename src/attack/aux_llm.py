"""DMN 的辅助 LLM：本地 Qwen3-8B。

原文用 Gemini-2.5-flash；本地替代，属已确认的偏离。
只做文本生成：关键短语、案件 JSON、T2I prompt、失败改写。
"""

from __future__ import annotations

import json
import re

from ..common.chat import apply_chat_template_no_think

REFUSAL_PATTERNS = (
    "i can't",
    "i cannot",
    "i'm sorry",
    "i am sorry",
    "cannot assist",
    "can't assist",
    "unable to assist",
    "i won't",
    "i will not",
    "not able to help",
)


def looks_like_refusal(text: str) -> bool:
    low = (text or "").strip().lower()
    return any(p in low for p in REFUSAL_PATTERNS) and "{" not in low


def extract_json(text: str):
    """从模型输出里取第一个完整 JSON 对象；容忍 ```json 围栏。"""
    s = (text or "").strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*```$", "", s)
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"没有 JSON 对象：{text[:300]!r}")
    return json.loads(s[start : end + 1])


class AuxLLM:
    def __init__(
        self,
        model_path: str,
        *,
        device: str = "cuda:0",
        dtype: str = "bfloat16",
        seed: int = 0,
    ):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, dtype=dtype, low_cpu_mem_usage=True
        ).to(device)
        self.model.eval()
        self.device = device
        self.seed = seed
        torch.manual_seed(seed)

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_new_tokens: int = 1024,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        text = apply_chat_template_no_think(
            self.tokenizer,
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.tokenizer([text], return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            out = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
        new = out[0, inputs["input_ids"].shape[1]:]
        return self.tokenizer.decode(new, skip_special_tokens=True).strip()

    def generate_json(self, prompt: str, *, system: str | None = None, max_new_tokens: int = 2048):
        raw = self.generate(prompt, system=system, max_new_tokens=max_new_tokens)
        if looks_like_refusal(raw):
            raise ValueError(f"辅助 LLM 拒答：{raw[:300]!r}")
        return extract_json(raw)

    def unload(self) -> None:
        del self.model
        self.model = None
        self.torch.cuda.empty_cache()
