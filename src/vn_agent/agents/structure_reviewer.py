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

Phase 13-2 Step 4e (Gemini smoke-review #C reframed):
  - Findings now emit as schema.script.StructureFinding (typed category +
    source + requires_retry) instead of plain strings. routing.py reads
    these to decide whether Director should re-run, and which step.
  - Non-advisory findings flow to state["warnings"] (NEW), no longer
    polluting state["errors"]. Pre-Step-4e runs reported "7 errors but
    [PASS]" in run_metrics.json — confusing because they were warnings.
  - Legacy state["structure_review_issues"] (list[str]) is preserved for
    Writer's existing prompt-context path; it's just `[f.message for f
    in findings]` now.

Output:
  state["structure_review_passed"]: bool
  state["structure_review_feedback"]: str summary
  state["structure_review_issues"]: list[str]              # legacy (messages)
  state["structure_review_findings"]: list[StructureFinding]  # NEW
  state["warnings"]: list[str]                             # NEW (was state["errors"])
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from vn_agent.agents.state import AgentState
from vn_agent.config import get_settings
from vn_agent.schema.script import StructureFinding, VNScript
from vn_agent.services.llm import ainvoke_llm
from vn_agent.strategies.narrative import DATASET_ALIGNED, StrategyType

# Valid category strings (mirror StructureFindingCategory Literal). Used to
# clamp LLM output: if the model emits an unknown category we fall back to
# "advisory" instead of failing the whole audit.
_VALID_CATEGORIES = frozenset({
    "roster_unused",
    "world_var_unused",
    "macro_pacing_misaligned",
    "foreshadow_payoff_missing",
    "branch_target_invalid",
    "unreachable_scene",
    "branch_dead_end",
    "branch_intent_misalign",
    "strategy_distribution_gap",
    "branch_bypass",
    "tone_inconsistent",
    "world_var_undeclared_use",
    "character_undeclared_use",
    "advisory",
})

# Phase 13-2 Step 4e/4 (Gemini hardening NIT #c): strict subset the LLM is
# allowed to emit. Categories like "branch_target_invalid",
# "unreachable_scene", "world_var_undeclared_use", "character_undeclared_use"
# are reserved for the deterministic _local_structural_audit (~0% false
# positives). If Sonnet hallucinates one of those, we'd accept a
# subjective LLM judgment as if it were a hard graph defect — and since
# unreachable_scene routes to step2_only (vs step1_step2 for roster_unused),
# the behavior would still trigger a Director retry, just on noisier
# evidence. Coerce LLM-emitted deterministic categories down to "advisory"
# so the routing helper sees them as low-confidence and skips the retry
# (Tier-2 LLM cap) on round 2+.
_LLM_VALID_CATEGORIES = frozenset({
    "branch_intent_misalign",
    "strategy_distribution_gap",
    "branch_bypass",
    "tone_inconsistent",
    "macro_pacing_misaligned",
    "foreshadow_payoff_missing",
    "advisory",
})

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
  "narrative_findings": [
    {{
      "category": "<see Category guidance below>",
      "message": "concrete one-line description of the issue",
      "requires_retry": true | false,
      "target_scene_id": "<scene id this concerns, or null>"
    }}
  ],
  "summary": "one-sentence overall assessment"
}}

## Category guidance

- `branch_intent_misalign`: branch text's implied consequence contradicts
  the target scene's content. Set requires_retry=true.
- `strategy_distribution_gap`: a critical narrative beat type is missing
  or only reachable on some paths. Set requires_retry=true.
- `branch_bypass`: a branch path skips a strategically critical scene.
  Set requires_retry=true.
- `tone_inconsistent`: scene contradicts macro_reference's voice charter.
  Set requires_retry=true.
- `macro_pacing_misaligned`: declared pacing arc doesn't match scene
  distribution. Set requires_retry=true. (Step1 layer.)
- `foreshadow_payoff_missing`: declared foreshadow has no payoff scene.
  Set requires_retry=true. (Step1 layer.)
- `advisory`: subjective stylistic concern that would NOT be reliably
  fixed by re-rolling Director. Set requires_retry=false. Use sparingly
  — most narrative critiques should pick a concrete category.

