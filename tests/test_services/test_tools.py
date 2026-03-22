"""Tests for LLM tool calling service."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from vn_agent.services.tools import (
    BackgroundPrompt,
    VisualProfileResult,
    ainvoke_with_tools,
)


class SimpleResult(BaseModel):
    """A test tool."""

    answer: str = Field(description="The answer")


class TestToolSchemas:
    def test_background_prompt_schema(self):
        bp = BackgroundPrompt(prompt="a sunset over the ocean")
        assert bp.prompt == "a sunset over the ocean"

    def test_visual_profile_schema(self):
        vp = VisualProfileResult(
            art_style="anime",
            appearance="blue hair, green eyes",
            default_outfit="school uniform",
        )
        assert vp.art_style == "anime"
        assert "blue hair" in vp.appearance


class TestAinvokeWithTools:
    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.llm_max_retries = 1
        settings.llm_provider = "anthropic"
        settings.llm_model = "test-model"
        settings.llm_temperature = 0.7
        settings.llm_max_tokens = 1000
        settings.llm_api_key = "test-key"
        settings.llm_base_url = ""
        settings.anthropic_api_key = "test-key"
        return settings

    @pytest.mark.asyncio
    async def test_successful_tool_call(self, mock_settings):
        """LLM returns a valid tool call → validated Pydantic model."""
        mock_result = MagicMock()
        mock_result.tool_calls = [
            {"name": "SimpleResult", "args": {"answer": "42"}}
        ]
        mock_result.response_metadata = {}

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_result)

        mock_base_llm = MagicMock()
        mock_base_llm.bind_tools = MagicMock(return_value=mock_llm)

        with (
            patch("vn_agent.services.tools.get_llm", return_value=mock_base_llm),
            patch("vn_agent.services.tools.get_settings", return_value=mock_settings),
        ):
            result = await ainvoke_with_tools("sys", "user", [SimpleResult], caller="test")
            assert isinstance(result, SimpleResult)
            assert result.answer == "42"

    @pytest.mark.asyncio
    async def test_no_tool_call_raises(self, mock_settings):
        """LLM returns content without tool call → raises ValueError."""
        mock_result = MagicMock()
        mock_result.tool_calls = []
        mock_result.response_metadata = {}

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_result)

        mock_base_llm = MagicMock()
        mock_base_llm.bind_tools = MagicMock(return_value=mock_llm)

        with (
            patch("vn_agent.services.tools.get_llm", return_value=mock_base_llm),
            patch("vn_agent.services.tools.get_settings", return_value=mock_settings),
        ):
            with pytest.raises(ValueError, match="did not return a tool call"):
                await ainvoke_with_tools("sys", "user", [SimpleResult], caller="test")

    @pytest.mark.asyncio
    async def test_background_prompt_tool(self, mock_settings):
        """Integration test with BackgroundPrompt schema."""
        mock_result = MagicMock()
        mock_result.tool_calls = [
            {"name": "BackgroundPrompt", "args": {"prompt": "sunset over ocean, anime style"}}
        ]
        mock_result.response_metadata = {}

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_result)

        mock_base_llm = MagicMock()
        mock_base_llm.bind_tools = MagicMock(return_value=mock_llm)

        with (
            patch("vn_agent.services.tools.get_llm", return_value=mock_base_llm),
            patch("vn_agent.services.tools.get_settings", return_value=mock_settings),
        ):
            result = await ainvoke_with_tools("sys", "user", [BackgroundPrompt], caller="test")
            assert isinstance(result, BackgroundPrompt)
            assert "sunset" in result.prompt
