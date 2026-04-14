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
    art_direction = state.get("art_direction", "")

    if not characters:
        return {}

    logger.info(f"CharacterDesigner: designing {len(characters)} characters (style: {art_direction[:50]})")

    char_ids = list(characters.keys())
    char_list = list(characters.values())

    results = await asyncio.gather(
        *[_design_character(char, output_dir, art_direction) for char in char_list],
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


async def _design_character(
    char: CharacterProfile, output_dir: str, art_direction: str = "",
) -> tuple[CharacterProfile, list[str]]:
    """Design visual profile for a character.

    Returns a tuple of (updated_character, errors).
    """
    style_note = f"\nProject art direction (MUST follow): {art_direction}" if art_direction else ""
    user_prompt = f"""Create a visual profile for this character:{style_note}

Name: {char.name}
Role: {char.role}
Personality: {char.personality}
Background: {char.background}

Provide:
1. Art style — MUST be consistent with the project art direction above
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
    """Generate sprite images using neutral-first consistency strategy.

    Sprint 6-9b: to avoid the identity drift that plagues text-to-image
    generators when producing the same character in different emotions,
    we generate ONE neutral sprite from a detailed text prompt, then use
    that image as a reference for happy/sad via image-to-image editing
    (if the provider supports it). Providers without reference support
    fall through to the legacy text-only path but with the same base
    descriptor for all 3 emotions so the prompt itself stays maximally
    consistent.

    On any failure, we fall back to neutral as the image for the missing
    emotion — Ren'Py references never go dangling, even if some variants
    weren't produced.
    """
    from vn_agent.config import get_settings
    from vn_agent.services.bg_remove import cutout_png
    from vn_agent.services.image_gen import (
        generate_image_with_reference,
        provider_supports_reference,
    )

    settings = get_settings()
    sprites: list[EmotionSprite] = []
    errors: list[str] = []

    # Base visual descriptor shared by all emotions — LLM only describes
    # appearance once, we just append the emotion modifier per variant.
    base_descriptor = (
        f"{visual.art_style}, {visual.appearance}, {visual.default_outfit}"
    )

    # Sprint 12-3b → 12-3c: sprites composite over scene backgrounds in
    # Ren'Py, so they need transparent PNGs. Two layers of defense:
    # (1) prompt asks the model for a flat background so the matte step
    #     has a clean edge to follow. Critical bug we hit first: saying
    #     "flat medium gray background" + "character portrait" made
    #     Nano Banana interpret this as a stylized monochrome silhouette
    #     art style — the model rendered characters as solid dark shapes
    #     against gray and rembg faithfully cut those out, producing
    #     black silhouettes in-game. Fix: use a warm off-white (not pure
    #     white, which blends with light hair/skin) and explicitly
    #     demand "full color" + "NOT a silhouette" to block the
    #     stylized-shadow interpretation. Held props stay — we want
    #     character identity preserved.
    # (2) rembg post-process runs u2net_human_seg on the saved PNG and
    #     replaces the background with alpha. Deterministic, local, ~1s.
    #     For non-human or prop-heavy subjects the cutout model can be
    #     swapped to `isnet-general-use` via settings.sprite_cutout_model.
    bg_clause = (
        "soft off-white studio background, full-color character with all "
        "facial features and clothing details clearly visible, "
        "NOT a silhouette, NOT a shadow, NOT a monochrome shape, "
        "standing pose, full body from head to toe in frame"
    )

    def _sprite_path(emotion: str) -> tuple[str, Path]:
        rel = f"images/characters/{char.id}/{emotion}.png"
        return rel, Path(output_dir) / "game" / rel

    # ── Step 1: neutral (anchor) ────────────────────────────────────────────
    neutral_rel, neutral_abs = _sprite_path("neutral")
    neutral_prompt = (
        f"{base_descriptor}, neutral expression, full body, "
        f"{bg_clause}, visual novel character sprite"
    )
    # Cutout is deferred until all sprites are generated: when provider
    # supports image-to-image, the neutral PNG is passed as a *reference*
    # for happy/sad. A transparent reference would confuse Nano Banana's
    # identity extraction (it reads the alpha as a checkerboard artifact
    # or a black shape), so we keep the reference opaque through the
    # whole reference-editing loop and strip backgrounds at the end.
    cutout_targets: list[tuple[Path, str]] = []

    neutral_ok = False
    try:
        # 3:4 portrait matches traditional VN full-body sprite framing —
        # character fills vertical space, 1920x1080 scenes get head-to-toe.
        await generate_image(neutral_prompt, neutral_abs, aspect_ratio="3:4")
        logger.info(f"Generated neutral sprite: {char.id}")
        cutout_targets.append((neutral_abs, f"{char.id}_neutral"))
        neutral_ok = True
    except Exception as e:
        logger.warning(f"Could not generate neutral sprite for {char.id}: {e}")
        errors.append(f"CharacterDesigner: sprite {char.id}_neutral: {e}")

    sprites.append(EmotionSprite(
        emotion="neutral",
        image_id=f"{char.id}_neutral",
        file_path=neutral_rel,
        generation_prompt=neutral_prompt,
    ))

    # ── Step 2: happy + sad, anchored on neutral if available ───────────────
    use_reference = neutral_ok and provider_supports_reference()
    emotion_hints = {
        "happy": "smiling warmly, eyes bright, relaxed posture",
        "sad": "downcast eyes, slight frown, slumped posture",
    }

    for emotion, hint in emotion_hints.items():
        rel, abs_path = _sprite_path(emotion)
        if use_reference:
            # Provider supports image-to-image: use neutral as the anchor
            prompt = (
                f"Same character as reference image. {hint}. "
                f"Keep face, hair, and outfit identical. "
                f"Full body, {bg_clause}, visual novel character sprite."
            )
        else:
            # Text-only path: repeat the full base descriptor verbatim so
            # at least the prompt is consistent across emotions
            prompt = (
                f"{base_descriptor}, {hint}, {emotion} expression, full body, "
                f"{bg_clause}, visual novel character sprite"
            )

        try:
            if use_reference:
                await generate_image_with_reference(
                    prompt, neutral_abs, abs_path, aspect_ratio="3:4",
                )
            else:
                await generate_image(prompt, abs_path, aspect_ratio="3:4")
            logger.info(f"Generated {emotion} sprite: {char.id}")
            cutout_targets.append((abs_path, f"{char.id}_{emotion}"))
        except Exception as e:
            logger.warning(f"Could not generate {emotion} sprite for {char.id}: {e}")
            errors.append(f"CharacterDesigner: sprite {char.id}_{emotion}: {e}")
            # Fallback: copy neutral bytes so Ren'Py doesn't load a blank
            if neutral_ok:
                try:
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_bytes(neutral_abs.read_bytes())
                    logger.info(
                        f"Fallback: {emotion} sprite for {char.id} = copy of neutral"
                    )
                except Exception as copy_err:
                    logger.warning(f"Neutral-copy fallback failed: {copy_err}")

        sprites.append(EmotionSprite(
            emotion=emotion,
            image_id=f"{char.id}_{emotion}",
            file_path=rel,
            generation_prompt=prompt,
        ))

    # ── Step 3: batch cutout all successful sprites ─────────────────────────
    # Deferred so reference-based generation sees opaque neutral. Failures
    # don't abort — the original opaque PNG stays on disk; creator sees a
    # rectangle but the VN still runs. Logged so eval scripts can flag it.
    if settings.sprite_cutout and cutout_targets:
        import time
        t0 = time.perf_counter()
        cut_ok = 0
        for path, label in cutout_targets:
            if cutout_png(path, model_name=settings.sprite_cutout_model):
                cut_ok += 1
            else:
                errors.append(f"CharacterDesigner: cutout {label} failed (kept opaque)")
        logger.info(
            f"Cutout batch for {char.id}: {cut_ok}/{len(cutout_targets)} alpha-stripped "
            f"in {time.perf_counter() - t0:.1f}s"
        )

    return sprites, errors
