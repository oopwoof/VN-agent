"""v4 P3-1: intent classifier. Zero real API — every test injects a fake
`llm` callable matching ainvoke_llm's `(system, user, schema=None, model=None,
caller=None) -> T | str` signature, per the same pattern as
`assets/web_search_agent.py::plan_queries`'s tests."""
from __future__ import annotations

import pytest

from vn_agent.chat_ops.intent_router import IntentClassification, classify_intent

_BLACKBOARD = {
    "theme": "A quiet school semester",
    "scene_scripts": [
        {"id": "ch1_arrival", "title": "Arrival"},
        {"id": "ch2_lunch", "title": "Lunch"},
    ],
    "characters": {"alice": {"name": "Alice"}, "bob": {"name": "Bob"}},
}


def _fake_llm(classification: IntentClassification):
    async def _llm(system, user, schema=None, model=None, caller=None):  # noqa: ARG001
        assert schema is IntentClassification
        return classification
    return _llm


class TestClassifyIntent:
    @pytest.mark.asyncio
    async def test_local_regen_with_valid_scene_id_passes_through(self):
        fake = _fake_llm(IntentClassification(
            intent="local_regen", target_scene_id="ch1_arrival",
            instruction="make it funnier", confidence=0.9,
        ))
        result = await classify_intent("make ch1_arrival funnier", _BLACKBOARD, llm=fake)
        assert result.intent == "local_regen"
        assert result.target_scene_id == "ch1_arrival"

    @pytest.mark.asyncio
    async def test_hallucinated_scene_id_demotes_to_unknown(self):
        """The classifier claimed a scene id that doesn't exist in this
        project — classify_intent must not trust it blindly."""
        fake = _fake_llm(IntentClassification(
            intent="local_regen", target_scene_id="ch99_nonexistent",
            instruction="rewrite it", confidence=0.8,
        ))
        result = await classify_intent("rewrite that scene", _BLACKBOARD, llm=fake)
        assert result.intent == "unknown"
        assert result.target_scene_id is None

    @pytest.mark.asyncio
    async def test_hallucinated_character_id_dropped_but_intent_kept(self):
        """edit_asset doesn't require a scene id specifically — only the
        invalid id itself is dropped, not the whole classification."""
        fake = _fake_llm(IntentClassification(
            intent="edit_asset", target_character_id="char_ghost",
            instruction="change her outfit", confidence=0.7,
        ))
        result = await classify_intent("change her outfit", _BLACKBOARD, llm=fake)
        assert result.intent == "edit_asset"
        assert result.target_character_id is None

    @pytest.mark.asyncio
    async def test_valid_character_id_kept(self):
        fake = _fake_llm(IntentClassification(
            intent="edit_asset", target_character_id="alice",
            instruction="change her outfit", confidence=0.7,
        ))
        result = await classify_intent("change alice's outfit", _BLACKBOARD, llm=fake)
        assert result.target_character_id == "alice"

    @pytest.mark.asyncio
    async def test_empty_message_short_circuits_without_llm_call(self):
        called = False

        async def _llm(*a, **kw):  # noqa: ARG001
            nonlocal called
            called = True
            return IntentClassification(intent="explain", confidence=1.0)

        result = await classify_intent("   ", _BLACKBOARD, llm=_llm)
        assert result.intent == "unknown"
        assert result.confidence == 0.0
        assert not called

    @pytest.mark.asyncio
    async def test_llm_failure_degrades_to_unknown_not_raise(self):
        async def _llm(*a, **kw):  # noqa: ARG001
            raise RuntimeError("simulated API error")

        result = await classify_intent("do something", _BLACKBOARD, llm=_llm)
        assert result.intent == "unknown"
        assert result.confidence == 0.0
        assert "simulated API error" in result.reasoning

    @pytest.mark.asyncio
    async def test_explain_intent_no_scene_required(self):
        fake = _fake_llm(IntentClassification(intent="explain", confidence=0.95, instruction="why does it end there"))
        result = await classify_intent("why does the story end there?", _BLACKBOARD, llm=fake)
        assert result.intent == "explain"
        assert result.target_scene_id is None

    @pytest.mark.asyncio
    async def test_non_schema_llm_return_degrades_gracefully(self):
        """A misbehaving injected llm returns a raw string instead of the
        parsed schema instance — must not crash, must degrade to unknown."""
        async def _llm(*a, **kw):  # noqa: ARG001
            return "not a schema instance"

        result = await classify_intent("do something", _BLACKBOARD, llm=_llm)
        assert result.intent == "unknown"
