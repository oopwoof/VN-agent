"""Reviewer Agent: Validates script integrity and coherence."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from vn_agent.agents.state import AgentState
from vn_agent.config import get_settings
from vn_agent.prompts.templates import REVIEWER_SYSTEM, strip_thinking
from vn_agent.schema.script import VNScript
from vn_agent.services.llm import ainvoke_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = REVIEWER_SYSTEM


@dataclass
class ReviewResult:
    passed: bool
    feedback: str
    issues: list[str]
    scores: dict[str, float] | None = None  # {coherence, voice, arc, branches, pacing, avg}


async def run_reviewer(state: AgentState) -> dict:
    """Reviewer node: validates the current script."""
    script = state["vn_script"]
    if not script:
        return {
            "review_passed": False,
            "review_feedback": "No script to review",
            "revision_count": state.get("revision_count", 0) + 1,
        }

    # First run structural checks (fast, no LLM needed)
    structural_result = _structural_check(script)

    if not structural_result.passed:
        logger.info(f"Reviewer found {len(structural_result.issues)} structural issues")
        return {
            "review_passed": False,
            "review_feedback": structural_result.feedback,
            "revision_count": state.get("revision_count", 0) + 1,
        }

    # Then LLM quality check (can be skipped for budget-sensitive runs)
    settings = get_settings()
    if settings.reviewer_skip_llm:
        logger.info("Reviewer: skipping LLM quality check (reviewer_skip_llm=True)")
        result = structural_result
    else:
        quality_result = await _quality_check(script)
        result = quality_result
    # Strategy consistency check (warnings only, non-blocking)
    strategy_warnings = check_strategy_consistency(script)
    if strategy_warnings:
        for w in strategy_warnings:
            logger.warning(f"Strategy consistency: {w}")

    feedback = result.feedback
    if strategy_warnings:
        feedback += "\n\nStrategy consistency warnings:\n" + "\n".join(f"- {w}" for w in strategy_warnings)

    if result.scores:
        logger.info(f"Reviewer scores: {result.scores}")
    logger.info(f"Reviewer result: {'PASS' if result.passed else 'FAIL'} - {result.feedback[:80]}")

    return {
        "review_passed": result.passed,
        "review_feedback": feedback,
        "review_scores": result.scores,
        "revision_count": state.get("revision_count", 0) + 1,
    }


def _structural_check(script: VNScript) -> ReviewResult:
    """Fast structural validation without LLM."""
    issues = []
    scene_ids = {s.id for s in script.scenes}

    # Check start scene exists
    if script.start_scene_id not in scene_ids:
        issues.append(f"Start scene '{script.start_scene_id}' not found in scenes")

    # Check all branch references
    for scene in script.scenes:
        for branch in scene.branches:
            if branch.next_scene_id not in scene_ids:
                issues.append(
                    f"Scene '{scene.id}': branch '{branch.text}' references "
                    f"non-existent scene '{branch.next_scene_id}'"
                )
        if scene.next_scene_id and scene.next_scene_id not in scene_ids:
            issues.append(
                f"Scene '{scene.id}': next_scene_id '{scene.next_scene_id}' does not exist"
            )

    # Check reachability (BFS from start)
    reachable = _find_reachable_scenes(script)
    unreachable = scene_ids - reachable
    if unreachable:
        issues.append(f"Unreachable scenes: {', '.join(sorted(unreachable))}")

    # Note: scenes with no exit (no next_scene_id, no branches) are valid terminal endings

    # Check character consistency
    declared_chars = {c.id if hasattr(c, 'id') else c for c in script.characters}
    for scene in script.scenes:
        for line in scene.dialogue:
            if line.character_id and line.character_id not in declared_chars:
                issues.append(
                    f"Scene '{scene.id}': character '{line.character_id}' speaks but is not declared"
                )

    if issues:
        feedback = "Structural issues found:\n" + "\n".join(f"- {i}" for i in issues)
        return ReviewResult(passed=False, feedback=feedback, issues=issues)

    return ReviewResult(passed=True, feedback="Structural checks passed", issues=[])


def _find_reachable_scenes(script: VNScript) -> set[str]:
    """BFS to find all scenes reachable from start."""
    reachable = set()
    queue = [script.start_scene_id]
    scene_map = {s.id: s for s in script.scenes}

    while queue:
        scene_id = queue.pop(0)
        if scene_id in reachable or scene_id not in scene_map:
            continue
        reachable.add(scene_id)
        scene = scene_map[scene_id]
        if scene.next_scene_id:
            queue.append(scene.next_scene_id)
        for branch in scene.branches:
            queue.append(branch.next_scene_id)

    return reachable


async def _quality_check(script: VNScript) -> ReviewResult:
    """LLM-based quality check for narrative coherence."""
    # Build script summary for review
    scene_summary = []
    for scene in script.scenes:
        exits = []
        if scene.next_scene_id:
            exits.append(f"→ {scene.next_scene_id}")
        for b in scene.branches:
            exits.append(f"[{b.text}] → {b.next_scene_id}")

        dialogue_preview = " | ".join(
            f"{d.character_id or 'NARR'}: {d.text[:40]}"
            for d in scene.dialogue[:3]
        )

        scene_summary.append(
            f"{scene.id} ({scene.title}): {scene.description[:60]} | "
            f"Dialogue: {dialogue_preview} | Exits: {', '.join(exits)}"
        )

    user_prompt = f"""Review this visual novel script:

