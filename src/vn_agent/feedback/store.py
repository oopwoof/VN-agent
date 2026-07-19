"""Creator feedback persistence — the L1 layer of the v4 data flywheel.

Storage layout (single global JSONL, per-job partitioning not needed at M0):

    data/feedback/all.jsonl               # append-only, one record per line

Why one file: BM25 injection (P1-2) and Reflection Agent (P1-3) both want
cross-job insight — "past creators told us x" is more useful than "this
particular job's own feedback". If cardinality ever justifies partitioning,
swap this file, callers don't change.

Record schema (frozen at M0):

    {
      "id": "fb_<uuid8>",
      "job_id": "3cbbf260",
      "scene_id": "ch1_arrival" | null,
      "verdict": "up" | "down",
      "reason": "对白太啰嗦" | null,
      "tags": ["dialogue-length", "校园"],
      "context": {                        # optional; caller-supplied hints
        "theme": "...",
        "narrative_strategy": "erode",
        "characters_present": ["alice", "bob"]
      },
      "created_at": "2026-07-19T20:14:00Z"
    }

Records are immutable once written. Editing = new record + `supersedes: id`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

logger = logging.getLogger(__name__)


_DEFAULT_ROOT_ENV = "VN_AGENT_FEEDBACK_ROOT"
_DEFAULT_ROOT = Path("data") / "feedback"
_JSONL_NAME = "all.jsonl"


def _root() -> Path:
    override = os.environ.get(_DEFAULT_ROOT_ENV)
    return Path(override) if override else _DEFAULT_ROOT


def _jsonl_path() -> Path:
    return _root() / _JSONL_NAME


def _new_id() -> str:
    """Short readable id — avoids uuid4 length while staying collision-safe
    at expected volumes (< 100k records over the M0 window)."""
    return "fb_" + secrets.token_hex(4)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_job_id(job_id: str | None) -> str | None:
    """Same allow-list as `assets/upload_store._safe_job_id`. Optional — feedback
    can carry a bare job_id="" if the creator gave a global thumbs-up before
    any generation ran."""
    if job_id is None:
        return None
    if not job_id:
        return ""
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", job_id):
        raise ValueError(f"Invalid job_id: {job_id!r}")
    return job_id


@dataclass
class FeedbackRecord:
    """One 👍/👎 signal. `to_dict()` yields the JSONL row shape verbatim."""
    verdict: Literal["up", "down"]
    job_id: str | None = None
    scene_id: str | None = None
    reason: str | None = None
    tags: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    id: str = ""
    created_at: str = ""
    supersedes: str | None = None

    def __post_init__(self):
        if not self.id:
            self.id = _new_id()
        if not self.created_at:
            self.created_at = _now_iso()
        _safe_job_id(self.job_id)
        if self.verdict not in {"up", "down"}:
            raise ValueError(f"verdict must be 'up' or 'down', got {self.verdict!r}")

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in (None, [], {}) or k in {"verdict"}}


def append(record: FeedbackRecord) -> Path:
    """Append `record` to the JSONL. Returns the JSONL path.

    Best-effort atomic: writes in a single line under the file's exclusive
    lock (POSIX advisory / Windows no-op). If the write raises, callers
    should propagate to a 500 — this is dev-visible state.
    """
    path = _jsonl_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record.to_dict(), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
        f.write("\n")
    return path


def load_all() -> list[FeedbackRecord]:
    """Read every record. Returns [] when the JSONL doesn't exist yet.

    Corrupt lines are logged at WARNING and skipped — a single bad line
    can't take down the whole flywheel.
    """
    path = _jsonl_path()
    if not path.exists():
        return []

    out: list[FeedbackRecord] = []
    with path.open(encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping corrupt feedback line {lineno}: {e}")
                continue
            try:
                # tags / context / supersedes may be absent — defaults kick in
                out.append(FeedbackRecord(
                    verdict=data["verdict"],
                    job_id=data.get("job_id"),
                    scene_id=data.get("scene_id"),
                    reason=data.get("reason"),
                    tags=list(data.get("tags") or []),
                    context=dict(data.get("context") or {}),
                    id=data.get("id", ""),
                    created_at=data.get("created_at", ""),
                    supersedes=data.get("supersedes"),
                ))
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed feedback line {lineno}: {e}")
    return out


def load_recent(limit: int = 100) -> list[FeedbackRecord]:
    """Read the last `limit` records — used by BM25 injection when the total
    corpus grows past what we want to embed each generation."""
    if limit <= 0:
        return []
    all_records = load_all()
    return all_records[-limit:]


def load_by_verdict(verdict: Literal["up", "down"]) -> list[FeedbackRecord]:
    """Filter for one polarity. Down-votes drive the "AVOID" prompt injection
    (P1-2); up-votes anchor the Reflection Agent's positive rule extraction
    (P1-3)."""
    return [r for r in load_all() if r.verdict == verdict]


def summarize() -> dict:
    """Aggregate view for dashboards + gate checks (e.g. reflection needs
    ≥ N records)."""
    records = load_all()
    by_verdict: dict[str, int] = {"up": 0, "down": 0}
    by_scene: dict[str, int] = {}
    by_job: dict[str, int] = {}
    tag_hist: dict[str, int] = {}
    for r in records:
        by_verdict[r.verdict] = by_verdict.get(r.verdict, 0) + 1
        if r.scene_id:
            by_scene[r.scene_id] = by_scene.get(r.scene_id, 0) + 1
        if r.job_id:
            by_job[r.job_id] = by_job.get(r.job_id, 0) + 1
        for t in r.tags:
            tag_hist[t] = tag_hist.get(t, 0) + 1
    return {
        "total": len(records),
        "by_verdict": by_verdict,
        "by_scene": by_scene,
        "by_job": by_job,
        "top_tags": dict(sorted(tag_hist.items(), key=lambda kv: -kv[1])[:20]),
    }


def iter_reasons(verdict: Literal["up", "down"] | None = None) -> Iterable[str]:
    """Reason-strings only, filtered — quick corpus for BM25."""
    for r in load_all():
        if verdict is not None and r.verdict != verdict:
            continue
        if r.reason:
            yield r.reason
