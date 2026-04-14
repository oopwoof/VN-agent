"""Sprint 12-5: unknown-character resolver extractor + reviewer integration."""
from __future__ import annotations

import pytest

from vn_agent.agents.unknown_chars import extract_unknown_characters
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import DialogueLine, Scene, VNScript


def _mk_script(scenes: list[Scene], character_ids: list[str] | None = None) -> VNScript:
    return VNScript(
        title="T",
        description="d",
        theme="th",
        start_scene_id=scenes[0].id if scenes else "s1",
        scenes=scenes,
        characters=character_ids or [],
    )


def _mk_scene(sid: str, dialogue: list[tuple[str | None, str]]) -> Scene:
    return Scene(
        id=sid, title=sid, description=f"scene {sid}",
        background_id="bg1",
        dialogue=[
            DialogueLine(character_id=cid, text=text, emotion="neutral")
            for cid, text in dialogue
        ],
    )


class TestExtractUnknown:
    def test_no_unknowns_when_cast_covers_all(self):
        script = _mk_script(
            [_mk_scene("s1", [("alice", "hi"), ("bob", "hey")])],
            character_ids=["alice", "bob"],
        )
        assert extract_unknown_characters(script, None) == []

    def test_flags_character_not_in_cast(self):
        script = _mk_script(
            [_mk_scene("s1", [("alice", "hi"), ("yuki", "who am i")])],
            character_ids=["alice"],
        )
        unknowns = extract_unknown_characters(script, {})
        assert len(unknowns) == 1
        assert unknowns[0]["character_id"] == "yuki"
        assert unknowns[0]["first_appearance_scene"] == "s1"
        assert unknowns[0]["reference_count"] == 1

    def test_accepts_characters_dict_as_declaration_source(self):
        """characters.json is authoritative even if script.characters lags."""
        script = _mk_script(
            [_mk_scene("s1", [("yuki", "hello")])],
            character_ids=[],  # lagging
        )
        chars = {"yuki": CharacterProfile(
            id="yuki", name="Yuki", personality="warm",
            background="drifter", role="supporting",
        )}
        assert extract_unknown_characters(script, chars) == []

    def test_narration_lines_never_trigger_unknown(self):
        script = _mk_script(
            [_mk_scene("s1", [(None, "the wind howls"), ("alice", "hi")])],
            character_ids=["alice"],
        )
        assert extract_unknown_characters(script, None) == []

    def test_collects_sample_lines_capped_per_char(self):
        many = [("ghost", f"line {i}") for i in range(12)]
        script = _mk_script([_mk_scene("s1", many)], character_ids=[])
        unknowns = extract_unknown_characters(script, None)
        assert len(unknowns) == 1
        assert unknowns[0]["reference_count"] == 12
        # Module caps at 6 sample lines
        assert len(unknowns[0]["sample_lines"]) == 6

    def test_profile_stub_uses_id_as_title_cased_name(self):
        script = _mk_script(
            [_mk_scene("s1", [("ragged_sage", "old words are heavy")])],
            character_ids=[],
        )
        unknowns = extract_unknown_characters(script, None)
        stub = unknowns[0]["profile_stub"]
        assert stub["id"] == "ragged_sage"
        assert stub["name"] == "Ragged Sage"
        assert stub["role"] == "TBD"
        assert "old words are heavy" in stub["dialogue_context_hint"]

    def test_stable_ordering_by_first_appearance(self):
        script = _mk_script([
            _mk_scene("s1", [("alpha", "first")]),
            _mk_scene("s2", [("beta", "second"), ("gamma", "third")]),
            _mk_scene("s3", [("alpha", "again")]),
        ], character_ids=[])
        unknowns = extract_unknown_characters(script, None)
        ids = [u["character_id"] for u in unknowns]
        assert ids == ["alpha", "beta", "gamma"]

    def test_max_unknown_cap_enforced(self):
        # 10 unknowns, only first 8 are returned
        dialogue = [(f"ghost_{i}", f"line {i}") for i in range(10)]
        script = _mk_script([_mk_scene("s1", dialogue)], character_ids=[])
        unknowns = extract_unknown_characters(script, None)
        assert len(unknowns) == 8


class TestReviewerIntegration:
    @pytest.mark.asyncio
    async def test_reviewer_emits_unknown_characters_on_fail(self):
        from vn_agent.agents.reviewer import run_reviewer

        # Script has 2 unknown chars but passes the line-count check
        dialogue = [("alice", f"line {i}") for i in range(5)]
        dialogue.append(("phantom", "who summons me"))
        script = _mk_script(
            [_mk_scene("s1", dialogue)], character_ids=["alice"],
        )
        state = {
            "vn_script": script,
            "characters": {},
            "revision_count": 0,
        }
        out = await run_reviewer(state)
        assert out["review_passed"] is False
        # The new field carries the structured unknown data
        assert "unknown_characters" in out
        ids = [u["character_id"] for u in out["unknown_characters"]]
        assert "phantom" in ids
