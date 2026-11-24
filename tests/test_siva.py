import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.attack.siva import build_siva_sample, split_image


class TestSiva(unittest.TestCase):
    def _img(self, d: str, w=120, h=90):
        p = Path(d) / "src.png"
        Image.new("RGB", (w, h), "white").save(p)
        return p

    def test_split_1_1(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._img(d)
            metas = split_image(p, Path(d) / "out", ratio="1:1")
            self.assertEqual(len(metas), 2)
            sizes = [Image.open(m.path).size for m in metas]
            self.assertEqual(sum(w for w, _ in sizes), 120)
            self.assertTrue(all(h == 90 for _, h in sizes))

    def test_split_1_2(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._img(d)
            metas = split_image(p, Path(d) / "out", ratio="1:2")
            sizes = [Image.open(m.path).size for m in metas]
            self.assertEqual(len(sizes), 2)
            self.assertEqual(sum(w for w, _ in sizes), 120)
            self.assertLess(sizes[0][0], sizes[1][0])

    def test_split_111(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._img(d)
            metas = split_image(p, Path(d) / "out", ratio="1:1:1")
            self.assertEqual(len(metas), 3)
            self.assertEqual(sum(Image.open(m.path).size[0] for m in metas), 120)

    def test_horizontal(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._img(d)
            metas = split_image(p, Path(d) / "out", ratio="1:1:1", axis="horizontal")
            sizes = [Image.open(m.path).size for m in metas]
            self.assertEqual(len(sizes), 3)
            self.assertEqual(sum(h for _, h in sizes), 90)
            self.assertTrue(all(w == 120 for w, _ in sizes))

    def test_build_sample(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._img(d)
            s = build_siva_sample(
                uid="c__1",
                image_path=str(p),
                instruction="Describe the image step by step.",
                out_dir=Path(d) / "sample",
                ratio="1:1:1",
            )
            self.assertEqual(len(s["images"]), 3)
            self.assertTrue(all(Path(im["path"]).exists() for im in s["images"]))
            self.assertEqual(s["prompt"], "Describe the image step by step.")
            self.assertEqual(s["meta"]["ratio"], "1:1:1")
            self.assertEqual(s["meta"]["num_pieces"], 3)


if __name__ == "__main__":
    unittest.main()
