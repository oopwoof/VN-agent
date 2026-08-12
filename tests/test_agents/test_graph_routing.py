"""Phase 13-2 Step 4e: graph.py conditional edge after structure_reviewer.

Tests _after_structure_review's routing decisions and ensures the new
director_step2_redo / director_full_redo nodes are wired and increment
director_revision_count correctly.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from vn_agent.agents.graph import _after_structure_review
from vn_agent.schema.script import StructureFinding


def _f(category, *, source="deterministic", requires_retry=True):
    return StructureFinding(
        category=category,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        message=f"test {category}",
        requires_retry=requires_retry,
    )


def _settings_stub(max_revisions: int = 2):
    class _S:
        max_director_revisions = max_revisions
    return _S()


# ---------------------------------------------------------------------------
# _after_structure_review (the conditional edge function)
# ---------------------------------------------------------------------------


class TestAfterStructureReview:
    def test_no_findings_routes_to_accept(self):
        state = {
            "structure_review_findings": [],
            "director_revision_count": 0,
        }
        with patch("vn_agent.agents.graph.get_settings", return_value=_settings_stub()):
            assert _after_structure_review(state) == "accept"

    def test_only_advisory_findings_routes_to_accept(self):
        state = {
            "structure_review_findings": [
                _f("advisory", requires_retry=False),
            ],
            "director_revision_count": 0,
        }
        with patch("vn_agent.agents.graph.get_settings", return_value=_settings_stub()):
            assert _after_structure_review(state) == "accept"

    def test_step2_class_findings_route_to_step2_only(self):
        state = {
            "structure_review_findings": [
                _f("branch_target_invalid"),
                _f("branch_intent_misalign", source="llm"),
            ],
            "director_revision_count": 0,
        }
        with patch("vn_agent.agents.graph.get_settings", return_value=_settings_stub()):
            assert _after_structure_review(state) == "step2_only"

    def test_step1_class_findings_route_to_step1_step2(self):
        """roster_unused triggers step1+step2 escalation immediately
        per Gemini design review #c."""
        state = {
            "structure_review_findings": [
                _f("roster_unused"),
            ],
            "director_revision_count": 0,
        }
        with patch("vn_agent.agents.graph.get_settings", return_value=_settings_stub()):
            assert _after_structure_review(state) == "step1_step2"

    def test_max_revisions_hit_routes_to_accept(self):
        """Even with actionable findings, budget exhausted → accept."""
        state = {
            "structure_review_findings": [_f("roster_unused")],
            "director_revision_count": 2,  # at the cap
        }
        with patch(
            "vn_agent.agents.graph.get_settings",
            return_value=_settings_stub(max_revisions=2),
        ):
            assert _after_structure_review(state) == "accept"

    def test_round_1_only_llm_findings_routes_to_accept(self):
        """Tier-2 LLM cap from routing.decide_retry_target."""
        state = {
            "structure_review_findings": [
                _f("branch_intent_misalign", source="llm"),
            ],
            "director_revision_count": 1,
        }
        with patch("vn_agent.agents.graph.get_settings", return_value=_settings_stub()):
            assert _after_structure_review(state) == "accept"

    def test_missing_findings_field_treated_as_empty(self):
        """Defensive: state without structure_review_findings shouldn't crash."""
        state = {"director_revision_count": 0}
        with patch("vn_agent.agents.graph.get_settings", return_value=_settings_stub()):
            assert _after_structure_review(state) == "accept"


# ---------------------------------------------------------------------------
# Graph topology — verify the new nodes + edges were added
# ---------------------------------------------------------------------------


class TestGraphTopology:
    def test_redo_nodes_exist_in_compiled_graph(self):
        """director_step2_redo + director_full_redo must be registered."""
        from vn_agent.agents.graph import build_graph
        compiled = build_graph()
        # LangGraph compiled graphs expose nodes via .nodes (mapping)
        node_names = set(compiled.nodes.keys())
        assert "director_step2_redo" in node_names
        assert "director_full_redo" in node_names
        # Original nodes still present
        assert "director" in node_names
        assert "structure_reviewer" in node_names
        assert "state_orchestrator" in node_names


# ---------------------------------------------------------------------------
# Director redo nodes — increment revision count + return correct shape
# ---------------------------------------------------------------------------


