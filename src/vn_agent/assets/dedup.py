"""Cross-source deduplication for uploads + library + generated assets.

Design decisions:
- Two dedup axes: perceptual image hash (pHash) for images, embedding
  cosine for text. They share a single `AssetFingerprint` shape so the
  caller keeps one seen-set even though the internals differ.
- Deterministic + threshold-based. pHash uses Hamming distance ≤ 8 bits
  (imagehash default `hash_size=8` yields 64-bit hashes; ≤8 flips is ~87%
  match, tuned to catch resizes/reencodes without merging visually-distinct
  art). Text uses cosine ≥ 0.90 — high enough to merge near-duplicates
  ("The quiet village…" vs "The quiet village.") without collapsing
  semantically-close but distinct chunks.
- Graceful degrade. Missing `imagehash` → images unhashable but dedup
  still works on text; missing sentence-transformers → text falls back
  to normalized-string equality (catches exact reuploads at least).
- Stateless dedup helpers + a stateful DedupIndex. The former for tests
  and one-off checks; the latter for pipeline flow where we build up a
  seen-set as we ingest uploads / library assets / web-search results.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from vn_agent.eval.corpus import AnnotatedSession

logger = logging.getLogger(__name__)

# Perceptual hash: bit-flip budget on a 64-bit pHash. imagehash's own
# docs recommend ≤ 5 for "same image" and ≤ 10 for "same but resized";
# we go with 8 as a middle ground — resizes/reencodes merge, distinct
# art stays distinct in practice on our expected image mix (backgrounds
# + sprites, high visual variance).
_PHASH_HAMMING_THRESHOLD = 8

# Text cosine merge threshold. Deliberately high — this is a dedup gate,
# not a similarity gate. Anything below → keep both; anything above →
# treat as a repeat. Same-source (identical upload) trivially hits 1.0.
_TEXT_COSINE_THRESHOLD = 0.90


@dataclass(frozen=True)
class AssetFingerprint:
    """One asset's identity for dedup purposes."""
    kind: str                              # "image" | "text"
    key: str                               # hex phash or sha256 of normalized text
    # Original identifier so callers can trace merged/skipped assets back
    # to their source (upload_id, library asset id, url, ...).
    origin: str = ""


