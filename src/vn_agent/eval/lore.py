"""Sprint 10-2: RAG pivot from dialogue few-shot to entity/lore retrieval.

Phase 13-1 / Step 3 upgrade: entity scope + sentence-boundary truncation
+ always-scope bypass of FAISS. Background:

- Cosine top-k over premise + characters + locations + world_vars can push
  the premise out of the retrieved set in any scene where its embedding
  doesn't match. Over 50 scenes the model loses its compass.
- Hard `[:N]` truncation from Sprint 7 (when 8K context was tight) slices
  mid-word, feeding half-sentences to Writer.
- The 1500-char format_lore_block cap is a legacy from the Sonnet-8K era
  — Sonnet 200K + prompt caching makes the budget effectively infinite.

Fix (Step 3): tag each entity with scope ∈ {always, chapter, scene}:
  - always:  premise + main (immutability≥8) characters → bypass FAISS,
             feed into system-prompt cached prefix (cache_control + 1h TTL)
  - chapter: world_vars + secondary characters → retrieved pool, cap 800
  - scene:   locations + callback hooks → retrieved pool, cap 300

Truncation switches from `[:N]` to `_sentence_break` (finds last '.', '。',
'!', '?', '\\n\\n' before cap, with a floor of cap*0.6 to avoid dropping
too much; fallback to [:cap] when no sentence boundary exists).

format_lore_block now returns THREE blocks so the Writer prompt assembler
can place them in the right prompt sections (always → system prefix;
chapter + retrieved → user message).
"""
from __future__ import annotations

import logging
from typing import Any

from vn_agent.eval.corpus import AnnotatedSession

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Helpers: scope tagging + sentence-boundary truncation
# ----------------------------------------------------------------------------

# Main-character heuristic when `immutability_score` is unset on the
# CharacterProfile — a character present in ≥50% of scenes is "main".
_MAIN_CHARACTER_SCENE_FRACTION = 0.5


def _is_main_character(char_id: str, char: Any, script: Any) -> bool:
    """Decide if a character is always-scope.

    Pure coverage heuristic: the character appears in ≥50% of scenes.

    Why NOT immutability_score: CharacterProfile's default immutability_score
    locks name/role at 10 for EVERY character (as a structural protection
    against Writer rename drift), not as a "this is a protagonist" signal.
    Using it for prominence would classify every secondary character as
    always-scope, bloating the cached prefix with characters who appear in
    one scene. Coverage is the honest signal.
    """
    if not script or not getattr(script, "scenes", None):
        return False
    if not char_id:
        return False
    appears = sum(1 for s in script.scenes if char_id in (s.characters_present or []))
    return appears >= len(script.scenes) * _MAIN_CHARACTER_SCENE_FRACTION


def _sentence_break(text: str, cap: int) -> str:
    """Break at the last sentence boundary before `cap` (floor cap*0.6).

    Falls back to a hard slice when no sentence punctuation is within the
    usable window. This prevents the original `[:240]` pattern from cutting
    mid-word or mid-clause, which fed half-sentences into Writer's prompt
    and was measurably degrading long-run coherence.
    """
    if len(text) <= cap:
        return text
    window = text[:cap]
    min_idx = int(cap * 0.6)
    # Longer separators first so "! " beats a bare "!" in run-on text.
    for sep in ("\n\n", "。", ". ", "! ", "? ", "!", "?", "\n"):
        idx = window.rfind(sep)
        if idx >= min_idx:
            return window[: idx + len(sep)].rstrip()
    return window


# ----------------------------------------------------------------------------
# Entity extraction + index build
# ----------------------------------------------------------------------------


