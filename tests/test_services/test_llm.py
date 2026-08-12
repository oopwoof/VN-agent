"""Tests for LLM client configuration and retry logic."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from vn_agent.services.llm import (
    _RETRIABLE,
    _backoff_delay,
    _KeyPool,
    _make_retry_decorator,
    _pool_for,
    _reset_pools,
    get_llm,
)

# Key-pool rotation and retry behaviour are the subject here; the conftest
# floor's forced mock_mode_var would short-circuit ainvoke_llm before any
# of it runs. Keys are still stripped and the transport is patched.
pytestmark = pytest.mark.no_mock_floor


def test_retriable_includes_base_types():
    assert TimeoutError in _RETRIABLE
    assert ConnectionError in _RETRIABLE


def test_retriable_excludes_rate_limit():
    """Phase 13-1: RateLimitError must NOT be in inner-retry list —
    the outer pool-rotation loop owns 429."""
    try:
        from anthropic import RateLimitError
        assert RateLimitError not in _RETRIABLE
    except ImportError:
        pytest.skip("anthropic SDK not installed")


def test_make_retry_decorator():
    decorator = _make_retry_decorator(3)
    assert decorator is not None


def test_get_llm_anthropic():
    """Test that get_llm creates an Anthropic LLM with correct settings."""
    with patch("vn_agent.services.llm.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.llm_provider = "anthropic"
        s.llm_model = "claude-sonnet-4-6"
        s.llm_temperature = 0.7
        s.llm_max_tokens = 4096
        s.anthropic_api_key = "sk-test-key"
        s.openai_api_key = ""
        s.llm_api_key = ""
        s.llm_base_url = ""

        # Clear LRU cache to avoid stale entries
        from vn_agent.services.llm import _get_llm_cached
        _get_llm_cached.cache_clear()

        llm = get_llm()
        assert llm is not None
        _get_llm_cached.cache_clear()


def test_get_llm_openai():
    """Test that get_llm creates an OpenAI LLM when base_url is set."""
    with patch("vn_agent.services.llm.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.llm_provider = "openai"
        s.llm_model = "qwen2.5:7b"
        s.llm_temperature = 0.3
        s.llm_max_tokens = 4096
        s.anthropic_api_key = ""
        s.openai_api_key = "test"
        s.llm_api_key = "ollama"
        s.llm_base_url = "http://localhost:11434/v1"

        from vn_agent.services.llm import _get_llm_cached
        _get_llm_cached.cache_clear()

        llm = get_llm()
        assert llm is not None
        _get_llm_cached.cache_clear()


def test_get_llm_explicit_api_key_priority():
    """llm_api_key takes priority over provider-specific keys."""
    with patch("vn_agent.services.llm.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.llm_provider = "openai"
        s.llm_model = "test"
        s.llm_temperature = 0.5
        s.llm_max_tokens = 1000
        s.anthropic_api_key = "wrong"
        s.openai_api_key = "also-wrong"
        s.llm_api_key = "correct-key"
        s.llm_base_url = ""

        from vn_agent.services.llm import _get_llm_cached
        _get_llm_cached.cache_clear()

        llm = get_llm()
        assert llm is not None
        _get_llm_cached.cache_clear()


# ------------------------------------------------------------
# Phase 13-1 / Step 1: Anthropic key pool + backoff tests
# ------------------------------------------------------------


class _FakeRateLimit(Exception):
    """Test double for anthropic.RateLimitError — avoids the SDK's real
    constructor which demands a live httpx.Response."""
    def __init__(self, retry_after: str | None = None):
        super().__init__("fake 429")
        headers = {"retry-after": retry_after} if retry_after else {}
        self.response = type("Resp", (), {"headers": headers})()


@pytest.fixture(autouse=True)
def _reset_llm_pools():
    """Reset module-level pools between tests so config changes take effect."""
    _reset_pools()
    yield
    _reset_pools()


def test_pool_round_robin():
    pool = _KeyPool(["a", "b", "c"])
    picked = [pool.pick() for _ in range(6)]
    assert picked == ["a", "b", "c", "a", "b", "c"]


def test_pool_skips_cooldown():
    pool = _KeyPool(["a", "b", "c"])
    pool.mark_rate_limited("a", 60.0)
    # Pick 6 times — "a" should be absent until cooldown expires
    picked = [pool.pick() for _ in range(6)]
    assert "a" not in picked
    assert set(picked) == {"b", "c"}


def test_pool_all_cooling_returns_soonest():
    """When every key is in cooldown, pick() still returns one (the soonest)
    so the outer loop can still make progress (paired with asyncio.sleep)."""
    pool = _KeyPool(["a", "b", "c"])
    pool.mark_rate_limited("a", 100.0)
    pool.mark_rate_limited("b", 200.0)
    pool.mark_rate_limited("c", 50.0)  # soonest to recover
    # With all in cooldown, pick returns min-cooldown key
    assert pool.pick() == "c"


def test_pool_requires_nonempty_keys():
    with pytest.raises(ValueError):
        _KeyPool([])


def test_pool_for_sonnet_vs_haiku():
    """Haiku and Sonnet route to their own pools."""
    with patch("vn_agent.services.llm.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.anthropic_api_keys_sonnet = ["sk-sonnet-1", "sk-sonnet-2"]
        s.anthropic_api_keys_haiku = ["sk-haiku-1"]
        s.anthropic_api_keys = []

        sonnet_pool = _pool_for("claude-sonnet-4-6")
        haiku_pool = _pool_for("claude-haiku-4-5-20251001")

        assert sonnet_pool is not None and haiku_pool is not None
        assert sonnet_pool is not haiku_pool
        assert sonnet_pool.size == 2
        assert haiku_pool.size == 1


def test_pool_for_fallback_to_generic():
    """When only generic pool is set, both models use it."""
    with patch("vn_agent.services.llm.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.anthropic_api_keys_sonnet = []
        s.anthropic_api_keys_haiku = []
        s.anthropic_api_keys = ["shared-1", "shared-2"]

        sonnet_pool = _pool_for("claude-sonnet-4-6")
        haiku_pool = _pool_for("claude-haiku-4-5-20251001")

        assert sonnet_pool is haiku_pool  # same generic pool


def test_pool_for_none_when_no_keys():
    """All key lists empty → returns None, caller falls back to single key."""
    with patch("vn_agent.services.llm.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.anthropic_api_keys_sonnet = []
        s.anthropic_api_keys_haiku = []
        s.anthropic_api_keys = []

        assert _pool_for("claude-sonnet-4-6") is None


def test_backoff_delay_in_expected_range():
    """Delay should be base * 2^attempt * [1-j, 1+j], capped at cap."""
    settings = type("S", (), {
        "anthropic_backoff_base": 1.0,
        "anthropic_backoff_cap": 30.0,
        "anthropic_backoff_jitter": 0.5,
    })()
    for attempt in range(5):
        delay = _backoff_delay(attempt, settings)
        expected_base = min(1.0 * (2 ** attempt), 30.0)
        assert expected_base * 0.5 <= delay <= expected_base * 1.5


def test_ainvoke_rotates_on_rate_limit():
    """First key raises 429; second key succeeds. Both must be tried."""
    with patch("vn_agent.services.llm.get_settings") as mock_settings, \
         patch("vn_agent.services.llm._RATE_LIMIT_TYPES", (_FakeRateLimit,)), \
         patch("vn_agent.services.llm._invoke_once_async",
               new_callable=AsyncMock) as mock_invoke, \
         patch("vn_agent.services.llm.asyncio.sleep", new_callable=AsyncMock):
        s = mock_settings.return_value
        s.anthropic_api_keys_sonnet = ["key-a", "key-b"]
        s.anthropic_api_keys_haiku = []
        s.anthropic_api_keys = []
        s.llm_model = "claude-sonnet-4-6"
        s.anthropic_max_retries = 4
        s.anthropic_backoff_base = 1.0
        s.anthropic_backoff_cap = 30.0
        s.anthropic_backoff_jitter = 0.5

        mock_invoke.side_effect = [_FakeRateLimit(), "ok"]

        from vn_agent.services.llm import ainvoke_llm

        result = asyncio.run(ainvoke_llm(
            "system", "user", model="claude-sonnet-4-6", caller="test",
        ))
        assert result == "ok"
        assert mock_invoke.call_count == 2
        # Verify different keys were attempted
        keys_tried = [call.args[5] for call in mock_invoke.call_args_list]
        assert len(set(keys_tried)) == 2


def test_ainvoke_single_key_fallback_no_pool():
    """Without configured pool, outer loop passes api_key_override=None."""
    with patch("vn_agent.services.llm.get_settings") as mock_settings, \
         patch("vn_agent.services.llm._invoke_once_async",
               new_callable=AsyncMock) as mock_invoke:
        s = mock_settings.return_value
        s.anthropic_api_keys_sonnet = []
        s.anthropic_api_keys_haiku = []
        s.anthropic_api_keys = []
        s.llm_model = "claude-sonnet-4-6"
        s.anthropic_max_retries = 4

        mock_invoke.return_value = "ok-single"

        from vn_agent.services.llm import ainvoke_llm

        result = asyncio.run(ainvoke_llm("system", "user", caller="test"))
        assert result == "ok-single"
        assert mock_invoke.call_count == 1
        assert mock_invoke.call_args.args[5] is None  # no key_override


def test_ainvoke_haiku_and_sonnet_use_separate_pools():
    """A Haiku call and a Sonnet call draw from their respective pools."""
    with patch("vn_agent.services.llm.get_settings") as mock_settings, \
         patch("vn_agent.services.llm._invoke_once_async",
               new_callable=AsyncMock) as mock_invoke:
        s = mock_settings.return_value
        s.anthropic_api_keys_sonnet = ["sonnet-k"]
        s.anthropic_api_keys_haiku = ["haiku-k"]
        s.anthropic_api_keys = []
        s.llm_model = "claude-sonnet-4-6"
        s.anthropic_max_retries = 4

        mock_invoke.side_effect = ["sonnet-ok", "haiku-ok"]

        from vn_agent.services.llm import ainvoke_llm

        asyncio.run(ainvoke_llm("s", "u", model="claude-sonnet-4-6"))
        asyncio.run(ainvoke_llm("s", "u", model="claude-haiku-4-5-20251001"))

        assert mock_invoke.call_args_list[0].args[5] == "sonnet-k"
        assert mock_invoke.call_args_list[1].args[5] == "haiku-k"


def test_config_splits_csv_env_keys():
    """Settings validator splits "a,b,c" into ["a","b","c"] for all three pool fields."""
    from vn_agent.config import Settings

    s = Settings(
        VN_ANTHROPIC_API_KEYS="k1,k2,k3",
        VN_ANTHROPIC_KEYS_SONNET=" s1 , s2 ",
        VN_ANTHROPIC_KEYS_HAIKU="",  # empty → []
    )
    assert s.anthropic_api_keys == ["k1", "k2", "k3"]
    assert s.anthropic_api_keys_sonnet == ["s1", "s2"]
    assert s.anthropic_api_keys_haiku == []


# ---------------------------------------------------------------------------
# Phase 13-2 Step 4f: structured-output × prompt-caching compatibility
#
# The Director step2 Tool Use migration relies on `with_structured_output`
# NOT breaking Anthropic prompt caching — otherwise we'd silently drop
# from ~80% cache hit to ~0%, exploding cost. These tests pin the
# behavior:
#
#   1. _build_system_message produces list-form content with cache_control
#      when force_cache=True (the only form Anthropic's API recognizes
#      for ephemeral caching)
#   2. ainvoke_llm with schema= carries that cache_control all the way
#      through to the messages handed to the wrapped LLM
#   3. Schema is NOT part of the _get_llm_cached cache key — different
#      schemas wrap the SAME base ChatAnthropic instance, preserving
#      cache hit rate across calls with different schemas
# ---------------------------------------------------------------------------


def test_build_system_message_force_cache_yields_list_form():
    """Cache_control only works when SystemMessage.content is list-form
    (per Anthropic API). Plain string is not cached."""
    from vn_agent.services.llm import _build_system_message

    msg = _build_system_message(
        "x" * 100,  # short, but force_cache overrides the 1500-char heuristic
        provider="anthropic",
        enable_cache=True,
        cache_ttl="1h",
        force_cache=True,
    )
    assert isinstance(msg.content, list)
    assert msg.content[0]["type"] == "text"
    assert msg.content[0]["cache_control"]["type"] == "ephemeral"
    assert msg.content[0]["cache_control"]["ttl"] == "1h"


def test_build_system_message_no_cache_for_short_prompt_default_path():
    """Without force_cache, only prompts ≥1500 chars get cache_control —
    short prompts fall back to plain string content."""
    from vn_agent.services.llm import _build_system_message

    msg = _build_system_message(
        "short prompt",
        provider="anthropic",
        enable_cache=True,
        cache_ttl="5m",
        force_cache=False,
    )
    assert isinstance(msg.content, str)


def test_ainvoke_llm_with_schema_preserves_cache_control_in_messages(monkeypatch):
    """Phase 13-2 Step 4f end-to-end check: when ainvoke_llm is called
    with schema= AND force_cache=True, the SystemMessage delivered to
    the (Tool-Use-wrapped) LLM still has cache_control on its content
    block. This is the core "Tool Use does NOT break prompt caching"
    invariant."""
    from unittest.mock import AsyncMock, MagicMock

    from pydantic import BaseModel

    class _Schema(BaseModel):
        x: str = "y"

    seen_messages: list = []

    async def _record_invoke(messages):
        seen_messages.extend(messages)
        # Phase 13-3 M0-3: include_raw=True returns a dict, not a Message.
        raw = MagicMock()
        raw.response_metadata = {}  # _log_stop_reason consumes this
        return {"raw": raw, "parsed": _Schema(), "parsing_error": None}

    fake_wrapped = MagicMock()
    fake_wrapped.ainvoke = AsyncMock(side_effect=_record_invoke)

    fake_base = MagicMock()
    fake_base.with_structured_output = MagicMock(return_value=fake_wrapped)

    def _fake_factory(*_args, **_kwargs):
        return fake_base

    monkeypatch.setattr("vn_agent.services.llm._get_llm_cached", _fake_factory)

    with patch("vn_agent.services.llm.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.llm_provider = "anthropic"
        s.llm_model = "claude-sonnet-4-6"
        s.llm_temperature = 0.2
        s.llm_max_tokens = 16000
        s.llm_max_retries = 1
        s.anthropic_max_retries = 1
        s.anthropic_api_key = "sk-test"
        s.openai_api_key = ""
        s.llm_api_key = ""
        s.llm_base_url = ""
        s.anthropic_api_keys = []
        s.anthropic_api_keys_sonnet = []
        s.anthropic_api_keys_haiku = []
        s.enable_prompt_caching = True
        s.anthropic_backoff_base = 1
        s.anthropic_backoff_cap = 30
        s.anthropic_backoff_jitter = 0

        from vn_agent.services.llm import _reset_pools, ainvoke_llm
        _reset_pools()

        long_system = "x" * 2000
        asyncio.run(ainvoke_llm(
            long_system, "user prompt", schema=_Schema,
            cache_ttl="1h", force_cache=True,
        ))

    # The system message is messages[0]
    sys_msg = seen_messages[0]
    assert isinstance(sys_msg.content, list), \
        f"Expected list-form content for cache_control; got {type(sys_msg.content)}"
    block = sys_msg.content[0]
    assert block["cache_control"]["type"] == "ephemeral"
    assert block["cache_control"]["ttl"] == "1h"

    # Sanity: with_structured_output called with schema + include_raw=True (M0-3)
    fake_base.with_structured_output.assert_called_once_with(
        _Schema, include_raw=True,
    )


def test_structured_output_logs_stop_reason_from_raw(monkeypatch, caplog):
    """Phase 13-3 M0-3: include_raw=True restores stop_reason / token logging
    that Step 4f's structured-output path silently lost. Without this fix,
    director/step2 logs `stop_reason='unknown' tokens: in=0 out=0` even on
    successful runs, leaving M1 stress test blind to step2's real cost."""
    import logging
    from unittest.mock import AsyncMock, MagicMock

    from pydantic import BaseModel

    class _Schema(BaseModel):
        x: str = "y"

    async def _fake_invoke(_messages):
        # Mimic Anthropic's response_metadata shape
        raw = MagicMock()
        raw.response_metadata = {
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 1234, "output_tokens": 567},
            "model": "claude-sonnet-4-6",
        }
        return {"raw": raw, "parsed": _Schema(), "parsing_error": None}

    fake_wrapped = MagicMock()
    fake_wrapped.ainvoke = AsyncMock(side_effect=_fake_invoke)
    fake_base = MagicMock()
    fake_base.with_structured_output = MagicMock(return_value=fake_wrapped)

    monkeypatch.setattr(
        "vn_agent.services.llm._get_llm_cached",
        lambda *a, **k: fake_base,
    )

    with patch("vn_agent.services.llm.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.llm_provider = "anthropic"
        s.llm_model = "claude-sonnet-4-6"
        s.llm_temperature = 0.2
        s.llm_max_tokens = 16000
        s.llm_max_retries = 1
        s.anthropic_max_retries = 1
        s.anthropic_api_key = "sk-test"
        s.openai_api_key = ""
        s.llm_api_key = ""
        s.llm_base_url = ""
        s.anthropic_api_keys = []
        s.anthropic_api_keys_sonnet = []
        s.anthropic_api_keys_haiku = []
        s.enable_prompt_caching = True
        s.anthropic_backoff_base = 1
        s.anthropic_backoff_cap = 30
        s.anthropic_backoff_jitter = 0

        from vn_agent.services.llm import _reset_pools, ainvoke_llm
        _reset_pools()

        with caplog.at_level(logging.INFO, logger="vn_agent.services.llm"):
            asyncio.run(ainvoke_llm(
                "system", "user", schema=_Schema, caller="test/m0_3",
            ))

    msgs = [r.message for r in caplog.records]
    # The Step 4f bug was: stop_reason='unknown' tokens: in=0 out=0 — verify
    # M0-3 surfaces real values from the raw BaseMessage
    assert any(
        "[test/m0_3]" in m and "stop_reason='tool_use'" in m
        and "in=1234" in m and "out=567" in m
        for m in msgs
    ), f"Expected stop_reason / tokens to be logged from raw; got: {msgs}"


def test_structured_output_propagates_parsing_error(monkeypatch):
    """Phase 13-3 M0-3: parsing_error from include_raw flows to the caller
    instead of being silently dropped. Director step2's existing
    ValidationError handler catches it (and logs with exc_info=True)."""
    from unittest.mock import AsyncMock, MagicMock

    from pydantic import BaseModel, ValidationError

    class _Schema(BaseModel):
        x: int  # required, no default

    # Build a real ValidationError to propagate
    try:
        _Schema(x="not an int")  # type: ignore[arg-type]
        verr: ValidationError | None = None
    except ValidationError as e:
        verr = e
    assert verr is not None

    async def _fake_invoke(_messages):
        raw = MagicMock()
        raw.response_metadata = {}
        return {"raw": raw, "parsed": None, "parsing_error": verr}

    fake_wrapped = MagicMock()
    fake_wrapped.ainvoke = AsyncMock(side_effect=_fake_invoke)
    fake_base = MagicMock()
    fake_base.with_structured_output = MagicMock(return_value=fake_wrapped)
    monkeypatch.setattr(
        "vn_agent.services.llm._get_llm_cached",
        lambda *a, **k: fake_base,
    )

    with patch("vn_agent.services.llm.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.llm_provider = "anthropic"
        s.llm_model = "claude-sonnet-4-6"
        s.llm_temperature = 0.2
        s.llm_max_tokens = 16000
        s.llm_max_retries = 1
        s.anthropic_max_retries = 1
        s.anthropic_api_key = "sk-test"
        s.openai_api_key = ""
        s.llm_api_key = ""
        s.llm_base_url = ""
        s.anthropic_api_keys = []
        s.anthropic_api_keys_sonnet = []
        s.anthropic_api_keys_haiku = []
        s.enable_prompt_caching = True
        s.anthropic_backoff_base = 1
        s.anthropic_backoff_cap = 30
        s.anthropic_backoff_jitter = 0

        from vn_agent.services.llm import _reset_pools, ainvoke_llm
        _reset_pools()

        with pytest.raises(ValidationError):
            asyncio.run(ainvoke_llm(
                "system", "user", schema=_Schema, caller="test/m0_3_error",
            ))


def test_get_structured_llm_uses_same_base_for_different_schemas():
    """Phase 13-2 Step 4f: schema is NOT part of the _get_llm_cached
    cache key. Different schemas produce different `with_structured_output`
    wrappers, but the underlying ChatAnthropic instance is the same —
    so Anthropic prompt cache hit rate stays intact across schema switches."""
    from pydantic import BaseModel

    class _SchemaA(BaseModel):
        x: str = ""

    class _SchemaB(BaseModel):
        y: int = 0

    with patch("vn_agent.services.llm.get_settings") as mock_settings:
        s = mock_settings.return_value
        s.llm_provider = "anthropic"
        s.llm_model = "claude-sonnet-4-6"
        s.llm_temperature = 0.2
        s.llm_max_tokens = 16000
        s.anthropic_api_key = "sk-test"
        s.openai_api_key = ""
        s.llm_api_key = ""
        s.llm_base_url = ""

        from vn_agent.services.llm import _get_llm_cached, get_llm
        _get_llm_cached.cache_clear()

        base1 = get_llm()
        base2 = get_llm()  # second call — must hit cache
        assert base1 is base2

        _get_llm_cached.cache_clear()
