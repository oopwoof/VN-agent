"""Phase 13-2 Steps 2-3 + 3.5 (路线四): thinking_fanout + cross_ref_sync nodes.

Sits between state_orchestrator and writer. Two-node sequence:

  state_orchestrator
    └→ thinking_fanout   — Step 2: each scene gets a draft SceneThinking
    └→ cross_ref_sync    — Steps 3 + 3.5: callback conflicts resolved
                           DETERMINISTICALLY (Director authority → latest
                           fallback); Director arbitration and Haiku
                           re-revision available as opt-in flags
    └→ writer

Core observation: naive parallel writing breaks because workers have no
visibility into peers. Thinking is cheap (Haiku × N), structured
(SceneThinking), and shared — the sync pass is where "two scenes planting
the same callback beat" gets detected and resolved.

Step 3.5 (post-Gemini-review 2026-04-24): replaced the default path from
"symmetric Haiku revision + difflib conflict detection" with "Tier-1
deterministic resolver + optional Tier-2 Director arbitration". Reasons:
- Symmetric Haiku revision was a logic race: both scenes could delete
  their claim to the same callback, erasing the payoff entirely.
- difflib.SequenceMatcher was character-level, not semantic. Now that
  callback_plan is a strict `list[CallbackItem]`, same `ref_scene_id`
  is itself the canonical collision signal — no text similarity needed.
- Conflict resolution is Director's job description (macro_reference.
  foreshadow_plan already declares payoff ownership). No new agent —
  Tier 2 reuses the Director model in a narrow arbitration call.

Step 4: parallel fanout.

Non-blocking throughout: per-scene failures log and skip; pipeline never
blocks on thinking/sync. Gated by settings so short demos don't pay the
Haiku cost.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from vn_agent.agents.state import AgentState
from vn_agent.config import get_settings
from vn_agent.prompts.templates import strip_thinking
from vn_agent.schema.script import CallbackItem, Scene, SceneThinking, VNScript
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
    """Phase 13-2 Step 3.5: callback collision detection, ID-only.

    Step 3.5 reasoning: callback_plan is now a strict `list[CallbackItem]`
    (Pydantic-enforced). Two scenes claiming the same `ref_scene_id` is
    the canonical collision signal — no text similarity needed. This was
    Gemini MAJOR-level feedback: difflib was character-level, paraphrases
    below 0.7 ratio would silently pass even when semantically identical.

    Returns one conflict dict per colliding ref_scene_id, listing ALL
    claimants (not pairwise). Empty list means clean plans.

    Resolution is caller's responsibility (resolve_callback_conflicts
    below). This function just surfaces the collisions.
    """
    by_ref: dict[str, list[tuple[str, CallbackItem]]] = {}
    for scene in scenes:
        if scene.thinking is None:
            continue
        for cb in scene.thinking.callback_plan or []:
            if not cb.ref_scene_id:
                continue
            by_ref.setdefault(cb.ref_scene_id, []).append((scene.id, cb))

    conflicts: list[dict] = []
    for ref_id, claims in by_ref.items():
        if len(claims) < 2:
            continue
        conflicts.append({
            "ref_scene_id": ref_id,
            "claimants": [sid for sid, _ in claims],
            "what_lands_by_scene": {
                sid: cb.what_lands for sid, cb in claims
            },
        })
    return conflicts


def _build_director_authority_map(script: VNScript) -> dict[str, str]:
    """Extract Director's declared payoff ownership from foreshadow_plan.

    Returns {planted_in_scene_id: payoff_in_scene_id}. Used by the Tier-1
    resolver as the canonical source of truth for who owns callbacks to
    the declared planting scene.
    """
    owners: dict[str, str] = {}
    mr = getattr(script, "macro_reference", None)
    if mr is None:
        return owners
    for fp in mr.foreshadow_plan or []:
        planted = fp.get("planted_in")
        payoff = fp.get("payoff_in")
        if isinstance(planted, str) and isinstance(payoff, str):
            owners[planted] = payoff
    return owners


def resolve_callback_conflicts(
    scenes: list[Scene],
    script: VNScript,
) -> tuple[list[Scene], list[dict]]:
    """Phase 13-2 Step 3.5: Tier-1 deterministic callback conflict resolver.

    Rule stack:
      1. If Director's macro_reference.foreshadow_plan declares a payoff_in
         for this ref_scene_id → that scene owns the callback. Others drop.
         Authority label: "director_foreshadow".
      2. Else the LATEST claimant (largest scene index) owns — payoffs
         land in the later segment of the arc. (Gemini's "earliest wins"
         was backwards for narrative payoff semantics.)
         Authority label: "fallback_latest".

    Returns (scenes_with_cleaned_callback_plans, resolution_log_entries).
    The log records each resolved conflict with authority + winner + losers
    so debug/creator-pause can audit the decision chain.
    """
    conflicts = detect_cross_ref_conflicts(scenes)
    if not conflicts:
        return scenes, []

    scene_order: dict[str, int] = {s.id: i for i, s in enumerate(scenes)}
    authority_map = _build_director_authority_map(script)

    # Build a per-scene "callback to drop" set keyed by ref_scene_id.
    # Mutating scenes' callback_plan in place is fine here — we're
    # returning a new list of model_copy'd scenes.
    drop_targets: dict[str, set[str]] = {}  # {scene_id: {ref_id_to_drop, ...}}
    resolution_log: list[dict] = []

    for conflict in conflicts:
        ref_id: str = conflict["ref_scene_id"]
        claimants: list[str] = conflict["claimants"]

        if ref_id in authority_map:
            winner = authority_map[ref_id]
            authority = "director_foreshadow"
            # If Director's declared payoff_in isn't even in the claimants
            # list, we STILL honor Director's intent — the whole claimant
            # set gets dropped (they all misread the pacing). The Director-
            # declared scene might not have a callback_plan entry yet; that
            # it has the authority to own the callback is unchanged.
        else:
            # Narrative fallback: latest claimant wins.
            winner = max(claimants, key=lambda sid: scene_order.get(sid, -1))
            authority = "fallback_latest"

        losers = [sid for sid in claimants if sid != winner]
        resolution_log.append({
            "ref_scene_id": ref_id,
            "claimants": claimants,
            "winner": winner,
            "losers": losers,
            "authority": authority,
            "what_lands_by_scene": conflict["what_lands_by_scene"],
        })

        for sid in losers:
            drop_targets.setdefault(sid, set()).add(ref_id)

    # Apply drops via model_copy (Scene is immutable-ish via Pydantic)
    updated: list[Scene] = []
    for scene in scenes:
        drops = drop_targets.get(scene.id)
        if not drops or scene.thinking is None:
            updated.append(scene)
            continue
        new_cb_plan = [
            cb for cb in scene.thinking.callback_plan
            if cb.ref_scene_id not in drops
        ]
        new_thinking = scene.thinking.model_copy(
            update={"callback_plan": new_cb_plan},
        )
        updated.append(scene.model_copy(update={"thinking": new_thinking}))

    return updated, resolution_log


# ---------------------------------------------------------------------------
# Tier 2: opt-in Director arbitration (not a new agent — reuses Director model)
# ---------------------------------------------------------------------------


DIRECTOR_ARBITRATE_SYSTEM = """You are the Director of this visual novel. \
Downstream scene planners (thinking phase) produced conflicts where \
multiple scenes claim the same callback. Your narrative judgment overrides \
theirs — decide which scene SHOULD own each callback, and optionally \
refine the story's foreshadow_plan so such conflicts don't recur.

