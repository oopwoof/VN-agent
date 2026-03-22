"""Tests for streaming LLM output."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vn_agent.services.streaming import astream_llm, astream_sse


def _make_chunk(content: str, usage: dict | None = None):
    """Create a mock LangChain AIMessageChunk."""
    chunk = MagicMock()
    chunk.content = content
    chunk.usage_metadata = usage or {}
    return chunk


async def _mock_astream(messages):
    """Simulate LLM streaming with 3 chunks."""
    yield _make_chunk("Hello")
    yield _make_chunk(" world")
    yield _make_chunk("!", {"input_tokens": 10, "output_tokens": 3})


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.astream = _mock_astream
    return llm


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.llm_model = "test-model"
    settings.llm_provider = "anthropic"
    settings.llm_temperature = 0.7
    settings.llm_max_tokens = 1000
    settings.llm_api_key = "test"
    settings.llm_base_url = ""
    settings.anthropic_api_key = "test"
    return settings


class TestAstreamLlm:
    @pytest.mark.asyncio
    async def test_collects_full_text(self, mock_llm, mock_settings):
        with (
            patch("vn_agent.services.streaming.get_llm", return_value=mock_llm),
            patch("vn_agent.services.streaming.get_settings", return_value=mock_settings),
        ):
            result = await astream_llm("sys", "user", caller="test")
            assert result == "Hello world!"

    @pytest.mark.asyncio
    async def test_on_token_callback(self, mock_llm, mock_settings):
        tokens = []
        with (
            patch("vn_agent.services.streaming.get_llm", return_value=mock_llm),
            patch("vn_agent.services.streaming.get_settings", return_value=mock_settings),
        ):
            await astream_llm("sys", "user", on_token=tokens.append, caller="test")
            assert tokens == ["Hello", " world", "!"]

    @pytest.mark.asyncio
    async def test_empty_chunks_skipped(self, mock_settings):
        async def empty_stream(messages):
            yield _make_chunk("")
            yield _make_chunk("data")
            yield _make_chunk("")

        llm = MagicMock()
        llm.astream = empty_stream

        tokens = []
        with (
            patch("vn_agent.services.streaming.get_llm", return_value=llm),
            patch("vn_agent.services.streaming.get_settings", return_value=mock_settings),
        ):
            result = await astream_llm("sys", "user", on_token=tokens.append, caller="test")
            assert result == "data"
            assert tokens == ["data"]


class TestAstreamSse:
    @pytest.mark.asyncio
    async def test_sse_format(self, mock_llm):
        with patch("vn_agent.services.streaming.get_llm", return_value=mock_llm):
            events = []
            async for event in astream_sse("sys", "user", caller="test"):
                events.append(event)

            # 3 data events + 1 DONE
            assert len(events) == 4
            assert events[-1] == "data: [DONE]\n\n"
            assert '"token": "Hello"' in events[0]
            assert all(e.startswith("data: ") for e in events)
