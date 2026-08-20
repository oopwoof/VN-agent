"""Tests for the VN_MOCK_SYNTH scene-count-aware mock synthesizer.

The 50-scene dry run needs mock mode to produce a *real* 50-scene plan —
the hand-written fixtures are 4 scenes (EN) / 3 (CN) and carry none of the
long-form fields (world_variables, scene_brief, context_deps, state I/O),
so every ≥10-scene gate stays closed and the dry run validates nothing.

The synthesizer is gated on the VN_MOCK_SYNTH env var, NOT on requested
scene count: the default pipeline already requests max_scenes=10 (above
fixture size) through the real dispatch, so count-triggered synthesis
would silently change existing tests' output. Gate off ⇒ byte-identical
fixtures for every caller.
"""
import json

import pytest

from vn_agent.services.mock_llm import DIRECTOR_STEP1, mock_ainvoke


def _step1_prompt(n_scenes: int, n_chars: int = 3) -> str:
    """Mirror of director._step1_outline's large-model user prompt markers."""
    return (
        "Create a visual novel story outline for this theme:\n\n"
        "Theme: a lighthouse keeper's last winter\n\n"
        "Requirements:\n"
        f"- Up to {n_scenes} scenes total\n"
        f"- {n_chars} characters\n"
        "- Clear emotional arc: beginning, middle, end\n\n"
        "Return ONLY this JSON (no branches, no music yet):"
    )


def _step2_prompt(scene_ids: list[str], start_id: str) -> str:
    """Mirror of director._step2_details's scene-id-list marker."""
    return (
        "You have this scene list:\n(elided)\n\n"
        f"All valid scene IDs: {json.dumps(scene_ids)}\n"
        f"Start scene: {start_id}\n"
    )


def _writer_prompt(scene_id: str, cast: list[str]) -> str:
    """Mirror of writer._write_scene's user prompt markers."""
    return (
        "Write dialogue for this scene:\n\n"
        f"Scene ID: {scene_id}\n"
        f"Title: Waypoint {scene_id}\n"
        "Description: mock\n\n"
        f"Characters present: {', '.join(cast)}\n"
        "Music mood: peaceful\n"
    )


class TestSynthGateOff:
    """With VN_MOCK_SYNTH unset, output is byte-identical to the fixtures —
    this is the regression pin that protects the 971-test baseline."""

    @pytest.mark.asyncio
    async def test_step1_at_50_scenes_returns_fixture_verbatim(self, monkeypatch):
        monkeypatch.delenv("VN_MOCK_SYNTH", raising=False)
        r = await mock_ainvoke(
            "You are a director", _step1_prompt(50), caller="director/step1",
        )
        assert r.content == DIRECTOR_STEP1

    @pytest.mark.asyncio
    async def test_writer_unknown_scene_returns_first_fixture_scene(self, monkeypatch):
        monkeypatch.delenv("VN_MOCK_SYNTH", raising=False)
        from vn_agent.services.mock_llm import _WRITER_SCENE_MAP

        r = await mock_ainvoke(
            "You write dialogue", _writer_prompt("s07", ["char_a"]), caller="writer/s07",
        )
        assert r.content == next(iter(_WRITER_SCENE_MAP.values()))


class TestSynthStep1Step2:
    @pytest.mark.asyncio
    async def test_50_scene_plan_round_trips_clean_through_director(self, monkeypatch):
        """The synthetic plan must survive every deterministic gate that
        would otherwise throw the run into director-redo loops."""
        monkeypatch.setenv("VN_MOCK_SYNTH", "1")
        from vn_agent.agents.director import (
            _build_from_plan,
            _extract_json,
            _merge_outline_details,
            _validate_branch_structure,
        )
        from vn_agent.agents.reviewer import (
            _structural_check,
            _validate_value_against_type,
        )
        from vn_agent.agents.structure_reviewer import _local_structural_audit

        r1 = await mock_ainvoke(
            "You are a director", _step1_prompt(50), caller="director/step1",
        )
        outline = _extract_json(r1.content)
        assert len(outline["scenes"]) == 50
        scene_ids = [s["id"] for s in outline["scenes"]]
        assert len(set(scene_ids)) == 50

        r2 = await mock_ainvoke(
            "You are a director. Add navigation",
            _step2_prompt(scene_ids, outline["start_scene_id"]),
            caller="director/step2",
        )
        details = _extract_json(r2.content)
        plan = _merge_outline_details(outline, details)
        script, characters = _build_from_plan(plan, "test theme")

        assert len(script.scenes) == 50
        # Director-layer branch validation: no degraded branches
        assert _validate_branch_structure(script) == []
        # StructureReviewer deterministic audit: nothing retry-worthy
        retry_findings = [
            f for f in _local_structural_audit(script, characters)
            if f.requires_retry
        ]
        assert retry_findings == []
        # Reviewer structural check: reachable, valid refs
        assert _structural_check(script).passed
        # State I/O is typed-correct against declarations
        declared = {v.name: v for v in script.world_variables}
        for s in script.scenes:
            for var, val in s.state_writes.items():
                assert var in declared
                assert _validate_value_against_type(declared[var], val) is None
            for var in s.state_reads:
                assert var in declared

    @pytest.mark.asyncio
    async def test_synth_plan_populates_every_longform_field(self, monkeypatch):
        monkeypatch.setenv("VN_MOCK_SYNTH", "1")
        from vn_agent.agents.director import (
            _build_from_plan, _extract_json, _merge_outline_details,
        )

        r1 = await mock_ainvoke(
            "You are a director", _step1_prompt(20), caller="director/step1",
        )
        outline = _extract_json(r1.content)
        scene_ids = [s["id"] for s in outline["scenes"]]
        r2 = await mock_ainvoke(
            "You are a director. Add navigation",
            _step2_prompt(scene_ids, outline["start_scene_id"]),
            caller="director/step2",
        )
        plan = _merge_outline_details(outline, _extract_json(r2.content))
        script, characters = _build_from_plan(plan, "test theme")

        assert script.world_variables, "world_variables missing — state layer stays no-op"
        assert script.macro_reference is not None
        assert all(s.scene_brief is not None for s in script.scenes)
        assert any(s.context_deps for s in script.scenes)
        assert any(len(s.branches) >= 2 for s in script.scenes)
        # every declared character is used (roster_unused would retry)
        used = {cid for s in script.scenes for cid in s.characters_present}
        assert used == set(characters.keys())

    @pytest.mark.asyncio
    async def test_step2_validates_as_tool_use_schema(self, monkeypatch):
        monkeypatch.setenv("VN_MOCK_SYNTH", "1")
        from vn_agent.schema.script import DirectorStep2Output

        ids = [f"s{i + 1:02d}" for i in range(12)]
        r = await mock_ainvoke(
            "You are a director. Add navigation",
            _step2_prompt(ids, "s01"),
            schema=DirectorStep2Output,
            caller="director/step2",
        )
        assert isinstance(r, DirectorStep2Output)
        assert [s.id for s in r.scenes] == ids

    @pytest.mark.asyncio
    async def test_waves_are_wider_than_one(self, monkeypatch):
        """context_deps must form a DAG whose topological waves actually
        parallelize — otherwise writer_max_concurrent>1 is untestable."""
        monkeypatch.setenv("VN_MOCK_SYNTH", "1")
        from vn_agent.agents.director import (
            _build_from_plan, _extract_json, _merge_outline_details,
        )
        from vn_agent.agents.writer_orchestrator import compute_waves

        r1 = await mock_ainvoke(
            "You are a director", _step1_prompt(20), caller="director/step1",
        )
        outline = _extract_json(r1.content)
        scene_ids = [s["id"] for s in outline["scenes"]]
        r2 = await mock_ainvoke(
            "You are a director. Add navigation",
            _step2_prompt(scene_ids, outline["start_scene_id"]),
            caller="director/step2",
        )
        plan = _merge_outline_details(outline, _extract_json(r2.content))
        script, _ = _build_from_plan(plan, "test theme")

        waves = compute_waves(list(script.scenes))
        assert len(waves) >= 2, "everything in one wave — deps didn't register"
        assert max(len(w) for w in waves) >= 5, "waves too narrow to parallelize"


