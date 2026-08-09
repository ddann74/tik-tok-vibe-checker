"""Computes precision/recall/F1 per event bucket from tests/fixtures/labeled_transcript_lines.json.

Buckets match PRD §9: goal, card (yellow+red combined), substitution, penalty, own_goal.
Run: python scripts/compute_detection_metrics.py
"""
import json
from pathlib import Path

from npl_engine.detection import classify_segment

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "labeled_transcript_lines.json"

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


def main():
    fixtures = json.loads(FIXTURES.read_text())
    predictions = []
    for f in fixtures:
        result = classify_segment(f["text"])
        predicted = result[0] if result else None
        predictions.append((f["text"], f["label"], predicted))

    print(f"{'bucket':<14}{'TP':>4}{'FP':>4}{'FN':>4}{'precision':>11}{'recall':>9}{'f1':>7}  target  status")
    all_pass = True
    for bucket, types in BUCKETS.items():
        tp = fp = fn = 0
        for text, label, predicted in predictions:
            true_in = label in types
            pred_in = predicted in types
            if true_in and pred_in:
                tp += 1
            elif pred_in and not true_in:
                fp += 1
                print(f"  FP in {bucket}: predicted={predicted} true={label} :: {text}")
            elif true_in and not pred_in:
                fn += 1
                print(f"  FN in {bucket}: predicted={predicted} true={label} :: {text}")
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        target = TARGETS[bucket]
        status = "PASS" if f1 >= target else "FAIL"
        if f1 < target:
            all_pass = False
        print(f"{bucket:<14}{tp:>4}{fp:>4}{fn:>4}{precision:>11.2f}{recall:>9.2f}{f1:>7.2f}  {target:<6.2f}  {status}")

    print("\nOVERALL:", "PASS" if all_pass else "FAIL")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
