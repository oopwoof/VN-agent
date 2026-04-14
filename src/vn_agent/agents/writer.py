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
    output_dir = state.get("output_dir", ".")

    if not script:
        return {"errors": state.get("errors", []) + ["Writer: No script found in state"]}

    settings = get_settings()
    logger.info(f"Writer starting: {len(script.scenes)} scenes to write")

    # Build character descriptions for context
    char_desc = _build_char_descriptions(characters)

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

    # Write dialogue for each scene
    updated_scenes = []
    for scene in script.scenes:
        updated_scene = await _write_scene(
            scene, script, char_desc, revision_feedback, output_dir,
            corpus=corpus, embedding_index=embedding_index,
        )
        updated_scenes.append(updated_scene)

    updated_script = script.model_copy(update={"scenes": updated_scenes})
    logger.info(f"Writer completed: dialogue written for {len(updated_scenes)} scenes")

    return {"vn_script": updated_script}


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

    user_prompt = f"""Write dialogue for this scene:

Scene ID: {scene.id}
Title: {scene.title}
Description: {scene.description}
{strategy_guidance}
{feedback_note}{transition_block}
Characters present: {', '.join(scene.characters_present)}
Music mood: {scene.music.mood.value if scene.music else 'none'}

{char_descriptions}

Story context: {script.description}

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
                user_prompt += (
                    f"\n\nReference examples of '{strategy_label}' strategy:\n"
                    f"{few_shot_block}"
                )
                # Surface which corpus items landed in the prompt so we can
                # reason about RAG quality after the run (instead of guessing).
                ex_ids = [getattr(e, "id", "?") for e in examples]
                ex_strats = [getattr(e, "strategy", "?") for e in examples]
                logger.info(
                    f"Writer[{scene.id}]: few-shot injected for '{strategy_label}' — "
                    f"{len(examples)} examples: ids={ex_ids} strategies={ex_strats}"
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

    response = await ainvoke_llm(
        SYSTEM_PROMPT, user_prompt,
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
