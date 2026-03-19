"""Strategy classification evaluator: compare LLM predictions against gold labels."""
from __future__ import annotations

import logging
import random
from collections import Counter
from collections.abc import Awaitable, Callable

from vn_agent.eval.corpus import AnnotatedSession

logger = logging.getLogger(__name__)

# VN-Agent strategies that have COLX_523 mappings
VALID_STRATEGIES = ["accumulate", "erode", "rupture", "reveal", "contrast", "weave"]

# Simple keyword baseline for --mock mode
_KEYWORD_RULES: dict[str, list[str]] = {
    "accumulate": ["gradually", "slowly build", "layer", "accumulate", "growing"],
    "erode": ["erode", "wear down", "doubt", "crumble", "decay"],
    "rupture": ["sudden", "shock", "rupture", "break", "snap", "explosion"],
    "reveal": ["secret", "hidden", "reveal", "uncover", "discover", "truth"],
    "contrast": ["contrast", "juxtapose", "oppose", "versus", "light and dark"],
    "weave": ["weave", "interleave", "thread", "drift", "wander", "parallel"],
}


def keyword_classifier(text: str) -> str:
    """Rule-based baseline classifier using keyword matching."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for strategy, keywords in _KEYWORD_RULES.items():
        scores[strategy] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=lambda s: scores[s])
    if scores[best] == 0:
        return random.choice(VALID_STRATEGIES)
    return best


async def evaluate_strategy_classification(
    corpus: list[AnnotatedSession],
    llm_callable: Callable[[str], Awaitable[str]],
    sample_size: int = 50,
) -> dict:
    """Evaluate strategy classification on a corpus sample.

    Args:
        corpus: List of annotated sessions (only those with non-None strategy are used).
        llm_callable: async function (text) -> predicted strategy label.
        sample_size: Number of samples to evaluate (0 = all).

    Returns:
        Dict with keys: accuracy, per_class (precision/recall/f1), confusion_matrix, total, errors.
    """
    # Filter to sessions with valid mapped strategies
    valid = [s for s in corpus if s.strategy in VALID_STRATEGIES]
    if not valid:
        return {"accuracy": 0.0, "per_class": {}, "confusion_matrix": {}, "total": 0, "errors": 0}

    if 0 < sample_size < len(valid):
        valid = random.sample(valid, sample_size)

    predictions: list[tuple[str, str]] = []  # (gold, predicted)
    errors = 0

    for session in valid:
        try:
            pred = await llm_callable(session.text)
            pred = pred.strip().lower()
            if pred not in VALID_STRATEGIES:
                pred = _closest_strategy(pred)
            predictions.append((session.strategy, pred))  # type: ignore[arg-type]
        except Exception as e:
            logger.warning(f"Classification error for {session.id}: {e}")
            errors += 1

    if not predictions:
        return {
            "accuracy": 0.0, "per_class": {}, "confusion_matrix": {},
            "total": 0, "errors": errors,
        }

    return _compute_metrics(predictions, errors)


def _closest_strategy(pred: str) -> str:
    """Map a noisy prediction to the closest valid strategy."""
    pred_lower = pred.lower()
    for s in VALID_STRATEGIES:
        if s in pred_lower:
            return s
    return "accumulate"  # default fallback


def _compute_metrics(predictions: list[tuple[str, str]], errors: int) -> dict:
    """Compute accuracy, per-class precision/recall/F1, and confusion matrix."""
    correct = sum(1 for g, p in predictions if g == p)
    total = len(predictions)
    accuracy = correct / total if total else 0.0

    # Confusion matrix
    labels = sorted(set(g for g, _ in predictions) | set(p for _, p in predictions))
    confusion: dict[str, dict[str, int]] = {g: {p: 0 for p in labels} for g in labels}
    for g, p in predictions:
        confusion[g][p] += 1

    # Per-class metrics
    gold_counts = Counter(g for g, _ in predictions)
    pred_counts = Counter(p for _, p in predictions)
    per_class: dict[str, dict[str, float]] = {}

    for label in labels:
        tp = confusion[label][label]
        precision = tp / pred_counts[label] if pred_counts[label] else 0.0
        recall = tp / gold_counts[label] if gold_counts[label] else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": gold_counts[label],
        }

    return {
        "accuracy": round(accuracy, 4),
        "per_class": per_class,
        "confusion_matrix": confusion,
        "total": total,
        "errors": errors,
    }


def format_report(metrics: dict) -> str:
    """Format metrics dict as a classification report string."""
    lines = [
        f"Strategy Classification Report ({metrics['total']} samples, {metrics['errors']} errors)",
        f"Overall Accuracy: {metrics['accuracy']:.1%}",
        "",
        f"{'Strategy':<15} {'Prec':>6} {'Recall':>6} {'F1':>6} {'Support':>8}",
        "-" * 45,
    ]
    for label, stats in sorted(metrics.get("per_class", {}).items()):
        lines.append(
            f"{label:<15} {stats['precision']:>6.2f} {stats['recall']:>6.2f} "
            f"{stats['f1']:>6.2f} {stats['support']:>8}"
        )
    return "\n".join(lines)
