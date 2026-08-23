"""Token usage accumulator and cost estimator.

Per-job isolation via ContextVar: each pipeline run sets its own tracker in
the current async context so concurrent jobs do not pollute each other. The
module-level `tracker` remains as a fallback for CLI one-shot usage and
backwards compatibility with existing callers that never set a context.

Usage inside pipeline:
    from vn_agent.services.token_tracker import TokenTracker, current_tracker
    job_tracker = TokenTracker()
    token = current_tracker.set(job_tracker)
    try:
        await run_pipeline(...)
        usage = job_tracker.summary_dict()
    finally:
        current_tracker.reset(token)
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Approximate costs per 1M tokens (USD) — updated for common models
_COST_PER_M = {
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    # Haiku 4.5 is $1/$5 per MTok. This row carried 3.5-Haiku's $0.80/$4.00
    # until 2026-08-24, under-reporting every Haiku call (summarizer, chapter
    # rollup, intent router, explain) by 20% — tolerable while the number was
    # only printed, and not once the budget watchdog started acting on it.
    "claude-haiku-4-5-20251001": {"in": 1.0, "out": 5.0},
    "gpt-4o": {"in": 2.5, "out": 10.0},
    "gpt-4o-mini": {"in": 0.15, "out": 0.6},
}


@dataclass
class _Call:
    caller: str
    model: str
    input_tokens: int
    output_tokens: int
    # Phase 13-3 M0 follow-up: Anthropic returns cache_read_input_tokens
    # (cache hits, billed at ~10% of base) and cache_creation_input_tokens
    # (cache writes, billed at ~125% of base). Tracking these lets us
    # surface cache_read_ratio = cache_read / total_input, which is THE
    # signal for whether prompt-caching is actually paying off on long
    # runs (50-scene north star expects ≥50%). Without them the smoke
    # harness logged "cache_read_ratio: ?" forever.
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class TokenTracker:
    def __init__(self):
        self.calls: list[_Call] = []

    def add(
        self,
        caller: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        *,
        cache_read_input_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
    ) -> None:
        """Record one LLM call. Cache token kwargs are optional so existing
        callers (and non-Anthropic providers) keep working unchanged.

        Anthropic note: ``input_tokens`` is the *uncached* input portion.
        Total input billed = input_tokens + cache_read + cache_creation.
        Cost-wise, the cache discount is captured by tracking the three
        buckets separately so a Sonnet call with mostly cache hits costs
        a fraction of a fresh call of the same prompt size.
        """
        self.calls.append(_Call(
            caller=caller,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
        ))

    def total_input(self) -> int:
        """Total uncached input tokens. Use ``total_input_with_cache`` for
        the billed-input total (uncached + cache_read + cache_creation)."""
        return sum(c.input_tokens for c in self.calls)

    def total_output(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    def total_cache_read_input(self) -> int:
        return sum(c.cache_read_input_tokens for c in self.calls)

    def total_cache_creation_input(self) -> int:
        return sum(c.cache_creation_input_tokens for c in self.calls)

    def total_input_with_cache(self) -> int:
        """Sum of all input-side tokens (uncached + cache_read + cache_creation).
        Matches Anthropic's billed-input total for cost reconciliation."""
        return (
            self.total_input()
            + self.total_cache_read_input()
            + self.total_cache_creation_input()
        )

    def cache_read_ratio(self) -> float:
        """Fraction of total input tokens served from prompt cache.

        Returns ``cache_read / total_input_with_cache`` as a float in [0, 1].
        Returns 0.0 when there have been no input tokens at all (e.g. a
        tracker that only saw failed calls). The 50-scene north-star target
        is ≥0.5 once Writer prompt caching kicks in past scene ~10.
        """
        denom = self.total_input_with_cache()
        if denom <= 0:
            return 0.0
        return self.total_cache_read_input() / denom

    def estimated_cost(self) -> float:
        """Estimate total cost in USD based on known model pricing.

        Phase 13-3 M0 follow-up: cache_read input is billed at ~10% of
        base input, cache_creation at ~125%. When cache token counts are
        zero (non-Anthropic providers, or Anthropic calls without
        cache_control), this falls back to plain in/out pricing — same
        behavior as before.
        """
        total = 0.0
        for c in self.calls:
            rates = _COST_PER_M.get(c.model, {"in": 3.0, "out": 15.0})
            total += c.input_tokens * rates["in"] / 1_000_000
            total += c.output_tokens * rates["out"] / 1_000_000
            # Anthropic cache pricing per 2025 docs: read ~0.1×, write ~1.25×.
            total += c.cache_read_input_tokens * rates["in"] * 0.1 / 1_000_000
            total += c.cache_creation_input_tokens * rates["in"] * 1.25 / 1_000_000
        return total

    def summary(self) -> str:
        if not self.calls:
            return "No LLM calls recorded."

        total_in = self.total_input()
        total_out = self.total_output()
        cost = self.estimated_cost()

        # Per-model breakdown
        by_model: dict[str, dict[str, int]] = {}
        for c in self.calls:
            m = by_model.setdefault(c.model, {"in": 0, "out": 0, "calls": 0})
            m["in"] += c.input_tokens
            m["out"] += c.output_tokens
            m["calls"] += 1

        lines = [
            f"Token Usage Summary ({len(self.calls)} LLM calls)",
            f"  Total: {total_in:,} input + {total_out:,} output = {total_in + total_out:,} tokens",
            f"  Estimated cost: ${cost:.4f}",
        ]
        for model, stats in by_model.items():
            lines.append(f"  {model}: {stats['calls']} calls, {stats['in']:,} in + {stats['out']:,} out")

        return "\n".join(lines)

    def summary_dict(self) -> dict:
        """JSON-serializable usage summary (suitable for blackboard storage)."""
        by_model: dict[str, dict[str, int]] = {}
        for c in self.calls:
            m = by_model.setdefault(
                c.model,
                {"in": 0, "out": 0, "cache_read": 0, "cache_create": 0, "calls": 0},
            )
            m["in"] += c.input_tokens
            m["out"] += c.output_tokens
            m["cache_read"] += c.cache_read_input_tokens
            m["cache_create"] += c.cache_creation_input_tokens
            m["calls"] += 1
        return {
            "total_input": self.total_input(),
            "total_output": self.total_output(),
            "total_cache_read_input": self.total_cache_read_input(),
            "total_cache_creation_input": self.total_cache_creation_input(),
            "cache_read_ratio": round(self.cache_read_ratio(), 4),
            "estimated_cost_usd": round(self.estimated_cost(), 4),
            "calls": len(self.calls),
            "by_model": by_model,
        }

    def reset(self) -> None:
        """Clear all recorded calls (useful for reusing a tracker instance)."""
        self.calls.clear()


# Module-level singleton — fallback for CLI one-shot usage and backwards
# compatibility. In server/pipeline contexts, prefer the per-job tracker
# via `current_tracker`.
tracker = TokenTracker()

# Per-job tracker injected via ContextVar. Async-safe and isolated
# across concurrent pipeline runs in the same process.
current_tracker: ContextVar[TokenTracker] = ContextVar("current_tracker", default=tracker)


def get_active_tracker() -> TokenTracker:
    """Return the active tracker for this async context (falls back to global)."""
    return current_tracker.get()
