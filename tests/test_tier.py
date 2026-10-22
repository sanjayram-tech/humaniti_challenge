import unittest
from pathlib import Path

import yaml

from scoring.tier import assign_tier, load_rubric

CALIBRATION = Path(__file__).resolve().parent.parent / "rubric" / "calibration" / "reviewed_classes.yaml"


class TierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rubric = load_rubric(custom_weights=False)
        with open(CALIBRATION) as f:
            cls.classes = yaml.safe_load(f)["classes"]

    def test_weights_sum_to_100(self):
        self.assertEqual(sum(d["weight"] for d in self.rubric["dimensions"]), 100)

    def test_reproduces_reviewer_tiers(self):
        for c in self.classes:
            with self.subTest(c["id"]):
                result = assign_tier(c["gates"], c["scores"], c["homework_set"], self.rubric)
                self.assertEqual(result.tier, c["reviewer_tier"], result.reasons)

    def test_critical_gate_failure_overrides_high_scores(self):
        scores = {d["id"]: 5 for d in self.rubric["dimensions"]}
        gates = {"background": "fail", "camera_face": "pass", "lighting": "pass", "av_clarity": "pass"}
        self.assertEqual(assign_tier(gates, scores, True, self.rubric).tier, "Quality issue")

    def test_invalid_score_rejected(self):
        scores = {d["id"]: 3 for d in self.rubric["dimensions"]}
        scores["energy"] = 6
        gates = {g["id"]: "pass" for g in self.rubric["gates"]}
        with self.assertRaises(ValueError):
            assign_tier(gates, scores, True, self.rubric)


if __name__ == "__main__":
    unittest.main()
