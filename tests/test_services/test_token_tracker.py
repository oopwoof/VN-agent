"""Tests for token usage tracker and cost estimator."""
from vn_agent.services.token_tracker import TokenTracker


def test_empty_tracker():
    t = TokenTracker()
    assert t.total_input() == 0
    assert t.total_output() == 0
    assert t.estimated_cost() == 0.0
    assert t.summary() == "No LLM calls recorded."


def test_add_and_totals():
    t = TokenTracker()
    t.add("director/step1", "claude-sonnet-4-6", 1000, 500)
    t.add("writer", "claude-sonnet-4-6", 2000, 800)
    assert t.total_input() == 3000
    assert t.total_output() == 1300


def test_estimated_cost_known_model():
    t = TokenTracker()
    # Sonnet: $3/MTok in, $15/MTok out
    t.add("test", "claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert t.estimated_cost() == 3.0 + 15.0


def test_estimated_cost_unknown_model():
    t = TokenTracker()
    # Unknown model falls back to Sonnet pricing
    t.add("test", "unknown-model", 1_000_000, 0)
    assert t.estimated_cost() == 3.0


def test_estimated_cost_haiku():
    t = TokenTracker()
    # Haiku: $0.80/MTok in, $4/MTok out
    t.add("test", "claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    assert t.estimated_cost() == 0.80 + 4.0


def test_summary_format():
    t = TokenTracker()
    t.add("director", "claude-sonnet-4-6", 500, 200)
    t.add("reviewer", "claude-haiku-4-5-20251001", 300, 100)
    s = t.summary()
    assert "2 LLM calls" in s
    assert "800" in s  # total input
    assert "300" in s  # total output
    assert "claude-sonnet" in s
    assert "claude-haiku" in s


def test_multi_model_breakdown():
    t = TokenTracker()
    t.add("a", "claude-sonnet-4-6", 100, 50)
    t.add("b", "claude-sonnet-4-6", 200, 100)
    t.add("c", "claude-haiku-4-5-20251001", 300, 150)
    s = t.summary()
    # Sonnet: 2 calls
    assert "2 calls" in s
    # Haiku: 1 call
    assert "1 calls" in s
