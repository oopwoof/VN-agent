"""LLM Tool Calling: Pydantic schemas as function definitions for structured agent outputs.

Instead of asking the LLM for free-text JSON and parsing with regex, we bind
Pydantic models as tools so the LLM returns validated, typed outputs directly.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from vn_agent.config import get_settings
from vn_agent.services.llm import _log_stop_reason, _make_retry_decorator, get_llm

logger = logging.getLogger(__name__)


# ── Tool schemas (Pydantic models that double as function definitions) ───────

class BackgroundPrompt(BaseModel):
    """Generate a detailed image prompt for a scene background."""

    prompt: str = Field(description="Detailed image generation prompt for the background")


class VisualProfileResult(BaseModel):
    """Design a character's visual appearance for consistent rendering."""

    art_style: str = Field(description="Art style descriptor (e.g. 'anime style, soft watercolor')")
    appearance: str = Field(description="Detailed physical appearance: hair, eyes, build, features")
    default_outfit: str = Field(description="Default clothing and accessories description")


# ── Tool-calling invocation ──────────────────────────────────────────────────

async def ainvoke_with_tools(
    system_prompt: str,
    user_prompt: str,
    tools: list[type[BaseModel]],
    model: str | None = None,
    caller: str = "llm/tools",
) -> BaseModel:
    """Invoke LLM with tool/function calling, return the validated tool result.

    The LLM is given the tool schemas via `bind_tools()`. If it returns a tool
    call, we validate the arguments against the Pydantic schema. If no tool call
    is returned, raises ValueError (caller should handle fallback).

    Args:
        system_prompt: system message
        user_prompt: user message
        tools: list of Pydantic BaseModel classes to bind as tools
        model: optional model override
        caller: identifier for logging

    Returns:
        Validated Pydantic model instance from the tool call
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    settings = get_settings()
    retrier = _make_retry_decorator(settings.llm_max_retries)

    tool_map = {t.__name__: t for t in tools}

    @retrier
    async def _call():
        llm = get_llm(model)
        llm_with_tools = llm.bind_tools(tools)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        result = await llm_with_tools.ainvoke(messages)
        _log_stop_reason(result, caller)

        # Extract tool call from response
        tool_calls = getattr(result, "tool_calls", None) or []
        if tool_calls:
            tc = tool_calls[0]
            tool_name = tc.get("name", "")
            tool_args = tc.get("args", {})
            schema = tool_map.get(tool_name)
            if schema:
                return schema.model_validate(tool_args)

        raise ValueError(f"[{caller}] LLM did not return a tool call")

    return await _call()
