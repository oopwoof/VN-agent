"""Full pipeline integration tests (text-only, mocked LLM)."""
from __future__ import annotations

import re

import pytest

from vn_agent.agents.graph import build_graph
from vn_agent.agents.state import initial_state
from vn_agent.compiler.renpy_compiler import compile_to_string

DIRECTOR_STEP1_RESPONSE = """{
  "title": "Echoes of Tomorrow",
  "description": "A short story about choices",
  "start_scene_id": "ch1_morning",
  "scenes": [
    {
      "id": "ch1_morning",
      "title": "Morning Arrival",
      "description": "The protagonist arrives at school",
      "background_id": "bg_school",
      "characters_present": ["char_hana"],
      "narrative_strategy": "accumulate"
    },
    {
      "id": "ch1_friendly",
      "title": "A Warm Greeting",
      "description": "They exchange warm words",
      "background_id": "bg_school",
      "characters_present": ["char_hana"],
      "narrative_strategy": "accumulate"
    },
    {
      "id": "ch1_distant",
      "title": "Silent Pass",
      "description": "They walk by in silence",
      "background_id": "bg_corridor",
      "characters_present": ["char_hana"],
      "narrative_strategy": "erode"
    }
  ],
  "characters": [
    {
      "id": "char_hana",
      "name": "Hana",
      "color": "#ff88aa",
      "personality": "Cheerful and warm",
      "background": "The protagonist's childhood friend",
      "role": "love interest"
    }
  ]
}"""

DIRECTOR_STEP2_RESPONSE = """{
  "scenes": [
    {
      "id": "ch1_morning",
      "next_scene_id": null,
      "branches": [
        {"text": "Say hello", "next_scene_id": "ch1_friendly"},
        {"text": "Walk past", "next_scene_id": "ch1_distant"}
      ],
      "music_mood": "peaceful",
      "music_description": "soft piano"
    },
    {
      "id": "ch1_friendly",
      "next_scene_id": null,
      "branches": [],
      "music_mood": "romantic",
      "music_description": "warm strings"
    },
    {
      "id": "ch1_distant",
      "next_scene_id": null,
      "branches": [],
      "music_mood": "melancholic",
      "music_description": "quiet piano"
    }
  ]
}"""

WRITER_MOCK_RESPONSE = """[
  {"character_id": null, "text": "The morning light filters through the windows.", "emotion": "neutral"},
  {"character_id": "char_hana", "text": "Good morning! You're early today.", "emotion": "happy"},
  {"character_id": null, "text": "She smiles warmly.", "emotion": "neutral"}
]"""

REVIEWER_MOCK_RESPONSE = "PASS"


class MockMessage:
    """A mock LLM message with a .content attribute."""

    def __init__(self, content: str):
        self.content = content


@pytest.fixture
def mock_ainvoke(mocker):
    from vn_agent.services.mock_llm import _dispatch

    async def side_effect(system, user, schema=None, model=None, caller="llm"):
        system_lower = system.lower()

        # For non-Chinese English tests, keep the original inline fixtures for backward compat
        has_cjk = bool(re.search(r'[\u4e00-\u9fff]', user))
        if has_cjk:
            content = _dispatch(system_lower, user, caller)
        elif "reviewer" in system_lower:
            content = REVIEWER_MOCK_RESPONSE
        elif "director" in system_lower:
            # Dispatch by caller tag (more reliable than system prompt content matching)
            if "step2" in caller or "details" in caller:
                content = DIRECTOR_STEP2_RESPONSE
            elif "navigation" in system_lower and "plan the overall" not in system_lower:
                content = DIRECTOR_STEP2_RESPONSE
            else:
                content = DIRECTOR_STEP1_RESPONSE
        elif "writer" in system_lower or "dialogue" in system_lower:
            content = WRITER_MOCK_RESPONSE
        else:
            content = WRITER_MOCK_RESPONSE

        return MockMessage(content)

    # Patch in each agent module's local namespace (they use `from ... import`)
    mocker.patch("vn_agent.agents.director.ainvoke_llm", side_effect=side_effect)
    mocker.patch("vn_agent.agents.writer.ainvoke_llm", side_effect=side_effect)
    mocker.patch("vn_agent.agents.reviewer.ainvoke_llm", side_effect=side_effect)
    # Also patch the source module for completeness
    return mocker.patch("vn_agent.services.llm.ainvoke_llm", side_effect=side_effect)


async def _run_pipeline(text_only: bool = True, theme: str = "A school romance about choices") -> dict:
    """Helper to run the full pipeline and return the final state."""
    graph = build_graph()
    state = initial_state(
        theme=theme,
        output_dir="/tmp/test_vn",
        text_only=text_only,
    )
    result = await graph.ainvoke(state)
    return result


class TestPipelineIntegration:
    @pytest.mark.asyncio
    async def test_text_only_pipeline_produces_valid_script(self, mock_ainvoke):
        """Run the full pipeline with text_only=True and verify the output VNScript."""
        final_state = await _run_pipeline(text_only=True)

        # vn_script must be a VNScript with exactly 3 scenes
        from vn_agent.schema.script import VNScript
        vn_script = final_state["vn_script"]
        assert vn_script is not None
        assert isinstance(vn_script, VNScript)
        assert len(vn_script.scenes) == 3

        # Title should match the director mock
        assert vn_script.title == "Echoes of Tomorrow"

        # Review should have passed
        assert final_state["review_passed"] is True

        # Structural check should also pass independently
        from vn_agent.agents.reviewer import _structural_check
        result = _structural_check(vn_script)
        assert result.passed, f"Structural check failed: {result.feedback}"

    @pytest.mark.asyncio
    async def test_pipeline_produces_compilable_renpy(self, mock_ainvoke):
        """Pipeline output compiles to valid Ren'Py that contains expected constructs."""
        final_state = await _run_pipeline(text_only=True)

        vn_script = final_state["vn_script"]
        characters = final_state["characters"]

        output = compile_to_string(vn_script, characters)

        assert "label ch1_morning:" in output
        assert "menu:" in output
        assert "jump ch1_friendly" in output
        assert "play music" in output  # from peaceful music cue

    @pytest.mark.asyncio
    async def test_pipeline_text_only_skips_assets(self, mock_ainvoke):
        """text_only=True must skip CharacterDesigner and SceneArtist."""
        final_state = await _run_pipeline(text_only=True)

        # CharacterDesigner sets visual on character profiles; it must NOT have run
        characters = final_state["characters"]
        assert len(characters) > 0
        for char_id, char in characters.items():
            assert char.visual is None, (
                f"Character {char_id} has a visual profile set — "
                "CharacterDesigner must not run in text_only mode"
            )

    @pytest.mark.asyncio
    async def test_chinese_theme_pipeline(self, mock_ainvoke):
        """Chinese theme should produce Chinese dialogue in the output."""
        final_state = await _run_pipeline(text_only=True, theme="校园恋爱")

        vn_script = final_state["vn_script"]
        assert vn_script is not None
        assert len(vn_script.scenes) > 0

        # At least some dialogue lines should contain CJK characters
        all_text = " ".join(
            line.text for scene in vn_script.scenes for line in scene.dialogue
        )
        assert re.search(r'[\u4e00-\u9fff]', all_text), (
            f"Expected Chinese characters in dialogue but got: {all_text[:200]}"
        )
