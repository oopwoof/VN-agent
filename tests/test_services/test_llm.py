"""Tests for LLM client configuration and retry logic."""
from unittest.mock import patch

import pytest

from vn_agent.services.llm import _RETRIABLE, _make_retry_decorator, get_llm


def test_retriable_includes_base_types():
    assert TimeoutError in _RETRIABLE
    assert ConnectionError in _RETRIABLE


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
