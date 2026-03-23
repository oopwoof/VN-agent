"""Tests for Pydantic schema models."""
import pytest

from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.music import Mood, MusicCue
from vn_agent.schema.script import Scene, VNScript


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
