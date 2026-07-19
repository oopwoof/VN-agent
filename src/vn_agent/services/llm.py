"""LLM client with retry logic and structured output.

Phase 13-1 / Step 1: Anthropic key pool added on top of the tenacity inner
retry. Outer loop handles RateLimitError + key rotation + exp backoff;
inner tenacity still handles connection errors and 5xx. RateLimitError is
intentionally EXCLUDED from the inner retry list so the outer loop owns it.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from contextvars import ContextVar
from functools import lru_cache
from itertools import cycle
from pathlib import Path
from threading import Lock
from typing import Any, TypeVar

from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# langchain_core imports are deferred inside functions to avoid pulling torch at import time
from vn_agent.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# v4 P0-7: per-request mock gate. Set to True from the web layer's job
# runner (or a test's contextmanager) to route ainvoke_llm to
# `mock_ainvoke` for THAT run only. Async-safe + isolated per job via
# ContextVar — same pattern as TokenTracker (`current_tracker`). Default
# False keeps the CLI/real-API path unchanged when nobody sets it.
mock_mode_var: ContextVar[bool] = ContextVar("vn_agent_mock_mode", default=False)


def _use_mock_llm() -> bool:
    """Read the per-request mock flag. Cheap; kept as a helper so callers
    other than ainvoke_llm can consult it (e.g., streaming variants)."""
    try:
        return bool(mock_mode_var.get())
    except LookupError:
        return False


# Inner-retry list (tenacity): connection errors, timeouts, 5xx. Does NOT
# include RateLimitError — the outer pool-rotation loop handles 429.
_RETRIABLE_LIST: list[type[Exception]] = [TimeoutError, ConnectionError]
_RATE_LIMIT_LIST: list[type[Exception]] = []
try:
    from anthropic import APIConnectionError, InternalServerError, RateLimitError
    _RETRIABLE_LIST.extend([APIConnectionError, InternalServerError])
    _RATE_LIMIT_LIST.append(RateLimitError)
except ImportError:
    pass
try:
    from openai import APIConnectionError as OC
    from openai import RateLimitError as OR
    _RETRIABLE_LIST.append(OC)
    _RATE_LIMIT_LIST.append(OR)
except ImportError:
    pass
_RETRIABLE = tuple(_RETRIABLE_LIST)


class _NeverRaised(Exception):
    """Sentinel for the empty rate-limit tuple case (SDKs missing).
    Using an empty tuple in `except` is illegal; this never-raised class
    makes `except _RATE_LIMIT_TYPES` a no-op when no SDK is available.
    """


_RATE_LIMIT_TYPES: tuple[type[Exception], ...] = (
    tuple(_RATE_LIMIT_LIST) if _RATE_LIMIT_LIST else (_NeverRaised,)
)


def _make_retry_decorator(max_retries: int):
    return retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(_RETRIABLE),
        reraise=True,
    )


# ----------------------------------------------------------------------------
# Phase 13-1 / Step 1: Anthropic key pool + exp backoff + cooldown
# ----------------------------------------------------------------------------


class _KeyPool:
    """Round-robin key pool with per-key cooldown after rate-limit hits.

    pick() skips keys currently in cooldown; if all are cooling, returns
    the one with earliest cooldown expiration so the loop still makes
    progress (waking up shortly after the earliest key becomes eligible).
    """

    def __init__(self, keys: list[str]):
        if not keys:
            raise ValueError("_KeyPool requires at least one key")
        self._keys = list(keys)
        self._cycle_iter = cycle(self._keys)
        self._lock = Lock()
        self._cooldown: dict[str, float] = {}  # key → available_at (monotonic)

    def pick(self) -> str:
        with self._lock:
            now = time.monotonic()
            for _ in range(len(self._keys)):
                k = next(self._cycle_iter)
                if self._cooldown.get(k, 0.0) <= now:
                    return k
            # All keys currently in cooldown — return the soonest-eligible.
            return min(self._keys, key=lambda k: self._cooldown.get(k, 0.0))

    def mark_rate_limited(self, key: str, cooldown_s: float) -> None:
        with self._lock:
            self._cooldown[key] = time.monotonic() + cooldown_s

    @property
    def size(self) -> int:
        return len(self._keys)


_pool_sonnet: _KeyPool | None = None
_pool_haiku: _KeyPool | None = None
_pool_generic: _KeyPool | None = None
_pool_init_lock = Lock()


def _reset_pools() -> None:
    """Test helper: reset module-level pools so config changes take effect."""
    global _pool_sonnet, _pool_haiku, _pool_generic
    with _pool_init_lock:
        _pool_sonnet = None
        _pool_haiku = None
        _pool_generic = None


def _pool_for(model: str) -> _KeyPool | None:
    """Pick the pool matching the model's tier. Returns None when no pool
    is configured (all key lists empty) — caller falls back to the single
    anthropic_api_key path (backward compat).

    Routing rules:
      - "haiku" in model name → haiku pool if set, else generic, else None
      - otherwise             → sonnet pool if set, else generic, else None
    """
    global _pool_sonnet, _pool_haiku, _pool_generic
    settings = get_settings()
    is_haiku = "haiku" in (model or "").lower()

    with _pool_init_lock:
        if is_haiku:
            if _pool_haiku is None and settings.anthropic_api_keys_haiku:
                _pool_haiku = _KeyPool(settings.anthropic_api_keys_haiku)
            if _pool_haiku is not None:
                return _pool_haiku
        else:
            if _pool_sonnet is None and settings.anthropic_api_keys_sonnet:
                _pool_sonnet = _KeyPool(settings.anthropic_api_keys_sonnet)
            if _pool_sonnet is not None:
                return _pool_sonnet
        if _pool_generic is None and settings.anthropic_api_keys:
            _pool_generic = _KeyPool(settings.anthropic_api_keys)
        return _pool_generic


def _extract_retry_after(exc: Exception) -> float | None:
    """Extract Retry-After header from an Anthropic/OpenAI RateLimitError."""
    try:
        resp = getattr(exc, "response", None)
        if resp is None:
            return None
        headers = getattr(resp, "headers", None) or {}
        v = headers.get("retry-after") or headers.get("Retry-After")
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError, AttributeError):
        return None


def _backoff_delay(attempt: int, settings: Any) -> float:
    """Exponential backoff with multiplicative jitter."""
    base = settings.anthropic_backoff_base * (2 ** attempt)
    capped = min(base, settings.anthropic_backoff_cap)
    jitter_low = 1.0 - settings.anthropic_backoff_jitter
    jitter_high = 1.0 + settings.anthropic_backoff_jitter
    return capped * random.uniform(jitter_low, jitter_high)


def _log_key_rotation(
    caller: str,
    attempt: int,
    key: str | None,
    reason: str,
    delay_s: float,
    model: str,
) -> None:
    """Log a rotation event. Always emits to logger; best-effort file write
    to ./api_key_rotations.jsonl in the active output dir if discoverable.
    """
    key_suffix = (key or "")[-4:] if key else ""
    logger.warning(
        f"[key-pool] rotate: caller={caller} attempt={attempt} "
        f"key_suffix={key_suffix} reason={reason} delay={delay_s:.2f}s model={model}"
    )
    # Best-effort JSONL audit trail in the current working directory.
    # Full output-dir wiring would require a context variable; defer to
    # existing rag_retrievals pattern if/when needed.
    try:
        import json
        from datetime import UTC, datetime

        path = Path.cwd() / "api_key_rotations.jsonl"
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "caller": caller,
            "attempt": attempt,
            "key_suffix": key_suffix,
            "reason": reason,
            "delay_s": round(delay_s, 2),
            "model": model,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001 — observability is best-effort
        logger.debug(f"Failed to persist key rotation event: {e}")



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


def _infer_provider_from_model(model: str) -> str | None:
    """Infer the API provider from a model name when the caller hasn't
    explicitly set one. Lets Sprint 8-1 cross-model judging pass
    model='gpt-4o' and have it routed to OpenAI even though the pipeline
    default is Anthropic.
    """
    lower = model.lower()
    if lower.startswith("claude"):
        return "anthropic"
    if lower.startswith("gpt") or lower.startswith("o1") or lower.startswith("o3"):
        return "openai"
    if lower.startswith("gemini"):
        return "google_gemini"  # future: add gemini langchain provider
    return None


def get_llm(
    model: str | None = None,
    *,
    api_key_override: str | None = None,
    max_tokens_override: int | None = None,
):
    """Get configured LLM instance (cached per model + api_key + max_tokens).

    Sprint 8-1 fix: when `model` is an OpenAI name (gpt-*, o1-*) but the
    pipeline provider is Anthropic (or vice versa), override the provider
    based on the model name. Prevents the Sonnet reviewer's cross-model
    judge calls to gpt-4o from being routed to Anthropic (which returns
    a 404 for unknown model names).

    Phase 13-1 / Step 1: api_key_override routes the request through a
    specific key (from `_KeyPool.pick()`). Different keys yield different
    `_get_llm_cached` cache entries, so key rotation naturally creates a
    fresh ChatAnthropic instance per key.

    Phase 13-3 M0-1: max_tokens_override lets callers (e.g. Writer) pin a
    per-call output budget. _get_llm_cached's lru_cache is keyed on
    max_tokens, so distinct callers using distinct caps still each get a
    cached instance (no perf regression).
    """
    settings = get_settings()
    resolved_model = model or settings.llm_model

    # Determine effective provider. Explicit base_url always wins (custom
    # OpenAI-compatible endpoints like Ollama). Otherwise, if the model
    # name clearly belongs to a different provider than the pipeline
    # default, swap.
    effective_provider = settings.llm_provider
    if not settings.llm_base_url:
        inferred = _infer_provider_from_model(resolved_model)
        if inferred and inferred != effective_provider and inferred in {"anthropic", "openai"}:
            effective_provider = inferred

    # Key resolution priority: pool override > explicit llm_api_key > env per provider
    if api_key_override:
        api_key = api_key_override
    elif settings.llm_api_key:
        api_key = settings.llm_api_key
    elif effective_provider == "anthropic":
        api_key = settings.anthropic_api_key
    else:
        api_key = settings.openai_api_key

    resolved_max_tokens = (
        max_tokens_override if max_tokens_override is not None
        else settings.llm_max_tokens
    )

    return _get_llm_cached(
        effective_provider,
        resolved_model,
        settings.llm_temperature,
        resolved_max_tokens,
        api_key,
        settings.llm_base_url,
    )


def get_structured_llm(
    schema: type[T],
    model: str | None = None,
    *,
    api_key_override: str | None = None,
    max_tokens_override: int | None = None,
) -> Any:
    """Get LLM with structured output bound to a Pydantic schema.

    Phase 13-3 M0-3: uses `include_raw=True` so we get back
    `{"raw": BaseMessage, "parsed": SchemaInstance, "parsing_error": ...}`.
    The raw BaseMessage carries `response_metadata` (stop_reason, usage)
    that token tracking + max_tokens warnings depend on. Without this,
    Step 4f's structured-output path silently lost stop_reason / token
    counts (langchain's Pydantic-only return path strips metadata).
    """
    return get_llm(
        model,
        api_key_override=api_key_override,
        max_tokens_override=max_tokens_override,
    ).with_structured_output(schema, include_raw=True)


def _log_stop_reason(result: Any, caller: str) -> None:
    """Log stop_reason and token usage from response metadata."""
    from vn_agent.services.token_tracker import get_active_tracker

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
        get_active_tracker().add(caller, model, input_tokens, output_tokens)

    if stop_reason == "max_tokens":
        settings = get_settings()
        logger.warning(
            f"[{caller}] Response hit max_tokens limit ({settings.llm_max_tokens}). "
            "Consider increasing llm.max_tokens in config/settings.yaml."
        )


def _build_system_message(
    system_prompt: str,
    provider: str,
    enable_cache: bool,
    *,
    cache_ttl: str = "5m",
    force_cache: bool = False,
):
    """Sprint 8-4 + Phase 13-1 Step 3: wrap SystemMessage for Anthropic caching.

    Anthropic's ephemeral cache cuts cached-read input cost to ~10% of
    base. TTL options: "5m" (default, Sprint 8-4) or "1h" (Step 3, for
    long-form runs where gaps between Writer calls exceed 5 min due to
    image/BGM generation).

    Activated when:
      - provider is anthropic, AND
      - enable_cache is True, AND
      - either force_cache=True (caller guarantees prefix meets threshold —
        see prompts/cached_prefix.build_monolithic_prefix) OR the legacy
        len≥1500-char heuristic passes.

    Short prompts or non-Anthropic providers fall back to plain string
    content so no provider-specific feature leaks.
    """
    from langchain_core.messages import SystemMessage

    should_cache = (
        enable_cache
        and provider == "anthropic"
        and system_prompt
        and (force_cache or len(system_prompt) >= 1500)
    )
    if should_cache:
        cache_block: dict = {"type": "ephemeral"}
        if cache_ttl and cache_ttl != "5m":
            cache_block["ttl"] = cache_ttl
        return SystemMessage(
            content=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": cache_block,
                }
            ]
        )
    return SystemMessage(content=system_prompt)


async def _invoke_once_async(
    system_prompt: str,
    user_prompt: str,
    schema: type[T] | None,
    model: str | None,
    caller: str,
    api_key_override: str | None,
    cache_ttl: str = "5m",
    force_cache: bool = False,
    max_tokens_override: int | None = None,
) -> T | str:
    """Single invocation attempt with inner tenacity retry (conn errors / 5xx).
    RateLimitError is NOT caught here — the outer pool-rotation loop owns it.
    """
    from langchain_core.messages import HumanMessage

    settings = get_settings()
    retrier = _make_retry_decorator(settings.llm_max_retries)
    enable_cache = getattr(settings, "enable_prompt_caching", True)

    @retrier
    async def _call():
        sys_msg = _build_system_message(
            system_prompt, settings.llm_provider, enable_cache,
            cache_ttl=cache_ttl, force_cache=force_cache,
        )
        messages = [sys_msg, HumanMessage(content=user_prompt)]
        if schema is not None:
            llm = get_structured_llm(
                schema, model,
                api_key_override=api_key_override,
                max_tokens_override=max_tokens_override,
            )
            # Phase 13-3 M0-3: include_raw=True returns
            # {"raw": BaseMessage, "parsed": Schema, "parsing_error": Exception | None}.
            # Use raw for stop_reason/token logging, propagate parsing_error,
            # return parsed so callers see a Pydantic instance just like before.
            result = await llm.ainvoke(messages)
            _log_stop_reason(result.get("raw"), caller)
            err = result.get("parsing_error")
            if err is not None:
                raise err
            return result.get("parsed")
        else:
            llm = get_llm(
                model,
                api_key_override=api_key_override,
                max_tokens_override=max_tokens_override,
            )
            result = await llm.ainvoke(messages)
            _log_stop_reason(result, caller)
            return result

    return await _call()


def _invoke_once_sync(
    system_prompt: str,
    user_prompt: str,
    schema: type[T] | None,
    model: str | None,
    caller: str,
    api_key_override: str | None,
    cache_ttl: str = "5m",
    force_cache: bool = False,
    max_tokens_override: int | None = None,
) -> T | str:
    """Sync counterpart to _invoke_once_async."""
    from langchain_core.messages import HumanMessage

    settings = get_settings()
    retrier = _make_retry_decorator(settings.llm_max_retries)
    enable_cache = getattr(settings, "enable_prompt_caching", True)

    @retrier
    def _call():
        sys_msg = _build_system_message(
            system_prompt, settings.llm_provider, enable_cache,
            cache_ttl=cache_ttl, force_cache=force_cache,
        )
        messages = [sys_msg, HumanMessage(content=user_prompt)]
        if schema is not None:
            llm = get_structured_llm(
                schema, model,
                api_key_override=api_key_override,
                max_tokens_override=max_tokens_override,
            )
            # Phase 13-3 M0-3: include_raw=True returns
            # {"raw": BaseMessage, "parsed": Schema, "parsing_error": Exception | None}.
            result = llm.invoke(messages)
            _log_stop_reason(result.get("raw"), caller)
            err = result.get("parsing_error")
            if err is not None:
                raise err
            return result.get("parsed")
        else:
            llm = get_llm(
                model,
                api_key_override=api_key_override,
                max_tokens_override=max_tokens_override,
            )
            result = llm.invoke(messages)
            _log_stop_reason(result, caller)
            return result

    return _call()


async def ainvoke_llm(
    system_prompt: str,
    user_prompt: str,
    schema: type[T] | None = None,
    model: str | None = None,
    caller: str = "llm",
    *,
    cache_ttl: str = "5m",
    force_cache: bool = False,
    max_tokens: int | None = None,
) -> T | str:
    """Invoke LLM with system+user prompts, optionally with structured output.

    Sprint 8-4: system prompts ≥1500 chars are auto-tagged for Anthropic
    prompt caching (5-min ephemeral).

    Phase 13-1 / Step 1: when a key pool is configured (any of the
    anthropic_api_keys_* settings set), each attempt picks a fresh key;
    RateLimitError triggers exp backoff + key rotation.

    Phase 13-1 / Step 3: callers supplying a monolithic prefix (see
    prompts/cached_prefix.build_monolithic_prefix) pass force_cache=True
    and cache_ttl="1h" to enable the 1-hour cache tier with the caller's
    own threshold decision (not the legacy 1500-char heuristic).

    Phase 13-3 M0-1: callers can pass `max_tokens` to pin a per-call
    output cap, overriding settings.llm_max_tokens. Used by Writer to
    bound per-scene cost (writer_max_tokens_per_scene).

    v4 P0-7: if `mock_mode_var` ContextVar is True (set by the web layer
    when GenerateRequest.mock=True), short-circuit into `mock_ainvoke`
    without touching real LLM keys / quotas. Per-job scoped so concurrent
    real+mock jobs don't cross-contaminate.
    """
    if _use_mock_llm():
        from vn_agent.services.mock_llm import mock_ainvoke
        return await mock_ainvoke(
            system_prompt, user_prompt,
            schema=schema, model=model, caller=caller,
            cache_ttl=cache_ttl, force_cache=force_cache,
            max_tokens=max_tokens,
        )

    settings = get_settings()
    resolved_model = model or settings.llm_model
    pool = _pool_for(resolved_model)
    n_keys = pool.size if pool else 1
    max_attempts = max(settings.anthropic_max_retries, n_keys)

    last_err: Exception | None = None
    for attempt in range(max_attempts):
        key_override = pool.pick() if pool else None
        try:
            return await _invoke_once_async(
                system_prompt, user_prompt, schema, resolved_model,
                caller, key_override, cache_ttl, force_cache,
                max_tokens_override=max_tokens,
            )
        except _RATE_LIMIT_TYPES as e:
            last_err = e
            cooldown = _extract_retry_after(e) or 30.0
            if pool and key_override:
                pool.mark_rate_limited(key_override, cooldown)
            delay = _backoff_delay(attempt, settings)
            _log_key_rotation(
                caller, attempt, key_override, "429", delay, resolved_model,
            )
            if attempt + 1 < max_attempts:
                await asyncio.sleep(delay)
            continue
    assert last_err is not None
    raise last_err


def invoke_llm(
    system_prompt: str,
    user_prompt: str,
    schema: type[T] | None = None,
    model: str | None = None,
    caller: str = "llm",
    *,
    cache_ttl: str = "5m",
    force_cache: bool = False,
    max_tokens: int | None = None,
) -> T | str:
    """Synchronous LLM invocation. Same pool + backoff + cache semantics as async."""
    settings = get_settings()
    resolved_model = model or settings.llm_model
    pool = _pool_for(resolved_model)
    n_keys = pool.size if pool else 1
    max_attempts = max(settings.anthropic_max_retries, n_keys)

    last_err: Exception | None = None
    for attempt in range(max_attempts):
        key_override = pool.pick() if pool else None
        try:
            return _invoke_once_sync(
                system_prompt, user_prompt, schema, resolved_model,
                caller, key_override, cache_ttl, force_cache,
                max_tokens_override=max_tokens,
            )
        except _RATE_LIMIT_TYPES as e:
            last_err = e
            cooldown = _extract_retry_after(e) or 30.0
            if pool and key_override:
                pool.mark_rate_limited(key_override, cooldown)
            delay = _backoff_delay(attempt, settings)
            _log_key_rotation(
                caller, attempt, key_override, "429", delay, resolved_model,
            )
            if attempt + 1 < max_attempts:
                time.sleep(delay)
            continue
    assert last_err is not None
    raise last_err
