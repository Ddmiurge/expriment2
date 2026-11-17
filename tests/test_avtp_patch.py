import unittest

from src.pruning.avtp_patch import (
    PatchError,
    patch_instrumented,
    patch_original,
    patch_state,
)

ORIGINAL = "x = 1\nreduce_layers = [1 ,19, 22]\ny = 2\n"
INSTRUMENTED = "_PRUNE_CONFIG = {}\nx = 1\n"
BOTH = ORIGINAL + INSTRUMENTED


class TestPatchState(unittest.TestCase):
    def test_states(self):
        self.assertEqual(patch_state("x = 1\n"), "none")
        self.assertEqual(patch_state(ORIGINAL), "original")
        self.assertEqual(patch_state(INSTRUMENTED), "instrumented")
        self.assertEqual(patch_state(BOTH), "both")

    def test_marker_variant(self):
        self.assertEqual(patch_state("# modify begin\n"), "original")

    def test_no_stacking(self):
        # 服务器上踩过的坑：original 状态下再打 instrumented 会重复 img_start_pos
        with self.assertRaises(PatchError):
            patch_instrumented(ORIGINAL)
        with self.assertRaises(PatchError):
            patch_original(INSTRUMENTED)
        with self.assertRaises(PatchError):
            patch_instrumented(BOTH)


if __name__ == "__main__":
    unittest.main()
