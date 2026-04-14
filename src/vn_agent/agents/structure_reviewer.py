"""StructureReviewer Agent (Sprint 7-5): Sonnet-backed audit of Director outline.

Runs AFTER Director, BEFORE Writer. Evaluates narrative-level issues on the
outline (scene descriptions + strategies + branches + characters), so structural
problems are caught BEFORE Writer spends ~6 Sonnet calls on dialogue for a
broken outline.

Two audits:
  1. Narrative shape: strategy distribution, emotional arc coherence, character
     count vs. scene count sanity, story-arc completeness (does it reach a
     meaningful endpoint?).
  2. Branch intent alignment (Sprint 6-10 fourth defense layer): for every
     branch option, check whether the option.text's intent matches the
     downstream scene's description. Catches Director producing two branches
     that both "work" structurally but semantically point to the wrong
     consequence (e.g. "Read aloud" → quiet-ascent scene instead of
     confrontation scene).

Non-blocking by default: issues land as warnings in state["errors"]. Blocking
failure only when settings.structure_review_strict=True and multiple issues
found — lets us catch regressions during sweeps without stopping on every
soft warning.

Output:
  state["structure_review_passed"]: bool
  state["structure_review_feedback"]: str summary
  state["structure_review_issues"]: list[str]
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from vn_agent.agents.state import AgentState
from vn_agent.config import get_settings
from vn_agent.schema.script import VNScript
from vn_agent.services.llm import ainvoke_llm
from vn_agent.strategies.narrative import DATASET_ALIGNED, StrategyType

logger = logging.getLogger(__name__)


STRUCTURE_REVIEWER_SYSTEM = """You are a narrative architect auditing a visual \
novel outline BEFORE dialogue is written. You read only scene descriptions, \
strategy labels, branches, and character profiles — there is no dialogue yet. \
Your judgment decides whether Writer proceeds or Director revises.

You evaluate two things in priority order:

## 1. Branch intent alignment (critical)

For every scene with branches, examine each branch's `text` and the \
description of its `next_scene_id` target. The player's choice wording MUST \
semantically lead to the consequence it points at.

Common failure modes:
- "Help them" option that leads to a scene where they were abandoned
- "Stay silent" option that leads to a confrontation scene
- Two options whose wording implies opposite approaches but whose targets \
describe the same consequence (cosmetic branch)

Score each branch 0 or 1: 1 = option text intent matches target scene \
meaning; 0 = the choice wording does not plausibly produce that target.

## 2. Narrative shape (supporting)

- Strategy distribution: does the arc cover beginning (drift/accumulate), \
middle (contest/erode/uncover), climax (rupture/escalate), resolution \
(resolve)? A 6-scene script that's 5× drift is broken.
- Character efficiency: are all characters used in at least 2 scenes? \
A character introduced but never used again is an outline defect.
- Terminal reachability: every branch and next_scene_id must lead \
eventually to a scene with no outgoing edges (ending).

## Output format

Return JSON with exactly this shape:
{{
  "verdict": "PASS" | "FAIL",
  "branch_alignment_score": <0.0-1.0 fraction of branches that align>,
  "aligned_branches": [{{"scene_id": "...", "branch_text": "...", "aligned": true|false, "reason": "..."}}],
  "narrative_issues": ["one issue per string, max 5"],
  "summary": "one-sentence overall assessment"
}}

Verdict rules:
- PASS if branch_alignment_score >= 0.8 AND narrative_issues has <=1 entry
- FAIL otherwise

