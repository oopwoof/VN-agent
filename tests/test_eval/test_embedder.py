"""Tests for the embedding-based RAG index."""
from __future__ import annotations

import pytest

from vn_agent.eval.corpus import AnnotatedSession

# Skip entire module if sentence-transformers not installed
sbert = pytest.importorskip("sentence_transformers", reason="requires [rag] extras")


def _make_sessions() -> list[AnnotatedSession]:
    """Create a small test corpus with distinct strategy clusters."""
    return [
        AnnotatedSession(
            id="s1", title="Trust Building",
            text="They sat together sharing stories, slowly building trust over cups of tea.",
            strategy="accumulate", pivot_line_idx=None, pacing="slow",
        ),
        AnnotatedSession(
            id="s2", title="Growing Bond",
            text="Each day they grew closer, layering shared memories one by one.",
            strategy="accumulate", pivot_line_idx=None, pacing="medium",
        ),
        AnnotatedSession(
            id="s3", title="Sudden Betrayal",
            text="Without warning he turned, shattering the fragile alliance in an instant.",
            strategy="rupture", pivot_line_idx=3, pacing="fast",
        ),
        AnnotatedSession(
            id="s4", title="Hidden Truth",
            text="She discovered the secret letter hidden beneath the floorboards.",
            strategy="reveal", pivot_line_idx=5, pacing="medium",
        ),
        AnnotatedSession(
            id="s5", title="Crumbling Faith",
            text="Doubt crept in as promises faded, slowly wearing away their bond.",
            strategy="erode", pivot_line_idx=None, pacing="slow",
        ),
    ]


@pytest.fixture
def corpus():
    return _make_sessions()


class TestEmbeddingIndex:
    def test_build_and_size(self, corpus):
        from vn_agent.eval.embedder import EmbeddingIndex

        index = EmbeddingIndex()
        index.build(corpus)
        assert index.size == 5

    def test_search_returns_k_results(self, corpus):
        from vn_agent.eval.embedder import EmbeddingIndex

        index = EmbeddingIndex()
        index.build(corpus)
        results = index.search("building trust slowly", k=2)
        assert len(results) == 2
        assert all(isinstance(r, AnnotatedSession) for r in results)

    def test_semantic_relevance(self, corpus):
        """Accumulate-themed query should rank accumulate sessions higher."""
        from vn_agent.eval.embedder import EmbeddingIndex

        index = EmbeddingIndex()
        index.build(corpus)
        results = index.search("gradually building a relationship over time", k=3)
        strategies = [r.strategy for r in results]
        # At least one accumulate result in top 3
        assert "accumulate" in strategies

    def test_strategy_filter_boosts(self, corpus):
        """Strategy filter should prefer matching sessions."""
        from vn_agent.eval.embedder import EmbeddingIndex

        index = EmbeddingIndex()
        index.build(corpus)
        results = index.search("something happened", k=2, strategy="rupture")
        # Rupture session should appear
        assert any(r.strategy == "rupture" for r in results)

    def test_pre_filter_hard_constraint(self, corpus):
        """Pre-filter should return ONLY matched strategy when subset is large enough."""
        from vn_agent.eval.embedder import EmbeddingIndex

        # Add more accumulate samples so subset >= 2*k
        big_corpus = corpus + [
            AnnotatedSession(
                id=f"s_extra_{i}", title=f"Extra {i}",
                text=f"Slowly building tension layer {i} through careful moments.",
                strategy="accumulate", pivot_line_idx=None, pacing="slow",
            )
            for i in range(4)
        ]

        index = EmbeddingIndex()
        index.build(big_corpus)
        # k=2 so subset >= 4 required for pure pre-filter
        results = index.search(
            "a character slowly changes", k=2,
            strategy="accumulate", pre_filter_strategy=True,
        )
        # All top-k should be accumulate — no leak from others
        assert len(results) == 2
        assert all(r.strategy == "accumulate" for r in results)

    def test_pre_filter_soft_degradation(self, corpus):
        """Pre-filter should backfill with others when matched subset is small."""
        from vn_agent.eval.embedder import EmbeddingIndex

        index = EmbeddingIndex()
        index.build(corpus)
        # Only 1 "rupture" sample in corpus, k=3 → must backfill
        results = index.search(
            "any content", k=3,
            strategy="rupture", pre_filter_strategy=True,
        )
        assert len(results) == 3
        # At least the one rupture sample is present
        assert any(r.strategy == "rupture" for r in results)

    def test_pre_filter_vs_post_filter(self, corpus):
        """pre_filter=False should fall back to legacy post-filter behavior."""
        from vn_agent.eval.embedder import EmbeddingIndex

        index = EmbeddingIndex()
        index.build(corpus)
        # Both modes should return something for a valid query
        pre = index.search("test", k=2, strategy="reveal", pre_filter_strategy=True)
        post = index.search("test", k=2, strategy="reveal", pre_filter_strategy=False)
        assert len(pre) == 2
        assert len(post) == 2

    def test_search_empty_index(self):
        from vn_agent.eval.embedder import EmbeddingIndex

        index = EmbeddingIndex()
        index.build([])
        assert index.search("query") == []

    def test_search_k_larger_than_corpus(self, corpus):
        from vn_agent.eval.embedder import EmbeddingIndex

        index = EmbeddingIndex()
        index.build(corpus)
        results = index.search("test", k=100)
        assert len(results) == 5  # returns all available

    def test_save_and_load(self, corpus, tmp_path):
        from vn_agent.eval.embedder import EmbeddingIndex

        index = EmbeddingIndex()
        index.build(corpus)

        save_dir = tmp_path / "test_index"
        index.save(save_dir)

        loaded = EmbeddingIndex.load(save_dir)
        assert loaded.size == 5

        # Loaded index should return same results
        r1 = index.search("building trust", k=2)
        r2 = loaded.search("building trust", k=2)
        assert [r.id for r in r1] == [r.id for r in r2]

    def test_load_missing_path_raises(self, tmp_path):
        from vn_agent.eval.embedder import EmbeddingIndex

        with pytest.raises(FileNotFoundError):
            EmbeddingIndex.load(tmp_path / "nonexistent")
