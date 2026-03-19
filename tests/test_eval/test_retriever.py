"""Tests for few-shot example retriever."""
from __future__ import annotations

from vn_agent.eval.corpus import AnnotatedSession
from vn_agent.eval.retriever import format_examples, retrieve_examples


def _make(id: str, strategy: str, text: str = "sample text") -> AnnotatedSession:
    return AnnotatedSession(id=id, title=f"S{id}", text=text, strategy=strategy)


CORPUS = [
    _make("1", "accumulate", "Gradual buildup"),
    _make("2", "accumulate", "Slow layer upon layer"),
    _make("3", "accumulate", "Third accumulate example"),
    _make("4", "erode", "Doubt creeps in"),
    _make("5", "rupture", "Sudden break"),
    _make("6", "reveal", "Hidden truth emerges"),
]


class TestRetrieveExamples:
    def test_returns_correct_strategy(self):
        results = retrieve_examples(CORPUS, "accumulate", k=2)
        assert len(results) == 2
        assert all(r.strategy == "accumulate" for r in results)

    def test_k_parameter_respected(self):
        results = retrieve_examples(CORPUS, "accumulate", k=1)
        assert len(results) == 1

    def test_pads_when_insufficient_matches(self):
        # Only 1 erode example, k=2 should pad from others
        results = retrieve_examples(CORPUS, "erode", k=2)
        assert len(results) == 2
        assert results[0].strategy == "erode"

    def test_returns_empty_for_no_corpus(self):
        results = retrieve_examples([], "accumulate", k=2)
        assert len(results) == 0


class TestFormatExamples:
    def test_formats_with_pacing(self):
        ex = AnnotatedSession(
            id="1", title="Test", text="Sample dialogue", strategy="accumulate", pacing="slow"
        )
        output = format_examples([ex])
        assert "Example 1" in output
        assert "accumulate" in output
        assert "pacing: slow" in output
        assert "Sample dialogue" in output

    def test_empty_list(self):
        assert format_examples([]) == ""

    def test_multiple_examples(self):
        exs = [
            AnnotatedSession(id="1", title="T1", text="Text1", strategy="accumulate"),
            AnnotatedSession(id="2", title="T2", text="Text2", strategy="erode"),
        ]
        output = format_examples(exs)
        assert "Example 1" in output
        assert "Example 2" in output