No markdown, no <thinking> tags in the final output. Return JSON only."""


@dataclass
class StructureReviewResult:
    passed: bool
    feedback: str
    issues: list[str]
    branch_alignment_score: float | None = None
    aligned_branches: list[dict] | None = None


async def run_structure_reviewer(state: AgentState) -> dict:
    """StructureReviewer node: audits Director outline before Writer runs."""
    script = state.get("vn_script")
    if not script:
        logger.warning("StructureReviewer: no vn_script in state — skipping")
        return {
            "structure_review_passed": True,
            "structure_review_feedback": "skipped (no script)",
            "structure_review_issues": [],
        }

    settings = get_settings()

    # Fast path: if there are no branches and only a handful of scenes, skip
    # the LLM call — nothing structural to audit beyond what Sprint 6-6
    # already covered.
    any_branches = any(s.branches for s in script.scenes)
    if not any_branches and len(script.scenes) <= 3:
        return {
            "structure_review_passed": True,
            "structure_review_feedback": "trivial outline, skipped",
            "structure_review_issues": [],
        }

    # ── Cheap local checks first (no LLM cost) ─────────────────────────────
    local_issues = _local_structural_audit(script, state.get("characters", {}))
    if local_issues and logger.isEnabledFor(logging.INFO):
        logger.info(f"StructureReviewer local issues: {local_issues[:3]}")

    # ── LLM-backed intent-alignment + narrative shape audit ────────────────
    user_prompt = _build_audit_prompt(script, state.get("characters", {}))
    try:
        response = await ainvoke_llm(
            STRUCTURE_REVIEWER_SYSTEM,
            user_prompt,
            model=settings.llm_structure_reviewer_model,
            caller="structure_reviewer",
        )
        content = response.content if hasattr(response, "content") else str(response)
        result = _parse_audit(content, local_issues)
    except Exception as e:
        logger.warning(f"StructureReviewer LLM call failed: {e} — passing through")
        return {
            "structure_review_passed": True,
            "structure_review_feedback": f"LLM audit failed: {e}",
            "structure_review_issues": local_issues,
        }

    if result.passed:
        logger.info(
            f"StructureReviewer PASS: alignment={result.branch_alignment_score}, "
            f"issues={len(result.issues)}"
        )
    else:
        logger.warning(
            f"StructureReviewer FAIL: alignment={result.branch_alignment_score}, "
            f"issues={result.issues[:3]}"
        )

    # Persist to state. Reviewer feedback will be visible to Writer as
    # `structure_feedback` in the prompt.
    errors = list(state.get("errors", []))
    for issue in result.issues:
        errors.append(f"StructureReviewer: {issue}")

    return {
        "structure_review_passed": result.passed,
        "structure_review_feedback": result.feedback,
        "structure_review_issues": result.issues,
        "structure_review_alignment_score": result.branch_alignment_score,
        "structure_review_aligned_branches": result.aligned_branches,
        "errors": errors,
    }


def _local_structural_audit(
    script: VNScript, characters: dict
) -> list[str]:
    """Cheap pre-LLM checks — catch obvious defects without a Sonnet call."""
    issues: list[str] = []

    if not script.scenes:
        issues.append("script has zero scenes")
        return issues

    # 1. Unreachable / dangling scenes already caught by Sprint 6-6 in Director.
    # Here we just verify character efficiency.
    if characters:
        used_chars = {
            cid for scene in script.scenes for cid in scene.characters_present
        }
        unused = set(characters.keys()) - used_chars
        if unused:
            issues.append(
                f"characters defined but never used in any scene: {sorted(unused)}"
            )

    # 2. Strategy variety: if every scene has the same strategy, the arc is flat.
    strategies = [s.narrative_strategy for s in script.scenes if s.narrative_strategy]
    if strategies and len(set(strategies)) == 1 and len(strategies) >= 3:
        issues.append(
            f"all {len(strategies)} scenes use the same strategy "
            f"'{strategies[0]}' — arc is flat"
        )

    # 3. Sprint 6-13 tag: if Director emits a non-enum strategy value,
    # downstream Writer/Reviewer/Judge all get confused (see "branch"
    # hallucination in sweep cell vn_20260413_194624).
    valid = {s.value for s in StrategyType}
    for scene in script.scenes:
        if scene.narrative_strategy and scene.narrative_strategy not in valid:
            issues.append(
                f"scene '{scene.id}' has non-canonical strategy "
                f"'{scene.narrative_strategy}' (not in StrategyType enum)"
            )

    # 4. Note for downstream: flag generation-only strategies so humans can
    # spot cases where RAG fallback behavior may be in play.
    gen_only = [
        s.id for s in script.scenes
        if s.narrative_strategy and s.narrative_strategy not in DATASET_ALIGNED
        and s.narrative_strategy in valid
    ]
    if gen_only:
        logger.info(
            f"StructureReviewer: {len(gen_only)} scene(s) use generation-only "
            f"strategies (no corpus few-shot): {gen_only}"
        )

    return issues


def _build_audit_prompt(script: VNScript, characters: dict) -> str:
    """Compact outline dump for the LLM auditor."""
    char_lines = [
        f"- {cid} ({c.name}): {c.role} — {c.personality[:80]}"
        for cid, c in characters.items()
    ]
    scene_lines = []
    for scene in script.scenes:
        exits = []
        if scene.next_scene_id:
            exits.append(f"→ {scene.next_scene_id}")
        for b in scene.branches:
            exits.append(f'  branch: "{b.text}" → {b.next_scene_id}')
        strat = scene.narrative_strategy or "unspecified"
        scene_lines.append(
            f"[{scene.id}] {scene.title} ({strat})\n"
            f"  description: {scene.description}\n"
            f"  characters: {scene.characters_present}\n"
            f"  exits: {exits or ['TERMINAL']}"
        )
    return (
        f"Title: {script.title}\n"
        f"Theme: {script.theme}\n"
        f"Start scene: {script.start_scene_id}\n\n"
        f"Characters ({len(characters)}):\n" + "\n".join(char_lines) + "\n\n"
        f"Scenes ({len(script.scenes)}):\n" + "\n\n".join(scene_lines) + "\n\n"
        "Audit per the rubric. Return JSON only."
    )


def _parse_audit(content: str, local_issues: list[str]) -> StructureReviewResult:
    """Extract JSON verdict. Falls back to local-only issues on parse fail."""
    import re
    content = content.strip()
    # Strip common wrappers
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        if start != -1:
            try:
                data, _ = json.JSONDecoder().raw_decode(content, start)
            except json.JSONDecodeError:
                logger.warning("StructureReviewer: JSON parse failed, using local checks only")
                return StructureReviewResult(
                    passed=not local_issues,
                    feedback="LLM audit JSON unparseable",
                    issues=local_issues,
                )
        else:
            return StructureReviewResult(
                passed=not local_issues,
                feedback="LLM returned no JSON",
                issues=local_issues,
            )

    verdict = (data.get("verdict") or "").upper().strip()
    narrative_issues = data.get("narrative_issues") or []
    summary = data.get("summary") or ""
    alignment_score = data.get("branch_alignment_score")
    aligned_branches = data.get("aligned_branches") or []

    # Misaligned branches as discrete issues so Writer sees them
    misaligned = [
        b for b in aligned_branches
        if isinstance(b, dict) and b.get("aligned") is False
    ]
    for m in misaligned:
        narrative_issues.append(
            f"branch intent misaligned in scene '{m.get('scene_id', '?')}': "
            f"'{m.get('branch_text', '?')[:60]}' — {m.get('reason', '')[:120]}"
        )

    all_issues = list(local_issues) + list(narrative_issues)
    passed = verdict == "PASS" and len(all_issues) <= 1

    return StructureReviewResult(
        passed=passed,
        feedback=summary or ("PASS" if passed else "FAIL"),
        issues=all_issues,
        branch_alignment_score=alignment_score,
        aligned_branches=aligned_branches,
    )
