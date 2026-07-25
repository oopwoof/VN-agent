"""P4 M0 orchestrator: load a project from disk, walk its branches,
composite a frame per selected node, judge each with the vision LLM,
aggregate, and write `<output_dir>/playtest/report.json`.

Not a LangGraph pipeline node — this is a manual, opt-in post-processing
step invoked against a project that already finished generating (CLI or
web job pipeline), same way `agents/local_regen.py` operates on an
already-built `output_dir`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from vn_agent.playtest.branch_walker import walk_script
from vn_agent.playtest.frame_compositor import composite_frame
from vn_agent.playtest.schema import FrameReportEntry, PlaytestReport, WalkNode, WalkPlan
from vn_agent.playtest.vision_judge import judge_frame
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import VNScript

logger = logging.getLogger(__name__)

_DEFAULT_MAX_FRAMES = 12
_DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"


class PlaytestError(Exception):
    """Raised when the project can't be loaded (missing vn_script.json etc.)."""


def _load_project(output_dir: Path) -> tuple[VNScript, dict[str, CharacterProfile]]:
    script_path = output_dir / "vn_script.json"
    if not script_path.exists():
        raise PlaytestError(f"vn_script.json not found at {script_path}")
    script = VNScript.model_validate_json(script_path.read_text(encoding="utf-8"))

    chars_path = output_dir / "characters.json"
    characters: dict[str, CharacterProfile] = {}
    if chars_path.exists():
        raw = json.loads(chars_path.read_text(encoding="utf-8"))
        characters = {k: CharacterProfile.model_validate(v) for k, v in raw.items()}
    return script, characters


def _select_frames(walk_plan: WalkPlan, max_frames: int) -> tuple[list[WalkNode], int]:
    """Cap frames composited/judged. choice_menu nodes are prioritized (the
    higher-signal nodes for dead-end / player-agency judging); truncation
    drops trailing scene nodes first, while preserving walk order in the
    final report for readability."""
    if len(walk_plan.nodes) <= max_frames:
        return walk_plan.nodes, 0
    choices = [n for n in walk_plan.nodes if n.kind == "choice_menu"]
    scenes = [n for n in walk_plan.nodes if n.kind == "scene"]
    selected = (choices + scenes)[:max_frames]
    order = {n.node_id: i for i, n in enumerate(walk_plan.nodes)}
    selected.sort(key=lambda n: order[n.node_id])
    return selected, len(walk_plan.nodes) - len(selected)


async def run_playtest(
    output_dir: Path | str,
    *,
    llm=None,
    max_frames: int | None = None,
) -> PlaytestReport:
    """Walk `output_dir`'s vn_script.json, composite + judge a bounded set
    of representative frames, write the report, and return it. Raises
    `PlaytestError` only if the project itself can't be loaded — a single
    frame's judge failure degrades that entry (`judgment=None,
    judge_error=...`) rather than aborting the whole run."""
    output_dir = Path(output_dir)
    from vn_agent.config import get_settings
    settings = get_settings()
    resolved_max_frames = (
        max_frames if max_frames is not None
        else getattr(settings, "playtest_max_frames", _DEFAULT_MAX_FRAMES)
    )
    judge_model = getattr(settings, "llm_playtest_judge_model", None) or _DEFAULT_JUDGE_MODEL
    # Mirrors the reviewer_timeout_seconds pattern (v4 P0-review-hang): a
    # single hung vision call must not stall the whole report indefinitely.
    judge_timeout = getattr(settings, "playtest_judge_timeout_seconds", 60.0)

    script, characters = _load_project(output_dir)
    walk_plan = walk_script(script)
    scene_map = {s.id: s for s in script.scenes}
    selected_nodes, frames_skipped = _select_frames(walk_plan, resolved_max_frames)

    entries: list[FrameReportEntry] = []
    for node in selected_nodes:
        scene = scene_map.get(node.scene_id)
        if scene is None:
            continue
        frame_path = composite_frame(node, scene, characters, output_dir, output_dir)
        rel_path = frame_path.relative_to(output_dir).as_posix()
        try:
            judgment = await asyncio.wait_for(
                judge_frame(frame_path, node, llm=llm, model=judge_model),
                timeout=judge_timeout,
            )
            entries.append(FrameReportEntry(
                node_id=node.node_id, scene_id=node.scene_id, kind=node.kind,
                frame_path=rel_path, judgment=judgment,
            ))
        except Exception as e:  # noqa: BLE001 — one bad frame must not kill the whole report
            logger.warning(f"playtest judge failed for node {node.node_id!r}: {e}")
            entries.append(FrameReportEntry(
                node_id=node.node_id, scene_id=node.scene_id, kind=node.kind,
                frame_path=rel_path, judgment=None, judge_error=str(e),
            ))

    report = _aggregate(script, walk_plan, entries, judge_model, frames_skipped)
    write_report(report, output_dir)
    return report


def _aggregate(
    script: VNScript,
    walk_plan: WalkPlan,
    entries: list[FrameReportEntry],
    judge_model: str,
    frames_skipped: int,
) -> PlaytestReport:
    judged = [e for e in entries if e.judgment is not None]
    dims: dict[str, float] = {}
    if judged:
        dims["ui_coherence"] = round(sum(e.judgment.ui_coherence_score for e in judged) / len(judged), 2)
        dims["interactivity_pacing"] = round(
            sum(e.judgment.interactivity_pacing_score for e in judged) / len(judged), 2
        )
        dims["player_agency"] = round(sum(e.judgment.player_agency_score for e in judged) / len(judged), 2)
        dead_end_count = sum(1 for e in judged if e.judgment.dead_end_risk != "none")
        dims["dead_end_risk_pct"] = round(dead_end_count / len(judged), 2)

    total_scenes = len(script.scenes) or 1
    coverage_score = round(len(walk_plan.visited_scene_ids) / total_scenes, 2)
    total_branches = walk_plan.total_declared_branches
    branch_reachability_score = (
        round(walk_plan.reachable_branches / total_branches, 2) if total_branches else 1.0
    )
    dims["coverage"] = coverage_score
    dims["branch_reachability"] = branch_reachability_score

    return PlaytestReport(
        generated_at=datetime.now(UTC).isoformat(),
        script_title=script.title,
        total_scenes=len(script.scenes),
        visited_scenes=len(walk_plan.visited_scene_ids),
        unreachable_scene_ids=walk_plan.unreachable_scene_ids,
        total_declared_branches=walk_plan.total_declared_branches,
        reachable_branches=walk_plan.reachable_branches,
        coverage_score=coverage_score,
        branch_reachability_score=branch_reachability_score,
        dimension_scores=dims,
        frames=entries,
        judge_model=judge_model,
        frames_judged=len(judged),
        frames_skipped=frames_skipped,
    )


def write_report(report: PlaytestReport, output_dir: Path) -> Path:
    path = Path(output_dir) / "playtest" / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path
