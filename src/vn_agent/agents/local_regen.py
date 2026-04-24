"""Sprint 12-4: regenerate a single scene without re-running the whole pipeline.

Given a vn_script.json + characters.json on disk, re-run ONLY Writer +
DialogueReviewer for one named scene. Walks the state timeline up to
that scene so world_state is exactly what it was at scene-start, fires
a fresh Writer call, updates the scene's dialogue + state_writes + snapshot.

Use cases:
  - Creator edits a branch target and wants to rewrite the affected scene
  - One scene's dialogue landed flat; regenerate with different temperature
  - A/B experiments on one scene without 6× the baseline cost

Non-goals (Sprint 12 may add later):
  - Auto-invalidate downstream scenes that depended on old state_writes
  - Resume from a specific scene and continue generating the rest
  - Web/UI surface — this module is called from CLI only right now
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from vn_agent.agents.writer import (
    _build_char_descriptions,
    _build_character_bible,
    _write_scene,
    _write_scene_snapshot,
)
from vn_agent.config import get_settings
from vn_agent.prompts.templates import WRITER_SYSTEM
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import StateTimelineEntry, VNScript

logger = logging.getLogger(__name__)


class RegenError(Exception):
    """Raised when the scene can't be regenerated (missing id, missing files, etc.)."""


