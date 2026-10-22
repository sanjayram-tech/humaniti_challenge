"""Assign a quality tier to a class from its rubric scores (rubric/rubric.yaml)."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

RUBRIC_PATH = Path(__file__).resolve().parent.parent / "rubric" / "rubric.yaml"
TIER_ORDER = ["Excellent", "Good", "Average", "Weak", "Quality issue"]
GATE_RESULTS = {"pass", "partial", "fail"}


@dataclass
class TierResult:
    tier: str
    score: float
    reasons: list = field(default_factory=list)


def load_rubric(path=RUBRIC_PATH):
    with open(path) as f:
        return yaml.safe_load(f)


def _lower(tier, max_tier):
    """Return whichever of the two tiers is worse."""
    return max(tier, max_tier, key=TIER_ORDER.index)


def weighted_score(rubric, scores):
    total = 0
    weights = 0
    for dim in rubric["dimensions"]:
        value = scores[dim["id"]]
        if not 1 <= value <= 5:
            raise ValueError(f"{dim['id']} score must be 1-5, got {value}")
        total += dim["weight"] * value
        weights += dim["weight"]
    return round(total / weights, 2)


def assign_tier(gates, scores, homework_set, rubric=None):
    """gates: {gate_id: pass|partial|fail}; scores: {dimension_id: 1-5}."""
    rubric = rubric or load_rubric()
    score = weighted_score(rubric, scores)

    tier = next(
        t["name"] for t in rubric["tiers"]
        if t["min_score"] is not None and score >= t["min_score"]
    )
    reasons = [f"Layer 2 score {score} -> {tier}"]

    def cap(max_tier, reason):
        nonlocal tier
        capped = _lower(tier, max_tier)
        if capped != tier:
            reasons.append(f"{reason} -> capped at {max_tier}")
            tier = capped

    triggered = {
        "no_homework": not homework_set,
        "rapport_at_most_2": scores["rapport"] <= 2,
    }
    for rule in rubric["caps"]:
        if triggered[rule["rule"]]:
            cap(rule["max_tier"], rule["description"])

    for gate in rubric["gates"]:
        result = gates[gate["id"]]
        if result not in GATE_RESULTS:
            raise ValueError(f"{gate['id']} must be one of {GATE_RESULTS}, got {result}")
        if gate["severity"] == "critical":
            if result == "fail":
                cap("Quality issue", f"Critical gate failed: {gate['name']}")
            elif result == "partial":
                cap("Weak", f"Critical gate partial: {gate['name']}")
        elif result == "fail":
            cap("Average", f"Minor gate failed: {gate['name']}")

    return TierResult(tier=tier, score=score, reasons=reasons)
