"""LangGraph shared state TypedDict for VN-Agent pipeline."""
from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import StructureFinding, VNScript


class AgentState(dict):
    """
    Shared state passed between all agents in the LangGraph pipeline.

    Fields:
        theme: Original user-provided story theme
        vn_script: Current VNScript (updated by Writer, Reviewer)
        characters: Character profiles (updated by CharacterDesigner)
        revision_count: How many revision rounds completed
        review_passed: Whether the last Reviewer check passed
        review_feedback: Feedback from last Reviewer run
        assets_generated: Whether multimodal assets are ready
        output_dir: Target output directory for compiled project
        messages: LangGraph message history (for debugging)
        errors: List of non-fatal errors encountered
        text_only: Skip image and music generation when True
        max_scenes: Maximum number of scenes to generate
        num_characters: Number of characters to create
        art_direction: Global art style shared across all asset agents
    """
    theme: str
    vn_script: VNScript | None
    characters: dict[str, CharacterProfile]  # character_id -> profile
    revision_count: int
    review_passed: bool
    review_feedback: str
    review_scores: dict | None
    # Sprint 7-5: structure-reviewer (pre-Writer audit) results. Informational
    # for Writer context, non-blocking by default.
    # Phase 13-2 Step 4e: structured findings (typed categories) populated
    # alongside the legacy issues list. routing.decide_retry_target consumes
    # findings to decide whether Director should re-run.
    structure_review_passed: bool
    structure_review_feedback: str
    structure_review_issues: list[str]              # legacy: just messages
    structure_review_findings: list[StructureFinding]  # NEW: categorized
    # Phase 13-2 Step 4e: how many Director retries triggered by
    # structure_reviewer findings have already happened. Capped at
    # settings.max_director_revisions.
    director_revision_count: int
    assets_generated: bool
    output_dir: str
    messages: Annotated[list[BaseMessage], add_messages]
    errors: list[str]
    # Phase 13-2 Step 4e: non-blocking findings (advisory + post-budget
    # un-fixable). Smoke harness reports these separately from `errors`
    # so a [PASS] run with structural warnings doesn't read as a failure.
    warnings: list[str]
    text_only: bool
    max_scenes: int
    num_characters: int
    art_direction: str
    # Sprint 9-1: live symbolic state — populated from
    # VNScript.world_variables at init time, mutated by each scene's
    # state_writes, consumed by StateOrchestrator (9-6) to compile
    # narrative constraints for Writer.
    world_state: dict[str, Any]
    # Sprint 9-6: compiled constraint text from StateOrchestrator.
    # Written by structure_orchestrator node, read by Writer.
    state_constraints: str
    # Sprint 12-5: when reviewer FAILs because dialogue references
    # a character_id that isn't in the cast, this carries structured
    # metadata so a creator-mode UI can offer auto-fill or cast-editor
    # workflows instead of making the creator re-open the JSON.
    unknown_characters: list[dict]
    # v4 P0: web-job identity for cross-agent lookups (uploaded RAG chunks,
    # asset library provenance, etc.). None when running from CLI or tests.
    # Populated by web/app.py at pipeline entry; agents check-and-fallback
    # so CLI paths continue to work with zero user-upload lookup.
    job_id: str | None


def initial_state(
    theme: str,
    output_dir: str,
    text_only: bool = False,
    max_scenes: int = 10,
    num_characters: int = 3,
    job_id: str | None = None,
) -> dict:
    """Create the initial state for a new VN generation pipeline."""
    return {
        "theme": theme,
        "vn_script": None,
        "characters": {},
        "revision_count": 0,
        "review_passed": False,
        "review_feedback": "",
        "structure_review_passed": False,
        "structure_review_feedback": "",
        "structure_review_issues": [],
        "structure_review_findings": [],
        "director_revision_count": 0,
        "assets_generated": False,
        "output_dir": output_dir,
        "messages": [],
        "errors": [],
        "warnings": [],
        "text_only": text_only,
        "max_scenes": max_scenes,
        "num_characters": num_characters,
        "art_direction": "",
        "world_state": {},
        "state_constraints": "",
        "unknown_characters": [],
        "job_id": job_id,
    }
