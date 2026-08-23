"""Chat-ops `edit_asset` executor.

Handles "make the rooftop scene look like dusk instead of noon" for a
scene background: try the open-source asset library first (a hit is a
free, licence-clean swap), and fall back to regenerating the image
through SceneArtist when the job is really generating images.

Two honest boundaries, both surfaced in the turn text rather than hidden:

- Under mock mode there is no image generation at all (image_gen refuses
  by design), so a library miss can't be fixed here. That turn succeeds
  with a message pointing at the asset-upload endpoint — a chat-ops turn
  that reports "no automated option, here's the manual one" is a useful
  answer, not a failure.
- Character sprites are not covered. Re-rendering one emotion out of a
  set breaks visual consistency with the rest; sprite work belongs with
  add_character or a full re-design, and the turn says so.
"""
from __future__ import annotations

import logging
from pathlib import Path

from vn_agent.schema.script import VNScript

logger = logging.getLogger(__name__)

_UPLOAD_HINT = (
    "You can also replace the file directly in the Asset panel "
    "(upload swaps the image without any generation)."
)


async def execute(output_dir: str, preview) -> tuple[bool, str, str | None]:
    """Handler signature shared by every chat-ops executor:
    returns (success, result_text, diff)."""
    out = Path(output_dir)
    script_path = out / "vn_script.json"
    if not script_path.exists():
        return False, "No vn_script.json in this project — generate a script first.", None

    if preview.target_character_id and not preview.target_scene_id:
        return True, (
            f"Sprite edits for '{preview.target_character_id}' aren't automated: "
            f"re-rendering one emotion out of a set drifts from the others, so "
            f"sprites are regenerated as a group, not one at a time. "
            f"{_UPLOAD_HINT}"
        ), None

    script = VNScript.model_validate_json(script_path.read_text(encoding="utf-8"))
    scene = _find_scene(script, preview.target_scene_id)
    if scene is None:
        return False, (
            "No target scene identified — name the scene whose background "
            "you want changed."
        ), None

    instruction = preview.instruction or preview.message
    target_path = out / "game" / "images" / "backgrounds" / f"{scene.background_id}.png"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Library first: a hit is free, licence-clean, and instant.
    hit = _try_library(instruction, scene, target_path, output_dir)
    if hit is not None:
        provenance = f"[library:{hit.id} · {hit.license} · {hit.attribution}]"
        _replace_scene(script, scene, f"{provenance} {instruction}")
        _atomic_write(script_path, script.model_dump_json(indent=2))
        return True, (
            f"Swapped the background for '{scene.title}' with a library asset "
            f"({hit.id}, {hit.license}). No generation call needed."
        ), f"- {scene.background_id}: (previous)\n+ {scene.background_id}: {provenance}"

    from vn_agent.services.llm import mock_mode_var
    if mock_mode_var.get():
        return True, (
            f"No library match for '{instruction}', and mock mode makes no "
            f"image calls, so nothing was regenerated. {_UPLOAD_HINT}"
        ), None

    try:
        updated, errors = await _regenerate(scene, instruction, output_dir, script)
    except Exception as e:  # noqa: BLE001
        logger.exception("edit_asset regeneration failed")
        return False, f"Could not regenerate the background: {e}", None

    _replace_scene(script, scene, updated.background_prompt or instruction)
    _atomic_write(script_path, script.model_dump_json(indent=2))

    if errors:
        return True, (
            f"Regenerated the prompt for '{scene.title}' but the image call "
            f"reported {len(errors)} error(s): {errors[0]}. {_UPLOAD_HINT}"
        ), None
    return True, (
        f"Regenerated the background for '{scene.title}' from: {instruction}"
    ), (
        f"- {scene.background_id}: {scene.background_prompt or '(no prompt)'}\n"
        f"+ {scene.background_id}: {updated.background_prompt or instruction}"
    )


def _try_library(instruction: str, scene, target_path: Path, output_dir: str):
    """Library swap. Never fatal — a library problem falls through to
    regeneration, same as the asset agents do."""
    try:
        from vn_agent.assets.library import record_library_hit, try_library_hit

        query = f"{instruction} {scene.title} {scene.description}"
        hit = try_library_hit(query, "background", target_path)
        if hit is not None:
            record_library_hit(output_dir, "background", scene.background_id, hit, query)
        return hit
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Library lookup failed for {scene.background_id}: {e}")
        return None


async def _regenerate(scene, instruction: str, output_dir: str, script: VNScript):
    """Hand SceneArtist a scene whose description carries the creator's
    instruction, so the prompt it writes reflects the requested change."""
    from vn_agent.agents.scene_artist import _generate_background

    described = scene.model_copy(update={
        "description": f"{scene.description}\n\nRequested change: {instruction}",
    })
    return await _generate_background(described, output_dir)


def _find_scene(script: VNScript, scene_id: str | None):
    if not scene_id:
        return None
    for s in script.scenes:
        if s.id == scene_id:
            return s
    return None


def _replace_scene(script: VNScript, scene, background_prompt: str) -> None:
    for i, s in enumerate(script.scenes):
        if s.id == scene.id:
            script.scenes[i] = s.model_copy(
                update={"background_prompt": background_prompt},
            )
            return


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