async def regenerate_scene(
    output_dir: Path,
    scene_id: str,
    revision_feedback: str = "",
) -> dict:
    """Rewrite a single scene in an existing run directory.

    Returns a summary dict:
      {scene_id, old_dialogue_count, new_dialogue_count,
       state_writes_changed: bool, wall_seconds}

    Raises RegenError on missing files / scene id not found.
    """
    output_dir = Path(output_dir)
    script_path = output_dir / "vn_script.json"
    chars_path = output_dir / "characters.json"

    if not script_path.exists():
        raise RegenError(f"vn_script.json not found at {script_path}")

    script = VNScript.model_validate_json(script_path.read_text(encoding="utf-8"))
    characters = _load_characters(chars_path)

    # Find target scene
    idx = next(
        (i for i, s in enumerate(script.scenes) if s.id == scene_id),
        None,
    )
    if idx is None:
        raise RegenError(
            f"Scene '{scene_id}' not in vn_script.json. "
            f"Available: {[s.id for s in script.scenes]}"
        )
    target = script.scenes[idx]
    old_dialogue_count = len(target.dialogue)
    old_state_writes = dict(target.state_writes)

    # Reconstruct world_state at the target scene's START by walking
    # all earlier scenes' state_writes. Matches Sprint 9-3's forward-
    # only semantics: scene N sees state shaped by scenes 0..N-1.
    world_state: dict = {
        v.name: v.initial_value for v in script.world_variables
    }
    for earlier in script.scenes[:idx]:
        for k, v in earlier.state_writes.items():
            world_state[k] = v

    # Older scenes' summaries (Sprint 11-1) go as-is so the regen has
    # long-form context. Prior scenes' full dialogue goes into the window.
    settings = get_settings()
    window = settings.writer_context_window
    prior_scenes = (
        script.scenes[max(0, idx - window) : idx] if window > 0 else []
    )
    older_summaries: list[tuple[str, str]] = [
        (s.id, s.summary)
        for s in script.scenes[: max(0, idx - window)]
        if s.summary
    ]

    char_desc = _build_char_descriptions(characters)
    run_system_prompt = WRITER_SYSTEM + _build_character_bible(characters)

    logger.info(
        f"Regenerating scene '{scene_id}' (index {idx}/{len(script.scenes) - 1})"
    )

    t0 = time.perf_counter()
    updated = await _write_scene(
        target,
        script,
        char_desc,
        revision_feedback,
        str(output_dir),
        corpus=None,        # no re-load of RAG corpus for regen (cheap path)
        embedding_index=None,
        prior_scenes=prior_scenes,
        structure_issues=[],
        world_state=world_state,
        state_constraints="",
        lore_index=None,
        older_summaries=older_summaries,
        system_prompt=run_system_prompt,
    )
    wall = time.perf_counter() - t0

    # Phase 13-1 / Step 4: refire summary if enabled — the regenerated
    # dialogue is new, so any stored summary is stale. Without this,
    # downstream scenes reading `older_summaries` get the OLD scene's
    # summary, gradually drifting the Writer's narrative memory. Guard
    # by enable_scene_summarization so 6-scene demos don't pay Haiku.
    if settings.enable_scene_summarization:
        try:
            from vn_agent.agents.summarizer import dialogue_digest, summarize_scene
            current_hash = dialogue_digest(updated)
            if (
                updated.summary
                and updated.summary_dialogue_hash == current_hash
            ):
                pass  # unchanged dialogue (shouldn't happen after regen, but cheap)
            else:
                summary = await summarize_scene(updated)
                if summary:
                    updated = updated.model_copy(update={
                        "summary": summary,
                        "summary_dialogue_hash": current_hash,
                    })
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Summary refire skipped for {scene_id}: {e}")

    # Splice the regenerated scene back into the script
    new_scenes = list(script.scenes)
    new_scenes[idx] = updated

    # Apply state_writes to world_state snapshot for this scene
    scene_state_after = dict(world_state)
    for k, v in updated.state_writes.items():
        scene_state_after[k] = v

    # Phase 13-1 / Step 2: hard-truncate state_timeline and chapters.
    # Why hard-delete instead of warn-and-keep: leaving state_timeline[idx+1:]
    # lets Writer's next call read polluted post-splice state (affinity,
    # flags, items from the OLD branch of events). That's context poisoning.
    # Creator who wants to preserve the old branch should snapshot the whole
    # project directory (git commit or cp -r) rather than rely on in-place
    # persistence. Downstream chapters that include any scene-id past idx
    # are also dropped — their rollup references dialogue that no longer
    # reflects the intended narrative.
    new_timeline = list(script.state_timeline)[: idx + 1]
    if len(new_timeline) <= idx:
        # Timeline shorter than idx (edge case — e.g. old script without
        # state_timeline field). Pad with empty entries up to idx, then replace.
        while len(new_timeline) < idx:
            missing_scene = script.scenes[len(new_timeline)]
            new_timeline.append(StateTimelineEntry(
                scene_id=missing_scene.id, state_after={},
            ))
        new_timeline.append(StateTimelineEntry(
            scene_id=scene_id, state_after=dict(scene_state_after),
        ))
    else:
        new_timeline[idx] = StateTimelineEntry(
            scene_id=scene_id, state_after=dict(scene_state_after),
        )
    dropped_timeline = max(0, len(script.state_timeline) - (idx + 1))

    kept_scene_ids = {s.id for s in new_scenes[: idx + 1]}
    new_chapters = [
        ch for ch in getattr(script, "chapters", [])
        if all(sid in kept_scene_ids for sid in ch.scene_ids)
    ] if hasattr(script, "chapters") else []
    dropped_chapters = len(getattr(script, "chapters", [])) - len(new_chapters)

    if dropped_timeline or dropped_chapters:
        logger.warning(
            f"local_regen at '{scene_id}' (idx={idx}): hard-truncated "
            f"state_timeline (dropped {dropped_timeline} rows) "
            f"and chapters (dropped {dropped_chapters}). "
            f"Downstream scenes must be re-run to reflect changed state."
        )

    update_fields: dict = {
        "scenes": new_scenes,
        "state_timeline": new_timeline,
    }
    if hasattr(script, "chapters"):
        update_fields["chapters"] = new_chapters
    new_script = script.model_copy(update=update_fields)

    # Persist: updated vn_script.json + fresh snapshot
    script_path.write_text(
        new_script.model_dump_json(indent=2), encoding="utf-8",
    )
    _write_scene_snapshot(
        str(output_dir),
        scene=updated,
        world_state_after=scene_state_after,
        summary=updated.summary,
    )

    state_writes_changed = updated.state_writes != old_state_writes
    if state_writes_changed:
        logger.warning(
            f"Scene '{scene_id}' state_writes changed from {old_state_writes} "
            f"to {updated.state_writes}. Downstream scenes may need re-running — "
            f"NOT auto-invalidated by this v1."
        )

    return {
        "scene_id": scene_id,
        "old_dialogue_count": old_dialogue_count,
        "new_dialogue_count": len(updated.dialogue),
        "state_writes_changed": state_writes_changed,
        "wall_seconds": round(wall, 1),
    }


def _load_characters(chars_path: Path) -> dict[str, CharacterProfile]:
    if not chars_path.exists():
        logger.warning(f"{chars_path} not found — regenerating with empty cast")
        return {}
    raw = json.loads(chars_path.read_text(encoding="utf-8"))
    return {k: CharacterProfile.model_validate(v) for k, v in raw.items()}
