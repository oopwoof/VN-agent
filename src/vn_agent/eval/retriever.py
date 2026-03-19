"""Few-shot example retriever: selects corpus examples by strategy for Writer prompt injection."""
from __future__ import annotations

import random

from vn_agent.eval.corpus import AnnotatedSession


def retrieve_examples(
    corpus: list[AnnotatedSession],
    strategy: str,
    k: int = 2,
) -> list[AnnotatedSession]:
    """Return up to k examples from corpus matching the given strategy.

    Falls back to random examples if fewer than k matches exist.
    """
    matching = [s for s in corpus if s.strategy == strategy]

    if len(matching) >= k:
        return random.sample(matching, k)

    # Pad with random examples from other strategies
    remaining = [s for s in corpus if s.strategy and s not in matching]
    padding = random.sample(remaining, min(k - len(matching), len(remaining)))
    return matching + padding


def format_examples(examples: list[AnnotatedSession]) -> str:
    """Format retrieved examples as a text block for prompt injection."""
    if not examples:
        return ""

    blocks = []
    for i, ex in enumerate(examples, 1):
        pacing_info = f" (pacing: {ex.pacing})" if ex.pacing else ""
        blocks.append(
            f"Example {i} [{ex.strategy}{pacing_info}]:\n"
            f'"{ex.text[:300]}"'
        )
    return "\n\n".join(blocks)
