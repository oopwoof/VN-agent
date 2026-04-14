"""LangGraph StateGraph pipeline orchestration."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from langgraph.graph import END, StateGraph

from vn_agent.agents.character_designer import run_character_designer
from vn_agent.agents.director import run_director
from vn_agent.agents.music_director import run_music_director
from vn_agent.agents.reviewer import run_reviewer
from vn_agent.agents.scene_artist import run_scene_artist
from vn_agent.agents.state import AgentState
from vn_agent.agents.state_orchestrator import run_state_orchestrator
from vn_agent.agents.structure_reviewer import run_structure_reviewer
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


async def _run_assets_parallel(state: AgentState) -> dict:
    """Run character_designer, scene_artist, and music_director concurrently.

    Each sub-agent gets its own trace span. Failures are collected as errors
    rather than crashing the pipeline (fault isolation).
    """
    trace = get_trace()

    async def _traced(name: str, func):
        t_in = token_tracker.total_input()
        t_out = token_tracker.total_output()
        with trace.span(name) as span:
            result = await func(state)
            span.set_attribute("input_tokens", token_tracker.total_input() - t_in)
            span.set_attribute("output_tokens", token_tracker.total_output() - t_out)
            return result

    results = await asyncio.gather(
        _traced("character_designer", run_character_designer),
        _traced("scene_artist", run_scene_artist),
        _traced("music_director", run_music_director),
        return_exceptions=True,
    )

    merged: dict = {}
    errors = list(state.get("errors", []))
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            agent_name = ["character_designer", "scene_artist", "music_director"][i]
            logger.error(f"Asset agent {agent_name} failed: {r}")
            errors.append(f"{agent_name}: {r}")
        elif isinstance(r, dict):
            merged.update(r)
    merged["errors"] = errors
    return merged


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


def build_graph():  # type: ignore[return]
    """Build the full VN generation pipeline.

    Topology (Sprint 9-6 state-aware):
        director → structure_reviewer → state_orchestrator → writer → reviewer ─┬─ PASS → assets → END
                                                               ↑                 ├─ FAIL → writer  (revision loop)
                                                               └─────────────────┘  end  → END     (text_only)

    - structure_reviewer (Sonnet): audits outline BEFORE writer — branch
      intent alignment, strategy distribution, narrative shape. Non-blocking
      by default; feedback lands in state for writer context and errors.
    - reviewer (Haiku, Sprint 7-5 revert): audits dialogue AFTER writer —
      mechanical format + keyword + rubric checks.

    asset_generation runs character_designer, scene_artist, and music_director
    concurrently via asyncio.gather with per-agent fault isolation.
    """
    graph = StateGraph(AgentState)  # type: ignore[type-var]

    # Core pipeline nodes (traced individually)
    graph.add_node("director", _make_traced_node("director", run_director))  # type: ignore[call-overload]
    graph.add_node(  # type: ignore[call-overload]
        "structure_reviewer",
        _make_traced_node("structure_reviewer", run_structure_reviewer),
    )
    graph.add_node(  # type: ignore[call-overload]
        "state_orchestrator",
        _make_traced_node("state_orchestrator", run_state_orchestrator),
    )
    graph.add_node("writer", _make_traced_node("writer", run_writer))  # type: ignore[call-overload]
    graph.add_node("reviewer", _make_traced_node("reviewer", run_reviewer))  # type: ignore[call-overload]

    # Parallel asset generation (3 sub-agents run concurrently inside one node)
    graph.add_node("asset_generation", _run_assets_parallel)  # type: ignore[call-overload]

    # Linear flow: director → structure_reviewer → writer → reviewer
    graph.set_entry_point("director")
    graph.add_edge("director", "structure_reviewer")
    graph.add_edge("structure_reviewer", "state_orchestrator")
    graph.add_edge("state_orchestrator", "writer")
    graph.add_edge("writer", "reviewer")

    # Conditional: reviewer either approves (with text_only check), or sends back to writer
    graph.add_conditional_edges(
        "reviewer",
        _after_review,
        {
            "proceed": "asset_generation",
            "revise": "writer",
            "end": END,
        },
    )

    # Asset generation → END
    graph.add_edge("asset_generation", END)

    return graph.compile()


def create_pipeline():
    """Create and return the compiled pipeline."""
    return build_graph()


def build_writer_graph():  # type: ignore[return]
    """Sprint 12-3: resume-from-outline graph — skips Director/structure/state.

    Entry at `writer`. Assumes vn_script, characters, world_state, and
    state_constraints are pre-populated in state by the caller (loaded
    from disk after a creator pauses-for-outline run). Same writer →
    reviewer → (revise|assets|end) topology as the full graph so
    revision loops and text_only still work identically.
    """
    graph = StateGraph(AgentState)  # type: ignore[type-var]

    graph.add_node("writer", _make_traced_node("writer", run_writer))  # type: ignore[call-overload]
    graph.add_node("reviewer", _make_traced_node("reviewer", run_reviewer))  # type: ignore[call-overload]
    graph.add_node("asset_generation", _run_assets_parallel)  # type: ignore[call-overload]

    graph.set_entry_point("writer")
    graph.add_edge("writer", "reviewer")
    graph.add_conditional_edges(
        "reviewer",
        _after_review,
        {
            "proceed": "asset_generation",
            "revise": "writer",
            "end": END,
        },
    )
    graph.add_edge("asset_generation", END)

    return graph.compile()
