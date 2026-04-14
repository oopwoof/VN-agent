"""Ren'Py script compiler: VNScript JSON → .rpy files."""
from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import VNScript

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Writer's full emotion vocabulary (must match reviewer._VALID_EMOTIONS).
# Every emotion here needs to resolve to SOME image at Ren'Py-init time,
# otherwise `show sable thoughtful` renders the label-over-silhouette
# placeholder.
_ALL_EMOTIONS = (
    "neutral", "happy", "sad", "angry", "surprised",
    "scared", "thoughtful", "loving", "determined",
)

# Fallback chain per emotion — used only when an emotion's own PNG is
# missing. Order matters: try the first mapping, then the next, all
# the way down to neutral. Keeps the alias semantically closest to the
# intended mood. Creators can override by simply dropping a real
# <emotion>.png next to neutral.png — compile picks it up automatically.
_EMOTION_FALLBACK = {
    "neutral":    ("neutral",),
    "happy":      ("happy", "neutral"),
    "sad":        ("sad", "neutral"),
    "loving":     ("loving", "happy", "neutral"),
    "scared":     ("scared", "sad", "neutral"),
    "thoughtful": ("thoughtful", "sad", "neutral"),
    "determined": ("determined", "neutral"),
    "surprised":  ("surprised", "happy", "neutral"),
    "angry":      ("angry", "sad", "neutral"),
}


def _build_sprite_emotion_map(
    characters: dict[str, CharacterProfile],
    output_dir: Path | None,
) -> dict[str, dict[str, str]]:
    """Filesystem-aware sprite alias resolution.

    For each character × emotion, pick the best available PNG:
      1. The emotion's own file if present.
      2. Otherwise walk _EMOTION_FALLBACK chain until a file exists.
      3. If nothing exists (output_dir missing, or pre-asset-gen compile),
         point to <emotion>.png anyway — Ren'Py will fall back to its
         own placeholder, and a later recompile after assets land will
         heal the path without requiring a source edit.

    Returns {char_id: {emotion: relative_path_for_rpy}}.
    """
    result: dict[str, dict[str, str]] = {}
    for char_id in characters:
        per_emotion: dict[str, str] = {}
        char_dir = (
            output_dir / "game" / "images" / "characters" / char_id
            if output_dir else None
        )
        for emotion in _ALL_EMOTIONS:
            resolved = f"{emotion}.png"  # fallback if no filesystem view
            if char_dir and char_dir.exists():
                for candidate in _EMOTION_FALLBACK.get(emotion, (emotion,)):
                    if (char_dir / f"{candidate}.png").exists():
                        resolved = f"{candidate}.png"
                        break
            per_emotion[emotion] = f"images/characters/{char_id}/{resolved}"
        result[char_id] = per_emotion
    return result


def _renpy_safe(text: str) -> str:
    r"""Escape a Python string for safe embedding in a Ren'Py dialogue literal.

    Ren'Py processes text through several layers of substitution:
      - `[name]`  → interpolation of `name` from the local scope; if `name`
                    isn't defined (e.g. "[Scene: Foo]") the game crashes
                    at runtime with a NameError. Escape by doubling: `[[`.
      - `{tag}`   → text tag (like {b}bold{/b}); raw braces outside tags
                    also need doubling. `{{`.
      - `"`       → literal quote inside a double-quoted rpy string; `\"`.
      - `\`       → backslash; `\\` (must happen FIRST so later escapes
                    don't get re-escaped).

    Order matters: backslash first (so we don't double-escape our own
    escapes), then brackets, then braces, then quotes.
    """
    text = text.replace("\\", "\\\\")
    text = text.replace("[", "[[")
    text = text.replace("{", "{{")
    text = text.replace('"', '\\"')
    return text


def _get_jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["renpy_safe"] = _renpy_safe
    return env


def compile_script(
    script: VNScript,
    characters: dict[str, CharacterProfile],
    output_dir: Path | None = None,
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
    # Sprint 12-3c: explicit image declarations needed because our asset
    # layout is `images/characters/<id>/<emotion>.png` (one level deeper
    # than Ren'Py's auto-discovery finds). Without these, Ren'Py shows
    # its label-over-silhouette placeholder instead of the real sprite.
    init_template = env.get_template("init.rpy.j2")
    bg_ids = sorted({s.background_id for s in script.scenes if s.background_id})
    character_sprites = _build_sprite_emotion_map(characters, output_dir)
    files["game/init.rpy"] = init_template.render(
        script=script,
        character_ids=sorted(characters.keys()),
        background_ids=bg_ids,
        character_sprites=character_sprites,
    )

    return files


def compile_to_string(script: VNScript, characters: dict[str, CharacterProfile]) -> str:
    """Compile script.rpy content as a string (for testing)."""
    files = compile_script(script, characters)
    return files.get("game/script.rpy", "")
