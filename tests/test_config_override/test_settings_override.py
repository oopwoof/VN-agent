"""v4 P5 M0 unit tests for the per-job Settings ContextVar override.

get_settings() is called ad-hoc from ~20 agent/graph call sites; Autopilot
needs a per-job preset applied without threading an explicit Settings object
through all of them. These tests pin down the contract that made that safe:
override-when-set, fall through to the cached default otherwise, isolation
across concurrent asyncio tasks, and reset-on-exit.
"""
from __future__ import annotations

import asyncio

import pytest

from vn_agent import config as config_module
from vn_agent.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _reset_override():
    """Belt-and-suspenders: guarantee no test leaves the override set for
    the next one, even if a test body raises before its own reset."""
    yield
    config_module._settings_override.set(None)


class TestGetSettingsOverride:
    def test_default_when_unset(self):
        settings = get_settings()
        assert isinstance(settings, Settings)
        # Ambient config/settings.yaml default, not any preset value.
        assert settings.max_scenes == 20

    def test_override_applies_when_set(self):
        override = Settings(max_scenes=1)
        token = config_module._settings_override.set(override)
        try:
            assert get_settings() is override
            assert get_settings().max_scenes == 1
        finally:
            config_module._settings_override.reset(token)

    def test_reset_restores_default(self):
        token = config_module._settings_override.set(Settings(max_scenes=1))
        config_module._settings_override.reset(token)
        assert get_settings().max_scenes == 20

    def test_cache_clear_attribute_preserved(self):
        # scripts/eval_ollama.py calls get_settings.cache_clear() directly —
        # get_settings is now a plain wrapper, not the lru_cache'd function
        # itself, so this attribute must be explicitly re-attached.
        assert hasattr(get_settings, "cache_clear")
        get_settings.cache_clear()  # must not raise
        assert get_settings().max_scenes == 20


class TestConcurrentIsolation:
    async def test_two_tasks_do_not_see_each_others_override(self):
        results = {}

        async def job_with_override(name: str, max_scenes: int, delay: float):
            token = config_module._settings_override.set(Settings(max_scenes=max_scenes))
            await asyncio.sleep(delay)
            results[name] = get_settings().max_scenes
            config_module._settings_override.reset(token)

        async def job_without_override(name: str, delay: float):
            await asyncio.sleep(delay)
            results[name] = get_settings().max_scenes

        await asyncio.gather(
            asyncio.create_task(job_with_override("a", 7, 0.05)),
            asyncio.create_task(job_without_override("b", 0.02)),
        )

        assert results["a"] == 7
        assert results["b"] == 20  # never saw job "a"'s override

    async def test_override_does_not_leak_after_task_completes(self):
        async def job_with_override():
            token = config_module._settings_override.set(Settings(max_scenes=99))
            config_module._settings_override.reset(token)

        await asyncio.create_task(job_with_override())
        # Caller's own context (this test function) never had the override set.
        assert get_settings().max_scenes == 20
