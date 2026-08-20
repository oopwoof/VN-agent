"""Tests for mock LLM dispatch logic."""
import json

import pytest

from vn_agent.services.mock_llm import mock_ainvoke


@pytest.mark.asyncio
async def test_dispatch_director_step1():
    r = await mock_ainvoke("You are a director", "A story about a lighthouse", caller="director/step1")
    assert "scenes" in r.content
    assert "characters" in r.content


@pytest.mark.asyncio
async def test_dispatch_director_step2():
    r = await mock_ainvoke(
        "You are a director. Add navigation and next_scene_id",
        "test",
        caller="director/step2",
    )
    assert "next_scene_id" in r.content
    assert "branches" in r.content


@pytest.mark.asyncio
async def test_dispatch_reviewer():
    r = await mock_ainvoke("You are a reviewer", "test script", caller="reviewer")
    assert "PASS" in r.content


@pytest.mark.asyncio
async def test_dispatch_writer():
    r = await mock_ainvoke("You write dialogue", "scene ch1_arrival", caller="writer/ch1_arrival")
    assert "character_id" in r.content


@pytest.mark.asyncio
async def test_dispatch_writer_fallback():
    r = await mock_ainvoke("You write dialogue", "unknown scene", caller="writer/unknown")
    assert "character_id" in r.content  # returns first scene as fallback


@pytest.mark.asyncio
async def test_dispatch_character_designer():
    r = await mock_ainvoke("You are a character designer", "describe Mara", caller="char_designer")
    assert "art_style" in r.content


@pytest.mark.asyncio
async def test_dispatch_scene_artist():
    r = await mock_ainvoke("You are a background artist", "lighthouse", caller="scene_artist/bg1")
    assert "prompt" in r.content


@pytest.mark.asyncio
async def test_dispatch_chinese():
    r = await mock_ainvoke("You are a director", "一个关于灯塔的故事", caller="director/step1")
    assert "樱花" in r.content or "scenes" in r.content  # Chinese fixture


@pytest.mark.asyncio
async def test_dispatch_fallback():
    r = await mock_ainvoke("Unknown system prompt", "test", caller="unknown")
    assert "mock response" in r.content


@pytest.mark.asyncio
async def test_mock_message_metadata():
    r = await mock_ainvoke("You are a reviewer", "test", caller="reviewer")
    assert hasattr(r, "response_metadata")
    assert r.response_metadata["stop_reason"] == "end_turn"


# ── v4 P3: chat_ops mock dispatch ──────────────────────────────────────────

class TestChatOpsMockDispatch:
    @pytest.mark.asyncio
    async def test_intent_classifier_returns_valid_schema(self):
        from vn_agent.chat_ops.intent_router import IntentClassification

        r = await mock_ainvoke(
            "You are the intent router",
            "Project context:\nScenes:\n  - ch1_arrival: Arrival\n\nCreator message: 'why does ch1 happen?'",
            schema=IntentClassification, caller="chat_ops/intent_router",
        )
        assert isinstance(r, IntentClassification)
        assert r.intent == "explain"

    @pytest.mark.asyncio
    async def test_intent_classifier_regen_keyword_picks_up_scene_id(self):
        from vn_agent.chat_ops.intent_router import IntentClassification

        r = await mock_ainvoke(
            "You are the intent router",
            "Project context:\nScenes:\n  - ch1_arrival: Arrival\n\nCreator message: 'rewrite ch1_arrival to be funnier'",
            schema=IntentClassification, caller="chat_ops/intent_router",
        )
        assert r.intent == "local_regen"
        assert r.target_scene_id == "ch1_arrival"

    @pytest.mark.asyncio
    async def test_intent_classifier_add_character_keyword(self):
        from vn_agent.chat_ops.intent_router import IntentClassification

        r = await mock_ainvoke(
            "You are the intent router",
            "Project context:\n(no project context available)\n\nCreator message: 'add a new character named Yuki'",
            schema=IntentClassification, caller="chat_ops/intent_router",
        )
        assert r.intent == "add_character"

    @pytest.mark.asyncio
    async def test_intent_classifier_no_keyword_no_scene_is_unknown(self):
        from vn_agent.chat_ops.intent_router import IntentClassification

        r = await mock_ainvoke(
            "You are the intent router",
            "Project context:\n(no project context available)\n\nCreator message: 'hello there'",
            schema=IntentClassification, caller="chat_ops/intent_router",
        )
        assert r.intent == "unknown"

    @pytest.mark.asyncio
    async def test_intent_classifier_chinese_keywords(self):
        from vn_agent.chat_ops.intent_router import IntentClassification

        r = await mock_ainvoke(
            "You are the intent router",
            "Project context:\nScenes:\n  - ch1: 开场\n\nCreator message: '为什么ch1这样设计'",
            schema=IntentClassification, caller="chat_ops/intent_router",
        )
        assert r.intent == "explain"

    @pytest.mark.asyncio
    async def test_explain_caller_returns_text_not_json(self):
        r = await mock_ainvoke(
            "You answer questions", "Question: why?", caller="chat_ops/explain",
        )
        assert r.content  # non-empty text, not schema-validated


