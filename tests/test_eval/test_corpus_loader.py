"""Tests for heterogeneous corpus loader (annotated CSV + unannotated JSONL)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vn_agent.eval.corpus_loader import _fingerprint, load_merged_corpus


@pytest.fixture
def annotated_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "annotations.csv"
    csv_path.write_text(
        "id,title,text,predominant_strategy,pivot_line_idx,pacing\n"
        "ann_1,Story A,Annotated text one about slowly building trust,Accumulate,3,slow\n"
        "ann_2,Story B,Annotated text two with sudden shocking truth,Rupture,4,fast\n",
        encoding="utf-8",
    )
    return csv_path


@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sessions"
    d.mkdir()
    # File with 3 unannotated sessions, one of which duplicates ann_1 by id
    (d / "part_00.jsonl").write_text(
        json.dumps({"id": "ann_1", "title": "Dup A", "n_lines": 12,
                    "text": "Duplicate of annotated ann_1 — should be filtered out"}) + "\n"
        + json.dumps({"id": "raw_100", "title": "Raw 100", "n_lines": 12,
                      "text": "Raw session 100 not yet annotated"}) + "\n"
        + json.dumps({"id": "raw_101", "title": "Raw 101", "n_lines": 12,
                      "text": "Another raw session for the unannotated pool"}) + "\n",
        encoding="utf-8",
    )
    # Second file: adds one more + a fingerprint-duplicate of ann_2
    (d / "part_01.jsonl").write_text(
        json.dumps({"id": "raw_200", "title": "Raw 200", "n_lines": 12,
                    "text": "Yet another raw session"}) + "\n"
        + json.dumps({"id": "diff_id_same_text", "title": "Story B",
                      "n_lines": 12,
                      "text": "Annotated text two with sudden shocking truth"}) + "\n",
        encoding="utf-8",
    )
    return d


class TestLoadMergedCorpus:
    def test_without_sessions_dir_returns_only_annotated(self, annotated_csv):
        result = load_merged_corpus(annotated_csv, sessions_dir=None)
        assert len(result) == 2
        assert all(s.strategy is not None for s in result)

    def test_missing_sessions_dir_falls_back_gracefully(self, annotated_csv, tmp_path):
        missing = tmp_path / "does_not_exist"
        result = load_merged_corpus(annotated_csv, sessions_dir=missing)
        assert len(result) == 2

    def test_merges_unannotated(self, annotated_csv, sessions_dir):
        result = load_merged_corpus(annotated_csv, sessions_dir)
        # 2 annotated + 3 unique unannotated (raw_100, raw_101, raw_200)
        # Duplicates filtered: ann_1 (id match) + Story B (fingerprint match)
        assert len(result) == 5

    def test_annotated_come_first(self, annotated_csv, sessions_dir):
        result = load_merged_corpus(annotated_csv, sessions_dir)
        annotated_count = sum(1 for s in result[:2] if s.strategy is not None)
        assert annotated_count == 2
        assert all(s.strategy is None for s in result[2:])

    def test_id_based_dedup(self, annotated_csv, sessions_dir):
        result = load_merged_corpus(annotated_csv, sessions_dir)
        # ann_1 appears only once (the annotated version), not duplicated
        assert [s.id for s in result].count("ann_1") == 1
        ann_1 = next(s for s in result if s.id == "ann_1")
        # The annotated version should win (has strategy)
        assert ann_1.strategy == "accumulate"

    def test_fingerprint_dedup(self, annotated_csv, sessions_dir):
        result = load_merged_corpus(annotated_csv, sessions_dir)
        # "diff_id_same_text" has different id but same fingerprint as ann_2
        assert not any(s.id == "diff_id_same_text" for s in result)

    def test_extras_dedup_among_themselves(self, annotated_csv, tmp_path):
        d = tmp_path / "sessions"
        d.mkdir()
        (d / "part_a.jsonl").write_text(
            json.dumps({"id": "x1", "title": "X", "n_lines": 12, "text": "Same content"}) + "\n",
            encoding="utf-8",
        )
        (d / "part_b.jsonl").write_text(
            json.dumps({"id": "x2", "title": "X", "n_lines": 12, "text": "Same content"}) + "\n",
            encoding="utf-8",
        )
        result = load_merged_corpus(annotated_csv, d)
        # Only one of x1/x2 survives (same fingerprint)
        survivors = [s for s in result if s.id in {"x1", "x2"}]
        assert len(survivors) == 1

    def test_malformed_line_skipped(self, annotated_csv, tmp_path):
        d = tmp_path / "sessions"
        d.mkdir()
        (d / "bad.jsonl").write_text(
            "{not json\n"
            + json.dumps({"id": "ok", "title": "OK", "n_lines": 12, "text": "good content"}) + "\n",
            encoding="utf-8",
        )
        result = load_merged_corpus(annotated_csv, d)
        # Malformed line silently skipped; valid one kept
        assert any(s.id == "ok" for s in result)


def test_fingerprint_stable():
    fp1 = _fingerprint("Title", "Body of text")
    fp2 = _fingerprint("Title", "Body of text")
    fp3 = _fingerprint("Title ", "Body of text")  # whitespace variation
    assert fp1 == fp2
    assert fp1 == fp3


def test_fingerprint_differs_on_content():
    fp1 = _fingerprint("Title", "Body A")
    fp2 = _fingerprint("Title", "Body B")
    assert fp1 != fp2