Verdict rules:
- PASS if branch_alignment_score >= 0.8 AND no findings have requires_retry=true
- FAIL otherwise

No markdown, no <thinking> tags in the final output. Return JSON only."""


@dataclass
class StructureReviewResult:
    passed: bool
    feedback: str
    findings: list[StructureFinding] = field(default_factory=list)
    branch_alignment_score: float | None = None
    aligned_branches: list[dict] | None = None

    @property
    def issues(self) -> list[str]:
        """Legacy view: just the message strings. Used by Writer's prompt
        context block (structure_feedback section) which was already
        consuming `state["structure_review_issues"]` pre-Step-4e."""
        return [f.message for f in self.findings]


async def run_structure_reviewer(state: AgentState) -> dict:
    """StructureReviewer node: audits Director outline before Writer runs."""
    script = state.get("vn_script")
    if not script:
        logger.warning("StructureReviewer: no vn_script in state — skipping")
        return {
            "structure_review_passed": True,
            "structure_review_feedback": "skipped (no script)",
            "structure_review_issues": [],
            "structure_review_findings": [],
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
            "structure_review_findings": [],
        }

    # ── Cheap local checks first (no LLM cost) ─────────────────────────────
    local_findings = _local_structural_audit(script, state.get("characters", {}))
    if local_findings and logger.isEnabledFor(logging.INFO):
        logger.info(
            f"StructureReviewer local findings: "
            f"{[f'{f.category}:{f.message[:40]}' for f in local_findings[:3]]}"
        )

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
        result = _parse_audit(content, local_findings)
    except Exception as e:
        logger.warning(f"StructureReviewer LLM call failed: {e} — passing through")
        return {
            "structure_review_passed": True,
            "structure_review_feedback": f"LLM audit failed: {e}",
            "structure_review_issues": [f.message for f in local_findings],
            "structure_review_findings": local_findings,
        }

    if result.passed:
        logger.info(
            f"StructureReviewer PASS: alignment={result.branch_alignment_score}, "
            f"findings={len(result.findings)}"
        )
    else:
        logger.warning(
            f"StructureReviewer FAIL: alignment={result.branch_alignment_score}, "
            f"findings={[f.category for f in result.findings[:5]]}"
        )

    # Phase 13-2 Step 4e: warnings go to state["warnings"], NOT state["errors"].
    # state["errors"] is reserved for hard pipeline failures; structural
    # audit findings are advisory/retry-eligible by design. Keeping the two
    # separate fixes the smoke harness's confusing "[PASS] but 7 errors"
    # display (Gemini smoke-review #C reframed).
    #
    # Phase 13-2 Step 4e/4 (Gemini hardening BLOCKER #e): filter previous-
    # round StructureReviewer entries before appending. The retry loop
    # re-runs structure_reviewer 1-3 times, and without this dedup
    # state["warnings"] would accumulate duplicates exponentially —
    # round 3 ends up with 3× copies of any persistent finding, blowing
    # up Writer's advisory-context block via the legacy
    # structure_review_issues path.
    warnings = [
        w for w in (state.get("warnings") or [])
        if not w.startswith("StructureReviewer[")
    ]
    for f in result.findings:
        warnings.append(f"StructureReviewer[{f.category}]: {f.message}")

    return {
        "structure_review_passed": result.passed,
        "structure_review_feedback": result.feedback,
        "structure_review_issues": [f.message for f in result.findings],  # legacy
        "structure_review_findings": result.findings,                     # NEW
        "structure_review_alignment_score": result.branch_alignment_score,
        "structure_review_aligned_branches": result.aligned_branches,
        "warnings": warnings,
    }


def _local_structural_audit(
    script: VNScript, characters: dict
) -> list[StructureFinding]:
    """Cheap pre-LLM checks — catch obvious defects without a Sonnet call.

    Phase 13-2 Step 4e: returns StructureFinding[] with typed categories
    so routing.decide_retry_target can act on them. All findings here are
    source="deterministic" (pure-Python static checks; ~0% false positives).
    """
    findings: list[StructureFinding] = []

    if not script.scenes:
        # Defensive: structure_reviewer's caller already short-circuits
        # on missing script, but if we get here something's badly wrong.
        findings.append(StructureFinding(
            category="advisory", source="deterministic",
            message="script has zero scenes",
            requires_retry=False,
        ))
        return findings

    # 1. Roster efficiency — characters declared in step1 but unused in
    # any scene. STEP1_CATEGORIES per routing.py: triggers step1+step2
    # escalation immediately (per Gemini design review #c — forcing step2
    # to inject a forced cameo degrades narrative quality).
    if characters:
        used_chars = {
            cid for scene in script.scenes for cid in scene.characters_present
        }
        unused = set(characters.keys()) - used_chars
        if unused:
            findings.append(StructureFinding(
                category="roster_unused", source="deterministic",
                message=(
                    f"characters defined but never used in any scene: "
                    f"{sorted(unused)}"
                ),
            ))

    # 2. Strategy variety: flat arc.
    strategies = [s.narrative_strategy for s in script.scenes if s.narrative_strategy]
    if strategies and len(set(strategies)) == 1 and len(strategies) >= 3:
        findings.append(StructureFinding(
            category="strategy_distribution_gap", source="deterministic",
            message=(
                f"all {len(strategies)} scenes use the same strategy "
                f"'{strategies[0]}' — arc is flat"
            ),
        ))

    # 2b. Strategy diversity for longer scripts.
    if len(strategies) >= 5 and len(set(strategies)) < 3:
        findings.append(StructureFinding(
            category="strategy_distribution_gap", source="deterministic",
            message=(
                f"{len(strategies)} scenes but only "
                f"{len(set(strategies))} distinct strategies — "
                f"arc lacks beginning/middle/end contrast"
            ),
        ))

    # 2c. Emotional arc shape: rising or rising-falling expected.
    early_strategies = {"drift", "accumulate"}
    ending_strategies = {"resolve", "uncover", "rupture"}
    if len(strategies) >= 4:
        last = strategies[-1]
        has_ending = any(s in ending_strategies for s in strategies)
        if last in early_strategies and not has_ending:
            findings.append(StructureFinding(
                category="strategy_distribution_gap", source="deterministic",
                message=(
                    f"final scene strategy '{last}' is an opening-type "
                    f"strategy and no ending-type strategy (resolve/uncover/"
                    f"rupture) appears anywhere — story has no landing"
                ),
            ))

    # 3. Non-canonical strategy values. Director typo would re-typo on
    # retry, so mark advisory (don't retry).
    valid = {s.value for s in StrategyType}
    for scene in script.scenes:
        if scene.narrative_strategy and scene.narrative_strategy not in valid:
            findings.append(StructureFinding(
                category="advisory", source="deterministic",
                message=(
                    f"scene '{scene.id}' has non-canonical strategy "
                    f"'{scene.narrative_strategy}' (not in StrategyType enum)"
                ),
                requires_retry=False,
                target_scene_id=scene.id,
            ))

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

    # 5. Phase 13-1 / Step 5: narrative graph validation.
    findings.extend(_check_context_deps(script, characters))

    return findings


def _check_context_deps(script: VNScript, characters: dict) -> list[StructureFinding]:
    """Phase 13-1 / Step 5: validate Director-emitted SceneContextRef entries.

    Phase 13-2 Step 4e: returns StructureFinding[] with categories so
    routing.py can decide which Director step needs to retry. Most
    findings here map to step2-class categories (per-scene context_dep
    is a step2 product). world_var refs to unknown vars map to
    `world_var_undeclared_use` (step2 — scene declared a var the
    declarations don't include, fix is in step2 by removing the use OR
    adding the var to step1; we route to step2_only by default).
    """
    findings: list[StructureFinding] = []

    scene_id_to_index: dict[str, int] = {
        s.id: i for i, s in enumerate(script.scenes)
    }
    valid_character_ids = set((characters or {}).keys())
    valid_world_var_names = {v.name for v in (script.world_variables or [])}
    valid_location_ids = {
        s.background_id for s in script.scenes if s.background_id
    }

    for scene_idx, scene in enumerate(script.scenes):
        deps = getattr(scene, "context_deps", None) or []
        for dep in deps:
            # Self-ref check (scene → itself)
            if dep.ref_type == "scene" and dep.ref_id == scene.id:
                findings.append(StructureFinding(
                    category="advisory", source="deterministic",
                    message=(
                        f"scene '{scene.id}': context_dep ref_id='{dep.ref_id}' "
                        f"self-references — backward-only graph forbids "
                        f"self-loops"
                    ),
                    requires_retry=False,
                    target_scene_id=scene.id,
                ))
                continue

            # ref_id existence + backward-only enforcement by ref_type
            if dep.ref_type == "scene":
                target_idx = scene_id_to_index.get(dep.ref_id)
                if target_idx is None:
                    findings.append(StructureFinding(
                        category="branch_target_invalid",
                        source="deterministic",
                        message=(
                            f"scene '{scene.id}': context_dep ref_id="
                            f"'{dep.ref_id}' points to unknown scene"
                        ),
                        target_scene_id=scene.id,
                    ))
                elif target_idx >= scene_idx:
                    findings.append(StructureFinding(
                        category="advisory", source="deterministic",
                        message=(
                            f"scene '{scene.id}': context_dep ref_id="
                            f"'{dep.ref_id}' is forward/same-scene "
                            f"(target idx {target_idx} ≥ current "
                            f"{scene_idx}) — graph must be backward-only"
                        ),
                        requires_retry=False,
                        target_scene_id=scene.id,
                    ))
            elif dep.ref_type == "character_arc":
                cid = dep.ref_id.split(":", 1)[1] if ":" in dep.ref_id else dep.ref_id
                if cid not in valid_character_ids:
                    findings.append(StructureFinding(
                        category="character_undeclared_use",
                        source="deterministic",
                        message=(
                            f"scene '{scene.id}': context_dep ref_id="
                            f"'{dep.ref_id}' points to unknown character"
                        ),
                        target_scene_id=scene.id,
                        target_character_id=cid,
                    ))
            elif dep.ref_type == "world_var":
                var_name = dep.ref_id.split(":", 1)[1] if ":" in dep.ref_id else dep.ref_id
                if var_name not in valid_world_var_names:
                    findings.append(StructureFinding(
                        category="world_var_undeclared_use",
                        source="deterministic",
                        message=(
                            f"scene '{scene.id}': context_dep ref_id="
                            f"'{dep.ref_id}' points to unknown world_variable"
                        ),
                        target_scene_id=scene.id,
                    ))
                # state_dependency must also be in state_reads
                if (
                    dep.link_type == "state_dependency"
                    and var_name not in (scene.state_reads or [])
                ):
                    findings.append(StructureFinding(
                        category="advisory", source="deterministic",
                        message=(
                            f"scene '{scene.id}': context_dep link_type="
                            f"'state_dependency' for '{var_name}' but it is "
                            f"not in scene.state_reads — symbolic state must "
                            f"agree with graph declaration"
                        ),
                        requires_retry=False,
                        target_scene_id=scene.id,
                    ))
            elif dep.ref_type == "location":
                bg_id = dep.ref_id.split(":", 1)[1] if ":" in dep.ref_id else dep.ref_id
                if bg_id not in valid_location_ids:
                    findings.append(StructureFinding(
                        category="advisory", source="deterministic",
                        message=(
                            f"scene '{scene.id}': context_dep ref_id="
                            f"'{dep.ref_id}' points to unknown "
                            f"location/background_id"
                        ),
                        requires_retry=False,
                        target_scene_id=scene.id,
                    ))
            # motif has no registry yet — Director invents them; accept any id

    return findings


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


def _normalize_finding_dict(d: dict) -> StructureFinding | None:
    """Coerce an LLM-emitted dict into a StructureFinding.

    Two layers of normalization:
      1. Unknown categories (Sonnet inventing labels) -> "advisory".
      2. Phase 13-2 Step 4e/4: categories the LLM is NOT allowed to emit
         (deterministic-only ones like `branch_target_invalid`) also -> "advisory".
         The deterministic audit owns those; allowing LLM to emit them
         would let Sonnet's subjective judgment masquerade as hard graph
         evidence and trigger expensive retries on noisy signals.
    """
    msg = (d.get("message") or "").strip()
    if not msg:
        return None
    category = (d.get("category") or "advisory").strip().lower()
    if category not in _VALID_CATEGORIES:
        logger.debug(
            f"StructureReviewer: unknown LLM category '{category}', "
            f"falling back to 'advisory'"
        )
        category = "advisory"
    elif category not in _LLM_VALID_CATEGORIES:
        logger.debug(
            f"StructureReviewer: LLM emitted deterministic-only category "
            f"'{category}' — coercing to 'advisory'. Use the deterministic "
            f"audit for that category instead."
        )
        category = "advisory"
    requires_retry = bool(d.get("requires_retry", category != "advisory"))
    target_scene_id = d.get("target_scene_id")
    if target_scene_id == "null" or target_scene_id == "":
        target_scene_id = None
    return StructureFinding(
        category=category,  # type: ignore[arg-type]
        source="llm",
        message=msg,
        requires_retry=requires_retry,
        target_scene_id=target_scene_id,
    )


def _parse_audit(
    content: str, local_findings: list[StructureFinding],
) -> StructureReviewResult:
    """Extract JSON verdict. Falls back to local-only findings on parse fail.

    Phase 13-2 Step 4e: returns StructureFinding[] (categorized) instead
    of plain strings. LLM-emitted findings get source="llm"; local pre-
    checks already arrived as source="deterministic".

    Backwards-compat: if the LLM emits the legacy `narrative_issues`
    (list[str]) instead of `narrative_findings` (list[dict]), each
    string becomes an "advisory" finding so we don't lose the signal.
    Sonnet drift in either direction is tolerated.
    """
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
                logger.warning(
                    "StructureReviewer: JSON parse failed, using local "
                    "checks only"
                )
                return StructureReviewResult(
                    passed=not any(f.requires_retry for f in local_findings),
                    feedback="LLM audit JSON unparseable",
                    findings=local_findings,
                )
        else:
            return StructureReviewResult(
                passed=not any(f.requires_retry for f in local_findings),
                feedback="LLM returned no JSON",
                findings=local_findings,
            )

    verdict = (data.get("verdict") or "").upper().strip()
    summary = data.get("summary") or ""
    alignment_score = data.get("branch_alignment_score")
    aligned_branches = data.get("aligned_branches") or []

    # Preferred new shape: narrative_findings (list of dicts with category)
    llm_findings: list[StructureFinding] = []
    raw_findings = data.get("narrative_findings")
    if isinstance(raw_findings, list):
        for d in raw_findings:
            if isinstance(d, dict):
                f = _normalize_finding_dict(d)
                if f is not None:
                    llm_findings.append(f)

    # Backwards-compat: legacy narrative_issues (list[str]).
    raw_issues = data.get("narrative_issues")
    if isinstance(raw_issues, list):
        for msg in raw_issues:
            if isinstance(msg, str) and msg.strip():
                llm_findings.append(StructureFinding(
                    category="advisory", source="llm",
                    message=msg.strip(),
                    requires_retry=False,
                ))

    # Misaligned branches: extract from aligned_branches and surface as
    # discrete findings (category=branch_intent_misalign, requires_retry=True).
    for b in aligned_branches:
        if isinstance(b, dict) and b.get("aligned") is False:
            llm_findings.append(StructureFinding(
                category="branch_intent_misalign",
                source="llm",
                message=(
                    f"branch intent misaligned in scene "
                    f"'{b.get('scene_id', '?')}': "
                    f"'{(b.get('branch_text') or '')[:60]}' — "
                    f"{(b.get('reason') or '')[:120]}"
                ),
                target_scene_id=b.get("scene_id"),
            ))

    all_findings = list(local_findings) + llm_findings
    actionable = [f for f in all_findings if f.requires_retry]
    passed = verdict == "PASS" and not actionable

    return StructureReviewResult(
        passed=passed,
        feedback=summary or ("PASS" if passed else "FAIL"),
        findings=all_findings,
        branch_alignment_score=alignment_score,
        aligned_branches=aligned_branches,
    )
