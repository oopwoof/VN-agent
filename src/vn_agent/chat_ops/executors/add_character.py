"""Chat-ops `add_character` executor.

Turns "add a rival pianist who transferred in last year" into a real
CharacterProfile on disk: an LLM synthesizes the written profile, the
existing CharacterDesigner fills the visual profile (and sprites, when
the job is actually generating images), and both characters.json and
vn_script.json are updated atomically.

Sprites are the one deliberate scope line. A mock job can't call an
image provider at all, and a text-only job was configured never to spend
on one — in both cases the executor writes the profile and says which
reason applied, instead of either failing the turn or quietly billing for
an image the project was set up to avoid. The character is playable
either way; the compiler fills missing sprites with placeholders.

What this deliberately does NOT do: rewrite existing scenes to include
the new character. Adding someone to the cast makes them *available*;
putting them on stage is a separate local_regen per scene, which the
result text points at.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import VNScript

logger = logging.getLogger(__name__)

_SYSTEM = """You design cast members for a visual novel.

Given the story's premise, its existing cast, and the creator's request,
write ONE new character that fits the world and fills a role the cast
doesn't already cover. Match the language of the story (if the premise is
Chinese, write the character in Chinese).

Return JSON only:
{
  "id": "lowercase_ascii_identifier",
  "name": "display name",
  "color": "#rrggbb",
  "role": "role in the story",
  "personality": "traits, in one or two sentences",
  "background": "backstory and motivation, two or three sentences",
  "speech_fingerprint": ["3-5 short signature speech traits"]
}

`id` must be ASCII, lowercase, underscore-separated — it becomes a Ren'Py
variable name. Never reuse an existing character's id or name."""

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# The id is emitted verbatim as a Ren'Py `define <id> = Character(...)`.
# A Python keyword there is a compile error, and a Ren'Py built-in is
# worse than an error: defining `narrator` silently replaces the engine's
# own narrator, so every line of narration in the game renders under this
# character's name and colour.
_RESERVED_IDS = {
    "narrator", "name_only_text", "centered", "vcentered", "nvl",
    "config", "store", "gui", "renpy", "style", "persistent", "preferences",
    "adv", "extend", "menu", "label", "screen", "default", "define",
}


