"""Tests for weighted RRF fusion."""
from vn_agent.eval.fusion import simple_tokenize, weighted_rrf


class TestWeightedRRF:
    def test_single_source_preserves_order(self):
        result = weighted_rrf([([3, 1, 2], 1.0)])
        assert result == [3, 1, 2]

    def test_agreement_boosts_shared_docs(self):
        """Docs that appear in both rankings should rise above disagreeing ones."""
        faiss_ranks = [1, 2, 3]
        bm25_ranks = [2, 1, 4]  # 1 and 2 in both; 3 vs 4 diverges
        result = weighted_rrf([(faiss_ranks, 0.5), (bm25_ranks, 0.5)])
        # 1 and 2 should be at the top (both sources agree)
        assert set(result[:2]) == {1, 2}

    def test_weight_affects_contribution(self):
        """Heavier weight should make that source dominate."""
        high = [10, 11, 12]
        low = [99, 98, 97]
        # If FAISS weight is 0.99 and BM25 weight is 0.01, top result must be 10
        result = weighted_rrf([(high, 0.99), (low, 0.01)])
        assert result[0] == 10

    def test_zero_weight_ignored(self):
        result = weighted_rrf([
            ([1, 2, 3], 1.0),
            ([99, 98, 97], 0.0),
        ])
        assert result == [1, 2, 3]

    def test_empty_inputs(self):
        assert weighted_rrf([]) == []
        assert weighted_rrf([([], 1.0)]) == []

    def test_returns_unique_indices(self):
        result = weighted_rrf([
            ([1, 2, 3], 0.5),
            ([3, 2, 1], 0.5),
        ])
        assert sorted(result) == [1, 2, 3]


class TestSimpleTokenize:
    def test_lowercases(self):
        assert simple_tokenize("Hello World") == ["hello", "world"]

    def test_strips_punctuation(self):
        assert simple_tokenize("Hello, world!") == ["hello", "world"]

    def test_keeps_hyphens(self):
        tokens = simple_tokenize("state-of-the-art")
        assert "state-of-the-art" in tokens

    def test_empty_string(self):
        assert simple_tokenize("") == []

    def test_only_punctuation(self):
        assert simple_tokenize("!!! ???") == []
