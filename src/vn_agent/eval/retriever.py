"""Few-shot example retriever: selects corpus examples by strategy for Writer prompt injection.

Supports two retrieval modes:
1. Label-based: filter by strategy label (default, no extra deps)
2. Semantic: embedding similarity search via EmbeddingIndex (requires [rag] extras)
"""
from __future__ import annotations

import logging
import random

from vn_agent.eval.corpus import AnnotatedSession

logger = logging.getLogger(__name__)


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


def retrieve_examples_semantic(
    index: object,  # EmbeddingIndex (avoid import for optional dep)
    query: str,
    strategy: str = "",
    k: int = 2,
    pre_filter_strategy: bool = True,
) -> list[AnnotatedSession]:
    """Retrieve examples using embedding similarity search.

    Args:
        index: An EmbeddingIndex instance
        query: scene description or other text to match against
        strategy: optional strategy label to constrain retrieval
        k: number of examples to return
        pre_filter_strategy: when True (default), strategy acts as a hard
            constraint — only matched sessions are vector-ranked, with soft
            backfill from others only when the matched subset is too small.
            When False, uses legacy post-filter reranking.
    """
    return index.search(  # type: ignore[attr-defined]
        query=query, k=k, strategy=strategy or None,
        pre_filter_strategy=pre_filter_strategy,
    )


def format_examples(examples: list[AnnotatedSession], max_chars: int = 2000) -> str:
    """Format retrieved examples as a text block for prompt injection.

    Each corpus session is a 12-line VN dialogue whose annotated pivot
    (where the strategy mechanism lands) sits at lines 3-10 — median text
    length ≈ 754 chars, p95 ≈ 1,296. An earlier 300-char cap sliced every
    single example mid-setup, **before** the pivot, so Writer was learning
    style from the opening beats but never seeing how the strategy
    actually resolves. Cap is now generous enough (2,000 chars ≈ p99) to
    include the full session for nearly all entries, and the pacing tag +
    pivot_line_idx are exposed so Writer sees *where* the mechanism lands.
    """
    if not examples:
        return ""

    blocks = []
    for i, ex in enumerate(examples, 1):
        pacing_info = f", pacing: {ex.pacing}" if ex.pacing else ""
        pivot_info = (
            f", pivot@line{ex.pivot_line_idx}"
            if ex.pivot_line_idx is not None
            else ""
        )
        text = ex.text[:max_chars]
        if len(ex.text) > max_chars:
            text += "…"
        blocks.append(
            f"Example {i} [{ex.strategy}{pacing_info}{pivot_info}]:\n"
            f'"{text}"'
        )
    return "\n\n".join(blocks)
