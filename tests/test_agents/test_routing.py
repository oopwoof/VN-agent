"""Phase 13-2 Step 4e: routing helper tests.

Pure function. No mocks. Tests the decision table for every cell.
"""
from __future__ import annotations

import pytest

from vn_agent.agents.routing import (
    STEP1_CATEGORIES,
    RouteDecision,
    decide_retry_target,
)
from vn_agent.schema.script import StructureFinding


def _f(category: str, *, source: str = "deterministic",
       requires_retry: bool = True) -> StructureFinding:
    return StructureFinding(
        category=category,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        message=f"test {category}",
        requires_retry=requires_retry,
    )


# ---------------------------------------------------------------------------
# Accept paths
# ---------------------------------------------------------------------------


class TestAcceptPaths:
    def test_no_findings_accept(self):
        decision = decide_retry_target([], revision_count=0, max_revisions=2)
        assert decision.target == "accept"
        assert "no actionable" in decision.reason

    def test_only_advisory_findings_accept(self):
        """requires_retry=False findings are warnings only — never block."""
        findings = [
            _f("advisory", requires_retry=False),
            _f("tone_inconsistent", source="llm", requires_retry=False),
        ]
        decision = decide_retry_target(findings, 0, 2)
        assert decision.target == "accept"

    def test_max_revisions_hit_accept(self):
        findings = [_f("roster_unused")]
        decision = decide_retry_target(findings, revision_count=2, max_revisions=2)
        assert decision.target == "accept"
        assert "max retries hit" in decision.reason
        assert "2/2" in decision.reason

    def test_max_revisions_hit_at_3rd_attempt(self):
        """revision_count=3 with max=2 also accepts (defensive)."""
        findings = [_f("roster_unused")]
        decision = decide_retry_target(findings, revision_count=3, max_revisions=2)
        assert decision.target == "accept"


# ---------------------------------------------------------------------------
# Step1+step2 escalation
# ---------------------------------------------------------------------------


class TestStep1Step2Escalation:
    @pytest.mark.parametrize("category", sorted(STEP1_CATEGORIES))
    def test_each_step1_category_triggers_escalation_at_round_0(self, category):
        """Every category in STEP1_CATEGORIES must escalate to step1+step2."""
        findings = [_f(category)]
        decision = decide_retry_target(findings, 0, 2)
        assert decision.target == "step1_step2", (
            f"category={category} did not escalate to step1_step2"
        )
        assert category in decision.reason

    def test_mixed_step1_and_step2_escalates_to_step1_step2(self):
        """If even one step1-class finding is active, route to step1_step2."""
        findings = [
            _f("roster_unused"),
            _f("branch_target_invalid"),
            _f("branch_intent_misalign", source="llm"),
        ]
        decision = decide_retry_target(findings, 0, 2)
        assert decision.target == "step1_step2"

    def test_step1_class_at_round_1_still_escalates(self):
        """If round 1 retry left a step1-class issue unsolved, round 2
        should still try (deterministic findings get the full budget)."""
        findings = [_f("world_var_unused")]
        decision = decide_retry_target(findings, revision_count=1, max_revisions=2)
        assert decision.target == "step1_step2"

    def test_step1_class_llm_judged_still_escalates_at_round_0(self):
        """LLM-judged step1-class findings (e.g. macro_pacing_misaligned)
        also escalate at round 0 — source filter only kicks in at round 1+."""
        findings = [_f("macro_pacing_misaligned", source="llm")]
        decision = decide_retry_target(findings, 0, 2)
        assert decision.target == "step1_step2"


# ---------------------------------------------------------------------------
# Step2-only retry
# ---------------------------------------------------------------------------


class TestStep2OnlyRetry:
    def test_round_0_step2_class_routes_to_step2_only(self):
        findings = [_f("branch_target_invalid")]
        decision = decide_retry_target(findings, 0, 2)
        assert decision.target == "step2_only"
        assert "branch_target_invalid" in decision.reason

    def test_round_0_multiple_step2_class_routes_to_step2_only(self):
        findings = [
            _f("unreachable_scene"),
            _f("branch_dead_end"),
            _f("branch_intent_misalign", source="llm"),
        ]
        decision = decide_retry_target(findings, 0, 2)
        assert decision.target == "step2_only"

    def test_round_1_with_deterministic_step2_findings_retries(self):
        """Deterministic step2-class findings get the full budget."""
        findings = [_f("branch_target_invalid")]
        decision = decide_retry_target(findings, revision_count=1, max_revisions=2)
        assert decision.target == "step2_only"


# ---------------------------------------------------------------------------
# Tier-2 LLM cap (key behavioral rule from Gemini design review)
# ---------------------------------------------------------------------------


class TestRound2LlmOnlyCapAccepts:
    def test_round_1_only_llm_findings_accepts(self):
        """The Sonnet-on-Sonnet judgment loop drift case. If round 0
        retry didn't fix the LLM-judged issues, round 2 of the same
        prompt won't either — accept and surface as warnings."""
        findings = [
            _f("branch_intent_misalign", source="llm"),
            _f("strategy_distribution_gap", source="llm"),
        ]
        decision = decide_retry_target(findings, revision_count=1, max_revisions=2)
        assert decision.target == "accept"
        assert "LLM signal didn't help" in decision.reason

    def test_round_1_mixed_llm_and_deterministic_keeps_deterministic(self):
        """If both sources active at round 1, deterministic findings
        still drive the routing — LLM ones ride along but don't gate."""
        findings = [
            _f("branch_intent_misalign", source="llm"),
            _f("branch_target_invalid", source="deterministic"),
        ]
        decision = decide_retry_target(findings, revision_count=1, max_revisions=2)
        assert decision.target == "step2_only"

    def test_round_0_llm_only_findings_still_retry(self):
        """Round 0 LLM-only findings DO trigger retry — the cap is
        round 1+ only. First attempt gets the benefit of the doubt."""
        findings = [_f("branch_intent_misalign", source="llm")]
        decision = decide_retry_target(findings, revision_count=0, max_revisions=2)
        assert decision.target == "step2_only"


# ---------------------------------------------------------------------------
# RouteDecision dataclass
# ---------------------------------------------------------------------------


class TestRouteDecisionShape:
    def test_decision_is_immutable(self):
        """frozen=True so callers can't mutate the routing decision in
        place (would mask bugs in graph.py edge dispatch)."""
        decision = RouteDecision("accept", "no findings")
        with pytest.raises(Exception):
            decision.target = "step2_only"  # type: ignore[misc]

    def test_reason_is_human_readable(self):
        """Reason should be meaningful for log output."""
        findings = [_f("roster_unused")]
        decision = decide_retry_target(findings, 0, 2)
        # Either category name or "step1-class" should surface
        assert "roster_unused" in decision.reason or "step1" in decision.reason


# ---------------------------------------------------------------------------
# Sanity: the categorization in STEP1_CATEGORIES
# ---------------------------------------------------------------------------


class TestStep1CategoriesContents:
    def test_step1_categories_match_design(self):
        """Pin the routing table from the design doc — adding/removing
        a category here is a deliberate design change requiring review."""
        assert STEP1_CATEGORIES == frozenset({
            "roster_unused",
            "world_var_unused",
            "macro_pacing_misaligned",
            "foreshadow_payoff_missing",
        })
