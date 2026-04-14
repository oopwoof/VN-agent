"""LangGraph shared state TypedDict for VN-Agent pipeline."""
from __future__ import annotations

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import VNScript


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
    structure_review_passed: bool
    structure_review_feedback: str
    structure_review_issues: list[str]
    assets_generated: bool
    output_dir: str
    messages: Annotated[list[BaseMessage], add_messages]
    errors: list[str]
    text_only: bool
    max_scenes: int
    num_characters: int
    art_direction: str


def initial_state(
    theme: str,
    output_dir: str,
    text_only: bool = False,
    max_scenes: int = 10,
    num_characters: int = 3,
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
        "assets_generated": False,
        "output_dir": output_dir,
        "messages": [],
        "errors": [],
        "text_only": text_only,
        "max_scenes": max_scenes,
        "num_characters": num_characters,
        "art_direction": "",
    }
