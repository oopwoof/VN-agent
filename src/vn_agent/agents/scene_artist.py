"""Scene Artist Agent: Generates background images for scenes."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from vn_agent.agents.state import AgentState
from vn_agent.config import get_settings
from vn_agent.prompts.templates import SCENE_ARTIST_SYSTEM
from vn_agent.schema.script import Scene
from vn_agent.services.image_gen import generate_image
from vn_agent.services.llm import ainvoke_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = SCENE_ARTIST_SYSTEM


async def run_scene_artist(state: AgentState) -> dict:
    """SceneArtist node: generates background images for all scenes."""
    script = state["vn_script"]
    output_dir = state["output_dir"]
    art_direction = state.get("art_direction", "")

    if not script:
        return {}

    logger.info(f"SceneArtist: generating {len(script.scenes)} backgrounds (style: {art_direction[:50]})")

    # Build a map: background_id -> scene (use first scene with that bg_id)
    unique_bgs: dict = {}
    for scene in script.scenes:
        if scene.background_id not in unique_bgs:
            unique_bgs[scene.background_id] = scene

    logger.info(f"SceneArtist: {len(unique_bgs)} unique backgrounds to generate")

    # Generate all unique backgrounds in parallel
    bg_ids = list(unique_bgs.keys())
    results = await asyncio.gather(
        *[_generate_background(scene, output_dir, art_direction) for scene in unique_bgs.values()],
        return_exceptions=True,
    )

    # Build a map from background_id -> generated background_prompt
    bg_prompt_map: dict[str, str | None] = {}
    all_errors = list(state.get("errors", []))
    for bg_id, result in zip(bg_ids, results):
        if isinstance(result, Exception):
            logger.error(f"Failed to generate background {bg_id}: {result}")
            bg_prompt_map[bg_id] = None
            all_errors.append(f"SceneArtist: background {bg_id}: {result}")
        else:
            bg_scene, bg_errors = result  # type: ignore[misc]
            bg_prompt_map[bg_id] = bg_scene.background_prompt
            all_errors.extend(bg_errors)

    # Apply the generated background_prompt back to all scenes sharing the same background_id
    updated_scenes = []
    for scene in script.scenes:
        prompt = bg_prompt_map.get(scene.background_id)
        if prompt is not None:
            updated_scenes.append(scene.model_copy(update={"background_prompt": prompt}))
        else:
            updated_scenes.append(scene)

    updated_script = script.model_copy(update={"scenes": updated_scenes})
    return {"vn_script": updated_script, "errors": all_errors}


async def _generate_background(
    scene: Scene, output_dir: str, art_direction: str = "",
) -> tuple[Scene, list[str]]:
    """Generate background image prompt and optionally the image.

    Returns a tuple of (updated_scene, errors).
    """
    style_line = art_direction if art_direction else "Painterly anime background art style"
    user_prompt = f"""Create an image generation prompt for this scene background:

Scene: {scene.title}
Description: {scene.description}
Background ID: {scene.background_id}

Requirements:
- Art style: {style_line}
- Wide landscape composition (16:9 ratio feeling)
- Detailed environment, atmospheric lighting
- No characters in the image

Return a JSON object:
{{"prompt": "detailed image generation prompt here"}}"""

    settings = get_settings()
    bg_prompt = scene.description  # fallback

    # Try tool calling first (structured output via bind_tools)
    if settings.use_tool_calling:
        try:
            from vn_agent.services.tools import BackgroundPrompt, ainvoke_with_tools

            result = await ainvoke_with_tools(
                SYSTEM_PROMPT, user_prompt, [BackgroundPrompt],
                model=settings.llm_scene_artist_model,
                caller=f"scene_artist/{scene.background_id}",
            )
            bg_prompt = result.prompt  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug(f"Tool calling fallback for {scene.background_id}: {e}")
            bg_prompt = await _text_fallback_prompt(
                scene, user_prompt, settings,
            )
    else:
        bg_prompt = await _text_fallback_prompt(scene, user_prompt, settings)

    updated_scene = scene.model_copy(update={"background_prompt": bg_prompt})
    errors: list[str] = []

    # Try to generate image; collect error if it fails
    file_path = Path(output_dir) / "game" / "images" / "backgrounds" / f"{scene.background_id}.png"
    try:
        bg_aspect = settings.bg_aspect_ratio
        await generate_image(bg_prompt, file_path, aspect_ratio=bg_aspect)
        # Nano Banana returns 1344×768 for "16:9" (the only ratio knob
        # it exposes). Ren'Py's base is 1920×1080 and `scene bg_x` draws
        # at native size centered — that leaves ~288px black bars on
        # every side. Post-process resize to the exact base resolution
        # so Ren'Py can render the scene with zero extra transforms and
        # no letterboxing. LANCZOS gives clean detail for the ~1.4×
        # upscale from 1344 wide.
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                if img.size != (1920, 1080):
                    img.convert("RGB").resize(
                        (1920, 1080), Image.Resampling.LANCZOS,
                    ).save(file_path)
                    logger.info(
                        f"Generated background: {scene.background_id} "
                        f"({bg_aspect} → 1920×1080)"
                    )
                else:
                    logger.info(f"Generated background: {scene.background_id}")
        except Exception as resize_err:
            logger.warning(
                f"Could not resize BG {scene.background_id} to 1920×1080: "
                f"{resize_err} (keeping native size)"
            )
    except Exception as e:
        logger.warning(f"Could not generate background {scene.background_id}: {e}")
        errors.append(f"SceneArtist: image {scene.background_id}: {e}")

    return updated_scene, errors


async def _text_fallback_prompt(scene: Scene, user_prompt: str, settings) -> str:
    """Fallback: extract background prompt from free-text LLM response."""
    import json
    import re

    caller = f"scene_artist/{scene.background_id}"
    response = await ainvoke_llm(
        SYSTEM_PROMPT, user_prompt,
        model=settings.llm_scene_artist_model, caller=caller,
    )
    content = response.content if hasattr(response, 'content') else str(response)

    bg_prompt = scene.description
    json_match = re.search(r'\{.*?\}', content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            bg_prompt = data.get("prompt", bg_prompt)
        except json.JSONDecodeError:
            pass
    return bg_prompt
