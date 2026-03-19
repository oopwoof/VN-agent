"""Token usage accumulator and cost estimator."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Approximate costs per 1M tokens (USD) — updated for common models
_COST_PER_M = {
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "claude-haiku-4-5-20251001": {"in": 0.80, "out": 4.0},
    "gpt-4o": {"in": 2.5, "out": 10.0},
    "gpt-4o-mini": {"in": 0.15, "out": 0.6},
}


@dataclass
class _Call:
    caller: str
    model: str
    input_tokens: int
    output_tokens: int


class TokenTracker:
    def __init__(self):
        self.calls: list[_Call] = []

    def add(self, caller: str, model: str, input_tokens: int, output_tokens: int) -> None:
        self.calls.append(_Call(caller=caller, model=model, input_tokens=input_tokens, output_tokens=output_tokens))

    def total_input(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    def total_output(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    def estimated_cost(self) -> float:
        """Estimate total cost in USD based on known model pricing."""
        total = 0.0
        for c in self.calls:
            rates = _COST_PER_M.get(c.model, {"in": 3.0, "out": 15.0})
            total += c.input_tokens * rates["in"] / 1_000_000
            total += c.output_tokens * rates["out"] / 1_000_000
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


# Module-level singleton
tracker = TokenTracker()
