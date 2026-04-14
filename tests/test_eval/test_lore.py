"""Tests for Sprint 10-2 lore extraction + formatting (zero-API)."""
from __future__ import annotations

from vn_agent.eval.lore import (
    extract_lore_entities,
    format_lore_block,
)
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import Scene, VNScript, WorldVariable


def _char(cid, name, bg="", role="supporting") -> CharacterProfile:
    return CharacterProfile(
        id=cid, name=name, role=role,
        personality="curious", background=bg,
    )


def _scene(sid, bg, desc="") -> Scene:
    return Scene(
        id=sid, title=sid, description=desc, background_id=bg,
        characters_present=[],
    )


class TestExtract:
    def test_empty_script_returns_empty(self):
        script = VNScript(
            title="", description="", theme="", start_scene_id="",
            scenes=[],
        )
        assert extract_lore_entities(script, {}) == []

    def test_premise_entity(self):
        script = VNScript(
            title="Lighthouse", description="A keeper in a storm.",
            theme="solitude", start_scene_id="s1",
            scenes=[_scene("s1", "bg1")],
        )
        entities = extract_lore_entities(script, {})
        ids = [e.id for e in entities]
        assert "premise:main" in ids
        premise = next(e for e in entities if e.id == "premise:main")
        assert "Lighthouse" in premise.text
        assert "solitude" in premise.text

    def test_character_entities_have_background(self):
        script = VNScript(
            title="T", description="", theme="", start_scene_id="s1",
            scenes=[_scene("s1", "bg1")],
        )
        chars = {
            "yui": _char("yui", "Yui", bg="lost her father at sea", role="protagonist"),
            "ren": _char("ren", "Ren", bg="young sailor washed ashore"),
        }
        entities = extract_lore_entities(script, chars)
        char_ents = [e for e in entities if e.id.startswith("character:")]
        assert len(char_ents) == 2
        yui_ent = next(e for e in char_ents if e.id == "character:yui")
        assert "lost her father at sea" in yui_ent.text

    def test_locations_dedupe_by_background_id(self):
        script = VNScript(
            title="T", description="", theme="", start_scene_id="s1",
            scenes=[
                _scene("s1", "bg_shore", "morning at the cliffs"),
                _scene("s2", "bg_shore", "returning to the cliffs at dusk"),
                _scene("s3", "bg_lighthouse", "inside the lamp room"),
            ],
        )
        entities = extract_lore_entities(script, {})
        loc_ents = [e for e in entities if e.id.startswith("location:")]
        assert len(loc_ents) == 2
        shore = next(e for e in loc_ents if e.id == "location:bg_shore")
        # both scenes referenced
        assert "s1" in shore.text and "s2" in shore.text

    def test_world_variables(self):
        script = VNScript(
            title="T", description="", theme="", start_scene_id="s1",
            scenes=[_scene("s1", "bg1")],
            world_variables=[
                WorldVariable(
                    name="affinity", type="int", initial_value=3,
                    description="closeness 0-10",
                ),
            ],
        )
        entities = extract_lore_entities(script, {})
        wv_ents = [e for e in entities if e.id.startswith("world_var:")]
        assert len(wv_ents) == 1
        assert "closeness 0-10" in wv_ents[0].text

    def test_strategy_always_none(self):
        """Lore entities must have strategy=None so they bypass the
        strategy pre-filter path in EmbeddingIndex.search."""
        script = VNScript(
            title="T", description="X", theme="", start_scene_id="s1",
            scenes=[_scene("s1", "bg1")],
        )
        entities = extract_lore_entities(
            script, {"yui": _char("yui", "Yui")},
        )
        assert all(e.strategy is None for e in entities)


class TestFormat:
    def test_empty_returns_empty_string(self):
        assert format_lore_block([]) == ""

    def test_renders_with_type_prefix(self):
        script = VNScript(
            title="T", description="A story.", theme="",
            start_scene_id="s1",
            scenes=[_scene("s1", "bg1")],
        )
        entities = extract_lore_entities(
            script, {"yui": _char("yui", "Yui", bg="a keeper")},
        )
        block = format_lore_block(entities)
        assert block.startswith("--- World lore relevant to this scene ---")
        assert block.endswith("--- End lore ---")
        # Type prefixes should appear
        assert "[character]" in block
        assert "[premise]" in block
        assert "[location]" in block

    def test_respects_max_chars(self):
        # Construct many entities so the block would exceed max_chars
        script = VNScript(
            title="Huge", description="x" * 200, theme="", start_scene_id="s1",
            scenes=[_scene(f"s{i}", f"bg{i}", "x" * 200) for i in range(20)],
        )
        entities = extract_lore_entities(script, {})
        block = format_lore_block(entities, max_chars=400)
        # Should have truncation marker
        assert "..." in block
        # Should be under 2x max_chars (allowing slight overshoot per line)
        assert len(block) < 800

    def test_strategy_none_doesnt_break_format(self):
        """Regression: older format_examples expected strategy strings; lore
        entities have strategy=None so format must not crash."""
        script = VNScript(
            title="T", description="A story.", theme="",
            start_scene_id="s1", scenes=[_scene("s1", "bg1")],
        )
        entities = extract_lore_entities(script, {})
        block = format_lore_block(entities)
        assert block  # non-empty
        assert "None" not in block  # shouldn't leak strategy=None to output
