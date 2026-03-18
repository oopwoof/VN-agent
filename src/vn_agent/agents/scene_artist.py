"""Scene Artist Agent: Generates background images for scenes."""
from __future__ import annotations

import logging
from pathlib import Path

from vn_agent.agents.state import AgentState
from vn_agent.schema.script import VNScript, Scene
from vn_agent.services.llm import ainvoke_llm
from vn_agent.services.image_gen import generate_image

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a background artist for visual novels.
Generate detailed image prompts for scene backgrounds.
Style: painterly anime background art, wide aspect ratio composition, detailed environments.
"""


async def run_scene_artist(state: AgentState) -> dict:
    """SceneArtist node: generates background images for all scenes."""
    script = state["vn_script"]
    output_dir = state["output_dir"]

    if not script:
        return {}

    logger.info(f"SceneArtist: generating {len(script.scenes)} backgrounds")

    # Get unique backgrounds
    bg_ids = {s.background_id: s for s in script.scenes}

    updated_scenes = list(script.scenes)
    for i, scene in enumerate(updated_scenes):
        updated_scene = await _generate_background(scene, output_dir)
        updated_scenes[i] = updated_scene

    updated_script = script.model_copy(update={"scenes": updated_scenes})
    return {"vn_script": updated_script}


async def _generate_background(scene: Scene, output_dir: str) -> Scene:
    """Generate background image prompt and optionally the image."""
    user_prompt = f"""Create an image generation prompt for this scene background:

Scene: {scene.title}
Description: {scene.description}
Background ID: {scene.background_id}

Requirements:
- Painterly anime background art style
- Wide landscape composition (16:9 ratio feeling)
- Detailed environment, atmospheric lighting
- No characters in the image

Return a JSON object:
{{"prompt": "detailed image generation prompt here"}}"""

    response = await ainvoke_llm(SYSTEM_PROMPT, user_prompt)
    content = response.content if hasattr(response, 'content') else str(response)

    # Extract prompt
    import json, re
    bg_prompt = scene.description  # fallback
    json_match = re.search(r'\{.*?\}', content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            bg_prompt = data.get("prompt", bg_prompt)
        except json.JSONDecodeError:
            pass

    updated_scene = scene.model_copy(update={"background_prompt": bg_prompt})

    # Try to generate image
    file_path = Path(output_dir) / "game" / "images" / "backgrounds" / f"{scene.background_id}.png"
    try:
        await generate_image(bg_prompt, file_path)
        logger.info(f"Generated background: {scene.background_id}")
    except Exception as e:
        logger.warning(f"Could not generate background {scene.background_id}: {e}")

    return updated_scene