Title: {script.title}
Theme: {script.theme}
Scenes: {len(script.scenes)}

{chr(10).join(scene_summary)}

Check for:
1. Narrative coherence (does the story make sense?)
2. Character consistency (do characters behave consistently?)
3. Pacing (is the story well-paced?)
4. Branch meaningfulness (do choices matter?)

If all good, respond ONLY with: PASS
If issues found, list them clearly."""

    settings = get_settings()
    response = await ainvoke_llm(SYSTEM_PROMPT, user_prompt, model=settings.llm_reviewer_model, caller="reviewer")
    content = response.content if hasattr(response, 'content') else str(response)
    content = strip_thinking(content)

    stripped = content.strip()
    first_line = stripped.split("\n", 1)[0].strip().upper()

    # Parse numeric scores if present (format: coherence=X voice=X arc=X branches=X pacing=X avg=X.X)
    scores = _parse_scores(stripped)

    has_issues = "\n-" in stripped or "\n*" in stripped or "\n1." in stripped
    is_pass = first_line.startswith("PASS") and not has_issues

    if is_pass:
        return ReviewResult(passed=True, feedback="Quality check passed", issues=[], scores=scores)

    return ReviewResult(passed=False, feedback=content, issues=[content], scores=scores)


def _parse_scores(text: str) -> dict[str, float] | None:
    """Extract reviewer rubric scores from response text."""
    import re as _re

    scores: dict[str, float] = {}
    # Match patterns like "coherence=4" or "coherence: 4" or "Narrative Coherence (4/5)"
    for key, patterns in {
        "coherence": [r"coherence[=:\s]+(\d+(?:\.\d+)?)", r"narrative coherence[^0-9]*(\d+)"],
        "voice": [r"voice[=:\s]+(\d+(?:\.\d+)?)", r"character voice[^0-9]*(\d+)"],
        "arc": [r"arc[=:\s]+(\d+(?:\.\d+)?)", r"emotional arc[^0-9]*(\d+)"],
        "branches": [r"branches[=:\s]+(\d+(?:\.\d+)?)", r"branch quality[^0-9]*(\d+)"],
        "pacing": [r"pacing[=:\s]+(\d+(?:\.\d+)?)", r"pacing[^0-9]*(\d+)"],
    }.items():
        for pattern in patterns:
            m = _re.search(pattern, text, _re.IGNORECASE)
            if m:
                scores[key] = float(m.group(1))
                break

    if not scores:
        return None

    # Compute average if we have at least 3 dimensions
    if len(scores) >= 3:
        scores["avg"] = round(sum(scores.values()) / len(scores), 2)

    return scores


# ── Strategy consistency check (non-blocking warnings) ─────────────────────

_STRATEGY_KEYWORDS: dict[str, list[str]] = {
    "accumulate": ["build", "layer", "gradual", "slowly", "growing", "deepen"],
    "erode": ["doubt", "wear", "crumble", "fade", "lose", "weaken"],
    "rupture": ["sudden", "shock", "break", "snap", "explosion", "shatter"],
    "reveal": ["secret", "hidden", "discover", "truth", "uncover", "realize"],
    "contrast": ["contrast", "opposite", "juxtapose", "versus", "conflict", "clash"],
    "weave": ["thread", "parallel", "interleave", "drift", "wander", "connect"],
    "escalate": ["escalate", "intensify", "raise", "stakes", "pressure", "urgent"],
    "resolve": ["resolve", "closure", "peace", "reconcile", "settle", "end"],
}


def check_strategy_consistency(script: VNScript) -> list[str]:
    """Check if scene dialogue loosely matches the assigned narrative strategy.

    Returns a list of warning strings (non-blocking).
    """
    warnings: list[str] = []
    for scene in script.scenes:
        strategy = scene.narrative_strategy
        if not strategy or strategy not in _STRATEGY_KEYWORDS:
            continue

        keywords = _STRATEGY_KEYWORDS[strategy]
        dialogue_text = " ".join(line.text.lower() for line in scene.dialogue)

        hits = sum(1 for kw in keywords if kw in dialogue_text)
        if hits == 0 and len(scene.dialogue) >= 3:
            warnings.append(
                f"Scene '{scene.id}': strategy '{strategy}' assigned but no matching "
                f"keywords found in dialogue ({len(scene.dialogue)} lines)"
            )

    return warnings
