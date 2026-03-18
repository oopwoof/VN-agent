"""Reviewer Agent: Validates script integrity and coherence."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from vn_agent.agents.state import AgentState
from vn_agent.schema.script import VNScript, Scene
from vn_agent.services.llm import ainvoke_llm
from vn_agent.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a visual novel script reviewer. Your job is to check scripts for:

1. **Structural integrity**: All branch next_scene_ids reference existing scenes
2. **Reachability**: All scenes can be reached from the start scene
3. **Character consistency**: Characters in dialogue are declared in characters_present
4. **Narrative coherence**: The story makes sense and flows naturally
5. **Branch completeness**: No dead ends (every non-final scene has either next_scene_id or branches)

If the script passes all checks, respond with: PASS

If there are issues, list them clearly and suggest specific fixes.
Be concise and actionable.
"""


@dataclass
class ReviewResult:
    passed: bool
    feedback: str
    issues: list[str]


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

    # Then LLM quality check
    quality_result = await _quality_check(script)

    result = quality_result
    logger.info(f"Reviewer result: {'PASS' if result.passed else 'FAIL'} - {result.feedback[:80]}")

    return {
        "review_passed": result.passed,
        "review_feedback": result.feedback,
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

    response = await ainvoke_llm(SYSTEM_PROMPT, user_prompt)
    content = response.content if hasattr(response, 'content') else str(response)

    if "PASS" in content.upper() and len(content.strip()) < 20:
        return ReviewResult(passed=True, feedback="Quality check passed", issues=[])

    return ReviewResult(passed=False, feedback=content, issues=[content])