Rules:
- One scene wins each conflict. Others drop the callback silently.
- Your decision reflects narrative weight: which scene has the \
higher-stakes payoff moment, earns the emotional beat, or completes a \
character arc.
- Do not introduce new callbacks or rename scenes. Work with what's given.

Output ONE JSON object:
{
  "decisions": [
    {"ref_scene_id": "s01", "winner": "s08", "reason": "s08 is the climactic moment where the watch's origin lands"}
  ]
}

No commentary, no code fences."""


async def _director_arbitrate(
    unresolved_conflicts: list[dict],
    script: VNScript,
    settings,
) -> dict[str, str]:
    """Opt-in Tier-2 arbitration. Returns {ref_scene_id: winner_scene_id}
    for conflicts Director provided judgment on. Any unresolved keys are
    silently dropped — caller proceeds without forced decisions.

    Reuses `settings.llm_director_model` (Sonnet) — not a new agent, just
    a second narrow call against the existing Director LLM. Labels
    decisions with authority='director_arbitration' in the caller's log.
    """
    if not unresolved_conflicts:
        return {}

    # Compact prompt — conflicts only, not the whole script
    brief_scenes = [
        {"id": s.id, "title": s.title,
         "strategy": s.narrative_strategy,
         "description": s.description[:200]}
        for s in script.scenes
    ]
    existing_foreshadow = (
        script.macro_reference.foreshadow_plan
        if script.macro_reference is not None else []
    )
    user_prompt = (
        f"Scene roster (brief):\n"
        f"{json.dumps(brief_scenes, ensure_ascii=False, indent=2)}\n\n"
        f"Existing macro_reference.foreshadow_plan:\n"
        f"{json.dumps(existing_foreshadow, ensure_ascii=False, indent=2)}\n\n"
        f"Unresolved callback conflicts to arbitrate:\n"
        f"{json.dumps(unresolved_conflicts, ensure_ascii=False, indent=2)}\n\n"
        "Return JSON with decisions[]."
    )
    try:
        response = await ainvoke_llm(
            DIRECTOR_ARBITRATE_SYSTEM,
            user_prompt,
            model=settings.llm_director_model,
            caller="director_arbitrate",
        )
        content = (
            response.content if hasattr(response, "content") else str(response)
        )
        content = strip_thinking(content).strip()
        data = _parse_thinking_json(content)
        if not isinstance(data, dict):
            return {}
        decisions = data.get("decisions") or []
        result: dict[str, str] = {}
        for d in decisions:
            ref_id = d.get("ref_scene_id")
            winner = d.get("winner")
            if isinstance(ref_id, str) and isinstance(winner, str):
                result[ref_id] = winner
        return result
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Director arbitration failed (non-fatal): {e}")
        return {}


def _persist_conflicts(log_entries: list[dict], output_dir: str) -> None:
    """Append resolution log entries to <output_dir>/cross_ref_conflicts.jsonl.

    Each entry includes 'authority' so creator-pause debug can trace which
    rule tier made the decision: "director_foreshadow" (macro_reference
    authority), "fallback_latest" (narrative heuristic), or
    "director_arbitration" (opt-in Tier 2). Best-effort: filesystem errors
    log at debug only.
    """
    if not log_entries or not output_dir:
        return
    try:
        path = Path(output_dir) / "cross_ref_conflicts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            ts = datetime.now(UTC).isoformat()
            for entry in log_entries:
                row = {"ts": ts, **entry}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001 — observability best-effort
        logger.debug(f"Failed to persist cross_ref conflicts: {e}")


async def run_cross_ref_sync(state: AgentState) -> dict:
    """Graph node: resolve callback collisions after thinking_fanout.

    Phase 13-2 Step 3.5 (post-Gemini-review) flow:

      1. Tier 1 (deterministic, always runs):
         - Detect collisions via shared ref_scene_id (strict schema —
           no difflib).
         - Apply Director foreshadow_plan → latest-fallback ownership.
         - Drop losers' callback entries; log with authority label.

      2. Tier 2 (opt-in, settings.enable_director_arbitration):
         - For conflicts Tier 1 had to fall back to "latest", re-ask the
           Director model (not a new agent) which scene should own.
         - Apply decisions; re-log with authority="director_arbitration".

      3. Tier 3 (opt-in, settings.enable_cross_ref_sync_llm_revise):
         - Legacy path. Each scene's Haiku-level self-revision given peer
           thinking. Kept behind a flag for research purposes (symmetric
           revision is a logic race — two scenes can both delete the
           same callback). OFF by default.

    Skipped when:
      - settings.enable_cross_ref_sync is False
      - fewer than settings.cross_ref_sync_min_scenes scenes
      - no scene has context_deps (nothing to sync)
      - no scene has thinking populated (thinking_fanout didn't run)
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

    has_thinking = any(s.thinking is not None for s in script.scenes)
    if not has_thinking:
        logger.info(
            "cross_ref_sync: no scene has thinking populated "
            "(thinking_fanout didn't run), skipping"
        )
        return {}

    all_log: list[dict] = []

    # ---- Tier 3 (opt-in, legacy): Haiku self-revision ----
    if getattr(settings, "enable_cross_ref_sync_llm_revise", False):
        logger.info(
            "cross_ref_sync: Tier 3 (LLM self-revision) enabled — running "
            "Haiku revision per scene with deps (research-only path)"
        )
        revised_scenes: list[Scene] = []
        revised = 0
        for scene in script.scenes:
            peers = _cross_ref_peer_subset(scene, script.scenes)
            if not peers or scene.thinking is None:
                revised_scenes.append(scene)
                continue
            new_thinking = await _resync_scene(
                scene=scene, script=script, peers=peers, settings=settings,
            )
            if new_thinking is not None:
                scene = scene.model_copy(update={"thinking": new_thinking})
                revised += 1
            revised_scenes.append(scene)
        logger.info(f"cross_ref_sync: Tier 3 revised {revised}/{len(script.scenes)}")
        working_scenes = revised_scenes
    else:
        working_scenes = list(script.scenes)

    # ---- Tier 1 (always): deterministic resolver ----
    resolved_scenes, tier1_log = resolve_callback_conflicts(working_scenes, script)
    all_log.extend(tier1_log)
    logger.info(
        f"cross_ref_sync: Tier 1 resolved {len(tier1_log)} callback conflict(s) "
        f"deterministically"
    )

    # ---- Tier 2 (opt-in): Director arbitration for fallback cases ----
    if getattr(settings, "enable_director_arbitration", False):
        # Re-arbitrate the "fallback_latest" decisions — these are the
        # ones Director's foreshadow_plan didn't cover. Keep
        # "director_foreshadow" decisions intact; they're already
        # Director-declared.
        fallback_entries = [
            e for e in tier1_log if e["authority"] == "fallback_latest"
        ]
        if fallback_entries:
            logger.info(
                f"cross_ref_sync: Tier 2 (Director arbitration) — re-arbitrating "
                f"{len(fallback_entries)} fallback decision(s)"
            )
            overrides = await _director_arbitrate(
                unresolved_conflicts=fallback_entries,
                script=script,
                settings=settings,
            )
            # Apply Director's decisions by revising the previous drops.
            # If Director changed the winner, we need to: (a) put the
            # callback back on the new winner (if it was originally dropped),
            # (b) drop it from the old winner.
            if overrides:
                # Re-derive full claimant sets from the pre-Tier-1 scenes.
                pre_claimants_by_ref: dict[str, list[str]] = {}
                for scene in working_scenes:
                    if scene.thinking is None:
                        continue
                    for cb in scene.thinking.callback_plan:
                        pre_claimants_by_ref.setdefault(
                            cb.ref_scene_id, []).append(scene.id)

                scene_by_id = {s.id: s for s in resolved_scenes}
                # Map entry by ref_scene_id for easier update
                entries_by_ref = {e["ref_scene_id"]: e for e in all_log}

                for ref_id, director_winner in overrides.items():
                    if ref_id not in entries_by_ref:
                        continue
                    entry = entries_by_ref[ref_id]
                    old_winner = entry["winner"]
                    if director_winner == old_winner:
                        entry["authority"] = "director_arbitration"  # confirmed
                        continue
                    # Director chose a different scene. Apply the swap.
                    # Find the original CallbackItem from working_scenes:
                    original_cb: CallbackItem | None = None
                    for s in working_scenes:
                        if s.id == director_winner and s.thinking is not None:
                            for cb in s.thinking.callback_plan:
                                if cb.ref_scene_id == ref_id:
                                    original_cb = cb
                                    break
                    if original_cb is None:
                        # Director picked a scene that didn't even claim the
                        # callback originally. Create a minimal CallbackItem
                        # so the callback actually lands somewhere.
                        original_cb = CallbackItem(
                            ref_scene_id=ref_id,
                            what_lands="(Director-assigned payoff)",
                        )

                    # Add to director's winner
                    winner_scene = scene_by_id.get(director_winner)
                    if winner_scene is not None and winner_scene.thinking is not None:
                        new_cbs = list(winner_scene.thinking.callback_plan)
                        if not any(
                            cb.ref_scene_id == ref_id for cb in new_cbs
                        ):
                            new_cbs.append(original_cb)
                            new_thinking = winner_scene.thinking.model_copy(
                                update={"callback_plan": new_cbs},
                            )
                            scene_by_id[director_winner] = winner_scene.model_copy(
                                update={"thinking": new_thinking},
                            )

                    # Remove from old winner
                    old_scene = scene_by_id.get(old_winner)
                    if old_scene is not None and old_scene.thinking is not None:
                        new_cbs = [
                            cb for cb in old_scene.thinking.callback_plan
                            if cb.ref_scene_id != ref_id
                        ]
                        new_thinking = old_scene.thinking.model_copy(
                            update={"callback_plan": new_cbs},
                        )
                        scene_by_id[old_winner] = old_scene.model_copy(
                            update={"thinking": new_thinking},
                        )

                    # Update log entry
                    entry["winner"] = director_winner
                    losers_pre = pre_claimants_by_ref.get(ref_id, [])
                    entry["losers"] = [
                        sid for sid in losers_pre if sid != director_winner
                    ]
                    entry["authority"] = "director_arbitration"

                # Rebuild scenes in original order
                resolved_scenes = [scene_by_id[s.id] for s in resolved_scenes]

    if all_log:
        logger.warning(
            f"cross_ref_sync: resolved {len(all_log)} callback conflict(s) "
            f"(authorities: "
            f"{set(e['authority'] for e in all_log)}; "
            f"details in cross_ref_conflicts.jsonl)"
        )
        _persist_conflicts(all_log, state.get("output_dir", ""))

    return {
        "vn_script": script.model_copy(update={"scenes": resolved_scenes}),
    }
