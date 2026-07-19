"""v4 P1-3 unit tests for the Reflection Agent."""
from __future__ import annotations

import json

import pytest

from vn_agent.feedback import reflection, store as fb_store


@pytest.fixture(autouse=True)
def _iso_feedback_root(tmp_path, monkeypatch):
    monkeypatch.setenv(fb_store._DEFAULT_ROOT_ENV, str(tmp_path))
    yield


class _Msg:
    def __init__(self, content: str):
        self.content = content


def _fake_llm(rules: list[dict]):
    async def _run(system, user, model=None, caller=None):  # noqa: ARG001
        return _Msg(json.dumps({"rules": rules}))
    return _run


class TestInsufficientSamples:
    @pytest.mark.asyncio
    async def test_below_min_samples_skips(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="up", reason="ok"))
        report = await reflection.run_reflection(min_samples=5, llm=_fake_llm([]))
        assert report.stopped_reason == "insufficient_samples"
        assert report.rules == []
        # Disk untouched.
        assert not reflection._guidelines_path().exists()

    @pytest.mark.asyncio
    async def test_force_bypasses_threshold(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="rambly"))
        report = await reflection.run_reflection(
            min_samples=99,
            force=True,
            llm=_fake_llm([{"text": "Avoid rambly dialogue.", "polarity": "avoid"}]),
        )
        assert report.stopped_reason == "ok"
        assert len(report.rules) == 1


class TestNoReasons:
    @pytest.mark.asyncio
    async def test_records_without_reasons_stop(self):
        for _ in range(5):
            fb_store.append(fb_store.FeedbackRecord(verdict="up", reason=None))
        report = await reflection.run_reflection(min_samples=3, llm=_fake_llm([]))
        assert report.stopped_reason == "no_reasons"


class TestLLMSuccess:
    @pytest.mark.asyncio
    async def test_parses_and_writes_atomically(self):
        for i in range(5):
            fb_store.append(fb_store.FeedbackRecord(verdict="down", reason=f"reason {i}"))
        rules = [
            {"text": "Avoid overly long monologues.", "polarity": "avoid", "confidence": 0.8, "source_count": 3},
            {"text": "Prefer specific sensory detail.", "polarity": "prefer", "confidence": 0.6, "source_count": 2},
        ]
        report = await reflection.run_reflection(min_samples=3, llm=_fake_llm(rules))
        assert report.stopped_reason == "ok"
        assert len(report.rules) == 2

        path = reflection._guidelines_path()
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["stopped_reason"] == "ok"
        assert len(loaded["rules"]) == 2

    @pytest.mark.asyncio
    async def test_dry_run_reports_but_doesnt_write(self):
        for i in range(5):
            fb_store.append(fb_store.FeedbackRecord(verdict="down", reason=f"reason {i}"))
        report = await reflection.run_reflection(
            min_samples=3,
            write=False,
            llm=_fake_llm([{"text": "Avoid X.", "polarity": "avoid", "confidence": 0.7}]),
        )
        assert report.rules
        assert not reflection._guidelines_path().exists()

    @pytest.mark.asyncio
    async def test_max_rules_caps_output(self):
        for i in range(5):
            fb_store.append(fb_store.FeedbackRecord(verdict="down", reason=f"r{i}"))
        rules = [{"text": f"rule {i}", "polarity": "avoid", "confidence": 0.5} for i in range(30)]
        report = await reflection.run_reflection(
            min_samples=3,
            max_rules=5,
            llm=_fake_llm(rules),
        )
        assert len(report.rules) == 5

    @pytest.mark.asyncio
    async def test_confidence_clamped(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="x"))
        report = await reflection.run_reflection(
            min_samples=1, force=True,
            llm=_fake_llm([
                {"text": "hi", "polarity": "avoid", "confidence": 1.5},
                {"text": "lo", "polarity": "avoid", "confidence": -0.2},
            ]),
        )
        assert report.rules[0].confidence == 1.0
        assert report.rules[1].confidence == 0.0

    @pytest.mark.asyncio
    async def test_polarity_defaults_to_avoid(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="x"))
        report = await reflection.run_reflection(
            min_samples=1, force=True,
            llm=_fake_llm([
                {"text": "no polarity given", "confidence": 0.5},
                {"text": "bad polarity", "polarity": "maybe", "confidence": 0.5},
            ]),
        )
        assert all(r.polarity == "avoid" for r in report.rules)

    @pytest.mark.asyncio
    async def test_prefer_polarity_preserved(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="up", reason="great"))
        report = await reflection.run_reflection(
            min_samples=1, force=True,
            llm=_fake_llm([{"text": "keep doing X", "polarity": "prefer", "confidence": 0.9}]),
        )
        assert report.rules[0].polarity == "prefer"


class TestLLMFailure:
    @pytest.mark.asyncio
    async def test_llm_raises_falls_back(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="x"))

        async def failing_llm(system, user, **kw):  # noqa: ARG001
            raise RuntimeError("network down")

        report = await reflection.run_reflection(min_samples=1, force=True, llm=failing_llm)
        assert report.stopped_reason == "llm_failed"
        assert report.rules == []

    @pytest.mark.asyncio
    async def test_unparseable_json_marked_failed(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="x"))
        async def bad_llm(system, user, **kw):  # noqa: ARG001
            return _Msg("sorry, no rules today")
        report = await reflection.run_reflection(min_samples=1, force=True, llm=bad_llm)
        assert report.stopped_reason == "llm_failed"


class TestLoadFormat:
    def test_load_missing_returns_none(self):
        assert reflection.load_guidelines() is None

    def test_load_corrupt_returns_none(self):
        path = reflection._guidelines_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ this is not json", encoding="utf-8")
        assert reflection.load_guidelines() is None

    def test_format_empty_returns_empty_string(self):
        assert reflection.format_guidelines_for_prompt(None) == ""
        assert reflection.format_guidelines_for_prompt(reflection.ReflectionReport()) == ""

    def test_format_groups_by_polarity(self):
        report = reflection.ReflectionReport(rules=[
            reflection.Guideline(text="don't be verbose", polarity="avoid"),
            reflection.Guideline(text="use sensory detail", polarity="prefer"),
            reflection.Guideline(text="don't repeat beats", polarity="avoid"),
        ])
        out = reflection.format_guidelines_for_prompt(report)
        assert "Avoid:" in out
        assert "Prefer:" in out
        assert out.index("Avoid:") < out.index("Prefer:")
        assert "don't be verbose" in out
        assert "use sensory detail" in out


class TestExtractRulesJSON:
    def test_bare_json(self):
        rules = reflection._extract_rules_json('{"rules": [{"text": "a"}]}')
        assert rules == [{"text": "a"}]

    def test_json_in_code_fence(self):
        raw = "```json\n{\"rules\": [{\"text\": \"a\"}]}\n```"
        rules = reflection._extract_rules_json(raw)
        assert rules == [{"text": "a"}]

    def test_no_json_returns_empty(self):
        assert reflection._extract_rules_json("nothing here") == []

    def test_missing_text_filtered(self):
        raw = '{"rules": [{"confidence": 0.5}, {"text": "keeper"}]}'
        rules = reflection._extract_rules_json(raw)
        assert rules == [{"text": "keeper"}]
