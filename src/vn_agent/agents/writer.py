"""Writer Agent: Creates dialogue for each scene."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from vn_agent.agents.director import _save_debug_raw
from vn_agent.agents.state import AgentState
from vn_agent.config import get_settings
from vn_agent.prompts.templates import WRITER_SYSTEM, strip_thinking
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import DialogueLine, Scene, VNScript
from vn_agent.services.llm import ainvoke_llm
from vn_agent.strategies.narrative import get_strategy

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = WRITER_SYSTEM


async def run_writer(state: AgentState) -> dict:
    """Writer node: fills in dialogue for all scenes."""
    script = state["vn_script"]
    characters = state["characters"]
    revision_feedback = state.get("review_feedback", "")
    # Sprint 7-5: StructureReviewer feedback (outline-level issues, especially
    # branch intent misalignment) surfaced so Writer can be more careful when
    # setting up choice points.
    structure_issues = state.get("structure_review_issues", []) or []
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
    run_system_prompt = SYSTEM_PROMPT + _build_character_bible(characters)

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
    # Orthogonal to dialogue RAG: runs in BOTH literary and action modes
    # because factual context doesn't style-contaminate.
    lore_index = None
    if settings.use_lore_retrieval:
        try:
            from vn_agent.eval.lore import build_lore_index
            lore_index = build_lore_index(script, characters)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Lore index build failed: {e}")

    # Write dialogue for each scene. Sprint 7-2: pass prior_scenes for
    # long-context coherence — Writer can reference previous scenes' actual
    # dialogue, not just Director's entry_context one-liner.
    updated_scenes = []
    for idx, scene in enumerate(script.scenes):
        window = settings.writer_context_window
        prior_scenes = (
            updated_scenes[max(0, idx - window) : idx] if window > 0 else []
        )
        # Sprint 11-1: long-form memory — scenes BEFORE the window get
        # compressed to their per-scene summaries (from 11-1 post-scene
        # Haiku). No summary → not passed. In short runs this list is
        # always empty.
        older_summaries: list[tuple[str, str]] = []
        if window > 0:
            older_summaries = [
                (s.id, s.summary)
                for s in updated_scenes[: max(0, idx - window)]
                if s.summary
            ]
        updated_scene = await _write_scene(
            scene, script, char_desc, revision_feedback, output_dir,
            corpus=corpus, embedding_index=embedding_index,
            prior_scenes=prior_scenes,
            structure_issues=structure_issues,
            world_state=world_state,
            state_constraints=state_constraints,
            lore_index=lore_index,
            older_summaries=older_summaries,
            system_prompt=run_system_prompt,
        )
        updated_scenes.append(updated_scene)

        # Sprint 9-3: apply state_writes AFTER the scene is written so the
        # next scene sees the updated state. state_writes is DIRECTOR-owned
        # (declared in step2 via 9-2); Writer does NOT produce additional
        # writes via its JSON output — _parse_dialogue only extracts
        # DialogueLine, any "state_writes" key is silently dropped. This is
        # intentional: authority boundary keeps Director responsible for
        # state logic while Writer focuses on dialogue craft.
        if updated_scene.state_writes:
            for var, value in updated_scene.state_writes.items():
                world_state[var] = value
            logger.debug(
                f"Writer[{updated_scene.id}] applied state_writes: "
                f"{list(updated_scene.state_writes.keys())}"
            )

        # Sprint 11-1: fire per-scene summarization (Haiku) for long-form runs.
        # Gated by both config toggle and total-scene-count threshold so
        # short demos don't pay the extra Haiku cost.
        if (
            settings.enable_scene_summarization
            and len(script.scenes) >= settings.summarization_min_scenes
        ):
            try:
                from vn_agent.agents.summarizer import summarize_scene
                summary = await summarize_scene(updated_scene)
                if summary:
                    updated_scene = updated_scene.model_copy(
                        update={"summary": summary},
                    )
                    # Overwrite the scene we just appended so the summary sticks
                    updated_scenes[-1] = updated_scene
                    logger.debug(
                        f"Writer[{updated_scene.id}] summary: {summary[:60]}..."
                    )
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Summarization skipped for {updated_scene.id}: {e}")

        # Sprint 11-4: per-scene snapshot (scene, state_after, optional
        # summary). Foundation for Sprint 12-4 local regen. Best-effort.
        _write_scene_snapshot(
            output_dir,
            scene=updated_scene,
            world_state_after=world_state,
            summary=updated_scene.summary,
        )

    updated_script = script.model_copy(update={"scenes": updated_scenes})
    logger.info(f"Writer completed: dialogue written for {len(updated_scenes)} scenes")

    return {
        "vn_script": updated_script,
        "world_state": world_state,
    }


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
    from datetime import datetime, timezone
    from pathlib import Path

    try:
        snap_dir = Path(output_dir) / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "scene_id": scene.id,
            "title": scene.title,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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


def _append_rag_record(
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
    """
    import json
    from pathlib import Path

    try:
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
        path = Path(output_dir) / "rag_retrievals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
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
) -> Scene:
    """Write dialogue for a single scene."""
    settings = get_settings()
    strategy = get_strategy(scene.narrative_strategy or "")
    strategy_guidance = (
        f"Narrative strategy: {strategy.description}\n{strategy.guidance}"
        if strategy else ""
    )

    feedback_note = ""
    if revision_feedback:
        feedback_note = f"\nIMPORTANT - Revision feedback to address:\n{revision_feedback}\n"

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

    # Sprint 7-2: long-context — inject prior scenes' actual dialogue so
    # Writer can keep character voice coherent across scene boundaries. Only
    # populated when writer_context_window > 0.
    prior_context_block = ""
    if prior_scenes:
        prior_blocks = []
        for ps in prior_scenes:
            dialog_lines = [
                f"  {d.character_id or 'NARR'} ({d.emotion}): {d.text}"
                for d in ps.dialogue
            ]
            strat = ps.narrative_strategy or "unspecified"
            prior_blocks.append(
                f"=== Previous scene: {ps.id} — {ps.title} "
                f"(strategy: {strat}) ===\n" + "\n".join(dialog_lines)
            )
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

    # Sprint 10-2: lore retrieval block — per-scene top-k facts from the
    # Director-extracted lore index. Runs in BOTH writer modes because
    # facts (character backgrounds, location descriptions, world vars)
    # don't contaminate literary style the way raw VN dialogue few-shot
    # does. Absent lore index / index build failure → empty string, no-op.
    lore_block = ""
    if lore_index is not None:
        try:
            from vn_agent.eval.lore import format_lore_block

            query = scene.description or scene.title or scene.id
            # Plain .search without strategy pre-filter (entities have
            # strategy=None), hybrid FAISS+BM25 top-k.
            hits = lore_index.search(
                query=query,
                k=settings.lore_k,
                strategy=None,
                pre_filter_strategy=False,
            )
            lore_block = format_lore_block(hits)
            if lore_block:
                lore_block = f"\n{lore_block}\n"
                # Persist to rag_retrievals.jsonl with __lore__ sentinel
                # so audit can distinguish from dialogue RAG
                _append_rag_record(
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

    user_prompt = f"""Write dialogue for this scene:

Scene ID: {scene.id}
Title: {scene.title}
Description: {scene.description}
{strategy_guidance}
{feedback_note}{structure_note}{transition_block}{lore_block}{state_block}
Characters present: {', '.join(scene.characters_present)}
Music mood: {scene.music.mood.value if scene.music else 'none'}

{char_descriptions}

Story context: {script.description}
{older_summaries_block}{prior_context_block}

Write {settings.min_dialogue_lines}-{settings.max_dialogue_lines} dialogue/narration lines.
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
                _append_rag_record(
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
    effective_system = system_prompt if system_prompt else SYSTEM_PROMPT
    response = await ainvoke_llm(
        effective_system, user_prompt,
        model=settings.llm_writer_model,
        caller=f"writer/{scene.id}",
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


def _parse_dialogue(content: str, scene: Scene) -> list[DialogueLine]:
    """Parse JSON dialogue from LLM response."""
    # 1. Try markdown code block for array
    arr_block_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', content, re.DOTALL)
    if arr_block_match:
        try:
            lines_data = json.loads(arr_block_match.group(1))
            return [
                DialogueLine(
                    character_id=d.get("character_id"),
                    text=d.get("text", ""),
                    emotion=d.get("emotion", "neutral"),
                )
                for d in lines_data
            ]
        except (json.JSONDecodeError, KeyError):
            pass

    # 2. Try raw_decode from first [
    start = content.find('[')
    if start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(content, start)
            if isinstance(obj, list):
                return [
                    DialogueLine(
                        character_id=d.get("character_id"),
                        text=d.get("text", ""),
                        emotion=d.get("emotion", "neutral"),
                    )
                    for d in obj
                ]
        except (json.JSONDecodeError, KeyError):
            pass

    # 3. Try full content as JSON array
    try:
        lines_data = json.loads(content)
        if isinstance(lines_data, list):
            return [
                DialogueLine(
                    character_id=d.get("character_id"),
                    text=d.get("text", ""),
                    emotion=d.get("emotion", "neutral"),
                )
                for d in lines_data
            ]
    except (json.JSONDecodeError, KeyError):
        pass

    # Fallback: create placeholder
    logger.warning(f"Could not parse dialogue for scene {scene.id}, using placeholder")
    return [DialogueLine(character_id=None, text=f"[Scene: {scene.title}]", emotion="neutral")]
