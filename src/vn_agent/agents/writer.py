"""Writer Agent: Creates dialogue for each scene."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC
from pathlib import Path
from typing import Any

from vn_agent.agents.director import _save_debug_raw
from vn_agent.agents.state import AgentState
from vn_agent.agents.writer_orchestrator import (
    compute_waves,
    group_scenes_by_chapter,
)
from vn_agent.config import get_settings
from vn_agent.prompts.templates import WRITER_SYSTEM, strip_thinking
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import (
    Chapter,
    DialogueLine,
    Scene,
    StateTimelineEntry,
    VNScript,
)
from vn_agent.services.llm import ainvoke_llm
from vn_agent.strategies.narrative import get_strategy

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = WRITER_SYSTEM

# Phase 13-2 Step 4b-5: shared-state concurrency guard.
# rag_retrievals.jsonl is the only file written by more than one
# coroutine within a Writer run (per-scene snapshots / debug raw
# files / scene_*.json are keyed by scene_id and never collide).
# Parallel waves call _append_rag_record concurrently — without a
# lock, simultaneous f.write() calls in TEXT mode can interleave
# at the encoder boundary for >PIPE_BUF UTF-8 payloads (Chinese
# themes regularly produce ~700-byte records). Lazy-init so we
# don't bind the lock to a loop that doesn't exist yet at import.
_rag_lock: asyncio.Lock | None = None


def _get_rag_lock() -> asyncio.Lock:
    """Return the module-level rag_records.jsonl lock, creating it
    on first call (after the event loop is running)."""
    global _rag_lock
    if _rag_lock is None:
        _rag_lock = asyncio.Lock()
    return _rag_lock


async def run_writer(state: AgentState) -> dict:
    """Writer node: fills in dialogue for all scenes."""
    script = state["vn_script"]
    characters = state["characters"]
    revision_feedback = state.get("review_feedback", "")
    # Sprint 7-5: StructureReviewer feedback (outline-level issues, especially
    # branch intent misalignment) surfaced so Writer can be more careful when
    # setting up choice points.
    # Phase 13-2 Step 4e/4 (Gemini hardening BLOCKER #e): read ONLY
    # structure_review_issues (the latest snapshot). state["warnings"]
    # accumulates across retry rounds + advisory findings; concatenating
    # both would feed Writer up to 4× duplicate messages and blow up
    # the per-scene prompt budget. structure_review_issues already
    # contains every advisory finding from the LATEST audit (it's
    # `[f.message for f in result.findings]` in structure_reviewer.py
    # which doesn't filter by requires_retry), so Writer still sees
    # advisory context — just without duplicates.
    structure_issues = list(state.get("structure_review_issues", []) or [])
    # Sprint 9-3 + Gemini-review fix: seed symbolic state from the
    # declared initial_values on EVERY Writer invocation so a revision
    # loop doesn't inherit the end-of-story state from the previous
    # attempt. Earlier versions read state["world_state"] which, after
    # the first Writer pass, contained the final state — causing scene
    # 1 on retry to see mid-story state values.
    world_state: dict = {}
    if state.get("vn_script") and state["vn_script"].world_variables:
        world_state = {
            v.name: v.initial_value for v in state["vn_script"].world_variables
        }
    state_constraints = state.get("state_constraints", "")
    output_dir = state.get("output_dir", ".")

    if not script:
        return {"errors": state.get("errors", []) + ["Writer: No script found in state"]}

    settings = get_settings()
    logger.info(f"Writer starting: {len(script.scenes)} scenes to write")

    # Build character descriptions for context
    char_desc = _build_char_descriptions(characters)
    # Sprint 11-2: per-run system prompt = WRITER_SYSTEM + Character Bible.
    # Identical across all scenes → Sprint 8-4 prompt caching caches the
    # whole thing (> 1500 chars) for a 5-min TTL. Amortizes across the
    # 6-18 Writer calls in a run (incl. revision loops).
    #
    # v4 P1-3: prepend dynamic guidelines from the Reflection Agent (if any).
    # The block is idempotent — cached alongside the rest of the system
    # prompt suffix — and empty when no dynamic_guidelines.json exists.
    dynamic_block = ""
    try:
        from vn_agent.feedback.reflection import format_guidelines_for_prompt, load_guidelines
        guidelines_report = load_guidelines()
        dynamic_block = format_guidelines_for_prompt(guidelines_report)
        if dynamic_block:
            logger.info(
                f"Writer: applying {len(guidelines_report.rules)} dynamic guideline(s) "
                f"from {guidelines_report.generated_at}"
            )
    except Exception as e:  # noqa: BLE001 — flywheel is opt-in, never blocks Writer
        logger.debug(f"Dynamic guidelines load failed: {e}")

    run_system_prompt = SYSTEM_PROMPT + _build_character_bible(characters)
    if dynamic_block:
        run_system_prompt = f"{run_system_prompt}\n\n{dynamic_block}\n"

    # Load corpus + optional embedding index for few-shot injection
    corpus = None
    embedding_index = None
    if settings.corpus_path:
        try:
            from vn_agent.eval.corpus_loader import load_merged_corpus

            sessions_dir = Path(settings.sessions_dir) if settings.sessions_dir else None
            corpus = load_merged_corpus(Path(settings.corpus_path), sessions_dir)

            # Try semantic retrieval (requires [rag] extras)
            if settings.use_semantic_retrieval:
                embedding_index = _build_or_load_embedding_index(corpus, settings)
        except Exception as e:
            logger.debug(f"Corpus loading failed, few-shot disabled: {e}")

    # Sprint 10-2: lore retrieval index — per-run, in-memory, extracted
    # from Director outputs (chars + locations + world_vars + premise).
    # Phase 13-1 / Step 3: index now also carries always_entities (premise +
    # main characters) and chapter_entities (world_vars + secondaries)
    # separately so Writer can place them in the cached system prefix
    # instead of competing for scene-level top-k slots.
    lore_index = None
    always_lore_block = ""
    chapter_lore_block = ""
    if settings.use_lore_retrieval:
        try:
            from vn_agent.eval.lore import build_lore_index, format_lore_block

            # v4 P0: creator-uploaded RAG chunks (md/pdf/docx and later
            # web-search results) join the scene-scope retrieval pool.
            # Only enabled when the pipeline is running under a web job —
            # CLI paths pass through with no uploads.
            user_upload_entities: list = []
            job_id = state.get("job_id")
            if job_id:
                try:
                    from vn_agent.assets.upload_store import load_chunks

                    user_upload_entities = load_chunks(job_id)
                    if user_upload_entities:
                        logger.info(
                            f"Writer: {len(user_upload_entities)} user_upload "
                            f"chunks loaded for job {job_id}"
                        )
                except Exception as e:  # noqa: BLE001 — non-fatal
                    logger.debug(f"user_upload load failed for job {job_id}: {e}")

            lore_index = build_lore_index(
                script, characters, user_upload_entities=user_upload_entities,
            )
            if lore_index is not None:
                # Render the stable always + chapter blocks once per run.
                # Retrieved scene block is rendered per-scene in _write_scene
                # and now automatically includes any user_upload chunks that
                # cosine-match the scene context (they live in the FAISS pool
                # alongside scene-scope lore).
                always_lore_block, chapter_lore_block, _ = format_lore_block(
                    retrieved=[],
                    always_entities=getattr(lore_index, "always_entities", []),
                    chapter_entities=getattr(lore_index, "chapter_entities", []),
                )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Lore index build failed: {e}")

    # Phase 13-1 / Step 3: assemble the monolithic cache prefix.
    # system prompt + character bible + always-scope lore + chapter-scope
    # lore. Meets Anthropic's 1024-token cache-write threshold (enforced
    # in build_monolithic_prefix; falls back to no-cache on short runs
    # to avoid paying 1.25× write cost with no payoff).
    #
    # Phase 13-2 Step 4b-7 (Gemini review fix): expose a closure that
    # rebuilds the prefix with finalized_chapters injected. Orchestrators
    # call it after each chapter barrier so chapter rollups actually
    # reach the Writer prompt — pre-fix, finalized_chapters was always
    # None and the rollup work landed in JSON only.
    from vn_agent.prompts.cached_prefix import build_monolithic_prefix

    raw_system_prompt = run_system_prompt  # WRITER_SYSTEM + Character Bible

    def _rebuild_prefix(
        finalized: list[Chapter] | None,
    ) -> tuple[str, bool]:
        return build_monolithic_prefix(
            system_prompt=raw_system_prompt,
            always_lore=always_lore_block,
            chapter_lore=chapter_lore_block,
            finalized_chapters=finalized,
        )

    cached_prefix_text, _enable_1h_cache = _rebuild_prefix(None)
    # Overwrite run_system_prompt with the monolithic prefix so all Writer
    # calls downstream (_write_scene, _regenerate_short_dialogue) see the
    # same text. Whether it actually caches is governed by _enable_1h_cache.
    run_system_prompt = cached_prefix_text

    rollup_enabled = (
        settings.enable_chapter_rollup
        and len(script.scenes) >= settings.chapter_rollup_min_scenes
    )

    # Phase 13-2 Step 4b-4: route between sequential and parallel paths.
    # Sequential (max_concurrent=1, default) is byte-identical to pre-4b
    # behavior. Parallel (>1) requires thinking_fanout + consume (enforced
    # at Settings construction in config._require_thinking_for_parallel_writer).
    if settings.writer_max_concurrent > 1:
        logger.info(
            f"Writer: parallel path with max_concurrent="
            f"{settings.writer_max_concurrent}"
        )
        updated_scenes, state_timeline, chapters_list = await _run_scenes_parallel(
            script=script, characters=characters, settings=settings,
            world_state=world_state,
            state_constraints=state_constraints, output_dir=output_dir,
            corpus=corpus, embedding_index=embedding_index,
            lore_index=lore_index,
            run_system_prompt=run_system_prompt,
            enable_1h_cache=_enable_1h_cache,
            rebuild_prefix=_rebuild_prefix,
            char_desc=char_desc, revision_feedback=revision_feedback,
            structure_issues=structure_issues,
            rollup_enabled=rollup_enabled,
        )
    else:
        updated_scenes, state_timeline, chapters_list = await _run_scenes_sequential(
            script=script, characters=characters, settings=settings,
            world_state=world_state,
            state_constraints=state_constraints, output_dir=output_dir,
            corpus=corpus, embedding_index=embedding_index,
            lore_index=lore_index,
            run_system_prompt=run_system_prompt,
            rebuild_prefix=_rebuild_prefix,
            enable_1h_cache=_enable_1h_cache,
            char_desc=char_desc, revision_feedback=revision_feedback,
            structure_issues=structure_issues,
            rollup_enabled=rollup_enabled,
        )

    updated_script = script.model_copy(update={
        "scenes": updated_scenes,
        "state_timeline": state_timeline,
        "chapters": chapters_list,
    })
    logger.info(f"Writer completed: dialogue written for {len(updated_scenes)} scenes")

    # Final authoritative checkpoint. The per-scene _flush_partial_vn_script
    # calls never carry chapters — final rollups can land after the last
    # scene's flush — so without this rewrite the on-disk vn_script.json
    # permanently lacks them (the first 50-scene dry run's disk artifact had
    # chapters: [] while run_metrics counted 5). Everything that loads the
    # file instead of the graph state (web resume, compiler, run analyzers)
    # must see the same script the graph returns.
    try:
        (Path(output_dir) / "vn_script.json").write_text(
            updated_script.model_dump_json(indent=2), encoding="utf-8",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Final vn_script.json checkpoint failed: {e}")

    return {
        "vn_script": updated_script,
        "world_state": world_state,
    }


async def _rollup_task(
    chapter_id: str,
    chapter_scenes: list[Scene],
    pinned_scene_ids: list[str],
    characters: dict,
    world_state_after: dict,
    settings: Any,
) -> Chapter | None:
    """Phase 13-1 / Step 6: async chapter rollup task.

    Returns a finalized Chapter (or None on Haiku failure — caller logs).
    summary_scene_hashes captures the members' summary_dialogue_hash so
    a future writer pass can detect "dialogue unchanged since rollup"
    and skip re-firing.
    """
    try:
        from vn_agent.agents.summarizer import dialogue_digest, rollup_chapter
        summary = await rollup_chapter(
            scenes=chapter_scenes,
            pinned_scene_ids=pinned_scene_ids,
            characters=characters,
            target_min_words=settings.rollup_target_min_words,
            target_max_words=settings.rollup_target_max_words,
        )
        return Chapter(
            chapter_id=chapter_id,
            scene_ids=[s.id for s in chapter_scenes],
            summary=summary,
            summary_scene_hashes=[
                s.summary_dialogue_hash or dialogue_digest(s)
                for s in chapter_scenes
            ],
            world_state_after=dict(world_state_after),
            pinned_scene_ids=list(pinned_scene_ids),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Chapter rollup for {chapter_id} failed: {e}")
        return None


async def _run_scenes_sequential(
    *,
    script: VNScript,
    characters: dict,
    settings: Any,
    world_state: dict,
    state_constraints: str,
    output_dir: str,
    corpus: Any,
    embedding_index: Any,
    lore_index: Any,
    run_system_prompt: str,
    enable_1h_cache: bool,
    rebuild_prefix: Any,
    char_desc: str,
    revision_feedback: str,
    structure_issues: list,
    rollup_enabled: bool,
) -> tuple[list[Scene], list[StateTimelineEntry], list[Chapter]]:
    """Phase 13-2 Step 4b-4: sequential Writer path.

    Byte-identical to the pre-4b-3 loop body — scenes processed one at a
    time in script order, world_state mutated in-place after each
    _process_scene return, state_timeline appended per scene, chapter
    rollup fired every chapter_rollup_every scenes as a fire-and-forget
    asyncio task awaited at the next boundary.

    This is the default path (writer_max_concurrent=1) and stays the
    fallback for short demos / revision loops where concurrency buys
    nothing. No thinking_fanout required.

    Phase 13-2 Step 4b-7 (Gemini review fix): after each chapter
    barrier (rollups awaited), call rebuild_prefix(chapters_list) so
    finalized chapter summaries reach the Writer prompt prefix on
    subsequent scenes.
    """
    updated_scenes: list[Scene] = []
    state_timeline: list[StateTimelineEntry] = []
    chapters_list: list[Chapter] = []
    pending_rollup_tasks: list[asyncio.Task] = []
    current_prefix = run_system_prompt
    current_enable_cache = enable_1h_cache

    for idx, scene in enumerate(script.scenes):
        # Await any pending rollups from the previous chapter boundary
        # before this scene's Writer call.
        if pending_rollup_tasks:
            done = await asyncio.gather(*pending_rollup_tasks, return_exceptions=True)
            new_finalized = False
            for result in done:
                if isinstance(result, Chapter):
                    chapters_list.append(result)
                    new_finalized = True
                elif isinstance(result, Exception):
                    logger.debug(f"Chapter rollup task raised: {result}")
            pending_rollup_tasks.clear()
            # 4b-7: rebuild prefix so chapter rollup lands in next scene's prompt.
            if new_finalized and rebuild_prefix is not None:
                current_prefix, current_enable_cache = rebuild_prefix(chapters_list)

        window = settings.writer_context_window
        prior_scenes = (
            updated_scenes[max(0, idx - window) : idx] if window > 0 else []
        )
        older_summaries: list[tuple[str, str]] = []
        if window > 0:
            older_summaries = [
                (s.id, s.summary)
                for s in updated_scenes[: max(0, idx - window)]
                if s.summary
            ]

        updated_scene = await _process_scene(
            scene=scene,
            script=script,
            char_desc=char_desc,
            revision_feedback=revision_feedback,
            structure_issues=structure_issues,
            prior_scenes=prior_scenes,
            older_summaries=older_summaries,
            world_state_snapshot=dict(world_state),
            state_constraints=state_constraints,
            output_dir=output_dir,
            corpus=corpus,
            embedding_index=embedding_index,
            lore_index=lore_index,
            system_prompt=current_prefix,
            enable_1h_cache=current_enable_cache,
            settings=settings,
            characters=characters,
        )
        updated_scenes.append(updated_scene)

        for var, value in updated_scene.state_writes.items():
            world_state[var] = value

        state_timeline.append(StateTimelineEntry(
            scene_id=updated_scene.id,
            state_after=dict(world_state),
        ))

        # v4 P0-resume: flush partial vn_script.json + characters.json so a
        # downstream hang (Reviewer / revision loop) still leaves recoverable
        # dialogue on disk. Best-effort; runs after every completed scene.
        _flush_partial_vn_script(
            output_dir=output_dir,
            base_script=script,
            updated_scenes=updated_scenes,
            characters=characters,
            state_timeline=state_timeline,
        )
        _publish_scene_ready(updated_scene)

        if rollup_enabled and (idx + 1) % settings.chapter_rollup_every == 0:
            chapter_start = idx + 1 - settings.chapter_rollup_every
            chapter_scenes = updated_scenes[chapter_start : idx + 1]
            chapter_id = f"ch{len(chapters_list) + len(pending_rollup_tasks) + 1:02d}"
            chapter_scene_id_set = {s.id for s in chapter_scenes}
            pinned: set[str] = set()
            for future_scene in script.scenes[idx + 1 :]:
                for dep in getattr(future_scene, "context_deps", None) or []:
                    if dep.ref_type == "scene" and dep.ref_id in chapter_scene_id_set:
                        pinned.add(dep.ref_id)
            ch_state = dict(world_state)
            pending_rollup_tasks.append(asyncio.create_task(
                _rollup_task(chapter_id, chapter_scenes, sorted(pinned),
                             characters, ch_state, settings),
            ))

    if pending_rollup_tasks:
        done = await asyncio.gather(*pending_rollup_tasks, return_exceptions=True)
        for result in done:
            if isinstance(result, Chapter):
                chapters_list.append(result)
            elif isinstance(result, Exception):
                logger.debug(f"Final chapter rollup task raised: {result}")
        pending_rollup_tasks.clear()

    return updated_scenes, state_timeline, chapters_list


async def _run_scenes_parallel(
    *,
    script: VNScript,
    characters: dict,
    settings: Any,
    world_state: dict,
    state_constraints: str,
    output_dir: str,
    corpus: Any,
    embedding_index: Any,
    lore_index: Any,
    run_system_prompt: str,
    enable_1h_cache: bool,
    rebuild_prefix: Any,
    char_desc: str,
    revision_feedback: str,
    structure_issues: list,
    rollup_enabled: bool,
) -> tuple[list[Scene], list[StateTimelineEntry], list[Chapter]]:
    """Phase 13-2 Step 4b-4 + 4b-7 (Gemini review fix): parallel Writer
    path (fanout-sync-fanout).

    Structure: chapter barrier outer loop → wave barrier inner loop →
    intra-wave asyncio.gather under Semaphore(writer_max_concurrent).

      - Chapter barrier: await prior chapter's rollup before the next
        chapter begins. Cross-chapter context_deps are satisfied by the
        barrier. After the barrier, rebuild_prefix(chapters_list) is
        called so finalized chapter summaries reach subsequent Writer
        prompts (4b-7 fix; pre-fix the rollup work landed in JSON only).
      - Wave barrier: intra-chapter scene dependencies are satisfied
        wave-by-wave. Scenes within a wave see the SAME world_state
        snapshot (no intra-wave peer visibility — that coordination
        happens upstream via thinking_fanout + cross_ref_sync).

    Sparse positional storage (4b-7 fix): updated_scenes is allocated
    as list[Scene | None] of len(script.scenes) and indexed by
    scene_pos. Same for state_timeline. This guarantees:
      (a) Final vn_script.scenes is in script order even when
          compute_waves produces script-discontinuous waves (e.g.
          wave 0 = [s0, s2], wave 1 = [s1] from a backward dep s1→s2).
      (b) prior_scenes for scene at position idx is built by slicing
          updated_scenes[idx-W:idx] then filtering Nones — gets the
          chronologically-correct prior context regardless of wave
          ordering.
      Pre-fix, both invariants broke whenever waves weren't position-
      contiguous; existing tests dodged this with diamond DAGs that
      produced contiguous waves by accident.

    Coupling enforced at Settings construction: writer_max_concurrent>1
    requires enable_thinking_fanout + writer_consume_thinking so parallel
    peers actually have a coordination signal.

    Failure policy: asyncio.gather(return_exceptions=True) so one scene's
    LLM failure does not cancel sibling waves. Failed scene falls back
    to its input (no dialogue) and is logged; the pipeline continues.
    NOTE: failed scene's state_writes are NOT applied — pre-existing
    inconsistency where scene.state_writes records "would have"
    semantics while world_state reflects "actually did". Tracked as
    follow-up; not fixed here to keep this commit scoped to Gemini's
    BLOCKERs.

    Rollup trigger (4b-7 hardening): count-based as in sequential, but
    only fires when the chunk's positional range is contiguously filled
    (no None gaps from scenes still pending in later waves). Tracked
    via next_rollup_at watermark.
    """
    n_scenes = len(script.scenes)
    updated_scenes_sparse: list[Scene | None] = [None] * n_scenes
    state_timeline_sparse: list[StateTimelineEntry | None] = [None] * n_scenes
    chapters_list: list[Chapter] = []
    pending_rollup_tasks: list[asyncio.Task] = []
    sem = asyncio.Semaphore(settings.writer_max_concurrent)

    scene_pos: dict[str, int] = {s.id: i for i, s in enumerate(script.scenes)}
    chapter_buckets = group_scenes_by_chapter(script)

    completed_count = 0
    next_rollup_at = settings.chapter_rollup_every if rollup_enabled else 0
    current_prefix = run_system_prompt
    current_enable_cache = enable_1h_cache

    async def _worker(scene: Scene, prior: list[Scene],
                      older: list[tuple[str, str]], snap: dict,
                      sys_prompt: str, enable_cache: bool) -> Scene:
        async with sem:
            return await _process_scene(
                scene=scene, script=script, char_desc=char_desc,
                revision_feedback=revision_feedback,
                structure_issues=structure_issues,
                prior_scenes=prior, older_summaries=older,
                world_state_snapshot=snap,
                state_constraints=state_constraints,
                output_dir=output_dir, corpus=corpus,
                embedding_index=embedding_index, lore_index=lore_index,
                system_prompt=sys_prompt,
                enable_1h_cache=enable_cache, settings=settings,
                characters=characters,
            )

    for chapter_scenes in chapter_buckets:
        # Chapter barrier: await all rollups from earlier chapters so
        # their Chapter entries land in chapters_list before this
        # chapter starts.
        if pending_rollup_tasks:
            done = await asyncio.gather(*pending_rollup_tasks, return_exceptions=True)
            new_finalized = False
            for result in done:
                if isinstance(result, Chapter):
                    chapters_list.append(result)
                    new_finalized = True
                elif isinstance(result, Exception):
                    logger.debug(f"Chapter rollup task raised: {result}")
            pending_rollup_tasks.clear()
            # 4b-7: rebuild prefix so finalized chapter rollups reach
            # subsequent Writer calls in this chapter and beyond.
            if new_finalized and rebuild_prefix is not None:
                current_prefix, current_enable_cache = rebuild_prefix(chapters_list)

        waves = compute_waves(chapter_scenes)
        logger.info(
            f"Writer parallel: chapter with {len(chapter_scenes)} scenes "
            f"→ {len(waves)} waves "
            f"(sizes={[len(w) for w in waves]})"
        )

        for wave_idx, wave in enumerate(waves):
            window = settings.writer_context_window

            # Snapshot state at wave start — all scenes in this wave see
            # the same world_state (no intra-wave peer visibility).
            state_snapshot_for_wave = dict(world_state)

            tasks = []
            for scene in wave:
                idx = scene_pos[scene.id]
                # Build prior context from sparse positional list — drop
                # Nones (current-wave peers + future waves), preserve
                # chronological order.
                if window > 0:
                    prior_slice = updated_scenes_sparse[max(0, idx - window):idx]
                    prior_scenes_for_this = [s for s in prior_slice if s is not None]
                    older_slice = updated_scenes_sparse[:max(0, idx - window)]
                    older_summaries_for_this = [
                        (s.id, s.summary)
                        for s in older_slice
                        if s is not None and s.summary
                    ]
                else:
                    prior_scenes_for_this = []
                    older_summaries_for_this = []
                tasks.append(_worker(
                    scene, prior_scenes_for_this,
                    older_summaries_for_this, state_snapshot_for_wave,
                    current_prefix, current_enable_cache,
                ))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Apply in script-positional order so state_writes land
            # deterministically regardless of which task finished first.
            ordered = sorted(
                zip(wave, results, strict=True),
                key=lambda pair: scene_pos[pair[0].id],
            )

            for scene, result in ordered:
                idx = scene_pos[scene.id]
                if isinstance(result, Exception):
                    logger.warning(
                        f"Writer[{scene.id}] failed in wave "
                        f"{wave_idx}: {result}; keeping input scene "
                        f"(no dialogue) and applying declared state_writes"
                    )
                    updated_scenes_sparse[idx] = scene
                    # 4b-8 fix: apply Director-declared state_writes even
                    # on Writer failure, so world_state stays consistent
                    # with scene.state_writes. Pre-fix, the scene's
                    # state_writes lived in the schema but never reached
                    # world_state — downstream state-dependent scenes saw
                    # a stale value while the persisted scene claimed the
                    # write happened. Director owns state authority; one
                    # missing dialogue body shouldn't fragment narrative
                    # state.
                    for var, value in scene.state_writes.items():
                        world_state[var] = value
                    state_timeline_sparse[idx] = StateTimelineEntry(
                        scene_id=scene.id, state_after=dict(world_state),
                    )
                    completed_count += 1
                    _publish_scene_ready(scene)
                    continue

                updated_scenes_sparse[idx] = result
                for var, value in result.state_writes.items():
                    world_state[var] = value
                state_timeline_sparse[idx] = StateTimelineEntry(
                    scene_id=result.id, state_after=dict(world_state),
                )
                completed_count += 1
                _publish_scene_ready(result)

            # v4 P0-resume: flush partial vn_script.json after every wave.
            # Uses the sparse-array-so-far; None entries in later slots are
            # dropped by _flush_partial_vn_script's overlay logic (base
            # scene from Director outline stays in place).
            _flush_partial_vn_script(
                output_dir=output_dir,
                base_script=script,
                updated_scenes=updated_scenes_sparse,
                characters=characters,
                state_timeline=[t for t in state_timeline_sparse if t is not None],
            )

            # After applying the whole wave, check rollup boundaries.
            # Only fire when the positional chunk is fully filled so
            # we never roll up a partial range.
            if rollup_enabled:
                while next_rollup_at <= completed_count:
                    chunk_start = next_rollup_at - settings.chapter_rollup_every
                    chunk = updated_scenes_sparse[chunk_start:next_rollup_at]
                    if any(s is None for s in chunk):
                        break  # gap — wait for later wave to fill
                    rollup_scenes_concrete = [s for s in chunk if s is not None]
                    chapter_id = (
                        f"ch{len(chapters_list) + len(pending_rollup_tasks) + 1:02d}"
                    )
                    rollup_scene_id_set = {s.id for s in rollup_scenes_concrete}
                    pinned: set[str] = set()
                    for future_scene in script.scenes[next_rollup_at:]:
                        for dep in getattr(future_scene, "context_deps", None) or []:
                            if (
                                dep.ref_type == "scene"
                                and dep.ref_id in rollup_scene_id_set
                            ):
                                pinned.add(dep.ref_id)
                    ch_state = dict(world_state)
                    pending_rollup_tasks.append(asyncio.create_task(
                        _rollup_task(
                            chapter_id, rollup_scenes_concrete, sorted(pinned),
                            characters, ch_state, settings,
                        ),
                    ))
                    next_rollup_at += settings.chapter_rollup_every

    # Final barrier: await any rollups still pending from the last chapter.
    if pending_rollup_tasks:
        done = await asyncio.gather(*pending_rollup_tasks, return_exceptions=True)
        for result in done:
            if isinstance(result, Chapter):
                chapters_list.append(result)
            elif isinstance(result, Exception):
                logger.debug(f"Final chapter rollup task raised: {result}")
        pending_rollup_tasks.clear()

    # Concretize sparse arrays. Any remaining None means a scene was
    # never reached — shouldn't happen if compute_waves covers every
    # scene, but defensive: substitute the input scene + an empty
    # timeline entry rather than raising.
    updated_scenes: list[Scene] = []
    state_timeline: list[StateTimelineEntry] = []
    for i, s in enumerate(updated_scenes_sparse):
        if s is None:
            logger.warning(
                f"Writer parallel: scene at position {i} "
                f"({script.scenes[i].id}) was never processed; "
                f"using input scene as fallback"
            )
            updated_scenes.append(script.scenes[i])
            state_timeline.append(StateTimelineEntry(
                scene_id=script.scenes[i].id, state_after=dict(world_state),
            ))
        else:
            updated_scenes.append(s)
            entry = state_timeline_sparse[i]
            if entry is None:
                entry = StateTimelineEntry(
                    scene_id=s.id, state_after=dict(world_state),
                )
            state_timeline.append(entry)

    return updated_scenes, state_timeline, chapters_list


async def _process_scene(
    *,
    scene: Scene,
    script: VNScript,
    char_desc: str,
    revision_feedback: str,
    structure_issues: list,
    prior_scenes: list[Scene],
    older_summaries: list[tuple[str, str]],
    world_state_snapshot: dict,
    state_constraints: str,
    output_dir: str,
    corpus: Any,
    embedding_index: Any,
    lore_index: Any,
    system_prompt: str,
    enable_1h_cache: bool,
    settings: Any,
    characters: dict | None = None,
) -> Scene:
    """Phase 13-2 Step 4b-3: per-scene Writer worker.

    Extracted from the original run_writer loop body so Step 4b-4 can
    invoke it concurrently under asyncio.Semaphore(writer_max_concurrent).
    Sequential (default) and parallel paths both call this.

    Contract:
      - Pure-ish: returns the new Scene; does NOT mutate world_state_snapshot,
        state_timeline, chapters_list, pending_rollup_tasks, or any
        other orchestrator-level state.
      - File I/O to output_dir is per-scene (rag records keyed by
        scene_id, scene snapshot keyed by scene_id) so concurrent calls
        on different scenes don't collide — except shared rag_records.jsonl
        which Step 4b-5 guards with a lock.
      - LLM calls: Sonnet (_write_scene) and optionally Haiku
        (summarize_scene). Failures in summarization are caught + logged;
        the scene still returns with dialogue populated.

    The orchestrator is responsible for:
      - sliding-window prior_scenes / older_summaries computation
      - world_state mutation (apply updated_scene.state_writes after return)
      - state_timeline append
      - chapter rollup triggering / awaiting
    """
    # 1. Snapshot state_constraints onto the scene (AUDITS §2).
    if state_constraints:
        scene = scene.model_copy(
            update={"state_constraints_seen": state_constraints},
        )

    # 2. Write dialogue.
    updated_scene = await _write_scene(
        scene, script, char_desc, revision_feedback, output_dir,
        corpus=corpus, embedding_index=embedding_index,
        prior_scenes=prior_scenes,
        structure_issues=structure_issues,
        world_state=world_state_snapshot,
        state_constraints=state_constraints,
        lore_index=lore_index,
        older_summaries=older_summaries,
        system_prompt=system_prompt,
        force_cache=enable_1h_cache,
        cache_ttl="1h",
        characters=characters,
    )

    # 3. Compute world_state_after locally so the snapshot file records
    # post-write state — without mutating the caller's snapshot dict.
    world_state_after = dict(world_state_snapshot)
    for k, v in updated_scene.state_writes.items():
        world_state_after[k] = v

    # Log state_writes application (original location; orchestrator still
    # applies them separately to its authoritative world_state dict).
    if updated_scene.state_writes:
        logger.debug(
            f"Writer[{updated_scene.id}] applied state_writes: "
            f"{list(updated_scene.state_writes.keys())}"
        )

    # 4. Per-scene summarization (gated; cache-aware). Non-blocking.
    if (
        settings.enable_scene_summarization
        and len(script.scenes) >= settings.summarization_min_scenes
    ):
        try:
            from vn_agent.agents.summarizer import dialogue_digest, summarize_scene
            current_hash = dialogue_digest(updated_scene)
            if (
                updated_scene.summary
                and updated_scene.summary_dialogue_hash == current_hash
            ):
                logger.debug(
                    f"Writer[{updated_scene.id}] summary: cache hit "
                    f"(hash={current_hash})"
                )
            else:
                summary = await summarize_scene(updated_scene)
                if summary:
                    updated_scene = updated_scene.model_copy(update={
                        "summary": summary,
                        "summary_dialogue_hash": current_hash,
                    })
                    logger.debug(
                        f"Writer[{updated_scene.id}] summary: {summary[:60]}..."
                    )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Summarization skipped for {updated_scene.id}: {e}")

    # 5. Scene snapshot (best-effort per-scene file write).
    _write_scene_snapshot(
        output_dir,
        scene=updated_scene,
        world_state_after=world_state_after,
        summary=updated_scene.summary,
    )

    return updated_scene


def _format_thinking_block(thinking: Any) -> str:
    """Phase 13-2 Step 4a: render SceneThinking as Writer's own briefing.

    Called only when settings.writer_consume_thinking is True and
    scene.thinking is populated. The block is the Writer's "final
    briefing" — positioned immediately before the "write N dialogue
    lines" instruction, so it's the last thing the model sees.

    Structure is flat + labeled (no nested JSON dumps) because it's the
    Writer's own thinking phase output being fed back as guidance. Heavy
    visual separators ("--- ... ---") help Sonnet treat this as a
    load-bearing section rather than background context.

    Layout rationale:
      - Intent first: orient the whole scene before beats
      - Opening hook → beats → closing beat: temporal order
      - Callbacks injected with the 'what_lands' angle
      - Voice notes per-character (mid-scene reminders override anything
        in macro_reference.character_voice_charter)
      - Risks last — directional "don't do X" guardrails
    """
    parts = ["\n--- Your scene plan (from thinking phase) — use this ---"]
    if thinking.writing_intent:
        parts.append(f"Intent: {thinking.writing_intent}")
    if thinking.opening_hook:
        parts.append(f"Opening hook: {thinking.opening_hook}")
    if thinking.key_beats_expanded:
        parts.append("Beats (inflate into dialogue, in order):")
        for i, beat in enumerate(thinking.key_beats_expanded, 1):
            parts.append(f"  {i}. {beat}")
    if thinking.callback_plan:
        parts.append("Callbacks landing this scene:")
        for cb in thinking.callback_plan:
            angle = cb.what_lands.strip() or "(no angle note)"
            parts.append(f"  → [{cb.ref_scene_id}] {angle}")
    if thinking.voice_notes:
        parts.append("Voice notes (scene-specific, override global charter):")
        for cid, note in thinking.voice_notes.items():
            parts.append(f"  {cid}: {note}")
    if thinking.closing_beat:
        parts.append(f"Closing beat: {thinking.closing_beat}")
    if thinking.risks:
        parts.append("Avoid:")
        for risk in thinking.risks:
            parts.append(f"  × {risk}")
    parts.append("--- End plan ---\n")
    return "\n".join(parts)


def _format_graph_context(
    scene: Scene,
    script: VNScript,
    emitted_scene_ids: set[str],
    emitted_character_ids: set[str],
) -> str:
    """Phase 13-1 / Step 5: render Director-declared context_deps as a
    prompt block. Adds to emitted_*_ids sets so downstream blocks (recent
    window, cosine lore) can skip duplicates (canonical dedup).

    Empty deps list → returns "". Invalid deps (dangling refs) are silently
    skipped — StructureReviewer will have already flagged them in
    structure_feedback where they belong.
    """
    deps = getattr(scene, "context_deps", None) or []
    if not deps:
        return ""

    scene_by_id = {s.id: s for s in script.scenes}
    blocks: list[str] = []

    for dep in deps:
        header = f"=== [{dep.link_type}] {dep.reason} ==="

        if dep.ref_type == "scene":
            target = scene_by_id.get(dep.ref_id)
            if target is None:
                continue
            emitted_scene_ids.add(target.id)
            if dep.inject_as == "full_dialogue" and target.dialogue:
                lines = [
                    f"  {d.character_id or 'NARR'} ({d.emotion}): {d.text}"
                    for d in target.dialogue
                ]
                blocks.append(
                    f"{header}\n"
                    f"Previous scene [{target.id}] — {target.title}:\n"
                    + "\n".join(lines)
                )
            elif target.summary:
                blocks.append(f"{header}\n[{target.id}] {target.summary}")
            else:
                # No summary available — fall back to scene title + description
                blocks.append(
                    f"{header}\n[{target.id}] {target.title}: {target.description}"
                )

        elif dep.ref_type == "character_arc":
            cid = dep.ref_id.split(":", 1)[1] if ":" in dep.ref_id else dep.ref_id
            emitted_character_ids.add(cid)
            # "arc so far" = titles + summaries of prior scenes featuring the
            # character. Cheap to assemble from script; avoids re-querying RAG.
            arc_scenes = [
                s for s in script.scenes
                if cid in (s.characters_present or []) and s.id in {
                    scene_by_id[sid].id for sid in scene_by_id
                    if scene_by_id[sid].id != scene.id
                }
            ]
            # Keep only scenes before the current one
            scene_idx_map = {s.id: i for i, s in enumerate(script.scenes)}
            cur_idx = scene_idx_map.get(scene.id, len(script.scenes))
            arc_scenes = [s for s in arc_scenes if scene_idx_map.get(s.id, 99) < cur_idx]
            if arc_scenes:
                arc_lines = [
                    f"  [{s.id}] {s.title}: " + (s.summary or s.description)[:150]
                    for s in arc_scenes
                ]
                blocks.append(
                    f"{header}\n{cid}'s arc so far:\n" + "\n".join(arc_lines)
                )

        elif dep.ref_type == "world_var":
            var_name = dep.ref_id.split(":", 1)[1] if ":" in dep.ref_id else dep.ref_id
            # Pull current value from state_timeline
            timeline = getattr(script, "state_timeline", []) or []
            current_value: Any = None
            for entry in timeline:
                if var_name in entry.state_after:
                    current_value = entry.state_after[var_name]
            # Fallback to initial value if timeline hasn't touched it yet
            if current_value is None:
                for wv in script.world_variables:
                    if wv.name == var_name:
                        current_value = wv.initial_value
                        break
            blocks.append(
                f"{header}\nWorld variable [{var_name}] = {current_value!r}"
            )

        elif dep.ref_type == "location":
            bg_id = dep.ref_id.split(":", 1)[1] if ":" in dep.ref_id else dep.ref_id
            # Find first scene using this background — its description is location's
            loc_scene = next(
                (s for s in script.scenes if s.background_id == bg_id), None,
            )
            if loc_scene:
                blocks.append(
                    f"{header}\nLocation [{bg_id}]: {loc_scene.description}"
                )

        elif dep.ref_type == "motif":
            motif = dep.ref_id.split(":", 1)[1] if ":" in dep.ref_id else dep.ref_id
            # No registry — just surface Director's reason as the motif reminder
            blocks.append(f"{header}\nMotif [{motif}]: {dep.reason}")

    if not blocks:
        return ""
    return (
        "\n--- Narrative dependencies (Director-declared, "
        "≥0.7-confidence callbacks / arcs / state / motifs) ---\n"
        + "\n\n".join(blocks)
        + "\n--- End dependencies ---\n"
    )


def _build_char_descriptions(characters: dict[str, CharacterProfile]) -> str:
    """Writer needs personality + backstory to give characters distinct voice.

    Background is the big lever: without it Writer can't reference the
    lighthouse keeper's drowned father, the soldier's posting, etc. Cost is
    ~80 input tokens per character — trivial compared to the dialogue output.
    """
    lines = ["Characters:\n"]
    for char_id, char in characters.items():
        lines.append(f"- {char_id} ({char.name}): {char.role}")
        lines.append(f"    Personality: {char.personality}")
        if char.background:
            lines.append(f"    Background: {char.background}")
    return "\n".join(lines)


def _build_character_bible(characters: dict[str, CharacterProfile]) -> str:
    """Sprint 11-2: Character Bible — static per-run structured character
    reference block that's IDENTICAL across every scene within a run.

    Goes into the system prompt (not user prompt) so Anthropic prompt
    caching (Sprint 8-4, cache_control=ephemeral) amortizes the cost
    across all 6-18 Writer calls within a run. First call pays 1.25× on
    the Bible tokens; scenes 2+ pay 0.1×. Break-even at 1.2 calls; huge
    win at 6+ scenes with revision loops.

    Includes immutability_score so Writer knows which character
    attributes are locked (Director-canonical) vs free to evolve.

    Empty characters dict → "" so system prompt stays unchanged.
    """
    if not characters:
        return ""
    lines = ["\n\n## Character Bible (Sprint 11-2, stable within this run)\n"]
    for cid, char in characters.items():
        lines.append(f"### {char.name} (id: {cid})")
        lines.append(f"Role: {char.role}")
        if char.personality:
            lines.append(f"Personality: {char.personality}")
        if char.background:
            lines.append(f"Background: {char.background}")
        # Surface locked attributes so Writer doesn't accidentally contradict
        locks = getattr(char, "immutability_score", {}) or {}
        locked = [k for k, v in locks.items() if v >= 8]
        if locked:
            lines.append(f"Locked attributes (must not contradict): {sorted(locked)}")
        lines.append("")
    return "\n".join(lines)


def _flush_partial_vn_script(
    output_dir: str,
    base_script,
    updated_scenes: list,
    characters: dict,
    state_timeline: list | None = None,
) -> None:
    """v4 P0-resume: rewrite vn_script.json + characters.json after each scene.

    Why: without this, if the pipeline hangs anywhere after Writer starts
    (Reviewer, revision loop, asset gen), the on-disk vn_script.json still
    only carries Director's outline. Users can't recover the dialogue they
    paid for — as happened with job 3cbbf260 (5 scenes / 66 dialogue lines
    / $1.08 nearly stranded).

    Behavior: merge `updated_scenes` into `base_script.scenes` positionally
    (index i in updated_scenes overrides base_script.scenes[i]), write the
    result to disk atomically. Never raises — best-effort like the
    per-scene snapshot writer. Called after every completed scene by the
    sequential + parallel writer loops.
    """
    import json as _json

    try:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Preserve Director's outline for scenes that haven't been written
        # yet; overlay the completed ones. Positional overlay keeps scene
        # ordering + count stable.
        merged_scenes = list(base_script.scenes)
        for i, sc in enumerate(updated_scenes):
            if sc is None:
                continue
            if i < len(merged_scenes):
                merged_scenes[i] = sc
            else:
                merged_scenes.append(sc)

        partial = base_script.model_copy(update={
            "scenes": merged_scenes,
            "state_timeline": state_timeline or [],
        })

        # Atomic write: temp file + rename. Prevents a crash mid-write
        # from leaving vn_script.json half-serialized (which would
        # kill --resume).
        tmp = out / "vn_script.json.tmp"
        tmp.write_text(partial.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(out / "vn_script.json")

        if characters:
            chars_data = {k: v.model_dump() for k, v in characters.items()}
            chars_tmp = out / "characters.json.tmp"
            chars_tmp.write_text(
                _json.dumps(chars_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            chars_tmp.replace(out / "characters.json")
    except Exception as e:  # noqa: BLE001 — best-effort; never break Writer
        logger.debug(f"Partial vn_script.json flush failed: {e}")


def _publish_scene_ready(scene: Scene) -> None:
    """v4 P2 ⑤: notify SSE subscribers a scene finished writing, so the
    frontend can start playback before the whole script is done. Best-effort
    — never raises, no-op if job_events isn't tracking a job in this context
    (CLI runs, tests)."""
    try:
        from vn_agent.services import job_events
        job_events.publish_scene_ready(scene.model_dump(mode="json"))
    except Exception as e:  # noqa: BLE001 — streaming is a nice-to-have, never break Writer
        logger.debug(f"Scene-ready publish failed: {e}")


def _write_scene_snapshot(
    output_dir: str,
    scene: Scene,
    world_state_after: dict,
    summary: str | None = None,
) -> None:
    """Sprint 11-4: persist a per-scene snapshot that downstream tooling
    (Sprint 12-4 local regen, replay, debug) can read to reconstruct the
    run state at that point in time.

    Written to <output_dir>/snapshots/<scene_id>.json as a single JSON
    object. Best-effort — any exception is logged at DEBUG, never
    raised. The primary pipeline artifact is still vn_script.json; this
    is supplementary.
    """
    import json
    from datetime import datetime
    from pathlib import Path

    try:
        snap_dir = Path(output_dir) / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "scene_id": scene.id,
            "title": scene.title,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "dialogue": [
                {"character_id": d.character_id, "text": d.text, "emotion": d.emotion}
                for d in scene.dialogue
            ],
            "narrative_strategy": scene.narrative_strategy,
            "state_reads": list(scene.state_reads),
            "state_writes": dict(scene.state_writes),
            "world_state_after": dict(world_state_after),
            "summary": summary,
        }
        (snap_dir / f"{scene.id}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Scene snapshot failed for {scene.id}: {e}")


async def _append_rag_record(
    output_dir: str,
    scene_id: str,
    strategy: str,
    query: str,
    examples,
) -> None:
    """Append one retrieval event to <output_dir>/rag_retrievals.jsonl.

    Each line is a self-contained JSON object. Future-you can grep any past
    run to audit which corpus sessions were shown to Writer for which scene
    — no re-run needed.

    Phase 13-2 Step 4b-5: async + module-level lock. The parallel Writer
    path may invoke this from N coroutines in the same wave; without
    serialization, large UTF-8 payloads (Chinese themes commonly hit
    ~700 bytes per record) can fragment when text-mode write() splits
    on encoder boundaries. The lock keeps the encode + write atomic.
    The actual file I/O remains sync inside the locked region — fast
    enough that swapping to aiofiles wouldn't pay back the dependency.
    """
    record = {
        "scene_id": scene_id,
        "strategy": strategy,
        "query": query,
        "retrieved": [
            {
                "id": getattr(ex, "id", "") or None,
                "title": getattr(ex, "title", ""),
                "strategy": getattr(ex, "strategy", None),
                "pivot_line_idx": getattr(ex, "pivot_line_idx", None),
                "pacing": getattr(ex, "pacing", None),
                "text_preview": (getattr(ex, "text", "") or "")[:400],
            }
            for ex in examples
        ],
    }
    line = json.dumps(record, ensure_ascii=False) + "\n"
    async with _get_rag_lock():
        try:
            path = Path(output_dir) / "rag_retrievals.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:  # noqa: BLE001 — debug artifact is best-effort
            logger.debug(f"Failed to persist RAG record for {scene_id}: {e}")


def _build_or_load_embedding_index(corpus, settings):
    """Build or load an embedding index for semantic retrieval. Returns None on failure."""
    try:
        from vn_agent.eval.embedder import EmbeddingIndex

        if settings.embedding_index_path:
            index_path = Path(settings.embedding_index_path)
            if index_path.exists():
                return EmbeddingIndex.load(index_path)

        index = EmbeddingIndex(model_name=settings.embedding_model)
        index.build(corpus)

        if settings.embedding_index_path:
            index.save(Path(settings.embedding_index_path))

        return index
    except ImportError:
        logger.debug("sentence-transformers not installed, semantic retrieval disabled")
        return None
    except Exception as e:
        logger.debug(f"Embedding index build failed: {e}")
        return None


async def _write_scene(
    scene: Scene,
    script: VNScript,
    char_descriptions: str,
    revision_feedback: str,
    output_dir: str = ".",
    corpus=None,
    embedding_index=None,
    prior_scenes: list[Scene] | None = None,
    structure_issues: list[str] | None = None,
    world_state: dict | None = None,
    state_constraints: str = "",
    lore_index=None,
    older_summaries: list[tuple[str, str]] | None = None,
    system_prompt: str | None = None,
    *,
    force_cache: bool = False,
    cache_ttl: str = "5m",
    characters: dict | None = None,
) -> Scene:
    """Write dialogue for a single scene.

    `characters` (keyword-only, optional) is the id→CharacterProfile dict —
    used only to enrich the flywheel injection query. Keyword-only because
    existing tests and chat_ops fakes call this positionally.
    """
    settings = get_settings()
    strategy = get_strategy(scene.narrative_strategy or "")
    strategy_guidance = (
        f"Narrative strategy: {strategy.description}\n{strategy.guidance}"
        if strategy else ""
    )

    feedback_note = ""
    if revision_feedback:
        feedback_note = f"\nIMPORTANT - Revision feedback to address:\n{revision_feedback}\n"

    # v4 P1-2: BM25-driven flywheel injection. Retrieves past 👎 reasons
    # relevant to THIS scene's context and renders them as "AVOID: ..."
    # lines. Empty string when there's no matching down-vote — never
    # blocks generation, only enriches it.
    try:
        from vn_agent.feedback import injector as _fb_injector
        _flywheel = _fb_injector.build_injection(
            scene, characters,
            extra_query=[script.theme, script.description],
        )
        if _flywheel.text:
            feedback_note = f"{feedback_note}\n{_flywheel.text}\n"
            logger.info(
                f"[Writer/{scene.id}] Flywheel injection: "
                f"{len(_flywheel.matched)} avoid rules (ids={_flywheel.matched_ids})"
            )
    except Exception as e:  # noqa: BLE001 — never block Writer on flywheel
        logger.debug(f"Flywheel injection failed for {scene.id}: {e}")

    # Sprint 7-5: pass StructureReviewer issues to Writer as context. Most
    # relevant for scenes with branches where intent-alignment failures were
    # flagged upstream; Writer can then write the choice-point setup more
    # deliberately so the option text matches what happens next.
    structure_note = ""
    if structure_issues:
        # Scope to issues mentioning this scene's id, plus one or two general
        # structural warnings so the prompt stays focused.
        mine = [i for i in structure_issues if scene.id in i]
        general = [i for i in structure_issues if scene.id not in i][:2]
        relevant = mine + general
        if relevant:
            structure_note = (
                "\n--- Structure review notes (from outline auditor) ---\n"
                + "\n".join(f"  - {i}" for i in relevant)
                + "\n"
            )

    # Sprint 11-1: older-scene summaries block — scenes too far back for
    # the raw-dialogue window (Sprint 7-2) appear here as compressed
    # ≤100-word summaries. Empty when not in long-form mode.
    older_summaries_block = ""
    if older_summaries:
        summary_lines = [
            f"  [{sid}] {summary[:150]}"
            for sid, summary in older_summaries
        ]
        older_summaries_block = (
            "\n\n--- Earlier scenes (summaries, chronological) ---\n"
            + "\n".join(summary_lines)
            + "\n--- End earlier scenes ---\n"
        )

    # Phase 13-1 / Step 5: narrative graph — Director-declared context_deps
    # pulled in BEFORE the recent window and cosine-retrieved blocks, because
    # the Director had whole-outline visibility when declaring these and they
    # carry explicit narrative intent (reasons). Canonical dedup: any scene
    # pulled here is tracked in `emitted_scene_ids` so the recent-window
    # block can skip it (Writer prompt must never carry the same scene twice).
    emitted_scene_ids: set[str] = set()
    emitted_character_ids: set[str] = set()
    graph_block = _format_graph_context(
        scene, script,
        emitted_scene_ids=emitted_scene_ids,
        emitted_character_ids=emitted_character_ids,
    )

    # Sprint 7-2: long-context — inject prior scenes' actual dialogue so
    # Writer can keep character voice coherent across scene boundaries. Only
    # populated when writer_context_window > 0.
    # Phase 13-1 / Step 5 dedup: scenes already pulled via graph above are
    # skipped here.
    prior_context_block = ""
    if prior_scenes:
        prior_blocks = []
        for ps in prior_scenes:
            if ps.id in emitted_scene_ids:
                continue  # already emitted via graph block (full_dialogue)
            dialog_lines = [
                f"  {d.character_id or 'NARR'} ({d.emotion}): {d.text}"
                for d in ps.dialogue
            ]
            strat = ps.narrative_strategy or "unspecified"
            prior_blocks.append(
                f"=== Previous scene: {ps.id} — {ps.title} "
                f"(strategy: {strat}) ===\n" + "\n".join(dialog_lines)
            )
            emitted_scene_ids.add(ps.id)
        if prior_blocks:
            prior_context_block = (
                "\n\n--- Recent story context (prior scene dialogue, "
                "for voice + continuity; do NOT copy lines) ---\n"
                + "\n\n".join(prior_blocks)
                + "\n--- End of prior context ---\n"
            )

    # Transition cards for cross-scene coherence (Sprint 6-1)
    transition_lines: list[str] = []
    if scene.entry_context:
        transition_lines.append(f"Entry context (what came before): {scene.entry_context}")
    if scene.emotional_arc:
        transition_lines.append(f"Emotional arc of this scene: {scene.emotional_arc}")
    if scene.exit_hook:
        transition_lines.append(f"Exit hook (set up the next scene with): {scene.exit_hook}")
    transition_block = "\n".join(transition_lines)
    if transition_block:
        transition_block = f"\n--- Transition Guidance ---\n{transition_block}\n"

    # Sprint 10-2 + Phase 13-1 Step 3: lore retrieval block — per-scene
    # top-k SCENE-scope facts. Always-scope (premise + main chars) and
    # chapter-scope (world_vars + secondary chars) are already inlined
    # into the cached system prefix at run_writer init; this block only
    # carries scene-local retrievals so the user message stays small.
    lore_block = ""
    if lore_index is not None:
        try:
            from vn_agent.eval.lore import format_lore_block

            query = scene.description or scene.title or scene.id
            hits = lore_index.search(
                query=query,
                k=settings.lore_k,
                strategy=None,
                pre_filter_strategy=False,
            )
            # Only render the retrieved (scene-scope) block — always +
            # chapter are already in system prefix, rendering them here
            # would duplicate content (violates Writer prompt dedup rule).
            _, _, lore_block = format_lore_block(
                retrieved=hits,
                always_entities=[],
                chapter_entities=[],
            )
            if lore_block:
                lore_block = f"\n{lore_block}\n"
                await _append_rag_record(
                    output_dir,
                    scene_id=scene.id,
                    strategy="__lore__",
                    query=query,
                    examples=hits,
                )
                logger.info(
                    f"Writer[{scene.id}]: lore INJECTED — "
                    f"{len(hits)} entities: "
                    f"{[getattr(h, 'id', '?') for h in hits]}"
                )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Lore retrieval skipped: {e}")

    # Sprint 9-3: state awareness block. Only injects when the scene
    # actually reads state variables, or when StateOrchestrator (9-6)
    # compiled narrative constraints. Scenes without state I/O get
    # nothing extra.
    state_block = ""
    if world_state and scene.state_reads:
        state_lines = [
            f"  {k} = {world_state[k]!r}"
            for k in scene.state_reads if k in world_state
        ]
        if state_lines:
            state_block += "\n--- Current world state (read-only) ---\n"
            state_block += "\n".join(state_lines)
            state_block += "\n"
    if scene.state_writes:
        state_block += (
            "\n--- State changes this scene makes (Director-declared) ---\n"
            + "\n".join(f"  {k} → {v!r}" for k, v in scene.state_writes.items())
            + "\nWrite dialogue consistent with these changes landing by scene end.\n"
        )
    if state_constraints:
        state_block += (
            "\n--- StateOrchestrator narrative constraints ---\n"
            f"{state_constraints}\n"
        )

    # Phase 13-2 Step 4a: consume scene.thinking when flag is on.
    # Renders the Writer's OWN plan from the thinking phase as the final
    # briefing — immediately before the "write dialogue now" instruction,
    # so it's the last signal Writer sees. Gated by writer_consume_thinking
    # so the default path is unchanged (and so we can A/B validate whether
    # thinking injection actually helps dialogue quality before Step 4b
    # invests in parallel writing infrastructure).
    thinking_block = ""
    if (
        getattr(settings, "writer_consume_thinking", False)
        and scene.thinking is not None
    ):
        thinking_block = _format_thinking_block(scene.thinking)

    user_prompt = f"""Write dialogue for this scene:

