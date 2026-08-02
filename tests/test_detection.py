"""PRD §6.2 / §9: detection quality must be measured from a checked-in
labeled set, not asserted in prose. This computes precision/recall/F1 per
event bucket from tests/fixtures/labeled_transcript_lines.json and checks it
against the (deliberately conservative, below the source report's claims)
targets in PRD §9.
"""
import json
from pathlib import Path

import pytest

from npl_engine.detection import PATTERNS, classify_segment

FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures" / "labeled_transcript_lines.json"

BUCKETS = {
    "goal": {"goal"},
    "card": {"yellow_card", "red_card"},
    "substitution": {"substitution"},
    "penalty": {"penalty"},
    "own_goal": {"own_goal"},
}

TARGETS = {
    "goal": 0.85,
    "card": 0.80,
    "substitution": 0.75,
    "penalty": 0.75,
    "own_goal": 0.65,
}


@pytest.fixture(scope="module")
def fixtures():
    return json.loads(FIXTURES_PATH.read_text())


def test_fixtures_have_minimum_coverage_per_event_type(fixtures):
    """PRD §6.2: >=5 true positives and >=3 negatives per event type."""
    for event_type in PATTERNS:
        positives = [f for f in fixtures if f["label"] == event_type]
        negatives = [f for f in fixtures if f.get("note") == f"negative:{event_type}"]
        assert len(positives) >= 5, f"{event_type} needs >=5 positive fixtures, has {len(positives)}"
        assert len(negatives) >= 3, f"{event_type} needs >=3 negative fixtures, has {len(negatives)}"


def _score_bucket(fixtures, types):
    tp = fp = fn = 0
    for f in fixtures:
        predicted_result = classify_segment(f["text"])
        predicted = predicted_result[0] if predicted_result else None
        true_in = f["label"] in types
        pred_in = predicted in types
        if true_in and pred_in:
            tp += 1
        elif pred_in and not true_in:
            fp += 1
        elif true_in and not pred_in:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


@pytest.mark.parametrize("bucket,types", BUCKETS.items())
def test_detection_f1_meets_target(fixtures, bucket, types):
    precision, recall, f1 = _score_bucket(fixtures, types)
    assert f1 >= TARGETS[bucket], (
        f"{bucket} F1={f1:.2f} (precision={precision:.2f}, recall={recall:.2f}) "
        f"below target {TARGETS[bucket]}"
    )


def test_own_goal_is_not_also_classified_as_plain_goal():
    result = classify_segment("Deflects past his own keeper, an unfortunate own goal.")
    assert result is not None
    assert result[0] == "own_goal"


def test_empty_and_irrelevant_text_returns_none():
    assert classify_segment("") is None
    assert classify_segment("The weather is clear for today's fixture.") is None
