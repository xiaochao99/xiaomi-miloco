# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def accuracy_score(predictions: List[Any], actuals: List[Any]) -> float:
    if not predictions or not actuals or len(predictions) != len(actuals):
        return 0.0
    correct = sum(1 for p, a in zip(predictions, actuals) if p == a)
    return correct / len(predictions)


def mae_score(predictions: List[float], actuals: List[float]) -> float:
    if not predictions or not actuals or len(predictions) != len(actuals):
        return float("inf")
    errors = [abs(p - a) for p, a in zip(predictions, actuals)]
    return sum(errors) / len(errors)


def time_mae_minutes(predicted_hours: List[float], actual_hours: List[float]) -> float:
    if not predicted_hours or not actual_hours or len(predicted_hours) != len(actual_hours):
        return float("inf")
    errors = []
    for p, a in zip(predicted_hours, actual_hours):
        diff = abs(p - a)
        if diff > 12:
            diff = 24 - diff
        errors.append(diff * 60)
    return sum(errors) / len(errors)


def precision_recall_f1(
    predictions: List[Any],
    actuals: List[Any],
    positive_label: Any = True,
) -> Dict[str, float]:
    if not predictions or not actuals or len(predictions) != len(actuals):
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    tp = sum(1 for p, a in zip(predictions, actuals) if p == positive_label and a == positive_label)
    fp = sum(1 for p, a in zip(predictions, actuals) if p == positive_label and a != positive_label)
    fn = sum(1 for p, a in zip(predictions, actuals) if p != positive_label and a == positive_label)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def confidence_calibration(
    predictions: List[Dict[str, Any]],
    bins: int = 10,
) -> Dict[str, Any]:
    if not predictions:
        return {"ece": 0.0, "bins": []}

    bin_size = 1.0 / bins
    bin_data = [{"total": 0, "correct": 0, "avg_confidence": 0.0} for _ in range(bins)]

    for pred in predictions:
        conf = pred.get("confidence", 0.0)
        correct = pred.get("correct", False)
        bin_idx = min(int(conf / bin_size), bins - 1)
        bin_data[bin_idx]["total"] += 1
        bin_data[bin_idx]["avg_confidence"] += conf
        if correct:
            bin_data[bin_idx]["correct"] += 1

    total_samples = sum(b["total"] for b in bin_data)
    ece = 0.0
    result_bins = []

    for i, b in enumerate(bin_data):
        if b["total"] > 0:
            avg_conf = b["avg_confidence"] / b["total"]
            accuracy = b["correct"] / b["total"]
            ece += (b["total"] / total_samples) * abs(accuracy - avg_conf)
            result_bins.append({
                "range": f"{i * bin_size:.1f}-{(i + 1) * bin_size:.1f}",
                "samples": b["total"],
                "avg_confidence": round(avg_conf, 3),
                "accuracy": round(accuracy, 3),
            })

    return {"ece": round(ece, 4), "bins": result_bins}
