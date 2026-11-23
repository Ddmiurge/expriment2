import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.attack.scj import build_scj_sample, generate_comic, validate_components
from src.attack.scj_prompts import PT1, PT2, PT3, build_attack_prompt

COMPONENTS = {
    "GI": "obtain a restricted item",
    "RS": "a determined investigator",
    "CR": "a map, a key, and a vehicle",
    "IS": ["locate the target", "prepare the tools", "enter the site", "leave the area"],
}


class FakeAux:
    def generate(self, prompt, *, system=None, max_new_tokens=1024):
        if "Decompose" in prompt:
            return json.dumps(COMPONENTS)
        if "comic script" in prompt:
            return json.dumps({
                "theme": "The Long Road",
                "cover": "a lone figure on a road at dusk",
                "scenes": [
                    {
                        "title": f"Scene {i+1}",
                        "setting": "a quiet street",
                        "characters": "a determined investigator",
                        "action": f"action {i+1}",
                        "dialogue": f"line {i+1}",
                    }
                    for i in range(6)
                ],
            })
        return "ok"


class FakeT2I:
    def generate(self, prompt, out_path, seed):
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (256, 256), "white").save(out_path)
        return True

    def measure_prompt(self, prompt):
        return {"t5_tokens": len(prompt.split()), "clip_tokens": len(prompt.split()),
                "t5_limit": 512, "clip_limit": 77}


class TestScjPrompts(unittest.TestCase):
    def test_pt_texts(self):
        self.assertIn("multiple comic images", PT1)
        self.assertIn("*THEME*", PT2)
        self.assertIn("professional detective", PT3)

    def test_attack_prompt(self):
        p = build_attack_prompt("My Theme")
        self.assertIn("My Theme", p)
        self.assertIn(PT1[:40], p)
        self.assertIn(PT3[:40], p)
        self.assertNotIn("*THEME*", p)


class TestScjPipeline(unittest.TestCase):
    def test_validate_components(self):
        c = validate_components(COMPONENTS)
        self.assertEqual(c["GI"], COMPONENTS["GI"])
        self.assertEqual(len(c["IS"]), 4)

    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            s = build_scj_sample(
                uid="c__1",
                instruction="test instruction",
                category="c",
                aux=FakeAux(),
                t2i=FakeT2I(),
                out_dir=Path(d),
                seed=0,
                n_panels=6,
            )
            self.assertEqual(len(s["images"]), 7)  # 封面 + 6 分镜
            self.assertTrue(all(im["mask_path"] is None for im in s["images"]))
            self.assertTrue(all(Path(im["path"]).exists() for im in s["images"]))
            self.assertEqual(s["images"][0]["kind"], "cover")
            self.assertEqual(s["images"][0]["caption"], "The Long Road")
            self.assertEqual(s["images"][1]["caption"], "line 1")
            self.assertIn("The Long Road", s["prompt"])
            self.assertIn(PT1[:40], s["prompt"])
            self.assertEqual(s["meta"]["num_panels"], 6)
            self.assertEqual(s["meta"]["image_meta"][0]["prompt_tokens"]["t5_tokens"] > 0, True)

    def test_caption_changes_image(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src.png"
            Image.new("RGB", (256, 256), "white").save(src)
            script = {
                "theme": "T",
                "cover": "c",
                "scenes": [
                    {"title": "s", "setting": "x", "characters": "y",
                     "action": "z", "dialogue": "caption"} for _ in range(6)
                ],
            }
            metas = generate_comic(FakeT2I(), script, Path(d) / "comic", seed=0)
            self.assertEqual(len(metas), 7)
            # 叠加了字幕，图片不应再是全白
            img = Image.open(metas[1]["path"]).convert("RGB")
            self.assertTrue(any(px != (255, 255, 255) for px in img.getdata()))


if __name__ == "__main__":
    unittest.main()
