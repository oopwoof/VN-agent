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

_DEFAULT_MODEL = "all-MiniLM-L6-v2"


class EmbeddingIndex:
    """Semantic search index over annotated corpus sessions.

    Build once, search many times. Supports optional persistence.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL):
        if not _HAS_SBERT:
            raise ImportError(
                "sentence-transformers is required for embedding RAG. "
                "Install with: uv sync --extra rag"
            )
        self._model_name = model_name
        self._model = SentenceTransformer(model_name)
        self._embeddings: np.ndarray | None = None
        self._faiss_index: object | None = None  # faiss.IndexFlatIP
        self._sessions: list[AnnotatedSession] = []

    @property
    def size(self) -> int:
        return len(self._sessions)

    def build(self, corpus: list[AnnotatedSession]) -> None:
        """Encode all corpus texts and build the search index."""
        if not corpus:
            return
        texts = [s.text for s in corpus]
        self._embeddings = self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False,
        )
        self._sessions = list(corpus)

        if _HAS_FAISS:
            dim = self._embeddings.shape[1]
            self._faiss_index = faiss.IndexFlatIP(dim)
            self._faiss_index.add(self._embeddings)
            logger.debug(f"Built FAISS index: {len(corpus)} vectors, dim={dim}")
        else:
            logger.debug(f"Built numpy index: {len(corpus)} vectors (FAISS not available)")

    def search(
        self,
        query: str,
        k: int = 3,
        strategy: str | None = None,
    ) -> list[AnnotatedSession]:
        """Find the k most semantically similar sessions to the query.

        Args:
            query: search text (e.g. scene description)
            k: number of results
            strategy: optional filter — prefer results matching this strategy
        """
        if not self._sessions or self._embeddings is None:
            return []

        q_emb = self._model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False,
        )

        # Over-retrieve to allow for strategy filtering
        fetch_k = min(k * 5, len(self._sessions))

        if _HAS_FAISS and self._faiss_index is not None:
            scores, indices = self._faiss_index.search(q_emb, fetch_k)
            candidates = [
                (self._sessions[idx], float(scores[0][i]))
                for i, idx in enumerate(indices[0])
                if idx >= 0
            ]
        else:
            # Numpy fallback: brute-force cosine similarity
            sims = np.dot(self._embeddings, q_emb.T).flatten()
            top_indices = np.argsort(sims)[::-1][:fetch_k]
            candidates = [(self._sessions[i], float(sims[i])) for i in top_indices]

        # Strategy-aware ranking: boost matching strategy results
        if strategy:
            matched = [(s, sc) for s, sc in candidates if s.strategy == strategy]
            others = [(s, sc) for s, sc in candidates if s.strategy != strategy]
            ranked = matched + others
        else:
            ranked = candidates

        return [s for s, _ in ranked[:k]]

    def save(self, path: Path) -> None:
        """Persist index to disk (embeddings + metadata)."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        np.save(str(path / "embeddings.npy"), self._embeddings)

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

        logger.info(f"Loaded embedding index from {path} ({len(idx._sessions)} vectors)")
        return idx
