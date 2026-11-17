import unittest

from src.common.chat import apply_chat_template_no_think


class FakeTokenizer:
    def __init__(self, supports=True):
        self.supports = supports
        self.kwargs = None

    def apply_chat_template(self, messages, **kwargs):
        if "enable_thinking" in kwargs and not self.supports:
            raise TypeError("unexpected keyword argument 'enable_thinking'")
        self.kwargs = kwargs
        return "rendered"


class TestNoThink(unittest.TestCase):
    def test_passes_false(self):
        tok = FakeTokenizer(supports=True)
        self.assertEqual(apply_chat_template_no_think(tok, [], tokenize=False), "rendered")
        self.assertIs(tok.kwargs["enable_thinking"], False)

    def test_falls_back(self):
        tok = FakeTokenizer(supports=False)
        self.assertEqual(apply_chat_template_no_think(tok, [], tokenize=False), "rendered")
        self.assertNotIn("enable_thinking", tok.kwargs)


if __name__ == "__main__":
    unittest.main()
