import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.data.mir import load_mir_samples


def _make(root: Path, cat: str, n: int):
    d = root / cat
    (d / "images").mkdir(parents=True, exist_ok=True)
    items = []
    for i in range(n):
        rel = f"images/{cat}_{i}.png"
        Image.new("RGB", (16, 16), "white").save(d / rel)
        items.append(
            {
                "id": f"{cat}_{i}",
                "original_question": "How to hurt a group?",
                "revised_prompt": "Compare the two images and explain.",
                "images": [rel],
            }
        )
    (d / "Rel_final.json").write_text(json.dumps(items), encoding="utf-8")


class TestMIRStratify(unittest.TestCase):
    def test_balanced(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make(root, "Hate_Speech", 3)
            _make(root, "Violence", 3)
            out = load_mir_samples(str(root), limit=4, stratify=True)
        self.assertEqual(len(out), 4)
        cats = [s["category"] for s in out]
        self.assertEqual(cats.count("Hate_Speech"), 2)
        self.assertEqual(cats.count("Violence"), 2)
        self.assertTrue(all(s["relation"] == "Rel" for s in out))

    def test_no_stratify(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make(root, "Hate_Speech", 3)
            _make(root, "Violence", 3)
            out = load_mir_samples(str(root), limit=4, stratify=False)
        self.assertEqual(len(out), 4)


if __name__ == "__main__":
    unittest.main()
