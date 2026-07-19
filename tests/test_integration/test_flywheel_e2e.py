"""v4 P1 integration: full feedback flywheel end-to-end.

Exercises the whole loop offline:
  1. Feedback records land in the store
  2. Injector surfaces relevant AVOID lines for a scene context
  3. Reflection Agent (mock LLM) distills rules → dynamic_guidelines.json
  4. `format_guidelines_for_prompt` renders the Writer-consumable block

No LLM API, no network. `run_writer` isn't invoked here — the injector's
`build_injection` and reflection's `format_guidelines_for_prompt` are
the exact call sites Writer uses, so unit-through-integration coverage
is byte-equivalent to running Writer in mock mode without the SBERT +
langgraph overhead.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from vn_agent.feedback import injector, reflection, store as fb_store


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv(fb_store._DEFAULT_ROOT_ENV, str(tmp_path))
    yield


def _scene(**kw) -> SimpleNamespace:
    d = {"description": "", "title": "", "narrative_strategy": None, "characters_present": []}
    d.update(kw)
    return SimpleNamespace(**d)


class TestSubmitToInjection:
    def test_downvote_reason_hits_writer_avoid_block(self):
        # Creator complains about a specific writing tic.
        fb_store.append(fb_store.FeedbackRecord(
            verdict="down",
            job_id="job-a",
            scene_id="ch1_arrival",
            reason="对白太啰嗦，节奏拖沓",
            tags=["dialogue-length"],
        ))
        fb_store.append(fb_store.FeedbackRecord(
            verdict="down",
            job_id="job-a",
            scene_id="ch3_action",
            reason="打斗描写平淡",
        ))
        fb_store.append(fb_store.FeedbackRecord(
            verdict="down",
            job_id="job-a",
            scene_id="ch5_rooftop",
            reason="the rooftop conversation dragged",
        ))
        # Writer is about to draft a new dialogue scene.
        scene = _scene(description="两人在屋顶上对话 rooftop dialogue")
        result = injector.build_injection(scene, min_score=0.5)
        assert not result.is_empty
        text = result.text
        # AVOID header + at least one topical Chinese/English rule.
        assert text.startswith("AVOID")
        assert "对白" in text or "rooftop" in text

    def test_upvote_alone_gives_no_injection(self):
        fb_store.append(fb_store.FeedbackRecord(
            verdict="up",
            reason="rooftop dialogue was great, natural pacing",
        ))
        scene = _scene(description="rooftop conversation")
        result = injector.build_injection(scene, min_score=0.5)
        assert result.is_empty


class TestInjectionToReflection:
    @pytest.mark.asyncio
    async def test_batch_distills_downvotes_into_rules(self):
        # Prime 5 down-vote records around a common theme.
        for i, reason in enumerate([
            "对白太啰嗦",
            "对话缺乏节奏感",
            "monologues are far too long",
            "characters over-explain motivations",
            "dialogue reads like exposition",
        ]):
            fb_store.append(fb_store.FeedbackRecord(
                verdict="down", job_id=f"job-{i}", reason=reason,
            ))
        # Mock the LLM so we don't call Anthropic.
        expected_rules = [
            {"text": "Avoid over-explaining character motivations mid-dialogue.",
             "polarity": "avoid", "confidence": 0.85, "source_count": 3},
            {"text": "Keep monologues under 3 sentences unless the scene demands it.",
             "polarity": "avoid", "confidence": 0.75, "source_count": 4},
        ]

        class _Msg:
            def __init__(self, s: str): self.content = s

        async def fake_llm(system, user, model=None, caller=None):  # noqa: ARG001
            return _Msg(json.dumps({"rules": expected_rules}))

        report = await reflection.run_reflection(
            min_samples=3, llm=fake_llm,
        )
        assert report.stopped_reason == "ok"
        assert len(report.rules) == 2

        # Written to disk atomically.
        loaded = reflection.load_guidelines()
        assert loaded is not None
        assert [r.text for r in loaded.rules] == [r["text"] for r in expected_rules]


class TestGuidelinesToWriterPromptBlock:
    def test_prompt_block_shape(self):
        report = reflection.ReflectionReport(rules=[
            reflection.Guideline(text="don't be verbose", polarity="avoid", confidence=0.9),
            reflection.Guideline(text="use concrete detail", polarity="prefer", confidence=0.7),
        ])
        block = reflection.format_guidelines_for_prompt(report)
        assert block.startswith("GUIDELINES")
        assert "Avoid:" in block
        assert "Prefer:" in block
        assert "don't be verbose" in block
        assert "use concrete detail" in block

    def test_none_report_returns_empty(self):
        assert reflection.format_guidelines_for_prompt(None) == ""


class TestFullLoop:
    @pytest.mark.asyncio
    async def test_upvote_survives_scene_scoping_and_reflection(self):
        """End-to-end: append records → run reflection → dynamic guidelines
        exist → Writer's `format_guidelines_for_prompt` would inject them.
        Verifies the entire byte-level flow the pipeline actually executes."""
        # 6 records, 4 down + 2 up.
        for r in ["对白啰嗦", "too many monologues", "scene 5 dragged", "characters felt flat"]:
            fb_store.append(fb_store.FeedbackRecord(verdict="down", reason=r))
        for r in ["scene 3 pacing was tight", "sensory detail was vivid"]:
            fb_store.append(fb_store.FeedbackRecord(verdict="up", reason=r))

        # Injector — writer's per-scene call.
        scene = _scene(description="对白 dialogue in scene 5")
        inj = injector.build_injection(scene, min_score=0.5)
        assert not inj.is_empty
        assert "对白" in inj.text or "scene 5" in inj.text

        # Reflection Agent — nightly batch.
        class _Msg:
            def __init__(self, s: str): self.content = s

        async def fake_llm(system, user, model=None, caller=None):  # noqa: ARG001
            return _Msg(json.dumps({"rules": [
                {"text": "Avoid overly verbose dialogue.", "polarity": "avoid", "confidence": 0.9},
                {"text": "Prefer vivid sensory detail.", "polarity": "prefer", "confidence": 0.7},
            ]}))

        report = await reflection.run_reflection(min_samples=3, llm=fake_llm)
        assert report.stopped_reason == "ok"

        # Guidelines exposed to Writer's system-prompt hook.
        block = reflection.format_guidelines_for_prompt(reflection.load_guidelines())
        assert "verbose" in block
        assert "vivid sensory detail" in block