def extract_lore_entities(script, characters: dict) -> list[AnnotatedSession]:
    """Synthesize lore entities from Director outputs, tagged with scope.

    Entity id encodes type prefix: 'premise:main', 'character:{id}',
    'location:{background_id}', 'world_var:{name}'.

    Scope assignment (Phase 13-1 / Step 3):
      - Premise                      → always
      - Main character (immut≥8, or
        ≥50% scene coverage)         → always
      - Secondary character          → scene (noisy dialogue-level retrieval)
      - world_var                    → chapter (story-wide but can evolve)
      - location (background_id)     → scene (dialogue-level, retrieved)

    Returns [] on empty inputs.
    """
    entities: list[AnnotatedSession] = []

    # Premise — the story compass. ALWAYS visible to Writer.
    premise_text = (script.description or "").strip()
    if premise_text:
        entities.append(AnnotatedSession(
            id="premise:main",
            title=script.title or "Story",
            text=f"{script.title or 'Untitled'}. Theme: {script.theme}. "
                 f"Premise: {premise_text}",
            strategy=None,
            scope="always",
        ))

    # Characters — main characters pinned to always-scope prefix, others
    # stay in the retrieved pool.
    for cid, char in (characters or {}).items():
        parts = [f"{char.name}", f"role: {char.role}"]
        if char.personality:
            parts.append(f"personality: {char.personality}")
        if char.background:
            parts.append(f"background: {char.background}")
        is_main = _is_main_character(cid, char, script)
        entities.append(AnnotatedSession(
            id=f"character:{cid}",
            title=char.name,
            text=" — ".join(parts),
            strategy=None,
            scope="always" if is_main else "scene",
        ))

    # Locations — unique background_ids with scene_refs.
    bg_to_scenes: dict[str, list] = {}
    for scene in script.scenes:
        if not scene.background_id:
            continue
        bg_to_scenes.setdefault(scene.background_id, []).append(scene)
    for bg_id, bg_scenes in bg_to_scenes.items():
        first = bg_scenes[0]
        scene_refs = ", ".join(s.id for s in bg_scenes)
        location_desc = _sentence_break(
            first.description or "no description", cap=600,
        )
        entities.append(AnnotatedSession(
            id=f"location:{bg_id}",
            title=bg_id,
            text=(
                f"{bg_id}: appears in {scene_refs}. "
                f"Described: {location_desc}"
            ),
            strategy=None,
            scope="scene",
        ))

    # World variables — chapter-scope (story-wide, but can evolve per chapter).
    for var in getattr(script, "world_variables", []) or []:
        entities.append(AnnotatedSession(
            id=f"world_var:{var.name}",
            title=var.name,
            text=(
                f"{var.name} ({var.type}, starts {var.initial_value!r}): "
                f"{var.description or '(no description)'}"
            ),
            strategy=None,
            scope="chapter",
        ))

    return entities


def build_lore_index(script, characters: dict):
    """Build a per-run EmbeddingIndex over lore entities.

    Phase 13-1 / Step 3: always-scope entities are extracted but NOT put
    into FAISS. They're attached to the returned index object as
    `.always_entities` so callers can inject them into the cached system
    prefix without competing for top-k slots.

    Returns None when:
      - Extraction yields zero entities
      - sentence-transformers / faiss aren't installed
      - Any other build-time failure (logged at DEBUG)
    """
    entities = extract_lore_entities(script, characters)
    if not entities:
        return None

    always_entities = [e for e in entities if e.scope == "always"]
    chapter_entities = [e for e in entities if e.scope == "chapter"]
    scene_entities = [e for e in entities if e.scope == "scene"]
    # Only scene-scope goes into FAISS for per-scene top-k retrieval.
    # Chapter-scope rides along in the cached system prefix (Step 3) — its
    # content is stable within a run, so it doesn't need cosine filtering.
    retrievable = scene_entities

    try:
        from vn_agent.eval.embedder import EmbeddingIndex
    except ImportError:
        logger.debug("EmbeddingIndex unavailable (sbert/faiss not installed)")
        return None

    try:
        from vn_agent.config import get_settings
        model_name = get_settings().embedding_model
        index = EmbeddingIndex(model_name=model_name)
        if retrievable:
            index.build(retrievable)
        else:
            # All entities are always-scope or chapter-scope (tiny script).
            # Build anyway so caller's retrieve() call returns [] cleanly.
            index.build(entities)
        # Attach the three scope buckets so Writer's prompt assembler can
        # place each in the right prompt section (always + chapter → cached
        # system prefix; scene → retrieved via top-k in user message).
        # setattr used to avoid mypy attr-defined complaints — EmbeddingIndex
        # doesn't declare these fields, they're a Step-3 extension attached
        # to the live instance only.
        index.always_entities = always_entities  # type: ignore[attr-defined]
        index.chapter_entities = chapter_entities  # type: ignore[attr-defined]
        index.scene_entities = scene_entities  # type: ignore[attr-defined]
        logger.info(
            f"Lore index built: {len(entities)} entities total "
            f"({len(always_entities)} always / {len(chapter_entities)} chapter "
            f"/ {len(scene_entities)} scene)"
        )
        return index
    except Exception as e:  # noqa: BLE001 — optional feature, don't crash pipeline
        logger.debug(f"Lore index build failed: {e}")
        return None


