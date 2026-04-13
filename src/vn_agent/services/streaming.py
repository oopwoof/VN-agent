"""Streaming LLM output: token-by-token delivery for CLI and SSE.

Uses LangChain's `.astream()` interface to yield chunks as they arrive,
reducing perceived latency for long LLM calls.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Callable

from vn_agent.config import get_settings
from vn_agent.services.llm import get_llm
from vn_agent.services.token_tracker import get_active_tracker

logger = logging.getLogger(__name__)


async def astream_llm(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    caller: str = "llm/stream",
    on_token: Callable[[str], None] | None = None,
) -> str:
    """Stream LLM response token-by-token, return the full collected text.

    Args:
        system_prompt: system message
        user_prompt: user message
        model: optional model override
        caller: identifier for logging
        on_token: optional callback invoked with each text chunk

    Returns:
        Complete response text
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_llm(model)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    chunks: list[str] = []
    total_input = 0
    total_output = 0

    async for chunk in llm.astream(messages):
        token = ""
        if hasattr(chunk, "content"):
            token = chunk.content or ""
        elif isinstance(chunk, str):
            token = chunk

        if token:
            chunks.append(token)
            if on_token:
                on_token(token)

        # Accumulate token usage from chunk metadata
        meta = getattr(chunk, "usage_metadata", None) or {}
        if isinstance(meta, dict):
            total_input += meta.get("input_tokens", 0)
            total_output += meta.get("output_tokens", 0)

    full_text = "".join(chunks)

    resolved_model = model or get_settings().llm_model
    if total_input or total_output:
        get_active_tracker().add(caller, resolved_model, total_input, total_output)
    logger.info(
        f"[{caller}] streamed {len(chunks)} chunks, "
        f"{len(full_text)} chars, tokens: in={total_input} out={total_output}"
    )

    return full_text


async def astream_sse(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    caller: str = "llm/sse",
) -> AsyncGenerator[str, None]:
    """Yield Server-Sent Events (SSE) for each token chunk.

    Format: `data: {"token": "..."}\n\n` per chunk, `data: [DONE]\n\n` at end.
    Compatible with EventSource / fetch API on the client side.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_llm(model)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    async for chunk in llm.astream(messages):
        token = ""
        if hasattr(chunk, "content"):
            token = chunk.content or ""
        elif isinstance(chunk, str):
            token = chunk

        if token:
            yield f"data: {json.dumps({'token': token})}\n\n"

    yield "data: [DONE]\n\n"
