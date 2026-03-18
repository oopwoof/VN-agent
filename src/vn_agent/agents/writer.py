"""Writer Agent: Creates dialogue for each scene."""
from __future__ import annotations

import logging
from pydantic import BaseModel, Field

from vn_agent.agents.state import AgentState
from vn_agent.schema.script import VNScript, Scene, DialogueLine
from vn_agent.schema.character import CharacterProfile
from vn_agent.services.llm import ainvoke_llm
from vn_agent.strategies.narrative import get_strategy
from vn_agent.config import get_settings
from vn_agent.agents.director import _extract_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a visual novel writer. Your job is to write compelling dialogue for scenes.

You will receive a scene description and list of characters, and you must write:
1. Engaging, character-consistent dialogue
2. Natural transitions between dialogue lines
3. Narration lines (character_id: null) for scene setting and inner thoughts
4. Emotional states for each line

Rules:
- Character IDs must match exactly the provided character list
- Each dialogue line needs: character_id (or null for narration), text, emotion
- Emotions: neutral, happy, sad, angry, surprised, scared, thoughtful, loving, determined
- Write natural, authentic dialogue that serves the narrative strategy
- Keep lines concise (1-3 sentences each)
"""


async def run_writer(state: AgentState) -> dict:
    """Writer node: fills in dialogue for all scenes."""
    script = state["vn_script"]
    characters = state["characters"]
    revision_feedback = state.get("review_feedback", "")

    if not script:
        return {"errors": state.get("errors", []) + ["Writer: No script found in state"]}

    settings = get_settings()
    logger.info(f"Writer starting: {len(script.scenes)} scenes to write")

    # Build character descriptions for context
    char_desc = _build_char_descriptions(characters)

    # Write dialogue for each scene
    updated_scenes = []
    for scene in script.scenes:
        updated_scene = await _write_scene(scene, script, char_desc, revision_feedback)
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
) -> Scene:
    """Write dialogue for a single scene."""
    settings = get_settings()
    strategy = get_strategy(scene.narrative_strategy or "")
    strategy_guidance = f"Narrative strategy: {strategy.description}\n{strategy.guidance}" if strategy else ""

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

    response = await ainvoke_llm(SYSTEM_PROMPT, user_prompt)
    content = response.content if hasattr(response, 'content') else str(response)

    # Parse dialogue lines
    dialogue = _parse_dialogue(content, scene)
    return scene.model_copy(update={"dialogue": dialogue})


def _parse_dialogue(content: str, scene: Scene) -> list[DialogueLine]:
    """Parse JSON dialogue from LLM response."""
    import json, re

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
