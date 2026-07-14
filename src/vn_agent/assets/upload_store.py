"""Per-job upload persistence: JSONL of AnnotatedSession[user_upload].

Storage layout:
  data/uploads/{job_id}/uploads.jsonl   — one JSON object per chunk
  data/uploads/{job_id}/raw/{filename}  — original bytes (optional; kept for
                                          diversity index audit + replay)

Design notes:
- JSONL, not SQLite. v3 shelved SQLite JobStore for pipeline state; here
  we deliberately stay flat-file because per-job upload volume is small
  (< 1 MB typical) and JSONL is trivial to grep, diff, and rsync during
  debug. If throughput ever justifies migration, swap this file, callers
  don't change.
- Best-effort raw persistence. If writing the raw bytes fails (disk full,
  permission), we still return the chunks — the RAG path only needs the
  chunks, not the source file. But we WARN loud so audit can catch it.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from vn_agent.eval.corpus import AnnotatedSession

logger = logging.getLogger(__name__)

_DATA_UPLOAD_ROOT_ENV = "VN_AGENT_UPLOAD_ROOT"
_DEFAULT_UPLOAD_ROOT = Path("data") / "uploads"


def _upload_root() -> Path:
    """Resolve the upload root, letting tests override via env var."""
    import os
    override = os.environ.get(_DATA_UPLOAD_ROOT_ENV)
    if override:
        return Path(override)
    return _DEFAULT_UPLOAD_ROOT


def _safe_job_id(job_id: str) -> str:
    """Filesystem-safe job id — strict allow-list, no separators, no `..`.

    Deliberately stricter than the upload endpoint's asset_id regex — job
    ids come from the JobStore (uuid or hex slug), and letting `.` or `/`
    through here would let a caller escape the upload_root via `../../etc`.
    """
    if not job_id or not re.fullmatch(r"[a-zA-Z0-9_-]+", job_id):
        raise ValueError(f"Invalid job_id: {job_id!r}")
    return job_id


def upload_dir(job_id: str) -> Path:
    """Where this job's uploads live. Created on first write."""
    return _upload_root() / _safe_job_id(job_id)


def save_chunks(job_id: str, chunks: list[AnnotatedSession]) -> Path:
    """Append `chunks` to the job's uploads.jsonl. Returns the JSONL path.

    Idempotent-friendly: if the file already exists we append, so multiple
    uploads within one job accumulate. Caller is responsible for dedup —
    see assets/dedup.py.
    """
    if not chunks:
        return upload_dir(job_id) / "uploads.jsonl"

    dst = upload_dir(job_id)
    dst.mkdir(parents=True, exist_ok=True)
    path = dst / "uploads.jsonl"

    with path.open("a", encoding="utf-8") as f:
        for ch in chunks:
            f.write(ch.model_dump_json())
            f.write("\n")

    return path


def save_raw(job_id: str, filename: str, data: bytes) -> Path | None:
    """Persist the original bytes under raw/. Returns path or None on failure.

    Best-effort: audit/replay convenience only. Failure is logged but not
    raised — chunks are the source of truth for retrieval.
    """
    from vn_agent.assets.text_ingest import _normalize_upload_id

    safe_name = _normalize_upload_id(filename)
    ext = ""
    if "." in filename:
        raw_ext = filename.rsplit(".", 1)[-1].lower()
        # Whitelist extensions to avoid accidentally writing .exe/.bat etc.
        if raw_ext in {"md", "txt", "markdown", "pdf", "docx"}:
            ext = f".{raw_ext}"

    raw_dir = upload_dir(job_id) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{safe_name}{ext}"

    try:
        path.write_bytes(data)
        return path
    except OSError as e:
        logger.warning(f"Failed to persist raw upload {filename!r} for job {job_id}: {e}")
        return None


def load_chunks(job_id: str) -> list[AnnotatedSession]:
    """Load all chunks for a job. Returns [] when no uploads exist."""
    path = upload_dir(job_id) / "uploads.jsonl"
    if not path.exists():
        return []

    chunks: list[AnnotatedSession] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(AnnotatedSession.model_validate_json(line))
            except Exception as e:  # noqa: BLE001 — corrupt line shouldn't kill load
                logger.warning(f"Skipping corrupt upload line in {path}: {e}")
    return chunks


def summarize(job_id: str) -> dict:
    """Provenance snapshot for the diversity index + UI badges."""
    chunks = load_chunks(job_id)
    if not chunks:
        return {"chunks": 0, "by_source": {}, "by_license": {}, "files": []}

    by_source: dict[str, int] = {}
    by_license: dict[str, int] = {}
    files: set[str] = set()
    for ch in chunks:
        meta = ch.source_meta or {}
        src = str(meta.get("source", "unknown"))
        lic = str(meta.get("license", "unknown"))
        by_source[src] = by_source.get(src, 0) + 1
        by_license[lic] = by_license.get(lic, 0) + 1
        # For web_search chunks the source_url is the canonical identifier;
        # for uploads/local_library the filename is. Track whichever is
        # semantically primary so the UI badge and audit trail point at
        # the right thing (URLs for citations, filenames for uploads).
        if src == "web_search" and meta.get("source_url"):
            files.add(str(meta["source_url"]))
        elif meta.get("filename"):
            files.add(str(meta["filename"]))
        elif meta.get("source_url"):
            files.add(str(meta["source_url"]))

    return {
        "chunks": len(chunks),
        "by_source": by_source,
        "by_license": by_license,
        "files": sorted(files),
    }
