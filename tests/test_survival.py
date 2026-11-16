import unittest

import numpy as np

from src.eval.survival import (
    compute_survival,
    kept_fraction_by_image_index,
)


class TestSurvival(unittest.TestCase):
    def test_compute(self):
        mask = np.zeros((4, 4), dtype=np.float32)
        mask[0:2, 0:2] = 1.0
        s = compute_survival(
            kept_local_by_image=[[0, 1, 2, 3], [1, 3]],
            grids=[(2, 2), (2, 2)],
            payload_masks=[mask, None],
        )
        self.assertEqual(s.per_image[0], 1.0)
        self.assertIsNone(s.per_image[1])
        self.assertAlmostEqual(s.overall, 1.0)
        self.assertEqual(s.per_image_kept_count, [4, 2])
        self.assertEqual(s.per_image_kept_fraction, [1.0, 0.5])

    def test_partial(self):
        mask = np.zeros((2, 2), dtype=np.float32)
        mask[0, 0] = mask[0, 1] = 1.0
        s = compute_survival([[0]], [(2, 2)], [mask])
        self.assertEqual(s.per_image[0], 0.5)  # 两个载荷块里保住一个

    def test_profile(self):
        m = np.ones((2, 2), dtype=np.float32)
        a = compute_survival([[0, 1], [0, 1]], [(2, 2), (2, 2)], [m, m])
        b = compute_survival([[0], [1]], [(2, 2), (2, 2)], [m, m])
        prof = kept_fraction_by_image_index([a, b])
        # a: 2/4，b: 1/4 → 按样本平均 3/8
        self.assertAlmostEqual(prof[0], 0.375)
        self.assertAlmostEqual(prof[1], 0.375)


if __name__ == "__main__":
    unittest.main()
