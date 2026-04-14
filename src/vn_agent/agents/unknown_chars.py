"""Sprint 12-5: unknown-character resolver surface.

Problem: in creator mode, a human editing dialogue can introduce a new
`character_id` that wasn't in the original cast. Before this module,
the structural check would just say "'yuki' speaks but is not declared"
and demand a full rewrite — blocking the creative flow.

With this module, the reviewer still fails (the script is genuinely
invalid until the character is resolved), but the failure carries
structured metadata so a creator-mode UI can offer:
  A) auto-generate a CharacterProfile from dialogue context, OR
  B) open the cast editor with a pre-populated profile stub.

The output is intentionally a plain dict (not a Pydantic model) so
the web/CLI layer can serialize it to JSON without schema coupling.
Auto-generation itself is deferred to the web layer (it requires a
CharacterDesigner call that costs money — creator must consent).
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import VNScript

# Caps to keep the resolver payload from exploding on a long VN that
# names 20 unknown characters by mistake. Creator sees the first few
# and can rerun after fixing those before seeing the rest.
_MAX_UNKNOWN = 8
_MAX_LINES_PER_CHAR = 6


def extract_unknown_characters(
    script: VNScript,
    characters: dict[str, CharacterProfile] | None,
) -> list[dict[str, Any]]:
    """Scan a VNScript for character_ids that aren't in the cast.

    Returns one dict per unknown id, with the sample dialogue lines
    that referenced it and a best-guess profile stub drawn from
    surrounding context. An empty list means no unknowns — reviewer
    can fall through to other checks.

    The "best-guess" fields are deliberately minimal (name only, role
    left TBD). We don't pattern-match speech style or personality here
    — that's an LLM's job, invoked on creator consent from the web UI.
    """
    known_ids = _known_character_ids(script, characters)

    # character_id → list of (scene_id, line_index, line_dict)
    refs: dict[str, list[tuple[str, int, dict[str, Any]]]] = {}
    for scene in script.scenes:
        for i, line in enumerate(scene.dialogue):
            if not line.character_id:
                continue  # narration; skip
            if line.character_id in known_ids:
                continue
            refs.setdefault(line.character_id, []).append(
                (scene.id, i, {
                    "text": line.text,
                    "emotion": line.emotion,
                })
            )

    if not refs:
        return []

    # Stable ordering: sort by first appearance (scene index, line index)
    scene_order = {s.id: i for i, s in enumerate(script.scenes)}
    ordered_ids = sorted(
        refs.keys(),
        key=lambda cid: (scene_order.get(refs[cid][0][0], 9999), refs[cid][0][1]),
    )

    result: list[dict[str, Any]] = []
    for cid in ordered_ids[:_MAX_UNKNOWN]:
        char_refs = refs[cid]
        sample_lines = [
            {"scene_id": sid, "line_index": idx, **line_data}
            for sid, idx, line_data in char_refs[:_MAX_LINES_PER_CHAR]
        ]
        result.append({
            "character_id": cid,
            "reference_count": len(char_refs),
            "first_appearance_scene": char_refs[0][0],
            "sample_lines": sample_lines,
            "profile_stub": _profile_stub(cid, sample_lines),
        })
    return result


def _known_character_ids(
    script: VNScript, characters: dict[str, CharacterProfile] | None,
) -> set[str]:
    """Union of ids from script.characters AND the characters dict.

    Either source can be authoritative — creator might have added a
    new character to characters.json but not yet updated
    script.characters, or vice versa. Be lenient on what we accept as
    declared; strict on what we flag.
    """
    known: set[str] = set()
    for c in script.characters:
        if isinstance(c, str):
            known.add(c)
        else:
            cid = getattr(c, "id", None)
            if cid:
                known.add(cid)
    if characters:
        known.update(characters.keys())
    return known


def _profile_stub(character_id: str, sample_lines: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal CharacterProfile-shaped stub for creator review.

    Name is the id title-cased as a reasonable first guess ('yuki' →
    'Yuki'). Everything else is left as placeholder text so the
    creator (or CharacterDesigner on consent) can fill in. We do NOT
    auto-generate personality from dialogue — that's a judgment call
    worth an LLM and explicit creator approval.
    """
    # Join first 2 sample texts as hint for downstream context
    texts = [line["text"] for line in sample_lines][:2]
    hint = " | ".join(t.strip()[:80] for t in texts if t)
    return {
        "id": character_id,
        "name": character_id.replace("_", " ").title() or character_id,
        "role": "TBD",
        "personality": "TBD",
        "background": "TBD",
        "dialogue_context_hint": hint,
    }
