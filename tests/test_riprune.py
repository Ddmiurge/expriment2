import unittest

import torch

from src.pruning.riprune import (
    _cache_has_tokens,
    prune_predecoder,
    query_positions_after_last_image,
    quotas,
    score_tokens,
)


class TestRiprune(unittest.TestCase):
    def test_cache_has_tokens(self):
        class Empty:
            def get_seq_length(self):
                return 0

        class Full:
            def get_seq_length(self):
                return 7

        self.assertFalse(_cache_has_tokens(None))
        self.assertFalse(_cache_has_tokens(Empty()))
        self.assertTrue(_cache_has_tokens(Full()))

    def test_quotas(self):
        self.assertEqual(quotas(10, 3, [4, 4, 4]), [4, 3, 3])
        # 第二张图容量不足，剩余分给其他图
        q = quotas(10, 3, [10, 1, 10])
        self.assertEqual(sum(q), 10)
        self.assertEqual(q[1], 1)
        self.assertTrue(q[0] <= 10 and q[2] <= 10)

    def test_query_positions(self):
        input_ids = torch.arange(10).view(1, -1)
        mask = torch.zeros(1, 10, dtype=torch.bool)
        mask[0, 2:5] = True
        q = query_positions_after_last_image(input_ids, mask)
        self.assertEqual(q.tolist(), [5, 6, 7, 8, 9])
        empty = query_positions_after_last_image(input_ids, torch.zeros(1, 10, dtype=torch.bool))
        self.assertEqual(empty.numel(), 0)

    def test_score_shape(self):
        torch.manual_seed(0)
        v = torch.randn(8, 4)
        t = torch.randn(3, 4)
        s = score_tokens(v, [4, 4], t, prototypes=2)
        self.assertEqual(tuple(s.shape), (8,))
        self.assertTrue(torch.isfinite(s).all())

    def test_prune_sync(self):
        torch.manual_seed(0)
        # 2 图，各 4 个视觉 token；总序列 12，非图像位置 0,1,10,11
        s_len, d, j = 12, 4, 8
        inputs = torch.randn(1, s_len, d)
        image_embeds = torch.randn(j, d)
        positions = torch.tensor([2, 3, 4, 5, 6, 7, 8, 9])
        mask = torch.zeros(1, s_len, dtype=torch.bool)
        mask[0, positions] = True
        position_ids = torch.arange(s_len).view(1, 1, -1).expand(3, 1, -1).clone()
        attention = torch.ones(1, s_len, dtype=torch.long)
        deep = [torch.randn(j, d), torch.randn(j, d)]

        out = prune_predecoder(
            inputs_embeds=inputs,
            image_embeds=image_embeds,
            image_token_positions=positions,
            image_lengths=[4, 4],
            position_ids=position_ids,
            attention_mask=attention,
            visual_pos_masks=mask,
            deepstack_visual_embeds=deep,
            budget=0.5,
            prototypes=2,
        )
        # 总预算 4，每图 2
        self.assertEqual([len(x) for x in out.kept_local], [2, 2])
        self.assertEqual(out.inputs_embeds.shape[1], s_len - 8 + 4)
        self.assertEqual(out.position_ids.shape[2], out.inputs_embeds.shape[1])
        self.assertEqual(out.attention_mask.shape[1], out.inputs_embeds.shape[1])
        self.assertEqual(out.visual_pos_masks.shape[1], out.inputs_embeds.shape[1])
        self.assertEqual(out.deepstack_visual_embeds[0].shape[0], 4)


if __name__ == "__main__":
    unittest.main()
