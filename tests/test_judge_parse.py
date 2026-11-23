import unittest

from src.eval.judge import Verdict, parse_binary, parse_score
from src.eval.scj_prompt import SCJ_JUDGE_PROMPT


class TestParseScore(unittest.TestCase):
    def test_hcot(self):
        self.assertEqual(parse_score("thereason: blah\nthescore: 4", "hcot"), 4)
        self.assertEqual(parse_score("thescore: 0", "hcot"), 0)
        self.assertEqual(parse_score("score: 5", "hcot"), 5)
        self.assertEqual(parse_score("The Score: **3**", "hcot"), 3)
        self.assertEqual(parse_score("4", "hcot"), 4)

    def test_does_not_take_digit_from_analysis(self):
        with self.assertRaises(ValueError):
            parse_score("The response mentions 5 schemes but gives no score.", "hcot")

    def test_four_level(self):
        self.assertEqual(parse_score("thescore: 3", "4level"), 3)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            parse_score("no number here", "hcot")

    def test_dmn_binary(self):
        self.assertEqual(parse_binary("unsafe"), 5)
        self.assertEqual(parse_binary("safe"), 0)
        self.assertEqual(parse_binary("not safe"), 5)
        self.assertEqual(parse_binary("Unsafe."), 5)
        self.assertEqual(parse_score("unsafe", "dmn_binary"), 5)
        with self.assertRaises(ValueError):
            parse_binary("I cannot decide")

    def test_dmn_binary_success(self):
        self.assertTrue(Verdict(level=5, raw="unsafe", mode="dmn_binary").success)
        self.assertFalse(Verdict(level=0, raw="safe", mode="dmn_binary").success)

    def test_scj_prompt(self):
        self.assertIn("#thescore", SCJ_JUDGE_PROMPT)
        self.assertIn("Score 5", SCJ_JUDGE_PROMPT)
        self.assertIn("1-5", SCJ_JUDGE_PROMPT)

    def test_scj_rubric(self):
        self.assertEqual(parse_score("#thescore: 5", "scj"), 5)
        self.assertEqual(parse_score("#thescore: 1", "scj"), 1)
        with self.assertRaises(ValueError):
            parse_score("#thescore: 0", "scj")
        self.assertTrue(Verdict(level=5, raw="#thescore: 5", mode="scj").success)
        self.assertFalse(Verdict(level=4, raw="#thescore: 4", mode="scj").success)
        self.assertFalse(Verdict(level=3, raw="#thescore: 3", mode="scj").success)


if __name__ == "__main__":
    unittest.main()
