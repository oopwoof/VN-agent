"""P4: vision_judge.judge_frame — llm=None injection pattern, no real API."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from vn_agent.playtest.schema import PlaytestFrameJudgment, WalkNode
from vn_agent.playtest.vision_judge import judge_frame
from vn_agent.services.mock_llm import mock_ainvoke


@pytest.fixture
def frame_path(tmp_path) -> Path:
    path = tmp_path / "frame.png"
    Image.new("RGB", (200, 120), (10, 10, 10)).save(path)
    return path


@pytest.fixture
def node() -> WalkNode:
    return WalkNode(
        node_id="s1", scene_id="s1", scene_title="Arrival", kind="scene",
        dialogue_excerpt=["alice (neutral): hello"],
    )


@pytest.mark.asyncio
async def test_judge_frame_passes_exactly_one_image(frame_path, node):
    captured: dict = {}

    async def fake_llm(system, user, schema=None, model=None, caller=None, **kw):
        captured["images"] = kw.get("images")
        captured["caller"] = caller
        return PlaytestFrameJudgment(
            ui_coherence_score=4, dead_end_risk="none",
            interactivity_pacing_score=3, player_agency_score=3,
            findings=[], summary="ok",
        )

    result = await judge_frame(frame_path, node, llm=fake_llm)

    assert isinstance(result, PlaytestFrameJudgment)
    assert captured["images"] is not None
    assert len(captured["images"]) == 1
    assert isinstance(captured["images"][0], bytes)
    assert captured["caller"] == "playtest/judge/s1"


@pytest.mark.asyncio
async def test_judge_frame_propagates_llm_failure(frame_path, node):
    async def failing_llm(system, user, schema=None, model=None, caller=None, **kw):
        raise RuntimeError("upstream 500")

    with pytest.raises(RuntimeError, match="upstream 500"):
        await judge_frame(frame_path, node, llm=failing_llm)


@pytest.mark.asyncio
async def test_judge_frame_raises_on_non_schema_result(frame_path, node):
    async def bad_llm(system, user, schema=None, model=None, caller=None, **kw):
        return "not a schema instance"

    with pytest.raises(RuntimeError, match="non-schema result"):
        await judge_frame(frame_path, node, llm=bad_llm)


@pytest.mark.asyncio
async def test_mock_ainvoke_dispatches_playtest_judge_fixture():
    result = await mock_ainvoke(
        "system", "user", schema=PlaytestFrameJudgment, caller="playtest/judge/s1",
    )
    assert isinstance(result, PlaytestFrameJudgment)
    assert 1 <= result.ui_coherence_score <= 5
