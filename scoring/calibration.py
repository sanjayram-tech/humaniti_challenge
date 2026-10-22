"""Compare rubric tiers with the reviewers' tiers on the reviewed classes."""

from pathlib import Path

import yaml

from scoring.tier import TIER_ORDER, assign_tier

CALIBRATION_PATH = Path(__file__).resolve().parent.parent / "rubric" / "calibration" / "reviewed_classes.yaml"


def check_against_reviewers(rubric, path=CALIBRATION_PATH):
    """Returns one row per reviewed class: reviewer tier, rubric tier, score, tiers apart."""
    with open(path) as f:
        classes = yaml.safe_load(f)["classes"]
    rows = []
    for c in classes:
        result = assign_tier(c["gates"], c["scores"], c["homework_set"], rubric)
        rows.append({
            "class": f"{c['batch']} {c['tutor']} ({c['date']})",
            "reviewer_tier": c["reviewer_tier"],
            "rubric_tier": result.tier,
            "score": result.score,
            "tiers_apart": abs(TIER_ORDER.index(result.tier) - TIER_ORDER.index(c["reviewer_tier"])),
        })
    return rows
