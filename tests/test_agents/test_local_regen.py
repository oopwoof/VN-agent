"""Phase 13-1 / Step 2: local_regen must hard-truncate downstream state.

Covers:
- state_timeline splice replaces idx's entry with new state
- state_timeline[idx+1:] is HARD-DELETED (not warned-and-kept) to prevent
  polluted post-splice state from poisoning Writer context on next run
- chapters whose scene_ids extend past idx are also dropped
- kept prefix (timeline[:idx]) remains untouched
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from vn_agent.agents.local_regen import regenerate_scene
from vn_agent.schema.script import (
    DialogueLine,
    Scene,
    StateTimelineEntry,
    VNScript,
    WorldVariable,
)


def _make_scene(sid: str, state_writes: dict | None = None) -> Scene:
    return Scene(
        id=sid,
        title=sid.upper(),
        description=f"scene {sid}",
        background_id="bg_default",
        characters_present=["alice"],
        dialogue=[DialogueLine(character_id="alice", text=f"hi from {sid}", emotion="neutral")],
        state_writes=state_writes or {},
    )


def _make_script(scene_ids: list[str], with_timeline: bool = True) -> VNScript:
    scenes = [
        _make_scene(sid, state_writes={"affinity": i * 10})
        for i, sid in enumerate(scene_ids)
    ]
    timeline = []
    if with_timeline:
        running = 0
        for sid in scene_ids:
            running += 10
            timeline.append(StateTimelineEntry(
                scene_id=sid, state_after={"affinity": running},
            ))
    return VNScript(
        title="Test",
        description="desc",
        theme="theme",
        start_scene_id=scene_ids[0],
        scenes=scenes,
        characters=["alice"],
        world_variables=[
            WorldVariable(
                name="affinity", type="int", initial_value=0,
                description="alice affinity",
            ),
        ],
        state_timeline=timeline,
    )


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    """Writes a fresh vn_script.json + characters.json into tmp_path."""
    script = _make_script(["s01", "s02", "s03", "s04", "s05"])
    (tmp_path / "vn_script.json").write_text(
        script.model_dump_json(indent=2), encoding="utf-8",
    )
    (tmp_path / "characters.json").write_text(
        json.dumps({
            "alice": {
                "id": "alice", "name": "Alice", "role": "main",
                "personality": "kind", "background": "village girl",
            },
        }),
        encoding="utf-8",
    )
    return tmp_path


def _fake_write_scene(target_scene: Scene) -> AsyncMock:
    """Return a mock _write_scene that returns the target scene unchanged
    except for an updated state_writes value (to trigger state_timeline mutation)."""
    async def _runner(*args, **kwargs):
        scene = args[0]  # first positional arg is target scene
        return scene.model_copy(update={
            "dialogue": [DialogueLine(character_id="alice", text="regenerated line", emotion="happy")],
            "state_writes": {"affinity": 99},  # differs from original state_writes
        })
    return AsyncMock(side_effect=_runner)


@pytest.mark.asyncio
async def test_timeline_hard_truncated_on_splice(tmp_output: Path):
    """Regenerating scene at idx=2 must drop timeline[3:] and keep timeline[:2]."""
    target_scene = _make_scene("s03")
    mock_writer = _fake_write_scene(target_scene)

    with patch("vn_agent.agents.local_regen._write_scene", mock_writer), \
         patch("vn_agent.agents.local_regen._write_scene_snapshot"):
        await regenerate_scene(tmp_output, scene_id="s03")

    # Reload from disk
    saved = VNScript.model_validate_json(
        (tmp_output / "vn_script.json").read_text(encoding="utf-8")
    )
    # idx=2 (s03) present; anything past it dropped.
    assert len(saved.state_timeline) == 3  # s01, s02, s03
    assert [e.scene_id for e in saved.state_timeline] == ["s01", "s02", "s03"]
    # idx=2's state_after reflects new state_writes (affinity=99, not the
    # original affinity=30)
    assert saved.state_timeline[2].state_after == {"affinity": 99}


@pytest.mark.asyncio
async def test_timeline_preserves_prefix(tmp_output: Path):
    """Timeline[:idx] must not be touched."""
    mock_writer = _fake_write_scene(_make_scene("s03"))

    with patch("vn_agent.agents.local_regen._write_scene", mock_writer), \
         patch("vn_agent.agents.local_regen._write_scene_snapshot"):
        await regenerate_scene(tmp_output, scene_id="s03")

    saved = VNScript.model_validate_json(
        (tmp_output / "vn_script.json").read_text(encoding="utf-8")
    )
    # s01 and s02 entries unchanged (from fixture: affinity 10, 20)
    assert saved.state_timeline[0].state_after == {"affinity": 10}
    assert saved.state_timeline[1].state_after == {"affinity": 20}


@pytest.mark.asyncio
async def test_missing_scene_id_raises(tmp_output: Path):
    from vn_agent.agents.local_regen import RegenError
    with pytest.raises(RegenError):
        await regenerate_scene(tmp_output, scene_id="nonexistent")


def test_state_timeline_entry_schema():
    """StateTimelineEntry basic validation."""
    e = StateTimelineEntry(scene_id="s01", state_after={"x": 1, "y": "foo"})
    assert e.scene_id == "s01"
    assert e.state_after == {"x": 1, "y": "foo"}
    # Default state_after = {}
    e2 = StateTimelineEntry(scene_id="s02")
    assert e2.state_after == {}


def test_vnscript_state_timeline_default_empty():
    """VNScript.state_timeline defaults to []."""
    s = VNScript(
        title="t", description="d", theme="th", start_scene_id="s01",
        scenes=[_make_scene("s01")],
    )
    assert s.state_timeline == []
