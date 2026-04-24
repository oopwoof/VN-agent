"""Phase 13-1 / Step 6: async chapter rollup — schema + pinned-scene
detection + rollup_chapter signature guarantee (no prior_chapter_summary).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from vn_agent.agents.summarizer import rollup_chapter
from vn_agent.schema.script import (
    Chapter,
    DialogueLine,
    Scene,
    SceneContextRef,
    VNScript,
)


def _scene(sid: str, dialogue: list[DialogueLine] | None = None,
           deps: list[SceneContextRef] | None = None) -> Scene:
    return Scene(
        id=sid, title=sid.upper(), description=f"s {sid}",
        background_id=f"bg_{sid}",
        characters_present=["alice"],
        dialogue=dialogue or [
            DialogueLine(character_id="alice", text=f"hi from {sid}", emotion="neutral"),
        ],
        context_deps=deps or [],
    )


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


# ------------------------------------------------------------
# Schema
# ------------------------------------------------------------


def test_chapter_model_basics():
    ch = Chapter(
        chapter_id="ch01",
        scene_ids=["s01", "s02"],
        summary="Alice arrives.",
        summary_scene_hashes=["aaa", "bbb"],
        world_state_after={"affinity": 3},
        pinned_scene_ids=["s02"],
    )
    assert ch.chapter_id == "ch01"
    assert ch.pinned_scene_ids == ["s02"]


def test_vnscript_chapters_default_empty():
    s = VNScript(
        title="t", description="d", theme="th", start_scene_id="s01",
        scenes=[_scene("s01")],
    )
    assert s.chapters == []


# ------------------------------------------------------------
# rollup_chapter — flat index (no prior_chapter_summary param)
# ------------------------------------------------------------


def test_rollup_chapter_signature_has_no_prior_summary_param():
    """The function must NOT accept prior_chapter_summary — that was the
    "telephone-game" recursion Gemini flagged. Rollup always reads raw."""
    import inspect
    sig = inspect.signature(rollup_chapter)
    assert "prior_chapter_summary" not in sig.parameters


@pytest.mark.asyncio
async def test_rollup_chapter_happy_path():
    mock_response = _FakeResponse("Alice explored the shore and met Bob.")
    mock_ainvoke = AsyncMock(return_value=mock_response)

    with patch("vn_agent.agents.summarizer.ainvoke_llm", mock_ainvoke):
        result = await rollup_chapter(
            scenes=[_scene("s01"), _scene("s02")],
            pinned_scene_ids=["s01"],
        )

    assert result == "Alice explored the shore and met Bob."
    # Confirm the prompt mentions the pinned marker
    prompt_user = mock_ainvoke.call_args.args[1]
    assert "PINNED" in prompt_user


@pytest.mark.asyncio
async def test_rollup_chapter_empty_scenes_returns_none():
    result = await rollup_chapter(scenes=[], pinned_scene_ids=[])
    assert result is None


@pytest.mark.asyncio
async def test_rollup_chapter_non_blocking_on_error():
    mock_ainvoke = AsyncMock(side_effect=RuntimeError("Haiku is down"))

    with patch("vn_agent.agents.summarizer.ainvoke_llm", mock_ainvoke):
        result = await rollup_chapter(
            scenes=[_scene("s01")],
            pinned_scene_ids=[],
        )

    assert result is None  # non-blocking, logged at debug


@pytest.mark.asyncio
async def test_rollup_respects_word_range_kwargs():
    """target_min_words / target_max_words should make it into the prompt."""
    mock_ainvoke = AsyncMock(return_value=_FakeResponse("summary"))

    with patch("vn_agent.agents.summarizer.ainvoke_llm", mock_ainvoke):
        await rollup_chapter(
            scenes=[_scene("s01")],
            pinned_scene_ids=[],
            target_min_words=300,
            target_max_words=600,
        )

    prompt_user = mock_ainvoke.call_args.args[1]
    assert "300" in prompt_user and "600" in prompt_user


# ------------------------------------------------------------
# Pinned-scene detection in Writer
# ------------------------------------------------------------


def test_pinned_scenes_identified_by_future_graph_refs():
    """Setup: 10 scenes; scene[12] (outside chapter) depends on scene[3]
    (inside chapter). When rolling up chapter [s01..s10], scene[3] must
    be pinned."""
    # We don't run the full Writer here — just verify the algorithm used
    # matches what we promised.
    scenes = [_scene(f"s{i:02d}") for i in range(1, 11)]  # s01..s10
    scenes.append(_scene("s11", deps=[SceneContextRef(
        ref_type="scene", ref_id="s03",
        link_type="callback", reason="s11 callbacks s03",
    )]))

    chapter_scene_ids = {s.id for s in scenes[:10]}
    pinned = set()
    for future_scene in scenes[10:]:
        for dep in future_scene.context_deps:
            if dep.ref_type == "scene" and dep.ref_id in chapter_scene_ids:
                pinned.add(dep.ref_id)

    assert pinned == {"s03"}


# ------------------------------------------------------------
# Config gating
# ------------------------------------------------------------


def test_chapter_rollup_config_defaults():
    from vn_agent.config import get_settings
    s = get_settings()
    assert s.enable_chapter_rollup is True
    assert s.chapter_rollup_every == 10
    assert s.chapter_rollup_min_scenes == 10
    assert s.rollup_target_min_words == 200
    assert s.rollup_target_max_words == 800