class DedupIndex:
    """Accumulating dedup set with per-job scope.

    Usage:
        idx = DedupIndex()
        for chunk in chunks:
            fp = idx.fingerprint_text(chunk.text, origin=chunk.id)
            if idx.register(fp):
                keep.append(chunk)
            else:
                skipped.append(chunk)
    """

    def __init__(self):
        self._image_hashes: list[tuple[int, str]] = []   # (hash_as_int, origin)
        self._text_keys: dict[str, str] = {}             # sha256 → origin
        self._text_embeddings: list[tuple[list[float], str]] = []  # (vec, origin)
        self._skipped: list[tuple[AssetFingerprint, str]] = []  # (dup fp, matched origin)

    # ------------------------------------------------------------------
    # Fingerprinting
    # ------------------------------------------------------------------

    def fingerprint_image(self, path: Path | str, origin: str = "") -> AssetFingerprint | None:
        """pHash-based fingerprint. Returns None when imagehash is unavailable."""
        try:
            import imagehash
            from PIL import Image
        except ImportError:
            logger.debug("imagehash / Pillow missing — image dedup disabled")
            return None

        try:
            with Image.open(str(path)) as img:
                ph = imagehash.phash(img)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"pHash failed for {path}: {e}")
            return None

        return AssetFingerprint(kind="image", key=str(ph), origin=origin)

    def fingerprint_text(self, text: str, origin: str = "") -> AssetFingerprint:
        """Sha256 over normalized text — cheap exact-dup detector.

        Normalization: NFKC + collapse whitespace + lowercase. Cosine dedup
        (register_text) handles near-duplicates; this is the strict axis.
        """
        norm = _normalize_text(text)
        key = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        return AssetFingerprint(kind="text", key=key, origin=origin)

    # ------------------------------------------------------------------
    # Registration + duplicate check
    # ------------------------------------------------------------------

    def register(self, fp: AssetFingerprint | None) -> bool:
        """Add `fp` to the seen-set. Returns True if novel, False if duplicate.

        None → treated as "unable to fingerprint" and passes through as
        novel (never blocks). This is intentional: we prefer occasional
        duplicates over silently dropping content when a dep is missing.
        """
        if fp is None:
            return True

        if fp.kind == "image":
            return self._register_image_hash(fp)
        elif fp.kind == "text":
            return self._register_text_hash(fp)
        else:
            logger.warning(f"DedupIndex: unknown fingerprint kind {fp.kind!r}")
            return True

    def register_text_with_embedding(
        self,
        text: str,
        embedding: list[float] | None,
        origin: str = "",
    ) -> bool:
        """Text dedup with both sha256 (exact) and embedding (near-dup) gates.

        Returns True when novel. Records the match reason via `_skipped`
        for debugging.
        """
        fp = self.fingerprint_text(text, origin=origin)
        # Exact match first (cheap).
        if not self._register_text_hash(fp):
            return False
        # Near-dup via embedding cosine (heavier but bounded by seen size).
        if embedding is None:
            return True
        for vec, seen_origin in self._text_embeddings:
            sim = _cosine(embedding, vec)
            if sim >= _TEXT_COSINE_THRESHOLD:
                # Roll back the sha256 registration so a later exact-hit
                # still sees the pre-embedding-dup entry as the winner.
                self._text_keys.pop(fp.key, None)
                self._skipped.append((fp, seen_origin))
                return False
        self._text_embeddings.append((list(embedding), origin))
        return True

    @property
    def skipped(self) -> list[tuple[AssetFingerprint, str]]:
        """Read-only view of what got merged and against whom."""
        return list(self._skipped)

    @property
    def size(self) -> int:
        """Total novel items registered (images + texts)."""
        return len(self._image_hashes) + len(self._text_keys)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _register_image_hash(self, fp: AssetFingerprint) -> bool:
        try:
            hash_int = int(fp.key, 16)
        except ValueError:
            logger.warning(f"DedupIndex: bad image hash {fp.key!r}")
            return True
        for seen_hash, seen_origin in self._image_hashes:
            distance = bin(seen_hash ^ hash_int).count("1")
            if distance <= _PHASH_HAMMING_THRESHOLD:
                self._skipped.append((fp, seen_origin))
                return False
        self._image_hashes.append((hash_int, fp.origin))
        return True

    def _register_text_hash(self, fp: AssetFingerprint) -> bool:
        if fp.key in self._text_keys:
            self._skipped.append((fp, self._text_keys[fp.key]))
            return False
        self._text_keys[fp.key] = fp.origin
        return True


# ----------------------------------------------------------------------
# Convenience: dedup a batch of AnnotatedSession chunks in one call.
# ----------------------------------------------------------------------


def dedup_chunks(
    chunks: Iterable[AnnotatedSession],
    embed_fn=None,
) -> tuple[list[AnnotatedSession], list[tuple[AnnotatedSession, str]]]:
    """Split `chunks` into (kept, dropped) preserving order.

    `embed_fn(text) -> list[float] | None` enables near-dup detection.
    When missing, exact sha256 dedup only. `dropped` items include the
    origin id they matched against for audit.
    """
    idx = DedupIndex()
    kept: list[AnnotatedSession] = []
    dropped: list[tuple[AnnotatedSession, str]] = []

    for ch in chunks:
        emb = embed_fn(ch.text) if embed_fn else None
        origin = ch.id
        if emb is not None:
            novel = idx.register_text_with_embedding(ch.text, emb, origin=origin)
        else:
            fp = idx.fingerprint_text(ch.text, origin=origin)
            novel = idx.register(fp)
        if novel:
            kept.append(ch)
        else:
            matched = idx.skipped[-1][1] if idx.skipped else "?"
            dropped.append((ch, matched))

    return kept, dropped


def _normalize_text(text: str) -> str:
    """NFKC + lowercase + whitespace-collapse. Keeps punctuation."""
    if not text:
        return ""
    n = unicodedata.normalize("NFKC", text).lower()
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity for two same-length lists; 0.0 on degenerate input."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