class TestDirectorRedoNodes:

    @pytest.mark.asyncio
    async def test_step2_redo_increments_revision_count_on_no_script(self):
        """Defensive: missing vn_script → log + bump count, no crash."""
        from vn_agent.agents.director import run_director_step2_redo
        result = await run_director_step2_redo({
            "theme": "x", "output_dir": ".",
            "director_revision_count": 0,
        })
        assert result == {"director_revision_count": 1}

    def test_format_retry_feedback_drops_advisory_findings(self):
        from vn_agent.agents.director import _format_retry_feedback
        findings = [
            _f("roster_unused"),
            _f("advisory", requires_retry=False),
        ]
        feedback = _format_retry_feedback(findings)
        assert "roster_unused" in feedback
        assert "advisory" not in feedback
        assert "RETRY FEEDBACK" in feedback

    def test_format_retry_feedback_empty_when_no_actionable(self):
        from vn_agent.agents.director import _format_retry_feedback
        findings = [_f("advisory", requires_retry=False)]
        assert _format_retry_feedback(findings) == ""

    def test_format_retry_feedback_groups_by_category(self):
        from vn_agent.agents.director import _format_retry_feedback
        findings = [
            _f("branch_intent_misalign", source="llm"),
            _f("branch_intent_misalign", source="llm"),
            _f("roster_unused"),
        ]
        feedback = _format_retry_feedback(findings)
        # Each category appears once as a section header
        assert feedback.count("### branch_intent_misalign") == 1
        assert feedback.count("### roster_unused") == 1
        # 2 findings under branch_intent_misalign, 1 under roster_unused
        assert "(2 findings)" in feedback
        assert "(1 finding)" in feedback

    def test_outline_dict_from_script_round_trip(self):
        """The outline dict reconstructed from a script must contain the
        fields _step2_details consumes. Smoke-level shape check."""
        from vn_agent.agents.director import _outline_dict_from_script
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import Scene, VNScript, WorldVariable
        scenes = [
            Scene(id="s0", title="S0", description="d", background_id="bg",
                  characters_present=["alice"]),
        ]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes,
            world_variables=[
                WorldVariable(name="trust", type="int", initial_value=0,
                              description="x"),
            ],
        )
        chars = {"alice": CharacterProfile(
            id="alice", name="A", role="p",
            personality="kind", background="bg",
        )}
        outline = _outline_dict_from_script(script, chars, "anime")
        assert outline["title"] == "T"
        assert outline["start_scene_id"] == "s0"
        assert outline["art_direction"] == "anime"
        assert len(outline["scenes"]) == 1
        assert outline["scenes"][0]["id"] == "s0"
        assert outline["characters"][0]["id"] == "alice"
        assert outline["world_variables"][0]["name"] == "trust"


# ---------------------------------------------------------------------------
# Phase 13-2 Step 4e/4 (Gemini hardening): end-to-end retry lifecycle test.
# Walks the full state machine via the routing helper, asserting we hit
# step1_step2 -> step2_only -> accept across 3 rounds with appropriate
# findings each time.
# ---------------------------------------------------------------------------


