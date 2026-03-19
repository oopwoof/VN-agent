"""End-to-end pipeline quality evaluator for generated VN scripts."""
from __future__ import annotations

import logging
import re

from vn_agent.agents.reviewer import _find_reachable_scenes, _structural_check
from vn_agent.schema.script import VNScript

logger = logging.getLogger(__name__)


def evaluate_pipeline_output(script: VNScript, token_usage: dict | None = None) -> dict:
    """Evaluate a generated VN script across multiple quality dimensions.

    Args:
        script: The generated VNScript to evaluate.
        token_usage: Optional dict with 'total_input', 'total_output' token counts.

    Returns:
        Dict with keys: structural, dialogue, strategy, cost.
    """
    return {
        "structural": _eval_structural(script),
        "dialogue": _eval_dialogue(script),
        "strategy": _eval_strategy(script),
        "cost": _eval_cost(script, token_usage),
    }


def _eval_structural(script: VNScript) -> dict:
    """Structural integrity checks."""
    result = _structural_check(script)
    reachable = _find_reachable_scenes(script)
    total_scenes = len(script.scenes)
    scene_ids = {s.id for s in script.scenes}

    # Count valid branch targets
    total_branches = 0
    valid_branches = 0
    for s in script.scenes:
        for b in s.branches:
            total_branches += 1
            if b.next_scene_id in scene_ids:
                valid_branches += 1

    return {
        "passed": result.passed,
        "issues": result.issues,
        "total_scenes": total_scenes,
        "reachable_scenes": len(reachable),
        "reachability_ratio": len(reachable) / total_scenes if total_scenes else 0.0,
        "total_branches": total_branches,
        "valid_branches": valid_branches,
    }


def _eval_dialogue(script: VNScript) -> dict:
    """Dialogue quality metrics."""
    line_counts = []
    has_cjk = []

    for scene in script.scenes:
        line_counts.append(len(scene.dialogue))
        for line in scene.dialogue:
            has_cjk.append(bool(re.search(r"[\u4e00-\u9fff]", line.text)))

    total_lines = sum(line_counts)
    avg_lines = total_lines / len(line_counts) if line_counts else 0.0
    cjk_ratio = sum(has_cjk) / len(has_cjk) if has_cjk else 0.0

    # Language consistency: either mostly CJK or mostly non-CJK
    lang_consistent = cjk_ratio > 0.8 or cjk_ratio < 0.2

    return {
        "total_lines": total_lines,
        "avg_lines_per_scene": round(avg_lines, 1),
        "min_lines": min(line_counts) if line_counts else 0,
        "max_lines": max(line_counts) if line_counts else 0,
        "cjk_ratio": round(cjk_ratio, 2),
        "language_consistent": lang_consistent,
    }


def _eval_strategy(script: VNScript) -> dict:
    """Strategy assignment coverage."""
    strategies = [s.narrative_strategy for s in script.scenes]
    assigned = sum(1 for s in strategies if s)
    unique = set(s for s in strategies if s)

    return {
        "assigned_ratio": round(assigned / len(strategies), 2) if strategies else 0.0,
        "unique_strategies": sorted(unique),
        "strategy_diversity": len(unique),
    }


def _eval_cost(script: VNScript, token_usage: dict | None) -> dict:
    """Cost efficiency metrics."""
    num_scenes = len(script.scenes)
    if not token_usage:
        return {"tokens_per_scene": None, "total_tokens": None}

    total = token_usage.get("total_input", 0) + token_usage.get("total_output", 0)
    return {
        "tokens_per_scene": round(total / num_scenes) if num_scenes else 0,
        "total_tokens": total,
    }


def format_pipeline_report(metrics: dict) -> str:
    """Format pipeline evaluation as a readable report."""
    lines = ["Pipeline Quality Report", "=" * 40]

    s = metrics["structural"]
    lines.append(f"\nStructural: {'PASS' if s['passed'] else 'FAIL'}")
    lines.append(f"  Scenes: {s['total_scenes']} total, {s['reachable_scenes']} reachable")
    lines.append(f"  Branches: {s['valid_branches']}/{s['total_branches']} valid")
    if s["issues"]:
        for issue in s["issues"]:
            lines.append(f"  ! {issue}")

    d = metrics["dialogue"]
    lines.append("\nDialogue:")
    lines.append(f"  Total lines: {d['total_lines']}, avg {d['avg_lines_per_scene']}/scene")
    lines.append(f"  Range: {d['min_lines']}-{d['max_lines']} lines/scene")
    lines.append(f"  Language consistent: {d['language_consistent']} (CJK ratio: {d['cjk_ratio']})")

    st = metrics["strategy"]
    lines.append("\nStrategy:")
    lines.append(f"  Assigned: {st['assigned_ratio']:.0%} of scenes")
    lines.append(f"  Diversity: {st['strategy_diversity']} unique strategies")

    c = metrics["cost"]
    if c.get("total_tokens"):
        lines.append("\nCost:")
        lines.append(f"  Total tokens: {c['total_tokens']:,}")
        lines.append(f"  Per scene: {c['tokens_per_scene']:,}")

    return "\n".join(lines)
