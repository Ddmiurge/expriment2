import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from src.data.midas import iter_instruction_records, stratified_records

CATS = [
    "Hate_Speech", "Violence", "Self-Harm", "Illegal_Activities",
    "Harassment", "Privacy", "Political_Lobbying", "Gov_Decision",
    "Legal_Opinion", "Financial_Advice", "Health_Consultation",
    "Fraud", "Malware",
]


def records():
    return [
        {"id": f"{cat}_{i:02d}", "category": cat, "instruction": "x", "source": "s"}
        for cat in CATS
        for i in range(5)
    ]


class TestStratify(unittest.TestCase):
    def test_balanced(self):
        out = stratified_records(records(), 40, seed=0)
        self.assertEqual(len(out), 40)
        counts = Counter(r["category"] for r in out)
        self.assertEqual(len(counts), len(CATS))
        # 40 / 13 = 3 余 1；排序后的第一类多 1 条
        self.assertEqual(counts[sorted(CATS)[0]], 4)
        self.assertTrue(all(counts[c] == 3 for c in sorted(CATS)[1:]))

    def test_deterministic(self):
        a = stratified_records(records(), 20, seed=7)
        b = stratified_records(records(), 20, seed=7)
        self.assertEqual([r["id"] for r in a], [r["id"] for r in b])

    def test_no_limit_keeps_all(self):
        rs = records()
        self.assertEqual(len(stratified_records(rs, None)), len(rs))

    def test_category_falls_back_to_parent_dir(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "Violence"
            p.mkdir()
            (p / "question.json").write_text(
                json.dumps([{"id": "v1", "question": "How to hurt someone?"}]),
                encoding="utf-8",
            )
            recs = list(iter_instruction_records(d))
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["category"], "Violence")


if __name__ == "__main__":
    unittest.main()
