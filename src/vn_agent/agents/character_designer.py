"""Character Designer Agent: Generates visual profiles for characters."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from vn_agent.agents.state import AgentState
from vn_agent.config import get_settings
from vn_agent.prompts.templates import CHARACTER_DESIGNER_SYSTEM
from vn_agent.schema.character import CharacterProfile, EmotionSprite, VisualProfile
from vn_agent.services.image_gen import generate_image
from vn_agent.services.llm import ainvoke_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = CHARACTER_DESIGNER_SYSTEM


async def run_character_designer(state: AgentState) -> dict:
    """CharacterDesigner node: creates visual profiles and optionally generates sprites."""
    characters = state["characters"]
    output_dir = state["output_dir"]

    if not characters:
        return {}

    logger.info(f"CharacterDesigner: designing {len(characters)} characters")

    char_ids = list(characters.keys())
    char_list = list(characters.values())

    results = await asyncio.gather(
        *[_design_character(char, output_dir) for char in char_list],
        return_exceptions=True,
    )

    updated_characters = {}
    all_errors = list(state.get("errors", []))
    for char_id, result in zip(char_ids, results):
        if isinstance(result, Exception):
            logger.error(f"Failed to design character {char_id}: {result}")
            updated_characters[char_id] = characters[char_id]
            all_errors.append(f"CharacterDesigner: {result}")
        else:
            updated_char, sprite_errors = result  # type: ignore[misc]
            updated_characters[char_id] = updated_char
            all_errors.extend(sprite_errors)

    return {"characters": updated_characters, "errors": all_errors}


async def _design_character(char: CharacterProfile, output_dir: str) -> tuple[CharacterProfile, list[str]]:
    """Design visual profile for a character.

    Returns a tuple of (updated_character, errors).
    """
    user_prompt = f"""Create a visual profile for this character:

Name: {char.name}
Role: {char.role}
Personality: {char.personality}
Background: {char.background}

Provide:
1. Art style (e.g. "anime style, soft watercolor, high quality")
2. Detailed appearance (hair, eyes, build, distinctive features) - be very specific for consistency
3. Default outfit description

Return as JSON:
{{
  "art_style": "...",
  "appearance": "very detailed description...",
  "default_outfit": "..."
}}"""

    settings = get_settings()
    visual_data: dict = {}

    # Try tool calling first (structured output via bind_tools)
    if settings.use_tool_calling:
        try:
            from vn_agent.services.tools import VisualProfileResult, ainvoke_with_tools

            result = await ainvoke_with_tools(
                SYSTEM_PROMPT, user_prompt, [VisualProfileResult],
                model=settings.llm_character_designer_model,
                caller=f"character_designer/{char.id}",
            )
            visual_data = result.model_dump()
        except Exception as e:
            logger.debug(f"Tool calling fallback for {char.id}: {e}")

    # Fallback to free-text JSON extraction
    if not visual_data:
        response = await ainvoke_llm(
            SYSTEM_PROMPT, user_prompt,
            model=settings.llm_character_designer_model,
            caller=f"character_designer/{char.id}",
        )
        content = response.content if hasattr(response, 'content') else str(response)
        visual_data = _parse_visual_profile(content)

    visual = VisualProfile(
        art_style=visual_data.get("art_style", "anime style, high quality"),
        appearance=visual_data.get("appearance", char.personality),
        default_outfit=visual_data.get("default_outfit", "casual clothes"),
    )

    # Generate sprites for key emotions
    sprites, sprite_errors = await _generate_sprites(char, visual, output_dir)
    visual = visual.model_copy(update={"sprites": sprites})

    return char.model_copy(update={"visual": visual}), sprite_errors


def _parse_visual_profile(content: str) -> dict:
    import json
    import re

    # 1. Try markdown code block
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 2. Try raw_decode from first {
    start = content.find('{')
    if start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(content, start)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # 3. Try full content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    return {}


async def _generate_sprites(
    char: CharacterProfile,
    visual: VisualProfile,
    output_dir: str,
) -> tuple[list[EmotionSprite], list[str]]:
    """Generate sprite images for key emotions.

    Returns a tuple of (sprites, errors).
    """
    key_emotions = ["neutral", "happy", "sad"]
    sprites = []
    errors: list[str] = []

    for emotion in key_emotions:
        image_id = f"{char.id}_{emotion}"
        file_path = f"images/characters/{char.id}/{emotion}.png"
        abs_path = Path(output_dir) / "game" / file_path

        prompt = (
            f"{visual.art_style}, {visual.appearance}, "
            f"{visual.default_outfit}, "
            f"{emotion} expression, full body, white background, "
            f"visual novel character sprite"
        )

        sprite = EmotionSprite(
            emotion=emotion,
            image_id=image_id,
            file_path=file_path,
            generation_prompt=prompt,
        )

        # Try to generate image; if fails, log and collect error
        try:
            await generate_image(prompt, abs_path)
            logger.info(f"Generated sprite: {image_id}")
        except Exception as e:
            logger.warning(f"Could not generate sprite {image_id}: {e}")
            errors.append(f"CharacterDesigner: sprite {image_id}: {e}")

        sprites.append(sprite)

    return sprites, errors
