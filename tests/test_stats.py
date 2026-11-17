import unittest

from src.eval.stats import (
    mcnemar_exact,
    paired_test,
    summarize_survival_vs_asr,
    wilson_ci,
)


class TestStats(unittest.TestCase):
    def test_mcnemar(self):
        self.assertEqual(mcnemar_exact(0, 0), 1.0)
        # 10 vs 0 的单侧概率约 0.00098，双侧 0.00195
        self.assertAlmostEqual(mcnemar_exact(10, 0), 2 / 2**10, places=6)
        self.assertAlmostEqual(mcnemar_exact(5, 5), 1.0, places=6)

    def test_paired_test_direction(self):
        a = [3] * 20 + [0] * 20
        b = [3] * 10 + [0] * 30
        r = paired_test(a, b, n_boot=2000, seed=1)
        self.assertAlmostEqual(r.asr_a, 0.5)
        self.assertAlmostEqual(r.asr_b, 0.25)
        self.assertLess(r.diff, 0)
        self.assertEqual(r.b, 10)  # a 成功 b 失败
        self.assertEqual(r.c, 0)
        self.assertLess(r.p_mcnemar, 0.01)

    def test_verdict(self):
        a = [3] * 50
        b = [3] * 10 + [0] * 40
        r = paired_test(a, b, n_boot=2000, seed=2)
        self.assertEqual(r.verdict(), "kill")

    def test_success_fn_scores5(self):
        r = paired_test([0, 3, 5], [0, 0, 0], n_boot=200, seed=3,
                        success_fn=lambda x: x >= 3)
        self.assertAlmostEqual(r.asr_a, 2 / 3)
        self.assertAlmostEqual(r.asr_b, 0.0)
        self.assertLess(r.diff, 0)

    def test_wilson(self):
        lo, hi = wilson_ci(0, 10)
        self.assertGreaterEqual(lo, 0.0)
        self.assertLess(lo, 0.01)
        self.assertGreater(hi, 0.2)

    def test_survival_summary(self):
        pts = [(0.1, 0.1), (0.5, 0.4), (0.9, 0.8)]
        s = summarize_survival_vs_asr(pts)
        self.assertEqual(s["n"], 3)
        self.assertGreater(s["spearman_rho"], 0.9)


if __name__ == "__main__":
    unittest.main()
