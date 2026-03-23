"""Ren'Py script compiler: VNScript JSON → .rpy files."""
from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import VNScript

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def compile_script(
    script: VNScript,
    characters: dict[str, CharacterProfile],
) -> dict[str, str]:
    """
    Compile a VNScript into Ren'Py source files.

    Returns:
        dict mapping relative path -> file content
    """
    env = _get_jinja_env()
    files: dict[str, str] = {}

    # script.rpy
    script_template = env.get_template("script.rpy.j2")
    files["game/script.rpy"] = script_template.render(
        script=script,
        characters=characters,
    )

    # characters.rpy
    char_template = env.get_template("characters.rpy.j2")
    files["game/characters.rpy"] = char_template.render(
        characters=characters,
    )

    # gui.rpy
    gui_template = env.get_template("gui.rpy.j2")
    files["game/gui.rpy"] = gui_template.render(
        script=script,
    )

    # init.rpy
    init_template = env.get_template("init.rpy.j2")
    files["game/init.rpy"] = init_template.render(
        script=script,
    )

    return files


def compile_to_string(script: VNScript, characters: dict[str, CharacterProfile]) -> str:
    """Compile script.rpy content as a string (for testing)."""
    files = compile_script(script, characters)
    return files.get("game/script.rpy", "")
