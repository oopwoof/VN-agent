"""Sprint 10-2: RAG pivot from dialogue few-shot to entity/lore retrieval.

Motivation: Sprint 7 introduced writer_mode=literary, which SUPPRESSES
raw-text few-shot injection because the VN corpus's JRPG/galgame style
contaminates Sonnet's literary latent space. The retrieval machinery
(FAISS, BM25, RRF, pre-filter) is still built and the audit trail
(rag_retrievals.jsonl) still populated, but no examples reach Writer's
prompt in literary mode.

Critique: "RAG is a flower vase — we build it and never use it in
literary mode." This module pivots the same infrastructure to a
different job: retrieve WORLD-BUILDING FACTS (character backgrounds,
location descriptions, world variables, story premise) per-scene so
Writer can keep those facts consistent across scenes without style
contamination.

Key design choices:
  - Lore is extracted from Director's outputs (no new LLM calls, no
    schema change) — characters, unique background_ids, world_variables,
    premise line from VNScript itself
  - Separate per-run in-memory EmbeddingIndex — dialogue corpus is
    disk-backed and reused across runs; lore is bespoke per-theme
  - Coerced into AnnotatedSession (strategy=None) to reuse
    EmbeddingIndex.search without changes
  - Injected in BOTH literary and action modes — facts don't
    contaminate style the way dialogue few-shot did

Per-run cost: ~80ms MiniLM encode of ~10 entities, trivial.
Per-call prompt cost: ~250 input tokens, ~$0.008/run (noise-level).
"""
from __future__ import annotations

import logging

from vn_agent.eval.corpus import AnnotatedSession

logger = logging.getLogger(__name__)


def extract_lore_entities(script, characters: dict) -> list[AnnotatedSession]:
    """Synthesize a list of lore entities from a VNScript + characters dict.

    Entities are heterogeneous facts the Writer might need to reference
    consistently: character backgrounds, recurring locations, world
    variable definitions, story premise. Returns a list of
    AnnotatedSession with strategy=None so EmbeddingIndex can index +
    search them without the strategy pre-filter path kicking in.

    Entity id encodes type: 'premise:main', 'character:{id}',
    'location:{background_id}', 'world_var:{name}'. Downstream
    format_lore_block uses this prefix to tag each line.

    Deduplication:
      - locations by background_id (scenes sharing a bg yield one entity)
      - characters by id (always 1 per cast entry)

    Returns [] if the script has no extractable content.
    """
    entities: list[AnnotatedSession] = []

    # Premise card — always rank-eligible, gives Writer the 1-line
    # story compass regardless of scene
    premise_text = (script.description or "").strip()
    if premise_text:
        entities.append(AnnotatedSession(
            id="premise:main",
            title=script.title or "Story",
            text=f"{script.title or 'Untitled'}. Theme: {script.theme}. "
                 f"Premise: {premise_text}",
            strategy=None,
        ))

    # Character entities — name + role + personality + background
    for cid, char in (characters or {}).items():
        parts = [f"{char.name}", f"role: {char.role}"]
        if char.personality:
            parts.append(f"personality: {char.personality}")
        if char.background:
            parts.append(f"background: {char.background}")
        entities.append(AnnotatedSession(
            id=f"character:{cid}",
            title=char.name,
            text=" — ".join(parts),
            strategy=None,
        ))

    # Location entities — unique background_ids, with scene_refs
    # included so Writer can see "this location appears in ch2, ch5"
    bg_to_scenes: dict[str, list] = {}
    for scene in script.scenes:
        if not scene.background_id:
            continue
        bg_to_scenes.setdefault(scene.background_id, []).append(scene)
    for bg_id, bg_scenes in bg_to_scenes.items():
        # Use the first scene's description as the location's description;
        # list all scenes referring to it for Writer context
        first = bg_scenes[0]
        scene_refs = ", ".join(s.id for s in bg_scenes)
        entities.append(AnnotatedSession(
            id=f"location:{bg_id}",
            title=bg_id,
            text=(
                f"{bg_id}: appears in {scene_refs}. "
                f"Described: {(first.description or 'no description')[:240]}"
            ),
            strategy=None,
        ))

    # World variable entities — name + type + initial + description
    for var in getattr(script, "world_variables", []) or []:
        entities.append(AnnotatedSession(
            id=f"world_var:{var.name}",
            title=var.name,
            text=(
                f"{var.name} ({var.type}, starts {var.initial_value!r}): "
                f"{var.description or '(no description)'}"
            ),
            strategy=None,
        ))

    return entities


def build_lore_index(script, characters: dict):
    """Build a per-run in-memory EmbeddingIndex over extracted lore entities.

    Returns None when:
      - Extraction yields zero entities (empty script)
      - sentence-transformers / faiss aren't installed (optional deps)
      - Any other build-time failure (logged at DEBUG, not raised)

    Callers treat None as "lore retrieval disabled for this run" —
    matches the existing dialogue-RAG graceful-degradation pattern.
    """
    entities = extract_lore_entities(script, characters)
    if not entities:
        return None

    try:
        from vn_agent.eval.embedder import EmbeddingIndex
    except ImportError:
        logger.debug("EmbeddingIndex unavailable (sbert/faiss not installed)")
        return None

    try:
        from vn_agent.config import get_settings
        model_name = get_settings().embedding_model
        index = EmbeddingIndex(model_name=model_name)
        index.build(entities)
        logger.info(
            f"Lore index built: {len(entities)} entities "
            f"({sum(1 for e in entities if e.id.startswith('character:'))} chars, "
            f"{sum(1 for e in entities if e.id.startswith('location:'))} locs, "
            f"{sum(1 for e in entities if e.id.startswith('world_var:'))} vars)"
        )
        return index
    except Exception as e:  # noqa: BLE001 — optional feature, don't crash pipeline
        logger.debug(f"Lore index build failed: {e}")
        return None


def format_lore_block(entities: list[AnnotatedSession], max_chars: int = 1500) -> str:
    """Render retrieved lore entities as a prompt-injectable block.

    Differs from eval/retriever.py::format_examples in three ways:
      - Header says "World lore for this scene" (facts, not style examples)
      - Each entity tagged by type (character/location/world_var/premise)
        derived from the id prefix, not by strategy label
      - Text per entity truncated to keep total block under max_chars

    Returns "" when entities is empty so callers can unconditionally
    include the result in the prompt.
    """
    if not entities:
        return ""

    lines = ["--- World lore relevant to this scene ---"]
    running = len(lines[0])
    for ex in entities:
        # Parse type from id prefix
        eid = getattr(ex, "id", "") or ""
        etype = eid.split(":", 1)[0] if ":" in eid else "entity"
        text = (getattr(ex, "text", "") or "")[:300]
        line = f"[{etype}] {text}"
        if running + len(line) + 1 > max_chars:
            lines.append("  ...")
            break
        lines.append(line)
        running += len(line) + 1
    lines.append("--- End lore ---")
    return "\n".join(lines)
