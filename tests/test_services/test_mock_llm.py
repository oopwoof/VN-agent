"""Tests for mock LLM dispatch logic."""
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
