"""COLX_523 corpus loader: CSV annotations + JSONL reasoning data."""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Map COLX_523 strategy labels to VN-Agent strategy names
STRATEGY_MAP: dict[str, str | None] = {
    "Accumulate": "accumulate",
    "Erode": "erode",
    "Rupture": "rupture",
    "Uncover": "reveal",
    "Contest": "contrast",
    "Drift": "weave",
    "Other": None,
}


class AnnotatedSession(BaseModel):
    """A single annotated VN dialogue session from the COLX_523 corpus."""

    id: str
    title: str
    text: str  # 12-line dialogue
    strategy: str | None  # normalized VN-Agent strategy name (None for unmapped)
    pivot_line_idx: int | None = None
    pacing: str | None = None  # slow / medium / fast


def load_corpus(csv_path: Path) -> list[AnnotatedSession]:
    """Load final_annotations.csv, normalize strategies via STRATEGY_MAP.

    Handles:
    - Trailing whitespace in fields
    - Title-case normalization of predominant_strategy
    - Rows with unknown strategies mapped to None
    """
    sessions: list[AnnotatedSession] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_strategy = row.get("predominant_strategy", "").strip().title()
            mapped = STRATEGY_MAP.get(raw_strategy)

            pivot_raw = row.get("pivot_line_idx", "").strip()
            pivot_idx: int | None = None
            if pivot_raw:
                try:
                    pivot_idx = int(pivot_raw)
                except ValueError:
                    pass

            sessions.append(
                AnnotatedSession(
                    id=row.get("id", "").strip(),
                    title=row.get("title", "").strip(),
                    text=row.get("text", "").strip(),
                    strategy=mapped,
                    pivot_line_idx=pivot_idx,
                    pacing=row.get("pacing", "").strip() or None,
                )
            )

    logger.info(f"Loaded {len(sessions)} sessions from {csv_path}")
    return sessions


def load_reasoning(jsonl_path: Path) -> dict[str, dict]:
    """Load reasoning-rich JSONL, keyed by session id.

    Each entry may contain: gist, strategy_reasoning, pivot_span, pivot_type, pacing_reasoning.
    """
    data: dict[str, dict] = {}
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            session_id = str(entry.get("id", "")).strip()
            if session_id:
                data[session_id] = entry

    logger.info(f"Loaded reasoning for {len(data)} sessions from {jsonl_path}")
    return data
