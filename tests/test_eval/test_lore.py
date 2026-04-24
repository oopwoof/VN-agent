"""Tests for Sprint 10-2 lore extraction + Phase 13-1 Step 3 scope formatting."""
from __future__ import annotations

from vn_agent.eval.corpus import AnnotatedSession
from vn_agent.eval.lore import (
    _sentence_break,
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


def _scene(sid, bg, desc="", characters: list[str] | None = None) -> Scene:
    return Scene(
        id=sid, title=sid, description=desc, background_id=bg,
        characters_present=characters or [],
    )


class TestExtract:
    def test_empty_script_returns_empty(self):
        script = VNScript(
            title="", description="", theme="", start_scene_id="",
            scenes=[],
        )
        assert extract_lore_entities(script, {}) == []

    def test_premise_entity_always_scope(self):
        """Phase 13-1 Step 3: premise must be tagged scope=always."""
        script = VNScript(
            title="Lighthouse", description="A keeper in a storm.",
            theme="solitude", start_scene_id="s1",
            scenes=[_scene("s1", "bg1")],
        )
        entities = extract_lore_entities(script, {})
        premise = next(e for e in entities if e.id == "premise:main")
        assert premise.scope == "always"
        assert "Lighthouse" in premise.text
        assert "solitude" in premise.text

    def test_main_character_scoped_always(self):
        """Character appearing in ≥50% of scenes is always-scope."""
        script = VNScript(
            title="T", description="", theme="", start_scene_id="s1",
            scenes=[
                _scene("s1", "bg1", characters=["yui"]),
                _scene("s2", "bg2", characters=["yui"]),
                _scene("s3", "bg3", characters=["yui", "ren"]),
            ],
        )
        chars = {
            "yui": _char("yui", "Yui", bg="lost her father", role="protagonist"),
            "ren": _char("ren", "Ren", bg="young sailor"),
        }
        entities = extract_lore_entities(script, chars)
        yui = next(e for e in entities if e.id == "character:yui")
        ren = next(e for e in entities if e.id == "character:ren")
        assert yui.scope == "always"  # in 3/3 scenes
        assert ren.scope == "scene"   # in 1/3 scenes

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
        # All locations are scene-scope
        assert all(e.scope == "scene" for e in loc_ents)
        shore = next(e for e in loc_ents if e.id == "location:bg_shore")
        assert "s1" in shore.text and "s2" in shore.text

    def test_world_variables_chapter_scoped(self):
        """world_var entities must be chapter-scope (stable across scenes but
        can evolve by chapter)."""
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
        wv = next(e for e in entities if e.id == "world_var:affinity")
        assert wv.scope == "chapter"
        assert "closeness 0-10" in wv.text

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


class TestSentenceBreak:
    def test_short_text_returned_unchanged(self):
        assert _sentence_break("short.", cap=100) == "short."

    def test_breaks_at_period(self):
        text = "First sentence. Second sentence. Third."
        # cap=20 — first period at idx 14, falls within min (0.6*20=12)
        result = _sentence_break(text, cap=20)
        assert result == "First sentence."

    def test_breaks_at_chinese_period(self):
        text = "第一句。第二句。第三句。"
        # char-based cap — be generous
        result = _sentence_break(text, cap=10)
        assert result.endswith("。")
        assert len(result) <= 10

    def test_fallback_to_hard_slice(self):
        text = "a" * 100  # no sentence boundaries
        result = _sentence_break(text, cap=50)
        assert result == "a" * 50


class TestFormatLoreBlock:
    def test_empty_returns_three_empty_strings(self):
        """New contract: always returns 3-tuple."""
        result = format_lore_block(retrieved=[])
        assert result == ("", "", "")

    def test_renders_three_separate_blocks(self):
        """Each scope gets its own labeled block."""
        always = [AnnotatedSession(
            id="premise:main", title="t", text="Test premise.", strategy=None, scope="always",
        )]
        chapter = [AnnotatedSession(
            id="world_var:affinity", title="affinity",
            text="affinity (int, starts 0): closeness 0-10",
            strategy=None, scope="chapter",
        )]
        retrieved = [AnnotatedSession(
            id="location:bg_shore", title="bg_shore",
            text="bg_shore: morning at the cliffs",
            strategy=None, scope="scene",
        )]
        a_block, c_block, r_block = format_lore_block(
            retrieved=retrieved,
            always_entities=always,
            chapter_entities=chapter,
        )
        assert "Always-on lore" in a_block
        assert "[premise]" in a_block
        assert "Chapter-scope lore" in c_block
        assert "[world_var]" in c_block
        assert "Retrieved lore" in r_block
        assert "[location]" in r_block

    def test_always_entities_never_truncated(self):
        """always-scope has cap=10**9 — long premise must NOT be cut."""
        long_premise = "X" * 5000  # way past any chapter/scene cap
        always = [AnnotatedSession(
            id="premise:main", title="t", text=long_premise,
            strategy=None, scope="always",
        )]
        a_block, _, _ = format_lore_block(
            retrieved=[], always_entities=always,
        )
        # full premise preserved
        assert long_premise in a_block

    def test_chapter_cap_applied(self):
        """chapter-scope text > 800 char gets sentence-broken."""
        long_text = "A. " + ("B" * 1000)
        chapter = [AnnotatedSession(
            id="world_var:x", title="x", text=long_text,
            strategy=None, scope="chapter",
        )]
        _, c_block, _ = format_lore_block(
            retrieved=[], chapter_entities=chapter,
        )
        # Chapter entity line cap is 800; "[world_var] " prefix ~12 chars;
        # _sentence_break applied with cap=800 → some truncation.
        assert len(c_block) < 900

    def test_retrieved_respects_total_cap(self):
        """When total_cap is tight, retrieved block gets dropped/truncated."""
        always = [AnnotatedSession(
            id="premise:main", title="t", text="P" * 500,
            strategy=None, scope="always",
        )]
        # 100 small retrieved entries — would blow past tight budget
        retrieved = [
            AnnotatedSession(
                id=f"location:bg{i}", title=f"bg{i}", text=f"desc {i}",
                strategy=None, scope="scene",
            )
            for i in range(100)
        ]
        _, _, r_block = format_lore_block(
            retrieved=retrieved, always_entities=always,
            total_cap=600,
        )
        # With always taking most budget, retrieved should be empty or truncated with "..."
        if r_block:
            assert "..." in r_block or len(r_block) < 200
