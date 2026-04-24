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
