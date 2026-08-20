"""12-scene mock integration: the long-form machinery actually engages.

Until the 50-scene dry run round, no test ran the full graph above the
≥10-scene gates — chapter rollup, thinking fanout, cross-ref sync, and the
parallel writer had unit tests but had never executed together. This test
crosses every gate at once (12 scenes: small enough for the suite, big
enough for one rollup and two shared-callback collisions) using the
VN_MOCK_SYNTH synthesizer, with no LLM patching at all: the suite-wide
mock floor (tests/conftest.py) forces mock_mode_var, so every agent's
ainvoke_llm — including structure_reviewer's function-local-import path
that once leaked real API calls — routes through the real dispatch gate.

The 50-scene tier lives in scripts/smoke_longvn.py --mock, not here.
"""
from __future__ import annotations

import json

import pytest

from vn_agent import config as config_module
from vn_agent.agents.graph import build_graph
from vn_agent.agents.state import initial_state
from vn_agent.config import Settings


@pytest.fixture
def _longform_settings():
    """Everything the long-form path needs, ON — the validator requires
    thinking fanout + consume before it allows writer_max_concurrent>1."""
    override = Settings(
        enable_thinking_fanout=True,
        writer_consume_thinking=True,
        enable_cross_ref_sync=True,
        writer_max_concurrent=5,
        enable_scene_summarization=True,
        summarization_min_scenes=10,
        use_lore_retrieval=False,  # keep SBERT out of this test — speed
    )
    token = config_module._settings_override.set(override)
    yield override
    config_module._settings_override.reset(token)


@pytest.mark.asyncio
async def test_longform_mock_pipeline_12_scenes(tmp_path, monkeypatch, _longform_settings):
    monkeypatch.setenv("VN_MOCK_SYNTH", "1")

    graph = build_graph()
    state = initial_state(
        theme="a lighthouse keeper's last winter",
        output_dir=str(tmp_path),
        text_only=True,
        max_scenes=12,
        num_characters=3,
    )
    final_state = await graph.ainvoke(state)

    script = final_state["vn_script"]
    assert script is not None
    assert len(script.scenes) == 12
    assert final_state.get("review_passed") is True

    # ── symbolic state layer: one timeline row per scene ──
    assert len(script.state_timeline) == 12
    assert script.world_variables, "synth world_variables should reach the script"

    # ── chapter rollup: 12 scenes cross the every-10 boundary once ──
    assert len(script.chapters) >= 1
    for ch in script.chapters:
        assert ch.summary, f"chapter {ch.chapter_id} has no rollup summary"
        try:
            parsed = json.loads(ch.summary)
        except json.JSONDecodeError:
            parsed = None
        assert not isinstance(parsed, list), (
            "Chapter.summary is a dialogue JSON array — the pre-P0 rollup "
            "misroute is back"
        )

    # ── thinking fanout: every scene got a non-vacuous plan ──
    vacuous = [s.id for s in script.scenes
               if s.thinking is None or not s.thinking.writing_intent]
    assert vacuous == [], f"vacuous thinking on {vacuous}"

    # ── dialogue: written, and pairwise distinct across scenes ──
    first_lines = [s.dialogue[0].text for s in script.scenes if s.dialogue]
    assert len(first_lines) == 12
    assert len(set(first_lines)) == 12, "identical dialogue across scenes"

    # ── scene summaries: populated (summarization gate crossed) ──
    missing_summaries = [s.id for s in script.scenes if not s.summary]
    assert missing_summaries == []

    # ── cross-ref sync: shared s01 callbacks collided and were resolved ──
    conflicts_file = tmp_path / "cross_ref_conflicts.jsonl"
    assert conflicts_file.exists(), (
        "no cross_ref_conflicts.jsonl — shared context_deps never collided, "
        "so cross_ref_sync validated nothing"
    )

    # ── the persisted artifact must match the in-memory result ──
    # The per-scene flushes never carry chapters (final rollups land after
    # the last scene's flush), so without a final checkpoint the on-disk
    # vn_script.json permanently lacks them — the first 50-scene dry run's
    # disk artifact had chapters: [] while run_metrics counted 5.
    on_disk = json.loads(
        (tmp_path / "vn_script.json").read_text(encoding="utf-8")
    )
    assert len(on_disk["chapters"]) == len(script.chapters), (
        "final vn_script.json lacks the chapter rollups the graph returned"
    )
    assert len(on_disk["state_timeline"]) == 12
