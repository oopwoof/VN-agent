"""Phase 13-2 Step 2 (路线四): thinking_fanout node.

Sits between state_orchestrator and writer. Its job: for each scene, call
Haiku with the planning context (scene_brief, context_deps, prior-scene
summaries, macro_reference, world_state) and produce a structured
SceneThinking artifact. NO dialogue is written here — that's Writer's
job. The whole point is to let Writer workers (eventually parallel, Step 4)
coordinate callbacks + voice + pacing via each other's thinking output
BEFORE any dialogue commits.

Step 2 (this file): sequential Haiku per scene. Validates thinking quality
under real prompts before committing to parallel infrastructure.

Step 3: `cross_ref_sync` — single round where each scene sees its deps'
thinking and revises its own plan.

Step 4: parallel fanout via asyncio.gather + RPM monitoring.

Non-blocking: Haiku failure on any scene leaves scene.thinking=None. The
pipeline continues — later Writer will fall back to scene_brief-only
planning. Gated by settings.enable_thinking_fanout AND scene count
≥ thinking_fanout_min_scenes (short demos don't pay the Haiku cost).
"""
from __future__ import annotations

import json
import logging

from vn_agent.agents.state import AgentState
from vn_agent.config import get_settings
from vn_agent.prompts.templates import strip_thinking
from vn_agent.schema.script import Scene, SceneThinking, VNScript
from vn_agent.services.llm import ainvoke_llm

logger = logging.getLogger(__name__)


THINKING_SYSTEM = """You are a scene planner for a long-form visual novel.

Your job is NOT to write dialogue. Your job is to produce a structured \
thinking plan that a downstream Writer worker will inflate into prose. \
Think of yourself as the director in a table read: you map the beats, \
the cadence, the subtext; the actors (Writer) deliver the lines.

You will receive:
  - scene_brief: director's per-scene creative instructions
  - context_deps: prior scenes / arcs / vars this scene depends on
  - macro_reference: story-wide voice charter + pacing arc + foreshadow plan
  - prior_scene_summaries: summaries of earlier scenes that are relevant
  - world_state_at_entry: effective world state when this scene begins

Output ONLY a JSON object matching this shape:

{
  "writing_intent": "one sentence on what the scene is trying to achieve",
  "key_beats_expanded": [
    "beat 1, with causality and subtext (~120 chars)",
    "beat 2..."
  ],
  "callback_plan": [
    {"ref_scene_id": "s03", "what_lands": "how the callback hits this time"}
  ],
  "opening_hook": "one line of stage direction or action",
  "closing_beat": "how the scene ends — the last emotional chord",
  "voice_notes": {"character_id": "scene-specific voice reminder"},
  "risks": ["failure mode Writer should avoid"]
}

Rules:
- NO dialogue. No quoted lines. Plans only.
- key_beats_expanded: 3-8 entries, each ≤120 chars, expands scene_brief.beats
- callback_plan: must reference scene_ids that appear in context_deps
- voice_notes: only for characters in characters_present, layer on top
  of macro_reference.character_voice_charter (don't repeat it verbatim)
- risks: 2-6 concrete pitfalls ("don't over-explain X", "avoid melodrama
  on the reveal"), NOT generic writing advice"""


async def run_thinking_fanout(state: AgentState) -> dict:
    """Graph node: populate SceneThinking for every scene.

    Sequential today (Step 2); parallel in Step 4. Non-blocking: per-scene
    Haiku failure leaves scene.thinking=None and logs at DEBUG.

    Gating:
      - settings.enable_thinking_fanout must be True
      - len(script.scenes) must be >= settings.thinking_fanout_min_scenes

    When skipped, returns the existing state unchanged (no scene.thinking
    gets populated). Writer's consumption path (Step 4) checks for None
    and falls back to scene_brief-only planning.
    """
    settings = get_settings()
    script: VNScript | None = state.get("vn_script")
    if script is None:
        logger.debug("thinking_fanout: no vn_script in state, skipping")
        return {}

    if not settings.enable_thinking_fanout:
        logger.info("thinking_fanout: disabled via settings, skipping")
        return {}

    if len(script.scenes) < settings.thinking_fanout_min_scenes:
        logger.info(
            f"thinking_fanout: {len(script.scenes)} scenes < "
            f"{settings.thinking_fanout_min_scenes} min, skipping "
            f"(short demos don't pay Haiku cost)"
        )
        return {}

    logger.info(
        f"thinking_fanout: planning {len(script.scenes)} scenes "
        f"(sequential, Step 4 will parallelize)"
    )

    updated_scenes: list[Scene] = []
    world_state_trail: dict = {
        v.name: v.initial_value for v in script.world_variables
    }
    filled = 0
    for scene in script.scenes:
        thinking = await _think_scene(
            scene=scene,
            script=script,
            prior_scenes=updated_scenes,
            world_state_at_entry=dict(world_state_trail),
            settings=settings,
        )
        if thinking is not None:
            scene = scene.model_copy(update={"thinking": thinking})
            filled += 1
        updated_scenes.append(scene)
        # Walk world_state forward so the next scene's Haiku sees the
        # correct effective state at its own start.
        for var, val in scene.state_writes.items():
            world_state_trail[var] = val

    logger.info(
        f"thinking_fanout: produced thinking for {filled}/{len(script.scenes)} scenes"
    )

    return {
        "vn_script": script.model_copy(update={"scenes": updated_scenes}),
    }


