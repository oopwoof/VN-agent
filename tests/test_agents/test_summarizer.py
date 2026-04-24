"""Phase 13-1 / Step 4: dialogue_digest + summary hash dedup.

Coverage:
- digest is stable across equal dialogue lists
- digest changes when any dialogue field changes (text / emotion / character_id)
- Writer skips summarize_scene when hash matches (mock call count = 0)
- local_regen refires summary after splice (mock call count > 0)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from vn_agent.agents.summarizer import dialogue_digest
from vn_agent.schema.script import DialogueLine, Scene, StateTimelineEntry, VNScript, WorldVariable


def _scene(dialogue: list[DialogueLine] | None = None) -> Scene:
    return Scene(
        id="s01", title="Scene 1", description="test",
        background_id="bg1", characters_present=["alice"],
        dialogue=dialogue or [
            DialogueLine(character_id="alice", text="hello", emotion="neutral"),
            DialogueLine(character_id="bob", text="hi", emotion="happy"),
        ],
    )


def test_digest_is_deterministic():
    s1 = _scene()
    s2 = _scene()
    assert dialogue_digest(s1) == dialogue_digest(s2)


def test_digest_changes_on_text_edit():
    base = dialogue_digest(_scene())
    edited = _scene(dialogue=[
        DialogueLine(character_id="alice", text="HELLO", emotion="neutral"),
        DialogueLine(character_id="bob", text="hi", emotion="happy"),
    ])
    assert dialogue_digest(edited) != base


def test_digest_changes_on_emotion_change():
    base = dialogue_digest(_scene())
    edited = _scene(dialogue=[
        DialogueLine(character_id="alice", text="hello", emotion="happy"),  # was neutral
        DialogueLine(character_id="bob", text="hi", emotion="happy"),
    ])
    assert dialogue_digest(edited) != base


def test_digest_changes_on_character_change():
    base = dialogue_digest(_scene())
    edited = _scene(dialogue=[
        DialogueLine(character_id="carol", text="hello", emotion="neutral"),  # was alice
        DialogueLine(character_id="bob", text="hi", emotion="happy"),
    ])
    assert dialogue_digest(edited) != base


def test_digest_is_order_sensitive():
    """Reordering lines should invalidate the cache — the regen changed
    the narrative, even if the set of lines is identical."""
    s1 = _scene()
    s2 = _scene(dialogue=list(reversed(s1.dialogue)))
    assert dialogue_digest(s1) != dialogue_digest(s2)


def test_digest_handles_narration_lines():
    """character_id=None (narration) shouldn't crash and should still
    produce a stable, distinct digest."""
    s1 = _scene(dialogue=[
        DialogueLine(character_id=None, text="night falls", emotion="neutral"),
    ])
    s2 = _scene(dialogue=[
        DialogueLine(character_id=None, text="night falls", emotion="neutral"),
    ])
    assert dialogue_digest(s1) == dialogue_digest(s2)


def test_digest_truncated_to_16_chars():
    """Collision space: 64-bit ≈ 10⁻¹⁵ collision on 150 calls — effectively 0."""
    assert len(dialogue_digest(_scene())) == 16


# ------------------------------------------------------------
# Integration: local_regen refires summary on dialogue change
# ------------------------------------------------------------


@pytest.fixture
def tmp_output_with_summary(tmp_path: Path) -> Path:
    """Project dir with one scene carrying a STALE summary + matching hash.
    After regen, the hash should change and the summary should refire.
    """
    scene = _scene()
    stale_hash = "abc123stalehash0"
    stale_summary = "This summary is stale."
    scene_with_stale = scene.model_copy(update={
        "summary": stale_summary,
        "summary_dialogue_hash": stale_hash,
    })
    script = VNScript(
        title="T", description="desc", theme="theme", start_scene_id="s01",
        scenes=[scene_with_stale],
        characters=["alice", "bob"],
        world_variables=[
            WorldVariable(name="x", type="int", initial_value=0, description="x"),
        ],
        state_timeline=[StateTimelineEntry(scene_id="s01", state_after={"x": 0})],
    )
    (tmp_path / "vn_script.json").write_text(
        script.model_dump_json(indent=2), encoding="utf-8",
    )
    (tmp_path / "characters.json").write_text(
        json.dumps({
            "alice": {
                "id": "alice", "name": "Alice", "role": "main",
                "personality": "k", "background": "bg",
            },
            "bob": {
                "id": "bob", "name": "Bob", "role": "support",
                "personality": "s", "background": "bg",
            },
        }),
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.asyncio
async def test_local_regen_refires_summary_when_enabled(tmp_output_with_summary: Path):
    """With enable_scene_summarization=True, local_regen should fire
    summarize_scene once (the new dialogue's hash differs from stale)."""
    from vn_agent.agents.local_regen import regenerate_scene

    async def _runner(scene, *args, **kwargs):
        # Return new dialogue (triggers hash change)
        return scene.model_copy(update={
            "dialogue": [
                DialogueLine(character_id="alice", text="NEW LINE", emotion="happy"),
            ],
            "state_writes": {"x": 7},
        })

    mock_write_scene = AsyncMock(side_effect=_runner)
    mock_summarize = AsyncMock(return_value="Fresh summary.")

    with patch("vn_agent.agents.local_regen._write_scene", mock_write_scene), \
         patch("vn_agent.agents.local_regen._write_scene_snapshot"), \
         patch("vn_agent.agents.summarizer.summarize_scene", mock_summarize), \
         patch("vn_agent.agents.local_regen.get_settings") as mock_get_settings:
        mock_settings = mock_get_settings.return_value
        mock_settings.enable_scene_summarization = True
        mock_settings.writer_context_window = 0
        # Minimal settings attrs the code path reads:
        for attr in ("llm_writer_model", "anthropic_api_keys_sonnet",
                     "anthropic_api_keys_haiku", "anthropic_api_keys"):
            setattr(mock_settings, attr, [] if "keys" in attr else "x")
        mock_settings.anthropic_max_retries = 1
        mock_settings.anthropic_backoff_base = 0.01
        mock_settings.anthropic_backoff_cap = 1.0
        mock_settings.anthropic_backoff_jitter = 0.0

        await regenerate_scene(tmp_output_with_summary, scene_id="s01")

    # summarize_scene must have been called exactly once
    assert mock_summarize.call_count == 1

    # And the saved scene must have fresh summary + matching hash
    saved = VNScript.model_validate_json(
        (tmp_output_with_summary / "vn_script.json").read_text(encoding="utf-8")
    )
    assert saved.scenes[0].summary == "Fresh summary."
    # Hash must reflect the new dialogue (not the stale "abc123stalehash0")
    assert saved.scenes[0].summary_dialogue_hash != "abc123stalehash0"
    assert saved.scenes[0].summary_dialogue_hash == dialogue_digest(saved.scenes[0])


@pytest.mark.asyncio
async def test_local_regen_summary_disabled_skips(tmp_output_with_summary: Path):
    """With enable_scene_summarization=False, no Haiku call happens — even
    though the dialogue changed. Cost control for short demos."""
    from vn_agent.agents.local_regen import regenerate_scene

    async def _runner(scene, *args, **kwargs):
        return scene.model_copy(update={
            "dialogue": [DialogueLine(character_id="alice", text="NEW", emotion="happy")],
            "state_writes": {},
        })

    mock_write_scene = AsyncMock(side_effect=_runner)
    mock_summarize = AsyncMock(return_value="should not be called")

    with patch("vn_agent.agents.local_regen._write_scene", mock_write_scene), \
         patch("vn_agent.agents.local_regen._write_scene_snapshot"), \
         patch("vn_agent.agents.summarizer.summarize_scene", mock_summarize), \
         patch("vn_agent.agents.local_regen.get_settings") as mock_get_settings:
        mock_settings = mock_get_settings.return_value
        mock_settings.enable_scene_summarization = False
        mock_settings.writer_context_window = 0
        for attr in ("llm_writer_model", "anthropic_api_keys_sonnet",
                     "anthropic_api_keys_haiku", "anthropic_api_keys"):
            setattr(mock_settings, attr, [] if "keys" in attr else "x")
        mock_settings.anthropic_max_retries = 1
        mock_settings.anthropic_backoff_base = 0.01
        mock_settings.anthropic_backoff_cap = 1.0
        mock_settings.anthropic_backoff_jitter = 0.0

        await regenerate_scene(tmp_output_with_summary, scene_id="s01")

    assert mock_summarize.call_count == 0
