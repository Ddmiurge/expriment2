import unittest

from src.attack.midas_offline import game_command


class TestGameCommand(unittest.TestCase):
    def test_dash_leading_answer(self):
        cmd = game_command("/tmp/game/1_compass.py", "/tmp/out", "-only", 3)
        self.assertIn("--target_answer=-only", cmd)
        self.assertIn("--out_dir=/tmp/out", cmd)
        self.assertIn("--max_steps=2", cmd)
        self.assertNotIn("-only", cmd)  # 不能作为独立 argv 出现

    def test_all_flags_use_equals(self):
        cmd = game_command("/tmp/game/5_odd_letter.py", "/tmp/out", "-ab", 1)
        for token in cmd[2:]:
            self.assertTrue(token.startswith("--"), token)
            self.assertIn("=", token, token)


if __name__ == "__main__":
    unittest.main()
