"""Tests for Pydantic schema models."""
import pytest
from pydantic import ValidationError

from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.music import Mood, MusicCue
from vn_agent.schema.script import (
    MacroReference,
    Scene,
    SceneBrief,
    SceneThinking,
    VNScript,
)


class TestMusicCue:
    def test_defaults(self):
        cue = MusicCue(mood=Mood.PEACEFUL, description="soft piano")
        assert cue.fade_in == 1.0
        assert cue.fade_out == 1.0
        assert cue.volume == 0.7
        assert cue.loop is True
        assert cue.track_id is None
        assert cue.file_path is None

    def test_all_moods_valid(self):
        for mood in Mood:
            cue = MusicCue(mood=mood, description="test")
            assert cue.mood == mood

    def test_volume_bounds(self):
        with pytest.raises(Exception):
            MusicCue(mood=Mood.PEACEFUL, description="test", volume=1.5)
        with pytest.raises(Exception):
            MusicCue(mood=Mood.PEACEFUL, description="test", volume=-0.1)


class TestScene:
    def test_minimal_scene(self):
        scene = Scene(
            id="ch1_open",
            title="Opening",
            description="The story begins",
            background_id="bg_classroom",
        )
        assert scene.id == "ch1_open"
        assert scene.dialogue == []
        assert scene.branches == []
        assert scene.music is None

    def test_scene_with_music(self):
        cue = MusicCue(mood=Mood.ROMANTIC, description="love theme")
        scene = Scene(
            id="ch1_romance",
            title="Romance",
            description="A romantic moment",
            background_id="bg_garden",
            music=cue,
        )
        assert scene.music is not None
        assert scene.music.mood == Mood.ROMANTIC

    def test_scene_serialization(self):
        scene = Scene(
            id="test",
            title="Test",
            description="A test scene",
            background_id="bg_test",
        )
        data = scene.model_dump()
        restored = Scene.model_validate(data)
        assert restored.id == scene.id


class TestVNScript:
    def test_minimal_script(self):
        script = VNScript(
            title="Test Story",
            description="A test",
            theme="test theme",
            start_scene_id="ch1_open",
        )
        assert script.revision_count == 0
        assert script.scenes == []

    def test_script_with_scenes(self):
        scene1 = Scene(
            id="ch1_open",
            title="Opening",
            description="Start",
            background_id="bg_start",
            next_scene_id="ch1_end",
        )
        scene2 = Scene(
            id="ch1_end",
            title="End",
            description="Finish",
            background_id="bg_end",
        )
        script = VNScript(
            title="Test",
            description="Test story",
            theme="test",
            start_scene_id="ch1_open",
            scenes=[scene1, scene2],
        )
        assert len(script.scenes) == 2

    def test_json_roundtrip(self):
        script = VNScript(
            title="Round Trip",
            description="Testing serialization",
            theme="test",
            start_scene_id="ch1",
            scenes=[
                Scene(id="ch1", title="Ch1", description="First", background_id="bg1")
            ],
        )
        json_str = script.model_dump_json()
        restored = VNScript.model_validate_json(json_str)
        assert restored.title == script.title
        assert len(restored.scenes) == len(script.scenes)


class TestCharacterProfile:
    def test_basic_character(self):
        char = CharacterProfile(
            id="char_hero",
            name="Hero",
            personality="Brave and kind",
            background="Orphan who became a knight",
            role="protagonist",
        )
        assert char.id == "char_hero"
        assert char.visual is None
        assert char.color == "#ffffff"


# ---------------------------------------------------------------------------
# Phase 13-2 Step 1 (route 4): MacroReference + SceneBrief + Scene/VNScript
# plumbing for AUDITS §2 state_constraints_seen.
# ---------------------------------------------------------------------------


class TestMacroReference:
    def test_all_defaults_empty_valid(self):
        """Every field is Optional-shaped so short demos can leave everything
        blank without tripping validation."""
        m = MacroReference()
        assert m.theme_thesis == ""
        assert m.pacing_arc == ""
        assert m.foreshadow_plan == []
        assert m.character_voice_charter == {}
        assert m.tone_register == ""

    def test_full_populated(self):
        m = MacroReference(
            theme_thesis="duty vs memory in the three hours before the tide",
            pacing_arc="accumulate s01-04 → rupture s05 → resolve s08",
            foreshadow_plan=[
                {"planted_in": "s01", "payoff_in": "s05", "element": "the watch"},
            ],
            character_voice_charter={
                "yui": "short declaratives, sea metaphors",
                "ren": "question-heavy, academic",
            },
            tone_register="literary third-person-limited",
        )
        assert m.character_voice_charter["yui"].startswith("short")
        assert m.foreshadow_plan[0]["element"] == "the watch"

    def test_theme_thesis_max_length_enforced(self):
        with pytest.raises(ValidationError):
            MacroReference(theme_thesis="x" * 400)

    def test_foreshadow_plan_accepts_heterogeneous_dicts(self):
        """list[dict] with varying keys is fine — Director invents the shape."""
        m = MacroReference(foreshadow_plan=[
            {"planted_in": "s01", "payoff_in": "s05"},
            {"planted_in": "s02", "payoff_in": "s07", "element": "the letter"},
        ])
        assert len(m.foreshadow_plan) == 2


