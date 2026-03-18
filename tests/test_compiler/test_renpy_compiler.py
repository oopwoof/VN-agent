"""Tests for Ren'Py compiler."""
import pytest
from vn_agent.schema.script import VNScript, Scene, DialogueLine, BranchOption
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.music import MusicCue, Mood
from vn_agent.compiler.renpy_compiler import compile_to_string, compile_script


def make_simple_script() -> tuple[VNScript, dict[str, CharacterProfile]]:
    """Create a minimal VNScript for testing."""
    chars = {
        "char_sakura": CharacterProfile(
            id="char_sakura",
            name="Sakura",
            color="#ff88aa",
            personality="Cheerful",
            background="High school student",
            role="protagonist",
        )
    }
    scenes = [
        Scene(
            id="ch1_start",
            title="Morning",
            description="A sunny morning",
            background_id="bg_classroom",
            music=MusicCue(
                mood=Mood.PEACEFUL,
                description="soft piano",
                track_id="peaceful_morning",
                file_path="audio/bgm/peaceful_morning.ogg",
            ),
            characters_present=["char_sakura"],
            dialogue=[
                DialogueLine(character_id=None, text="The morning sun filters through the windows.", emotion="neutral"),
                DialogueLine(character_id="char_sakura", text="Good morning!", emotion="happy"),
            ],
            branches=[
                BranchOption(text="Say hello back", next_scene_id="ch1_friendly"),
                BranchOption(text="Stay silent", next_scene_id="ch1_shy"),
            ],
        ),
        Scene(
            id="ch1_friendly",
            title="Friendly",
            description="A friendly response",
            background_id="bg_classroom",
            characters_present=["char_sakura"],
            dialogue=[
                DialogueLine(character_id="char_sakura", text="You seem friendly!", emotion="happy"),
            ],
            next_scene_id=None,
        ),
        Scene(
            id="ch1_shy",
            title="Shy",
            description="A shy response",
            background_id="bg_classroom",
            characters_present=["char_sakura"],
            dialogue=[
                DialogueLine(character_id="char_sakura", text="Oh... I see.", emotion="sad"),
            ],
            next_scene_id=None,
        ),
    ]
    script = VNScript(
        title="Test VN",
        description="A test visual novel",
        theme="testing",
        start_scene_id="ch1_start",
        scenes=scenes,
        characters=list(chars.keys()),
    )
    return script, chars


class TestRenPyCompiler:
    def test_compiles_without_error(self):
        script, chars = make_simple_script()
        result = compile_to_string(script, chars)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_labels(self):
        script, chars = make_simple_script()
        result = compile_to_string(script, chars)
        assert "label ch1_start:" in result
        assert "label ch1_friendly:" in result
        assert "label ch1_shy:" in result

    def test_contains_dialogue(self):
        script, chars = make_simple_script()
        result = compile_to_string(script, chars)
        assert "Good morning!" in result
        assert "The morning sun" in result

    def test_contains_menu(self):
        script, chars = make_simple_script()
        result = compile_to_string(script, chars)
        assert "menu:" in result
        assert "Say hello back" in result
        assert "jump ch1_friendly" in result

    def test_contains_play_music(self):
        script, chars = make_simple_script()
        result = compile_to_string(script, chars)
        assert "play music" in result
        assert "peaceful_morning.ogg" in result
        assert "fadein" in result

    def test_compiles_all_files(self):
        script, chars = make_simple_script()
        files = compile_script(script, chars)
        assert "game/script.rpy" in files
        assert "game/characters.rpy" in files
        assert "game/gui.rpy" in files

    def test_characters_rpy_defines(self):
        script, chars = make_simple_script()
        files = compile_script(script, chars)
        chars_rpy = files["game/characters.rpy"]
        assert "define char_sakura" in chars_rpy
        assert "Sakura" in chars_rpy

    def test_contains_start_label(self):
        script, chars = make_simple_script()
        result = compile_to_string(script, chars)
        assert "label start:" in result
        assert "jump ch1_start" in result