class TestEndToEndRetryLifecycle:
    """Pin the routing decisions across a realistic 3-round retry sequence.

    Round 0: structure_reviewer surfaces a step1-class finding
             (roster_unused) -> route to step1_step2
    Round 1: structure_reviewer surfaces a step2-class finding only
             (branch_intent_misalign, LLM source) -> route to step2_only
    Round 2: structure_reviewer surfaces only LLM-judged findings ->
             tier-2 cap accepts (LLM signal didn't help, rolling dice
             on round 2 is wasteful)
    """

    def test_lifecycle_routing_sequence(self):
        """Walk a representative 3-round retry: deterministic step1-class
        finding → step1_step2 escalation; deterministic step2-class
        finding remains → step2_only retry; only LLM findings left →
        tier-2 cap accepts."""
        from vn_agent.agents.routing import decide_retry_target
        max_rev = 2

        # Round 0: roster_unused (deterministic, step1-class)
        round0 = [_f("roster_unused")]
        d0 = decide_retry_target(round0, revision_count=0, max_revisions=max_rev)
        assert d0.target == "step1_step2", (
            f"Round 0 with roster_unused must escalate to step1_step2; "
            f"got {d0.target} ({d0.reason})"
        )

        # Round 1: roster_unused fixed; a step2-class deterministic
        # finding was uncovered (e.g. branch_target_invalid that wasn't
        # caught the first time). Deterministic findings get the full
        # max_revisions budget.
        round1 = [_f("branch_target_invalid", source="deterministic")]
        d1 = decide_retry_target(round1, revision_count=1, max_revisions=max_rev)
        assert d1.target == "step2_only", (
            f"Round 1 with deterministic step2-class finding must retry "
            f"step2_only; got {d1.target} ({d1.reason})"
        )

        # Round 2: budget exhausted -> accept regardless of findings.
        round2 = [_f("branch_target_invalid", source="deterministic")]
        d2 = decide_retry_target(round2, revision_count=2, max_revisions=max_rev)
        assert d2.target == "accept", (
            f"Round 2 must accept (max_revisions hit); "
            f"got {d2.target} ({d2.reason})"
        )

    def test_lifecycle_llm_only_round1_hits_tier2_cap(self):
        """Tier-2 cap regression: round 0 retries on LLM-only findings,
        round 1 accepts because Sonnet-on-Sonnet didn't help."""
        from vn_agent.agents.routing import decide_retry_target
        max_rev = 2

        round0 = [_f("branch_intent_misalign", source="llm")]
        d0 = decide_retry_target(round0, revision_count=0, max_revisions=max_rev)
        assert d0.target == "step2_only", (
            f"Round 0 must retry on LLM-only findings (full benefit of "
            f"the doubt); got {d0.target} ({d0.reason})"
        )

        # Round 1: same LLM finding persisting -> accept (tier-2 cap)
        round1 = [_f("branch_intent_misalign", source="llm")]
        d1 = decide_retry_target(round1, revision_count=1, max_revisions=max_rev)
        assert d1.target == "accept", (
            f"Round 1 with only LLM findings must hit tier-2 cap; "
            f"got {d1.target} ({d1.reason})"
        )
        assert "LLM signal didn't help" in d1.reason

    def test_lifecycle_revision_count_increments_through_loop(self, mocker):
        """Verify the redo nodes actually bump director_revision_count
        when they execute end-to-end (mocking out the LLM)."""
        from vn_agent.agents.director import (
            run_director_full_redo,
            run_director_step2_redo,
        )
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import Scene, VNScript

        # Mock _step1_outline / _step2_details to return minimal valid
        # plan_data so _build_from_plan succeeds.
        async def _fake_step1(*args, **kwargs):
            return {
                "title": "T", "description": "d", "art_direction": "x",
                "start_scene_id": "s0",
                "scenes": [{
                    "id": "s0", "title": "S0", "description": "d",
                    "background_id": "bg", "characters_present": ["alice"],
                }],
                "characters": [{
                    "id": "alice", "name": "A", "color": "#ffffff",
                    "personality": "p", "background": "b", "role": "main",
                }],
                "world_variables": [],
            }

        async def _fake_step2(outline, output_dir, settings, **kwargs):
            return {
                "scenes": [{
                    "id": "s0",
                    "next_scene_id": None,
                    "branches": [],
                    "music_mood": "peaceful",
                    "music_description": "",
                    "emotional_arc": "",
                }],
            }

        mocker.patch("vn_agent.agents.director._step1_outline",
                     side_effect=_fake_step1)
        mocker.patch("vn_agent.agents.director._step2_details",
                     side_effect=_fake_step2)
        mocker.patch("vn_agent.agents.director._save_checkpoint")

        # Initial state with a script (for step2_redo) and revision_count=0
        scenes = [Scene(
            id="s0", title="S0", description="d", background_id="bg",
            characters_present=["alice"],
        )]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes, world_variables=[],
        )
        chars = {"alice": CharacterProfile(
            id="alice", name="A", role="main",
            personality="p", background="b",
        )}

        import asyncio
        state = {
            "theme": "th", "output_dir": ".",
            "max_scenes": 1, "num_characters": 1,
            "art_direction": "x",
            "vn_script": script, "characters": chars,
            "structure_review_findings": [_f("roster_unused")],
            "director_revision_count": 0,
        }

        # Execute step1_step2 redo (round 0 -> 1)
        result1 = asyncio.run(run_director_full_redo(state))
        assert result1["director_revision_count"] == 1
        assert "vn_script" in result1

        # Now execute step2 redo (round 1 -> 2)
        state2 = {**state, **result1, "structure_review_findings": [
            _f("branch_intent_misalign", source="llm"),
        ]}
        result2 = asyncio.run(run_director_step2_redo(state2))
        assert result2["director_revision_count"] == 2


