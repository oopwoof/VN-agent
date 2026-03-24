"""LLM client with retry logic and structured output."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# langchain_core imports are deferred inside functions to avoid pulling torch at import time
from vn_agent.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


_RETRIABLE_LIST: list[type[Exception]] = [TimeoutError, ConnectionError]
try:
    from anthropic import APIConnectionError, InternalServerError, RateLimitError
    _RETRIABLE_LIST.extend([APIConnectionError, RateLimitError, InternalServerError])
except ImportError:
    pass
try:
    from openai import APIConnectionError as OC
    from openai import RateLimitError as OR
    _RETRIABLE_LIST.extend([OC, OR])
except ImportError:
    pass
_RETRIABLE = tuple(_RETRIABLE_LIST)


def _make_retry_decorator(max_retries: int):
    return retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(_RETRIABLE),
        reraise=True,
    )


@lru_cache(maxsize=8)
def _get_llm_cached(
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    api_key: str,
    base_url: str,
):
    """Create and cache an LLM instance keyed by its full configuration."""
    logger.debug(
        f"Creating LLM: provider={provider} model={model} "
        f"max_tokens={max_tokens}"
        + (f" base_url={base_url}" if base_url else "")
    )
    if provider == "anthropic" and not base_url:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,  # type: ignore[call-arg]
            api_key=api_key,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,  # type: ignore[call-arg]
        )
    else:
        # "openai" provider, OR any provider with a custom base_url
        # (Ollama / LM Studio / Groq / OpenRouter all speak OpenAI protocol)
        from langchain_openai import ChatOpenAI
        kwargs: dict = dict(
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenAI(**kwargs)


def get_llm(model: str | None = None):
    """Get configured LLM instance (cached per model)."""
    settings = get_settings()
    resolved_model = model or settings.llm_model

    # Explicit api_key override takes priority; then provider-specific env key
    if settings.llm_api_key:
        api_key = settings.llm_api_key
    elif settings.llm_provider == "anthropic":
        api_key = settings.anthropic_api_key
    else:
        api_key = settings.openai_api_key

    return _get_llm_cached(
        settings.llm_provider,
        resolved_model,
        settings.llm_temperature,
        settings.llm_max_tokens,
        api_key,
        settings.llm_base_url,
    )


def get_structured_llm(schema: type[T], model: str | None = None) -> Any:
    """Get LLM with structured output bound to a Pydantic schema."""
    return get_llm(model).with_structured_output(schema)


def _log_stop_reason(result: Any, caller: str) -> None:
    """Log stop_reason and token usage from response metadata."""
    from vn_agent.services.token_tracker import tracker

    meta = getattr(result, "response_metadata", None) or {}
    stop_reason = meta.get("stop_reason") or meta.get("finish_reason", "unknown")
    usage = meta.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    model = meta.get("model_id") or meta.get("model", "unknown")
    logger.info(
        f"[{caller}] stop_reason={stop_reason!r}  "
        f"tokens: in={input_tokens} out={output_tokens}"
    )

    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        tracker.add(caller, model, input_tokens, output_tokens)

    if stop_reason == "max_tokens":
        settings = get_settings()
        logger.warning(
            f"[{caller}] Response hit max_tokens limit ({settings.llm_max_tokens}). "
            "Consider increasing llm.max_tokens in config/settings.yaml."
        )


async def ainvoke_llm(
    system_prompt: str,
    user_prompt: str,
    schema: type[T] | None = None,
    model: str | None = None,
    caller: str = "llm",
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
            llm = get_structured_llm(schema, model)
        else:
            llm = get_llm(model)
        result = await llm.ainvoke(messages)
        _log_stop_reason(result, caller)
        return result

    return await _call()


def invoke_llm(
    system_prompt: str,
    user_prompt: str,
    schema: type[T] | None = None,
    model: str | None = None,
    caller: str = "llm",
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
            llm = get_structured_llm(schema, model)
        else:
            llm = get_llm(model)
        result = llm.invoke(messages)
        _log_stop_reason(result, caller)
        return result

    return _call()