# ----------------------------------------------------------------------------
# Block formatting: three-way output so Writer can place each segment
# ----------------------------------------------------------------------------


_DEFAULT_SCOPE_CAPS: dict[str, int] = {
    "always": 10**9,   # never truncate always-scope
    "chapter": 800,
    "scene": 300,
}


def _format_entity_line(ex: AnnotatedSession, cap: int) -> str:
    """One-line [type] prefix + sentence-bounded text."""
    eid = getattr(ex, "id", "") or ""
    etype = eid.split(":", 1)[0] if ":" in eid else "entity"
    text = _sentence_break((getattr(ex, "text", "") or "").strip(), cap=cap)
    return f"[{etype}] {text}"


def format_lore_block(
    retrieved: list[AnnotatedSession],
    always_entities: list[AnnotatedSession] | None = None,
    chapter_entities: list[AnnotatedSession] | None = None,
    scope_caps: dict[str, int] | None = None,
    total_cap: int = 6000,
) -> tuple[str, str, str]:
    """Render three separately-addressable lore blocks.

    Returns (always_block, chapter_block, retrieved_block).

    Placement convention (Writer assembler's responsibility):
      - always_block  → cached system-prompt prefix (cache_control: 1h)
      - chapter_block → user message, prepended to recent window
      - retrieved_block → user message, after chapter_block (lower priority)

    Backward-compat: callers passing a single `retrieved` list (pre-Step 3
    shape) still get the old behavior — always/chapter blocks are "" and
    the full retrieved output ends up in the retrieved_block.
    """
    scope_caps = scope_caps or _DEFAULT_SCOPE_CAPS
    always_entities = always_entities or []
    chapter_entities = chapter_entities or []

    def _render_block(entities: list[AnnotatedSession], header: str, cap: int) -> str:
        if not entities:
            return ""
        lines = [header]
        for ex in entities:
            lines.append(_format_entity_line(ex, cap=cap))
        return "\n".join(lines)

    always_block = _render_block(
        always_entities,
        "--- Always-on lore (story compass — premise + main characters) ---",
        cap=scope_caps.get("always", 10**9),
    )
    chapter_block = _render_block(
        chapter_entities,
        "--- Chapter-scope lore (world variables + secondary characters) ---",
        cap=scope_caps.get("chapter", 800),
    )
    # Retrieved pool (scene-scope plus anything the caller passes) shares
    # the remaining total_cap budget after always + chapter have taken their
    # share. Enforce: if always + chapter already exceeds total_cap, drop
    # retrieved entirely rather than emitting a half-line.
    used = len(always_block) + len(chapter_block)
    remaining = max(0, total_cap - used)
    retrieved_block = ""
    if retrieved and remaining > 50:
        lines = ["--- Retrieved lore (scene-specific) ---"]
        running = len(lines[0])
        for ex in retrieved:
            line = _format_entity_line(ex, cap=scope_caps.get("scene", 300))
            if running + len(line) + 1 > remaining:
                lines.append("  ...")
                break
            lines.append(line)
            running += len(line) + 1
        retrieved_block = "\n".join(lines)

    return always_block, chapter_block, retrieved_block
