"""Heterogeneous corpus loader: merge annotated CSV + unannotated JSONL sessions.

The annotated CSV (`data/final_annotations.csv`) holds ~1,036 sessions with
strategy labels — this is the primary corpus.

The sessions directory (e.g. `data/sessions/part_*.jsonl`) holds a larger pool
of raw VN dialogue sessions without strategy labels. We merge these in as
fallback material for RAG backfill, but never let them outrank annotated
sessions (see `EmbeddingIndex._search_pre_filter` for enforcement).

Deduplication:
  1. Primary key: `id`. If an id appears in both sources, the annotated
     version wins.
  2. Fingerprint fallback: for sources where ids may differ but content is
     identical, we also dedupe by `title + text[:200]` hash.

Usage:
    sessions = load_merged_corpus(
        annotated_csv=Path("data/final_annotations.csv"),
        sessions_dir=Path("data/sessions"),  # optional
    )
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable
from pathlib import Path

from vn_agent.eval.corpus import AnnotatedSession, load_corpus

logger = logging.getLogger(__name__)


def _fingerprint(title: str, text: str) -> str:
    """Stable fingerprint for dedup across heterogeneous sources."""
    material = f"{title.strip().lower()}\0{text[:200].strip()}"
    return hashlib.sha1(material.encode("utf-8", errors="ignore")).hexdigest()


def _iter_jsonl_files(root: Path) -> Iterable[Path]:
    """Yield .jsonl files under root (non-recursive + one level deep)."""
    if not root.exists():
        return
    yield from sorted(root.glob("*.jsonl"))
    yield from sorted(root.glob("*/*.jsonl"))


def _load_unannotated_sessions(sessions_dir: Path) -> list[AnnotatedSession]:
    """Load all JSONL sessions under sessions_dir as strategy=None entries.

    Expected JSONL line shape:
        {"id": "0_0", "title": "...", "n_lines": 12, "text": "..."}

    Silently skips malformed lines and files that can't be opened.
    """
    sessions: list[AnnotatedSession] = []
    for path in _iter_jsonl_files(sessions_dir):
        try:
            with open(path, encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug(f"Skipping malformed line {path}:{line_no}")
                        continue
                    sid = str(entry.get("id") or "").strip()
                    title = str(entry.get("title") or "").strip()
                    text = str(entry.get("text") or "").strip()
                    if not sid or not text:
                        continue
                    sessions.append(
                        AnnotatedSession(
                            id=sid,
                            title=title or sid,
                            text=text,
                            strategy=None,
                            pivot_line_idx=None,
                            pacing=None,
                        )
                    )
        except OSError as e:
            logger.warning(f"Could not read {path}: {e}")
    return sessions


def load_merged_corpus(
    annotated_csv: Path,
    sessions_dir: Path | None = None,
) -> list[AnnotatedSession]:
    """Load annotated CSV + optional unannotated sessions dir with dedup.

    Annotated sessions come first (preserving their CSV order). Unannotated
    sessions are appended in arrival order, excluding any duplicates of
    annotated sessions by id or fingerprint.

    Args:
        annotated_csv: path to final_annotations.csv (required)
        sessions_dir: optional path to dir of *.jsonl session files

    Returns:
        Combined session list. Unannotated sessions carry strategy=None so
        retrieval code can treat them as low-priority backfill.
    """
    annotated = load_corpus(annotated_csv)

    if sessions_dir is None or not Path(sessions_dir).exists():
        logger.info(
            f"Loaded {len(annotated)} annotated sessions "
            f"(sessions_dir not provided or missing — no expansion)"
        )
        return annotated

    # Build dedup indexes from annotated sessions
    annotated_ids = {s.id for s in annotated}
    annotated_fps = {_fingerprint(s.title, s.text) for s in annotated}

    raw_extra = _load_unannotated_sessions(Path(sessions_dir))

    # Deduplicate within extras themselves too (same text appearing in multiple
    # JSONL parts) and against annotated set.
    seen_extra_ids: set[str] = set()
    seen_extra_fps: set[str] = set()
    unique_extras: list[AnnotatedSession] = []
    for s in raw_extra:
        if s.id in annotated_ids:
            continue
        fp = _fingerprint(s.title, s.text)
        if fp in annotated_fps:
            continue
        if s.id in seen_extra_ids or fp in seen_extra_fps:
            continue
        seen_extra_ids.add(s.id)
        seen_extra_fps.add(fp)
        unique_extras.append(s)

    logger.info(
        f"Loaded {len(annotated)} annotated + {len(raw_extra)} raw unannotated; "
        f"deduped to {len(unique_extras)} unique unannotated. "
        f"Total corpus: {len(annotated) + len(unique_extras)}"
    )
    return annotated + unique_extras
