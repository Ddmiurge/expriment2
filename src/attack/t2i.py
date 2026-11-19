"""DMN 的 T2I 后端。

原文用 GPT Image 1；本仓库主用本地 FLUX.1-schnell（Apache 2.0），
SDXL 保留为备选（但 CLIP 只有 77 token，长 prompt 会被截）。

接口很窄：generate(prompt, out_path, seed) -> bool；
measure_prompt(prompt) -> {t5_tokens, clip_tokens} 用来在 D0 里检查截断。
"""

from __future__ import annotations

from pathlib import Path


class FluxBackend:
    def __init__(
        self,
        model_path: str,
        *,
        device: str = "cuda:0",
        num_inference_steps: int = 4,
        guidance_scale: float = 0.0,
        max_sequence_length: int = 512,
    ):
        import torch
        from diffusers import FluxPipeline

        self.torch = torch
        self.max_sequence_length = max_sequence_length
        self.pipe = FluxPipeline.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
        )
        # 12B + T5；24GB 卡必须 offload，否则 OOM。
        # gpu_id 必须显式给：否则 offload 用当前设备，可能跑到辅助 LLM 的卡上。
        gpu_id = int(device.split(":")[-1]) if ":" in device else 0
        try:
            self.pipe.enable_model_cpu_offload(gpu_id=gpu_id)
        except Exception:
            try:
                self.pipe.enable_sequential_cpu_offload(gpu_id=gpu_id)
            except Exception:
                self.pipe.to(device)
        self.pipe.set_progress_bar_config(disable=True)
        self.device = device
        self.steps = num_inference_steps
        self.guidance = guidance_scale

    def generate(self, prompt: str, out_path: str | Path, seed: int) -> bool:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            g = self.torch.Generator(device="cpu").manual_seed(int(seed))
            image = self.pipe(
                prompt,
                num_inference_steps=self.steps,
                guidance_scale=self.guidance,
                generator=g,
                max_sequence_length=self.max_sequence_length,
            ).images[0]
            image.save(out_path)
            return out_path.exists() and out_path.stat().st_size > 0
        except Exception:
            return False

    def measure_prompt(self, prompt: str) -> dict:
        t5 = self.pipe.tokenizer_2(prompt, truncation=False)["input_ids"]
        clip = self.pipe.tokenizer(prompt, truncation=False)["input_ids"]
        return {
            "t5_tokens": len(t5),
            "clip_tokens": len(clip),
            "t5_limit": int(self.max_sequence_length),
            "clip_limit": int(self.pipe.tokenizer.model_max_length),
        }

    def unload(self) -> None:
        del self.pipe
        self.torch.cuda.empty_cache()


class SDXLBackend:
    """备选。注意：CLIP 文本编码器只有 77 token，长 prompt 会被截断。"""

    def __init__(
        self,
        model_path: str,
        *,
        device: str = "cuda:0",
        num_inference_steps: int = 30,
        guidance_scale: float = 7.0,
    ):
        import torch
        from diffusers import StableDiffusionXLPipeline

        self.torch = torch
        self.pipe = StableDiffusionXLPipeline.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            use_safetensors=True,
        ).to(device)
        self.pipe.set_progress_bar_config(disable=True)
        self.device = device
        self.steps = num_inference_steps
        self.guidance = guidance_scale

    def generate(self, prompt: str, out_path: str | Path, seed: int) -> bool:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            g = self.torch.Generator(device=self.device).manual_seed(int(seed))
            image = self.pipe(
                prompt,
                num_inference_steps=self.steps,
                guidance_scale=self.guidance,
                generator=g,
            ).images[0]
            image.save(out_path)
            return out_path.exists() and out_path.stat().st_size > 0
        except Exception:
            return False

    def measure_prompt(self, prompt: str) -> dict:
        clip = self.pipe.tokenizer(prompt, truncation=False)["input_ids"]
        return {
            "t5_tokens": None,
            "clip_tokens": len(clip),
            "t5_limit": None,
            "clip_limit": int(self.pipe.tokenizer.model_max_length),
        }

    def unload(self) -> None:
        del self.pipe
        self.torch.cuda.empty_cache()