class TestSynthWriter:
    @pytest.mark.asyncio
    async def test_writer_synthesizes_valid_distinct_dialogue(self, monkeypatch):
        monkeypatch.setenv("VN_MOCK_SYNTH", "1")
        from vn_agent.schema.emotions import VALID_EMOTIONS_SET

        cast = ["char_asha", "char_bren"]
        r_a = await mock_ainvoke(
            "You write dialogue", _writer_prompt("s07", cast), caller="writer/s07",
        )
        r_b = await mock_ainvoke(
            "You write dialogue", _writer_prompt("s08", cast), caller="writer/s08",
        )
        lines_a = json.loads(r_a.content)
        lines_b = json.loads(r_b.content)
        # clears min_dialogue_lines=5 with margin, well under any max
        assert 7 <= len(lines_a) <= 9
        # speakers ⊆ cast (reviewer mechanical check rejects strangers)
        assert {ln["character_id"] for ln in lines_a} - {None} <= set(cast)
        assert all(ln["emotion"] in VALID_EMOTIONS_SET for ln in lines_a)
        # distinct dialogue across scenes — the dry run asserts this globally
        assert [ln["text"] for ln in lines_a] != [ln["text"] for ln in lines_b]

    @pytest.mark.asyncio
    async def test_writer_fixture_scenes_still_use_fixtures_with_gate_on(self, monkeypatch):
        monkeypatch.setenv("VN_MOCK_SYNTH", "1")
        from vn_agent.services.mock_llm import _WRITER_SCENE_MAP

        r = await mock_ainvoke(
            "You write dialogue",
            _writer_prompt("ch1_arrival", ["char_mara"]),
            caller="writer/ch1_arrival",
        )
        assert r.content == _WRITER_SCENE_MAP["ch1_arrival"]


class TestSynthThinkingAndSummaries:
    @pytest.mark.asyncio
    async def test_thinking_derives_callback_plan_from_context_deps(self, monkeypatch):
        monkeypatch.setenv("VN_MOCK_SYNTH", "1")
        from vn_agent.agents.thinking import THINKING_SYSTEM
        from vn_agent.schema.script import SceneThinking

        prompt = (
            "## Scene being planned: s09 — Waypoint 09\n"
            "Characters present: ['char_asha', 'char_bren']\n\n"
            "## Director-declared context_deps (backward refs):\n"
            "  - callback → scene:s01 (echo the opening)\n"
            "  - arc_beat → scene:s05 (block anchor)\n"
        )
        r = await mock_ainvoke(THINKING_SYSTEM, prompt, caller="thinking/s09")
        thinking = SceneThinking.model_validate(json.loads(r.content))
        assert thinking.writing_intent
        assert {c.ref_scene_id for c in thinking.callback_plan} == {"s01", "s05"}

    @pytest.mark.asyncio
    async def test_scene_summaries_are_distinct_per_scene(self, monkeypatch):
        monkeypatch.setenv("VN_MOCK_SYNTH", "1")
        r1 = await mock_ainvoke("You are a scene summarizer", "Scene id: s01", caller="summarizer/s01")
        r2 = await mock_ainvoke("You are a scene summarizer", "Scene id: s02", caller="summarizer/s02")
        assert r1.content != r2.content
        assert "s01" in r1.content
