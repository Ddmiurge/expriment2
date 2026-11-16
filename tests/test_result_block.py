import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from result_block import ResultBlock, parse_block, to_text  # noqa: E402


class TestResultBlock(unittest.TestCase):
    def test_roundtrip(self):
        b = ResultBlock(
            exp="t",
            levels=[0, 3, 2, 1],
            survival=[0.0, 1.0, 0.5, None],
            cfg={"pruner": "sieve", "budget": "0.25"},
            extra={"keepfrac": "0=0.25 1=0.24"},
            kind="profile",
        )
        got = parse_block(to_text(b))
        self.assertEqual(got.levels, b.levels)
        self.assertEqual(got.survival, [0.0, 1.0, 0.5, None])
        self.assertEqual(got.cfg, b.cfg)
        self.assertEqual(got.extra["keepfrac"], "0=0.25 1=0.24")

    def test_truncation_raises(self):
        b = ResultBlock(exp="t", levels=[0, 1, 2], survival=[0.1, 0.2, 0.3])
        text = to_text(b)
        with self.assertRaises(ValueError):
            parse_block(text.replace("n:      3", "n:      4"))
        with self.assertRaises(ValueError):
            parse_block(text[:-20])

    def test_no_survival(self):
        b = ResultBlock(exp="t", levels=[3, 3], kind="asr")
        got = parse_block(to_text(b))
        self.assertIsNone(got.survival_mean())
        self.assertEqual(got.asr(), 1.0)


if __name__ == "__main__":
    unittest.main()
