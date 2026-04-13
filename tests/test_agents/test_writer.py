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