async def execute(output_dir: str, preview) -> tuple[bool, str, str | None]:
    """Handler signature shared by every chat-ops executor:
    returns (success, result_text, diff)."""
    out = Path(output_dir)
    script_path = out / "vn_script.json"
    if not script_path.exists():
        return False, "No vn_script.json in this project — generate a script first.", None

    script = VNScript.model_validate_json(script_path.read_text(encoding="utf-8"))
    characters = _load_characters(out)

    try:
        profile = await _synthesize_profile(
            script, characters, preview.instruction or preview.message,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("add_character profile synthesis failed")
        return False, f"Could not design the character: {e}", None

    if profile.id in characters:
        return False, (
            f"'{profile.id}' is already in the cast — rephrase with a clearer "
            f"description if you meant a different character."
        ), None

    profile, sprite_note = await _fill_visual_profile(profile, output_dir, characters)

    characters[profile.id] = profile
    if profile.id not in script.characters:
        script.characters.append(profile.id)

    _atomic_write(out / "characters.json", json.dumps(
        {k: v.model_dump() for k, v in characters.items()},
        indent=2, ensure_ascii=False,
    ))
    _atomic_write(script_path, script.model_dump_json(indent=2))

    diff = (
        f"+ {profile.id} ({profile.name}) — {profile.role}\n"
        f"+ personality: {profile.personality}\n"
        f"+ background: {profile.background}"
    )
    result = (
        f"Added '{profile.name}' ({profile.id}) as {profile.role}. {sprite_note} "
        f"They're in the cast now but not in any scene yet — ask me to rewrite "
        f"a scene with them in it to put them on stage."
    )
    return True, result, diff


async def _synthesize_profile(
    script: VNScript, characters: dict[str, CharacterProfile], instruction: str,
) -> CharacterProfile:
    from vn_agent.config import get_settings
    from vn_agent.services.llm import ainvoke_llm

    settings = get_settings()
    existing = "\n".join(
        f"- {c.id}: {c.name} ({c.role}) — {c.personality}"
        for c in characters.values()
    ) or "(no characters yet)"

    user = (
        f"Story: {script.title}\n"
        f"{script.description}\n\n"
        f"Existing cast:\n{existing}\n\n"
        f"Creator's request: {instruction}"
    )
    response = await ainvoke_llm(
        _SYSTEM, user,
        model=settings.llm_character_designer_model,
        caller="chat_ops/add_character",
    )
    content = response.content if hasattr(response, "content") else str(response)
    data = _parse_json_object(content)

    char_id = _safe_id(
        str(data.get("id") or ""), str(data.get("name") or "new_character"),
    )
    return CharacterProfile(
        id=char_id,
        name=str(data.get("name") or char_id),
        color=str(data.get("color") or "#ffffff"),
        role=str(data.get("role") or "supporting"),
        personality=str(data.get("personality") or ""),
        background=str(data.get("background") or ""),
        speech_fingerprint=[str(s) for s in (data.get("speech_fingerprint") or [])][:5],
    )


async def _fill_visual_profile(
    profile: CharacterProfile, output_dir: str,
    characters: dict[str, CharacterProfile],
) -> tuple[CharacterProfile, str]:
    """Visual profile always; sprites only when the job can actually make
    images. Returns (profile, human-readable note about sprites)."""
    from vn_agent.agents.character_designer import _design_character
    from vn_agent.chat_ops.run_context import images_allowed, no_images_reason

    want_sprites = images_allowed()
    try:
        designed, errors = await _design_character(
            profile, output_dir,
            art_direction=_existing_art_style(characters),
            generate_sprites=want_sprites,
        )
    except Exception as e:  # noqa: BLE001 — a written character with no
        # visual profile still compiles and plays; don't fail the turn.
        logger.warning(f"Visual profile for {profile.id} failed: {e}")
        return profile, "No visual profile yet (designer unavailable)."

    if not want_sprites:
        return designed, f"Sprites skipped ({no_images_reason()})."
    if errors:
        return designed, f"Sprites partially failed ({len(errors)} error(s))."
    return designed, "Sprites generated."


def _existing_art_style(characters: dict[str, CharacterProfile]) -> str:
    """The project's art direction as actually realized.

    `art_direction` lives in graph state and never reaches disk, so a
    chat-ops executor reading a finished project can't see it. The
    art_style already recorded on an existing cast member is the same
    decision, one step downstream — matching it is what keeps a
    chat-added character from looking like it came from another game.
    """
    for c in characters.values():
        if c.visual and c.visual.art_style:
            return c.visual.art_style
    return ""


def _load_characters(out: Path) -> dict[str, CharacterProfile]:
    path = out / "characters.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: CharacterProfile.model_validate(v) for k, v in raw.items()}


def _atomic_write(path: Path, text: str) -> None:
    """tmp + replace, the same shape Writer uses — a half-written
    characters.json breaks every later load."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _parse_json_object(content: str) -> dict:
    try:
        return json.loads(content)
    except Exception:  # noqa: BLE001
        pass
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("model returned no JSON object")
    return json.loads(match.group(0))


def _safe_id(proposed: str, fallback_name: str) -> str:
    """A Ren'Py-safe identifier, preferring the model's own id.

    Falls back to a slug of the display name when the proposed id isn't
    usable, then prefixes anything that would collide with a keyword or
    engine built-in — `char_narrator` is a harmless name, `narrator` is a
    silent takeover of every narration line in the game.
    """
    import keyword

    candidate = proposed.strip().lower()
    if not _ID_RE.match(candidate):
        candidate = _slugify(fallback_name)
    if keyword.iskeyword(candidate) or candidate in _RESERVED_IDS:
        candidate = f"char_{candidate}"
    return candidate


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"char_{slug}" if slug else "new_character"
    return slug
