"""Tests for Ren'Py compiler."""
from vn_agent.compiler.renpy_compiler import compile_script, compile_to_string
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.music import Mood, MusicCue
from vn_agent.schema.script import BranchOption, DialogueLine, Scene, VNScript


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

    def test_emotion_switching(self):
        """Dialogue with emotion changes should emit 'show char emotion' directives."""
        chars = {
            "char_hana": CharacterProfile(
                id="char_hana", name="Hana", color="#ff88aa",
                personality="Cheerful", background="Student", role="protagonist",
            )
        }
        scenes = [
            Scene(
                id="ch1_test",
                title="Test",
                description="test",
                background_id="bg_test",
                characters_present=["char_hana"],
                dialogue=[
                    DialogueLine(character_id="char_hana", text="Hello", emotion="neutral"),
                    DialogueLine(character_id="char_hana", text="Yay!", emotion="happy"),
                ],
                next_scene_id=None,
            ),
        ]
        script = VNScript(
            title="Test", description="t", theme="t",
            start_scene_id="ch1_test", scenes=scenes, characters=["char_hana"],
        )
        result = compile_to_string(script, chars)
        assert "show char_hana happy" in result

    def test_scene_transitions(self):
        """First scene uses 'with fade', subsequent scenes use 'with dissolve'."""
        script, chars = make_simple_script()
        result = compile_to_string(script, chars)
        assert "with fade" in result
        assert "with dissolve" in result

    def test_character_positioning(self):
        """2-character scene should use 'at left' and 'at right'."""
        chars = {
            "char_a": CharacterProfile(
                id="char_a", name="A", color="#ff0000",
                personality="", background="", role="protagonist",
            ),
            "char_b": CharacterProfile(
                id="char_b", name="B", color="#0000ff",
                personality="", background="", role="supporting",
            ),
        }
        scenes = [
            Scene(
                id="ch1_duo",
                title="Duo",
                description="Two characters",
                background_id="bg_test",
                characters_present=["char_a", "char_b"],
                dialogue=[
                    DialogueLine(character_id="char_a", text="Hi", emotion="neutral"),
                ],
                next_scene_id=None,
            ),
        ]
        script = VNScript(
            title="Test", description="t", theme="t",
            start_scene_id="ch1_duo", scenes=scenes,
            characters=["char_a", "char_b"],
        )
        result = compile_to_string(script, chars)
        assert "at left" in result
        assert "at right" in result
