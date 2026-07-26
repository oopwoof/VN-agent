"""v4 P5 M0 unit tests for the autopilot run-outcome log."""
from __future__ import annotations

import pytest

from vn_agent.autopilot import outcomes as ap_outcomes


@pytest.fixture(autouse=True)
def _iso_autopilot_root(tmp_path, monkeypatch):
    monkeypatch.setenv(ap_outcomes._DEFAULT_ROOT_ENV, str(tmp_path))
    yield


class TestAutopilotOutcome:
    def test_defaults(self):
        rec = ap_outcomes.AutopilotOutcome(
            job_id="abc123", theme="a school romance", preset_used="autopilot_best",
            success=True, wall_time_seconds=120.5,
        )
        assert rec.id.startswith("apr_")
        assert rec.created_at.endswith("Z")
        assert rec.estimated_cost_usd == 0.0
        assert rec.error is None


class TestAppendLoad:
    def test_load_all_empty_when_no_file(self):
        assert ap_outcomes.load_all() == []

    def test_append_and_load_roundtrip(self):
        rec = ap_outcomes.AutopilotOutcome(
            job_id="job1", theme="theme1", preset_used="autopilot_best",
            success=True, wall_time_seconds=90.0, estimated_cost_usd=0.15, scene_count=6,
        )
        ap_outcomes.append(rec)
        loaded = ap_outcomes.load_all()
        assert len(loaded) == 1
        assert loaded[0].job_id == "job1"
        assert loaded[0].scene_count == 6

    def test_corrupt_line_skipped(self, tmp_path):
        path = ap_outcomes._jsonl_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json\n", encoding="utf-8")
        assert ap_outcomes.load_all() == []

    def test_summarize_success_rate(self):
        ap_outcomes.append(ap_outcomes.AutopilotOutcome(
            job_id="a", theme="t", preset_used="autopilot_best", success=True, wall_time_seconds=60.0,
        ))
        ap_outcomes.append(ap_outcomes.AutopilotOutcome(
            job_id="b", theme="t", preset_used="autopilot_best", success=False, wall_time_seconds=30.0,
        ))
        summary = ap_outcomes.summarize()
        assert summary["total"] == 2
        assert summary["success_rate"] == 0.5

    def test_summarize_empty(self):
        summary = ap_outcomes.summarize()
        assert summary["total"] == 0
        assert summary["success_rate"] is None
