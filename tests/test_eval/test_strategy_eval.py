"""Tests for strategy classification evaluator."""
from __future__ import annotations

import pytest

from vn_agent.eval.corpus import AnnotatedSession
from vn_agent.eval.strategy_eval import (
    VALID_STRATEGIES,
    _compute_metrics,
    evaluate_strategy_classification,
    format_report,
    keyword_classifier,
)


def _make_session(id: str, text: str, strategy: str) -> AnnotatedSession:
    return AnnotatedSession(id=id, title=f"Session {id}", text=text, strategy=strategy)


MOCK_CORPUS = [
    _make_session("1", "The tension gradually builds layer by layer", "accumulate"),
    _make_session("2", "Doubt begins to erode her confidence", "erode"),
    _make_session("3", "A sudden shock ruptures the calm", "rupture"),
    _make_session("4", "They slowly uncover the hidden secret truth", "reveal"),
    _make_session("5", "Light and dark contrast sharply", "contrast"),
    _make_session("6", "Threads weave and interleave through time", "weave"),
]


class TestKeywordClassifier:
    def test_accumulate_keywords(self):
        assert keyword_classifier("The tension gradually builds layer by layer") == "accumulate"

    def test_rupture_keywords(self):
        assert keyword_classifier("A sudden shock breaks everything") == "rupture"

    def test_reveal_keywords(self):
        assert keyword_classifier("The hidden truth is finally revealed") == "reveal"

    def test_no_match_returns_valid_strategy(self):
        result = keyword_classifier("Just a normal conversation about weather")
        assert result in VALID_STRATEGIES


class TestComputeMetrics:
    def test_perfect_predictions(self):
        preds = [("accumulate", "accumulate"), ("erode", "erode"), ("rupture", "rupture")]
        metrics = _compute_metrics(preds, errors=0)
        assert metrics["accuracy"] == 1.0
        assert metrics["total"] == 3
        assert metrics["errors"] == 0
        for label_stats in metrics["per_class"].values():
            assert label_stats["f1"] == 1.0

    def test_zero_correct(self):
        preds = [("accumulate", "erode"), ("erode", "accumulate")]
        metrics = _compute_metrics(preds, errors=0)
        assert metrics["accuracy"] == 0.0

    def test_partial_correct(self):
        preds = [
            ("accumulate", "accumulate"),
            ("accumulate", "erode"),
            ("erode", "erode"),
        ]
        metrics = _compute_metrics(preds, errors=0)
        assert metrics["accuracy"] == pytest.approx(2 / 3, abs=0.01)

    def test_confusion_matrix(self):
        preds = [("accumulate", "erode"), ("accumulate", "accumulate")]
        metrics = _compute_metrics(preds, errors=0)
        assert metrics["confusion_matrix"]["accumulate"]["erode"] == 1
        assert metrics["confusion_matrix"]["accumulate"]["accumulate"] == 1


class TestEvaluateStrategyClassification:
    @pytest.mark.asyncio
    async def test_perfect_classifier(self):
        async def perfect_classifier(text: str) -> str:
            # Return the gold strategy by keyword matching
            return keyword_classifier(text)

        metrics = await evaluate_strategy_classification(
            MOCK_CORPUS, perfect_classifier, sample_size=0
        )
        assert metrics["total"] == 6
        assert metrics["accuracy"] > 0  # keyword classifier won't be perfect but should score

    @pytest.mark.asyncio
    async def test_empty_corpus(self):
        async def dummy(text: str) -> str:
            return "accumulate"

        metrics = await evaluate_strategy_classification([], dummy, sample_size=0)
        assert metrics["total"] == 0
        assert metrics["accuracy"] == 0.0

    @pytest.mark.asyncio
    async def test_filters_unmapped_strategies(self):
        corpus_with_none = MOCK_CORPUS + [
            _make_session("7", "Some text", None),  # type: ignore[arg-type]
        ]

        async def dummy(text: str) -> str:
            return "accumulate"

        metrics = await evaluate_strategy_classification(
            corpus_with_none, dummy, sample_size=0
        )
        # Should only evaluate the 6 sessions with valid strategies
        assert metrics["total"] == 6

    @pytest.mark.asyncio
    async def test_sample_size_limits(self):
        async def dummy(text: str) -> str:
            return "accumulate"

        metrics = await evaluate_strategy_classification(
            MOCK_CORPUS, dummy, sample_size=3
        )
        assert metrics["total"] == 3


class TestFormatReport:
    def test_format_produces_string(self):
        metrics = {
            "accuracy": 0.75,
            "per_class": {
                "accumulate": {"precision": 1.0, "recall": 0.5, "f1": 0.67, "support": 2},
            },
            "confusion_matrix": {},
            "total": 4,
            "errors": 0,
        }
        report = format_report(metrics)
        assert "75.0%" in report
        assert "accumulate" in report