class TestSceneBrief:
    def test_defaults(self):
        b = SceneBrief()
        assert b.beats == []
        assert b.character_blocking == {}
        assert b.emotional_curve == []
        assert b.tension_target == "medium"
        assert b.subtext_notes == ""

    def test_beats_hard_capped_at_7(self):
        """Director over-producing beats gets silently truncated, not
        rejected — pipeline continuity beats strict validation."""
        b = SceneBrief(beats=[f"beat {i}" for i in range(12)])
        assert len(b.beats) == 7
        assert b.beats[-1] == "beat 6"  # kept first 7

    def test_emotional_curve_hard_capped_at_5(self):
        b = SceneBrief(emotional_curve=["a", "b", "c", "d", "e", "f", "g"])
        assert len(b.emotional_curve) == 5

    def test_tension_target_literal(self):
        for valid in ("low", "medium", "high", "climax"):
            b = SceneBrief(tension_target=valid)
            assert b.tension_target == valid
        with pytest.raises(ValidationError):
            SceneBrief(tension_target="extreme")

    def test_subtext_notes_max_length(self):
        with pytest.raises(ValidationError):
            SceneBrief(subtext_notes="x" * 500)


class TestScenePhase13_2Fields:
    """Scene-level new fields — both Optional, must default to None to keep
    older vn_script.json round-tripping."""

    def test_scene_brief_default_none(self):
        scene = Scene(
            id="s1", title="t", description="d", background_id="bg",
        )
        assert scene.scene_brief is None

    def test_scene_brief_accepts_nested(self):
        scene = Scene(
            id="s1", title="t", description="d", background_id="bg",
            scene_brief=SceneBrief(beats=["arrival", "recognition"]),
        )
        assert scene.scene_brief is not None
        assert scene.scene_brief.beats == ["arrival", "recognition"]

    def test_state_constraints_seen_default_none(self):
        scene = Scene(
            id="s1", title="t", description="d", background_id="bg",
        )
        assert scene.state_constraints_seen is None


class TestVNScriptMacroReference:
    def test_macro_reference_default_none(self):
        """Backward-compat: older vn_script.json files without macro_reference
        still load without error."""
        script = VNScript(
            title="t", description="d", theme="th", start_scene_id="s1",
        )
        assert script.macro_reference is None

    def test_macro_reference_round_trip_via_dump(self):
        """Serialize + revalidate must preserve MacroReference nested structure."""
        original = VNScript(
            title="T", description="d", theme="th", start_scene_id="s1",
            macro_reference=MacroReference(
                theme_thesis="x",
                character_voice_charter={"a": "brief"},
            ),
        )
        payload = original.model_dump_json()
        revived = VNScript.model_validate_json(payload)
        assert revived.macro_reference is not None
        assert revived.macro_reference.theme_thesis == "x"
        assert revived.macro_reference.character_voice_charter == {"a": "brief"}


# ---------------------------------------------------------------------------
# Phase 13-2 Step 2 (route 4): SceneThinking — pre-write planning artifact.
# ---------------------------------------------------------------------------


class TestSceneThinking:
    def test_all_defaults_empty_valid(self):
        t = SceneThinking()
        assert t.writing_intent == ""
        assert t.key_beats_expanded == []
        assert t.callback_plan == []
        assert t.opening_hook == ""
        assert t.closing_beat == ""
        assert t.voice_notes == {}
        assert t.risks == []

    def test_full_populated(self):
        t = SceneThinking(
            writing_intent="resolve the father's watch callback with restraint",
            key_beats_expanded=[
                "yui holds the watch — first time since s01",
                "ren sees it, says nothing",
                "the lamp catches the second hand's reflection",
            ],
            callback_plan=[
                {"ref_scene_id": "s01", "what_lands": "reveal that the watch stopped the night he died"},
            ],
            opening_hook="waves hitting the lantern room — rhythm Wider than speech",
            closing_beat="yui pockets the watch without looking at ren; cuts to black",
            voice_notes={"yui": "tighter cadence — she's guarding"},
            risks=["don't over-explain the watch; subtext only"],
        )
        assert t.writing_intent.startswith("resolve")
        assert len(t.key_beats_expanded) == 3
        assert t.callback_plan[0]["ref_scene_id"] == "s01"

    def test_key_beats_expanded_capped_at_8(self):
        t = SceneThinking(key_beats_expanded=[f"beat {i}" for i in range(15)])
        assert len(t.key_beats_expanded) == 8

    def test_risks_capped_at_6(self):
        t = SceneThinking(risks=[f"risk {i}" for i in range(10)])
        assert len(t.risks) == 6

    def test_writing_intent_max_length(self):
        with pytest.raises(ValidationError):
            SceneThinking(writing_intent="x" * 400)


class TestSceneThinkingOnScene:
    def test_scene_thinking_default_none(self):
        scene = Scene(
            id="s1", title="t", description="d", background_id="bg",
        )
        assert scene.thinking is None

    def test_scene_thinking_nested_round_trip(self):
        """Scene with SceneThinking survives JSON round-trip."""
        scene = Scene(
            id="s1", title="t", description="d", background_id="bg",
            thinking=SceneThinking(
                writing_intent="open with silence",
                key_beats_expanded=["pause", "look", "speak"],
            ),
        )
        payload = scene.model_dump_json()
        revived = Scene.model_validate_json(payload)
        assert revived.thinking is not None
        assert revived.thinking.writing_intent == "open with silence"
        assert revived.thinking.key_beats_expanded == ["pause", "look", "speak"]
