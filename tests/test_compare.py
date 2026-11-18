import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_stage1 import paired_compare  # noqa: E402


class TestPairedCompare(unittest.TestCase):
    def _base(self, d):
        path = Path(d) / "base.jsonl"
        rows = [
            {"uid": "a__1", "score5": 5, "level": 3},
            {"uid": "a__2", "score5": 0, "level": 0},
            {"uid": "a__3", "score5": 5, "level": 3},
        ]
        path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        return path

    def test_hcot_uses_score5(self):
        with tempfile.TemporaryDirectory() as d:
            base = self._base(d)
            rows = [
                {"uid": "a__1", "score5": 0, "level": 0},
                {"uid": "a__2", "score5": 0, "level": 0},
                {"uid": "a__3", "score5": 5, "level": 3},
            ]
            res, use5 = paired_compare(base, rows, "hcot")
        self.assertTrue(use5)
        self.assertAlmostEqual(res.asr_a, 2 / 3)
        self.assertAlmostEqual(res.asr_b, 1 / 3)
        self.assertLess(res.diff, 0)

    def test_no_pairs(self):
        with tempfile.TemporaryDirectory() as d:
            base = self._base(d)
            self.assertIsNone(paired_compare(base, [{"uid": "other__1", "score5": 5}], "hcot"))


if __name__ == "__main__":
    unittest.main()
