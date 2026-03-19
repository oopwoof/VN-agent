"""LangGraph StateGraph pipeline orchestration."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from langgraph.graph import END, StateGraph

from vn_agent.agents.character_designer import run_character_designer
from vn_agent.agents.director import run_director
from vn_agent.agents.music_director import run_music_director
from vn_agent.agents.reviewer import run_reviewer
from vn_agent.agents.scene_artist import run_scene_artist
from vn_agent.agents.state import AgentState
from vn_agent.agents.writer import run_writer
from vn_agent.config import get_settings
from vn_agent.observability.tracing import get_trace
from vn_agent.services.token_tracker import tracker as token_tracker

logger = logging.getLogger(__name__)


def _make_traced_node(
    name: str, func: Callable[[AgentState], Awaitable[dict]]
) -> Callable[[AgentState], Awaitable[dict]]:
    """Wrap an agent node function with trace span recording."""

    async def traced(state: AgentState) -> dict:
        trace = get_trace()
        # Snapshot token count before
        tokens_before_in = token_tracker.total_input()
        tokens_before_out = token_tracker.total_output()

        with trace.span(name) as span:
            result = await func(state)
            # Record tokens used by this node
            span.set_attribute("input_tokens", token_tracker.total_input() - tokens_before_in)
            span.set_attribute("output_tokens", token_tracker.total_output() - tokens_before_out)
            return result

    return traced


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
    revision_count = state.get("revision_count", 0)
    if not state.get("review_passed") and revision_count < settings.max_revision_rounds:
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

    # Add traced nodes
    graph.add_node("director", _make_traced_node("director", run_director))
    graph.add_node("writer", _make_traced_node("writer", run_writer))
    graph.add_node("reviewer", _make_traced_node("reviewer", run_reviewer))
    graph.add_node(
        "character_designer", _make_traced_node("character_designer", run_character_designer)
    )
    graph.add_node("scene_artist", _make_traced_node("scene_artist", run_scene_artist))
    graph.add_node("music_director", _make_traced_node("music_director", run_music_director))

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
