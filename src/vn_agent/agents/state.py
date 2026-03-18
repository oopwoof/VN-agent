"""LangGraph shared state TypedDict for VN-Agent pipeline."""
from __future__ import annotations

from typing import Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from vn_agent.schema.script import VNScript
from vn_agent.schema.character import CharacterProfile


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
    """
    theme: str
    vn_script: VNScript | None
    characters: dict[str, CharacterProfile]  # character_id -> profile
    revision_count: int
    review_passed: bool
    review_feedback: str
    assets_generated: bool
    output_dir: str
    messages: Annotated[list[BaseMessage], add_messages]
    errors: list[str]


def initial_state(theme: str, output_dir: str) -> dict:
    """Create the initial state for a new VN generation pipeline."""
    return {
        "theme": theme,
        "vn_script": None,
        "characters": {},
        "revision_count": 0,
        "review_passed": False,
        "review_feedback": "",
        "assets_generated": False,
        "output_dir": output_dir,
        "messages": [],
        "errors": [],
    }
