"""Phase 13-2 Steps 2-3 (路线四): thinking_fanout + cross_ref_sync nodes.

Sits between state_orchestrator and writer. Two-node sequence:

  state_orchestrator
    └→ thinking_fanout   — Step 2: each scene gets a draft SceneThinking
    └→ cross_ref_sync    — Step 3: each scene revises after seeing its
                                    context_deps' thinking; conflicts logged
    └→ writer

The core observation: naive parallel writing breaks because workers have
no visibility into peers. Thinking + sync is cheap (Haiku × N per step),
structured (SceneThinking), and shared — the sync pass is where "two
scenes planting the same callback beat" gets detected and resolved.

Step 2 (thinking_fanout): draft thinking, sequential today.
Step 3 (cross_ref_sync): one-shot revision + conflict detection. NOT an
  iterative fixed-point — explicit non-goal per ARCHITECTURE.md 路线四
  ("1 轮固定 + 冲突检测, 不追不动点"). If a revision creates a new
  conflict downstream, it survives as a logged warning and Reviewer
  catches it later — cheaper than iterating to convergence.
Step 4: parallel fanout.

Non-blocking all the way: per-scene failures log and skip; pipeline never
blocks on thinking/sync. Gated by settings so short demos don't pay the
Haiku cost.
"""
from __future__ import annotations

import difflib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

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


# ============================================================================
# Phase 13-2 Step 3 (路线四): cross_ref_sync — single-round peer revision
# ============================================================================


RESYNC_SYSTEM = """You are revising a scene's thinking plan after seeing \
the plans of the scenes it depends on. Your job is to fix coordination \
problems — NOT to rewrite the plan from scratch.

You will receive:
  - scene being revised (with its existing thinking plan)
  - upstream peer thinking: the SceneThinking plans of scenes this one \
references via context_deps
  - original scene_brief + macro_reference (for grounding)

Revise the scene's thinking to:

1. **Align callbacks with peers**: if peer thinking shows a callback \
already plants a beat you were about to plant redundantly, reframe \
yours (pick a different angle or inherit theirs).
2. **Respect peer voice notes**: if peer thinking locks a character's \
cadence choice, don't contradict it within the same arc.
3. **Tighten opening_hook / closing_beat**: if peer closing_beat feeds \
naturally into your opening_hook, make that seam explicit.
4. **Add or sharpen risks**: surface NEW risks your plan now creates \
in light of peer plans (e.g. "peer s04 already planted the watch \
reveal — this scene shouldn't re-reveal").

Rules:
- One revision pass only. Do NOT chase convergence or imagine further rounds.
- Keep the SceneThinking JSON shape unchanged (same keys).
- If peers give you nothing actionable, return your plan essentially \
unchanged (not a forced rewrite).
- NO dialogue.

Output ONLY a JSON object matching the SceneThinking schema."""


def _cross_ref_peer_subset(
    scene: Scene,
    all_scenes: list[Scene],
) -> list[Scene]:
    """Collect peer scenes this one explicitly depends on.

    Only context_deps with ref_type='scene' resolve to actual peer
    SceneThinking to show. character_arc / world_var / motif / location
    refs can't be shown as SceneThinking — those get rendered in
    thinking_fanout's base prompt already.
    """
    dep_scene_ids = {
        dep.ref_id
        for dep in scene.context_deps
        if dep.ref_type == "scene"
    }
    if not dep_scene_ids:
        return []
    by_id = {s.id: s for s in all_scenes}
    peers: list[Scene] = []
    for sid in dep_scene_ids:
        peer = by_id.get(sid)
        if peer is not None and peer.thinking is not None:
            peers.append(peer)
    return peers


def _build_resync_prompt(
    scene: Scene,
    script: VNScript,
    peers: list[Scene],
) -> str:
    """Assemble the revision prompt. Includes the current thinking plus
    each peer's plan, flagged by scene_id."""
    parts: list[str] = []

    parts.append(f"## Scene being revised: {scene.id} — {scene.title}")
    parts.append(f"Description: {scene.description}")
    parts.append(f"Characters present: {scene.characters_present}")

    # Current thinking (must exist for resync to run)
    if scene.thinking is not None:
        parts.append("\n## Your CURRENT thinking plan (draft):")
        parts.append(json.dumps(
            scene.thinking.model_dump(), ensure_ascii=False, indent=2,
        ))

    # Peer thinkings (the whole point of this step)
    parts.append("\n## Upstream peer thinking plans (scenes this one depends on):")
    for peer in peers:
        parts.append(f"\n### Peer [{peer.id} — {peer.title}]")
        if peer.thinking is not None:
            parts.append(json.dumps(
                peer.thinking.model_dump(), ensure_ascii=False, indent=2,
            ))

    # Grounding (scene_brief + macro)
    if scene.scene_brief is not None:
        parts.append("\n## Scene brief (from Director):")
        parts.append(json.dumps(
            scene.scene_brief.model_dump(), ensure_ascii=False, indent=2,
        ))
    if script.macro_reference is not None:
        parts.append("\n## Macro reference (story-wide charter):")
        parts.append(json.dumps(
            script.macro_reference.model_dump(), ensure_ascii=False, indent=2,
        ))

    parts.append(
        "\n## Output\n"
        "Produce ONE revised SceneThinking JSON object. Same keys as before. "
        "Do not chase further revision rounds."
    )
    return "\n".join(parts)


