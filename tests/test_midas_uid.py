import json
import tempfile
import unittest
from pathlib import Path

from src.data.midas import iter_instruction_records, sample_uid


class TestUID(unittest.TestCase):
    def test_same_id_different_categories(self):
        with tempfile.TemporaryDirectory() as d:
            qdir = Path(d)
            for cat in ("01-Illegal_Activitiy", "02-HateSpeech"):
                (qdir / f"{cat}.json").write_text(
                    json.dumps({"5": {"Question": f"{cat} question"}}),
                    encoding="utf-8",
                )
            recs = list(iter_instruction_records(qdir))
        self.assertEqual({r["id"] for r in recs}, {"5"})
        self.assertEqual(len({r["uid"] for r in recs}), 2)
        self.assertEqual({r["uid"] for r in recs}, {"01-Illegal_Activitiy__5", "02-HateSpeech__5"})

    def test_sample_uid_old_and_new(self):
        self.assertEqual(sample_uid({"id": "5", "category": "01-X"}), "01-X__5")
        self.assertEqual(sample_uid({"id": "01-X__5"}), "01-X__5")
        self.assertEqual(sample_uid({"uid": "a__1", "id": "1"}), "a__1")


if __name__ == "__main__":
    unittest.main()