Scene ID: {scene.id}
Title: {scene.title}
Description: {scene.description}
{strategy_guidance}
{feedback_note}{structure_note}{transition_block}{graph_block}{lore_block}{state_block}
Characters present: {', '.join(scene.characters_present)}
Music mood: {scene.music.mood.value if scene.music else 'none'}

{char_descriptions}

Story context: {script.description}
{older_summaries_block}{prior_context_block}
{thinking_block}
Write {settings.min_dialogue_lines}-{settings.max_dialogue_lines} dialogue/narration lines.
Target 800-1500 words total dialogue/narration for this scene — aim for the
shorter end on transitional scenes, the longer end on emotional turning
points or revelations. Avoid repeating beats; every line should advance
the scene.

Return JSON array:
[
  {{"character_id": "char_id_or_null", "text": "dialogue text", "emotion": "neutral"}},
  ...
]

After dialogue, if branches exist, the player will choose:
{[b.text for b in scene.branches]}"""

    # Few-shot example injection: prefer semantic RAG, fallback to label filter
    if corpus or embedding_index:
        try:
            from vn_agent.eval.retriever import (
                format_examples,
                retrieve_examples,
                retrieve_examples_semantic,
            )

            strategy_label = scene.narrative_strategy or ""
            query = ""
            if embedding_index is not None:
                query = f"{scene.description} | strategy: {strategy_label}"
                examples = retrieve_examples_semantic(
                    embedding_index, query, strategy_label, k=settings.few_shot_k,
                    pre_filter_strategy=settings.rag_pre_filter_strategy,
                )
            else:
                examples = retrieve_examples(
                    corpus, strategy_label, k=settings.few_shot_k,
                )
            few_shot_block = format_examples(examples)
            if few_shot_block:
                # Persist retrieval record regardless of injection — RAG is
                # always auditable even when Writer won't actually see the
                # examples (literary mode).
                await _append_rag_record(
                    output_dir,
                    scene_id=scene.id,
                    strategy=strategy_label,
                    query=query,
                    examples=examples,
                )
                ex_strats = [getattr(e, "strategy", "?") for e in examples]

                # Sprint 7-1: only inject raw text-shot in action mode.
                # Literary mode relies on the physics-framework system prompt
                # and avoids style contamination from the VN corpus (which
                # skews action-heavy JRPG / galgame). Retrieval still runs so
                # audits + future reranker experiments have data.
                if settings.writer_mode == "action":
                    user_prompt += (
                        f"\n\nReference examples of '{strategy_label}' strategy:\n"
                        f"{few_shot_block}"
                    )
                    logger.info(
                        f"Writer[{scene.id}]: few-shot INJECTED (action mode) "
                        f"for '{strategy_label}' — {len(examples)} examples, "
                        f"strategies={ex_strats}"
                    )
                else:  # "literary"
                    logger.info(
                        f"Writer[{scene.id}]: few-shot retrieved but "
                        f"NOT INJECTED (literary mode) for '{strategy_label}' "
                        f"— {len(examples)} examples recorded to "
                        f"rag_retrievals.jsonl, strategies={ex_strats}"
                    )
        except Exception as e:
            logger.debug(f"Few-shot injection skipped: {e}")

    # Detect Chinese theme and add language hint
    is_chinese = bool(re.search(r'[\u4e00-\u9fff]', script.description or ""))
    if is_chinese:
        user_prompt += (
            "\n\nIMPORTANT: Write ALL dialogue text in Chinese (简体中文)."
            " Keep character_id as English identifiers."
        )

    # Sprint 11-2: prefer the caller-built system prompt (WRITER_SYSTEM +
    # Character Bible) so prompt caching amortizes the Bible cost across
    # all scenes in a run. Fall back to the static SYSTEM_PROMPT when
    # called outside the run_writer entry (legacy tests).
    # Phase 13-1 / Step 3: caller (run_writer) passes force_cache=True and
    # cache_ttl="1h" when the monolithic prefix meets the 1024-token
    # threshold (see prompts/cached_prefix.build_monolithic_prefix).
    effective_system = system_prompt if system_prompt else SYSTEM_PROMPT
    # Phase 13-3 M0-1: hard cap per-scene output to bound cost. Without
    # this, Writer is unbounded and the long tail (observed: 7205 tokens
    # at n=6 smoke) drives 50-scene cost past the $15 north star. The
    # word-count guidance baked into user_prompt biases the model toward
    # the typical band; max_tokens is the safety net.
    response = await ainvoke_llm(
        effective_system, user_prompt,
        model=settings.llm_writer_model,
        caller=f"writer/{scene.id}",
        cache_ttl=cache_ttl,
        force_cache=force_cache,
        max_tokens=settings.writer_max_tokens_per_scene,
    )
    content = response.content if hasattr(response, 'content') else str(response)

    _save_debug_raw(output_dir, f"writer_{scene.id}.txt", content)
    content = strip_thinking(content)

    # Parse dialogue lines
    dialogue = _parse_dialogue(content, scene)

    # Validate each line via Pydantic
    validated = []
    for d in dialogue:
        try:
            validated.append(DialogueLine.model_validate(d.model_dump()))
        except Exception:
            validated.append(d)
    dialogue = validated

    # Enforce dialogue line count bounds with smart regeneration fallback
    # (Sprint 6-8): when output is truncated, retry once with the successfully
    # parsed tail as context instead of inserting a placeholder that breaks
    # immersion.
    if len(dialogue) < settings.min_dialogue_lines:
        missing = settings.min_dialogue_lines - len(dialogue)
        regenerated = await _regenerate_short_dialogue(
            scene, dialogue, missing, settings, output_dir,
        )
        if regenerated:
            dialogue.extend(regenerated)
            logger.info(
                f"Scene {scene.id}: regenerated {len(regenerated)} continuation lines "
                f"(now {len(dialogue)}, min={settings.min_dialogue_lines})"
            )
        # If still short after retry, fall back to placeholder so pipeline proceeds
        if len(dialogue) < settings.min_dialogue_lines:
            dialogue.append(
                DialogueLine(character_id=None, text=f"[{scene.title}]", emotion="neutral")
            )
            logger.warning(
                f"Scene {scene.id}: padded to {len(dialogue)} lines "
                f"(min={settings.min_dialogue_lines}, regeneration incomplete)"
            )
    if len(dialogue) > settings.max_dialogue_lines:
        dialogue = dialogue[:settings.max_dialogue_lines]
        logger.warning(f"Scene {scene.id}: truncated to {settings.max_dialogue_lines} lines")

    return scene.model_copy(update={"dialogue": dialogue})


async def _regenerate_short_dialogue(
    scene: Scene,
    existing: list[DialogueLine],
    missing: int,
    settings,
    output_dir: str,
) -> list[DialogueLine]:
    """Continue a truncated dialogue by calling the LLM once more with the
    already-parsed tail as context.

    Returns the parsed continuation lines (possibly empty). Safe on any
    failure: returns [] so caller can fall back to the placeholder path.
    Does NOT retry beyond this one extra call to avoid infinite loops.
    """
    if not existing:
        # Nothing parsed at all — no context to continue from; caller falls back
        return []

    tail_ctx = "\n".join(
        f"  {d.character_id or 'NARR'}: {d.text}" for d in existing[-2:]
    )
    emotion_vocab = "neutral, happy, sad, angry, surprised, scared, thoughtful, loving, determined"
    user_prompt = (
        f"Scene '{scene.title}' dialogue was cut short. Continue with exactly "
        f"{missing} more line(s), matching the tone and character voices of "
        f"what already exists.\n\n"
        f"Last lines of the scene so far:\n{tail_ctx}\n\n"
        f"Characters allowed: {', '.join(scene.characters_present) or 'any declared'}\n"
        f"Emotions: {emotion_vocab}\n\n"
        f"Return JSON array only:\n"
        f'[{{"character_id": "id_or_null", "text": "...", "emotion": "neutral"}}]'
    )
    try:
        response = await ainvoke_llm(
            SYSTEM_PROMPT, user_prompt,
            model=settings.llm_writer_model,
            caller=f"writer/{scene.id}/continuation",
        )
        content = response.content if hasattr(response, "content") else str(response)
        _save_debug_raw(output_dir, f"writer_{scene.id}_continuation.txt", content)
        content = strip_thinking(content)
        parsed = _parse_dialogue(content, scene)
        # Guard: if continuation itself is empty, just return []; caller handles it
        return parsed[:missing]
    except Exception as e:
        logger.debug(f"Scene {scene.id}: continuation call failed ({e}), falling back")
        return []


def _to_dialogue_line(d: dict) -> DialogueLine | None:
    """Convert a parsed dict to a DialogueLine. Returns None if the dict
    doesn't carry a usable 'text' value — silently dropping malformed
    entries beats inserting a confusing placeholder mid-scene."""
    text = d.get("text")
    if not text or not isinstance(text, str):
        return None
    return DialogueLine(
        character_id=d.get("character_id"),
        text=text,
        emotion=d.get("emotion", "neutral") or "neutral",
    )


def _try_parse_array(text: str) -> list[DialogueLine] | None:
    """Try to parse `text` as a JSON array of DialogueLine dicts. Returns
    None if it's not a valid array; returns [] if it parsed but had no
    usable entries (caller decides whether that's acceptable)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    out = [_to_dialogue_line(d) for d in data if isinstance(d, dict)]
    return [d for d in out if d is not None]


def _extract_balanced_array(content: str, start: int) -> str | None:
    """Scan forward from `content[start]` (which must be '[') and return
    the substring up to and including the matching ']', tracking string
    state so brackets inside JSON strings don't confuse the balance count.

    Returns None if no balanced array is found before content ends — i.e.
    the model truncated mid-array.
    """
    if start < 0 or start >= len(content) or content[start] != "[":
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(content)):
        ch = content[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return content[start:i + 1]
    return None  # truncated


def _recover_objects(content: str, start: int) -> list[DialogueLine]:
    """Last-resort recovery: walk forward from `start` (typically the
    position of the array's '['), extract each top-level JSON object
    (`{...}`) that's bracket-balanced, and parse it independently.

    Tolerates a truncated final object — returns whatever objects we
    successfully parsed before the truncation point. This is what saves
    a scene when Sonnet hits max_tokens mid-dialogue: instead of losing
    all 14 lines because line 15's JSON is unclosed, we keep 14.
    """
    out: list[DialogueLine] = []
    i = start
    n = len(content)
    while i < n:
        if content[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        escape = False
        end = -1
        for j in range(i, n):
            ch = content[j]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end < 0:
            break  # truncated mid-object
        try:
            obj = json.loads(content[i:end + 1])
            if isinstance(obj, dict):
                line = _to_dialogue_line(obj)
                if line is not None:
                    out.append(line)
        except json.JSONDecodeError:
            pass  # skip malformed individual object, keep going
        i = end + 1
    return out


def _parse_dialogue(content: str, scene: Scene) -> list[DialogueLine]:
    """Parse JSON dialogue from LLM response.

    Phase 13-2 Step 4d (Gemini smoke-review BLOCKER #B): the prior parser
    was a single-stage best-of-three regex+raw_decode chain. When Sonnet
    output had ANY of the following, all three fell through to a 1-line
    placeholder, triggering Reviewer's mechanical_check (line count) and
    a wasteful revision loop:

      - multiple ```json...``` code blocks (model emitting "draft" then
        "final version" — first match could be a malformed early draft)
      - prose preamble between the array's opening '[' and the first '{'
      - a single malformed entry (e.g. unescaped quote in dialogue)
        invalidating the WHOLE array
      - max_tokens truncation mid-array (no closing ']')

    New strategy is a 5-stage cascade, each stage strictly more permissive
    than the last, terminating in object-by-object recovery so we keep
    every successfully parseable line even from a truncated array:

      Stage 1: every ```json...``` fenced array block, in order. First
               that parses wins. Beats the previous single-match regex.
      Stage 2: bracket-balanced extraction from the first '[' that
               actually starts a parseable array. Tolerates prose before
               and after, including '[neutral]' style emotion tags in
               narration.
      Stage 3: full content as JSON.
      Stage 4: object-by-object recovery from the first '['. Salvages
               truncated arrays and arrays with one bad entry.
      Stage 5: placeholder. Returned only when literally zero objects
               parsed.

    Each stage filters out None text via _to_dialogue_line so the
    placeholder is the LAST resort, not a fallback for any single-bad-
    entry case.
    """
    # Stage 1: every ```json...``` fenced block in order. Use bracket-
    # balanced extraction inside each so nested arrays in narration don't
    # break us. Pattern matches both ```json and bare ```.
    for fence_match in re.finditer(r"```(?:json|JSON)?\s*\n", content):
        body_start = fence_match.end()
        # Find the closing ``` (allow it to be missing — model may have
        # truncated; fall through to balanced extraction on body).
        close = content.find("```", body_start)
        body = content[body_start:close] if close != -1 else content[body_start:]
        # Inside the body, find a balanced array.
        arr_start = body.find("[")
        if arr_start != -1:
            balanced = _extract_balanced_array(body, arr_start)
            if balanced is not None:
                lines = _try_parse_array(balanced)
                if lines:
                    return lines

    # Stage 2: scan content for any '[' that starts a parseable
    # balanced array, ignoring '[neutral]' / '[scared]' single-token
    # bracket pairs that show up in Sonnet's prose draft.
    pos = 0
    while True:
        bracket = content.find("[", pos)
        if bracket == -1:
            break
        balanced = _extract_balanced_array(content, bracket)
        if balanced is not None:
            lines = _try_parse_array(balanced)
            if lines:
                return lines
        pos = bracket + 1

    # Stage 3: full content as JSON array (legacy fallback).
    full = _try_parse_array(content)
    if full:
        return full

    # Stage 4: object-by-object recovery from the first '['. Saves
    # truncated arrays and arrays with one bad entry.
    arr_start = content.find("[")
    if arr_start != -1:
        recovered = _recover_objects(content, arr_start + 1)
        if recovered:
            logger.info(
                f"Scene {scene.id}: array parse failed, recovered "
                f"{len(recovered)} dialogue line(s) via per-object "
                f"fallback"
            )
            return recovered

    # Stage 5: placeholder. Reviewer's mechanical_check will reject this
    # as too short — by design. The continuation regen path then fires a
    # second LLM call to fill in lines.
    logger.warning(f"Could not parse dialogue for scene {scene.id}, using placeholder")
    return [DialogueLine(character_id=None, text=f"[Scene: {scene.title}]", emotion="neutral")]
