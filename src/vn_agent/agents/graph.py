"""LangGraph StateGraph pipeline orchestration."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from langgraph.graph import END, StateGraph

from vn_agent.agents.character_designer import run_character_designer
from vn_agent.agents.director import (
    run_director,
    run_director_full_redo,
    run_director_step2_redo,
)
from vn_agent.agents.music_director import run_music_director
from vn_agent.agents.reviewer import run_reviewer
from vn_agent.agents.routing import decide_retry_target
from vn_agent.agents.scene_artist import run_scene_artist
from vn_agent.agents.state import AgentState
from vn_agent.agents.state_orchestrator import run_state_orchestrator
from vn_agent.agents.structure_reviewer import run_structure_reviewer
from vn_agent.agents.thinking import run_cross_ref_sync, run_thinking_fanout
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


def _after_structure_review(state: AgentState) -> str:
    """Phase 13-2 Step 4e: route on structure_reviewer findings.

    Calls vn_agent.agents.routing.decide_retry_target with the typed
    findings + revision_count + max_director_revisions cap. Returns the
    edge label graph.add_conditional_edges dispatches on:

      "accept"       -> state_orchestrator (proceed normally)
      "step2_only"   -> director_step2_redo (re-run step2 only)
      "step1_step2"  -> director_full_redo  (re-run both steps)

    Pre-Step-4e topology: structure_reviewer -> state_orchestrator
    (advisory only). Now structural failures actually cycle back to
    Director instead of being silently passed through to Writer (which
    can't fix scene-graph defects anyway — Gemini smoke-review #C).
    """
    settings = get_settings()
    findings = state.get("structure_review_findings", []) or []
    revision_count = state.get("director_revision_count", 0)
    decision = decide_retry_target(
        findings,
        revision_count=revision_count,
        max_revisions=settings.max_director_revisions,
    )
    if decision.target == "accept":
        if findings:
            logger.info(
                f"StructureReviewer findings accepted "
                f"(rev={revision_count}/{settings.max_director_revisions}): "
                f"{decision.reason}"
            )
        return "accept"
    logger.info(
        f"StructureReviewer triggering Director {decision.target} "
        f"(rev={revision_count} -> {revision_count + 1}): "
        f"{decision.reason}"
    )
    return decision.target


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

    Topology (Phase 13-2 Steps 2-3: thinking + cross_ref_sync in front of writer):
        director → structure_reviewer → state_orchestrator
            → thinking_fanout → cross_ref_sync → writer
            → reviewer ─┬─ PASS → assets → END
                        ├─ FAIL → writer  (revision loop)
                        └─ end  → END     (text_only)

    - structure_reviewer (Sonnet): audits outline BEFORE writer — branch
      intent alignment, strategy distribution, narrative shape. Non-blocking
      by default; feedback lands in state for writer context and errors.
    - thinking_fanout (Haiku, route-4 Step 2): per-scene creative planning
      artifact. Gated off by default (enable_thinking_fanout) and by scene
      count. No-op pass-through otherwise.
    - cross_ref_sync (Haiku, route-4 Step 3): one-shot revision pass where
      each scene sees its context_deps' thinking and adjusts. Emits
      cross_ref_conflicts.jsonl when callback collisions survive the
      revision. Also gated off by default. Step 4 will parallelize.
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
    # Phase 13-2 Step 4e: Director retry nodes triggered by routing
    # decision after structure_reviewer flags actionable findings.
    graph.add_node(  # type: ignore[call-overload]
        "director_step2_redo",
        _make_traced_node("director_step2_redo", run_director_step2_redo),
    )
    graph.add_node(  # type: ignore[call-overload]
        "director_full_redo",
        _make_traced_node("director_full_redo", run_director_full_redo),
    )
    graph.add_node(  # type: ignore[call-overload]
        "state_orchestrator",
        _make_traced_node("state_orchestrator", run_state_orchestrator),
    )
    graph.add_node(  # type: ignore[call-overload]
        "thinking_fanout",
        _make_traced_node("thinking_fanout", run_thinking_fanout),
    )
    graph.add_node(  # type: ignore[call-overload]
        "cross_ref_sync",
        _make_traced_node("cross_ref_sync", run_cross_ref_sync),
    )
    graph.add_node("writer", _make_traced_node("writer", run_writer))  # type: ignore[call-overload]
    graph.add_node("reviewer", _make_traced_node("reviewer", run_reviewer))  # type: ignore[call-overload]

    # Parallel asset generation (3 sub-agents run concurrently inside one node)
    graph.add_node("asset_generation", _run_assets_parallel)  # type: ignore[call-overload]

    # Linear flow: director → structure → state → thinking → sync → writer → reviewer
    # Phase 13-2 Step 4e: structure_reviewer now has a conditional edge
    # that can route back to a Director redo node when actionable
    # findings are present. Redo nodes loop back to structure_reviewer
    # to re-audit; the routing helper accepts after max_director_revisions.
    graph.set_entry_point("director")
    graph.add_edge("director", "structure_reviewer")
    graph.add_conditional_edges(
        "structure_reviewer",
        _after_structure_review,
        {
            "accept": "state_orchestrator",
            "step2_only": "director_step2_redo",
            "step1_step2": "director_full_redo",
        },
    )
    graph.add_edge("director_step2_redo", "structure_reviewer")
    graph.add_edge("director_full_redo", "structure_reviewer")
    graph.add_edge("state_orchestrator", "thinking_fanout")
    graph.add_edge("thinking_fanout", "cross_ref_sync")
    graph.add_edge("cross_ref_sync", "writer")
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

    Entry at `thinking_fanout` (Phase 13-2 Step 2), then `cross_ref_sync`
    (Step 3), then writer. Both planning nodes are gated off by default,
    so this is a no-op pass-through for short runs.

    Assumes vn_script, characters, world_state, and state_constraints are
    pre-populated in state by the caller (loaded from disk after a
    creator pauses-for-outline run).
    """
    graph = StateGraph(AgentState)  # type: ignore[type-var]

    graph.add_node(  # type: ignore[call-overload]
        "thinking_fanout",
        _make_traced_node("thinking_fanout", run_thinking_fanout),
    )
    graph.add_node(  # type: ignore[call-overload]
        "cross_ref_sync",
        _make_traced_node("cross_ref_sync", run_cross_ref_sync),
    )
    graph.add_node("writer", _make_traced_node("writer", run_writer))  # type: ignore[call-overload]
    graph.add_node("reviewer", _make_traced_node("reviewer", run_reviewer))  # type: ignore[call-overload]
    graph.add_node("asset_generation", _run_assets_parallel)  # type: ignore[call-overload]

    graph.set_entry_point("thinking_fanout")
    graph.add_edge("thinking_fanout", "cross_ref_sync")
    graph.add_edge("cross_ref_sync", "writer")
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
