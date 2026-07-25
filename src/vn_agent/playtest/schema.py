"""Pydantic models for the P4 PlaytestAgent pipeline: walk plan → composited
frames → per-frame vision judgment → aggregated report."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WalkNode(BaseModel):
    """One stop on the branch walker's traversal — either a scene (renders
    its dialogue) or a choice menu (renders the branch options at a scene's
    exit). `node_id` is `<scene_id>` for scenes, `<scene_id>::choice` for
    the choice-menu node emitted when a scene has branches."""

    node_id: str
    scene_id: str
    scene_title: str
    kind: Literal["scene", "choice_menu"]
    dialogue_excerpt: list[str] = Field(
        default_factory=list,
        description="Up to 3 'speaker (emotion): text' lines representative of this scene.",
    )
    choice_texts: list[str] = Field(default_factory=list, description="kind=='choice_menu' only")
    locked_choice_texts: list[str] = Field(
        default_factory=list,
        description="Declared branch texts whose `requires` gate is NOT met by this path's "
                    "world_state — rendered dimmed/locked rather than omitted.",
    )
    world_state: dict = Field(default_factory=dict)
    reachable: bool = True
    unreachable_reason: str | None = None


class WalkPlan(BaseModel):
    nodes: list[WalkNode]
    visited_scene_ids: list[str]
    unreachable_scene_ids: list[str]
    total_scenes: int
    total_declared_branches: int
    reachable_branches: int


class PlaytestFrameFinding(BaseModel):
    category: Literal["ui_coherence", "dead_end", "pacing", "player_agency", "advisory"]
    message: str = Field(max_length=200)
    severity: Literal["info", "warning", "critical"] = "info"


class PlaytestFrameJudgment(BaseModel):
    """Structured vision-judge output for one composited frame."""

    ui_coherence_score: int = Field(ge=1, le=5)
    dead_end_risk: Literal["none", "low", "high"]
    interactivity_pacing_score: int = Field(ge=1, le=5)
    player_agency_score: int = Field(ge=1, le=5)
    findings: list[PlaytestFrameFinding] = Field(default_factory=list, max_length=5)
    summary: str = Field(max_length=300)


class FrameReportEntry(BaseModel):
    node_id: str
    scene_id: str
    kind: Literal["scene", "choice_menu"]
    frame_path: str = Field(description="Relative to output_dir, e.g. 'playtest/frames/scene_1.png'")
    judgment: PlaytestFrameJudgment | None = None
    judge_error: str | None = None


class PlaytestReport(BaseModel):
    generated_at: str
    script_title: str
    total_scenes: int
    visited_scenes: int
    unreachable_scene_ids: list[str]
    total_declared_branches: int
    reachable_branches: int
    coverage_score: float = Field(description="visited_scenes / total_scenes")
    branch_reachability_score: float = Field(
        description="reachable_branches / total_declared_branches; 1.0 if none declared"
    )
    dimension_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Averaged across judged frames: ui_coherence, dead_end_risk_pct "
                    "(share of frames with dead_end_risk != 'none'), interactivity_pacing, "
                    "player_agency — plus the deterministic coverage/branch_reachability.",
    )
    frames: list[FrameReportEntry] = Field(default_factory=list)
    judge_model: str = ""
    frames_judged: int = 0
    frames_skipped: int = Field(default=0, description="Nodes truncated by playtest_max_frames")