# ── 50-scene dry run P0: caller-tag routing ────────────────────────────────
#
# The keyword ladder misroutes exactly the long-form callers, and it fails
# *silently and positively*: THINKING_SYSTEM mentions "director" so thinking
# workers got the step1 outline back — which validates into an all-defaults
# SceneThinking while the node logs "produced thinking for N/N scenes".
# ROLLUP_SYSTEM says "RAW DIALOGUE" and its user prompt embeds scene ids, so
# chapter rollups got a writer dialogue array stored as Chapter.summary.
# These tests call through the REAL system prompts (imported, not paraphrased)
# so a prompt rewording that reintroduces a collision fails here, not in a
# 50-scene run's silent output.

class TestCallerTagRouting:
    @pytest.mark.asyncio
    async def test_thinking_caller_returns_nonvacuous_scene_thinking(self):
        from vn_agent.agents.thinking import THINKING_SYSTEM
        from vn_agent.schema.script import SceneThinking

        r = await mock_ainvoke(
            THINKING_SYSTEM,
            "## Scene being planned: ch1_arrival — Storm's Eve\n"
            "Characters present: ['char_mara', 'char_voice']",
            caller="thinking/ch1_arrival",
        )
        thinking = SceneThinking.model_validate(json.loads(r.content))
        assert thinking.writing_intent
        assert thinking.key_beats_expanded

    @pytest.mark.asyncio
    async def test_resync_caller_returns_scene_thinking_not_dialogue(self):
        from vn_agent.agents.thinking import RESYNC_SYSTEM
        from vn_agent.schema.script import SceneThinking

        r = await mock_ainvoke(
            RESYNC_SYSTEM,
            "Your current thinking for ch1_signal, plus peer plans.",
            caller="resync/ch1_signal",
        )
        data = json.loads(r.content)
        assert isinstance(data, dict)  # not a writer dialogue array
        assert SceneThinking.model_validate(data).writing_intent

    @pytest.mark.asyncio
    async def test_rollup_caller_returns_prose_not_dialogue_json(self):
        from vn_agent.agents.summarizer import ROLLUP_SYSTEM

        r = await mock_ainvoke(
            ROLLUP_SYSTEM,
            "Chapter has 2 scenes. Target length: 200-800 words.\n\n"
            "=== Scene ch1_arrival: Storm's Eve ===\nDialogue:\n  ...\n\n"
            "=== Scene ch1_signal: Distress Signal ===\nDialogue:\n  ...",
            caller="rollup_chapter/ch_ch1_arrival-ch1_signal",
        )
        content = r.content.strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = None
        assert not isinstance(parsed, list)  # prose summary, not dialogue JSON
        assert len(content) > 40

    @pytest.mark.asyncio
    async def test_director_arbitrate_returns_decisions_list(self):
        from vn_agent.agents.thinking import DIRECTOR_ARBITRATE_SYSTEM

        r = await mock_ainvoke(
            DIRECTOR_ARBITRATE_SYSTEM,
            "Unresolved callback conflicts to arbitrate: []",
            caller="director_arbitrate",
        )
        data = json.loads(r.content)
        assert isinstance(data.get("decisions"), list)
