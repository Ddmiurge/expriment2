import unittest

import numpy as np

from src.pruning.layout import (
    find_image_segments,
    grid_shape,
    local_to_rowcol,
    mask_to_grid,
    survival_rate,
    validate_against_grid,
)

VS, VE, IT = 100, 101, 102


def make_ids(n_images=2, per_image=4):
    ids = [7, 8]
    for _ in range(n_images):
        ids += [VS] + [IT] * per_image + [VE]
    ids += [9]
    return ids


class TestLayout(unittest.TestCase):
    def test_segments(self):
        segs = find_image_segments(make_ids(), VS, VE)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0].n_tokens, 4)
        self.assertEqual(list(segs[0].positions), [3, 4, 5, 6])
        self.assertEqual(segs[1].start, 8)

    def test_grid_validation(self):
        segs = find_image_segments(make_ids(), VS, VE)
        # 4x4 grid, merge 2 -> 2x2 = 4 tokens
        validate_against_grid(segs, [[1, 4, 4], [1, 4, 4]], merge_size=2)
        with self.assertRaises(ValueError):
            validate_against_grid(segs, [[1, 4, 8], [1, 4, 4]], merge_size=2)

    def test_grid_shape(self):
        self.assertEqual(grid_shape([[1, 6, 8]], 0, merge_size=2), (3, 4))

    def test_local_to_rowcol(self):
        rows, cols = local_to_rowcol([0, 1, 2, 3], 2, 2)
        self.assertEqual(rows.tolist(), [0, 0, 1, 1])
        self.assertEqual(cols.tolist(), [0, 1, 0, 1])
        with self.assertRaises(ValueError):
            local_to_rowcol([4], 2, 2)

    def test_mask_to_grid(self):
        m = np.zeros((4, 4), dtype=np.float32)
        m[0:2, 0:2] = 1.0  # 左上角一个 2x2 块
        g = mask_to_grid(m, 2, 2)
        self.assertTrue(g[0, 0])
        self.assertFalse(g[0, 1] or g[1, 0] or g[1, 1])

    def test_mask_to_grid_non_divisible(self):
        m = np.zeros((5, 5), dtype=np.float32)
        m[0:3, 0:3] = 1.0
        g = mask_to_grid(m, 2, 2)
        self.assertEqual(g.shape, (2, 2))
        self.assertTrue(g[0, 0])

    def test_survival(self):
        pg = np.array([[True, False], [False, False]])
        # 保留全部 -> 1.0；保留右下 -> 0.0；保留左上 -> 1.0
        self.assertEqual(survival_rate([0, 1, 2, 3], 2, 2, pg), 1.0)
        self.assertEqual(survival_rate([3], 2, 2, pg), 0.0)
        self.assertEqual(survival_rate([0], 2, 2, pg), 1.0)


if __name__ == "__main__":
    unittest.main()