class TestWarningsDedup:
    """Phase 13-2 Step 4e/4 (Gemini hardening BLOCKER #e):
    structure_reviewer must filter previous-round StructureReviewer[
    entries before appending new ones, so the retry loop doesn't
    accumulate exponential duplicates."""

    @pytest.mark.asyncio
    async def test_round2_warnings_does_not_duplicate_round1(self, mocker):
        from unittest.mock import AsyncMock

        from vn_agent.agents.structure_reviewer import run_structure_reviewer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import (
            BranchOption,
            Scene,
            VNScript,
        )

        # Script with one unused character so _local_structural_audit
        # produces a roster_unused finding consistently across rounds.
        scenes = [
            Scene(id="s0", title="S0", description="d", background_id="bg",
                  characters_present=["alice"], branches=[
                      BranchOption(text="go", next_scene_id="s1"),
                  ]),
            Scene(id="s1", title="S1", description="d", background_id="bg",
                  characters_present=["alice"]),
        ]
        chars = {
            "alice": CharacterProfile(id="alice", name="A", role="p",
                                      personality="", background=""),
            "ghost": CharacterProfile(id="ghost", name="G", role="x",
                                      personality="", background=""),
        }
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes, world_variables=[],
        )

        import json as _json

        class _Resp:
            content = _json.dumps({
                "verdict": "FAIL",
                "branch_alignment_score": 0.9,
                "aligned_branches": [],
                "narrative_findings": [],
                "summary": "x",
            })

        mock_settings = mocker.patch(
            "vn_agent.agents.structure_reviewer.get_settings",
        )
        mock_settings.return_value.llm_structure_reviewer_model = "claude-sonnet-4-6"
        mock_settings.return_value.structure_review_strict = False
        # Patch what structure_reviewer awaits, not a name it never reads.
        # This test used to patch `structure_reviewer.ainvoke_llm`, which
        # `ainvoke_with_pending_debug` bypasses via its own function-local
        # import — so it was calling the live model, and "flaking" purely
        # because the model returned a different number of findings each
        # run (4 vs 5). See tests/conftest.py.
        mocker.patch(
            "vn_agent.services.pending_debug.ainvoke_with_pending_debug",
            AsyncMock(return_value=_Resp()),
        )

        # Round 1: empty warnings -> populated with roster_unused
        state_round1 = {"vn_script": script, "characters": chars,
                        "warnings": [], "errors": ["pre-existing pipeline error"]}
        result1 = await run_structure_reviewer(state_round1)
        round1_sr_warnings = [
            w for w in result1["warnings"] if w.startswith("StructureReviewer[")
        ]
        assert len(round1_sr_warnings) >= 1
        # Pre-existing non-StructureReviewer warning is preserved if
        # already present in state — but we passed in state["warnings"]=[]
        # so it shouldn't be there.

        # Round 2: simulate the retry loop where state["warnings"]
        # already contains round 1's StructureReviewer entries.
        state_round2 = {
            "vn_script": script, "characters": chars,
            "warnings": list(result1["warnings"]),
            "errors": [],
        }
        result2 = await run_structure_reviewer(state_round2)
        round2_sr_warnings = [
            w for w in result2["warnings"] if w.startswith("StructureReviewer[")
        ]
        # Critical: round 2 warnings list is NOT round 1 entries + new
        # entries. It's just round 2's entries (round 1 dropped via filter).
        assert len(round2_sr_warnings) == len(round1_sr_warnings), (
            f"Round 2 must not accumulate: round 1 had "
            f"{len(round1_sr_warnings)} StructureReviewer warnings; "
            f"round 2 has {len(round2_sr_warnings)}. They should be "
            f"equal (round 1 dropped via filter)."
        )

    @pytest.mark.asyncio
    async def test_writer_does_not_extend_with_warnings(self, mocker, tmp_path):
        """Phase 13-2 Step 4e/4: writer.py reads ONLY structure_review_issues,
        not state["warnings"], to prevent advisory duplication."""
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import Scene, VNScript

        captured_structure_issues: list = []

        async def _fake_write(scene, *args, **kwargs):
            captured_structure_issues.append(kwargs.get("structure_issues") or [])
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")

        scenes = [Scene(id="s0", title="S0", description="d",
                        background_id="bg", characters_present=["alice"])]
        script = VNScript(title="T", description="d", theme="th",
                          start_scene_id="s0", scenes=scenes, world_variables=[])
        chars = {"alice": CharacterProfile(
            id="alice", name="A", role="p", personality="", background="",
        )}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=1, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)
        state["structure_review_issues"] = ["finding A", "finding B"]
        # Stuff state["warnings"] with overlapping content to ensure
        # writer.py does NOT append it.
        state["warnings"] = [
            "StructureReviewer[advisory]: finding A",
            "StructureReviewer[advisory]: finding B",
            "StructureReviewer[advisory]: finding A",  # duplicate from prior round
        ]

        await run_writer(state)
        # Each scene's structure_issues should match input length, NOT
        # input + warnings (which would be 5 entries).
        assert captured_structure_issues
        assert all(len(issues) == 2 for issues in captured_structure_issues), (
            f"writer.py must read ONLY structure_review_issues (len 2); "
            f"got per-scene lengths {[len(i) for i in captured_structure_issues]}"
        )
