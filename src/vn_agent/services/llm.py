"""LLM client with retry logic and structured output."""
from __future__ import annotations

import logging
from typing import Any, TypeVar
from functools import lru_cache

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pydantic import BaseModel

# langchain_core imports are deferred inside functions to avoid pulling torch at import time

from vn_agent.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _make_retry_decorator(max_retries: int):
    return retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )


@lru_cache(maxsize=1)
def get_llm():
    """Get configured LLM instance (cached)."""
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )


def get_structured_llm(schema: type[T]) -> Any:
    """Get LLM with structured output bound to a Pydantic schema."""
    return get_llm().with_structured_output(schema)


async def ainvoke_llm(
    system_prompt: str,
    user_prompt: str,
    schema: type[T] | None = None,
) -> T | str:
    """Invoke LLM with system+user prompts, optionally with structured output."""
    from langchain_core.messages import HumanMessage, SystemMessage

    settings = get_settings()
    retrier = _make_retry_decorator(settings.llm_max_retries)

    @retrier
    async def _call():
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        if schema is not None:
            llm = get_structured_llm(schema)
        else:
            llm = get_llm()
        result = await llm.ainvoke(messages)
        return result

    return await _call()


def invoke_llm(
    system_prompt: str,
    user_prompt: str,
    schema: type[T] | None = None,
) -> T | str:
    """Synchronous LLM invocation."""
    from langchain_core.messages import HumanMessage, SystemMessage

    settings = get_settings()
    retrier = _make_retry_decorator(settings.llm_max_retries)

    @retrier
    def _call():
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        if schema is not None:
            llm = get_structured_llm(schema)
        else:
            llm = get_llm()
        return llm.invoke(messages)

    return _call()
