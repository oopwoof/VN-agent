"""v4 P1-1 unit tests for feedback store."""
from __future__ import annotations

import pytest

from vn_agent.feedback import store as fb_store


@pytest.fixture(autouse=True)
def _iso_feedback_root(tmp_path, monkeypatch):
    monkeypatch.setenv(fb_store._DEFAULT_ROOT_ENV, str(tmp_path))
    yield


class TestFeedbackRecord:
    def test_defaults(self):
        rec = fb_store.FeedbackRecord(verdict="up")
        assert rec.id.startswith("fb_")
        assert rec.created_at.endswith("Z")
        assert rec.tags == []
        assert rec.context == {}

    def test_verdict_validated(self):
        with pytest.raises(ValueError):
            fb_store.FeedbackRecord(verdict="maybe")  # type: ignore[arg-type]

    def test_bad_job_id_raises(self):
        with pytest.raises(ValueError):
            fb_store.FeedbackRecord(verdict="up", job_id="../../etc/passwd")

    def test_to_dict_drops_empty_collections(self):
        rec = fb_store.FeedbackRecord(verdict="up")
        d = rec.to_dict()
        assert "tags" not in d
        assert "context" not in d
        # verdict is retained even for the default up value (it's not "empty").
        assert d["verdict"] == "up"


class TestAppendLoad:
    def test_round_trip(self):
        rec = fb_store.FeedbackRecord(
            verdict="down",
            job_id="job-1",
            scene_id="ch1",
            reason="对白太啰嗦",
            tags=["dialogue-length"],
            context={"strategy": "erode"},
        )
        fb_store.append(rec)

        loaded = fb_store.load_all()
        assert len(loaded) == 1
        got = loaded[0]
        assert got.verdict == "down"
        assert got.reason == "对白太啰嗦"
        assert got.tags == ["dialogue-length"]
        assert got.context == {"strategy": "erode"}

    def test_load_empty_when_no_file(self):
        assert fb_store.load_all() == []

    def test_multiple_appends_preserve_order(self):
        for i, verdict in enumerate(["up", "down", "up"]):
            fb_store.append(fb_store.FeedbackRecord(verdict=verdict, reason=f"r{i}"))  # type: ignore[arg-type]
        loaded = fb_store.load_all()
        assert [r.reason for r in loaded] == ["r0", "r1", "r2"]

    def test_load_recent_slices_tail(self):
        for i in range(10):
            fb_store.append(fb_store.FeedbackRecord(verdict="up", reason=f"r{i}"))
        recent = fb_store.load_recent(3)
        assert [r.reason for r in recent] == ["r7", "r8", "r9"]

    def test_load_recent_zero_returns_empty(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="up"))
        assert fb_store.load_recent(0) == []


class TestCorruptLineTolerance:
    def test_bad_json_line_skipped(self):
        # Prime with a valid record so we have a real file to hand-edit.
        fb_store.append(fb_store.FeedbackRecord(verdict="up", reason="valid"))

        # Now write a corrupt line + a second good record via the raw path.
        path = fb_store._jsonl_path()
        with path.open("a", encoding="utf-8") as f:
            f.write("not json at all\n")
            f.write('{"verdict":"down","reason":"still valid"}\n')

        loaded = fb_store.load_all()
        assert [r.reason for r in loaded] == ["valid", "still valid"]

    def test_missing_verdict_key_skipped(self):
        path = fb_store._jsonl_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write('{"reason":"no verdict here"}\n')
            f.write('{"verdict":"up","reason":"ok"}\n')

        loaded = fb_store.load_all()
        assert [r.reason for r in loaded] == ["ok"]


class TestFiltering:
    def test_load_by_verdict(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="up", reason="a"))
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="b"))
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="c"))
        downs = fb_store.load_by_verdict("down")
        assert [r.reason for r in downs] == ["b", "c"]
        ups = fb_store.load_by_verdict("up")
        assert [r.reason for r in ups] == ["a"]

    def test_iter_reasons_skips_empty(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="up", reason="present"))
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason=None))
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="also present"))
        reasons = list(fb_store.iter_reasons())
        assert reasons == ["present", "also present"]

    def test_iter_reasons_verdict_filter(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="up", reason="a"))
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="b"))
        assert list(fb_store.iter_reasons("down")) == ["b"]
        assert list(fb_store.iter_reasons("up")) == ["a"]


class TestSummarize:
    def test_empty(self):
        s = fb_store.summarize()
        assert s == {
            "total": 0,
            "by_verdict": {"up": 0, "down": 0},
            "by_scene": {},
            "by_job": {},
            "top_tags": {},
        }

    def test_counts_and_tag_histogram(self):
        fb_store.append(fb_store.FeedbackRecord(
            verdict="up", job_id="j1", scene_id="s1", tags=["dialogue"],
        ))
        fb_store.append(fb_store.FeedbackRecord(
            verdict="down", job_id="j1", scene_id="s2", tags=["dialogue", "校园"],
        ))
        fb_store.append(fb_store.FeedbackRecord(
            verdict="down", job_id="j2", scene_id="s1", tags=["校园"],
        ))
        s = fb_store.summarize()
        assert s["total"] == 3
        assert s["by_verdict"] == {"up": 1, "down": 2}
        assert s["by_scene"] == {"s1": 2, "s2": 1}
        assert s["by_job"] == {"j1": 2, "j2": 1}
        assert s["top_tags"]["校园"] == 2
        assert s["top_tags"]["dialogue"] == 2
