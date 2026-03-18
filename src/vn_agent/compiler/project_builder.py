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

    logger.info(f"Ren'Py project built at: {output_dir}")
    return output_dir
