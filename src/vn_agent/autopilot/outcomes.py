"""Autopilot run-outcome log — M0 clone of feedback/store.py's JSONL pattern.

Storage layout (single global JSONL, matches feedback/store.py's rationale —
cross-job aggregate view is more useful than per-job partitioning at M0):

    data/autopilot/runs.jsonl               # append-only, one record per line

M0: captured, not consumed. M1 ranks preset variants by success rate +
completion rate + P4 Vision Judge score once this log has enough rows
(see docs/v4/PRODUCT_v4.md P5 section, "M1 静态排序").
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_ROOT_ENV = "VN_AGENT_AUTOPILOT_ROOT"
_DEFAULT_ROOT = Path("data") / "autopilot"
_JSONL_NAME = "runs.jsonl"


def _root() -> Path:
    override = os.environ.get(_DEFAULT_ROOT_ENV)
    return Path(override) if override else _DEFAULT_ROOT


def _jsonl_path() -> Path:
    return _root() / _JSONL_NAME


def _new_id() -> str:
    return "apr_" + secrets.token_hex(4)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class AutopilotOutcome:
    """One completed (or failed) Autopilot run."""
    job_id: str
    theme: str
    preset_used: str
    success: bool
    wall_time_seconds: float
    estimated_cost_usd: float = 0.0
    scene_count: int = 0
    error: str | None = None
    id: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _new_id()
        if not self.created_at:
            self.created_at = _now_iso()

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in (None,)}


def append(outcome: AutopilotOutcome) -> Path:
    """Append `outcome` to the JSONL. Returns the JSONL path."""
    path = _jsonl_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(outcome.to_dict(), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
        f.write("\n")
    return path


def load_all() -> list[AutopilotOutcome]:
    """Read every record. Returns [] when the JSONL doesn't exist yet.

    Corrupt lines are logged at WARNING and skipped, matching
    feedback/store.py's tolerance policy.
    """
    path = _jsonl_path()
    if not path.exists():
        return []

    out: list[AutopilotOutcome] = []
    with path.open(encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping corrupt autopilot outcome line {lineno}: {e}")
                continue
            try:
                out.append(AutopilotOutcome(
                    job_id=data["job_id"],
                    theme=data["theme"],
                    preset_used=data["preset_used"],
                    success=data["success"],
                    wall_time_seconds=data["wall_time_seconds"],
                    estimated_cost_usd=data.get("estimated_cost_usd", 0.0),
                    scene_count=data.get("scene_count", 0),
                    error=data.get("error"),
                    id=data.get("id", ""),
                    created_at=data.get("created_at", ""),
                ))
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed autopilot outcome line {lineno}: {e}")
    return out


def summarize() -> dict:
    """Aggregate view — success rate + avg wall-clock, the two P5 KPIs."""
    records = load_all()
    if not records:
        return {"total": 0, "success_rate": None, "avg_wall_time_seconds": None}
    successes = sum(1 for r in records if r.success)
    return {
        "total": len(records),
        "success_rate": round(successes / len(records), 3),
        "avg_wall_time_seconds": round(sum(r.wall_time_seconds for r in records) / len(records), 1),
        "by_preset": _count_by(records, lambda r: r.preset_used),
    }


def _count_by(records: list[AutopilotOutcome], key) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        k = key(r)
        counts[k] = counts.get(k, 0) + 1
    return counts
