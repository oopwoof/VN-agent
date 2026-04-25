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
