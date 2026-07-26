"""v4 P5 M0 unit tests for autopilot preset resolution."""
from __future__ import annotations

import pytest

from vn_agent.autopilot import resolver
from vn_agent.config import Settings


class TestLoadPreset:
    def test_autopilot_best_flattens_llm_section(self):
        flat = resolver.load_preset("autopilot_best")
        assert flat["llm_model"] == "claude-sonnet-4-6"
        assert flat["llm_director_model"] == "claude-sonnet-4-6"
        assert flat["llm_character_designer_model"] == "claude-haiku-4-5-20251001"

    def test_autopilot_best_generation_knobs_are_bare_top_level(self):
        # These fields carry no "generation_" prefix on the Settings model
        # (unlike llm_*/image_*/music_*/playtest_*), so the preset file
        # deliberately keeps them as bare top-level YAML keys rather than
        # nested under a `generation:` section.
        flat = resolver.load_preset("autopilot_best")
        assert flat["max_scenes"] == 10
        assert flat["max_revision_rounds"] == 1
        assert flat["reviewer_skip_llm"] is False

    def test_unknown_preset_raises(self):
        with pytest.raises(FileNotFoundError):
            resolver.load_preset("does_not_exist")


class TestBuildSettings:
    def test_overlay_applies_over_ambient_defaults(self):
        settings = resolver.build_settings("autopilot_best")
        assert isinstance(settings, Settings)
        assert settings.max_scenes == 10
        assert settings.max_revision_rounds == 1
        assert settings.llm_director_model == "claude-sonnet-4-6"

    def test_cross_field_validator_still_runs(self):
        # writer_max_concurrent > 1 requires enable_thinking_fanout +
        # writer_consume_thinking — build_settings must construct via
        # Settings(**merged), not patch an existing instance, so this
        # @model_validator still fires on every override.
        with pytest.raises(ValueError):
            Settings(**{**resolver.load_yaml_settings(), "writer_max_concurrent": 4})


class TestResolvePreset:
    def test_m0_always_returns_autopilot_best(self):
        assert resolver.resolve_preset("a school romance") == "autopilot_best"
        assert resolver.resolve_preset("a noir mystery") == "autopilot_best"
        assert resolver.resolve_preset("") == "autopilot_best"
