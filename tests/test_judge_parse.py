import unittest

from src.eval.judge import parse_score


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


if __name__ == "__main__":
    unittest.main()