async def _resync_scene(
    scene: Scene,
    script: VNScript,
    peers: list[Scene],
    settings,
) -> SceneThinking | None:
    """Single-scene revision call. Returns the revised SceneThinking on
    success, or None to signal 'keep the original' (caller handles).
    """
    try:
        user_prompt = _build_resync_prompt(scene, script, peers)
        response = await ainvoke_llm(
            RESYNC_SYSTEM,
            user_prompt,
            model=settings.llm_thinking_model,
            caller=f"resync/{scene.id}",
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
        logger.debug(f"resync for {scene.id} failed (non-fatal): {e}")
        return None


def detect_cross_ref_conflicts(scenes: list[Scene]) -> list[dict]:
    """Find callback collisions across scenes' thinking plans.

    A conflict = two scenes' callback_plan entries reference the SAME
    upstream scene_id AND describe overlapping what_lands text (≥ 70%
    similarity via difflib.SequenceMatcher). That's the "both workers
    planted the same callback beat" problem we're trying to surface.

    Returns list of conflict dicts; empty list means clean plans.
    Step 3 logs but does NOT block on conflicts — Reviewer catches
    the concrete dialogue-level outcome after Writer runs.
    """
    # Collect (scene_id, callback_entry) pairs for every scene with thinking.
    by_ref: dict[str, list[tuple[str, dict]]] = {}
    for scene in scenes:
        if scene.thinking is None:
            continue
        for callback in scene.thinking.callback_plan or []:
            ref_id = callback.get("ref_scene_id")
            if not ref_id:
                continue
            by_ref.setdefault(ref_id, []).append((scene.id, callback))

    conflicts: list[dict] = []
    for ref_id, claims in by_ref.items():
        if len(claims) < 2:
            continue
        # Pairwise similarity check on what_lands
        for i in range(len(claims)):
            for j in range(i + 1, len(claims)):
                scene_i, cb_i = claims[i]
                scene_j, cb_j = claims[j]
                text_i = (cb_i.get("what_lands") or "").strip().lower()
                text_j = (cb_j.get("what_lands") or "").strip().lower()
                if not text_i or not text_j:
                    continue
                ratio = difflib.SequenceMatcher(None, text_i, text_j).ratio()
                if ratio >= 0.7:
                    conflicts.append({
                        "ref_scene_id": ref_id,
                        "scene_a": scene_i,
                        "scene_b": scene_j,
                        "similarity": round(ratio, 3),
                        "what_lands_a": cb_i.get("what_lands"),
                        "what_lands_b": cb_j.get("what_lands"),
                    })
    return conflicts


def _persist_conflicts(conflicts: list[dict], output_dir: str) -> None:
    """Append conflict entries to <output_dir>/cross_ref_conflicts.jsonl.
    Best-effort: directory-missing / permission errors log at debug only."""
    if not conflicts or not output_dir:
        return
    try:
        path = Path(output_dir) / "cross_ref_conflicts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            ts = datetime.now(UTC).isoformat()
            for c in conflicts:
                row = {"ts": ts, **c}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001 — observability best-effort
        logger.debug(f"Failed to persist cross_ref conflicts: {e}")


async def run_cross_ref_sync(state: AgentState) -> dict:
    """Graph node: single-round revision of scene thinking after peer visibility.

    Runs AFTER thinking_fanout. Skipped when:
      - settings.enable_cross_ref_sync is False
      - fewer than settings.cross_ref_sync_min_scenes scenes (short demos)
      - no scene has context_deps (nothing to sync against)
      - no scene has thinking populated (thinking_fanout didn't run)

    Returns the updated vn_script (with revised thinking per scene) and
    logs any detected conflicts. Non-blocking: per-scene failures keep
    the original draft thinking.
    """
    settings = get_settings()
    script: VNScript | None = state.get("vn_script")
    if script is None:
        logger.debug("cross_ref_sync: no vn_script in state, skipping")
        return {}

    if not settings.enable_cross_ref_sync:
        logger.info("cross_ref_sync: disabled via settings, skipping")
        return {}

    if len(script.scenes) < settings.cross_ref_sync_min_scenes:
        logger.info(
            f"cross_ref_sync: {len(script.scenes)} scenes < "
            f"{settings.cross_ref_sync_min_scenes} min, skipping"
        )
        return {}

    # Pre-check: any scene with both context_deps AND a thinking draft?
    has_work = any(
        s.thinking is not None and any(
            dep.ref_type == "scene" for dep in s.context_deps
        )
        for s in script.scenes
    )
    if not has_work:
        logger.info(
            "cross_ref_sync: no scene has (thinking + scene-type context_deps), "
            "skipping — thinking_fanout likely didn't run or context_deps empty"
        )
        return {}

    logger.info(f"cross_ref_sync: revising {len(script.scenes)} scenes (one pass)")

    updated_scenes: list[Scene] = []
    revised = 0
    for scene in script.scenes:
        peers = _cross_ref_peer_subset(scene, script.scenes)
        if not peers or scene.thinking is None:
            updated_scenes.append(scene)
            continue
        new_thinking = await _resync_scene(
            scene=scene,
            script=script,
            peers=peers,
            settings=settings,
        )
        if new_thinking is not None:
            scene = scene.model_copy(update={"thinking": new_thinking})
            revised += 1
        updated_scenes.append(scene)

    logger.info(f"cross_ref_sync: revised {revised}/{len(script.scenes)} scenes")

    # Conflict detection runs AFTER revision — we want to flag what's
    # left over post-sync, not what existed pre-sync.
    conflicts = detect_cross_ref_conflicts(updated_scenes)
    if conflicts:
        logger.warning(
            f"cross_ref_sync: {len(conflicts)} callback collision(s) survived "
            f"revision (logged to cross_ref_conflicts.jsonl; Reviewer catches "
            f"dialogue-level outcomes later)"
        )
        _persist_conflicts(conflicts, state.get("output_dir", ""))

    return {
        "vn_script": script.model_copy(update={"scenes": updated_scenes}),
    }
