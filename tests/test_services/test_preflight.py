"""Tests for pre-flight checks (Sprint 6-9a)."""
from __future__ import annotations

import pytest

from vn_agent.services.preflight import (
    PreflightReport,
    check_readiness,
    estimate_cost,
)


class _FakeSettings:
    """Minimal stub exposing just the fields preflight reads."""
    def __init__(self, **overrides):
        self.llm_provider = "anthropic"
        self.anthropic_api_key = ""
        self.openai_api_key = ""
        self.stability_api_key = ""
        self.llm_api_key = ""
        self.llm_director_model = "claude-sonnet-4-6"
        self.llm_writer_model = "claude-sonnet-4-6"
        self.llm_reviewer_model = "claude-haiku-4-5-20251001"
        self.llm_character_designer_model = "claude-haiku-4-5-20251001"
        self.llm_scene_artist_model = "claude-haiku-4-5-20251001"
        self.image_provider = "openai"
        self.image_model = "dall-e-3"
        for k, v in overrides.items():
            setattr(self, k, v)


class TestEstimateCost:
    def test_text_only_has_no_image_cost(self):
        s = _FakeSettings()
        total, breakdown, llm_calls, images = estimate_cost(
            s, max_scenes=5, num_characters=3, text_only=True,
        )
        assert images == 0
        assert "Images" not in breakdown
        assert total > 0  # LLM still costs money
        assert llm_calls == 1 + 1 + 5 + 1  # step1 + step2 + 5 writer + reviewer

    def test_non_text_only_includes_images(self):
        s = _FakeSettings()
        total, breakdown, llm_calls, images = estimate_cost(
            s, max_scenes=5, num_characters=3, text_only=False,
        )
        # 3 chars × 3 emotions + 5 unique backgrounds = 14
        assert images == 14
        assert "Images" in breakdown
        assert breakdown["Images"] > 0

    def test_cost_scales_with_scenes(self):
        s = _FakeSettings()
        t_small, *_ = estimate_cost(s, max_scenes=3, num_characters=2, text_only=True)
        t_big, *_ = estimate_cost(s, max_scenes=10, num_characters=2, text_only=True)
        assert t_big > t_small

    def test_unknown_model_defaults_to_sonnet_pricing(self):
        s = _FakeSettings(llm_director_model="some-unknown-model-v99")
        total, _breakdown, _calls, _images = estimate_cost(
            s, max_scenes=3, num_characters=2, text_only=True,
        )
        # Just make sure it doesn't crash and produces a positive number
        assert total > 0


class TestCheckReadiness:
    @pytest.mark.asyncio
    async def test_fails_when_anthropic_key_missing(self):
        s = _FakeSettings()
        r = await check_readiness(s, 3, 2, text_only=True)
        assert r.passed is False
        assert any("ANTHROPIC_API_KEY" in e for e in r.errors)

    @pytest.mark.asyncio
    async def test_passes_when_anthropic_key_set(self, tmp_path):
        s = _FakeSettings(anthropic_api_key="sk-test")
        r = await check_readiness(s, 3, 2, text_only=True, output_dir=tmp_path)
        assert r.passed is True
        assert r.errors == []

    @pytest.mark.asyncio
    async def test_fails_on_missing_image_key_non_text_only(self):
        s = _FakeSettings(anthropic_api_key="sk-llm")
        # No OPENAI_API_KEY, image_provider default is "openai"
        r = await check_readiness(s, 3, 2, text_only=False)
        assert r.passed is False
        assert any("OPENAI_API_KEY" in e for e in r.errors)

    @pytest.mark.asyncio
    async def test_image_key_not_required_in_text_only(self):
        s = _FakeSettings(anthropic_api_key="sk-llm")
        r = await check_readiness(s, 3, 2, text_only=True)
        # No image provider check when text_only
        assert not any("OPENAI_API_KEY" in e for e in r.errors)

    @pytest.mark.asyncio
    async def test_cost_estimate_included(self):
        s = _FakeSettings(anthropic_api_key="sk-llm")
        r = await check_readiness(s, 5, 3, text_only=True)
        assert r.cost_estimate_usd > 0
        assert r.estimated_llm_calls > 0

    @pytest.mark.asyncio
    async def test_unwritable_output_dir_caught(self, tmp_path, monkeypatch):
        s = _FakeSettings(anthropic_api_key="sk-llm")
        # Use an obviously invalid path on all platforms
        invalid = tmp_path / "file.txt"
        invalid.write_text("this is a file, not a dir")
        bad_dir = invalid / "subdir"  # can't mkdir under a file
        r = await check_readiness(s, 3, 2, text_only=True, output_dir=bad_dir)
        assert r.passed is False
        assert any("Output directory not writable" in e for e in r.errors)

    @pytest.mark.asyncio
    async def test_llm_api_key_overrides_provider_key(self):
        """Explicit llm_api_key should satisfy the LLM check regardless of provider."""
        s = _FakeSettings(llm_api_key="ollama-dummy", llm_provider="openai")
        r = await check_readiness(s, 3, 2, text_only=True)
        assert r.passed is True


class TestReportFormat:
    def test_format_includes_status_line(self):
        r = PreflightReport(passed=True)
        out = r.format()
        assert "READY" in out

    def test_format_lists_errors(self):
        r = PreflightReport(passed=False, errors=["missing X", "bad Y"])
        out = r.format()
        assert "missing X" in out
        assert "bad Y" in out

    def test_format_shows_cost_when_present(self):
        r = PreflightReport(
            passed=True, cost_estimate_usd=0.42,
            cost_breakdown={"LLM": 0.30, "Images": 0.12},
        )
        out = r.format()
        assert "$0.300" in out or "$0.30" in out
        assert "$0.420" in out or "$0.42" in out
