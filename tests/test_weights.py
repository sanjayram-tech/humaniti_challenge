import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scoring import tier
from scoring.calibration import check_against_reviewers


class WeightsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(tier, "WEIGHTS_PATH", Path(tmp.name) / "weights.yaml")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.defaults = {d["id"]: d["weight"] for d in tier.load_rubric(custom_weights=False)["dimensions"]}

    def test_saved_weights_are_applied_and_reset(self):
        custom = dict(self.defaults, rapport=25, chess_clarity=0)
        tier.save_weights(custom)
        loaded = {d["id"]: d["weight"] for d in tier.load_rubric()["dimensions"]}
        self.assertEqual(loaded, custom)
        tier.reset_weights()
        loaded = {d["id"]: d["weight"] for d in tier.load_rubric()["dimensions"]}
        self.assertEqual(loaded, self.defaults)

    def test_weights_must_total_100(self):
        with self.assertRaises(ValueError):
            tier.save_weights(dict(self.defaults, rapport=99))

    def test_default_weights_match_all_reviewers(self):
        rows = check_against_reviewers(tier.load_rubric(custom_weights=False))
        self.assertTrue(all(r["tiers_apart"] == 0 for r in rows))


if __name__ == "__main__":
    unittest.main()
