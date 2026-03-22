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

    # Load corpus once for few-shot injection (avoid per-scene reload)
    corpus = None
    if settings.corpus_path:
        try:
            from vn_agent.eval.corpus import load_corpus

            corpus = load_corpus(Path(settings.corpus_path))
        except Exception as e:
            logger.debug(f"Corpus loading failed, few-shot disabled: {e}")

    # Write dialogue for each scene
    updated_scenes = []
    for scene in script.scenes:
        updated_scene = await _write_scene(
            scene, script, char_desc, revision_feedback, output_dir, corpus=corpus
        )
        updated_scenes.append(updated_scene)

    updated_script = script.model_copy(update={"scenes": updated_scenes})
    logger.info(f"Writer completed: dialogue written for {len(updated_scenes)} scenes")

    return {"vn_script": updated_script}


def _build_char_descriptions(characters: dict[str, CharacterProfile]) -> str:
    lines = ["Characters:\n"]
    for char_id, char in characters.items():
        lines.append(f"- {char_id} ({char.name}): {char.role}. {char.personality}")
    return "\n".join(lines)


async def _write_scene(
    scene: Scene,
    script: VNScript,
    char_descriptions: str,
    revision_feedback: str,
    output_dir: str = ".",
    corpus=None,
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

    user_prompt = f"""Write dialogue for this scene:

Scene ID: {scene.id}
Title: {scene.title}
Description: {scene.description}
{strategy_guidance}
{feedback_note}
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

    # Few-shot example injection (when corpus is passed in)
    if corpus:
        try:
            from vn_agent.eval.retriever import (
                format_examples,
                retrieve_examples,
            )

            examples = retrieve_examples(
                corpus, scene.narrative_strategy or "", k=settings.few_shot_k
            )
            few_shot_block = format_examples(examples)
            if few_shot_block:
                user_prompt += (
                    f"\n\nReference examples of '{scene.narrative_strategy}' strategy:\n"
                    f"{few_shot_block}"
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

    # Enforce dialogue line count bounds
    if len(dialogue) < settings.min_dialogue_lines:
        dialogue.append(DialogueLine(character_id=None, text=f"[{scene.title}]", emotion="neutral"))
        logger.warning(
            f"Scene {scene.id}: padded to {len(dialogue)} lines"
            f" (min={settings.min_dialogue_lines})"
        )
    if len(dialogue) > settings.max_dialogue_lines:
        dialogue = dialogue[:settings.max_dialogue_lines]
        logger.warning(f"Scene {scene.id}: truncated to {settings.max_dialogue_lines} lines")

    return scene.model_copy(update={"dialogue": dialogue})


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
