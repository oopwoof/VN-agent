"""Tests for Writer smart truncation fallback (Sprint 6-8)."""
from __future__ import annotations

import pytest

from vn_agent.agents.writer import _regenerate_short_dialogue
from vn_agent.schema.script import DialogueLine, Scene


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


def _scene() -> Scene:
    return Scene(
        id="s1", title="Test Scene", description="a test scene",
        background_id="bg", characters_present=["alice", "bob"],
    )


def _existing(n: int = 2) -> list[DialogueLine]:
    return [
        DialogueLine(character_id="alice", text=f"Line {i} from alice", emotion="neutral")
        for i in range(n)
    ]


def _settings_stub(writer_model: str = "claude-haiku-4-5-20251001"):
    """Minimal settings object exposing the two fields _regenerate_short_dialogue uses."""
    class _S:
        llm_writer_model = writer_model
    return _S()


class TestRegenerateShortDialogue:
    @pytest.mark.asyncio
    async def test_empty_existing_returns_empty(self, tmp_path):
        """When parser produced nothing, we can't continue — return empty and let caller fall back."""
        result = await _regenerate_short_dialogue(
            _scene(), [], missing=3, settings=_settings_stub(),
            output_dir=str(tmp_path),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_successful_continuation(self, mocker, tmp_path):
        """Happy path: LLM returns valid JSON continuation, we parse and cap to `missing`."""
        fake_json = (
            '[{"character_id": "alice", "text": "Continuation line 1", "emotion": "happy"},'
            '{"character_id": "bob", "text": "Continuation line 2", "emotion": "sad"},'
            '{"character_id": null, "text": "Continuation narration", "emotion": "neutral"}]'
        )
        mocker.patch(
            "vn_agent.agents.writer.ainvoke_llm",
            return_value=_FakeMessage(fake_json),
        )
        result = await _regenerate_short_dialogue(
            _scene(), _existing(2), missing=2,
            settings=_settings_stub(), output_dir=str(tmp_path),
        )
        assert len(result) == 2  # capped to missing=2 even though LLM returned 3
        assert result[0].text == "Continuation line 1"
        assert result[1].text == "Continuation line 2"

    @pytest.mark.asyncio
    async def test_llm_exception_returns_empty(self, mocker, tmp_path):
        """When the continuation call raises, we must NOT propagate — caller expects []."""
        mocker.patch(
            "vn_agent.agents.writer.ainvoke_llm",
            side_effect=RuntimeError("simulated API failure"),
        )
        result = await _regenerate_short_dialogue(
            _scene(), _existing(2), missing=2,
            settings=_settings_stub(), output_dir=str(tmp_path),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_garbage_response_returns_empty_or_fallback(self, mocker, tmp_path):
        """LLM returns non-JSON nonsense — _parse_dialogue will fall back; we just verify no crash."""
        mocker.patch(
            "vn_agent.agents.writer.ainvoke_llm",
            return_value=_FakeMessage("this is not JSON at all, just prose about cats"),
        )
        result = await _regenerate_short_dialogue(
            _scene(), _existing(2), missing=3,
            settings=_settings_stub(), output_dir=str(tmp_path),
        )
        # _parse_dialogue's fallback produces a placeholder; we cap to missing=3.
        # Either empty or partial is acceptable — the key is no exception.
        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_cap_applies_when_llm_generous(self, mocker, tmp_path):
        """If LLM returns more lines than requested, we cap to missing."""
        many_lines = "[" + ",".join(
            f'{{"character_id": null, "text": "line {i}", "emotion": "neutral"}}'
            for i in range(10)
        ) + "]"
        mocker.patch(
            "vn_agent.agents.writer.ainvoke_llm",
            return_value=_FakeMessage(many_lines),
        )
        result = await _regenerate_short_dialogue(
            _scene(), _existing(1), missing=1,
            settings=_settings_stub(), output_dir=str(tmp_path),
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Phase 13-2 Step 1 (AUDITS §2 piggyback):
# run_writer must snapshot state_constraints onto each scene's
# state_constraints_seen before calling _write_scene.
# ---------------------------------------------------------------------------


class TestStateConstraintsSnapshot:
    """End-to-end check: run_writer loop copies the current state_constraints
    text onto scene.state_constraints_seen so it survives into the persisted
    vn_script.json (AUDITS §2: "Writer 当时看到了什么" was previously lost)."""

    @pytest.mark.asyncio
    async def test_constraints_propagated_to_every_scene(self, mocker, tmp_path):
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import Scene, VNScript

        # Mock _write_scene to pass the input scene through untouched,
        # so we can inspect what run_writer set on it.
        captured_scenes = []

        async def _fake_write(scene, *args, **kwargs):
            captured_scenes.append(scene)
            return scene  # unchanged — dialogue left empty

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")  # no disk IO

        scenes = [
            Scene(id=f"s{i}", title=f"S{i}", description="x",
                  background_id="bg", characters_present=["a"])
            for i in range(3)
        ]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes, world_variables=[],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=3, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)
        state["state_constraints"] = "CONSTRAINT: x==1 ⇒ hesitate. x==0 ⇒ push."

        result = await run_writer(state)
        out_script = result["vn_script"]

        assert len(out_script.scenes) == 3
        # Every persisted scene carries the constraint snapshot
        for scene in out_script.scenes:
            assert scene.state_constraints_seen == \
                "CONSTRAINT: x==1 ⇒ hesitate. x==0 ⇒ push."

    @pytest.mark.asyncio
    async def test_empty_constraints_leaves_field_none(self, mocker, tmp_path):
        """When state_constraints is empty string (no orchestrator output),
        scene.state_constraints_seen must stay None — don't pollute with ""."""
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import Scene, VNScript

        async def _fake_write(scene, *args, **kwargs):
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")

        scenes = [Scene(id="s0", title="S", description="x", background_id="bg")]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes, world_variables=[],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=1, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)
        state["state_constraints"] = ""  # empty

        result = await run_writer(state)
        assert result["vn_script"].scenes[0].state_constraints_seen is None
