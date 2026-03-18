"""Project builder: assembles complete Ren'Py project directory."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from vn_agent.schema.script import VNScript
from vn_agent.schema.character import CharacterProfile
from vn_agent.compiler.renpy_compiler import compile_script

logger = logging.getLogger(__name__)

# Ren'Py project directory structure
GAME_DIRS = [
    "game/audio/bgm",
    "game/images/backgrounds",
    "game/images/characters",
]


def build_project(
    script: VNScript,
    characters: dict[str, CharacterProfile],
    output_dir: Path,
) -> Path:
    """
    Build a complete Ren'Py project in output_dir.

    Returns the output directory path.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create directory structure
    for subdir in GAME_DIRS:
        (output_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Compile .rpy files
    rpy_files = compile_script(script, characters)
    for rel_path, content in rpy_files.items():
        target = output_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.info(f"Written: {rel_path}")

    # Save intermediate JSON (useful for debugging/manual editing)
    json_path = output_dir / "vn_script.json"
    json_path.write_text(
        script.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # Save characters JSON
    chars_json = {k: v.model_dump() for k, v in characters.items()}
    chars_path = output_dir / "characters.json"
    chars_path.write_text(
        json.dumps(chars_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Write placeholder assets for any missing image/audio files so Ren'Py
    # doesn't error on missing files during development / text-only runs.
    _write_placeholder_assets(script, characters, output_dir)

    logger.info(f"Ren'Py project built at: {output_dir}")
    return output_dir


# Minimal 1×1 transparent PNG (67 bytes, no external deps)
_PLACEHOLDER_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _write_placeholder_assets(
    script: VNScript,
    characters: dict[str, CharacterProfile],
    output_dir: Path,
) -> None:
    """Create 1×1 transparent PNG placeholders for any missing sprite/background.

    Ren'Py will display a blank image instead of throwing a missing-file error,
    which keeps the game runnable during development before real art is generated.
    Only writes files that don't already exist.
    """
    game = output_dir / "game"

    # Background placeholders
    bg_ids = {scene.background_id for scene in script.scenes if scene.background_id}
    for bg_id in bg_ids:
        path = game / "images" / "backgrounds" / f"{bg_id}.png"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_PLACEHOLDER_PNG)
            logger.debug(f"Placeholder: {path.relative_to(output_dir)}")

    # Character sprite placeholders (neutral emotion used as default)
    for char_id in characters:
        char_dir = game / "images" / "characters" / char_id
        char_dir.mkdir(parents=True, exist_ok=True)
        for emotion in ("neutral", "happy", "sad"):
            path = char_dir / f"{emotion}.png"
            if not path.exists():
                path.write_bytes(_PLACEHOLDER_PNG)
                logger.debug(f"Placeholder: {path.relative_to(output_dir)}")
