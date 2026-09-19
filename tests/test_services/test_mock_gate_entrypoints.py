"""Every door to a live model must honour `mock_mode_var`, not just one.

`ainvoke_llm` has consulted the gate since v4 P0-7, but it is not the only
way to reach a provider: `services/tools.ainvoke_with_tools` and both
`services/streaming` helpers build their own client through `get_llm()`.
Both were ungated, so a `--mock` smoke run still billed real Haiku calls —
character_designer and scene_artist take the tool-calling path whenever
`settings.use_tool_calling` is on, which is the default.

The suite never caught it because the conftest floor strips provider keys:
in tests the ungated call *fails* and falls through to the mocked free-text
path, so it looks like mock worked. Only a real run — with keys in .env —
actually spends. These tests sabotage `get_llm` instead of relying on a
missing key, so an ungated entry point fails loudly here too.
"""
from __future__ import annotations

import pytest

from vn_agent.services.llm import mock_mode_var

# These drive the gate by hand, in both directions.
pytestmark = pytest.mark.no_mock_floor


def _no_live_client(*a, **kw):  # noqa: ARG001
    raise AssertionError("get_llm() reached under mock_mode_var — real spend")


class TestToolCallingHonoursMockGate:
    @pytest.mark.asyncio
    async def test_routes_to_mock_instead_of_building_a_client(self, monkeypatch):
        from vn_agent.services.tools import VisualProfileResult, ainvoke_with_tools

        monkeypatch.setattr("vn_agent.services.tools.get_llm", _no_live_client)

        token = mock_mode_var.set(True)
        try:
            out = await ainvoke_with_tools(
                "sys", "user", [VisualProfileResult],
                caller="character_designer/char_x",
            )
        finally:
            mock_mode_var.reset(token)

        # The canned character_designer fixture already matches this schema —
        # it was written for the tool path but only the fallback ever used it.
        assert isinstance(out, VisualProfileResult)
        assert "anime" in out.art_style

    @pytest.mark.asyncio
    async def test_scene_artist_tool_also_routes_to_mock(self, monkeypatch):
        from vn_agent.services.tools import BackgroundPrompt, ainvoke_with_tools

        monkeypatch.setattr("vn_agent.services.tools.get_llm", _no_live_client)

        token = mock_mode_var.set(True)
        try:
            out = await ainvoke_with_tools(
                "sys", "user", [BackgroundPrompt], caller="scene_artist/scene_1",
            )
        finally:
            mock_mode_var.reset(token)

        assert isinstance(out, BackgroundPrompt)
        assert out.prompt

    @pytest.mark.asyncio
    async def test_gate_off_still_builds_a_real_client(self, monkeypatch):
        """The gate must not swallow the real path when mock is off."""
        from vn_agent.services.tools import BackgroundPrompt, ainvoke_with_tools

        class _FakeResult:
            tool_calls = [{"name": "BackgroundPrompt", "args": {"prompt": "REAL"}}]

        class _FakeLLM:
            def bind_tools(self, tools):  # noqa: ARG002
                return self

            async def ainvoke(self, messages):  # noqa: ARG002
                return _FakeResult()

        monkeypatch.setattr("vn_agent.services.tools.get_llm", lambda *a, **kw: _FakeLLM())
        monkeypatch.setattr("vn_agent.services.tools._log_stop_reason", lambda *a, **kw: None)

        out = await ainvoke_with_tools("sys", "user", [BackgroundPrompt], caller="t")
        assert out.prompt == "REAL"


class TestStreamingHonoursMockGate:
    @pytest.mark.asyncio
    async def test_astream_llm_routes_to_mock(self, monkeypatch):
        from vn_agent.services.streaming import astream_llm

        monkeypatch.setattr("vn_agent.services.streaming.get_llm", _no_live_client)

        seen: list[str] = []
        token = mock_mode_var.set(True)
        try:
            out = await astream_llm(
                "sys", "user", caller="web/stream", on_token=seen.append,
            )
        finally:
            mock_mode_var.reset(token)

        assert out
        assert "".join(seen) == out

    @pytest.mark.asyncio
    async def test_astream_sse_routes_to_mock(self, monkeypatch):
        from vn_agent.services.streaming import astream_sse

        monkeypatch.setattr("vn_agent.services.streaming.get_llm", _no_live_client)

        token = mock_mode_var.set(True)
        try:
            events = [e async for e in astream_sse("sys", "user", caller="web/stream")]
        finally:
            mock_mode_var.reset(token)

        assert events[-1] == "data: [DONE]\n\n"
        assert any(e.startswith("data: {") for e in events[:-1])
