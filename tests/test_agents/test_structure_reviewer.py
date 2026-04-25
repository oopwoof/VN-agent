"""Phase 13-2 Step 4e: structure_reviewer emits StructureFinding[].

Tests categorization (deterministic + LLM parsing) and the warnings vs
errors state split. No real LLM calls — all mocked.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from vn_agent.agents.structure_reviewer import (
    _local_structural_audit,
    _normalize_finding_dict,
    _parse_audit,
    run_structure_reviewer,
)
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import (
    BranchOption,
    Scene,
    SceneContextRef,
    StructureFinding,
    VNScript,
)


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


def _scene(sid: str, *, characters=None, branches=None, strategy=None,
           context_deps=None, state_reads=None, bg=None):
    return Scene(
        id=sid, title=sid.upper(), description=f"scene {sid}",
        background_id=bg or f"bg_{sid}",
        characters_present=characters or ["alice"],
        branches=branches or [],
        narrative_strategy=strategy,
        context_deps=context_deps or [],
        state_reads=state_reads or [],
    )


def _script(scenes, characters=None, world_vars=None):
    return VNScript(
        title="T", description="d", theme="th",
        start_scene_id=scenes[0].id,
        scenes=scenes,
        world_variables=world_vars or [],
    )


# ---------------------------------------------------------------------------
# Local (deterministic) audit categorization
# ---------------------------------------------------------------------------


class TestLocalAuditCategories:

    def test_unused_character_emits_roster_unused(self):
        scenes = [_scene("s0"), _scene("s1")]
        chars = {
            "alice": CharacterProfile(id="alice", name="A", role="p",
                                      personality="", background=""),
            "ghost": CharacterProfile(id="ghost", name="G", role="x",
                                      personality="", background=""),
        }
        findings = _local_structural_audit(_script(scenes), chars)
        assert any(f.category == "roster_unused" for f in findings)
        roster = next(f for f in findings if f.category == "roster_unused")
        assert roster.source == "deterministic"
        assert roster.requires_retry is True
        assert "ghost" in roster.message

    def test_flat_strategy_emits_strategy_distribution_gap(self):
        scenes = [_scene(f"s{i}", strategy="drift") for i in range(3)]
        findings = _local_structural_audit(_script(scenes), {})
        assert any(f.category == "strategy_distribution_gap" for f in findings)

    def test_low_diversity_emits_strategy_distribution_gap(self):
        scenes = [
            _scene("s0", strategy="drift"),
            _scene("s1", strategy="drift"),
            _scene("s2", strategy="accumulate"),
            _scene("s3", strategy="drift"),
            _scene("s4", strategy="accumulate"),
        ]
        findings = _local_structural_audit(_script(scenes), {})
        assert any(f.category == "strategy_distribution_gap" for f in findings)

    def test_non_canonical_strategy_is_advisory(self):
        """Director typo — retry would re-typo. Mark advisory."""
        scenes = [_scene("s0", strategy="bogus_strategy")]
        findings = _local_structural_audit(_script(scenes), {})
        bogus = [f for f in findings if "bogus_strategy" in f.message]
        assert len(bogus) == 1
        assert bogus[0].category == "advisory"
        assert bogus[0].requires_retry is False

    def test_context_dep_unknown_scene_is_branch_target_invalid(self):
        scenes = [
            _scene("s0"),
            _scene("s1", context_deps=[
                SceneContextRef(
                    ref_type="scene", ref_id="missing_scene",
                    link_type="callback", reason="t",
                ),
            ]),
        ]
        findings = _local_structural_audit(_script(scenes), {})
        assert any(f.category == "branch_target_invalid" for f in findings)

    def test_context_dep_unknown_character_is_character_undeclared_use(self):
        scenes = [
            _scene("s0"),
            _scene("s1", context_deps=[
                SceneContextRef(
                    ref_type="character_arc", ref_id="character:phantom",
                    link_type="callback", reason="t",
                ),
            ]),
        ]
        findings = _local_structural_audit(_script(scenes), {})
        cat_finding = next(
            (f for f in findings if f.category == "character_undeclared_use"),
            None,
        )
        assert cat_finding is not None
        assert cat_finding.target_character_id == "phantom"

    def test_context_dep_unknown_world_var_is_world_var_undeclared_use(self):
        scenes = [
            _scene("s0"),
            _scene("s1", context_deps=[
                SceneContextRef(
                    ref_type="world_var", ref_id="world_var:trust",
                    link_type="state_dependency", reason="t",
                ),
            ], state_reads=["trust"]),
        ]
        findings = _local_structural_audit(_script(scenes), {})
        assert any(f.category == "world_var_undeclared_use" for f in findings)


# ---------------------------------------------------------------------------
# LLM finding normalization
# ---------------------------------------------------------------------------


class TestNormalizeFindingDict:

    def test_known_category_passes_through(self):
        f = _normalize_finding_dict({
            "category": "branch_intent_misalign",
            "message": "branch x doesn't match target",
            "requires_retry": True,
        })
        assert f is not None
        assert f.category == "branch_intent_misalign"
        assert f.source == "llm"
        assert f.requires_retry is True

    def test_unknown_category_falls_back_to_advisory(self):
        f = _normalize_finding_dict({
            "category": "bogus_made_up_label",
            "message": "something wrong",
            "requires_retry": True,
        })
        assert f is not None
        assert f.category == "advisory"

    def test_empty_message_returns_none(self):
        f = _normalize_finding_dict({"category": "advisory", "message": ""})
        assert f is None

    def test_missing_requires_retry_defaults_by_category(self):
        """advisory → requires_retry=False, others → True."""
        adv = _normalize_finding_dict({"category": "advisory", "message": "x"})
        cat = _normalize_finding_dict({
            "category": "branch_intent_misalign", "message": "x",
        })
        assert adv.requires_retry is False
        assert cat.requires_retry is True


# ---------------------------------------------------------------------------
# _parse_audit
# ---------------------------------------------------------------------------


class TestParseAudit:

    def test_parses_new_shape_narrative_findings(self):
        content = json.dumps({
            "verdict": "FAIL",
            "branch_alignment_score": 0.5,
            "aligned_branches": [],
            "narrative_findings": [
                {"category": "branch_intent_misalign",
                 "message": "branch X bypasses Y", "requires_retry": True},
            ],
            "summary": "issues found",
        })
        result = _parse_audit(content, [])
        assert len(result.findings) == 1
        assert result.findings[0].category == "branch_intent_misalign"
        assert result.findings[0].source == "llm"
        assert not result.passed

    def test_parses_legacy_narrative_issues_as_advisory(self):
        """If the LLM ignores the new prompt and emits old-shape strings,
        we still capture them — as advisory findings (don't trigger retry)."""
        content = json.dumps({
            "verdict": "FAIL",
            "branch_alignment_score": 0.5,
            "aligned_branches": [],
            "narrative_issues": ["old-shape string issue"],
            "summary": "",
        })
        result = _parse_audit(content, [])
        assert len(result.findings) == 1
        assert result.findings[0].category == "advisory"
        assert result.findings[0].requires_retry is False

    def test_misaligned_branches_become_findings(self):
        content = json.dumps({
            "verdict": "FAIL",
            "branch_alignment_score": 0.4,
            "aligned_branches": [
                {"scene_id": "s2", "branch_text": "Help",
                 "aligned": False, "reason": "leads to abandonment scene"},
            ],
            "narrative_findings": [],
            "summary": "branch 'Help' inverted",
        })
        result = _parse_audit(content, [])
        assert any(
            f.category == "branch_intent_misalign" for f in result.findings
        )

    def test_combines_local_and_llm_findings(self):
        local = [StructureFinding(
            category="roster_unused", source="deterministic",
            message="unused: ['ghost']",
        )]
        content = json.dumps({
            "verdict": "FAIL",
            "branch_alignment_score": 0.7,
            "aligned_branches": [],
            "narrative_findings": [
                {"category": "strategy_distribution_gap",
                 "message": "no rupture beat", "requires_retry": True},
            ],
            "summary": "x",
        })
        result = _parse_audit(content, local)
        cats = {f.category for f in result.findings}
        assert "roster_unused" in cats
        assert "strategy_distribution_gap" in cats

    def test_unparseable_json_falls_back_to_local_only(self):
        result = _parse_audit("not json at all", [
            StructureFinding(category="roster_unused", source="deterministic",
                             message="x"),
        ])
        assert len(result.findings) == 1
        assert result.findings[0].source == "deterministic"

    def test_passed_when_no_actionable_findings(self):
        content = json.dumps({
            "verdict": "PASS",
            "branch_alignment_score": 0.95,
            "aligned_branches": [],
            "narrative_findings": [],
            "summary": "all good",
        })
        result = _parse_audit(content, [])
        assert result.passed
        assert result.findings == []


# ---------------------------------------------------------------------------
# run_structure_reviewer state output
# ---------------------------------------------------------------------------


class TestRunStructureReviewerStateOutput:

    @pytest.mark.asyncio
    async def test_warnings_go_to_state_warnings_not_errors(self):
        """Phase 13-2 Step 4e: structural findings populate state['warnings'],
        NOT state['errors']. Pre-fix the smoke harness reported '[PASS] but
        7 errors' which was confusing — those were warnings, not errors."""
        scenes = [
            _scene("s0", branches=[
                BranchOption(text="go", next_scene_id="s1"),
            ]),
            _scene("s1"),
        ]
        chars = {
            "alice": CharacterProfile(id="alice", name="A", role="p",
                                      personality="", background=""),
            "ghost": CharacterProfile(id="ghost", name="G", role="x",
                                      personality="", background=""),
        }
        script = _script(scenes)
        state = {
            "vn_script": script,
            "characters": chars,
            "errors": ["pre-existing pipeline error"],
            "warnings": [],
        }

        # Mock the LLM call to return a clean JSON response with one finding
        llm_response = json.dumps({
            "verdict": "FAIL",
            "branch_alignment_score": 0.9,
            "aligned_branches": [],
            "narrative_findings": [],
            "summary": "found one local issue",
        })
        mock_ainvoke = AsyncMock(return_value=_FakeResponse(llm_response))

        with patch("vn_agent.agents.structure_reviewer.get_settings") as mock_s, \
             patch("vn_agent.agents.structure_reviewer.ainvoke_llm", mock_ainvoke):
            mock_s.return_value.llm_structure_reviewer_model = "claude-sonnet-4-6"
            mock_s.return_value.structure_review_strict = False
            result = await run_structure_reviewer(state)

        # roster_unused finding (local, deterministic) should land in warnings
        warnings = result["warnings"]
        assert any("StructureReviewer" in w for w in warnings)
        assert any("roster_unused" in w for w in warnings)
        # state['errors'] must NOT have any new StructureReviewer entries.
        # (The pre-existing entry stays — we don't touch it.)
        assert "errors" not in result, (
            "structure_reviewer must not push to state['errors']; "
            "warnings is the new home"
        )

    @pytest.mark.asyncio
    async def test_findings_field_populated(self):
        """state['structure_review_findings'] is the new typed surface;
        legacy state['structure_review_issues'] (str list) remains for
        Writer prompt context."""
        scenes = [
            _scene("s0", branches=[
                BranchOption(text="go", next_scene_id="s1"),
            ]),
            _scene("s1"),
        ]
        chars = {
            "alice": CharacterProfile(id="alice", name="A", role="p",
                                      personality="", background=""),
            "ghost": CharacterProfile(id="ghost", name="G", role="x",
                                      personality="", background=""),
        }
        state = {"vn_script": _script(scenes), "characters": chars}
        llm_response = json.dumps({
            "verdict": "FAIL",
            "branch_alignment_score": 0.9,
            "aligned_branches": [],
            "narrative_findings": [
                {"category": "branch_intent_misalign",
                 "message": "mismatch", "requires_retry": True},
            ],
            "summary": "mixed",
        })

        with patch("vn_agent.agents.structure_reviewer.get_settings") as mock_s, \
             patch("vn_agent.agents.structure_reviewer.ainvoke_llm",
                   AsyncMock(return_value=_FakeResponse(llm_response))):
            mock_s.return_value.llm_structure_reviewer_model = "claude-sonnet-4-6"
            mock_s.return_value.structure_review_strict = False
            result = await run_structure_reviewer(state)

        findings = result["structure_review_findings"]
        assert isinstance(findings, list)
        assert all(isinstance(f, StructureFinding) for f in findings)
        # mix of source="deterministic" (roster_unused) + source="llm"
        sources = {f.source for f in findings}
        assert "deterministic" in sources
        assert "llm" in sources

        # Legacy issues string list still populated
        issues = result["structure_review_issues"]
        assert isinstance(issues, list)
        assert all(isinstance(s, str) for s in issues)
        assert len(issues) == len(findings)
