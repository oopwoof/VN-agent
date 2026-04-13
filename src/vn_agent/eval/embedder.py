"""Embedding-based semantic index for corpus retrieval (RAG).

Uses sentence-transformers for encoding and FAISS for fast similarity search.
Falls back to numpy brute-force cosine similarity when FAISS is unavailable.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from vn_agent.eval.corpus import AnnotatedSession

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer

    _HAS_SBERT = True
except ImportError:
    _HAS_SBERT = False

try:
    import faiss

    _HAS_FAISS = True
except ImportError:
    _HAS_FAISS = False

try:
    from rank_bm25 import BM25Okapi

    _HAS_BM25 = True
except ImportError:
    _HAS_BM25 = False

_DEFAULT_MODEL = "all-MiniLM-L6-v2"

# BM25 fusion weights — see fusion.py docstring for why BM25 is under-weighted
# in this corpus. Override via EmbeddingIndex(rrf_weights=(0.6, 0.4)) if your
# queries carry more exact-match signal (character names, specific keywords).
_DEFAULT_FAISS_WEIGHT = 0.7
_DEFAULT_BM25_WEIGHT = 0.3


class EmbeddingIndex:
    """Semantic search index over annotated corpus sessions.

    Build once, search many times. Supports optional persistence.
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        rrf_weights: tuple[float, float] = (_DEFAULT_FAISS_WEIGHT, _DEFAULT_BM25_WEIGHT),
    ):
        if not _HAS_SBERT:
            raise ImportError(
                "sentence-transformers is required for embedding RAG. "
                "Install with: uv sync --extra rag"
            )
        self._model_name = model_name
        self._model = SentenceTransformer(model_name)
        self._embeddings: np.ndarray | None = None
        self._faiss_index: object | None = None  # faiss.IndexFlatIP
        self._bm25: object | None = None  # BM25Okapi
        self._sessions: list[AnnotatedSession] = []
        self._rrf_weights = rrf_weights

    @property
    def size(self) -> int:
        return len(self._sessions)

    def build(self, corpus: list[AnnotatedSession]) -> None:
        """Encode all corpus texts and build both FAISS + BM25 indexes."""
        if not corpus:
            return
        texts = [s.text for s in corpus]
        self._embeddings = self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False,
        )
        self._sessions = list(corpus)

        if _HAS_FAISS:
            dim = self._embeddings.shape[1]
            self._faiss_index = faiss.IndexFlatIP(dim)  # type: ignore[union-attr]
            self._faiss_index.add(self._embeddings)  # type: ignore[union-attr]
            logger.debug(f"Built FAISS index: {len(corpus)} vectors, dim={dim}")
        else:
            logger.debug(f"Built numpy index: {len(corpus)} vectors (FAISS not available)")

        # Build BM25 index in parallel for hybrid retrieval
        if _HAS_BM25:
            from vn_agent.eval.fusion import simple_tokenize

            tokenized = [simple_tokenize(t) for t in texts]
            self._bm25 = BM25Okapi(tokenized)
            logger.debug(f"Built BM25 index: {len(corpus)} documents")
        else:
            logger.debug("BM25 not available — hybrid retrieval falls back to vector only")

    def search(
        self,
        query: str,
        k: int = 3,
        strategy: str | None = None,
        pre_filter_strategy: bool = True,
        hybrid: bool = True,
    ) -> list[AnnotatedSession]:
        """Find the k most relevant sessions to the query.

        Args:
            query: search text (e.g. scene description)
            k: number of results
            strategy: optional strategy constraint
            pre_filter_strategy: hard-constrain to strategy-matched subset
                before ranking. See class docs for soft-degradation rules.
            hybrid: when True and BM25 is available, fuse FAISS + BM25 rankings
                via weighted RRF (see fusion.py). When False, pure vector.
        """
        if not self._sessions or self._embeddings is None:
            return []

        q_emb = self._model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False,
        )

        if strategy and pre_filter_strategy:
            return self._search_pre_filter(q_emb, k, strategy, hybrid=hybrid, query=query)
        return self._search_post_filter(q_emb, k, strategy, hybrid=hybrid, query=query)

    def _search_pre_filter(
        self, q_emb: np.ndarray, k: int, strategy: str,
        hybrid: bool = True, query: str = "",
    ) -> list[AnnotatedSession]:
        """Strategy hard-constraint: rank within matched subset first."""
        matched_idx = [i for i, s in enumerate(self._sessions) if s.strategy == strategy]
        others_idx = [i for i, s in enumerate(self._sessions) if s.strategy != strategy]

        matched_ranked = self._rank_subset(q_emb, matched_idx, hybrid=hybrid, query=query)
        if len(matched_ranked) >= 2 * k:
            return [self._sessions[i] for i in matched_ranked[:k]]

        # Soft degradation: take all matched + backfill with top others
        result_indices = list(matched_ranked)
        need = k - len(result_indices)
        if need > 0 and others_idx:
            others_ranked = self._rank_subset(q_emb, others_idx, hybrid=hybrid, query=query)
            result_indices.extend(others_ranked[:need])
        return [self._sessions[i] for i in result_indices[:k]]

    def _search_post_filter(
        self, q_emb: np.ndarray, k: int, strategy: str | None,
        hybrid: bool = True, query: str = "",
    ) -> list[AnnotatedSession]:
        """Legacy behavior: rank full index, then bubble strategy-matched up."""
        fetch_k = min(k * 5, len(self._sessions))
        all_idx = list(range(len(self._sessions)))
        ranked_indices = self._rank_subset(q_emb, all_idx, hybrid=hybrid, query=query)[:fetch_k]
        candidates = [self._sessions[i] for i in ranked_indices]

        if strategy:
            matched = [s for s in candidates if s.strategy == strategy]
            others = [s for s in candidates if s.strategy != strategy]
            ranked = matched + others
        else:
            ranked = candidates

        return ranked[:k]

    def _vector_rank(
        self, q_emb: np.ndarray, subset_idx: list[int],
    ) -> list[tuple[int, float]]:
        """Rank a subset by FAISS-style cosine similarity against query.

        Uses numpy on the subset directly — FAISS doesn't support searching
        an arbitrary index subset without rebuilding, and numpy is fast enough
        for subsets (O(|subset| * dim)).
        """
        if not subset_idx or self._embeddings is None:
            return []
        subset_emb = self._embeddings[subset_idx]  # type: ignore[index]
        sims = np.dot(subset_emb, q_emb.T).flatten()
        order = np.argsort(sims)[::-1]
        return [(subset_idx[int(j)], float(sims[int(j)])) for j in order]

    def _bm25_rank(self, query: str, subset_idx: list[int]) -> list[int]:
        """Rank a subset by BM25 score on the query. Empty list if unavailable."""
        if not _HAS_BM25 or self._bm25 is None or not subset_idx or not query.strip():
            return []
        from vn_agent.eval.fusion import simple_tokenize

        tokens = simple_tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)  # type: ignore[attr-defined]
        # Restrict to subset and sort by score descending
        subset_scored = [(i, float(scores[i])) for i in subset_idx]
        subset_scored.sort(key=lambda pair: pair[1], reverse=True)
        return [i for i, _ in subset_scored]

    def _rank_subset(
        self,
        q_emb: np.ndarray,
        subset_idx: list[int],
        hybrid: bool = True,
        query: str = "",
    ) -> list[int]:
        """Return indices of subset ordered by relevance.

        If hybrid=True and BM25 available, fuses vector + BM25 rankings via
        weighted RRF. Otherwise falls back to pure vector.
        """
        vector_ranked = [i for i, _ in self._vector_rank(q_emb, subset_idx)]

        if not hybrid or not _HAS_BM25 or self._bm25 is None:
            return vector_ranked

        bm25_ranked = self._bm25_rank(query, subset_idx)
        if not bm25_ranked:
            return vector_ranked

        from vn_agent.eval.fusion import weighted_rrf

        faiss_w, bm25_w = self._rrf_weights
        fused = weighted_rrf(
            [(vector_ranked, faiss_w), (bm25_ranked, bm25_w)],
        )
        return fused

    def save(self, path: Path) -> None:
        """Persist index to disk (embeddings + metadata)."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        np.save(str(path / "embeddings.npy"), self._embeddings)  # type: ignore[arg-type]

        metadata = {
            "model_name": self._model_name,
            "sessions": [s.model_dump() for s in self._sessions],
        }
        (path / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8",
        )

        if _HAS_FAISS and self._faiss_index is not None:
            faiss.write_index(self._faiss_index, str(path / "index.faiss"))

        logger.info(f"Saved embedding index to {path} ({len(self._sessions)} vectors)")

    @classmethod
    def load(cls, path: Path) -> EmbeddingIndex:
        """Load a persisted index from disk."""
        path = Path(path)
        meta_path = path / "metadata.json"
        emb_path = path / "embeddings.npy"

        if not meta_path.exists() or not emb_path.exists():
            raise FileNotFoundError(f"Index files not found at {path}")

        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        model_name = metadata.get("model_name", _DEFAULT_MODEL)

        idx = cls(model_name=model_name)
        idx._embeddings = np.load(str(emb_path))
        idx._sessions = [AnnotatedSession(**s) for s in metadata["sessions"]]

        faiss_path = path / "index.faiss"
        if _HAS_FAISS and faiss_path.exists():
            idx._faiss_index = faiss.read_index(str(faiss_path))

        # Rebuild BM25 from session texts (fast, no serialization needed)
        if _HAS_BM25 and idx._sessions:
            from vn_agent.eval.fusion import simple_tokenize

            tokenized = [simple_tokenize(s.text) for s in idx._sessions]
            idx._bm25 = BM25Okapi(tokenized)

        logger.info(f"Loaded embedding index from {path} ({len(idx._sessions)} vectors)")
        return idx
