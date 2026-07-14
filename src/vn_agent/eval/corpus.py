"""COLX_523 corpus loader: CSV annotations + JSONL reasoning data."""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Map COLX_523 annotation labels → VN-Agent StrategyType values.
#
# The taxonomy is aligned: dataset and code use the same six names
# (case-normalized). Previously three labels were semantically wrong
# (Uncover→reveal, Contest→contrast, Drift→weave) — those made RAG
# retrieval fetch examples that taught Writer the opposite style.
# See strategies/narrative.py for the physics-framework definitions.
STRATEGY_MAP: dict[str, str | None] = {
    "Accumulate": "accumulate",
    "Erode": "erode",
    "Rupture": "rupture",
    "Uncover": "uncover",
    "Contest": "contest",
    "Drift": "drift",
    "Other": None,
}


class AnnotatedSession(BaseModel):
    """A single annotated VN dialogue session from the COLX_523 corpus.

    Phase 13-1 / Step 3: also used as a lore entity carrier (see eval/lore.py)
    where `scope` tags whether the entity is premise-class (always in prompt
    prefix), chapter-wide (changes at chapter boundaries), or scene-local
    (dynamically retrieved via cosine top-k).
    """

    id: str
    title: str
    text: str  # 12-line dialogue
    strategy: str | None  # normalized VN-Agent strategy name (None for unmapped)
    pivot_line_idx: int | None = None
    pacing: str | None = None  # slow / medium / fast
    # Phase 13-1 / Step 3: lore-entity scope. "scene" is the default so existing
    # corpus sessions (which are dialogue few-shots, not lore) stay unchanged.
    #   always       → premise, immutability_score≥8 characters. Bypass FAISS,
    #                  inject in cached system-prompt prefix with cache_control.
    #   chapter      → story-wide world_vars + secondary characters. In retrieved
    #                  pool but cap raised (800 char).
    #   scene        → locations, callback hooks, noisy retrieval context. Cap
    #                  stays at 300 char.
    #   user_upload  → v4 P0: user-uploaded text (md/pdf/docx) or web-search
    #                  chunks. Joins the FAISS retrieval pool alongside scene
    #                  scope. `source_meta` carries provenance for license
    #                  gate + diversity index.
    scope: Literal["always", "chapter", "scene", "user_upload"] = "scene"

    # v4 P0: provenance metadata. Optional; only user_upload / web_search
    # chunks populate this. Fields typically include:
    #   source: "upload" | "web_search" | "local_library" | "llm_generated"
    #   source_url: original URL for web_search, or filename for upload
    #   license: "CC0" | "CC-BY" | "user_owned" | "derived" | "unknown"
    #   retrieved_at: ISO timestamp
    #   search_query: original search query (web_search only)
    source_meta: dict = Field(default_factory=dict)


def load_corpus(csv_path: Path) -> list[AnnotatedSession]:
    """Load final_annotations.csv, normalize strategies via STRATEGY_MAP.

    Handles:
    - Trailing whitespace in fields
    - Title-case normalization of predominant_strategy
    - Rows with unknown strategies mapped to None
    """
    sessions: list[AnnotatedSession] = []
    # utf-8-sig strips the UTF-8 BOM so the first header is 'id', not '\ufeffid'
    # — without this, row.get("id") silently returned '' and every session id
    # came out empty, making RAG retrieval records unidentifiable.
    with open(csv_path, encoding="utf-8-sig") as f:
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
