"""Phase 13-2 Step 4e: pure-function routing for structure_reviewer findings.

Sits between structure_reviewer and the rest of the pipeline. Decides whether
Director should re-run on outline-level issues, and if so which step to
re-run (step2-only by default, step1+step2 for declaration-level issues).

Why a separate module (instead of letting structure_reviewer or graph.py
own this logic):
  - structure_reviewer's job is judgment ("what's wrong"). Putting routing
    inside it would force its LLM prompt to also reason about pipeline
    structure (step1 vs step2 boundaries) — extra surface for LLM error
    with no information gain since the mapping is currently table-lookup.
  - graph.py's job is wiring. Hardcoding the mapping there mixes policy
    with topology and makes the rules hard to test in isolation.
  - This module is a pure function: easy to exhaustively test, easy to
    swap to "structure_reviewer decides directly" later if the mapping
    grows past simple table lookup.

Decision rules (see decide_retry_target docstring for full table):
  1. No actionable findings → accept (move on)
  2. revision_count ≥ max_revisions → accept (budget exhausted)
  3. revision_count ≥ 1 + only LLM-judged findings remain → accept
     (LLM signal didn't help round 1; round 2 is rolling dice)
  4. Any step1-class finding active → step1_step2 retry
     (declarations need step1 ownership; step2-only would force forced
      cameo / unused-vars retention)
  5. Otherwise → step2_only retry
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vn_agent.schema.script import StructureFinding

# Categories owned by Director step1 (roster / world_vars / macro_reference /
# foreshadow declarations). Findings in these categories require re-running
# step1 to authoritatively change the declaration — step2-only retry would
# either fail to fix the issue or paper over it (e.g. unused character →
# step2 forced to inject a cameo just to satisfy the constraint).
STEP1_CATEGORIES: frozenset[str] = frozenset({
    "roster_unused",
    "world_var_unused",
    "macro_pacing_misaligned",
    "foreshadow_payoff_missing",
})


RouteTarget = Literal["accept", "step2_only", "step1_step2"]


@dataclass(frozen=True)
class RouteDecision:
    target: RouteTarget
    reason: str


def decide_retry_target(
    findings: list[StructureFinding],
    revision_count: int,
    max_revisions: int,
) -> RouteDecision:
    """Decide whether to retry Director, and which step.

    Args:
        findings: All findings from the most recent structure_reviewer pass.
        revision_count: How many Director retries have ALREADY happened (0
            on the first review). Increment AFTER this returns a non-accept
            target and you actually run the retry.
        max_revisions: Hard cap from settings.max_director_revisions.

    Returns:
        RouteDecision with target ∈ {"accept", "step2_only", "step1_step2"}
        and a human-readable reason for logging.

    Decision table:

        | Condition                                       | Target        |
        |-------------------------------------------------|---------------|
        | no findings with requires_retry=True            | accept        |
        | revision_count ≥ max_revisions                  | accept        |
        | revision_count ≥ 1 AND only LLM findings remain | accept        |
        | any step1-class category active                 | step1_step2   |
        | only step2-class categories active              | step2_only    |

    Tier-2 LLM cap rationale: when revision_count ≥ 1 and the only
    remaining actionable findings come from the LLM-judged audit (no
    deterministic findings left), we accept rather than retry. Reasoning:
    if a Sonnet judgment didn't help on round 1, round 2 of the same
    Sonnet on the same prompt rolls dice with no new information.
    Deterministic findings (unused character, broken branch target, etc.)
    are reliable enough to keep retrying — those follow the full
    max_revisions budget.
    """
    actionable = [f for f in findings if f.requires_retry]
    if not actionable:
        return RouteDecision("accept", "no actionable findings")

    if revision_count >= max_revisions:
        return RouteDecision(
            "accept",
            f"max retries hit ({revision_count}/{max_revisions})",
        )

    if revision_count >= 1:
        actionable = [f for f in actionable if f.source == "deterministic"]
        if not actionable:
            return RouteDecision(
                "accept",
                "round 2: only LLM-judged findings remain — skipping retry "
                "(LLM signal didn't help on round 1)",
            )

    step1_active = [f for f in actionable if f.category in STEP1_CATEGORIES]
    if step1_active:
        cats = sorted({f.category for f in step1_active})
        return RouteDecision(
            "step1_step2",
            f"step1-class findings active: {cats}",
        )

    cats = sorted({f.category for f in actionable})
    return RouteDecision(
        "step2_only",
        f"step2-class findings active: {cats}",
    )
