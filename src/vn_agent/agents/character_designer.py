"""Character Designer Agent: Generates visual profiles for characters."""
from __future__ import annotations

import logging
from pathlib import Path

from vn_agent.agents.state import AgentState
from vn_agent.schema.character import CharacterProfile, VisualProfile, EmotionSprite
from vn_agent.services.llm import ainvoke_llm
from vn_agent.services.image_gen import generate_image

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a character visual designer for anime-style visual novels.
Given a character description, create a detailed visual profile for consistent image generation.
Be specific about: hair color/style, eye color, outfit, distinctive features.
"""


async def run_character_designer(state: AgentState) -> dict:
    """CharacterDesigner node: creates visual profiles and optionally generates sprites."""
    characters = state["characters"]
    output_dir = state["output_dir"]

    if not characters:
        return {}

    logger.info(f"CharacterDesigner: designing {len(characters)} characters")
    updated_characters = {}

    for char_id, char in characters.items():
        updated_char = await _design_character(char, output_dir)
        updated_characters[char_id] = updated_char

    return {"characters": updated_characters}


async def _design_character(char: CharacterProfile, output_dir: str) -> CharacterProfile:
    """Design visual profile for a character."""
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

    response = await ainvoke_llm(SYSTEM_PROMPT, user_prompt)
    content = response.content if hasattr(response, 'content') else str(response)

    visual_data = _parse_visual_profile(content)

    visual = VisualProfile(
        art_style=visual_data.get("art_style", "anime style, high quality"),
        appearance=visual_data.get("appearance", char.personality),
        default_outfit=visual_data.get("default_outfit", "casual clothes"),
    )

    # Generate sprites for key emotions
    sprites = await _generate_sprites(char, visual, output_dir)
    visual = visual.model_copy(update={"sprites": sprites})

    return char.model_copy(update={"visual": visual})


def _parse_visual_profile(content: str) -> dict:
    import json, re
    json_match = re.search(r'\{.*?\}', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


async def _generate_sprites(
    char: CharacterProfile,
    visual: VisualProfile,
    output_dir: str,
) -> list[EmotionSprite]:
    """Generate sprite images for key emotions."""
    key_emotions = ["neutral", "happy", "sad"]
    sprites = []

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

        # Try to generate image; if fails, log and continue with placeholder
        try:
            await generate_image(prompt, abs_path)
            logger.info(f"Generated sprite: {image_id}")
        except Exception as e:
            logger.warning(f"Could not generate sprite {image_id}: {e}")

        sprites.append(sprite)

    return sprites
