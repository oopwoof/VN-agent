"""LangGraph StateGraph pipeline orchestration."""
from __future__ import annotations

import logging
from langgraph.graph import StateGraph, END

from vn_agent.agents.state import AgentState, initial_state
from vn_agent.agents.director import run_director
from vn_agent.agents.writer import run_writer
from vn_agent.agents.reviewer import run_reviewer
from vn_agent.agents.character_designer import run_character_designer
from vn_agent.agents.scene_artist import run_scene_artist
from vn_agent.agents.music_director import run_music_director
from vn_agent.config import get_settings

logger = logging.getLogger(__name__)


def _should_revise(state: AgentState) -> str:
    """Conditional edge: decide whether to revise or proceed."""
    settings = get_settings()

    if state.get("review_passed"):
        logger.info("Reviewer PASSED - proceeding to asset generation")
        return "proceed"

    if state.get("revision_count", 0) >= settings.max_revision_rounds:
        logger.warning(
            f"Max revisions ({settings.max_revision_rounds}) reached - proceeding anyway"
        )
        return "proceed"

    logger.info(f"Reviewer FAILED (round {state.get('revision_count', 0)}) - revising")
    return "revise"


def _after_review(state: AgentState) -> str:
    """Conditional edge after reviewer: text_only goes to END, otherwise asset generation."""
    settings = get_settings()

    # Check if we should revise first
    if not state.get("review_passed") and state.get("revision_count", 0) < settings.max_revision_rounds:
        logger.info(f"Reviewer FAILED (round {state.get('revision_count', 0)}) - revising")
        return "revise"

    if state.get("text_only"):
        logger.info("text_only=True - skipping asset generation, going to END")
        return "end"

    if state.get("review_passed"):
        logger.info("Reviewer PASSED - proceeding to asset generation")
    else:
        logger.warning(
            f"Max revisions ({settings.max_revision_rounds}) reached - proceeding anyway"
        )
    return "proceed"


def build_graph() -> StateGraph:
    """Build the full VN generation pipeline."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("director", run_director)
    graph.add_node("writer", run_writer)
    graph.add_node("reviewer", run_reviewer)
    graph.add_node("character_designer", run_character_designer)
    graph.add_node("scene_artist", run_scene_artist)
    graph.add_node("music_director", run_music_director)

    # Linear flow
    graph.set_entry_point("director")
    graph.add_edge("director", "writer")
    graph.add_edge("writer", "reviewer")

    # Conditional: reviewer either approves (with text_only check), or sends back to writer
    graph.add_conditional_edges(
        "reviewer",
        _after_review,
        {
            "proceed": "character_designer",
            "revise": "writer",
            "end": END,
        },
    )

    # Asset generation pipeline
    graph.add_edge("character_designer", "scene_artist")
    graph.add_edge("scene_artist", "music_director")
    graph.add_edge("music_director", END)

    return graph.compile()


def create_pipeline():
    """Create and return the compiled pipeline."""
    return build_graph()