async def _think_scene(
    scene: Scene,
    script: VNScript,
    prior_scenes: list[Scene],
    world_state_at_entry: dict,
    settings,
) -> SceneThinking | None:
    """Single-scene Haiku thinking call. Returns None on any failure —
    caller keeps the original scene unchanged (thinking stays None)."""
    try:
        user_prompt = _build_thinking_prompt(
            scene=scene,
            script=script,
            prior_scenes=prior_scenes,
            world_state_at_entry=world_state_at_entry,
        )
        response = await ainvoke_llm(
            THINKING_SYSTEM,
            user_prompt,
            model=settings.llm_thinking_model,
            caller=f"thinking/{scene.id}",
        )
        content = (
            response.content if hasattr(response, "content") else str(response)
        )
        content = strip_thinking(content).strip()
        if not content:
            return None
        data = _parse_thinking_json(content)
        if not data:
            return None
        return SceneThinking.model_validate(data)
    except Exception as e:  # noqa: BLE001 — non-blocking
        logger.debug(f"thinking for {scene.id} failed (non-fatal): {e}")
        return None


def _build_thinking_prompt(
    scene: Scene,
    script: VNScript,
    prior_scenes: list[Scene],
    world_state_at_entry: dict,
) -> str:
    """Assemble the per-scene user prompt for the Haiku thinking call."""
    parts: list[str] = []

    parts.append(f"## Scene being planned: {scene.id} — {scene.title}")
    parts.append(f"Description: {scene.description}")
    parts.append(f"Characters present: {scene.characters_present}")
    if scene.narrative_strategy:
        parts.append(f"Narrative strategy: {scene.narrative_strategy}")
    if scene.entry_context:
        parts.append(f"Entry context (from Director): {scene.entry_context}")
    if scene.exit_hook:
        parts.append(f"Exit hook target: {scene.exit_hook}")
    if scene.emotional_arc:
        parts.append(f"Emotional arc target: {scene.emotional_arc}")

    # scene_brief (Step 1 output) — the creative spine
    if scene.scene_brief is not None:
        parts.append("\n## Scene brief (from Director step2):")
        parts.append(json.dumps(
            scene.scene_brief.model_dump(),
            ensure_ascii=False, indent=2,
        ))

    # macro_reference (Step 1 output) — story-wide charter
    if script.macro_reference is not None:
        parts.append("\n## Macro reference (story-wide charter):")
        parts.append(json.dumps(
            script.macro_reference.model_dump(),
            ensure_ascii=False, indent=2,
        ))

    # context_deps (Phase 13-1 Step 5) — what this scene strongly depends on
    if scene.context_deps:
        parts.append("\n## Director-declared context_deps (backward refs):")
        for dep in scene.context_deps:
            parts.append(
                f"  - {dep.link_type} → {dep.ref_type}:{dep.ref_id} "
                f"({dep.reason})"
            )

    # world_state at entry
    if world_state_at_entry:
        parts.append(f"\n## World state at scene entry: {world_state_at_entry}")

    # Prior scene summaries (for callback context) — only those referenced
    # in context_deps (keeps prompt bounded).
    ref_scene_ids = {
        dep.ref_id for dep in scene.context_deps
        if dep.ref_type == "scene"
    }
    relevant_priors = [
        s for s in prior_scenes
        if s.id in ref_scene_ids and s.summary
    ]
    if relevant_priors:
        parts.append("\n## Relevant prior scene summaries:")
        for s in relevant_priors:
            parts.append(f"  [{s.id}] {s.summary}")

    parts.append(
        "\n## Output\n"
        "Produce ONE JSON object matching the SceneThinking schema. "
        "No commentary, no code fences, no <thinking> tags."
    )
    return "\n".join(parts)


def _parse_thinking_json(content: str) -> dict | None:
    """Extract a JSON object from the Haiku response. Tolerates stray
    code fences / prose because Haiku occasionally decorates."""
    # Strip common fences
    stripped = content.strip()
    if stripped.startswith("```"):
        # Find first newline after opening fence, take until closing fence
        first_nl = stripped.find("\n")
        if first_nl != -1:
            stripped = stripped[first_nl + 1 :]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[: -3]

    # Try direct parse first
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Fallback: find the first {...} block
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(stripped[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    logger.debug(f"thinking JSON parse failed; first 200 chars: {content[:200]}")
    return None
