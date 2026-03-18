"""Tests for CLI commands: dry-run, validate, compile."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vn_agent.cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Shared fixture data (mirrors the 3-scene script from the integration test)
# ---------------------------------------------------------------------------

VALID_SCRIPT = {
    "title": "Echoes of Tomorrow",
    "description": "A short story about choices",
    "theme": "A school romance about choices",
    "start_scene_id": "ch1_morning",
    "scenes": [
        {
            "id": "ch1_morning",
            "title": "Morning Arrival",
            "description": "The protagonist arrives at school",
            "background_id": "bg_school",
            "music_mood": "peaceful",
            "music_description": "soft piano",
            "characters_present": ["char_hana"],
            "next_scene_id": None,
            "branches": [
                {"text": "Say hello", "next_scene_id": "ch1_friendly"},
                {"text": "Walk past", "next_scene_id": "ch1_distant"},
            ],
            "narrative_strategy": "accumulate",
        },
        {
            "id": "ch1_friendly",
            "title": "A Warm Greeting",
            "description": "They exchange warm words",
            "background_id": "bg_school",
            "music_mood": "romantic",
            "music_description": "warm strings",
            "characters_present": ["char_hana"],
            "next_scene_id": None,
            "branches": [],
            "narrative_strategy": "accumulate",
        },
        {
            "id": "ch1_distant",
            "title": "Silent Pass",
            "description": "They walk by in silence",
            "background_id": "bg_corridor",
            "music_mood": "melancholic",
            "music_description": "quiet piano",
            "characters_present": ["char_hana"],
            "next_scene_id": None,
            "branches": [],
            "narrative_strategy": "erode",
        },
    ],
    "characters": ["char_hana"],
    "revision_count": 0,
    "revision_notes": [],
}

VALID_CHARACTERS = {
    "char_hana": {
        "id": "char_hana",
        "name": "Hana",
        "color": "#ff88aa",
        "personality": "Cheerful and warm",
        "background": "The protagonist's childhood friend",
        "role": "love interest",
        "visual": None,
    }
}

INVALID_SCRIPT = {
    "title": "Bad Script",
    # missing required fields: description, theme, start_scene_id, scenes
}


# ---------------------------------------------------------------------------
# dry-run tests
# ---------------------------------------------------------------------------


def test_dry_run_shows_summary():
    result = runner.invoke(app, ["dry-run", "A romantic story about a pianist"])
    assert result.exit_code == 0
    output_lower = result.output.lower()
    assert "theme" in output_lower
    assert "pianist" in output_lower or "romantic" in output_lower


def test_dry_run_shows_provider_and_model():
    result = runner.invoke(app, ["dry-run", "Space opera adventure"])
    assert result.exit_code == 0
    # Should contain provider/model info
    assert "anthropic" in result.output.lower() or "openai" in result.output.lower()


def test_dry_run_text_only_flag():
    result = runner.invoke(app, ["dry-run", "A mystery story", "--text-only"])
    assert result.exit_code == 0
    assert "text" in result.output.lower() or "yes" in result.output.lower()


def test_dry_run_custom_max_scenes():
    result = runner.invoke(app, ["dry-run", "A fantasy epic", "--max-scenes", "5"])
    assert result.exit_code == 0
    assert "5" in result.output


def test_dry_run_does_not_invoke_agents(monkeypatch):
    """dry-run must not call any LLM or agent code."""
    called = []

    def fake_create_pipeline():
        called.append("pipeline")
        raise RuntimeError("Should not be called in dry-run")

    monkeypatch.setattr("vn_agent.agents.graph.create_pipeline", fake_create_pipeline, raising=False)

    result = runner.invoke(app, ["dry-run", "Fantasy adventure"])
    assert result.exit_code == 0
    assert "pipeline" not in called


# ---------------------------------------------------------------------------
# validate tests
# ---------------------------------------------------------------------------


def test_validate_valid_script(tmp_path: Path):
    script_file = tmp_path / "vn_script.json"
    script_file.write_text(json.dumps(VALID_SCRIPT), encoding="utf-8")

    result = runner.invoke(app, ["validate", str(script_file)])
    assert result.exit_code == 0
    assert "valid" in result.output.lower() or "✓" in result.output


def test_validate_invalid_script(tmp_path: Path):
    script_file = tmp_path / "bad_script.json"
    script_file.write_text(json.dumps(INVALID_SCRIPT), encoding="utf-8")

    result = runner.invoke(app, ["validate", str(script_file)])
    assert result.exit_code != 0


def test_validate_missing_file(tmp_path: Path):
    nonexistent = tmp_path / "nonexistent.json"
    result = runner.invoke(app, ["validate", str(nonexistent)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# compile tests
# ---------------------------------------------------------------------------


def test_compile_command(tmp_path: Path):
    script_file = tmp_path / "vn_script.json"
    script_file.write_text(json.dumps(VALID_SCRIPT), encoding="utf-8")

    output_dir = tmp_path / "out"

    result = runner.invoke(app, ["compile", str(script_file), "--output", str(output_dir)])
    assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"

    # Check that .rpy files were generated
    rpy_files = list(output_dir.rglob("*.rpy"))
    assert len(rpy_files) > 0, "No .rpy files were generated"


def test_compile_with_characters(tmp_path: Path):
    script_file = tmp_path / "vn_script.json"
    script_file.write_text(json.dumps(VALID_SCRIPT), encoding="utf-8")

    chars_file = tmp_path / "characters.json"
    chars_file.write_text(json.dumps(VALID_CHARACTERS), encoding="utf-8")

    output_dir = tmp_path / "out"

    result = runner.invoke(
        app,
        ["compile", str(script_file), "--characters", str(chars_file), "--output", str(output_dir)],
    )
    assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"

    rpy_files = list(output_dir.rglob("*.rpy"))
    assert len(rpy_files) > 0, "No .rpy files were generated"


def test_compile_output_contains_scene_labels(tmp_path: Path):
    script_file = tmp_path / "vn_script.json"
    script_file.write_text(json.dumps(VALID_SCRIPT), encoding="utf-8")

    output_dir = tmp_path / "out"
    runner.invoke(app, ["compile", str(script_file), "--output", str(output_dir)])

    # Read the compiled .rpy content
    rpy_content = ""
    for rpy_file in output_dir.rglob("*.rpy"):
        rpy_content += rpy_file.read_text(encoding="utf-8")

    assert "label ch1_morning:" in rpy_content


def test_compile_invalid_script(tmp_path: Path):
    script_file = tmp_path / "bad.json"
    script_file.write_text(json.dumps(INVALID_SCRIPT), encoding="utf-8")

    output_dir = tmp_path / "out"
    result = runner.invoke(app, ["compile", str(script_file), "--output", str(output_dir)])
    assert result.exit_code != 0
