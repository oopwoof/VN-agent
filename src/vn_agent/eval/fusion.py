"""Rank fusion utilities for hybrid retrieval.

Combines multiple ranked result lists (e.g. FAISS vector + BM25 keyword) into
a single unified ranking via Reciprocal Rank Fusion (RRF).

Honest note on BM25 in this project:
    Our corpus is VN dialogue (lines like *"Good morning, you're early today."*).
    The strategy labels (Accumulate / Rupture / etc.) live in metadata, NOT in
    the dialogue text itself. So BM25 on dialogue tokens contributes less here
    than in entity-heavy retrieval tasks. We still include it because
    (a) it does help when queries contain specific character names or entities,
    and (b) multi-retriever fusion is a standard production pattern worth
    demonstrating. The low default weight (0.3) reflects the reality that
    FAISS is doing most of the work on this corpus.

Reference: Cormack et al. 2009, "Reciprocal Rank Fusion outperforms Condorcet
and individual Rank Learning Methods."
"""
from __future__ import annotations

from collections.abc import Sequence


def weighted_rrf(
    rankings: Sequence[tuple[list[int], float]],
    k: int = 60,
) -> list[int]:
    """Fuse multiple ranked lists with weighted Reciprocal Rank Fusion.

    Args:
        rankings: sequence of (ordered_indices, weight) tuples. Each
            `ordered_indices` is a list of corpus indices ranked best-first.
            Weights multiply the RRF contribution of each source.
        k: RRF constant. 60 is the canonical default from the RRF paper;
            larger k flattens the contribution of top ranks.

    Returns:
        Fused list of corpus indices, ordered by descending combined score.
        Indices that appear in any input list appear at most once in output.

    Formula (for each source s with weight w_s):
        score(doc) += w_s / (k + rank_s(doc) + 1)

    Example:
        fused = weighted_rrf([
            (faiss_top_indices, 0.7),
            (bm25_top_indices, 0.3),
        ], k=60)
    """
    scores: dict[int, float] = {}
    for indices, weight in rankings:
        if weight == 0.0:
            continue
        for rank, idx in enumerate(indices):
            scores[idx] = scores.get(idx, 0.0) + weight / (k + rank + 1)
    return sorted(scores.keys(), key=lambda i: scores[i], reverse=True)


def simple_tokenize(text: str) -> list[str]:
    """Lowercase whitespace tokenizer suitable for BM25 over VN dialogue.

    Not language-aware — strips punctuation heuristically. Good enough for
    English-dominated corpora. Chinese/Japanese would need a better tokenizer,
    but the default sentence-transformer model we use handles CJK semantically.
    """
    import re

    # Keep word chars and hyphens; drop everything else
    cleaned = re.sub(r"[^\w\-]+", " ", text.lower())
    return [t for t in cleaned.split() if t]
