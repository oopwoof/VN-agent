"""Tests for token usage tracker and cost estimator."""
import asyncio

from vn_agent.services.token_tracker import (
    TokenTracker,
    current_tracker,
    get_active_tracker,
)


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
    # Haiku 4.5: $1/MTok in, $5/MTok out. (Pinned at 3.5-Haiku's $0.80/$4.00
    # until 2026-08-24 — a 20% under-report the budget watchdog now acts on.)
    t.add("test", "claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    assert t.estimated_cost() == 1.0 + 5.0


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


def test_summary_dict_shape():
    t = TokenTracker()
    t.add("director", "claude-sonnet-4-6", 500, 200)
    t.add("reviewer", "claude-haiku-4-5-20251001", 300, 100)
    d = t.summary_dict()
    assert d["total_input"] == 800
    assert d["total_output"] == 300
    assert d["calls"] == 2
    assert d["estimated_cost_usd"] > 0
    assert "claude-sonnet-4-6" in d["by_model"]
    assert d["by_model"]["claude-sonnet-4-6"]["calls"] == 1


def test_reset_clears_calls():
    t = TokenTracker()
    t.add("x", "claude-haiku-4-5-20251001", 100, 50)
    assert t.total_input() == 100
    t.reset()
    assert t.total_input() == 0
    assert t.calls == []


def test_context_var_isolation():
    """Two trackers in the same event loop should not leak into each other."""
    results: dict[str, int] = {}

    async def run_with_tracker(name: str, input_tok: int) -> None:
        t = TokenTracker()
        token = current_tracker.set(t)
        try:
            # Simulate LLM calls via get_active_tracker()
            get_active_tracker().add(name, "claude-haiku-4-5-20251001", input_tok, 10)
            await asyncio.sleep(0.01)  # yield control so jobs interleave
            get_active_tracker().add(name, "claude-haiku-4-5-20251001", input_tok, 10)
            results[name] = t.total_input()
        finally:
            current_tracker.reset(token)

    async def main() -> None:
        await asyncio.gather(
            run_with_tracker("job_a", 100),
            run_with_tracker("job_b", 200),
        )

    asyncio.run(main())
    assert results["job_a"] == 200  # 2 calls × 100 in, not mixed with job_b
    assert results["job_b"] == 400  # 2 calls × 200 in, not mixed with job_a


def test_get_active_tracker_default_is_global():
    """Outside of any ContextVar set, get_active_tracker returns global fallback."""
    from vn_agent.services.token_tracker import tracker as global_tracker

    active = get_active_tracker()
    assert active is global_tracker


# ---------------------------------------------------------------------------
# Phase 13-3 M0 follow-up: cache token tracking + cache_read_ratio
# ---------------------------------------------------------------------------


class TestCacheTokenTracking:
    """The 2026-04-26 M0 sanity smoke caught smoke_longvn.py guarding writes
    of total_cost_usd / cache_read_ratio behind hasattr() checks against
    method names that never existed (total_cost_usd, cache_read_ratio).
    Both fields silently dropped from run_metrics.json. Fix: rename the
    cost call to estimated_cost() AND add cache_read_ratio as a real
    method backed by Anthropic's cache_read_input_tokens usage bucket.
    """

    def test_add_with_cache_kwargs_records_buckets(self):
        t = TokenTracker()
        t.add(
            "writer", "claude-sonnet-4-6",
            input_tokens=100, output_tokens=50,
            cache_read_input_tokens=2000,
            cache_creation_input_tokens=500,
        )
        assert t.total_input() == 100  # uncached only
        assert t.total_cache_read_input() == 2000
        assert t.total_cache_creation_input() == 500
        assert t.total_input_with_cache() == 100 + 2000 + 500

    def test_add_without_cache_kwargs_defaults_to_zero(self):
        # Backwards-compat: existing callers passing only positional args
        # should still work with cache buckets defaulting to 0.
        t = TokenTracker()
        t.add("director", "claude-sonnet-4-6", 1000, 500)
        assert t.total_cache_read_input() == 0
        assert t.total_cache_creation_input() == 0
        assert t.total_input_with_cache() == 1000

    def test_cache_read_ratio_zero_on_empty_tracker(self):
        assert TokenTracker().cache_read_ratio() == 0.0

    def test_cache_read_ratio_zero_when_no_cache_hits(self):
        t = TokenTracker()
        t.add("director", "claude-sonnet-4-6", 1000, 500)
        assert t.cache_read_ratio() == 0.0

    def test_cache_read_ratio_full_hit(self):
        t = TokenTracker()
        # All input came from cache_read — ratio should be 1.0.
        t.add(
            "writer", "claude-sonnet-4-6",
            input_tokens=0, output_tokens=100,
            cache_read_input_tokens=5000,
        )
        assert t.cache_read_ratio() == 1.0

    def test_cache_read_ratio_mixed(self):
        t = TokenTracker()
        # 30% of total input was cache_read.
        t.add(
            "writer", "claude-sonnet-4-6",
            input_tokens=700, output_tokens=200,
            cache_read_input_tokens=300,
        )
        assert abs(t.cache_read_ratio() - 0.3) < 1e-9

    def test_estimated_cost_applies_anthropic_cache_pricing(self):
        # cache_read billed at ~10% of base input; cache_creation at ~125%.
        # Verify both are added on top of plain input/output cost.
        t = TokenTracker()
        t.add(
            "writer", "claude-sonnet-4-6",
            input_tokens=1_000_000, output_tokens=0,
            cache_read_input_tokens=1_000_000,
            cache_creation_input_tokens=1_000_000,
        )
        # base in: 1M × $3/M = $3.0
        # cache read: 1M × $3/M × 0.1 = $0.3
        # cache create: 1M × $3/M × 1.25 = $3.75
        # output: 0
        assert abs(t.estimated_cost() - (3.0 + 0.3 + 3.75)) < 1e-9

    def test_summary_dict_includes_cache_fields(self):
        t = TokenTracker()
        t.add(
            "writer", "claude-sonnet-4-6",
            input_tokens=1000, output_tokens=500,
            cache_read_input_tokens=2000,
            cache_creation_input_tokens=200,
        )
        d = t.summary_dict()
        assert d["total_cache_read_input"] == 2000
        assert d["total_cache_creation_input"] == 200
        # cache_read / (1000 + 2000 + 200) ≈ 0.625
        assert abs(d["cache_read_ratio"] - 2000 / 3200) < 1e-3
        # by_model breakdown also surfaces the new buckets.
        m = d["by_model"]["claude-sonnet-4-6"]
        assert m["cache_read"] == 2000
        assert m["cache_create"] == 200
