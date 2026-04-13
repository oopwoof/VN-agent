"""Tests for corpus loading and strategy mapping."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from vn_agent.eval.corpus import (
    STRATEGY_MAP,
    load_corpus,
    load_reasoning,
)

# 5-row test fixture (inline, no external files needed)
FIXTURE_ROWS = [
    {"id": "1", "title": "A Gentle Start", "text": "Line1\nLine2\nLine3",
     "predominant_strategy": "Accumulate", "pivot_line_idx": "3", "pacing": "slow"},
    {"id": "2", "title": "Breaking Point", "text": "Shock\nRevelation",
     "predominant_strategy": "Rupture", "pivot_line_idx": "1", "pacing": "fast"},
    {"id": "3", "title": "Hidden Truth  ", "text": "Mystery unfolds",
     "predominant_strategy": " Uncover ", "pivot_line_idx": "", "pacing": " medium "},
    {"id": "4", "title": "Battle Lines", "text": "Conflict text",
     "predominant_strategy": "Contest", "pivot_line_idx": "5", "pacing": ""},
    {"id": "5", "title": "Miscellaneous", "text": "Random text",
     "predominant_strategy": "Other", "pivot_line_idx": "", "pacing": ""},
]


def _write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = ["id", "title", "text", "predominant_strategy", "pivot_line_idx", "pacing"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestLoadCorpus:
    def test_loads_correct_count(self, tmp_path):
        csv_path = tmp_path / "annotations.csv"
        _write_csv(csv_path, FIXTURE_ROWS)
        sessions = load_corpus(csv_path)
        assert len(sessions) == 5

    def test_strategy_mapping(self, tmp_path):
        csv_path = tmp_path / "annotations.csv"
        _write_csv(csv_path, FIXTURE_ROWS)
        sessions = load_corpus(csv_path)

        assert sessions[0].strategy == "accumulate"  # Accumulate -> accumulate
        assert sessions[1].strategy == "rupture"  # Rupture -> rupture
        assert sessions[2].strategy == "uncover"  # Uncover -> uncover (with whitespace)
        assert sessions[3].strategy == "contest"  # Contest -> contest
        assert sessions[4].strategy is None  # Other -> None

    def test_trailing_space_cleaning(self, tmp_path):
        csv_path = tmp_path / "annotations.csv"
        _write_csv(csv_path, FIXTURE_ROWS)
        sessions = load_corpus(csv_path)

        # Row 3 has trailing spaces on title and pacing
        assert sessions[2].title == "Hidden Truth"
        assert sessions[2].pacing == "medium"

    def test_pivot_line_idx_parsing(self, tmp_path):
        csv_path = tmp_path / "annotations.csv"
        _write_csv(csv_path, FIXTURE_ROWS)
        sessions = load_corpus(csv_path)

        assert sessions[0].pivot_line_idx == 3
        assert sessions[2].pivot_line_idx is None  # empty string
        assert sessions[3].pivot_line_idx == 5

    def test_empty_pacing_becomes_none(self, tmp_path):
        csv_path = tmp_path / "annotations.csv"
        _write_csv(csv_path, FIXTURE_ROWS)
        sessions = load_corpus(csv_path)

        assert sessions[4].pacing is None


class TestLoadReasoning:
    def test_loads_jsonl(self, tmp_path):
        jsonl_path = tmp_path / "reasoning.jsonl"
        entries = [
            {"id": "1", "gist": "A gentle buildup", "strategy_reasoning": "Slow accumulation"},
            {"id": "2", "gist": "Sudden break", "pivot_type": "revelation"},
        ]
        jsonl_path.write_text(
            "\n".join(json.dumps(e) for e in entries), encoding="utf-8"
        )
        data = load_reasoning(jsonl_path)

        assert len(data) == 2
        assert data["1"]["gist"] == "A gentle buildup"
        assert data["2"]["pivot_type"] == "revelation"

    def test_skips_empty_lines(self, tmp_path):
        jsonl_path = tmp_path / "reasoning.jsonl"
        jsonl_path.write_text(
            '{"id": "1", "gist": "test"}\n\n\n{"id": "2", "gist": "test2"}\n',
            encoding="utf-8",
        )
        data = load_reasoning(jsonl_path)
        assert len(data) == 2


class TestStrategyMap:
    def test_all_colx_strategies_mapped(self):
        expected_colx = {"Accumulate", "Erode", "Rupture", "Uncover", "Contest", "Drift", "Other"}
        assert set(STRATEGY_MAP.keys()) == expected_colx

    def test_maps_to_valid_vn_agent_strategies(self):
        vn_strategies = {"accumulate", "erode", "rupture", "uncover", "contest", "drift"}
        mapped = {v for v in STRATEGY_MAP.values() if v is not None}
        assert mapped == vn_strategies
