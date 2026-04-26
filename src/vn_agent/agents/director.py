"""Director Agent: Plans story structure, scenes, and characters."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from vn_agent.agents.state import AgentState
from vn_agent.config import get_settings
from vn_agent.prompts.templates import (
    DIRECTOR_DETAILS_SYSTEM,
    DIRECTOR_OUTLINE_SYSTEM,
    strip_thinking,
)
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.music import Mood, MusicCue
from vn_agent.schema.script import (
    BranchOption,
    DirectorStep2Output,
    MacroReference,
    Scene,
    SceneBrief,
    VNScript,
    WorldVariable,
)
from vn_agent.services.llm import ainvoke_llm
from vn_agent.strategies.narrative import format_strategies_for_prompt

logger = logging.getLogger(__name__)

_SYSTEM_OUTLINE = DIRECTOR_OUTLINE_SYSTEM
_SYSTEM_DETAILS = DIRECTOR_DETAILS_SYSTEM

# Simplified prompts for small models (7B and below) that struggle with complex instructions
_SMALL_MODEL_KEYWORDS = ("qwen", "llama", "phi", "mistral", "gemma", "yi-")

_SYSTEM_OUTLINE_SIMPLE = (
    "You are a visual novel story planner. "
    "Given a theme, create a story with interesting characters and emotional scenes. "
    "Each scene should advance the plot — avoid filler scenes. "
    "Characters need distinct personalities that create conflict. "
    "Include a mix of narrative strategies: accumulate (build tension), "
    "erode (wear down certainty), rupture (sudden revelation). "
    "Output ONLY valid JSON, no explanation or commentary."
)

_SYSTEM_DETAILS_SIMPLE = (
    "You are a visual novel story planner. "
    "Given a scene list, add navigation and music. "
    "Place branches at emotional turning points where the player's choice "
    "changes the story outcome. Each branch choice should feel like a real dilemma. "
    "Music moods: peaceful, romantic, tense, melancholic, joyful, mysterious, epic, neutral. "
    "Output ONLY valid JSON, no explanation or commentary."
)


def _is_small_model(model_name: str) -> bool:
    """Detect if the model is a small local model that needs simplified prompts."""
    name = model_name.lower()
    return any(kw in name for kw in _SMALL_MODEL_KEYWORDS)


async def run_director(state: AgentState) -> dict:
    """Director node: two-step plan — outline first, then navigation + music."""
    theme = state["theme"]
    settings = get_settings()
    output_dir = state.get("output_dir", ".")
    max_scenes = state.get("max_scenes", 10)
    num_characters = state.get("num_characters", 3)
    logger.info(f"Director starting for theme: {theme[:50]}...")

    # ── Step 1: scene outline + characters (no branches/music yet) ────────────
    outline_data = await _step1_outline(
        theme, max_scenes, num_characters, output_dir, settings
    )

    # ── Step 2: fill in branches + music per scene ────────────────────────────
    detail_data = await _step2_details(outline_data, output_dir, settings)

    # Merge: inject branch/music back into outline scenes
    plan_data = _merge_outline_details(outline_data, detail_data)

    try:
        script, characters = _build_from_plan(plan_data, theme)
    except Exception as e:
        logger.warning(f"Director build failed, attempting LLM repair: {e}")
        repaired = await _attempt_repair(plan_data, str(e), output_dir, settings)
        if repaired:
            script, characters = _build_from_plan(repaired, theme)
        else:
            logger.error(f"Director failed to build plan after repair attempt: {e}")
            raise

    if not script.scenes:
        logger.warning("Director produced 0 scenes — LLM may have returned empty/null scenes list")

    # ── Branch structural validation (Sprint 6-6) ─────────────────────────────
    # Defense-in-depth: fail fast on structurally-meaningless branches before
    # Writer wastes tokens generating dialogue for a cosmetic choice tree.
    #
    # Sprint 7-4 fix: we used to call LLM repair here, but a free-text repair
    # prompt gives the model too much latitude — real observed failures
    # included it inventing a "branch" strategy label and dropping the
    # `characters` field entirely. Structural branch defects have a cheap
    # surgical fix (_degrade_invalid_branches: strip the bad branches,
    # promote the first target to next_scene_id), so use it directly.
    # LLM repair is reserved for JSON shape / Pydantic build failures
    # where a more creative fix is genuinely needed.
    branch_issues = _validate_branch_structure(script)
    if branch_issues:
        logger.warning(
            f"Director branch structure issues: {len(branch_issues)} — "
            f"degrading invalid branches. First: {branch_issues[0]}"
        )
        _degrade_invalid_branches(script, branch_issues)

    logger.info(f"Director created: '{script.title}' with {len(script.scenes)} scenes, {len(characters)} characters")

    # Checkpoint: save immediately so --resume works if Writer crashes
    _save_checkpoint(output_dir, script, characters)

    # Extract art direction from plan (set by Director for style consistency)
    art_direction = plan_data.get("art_direction", "")
    if not art_direction:
        art_direction = "painterly anime style, consistent color palette, atmospheric lighting"

    # Sprint 9-2: seed world_state from declared initial_values so
    # StateOrchestrator (9-6) and downstream scenes see the starting
    # symbolic state.
    world_state: dict = {v.name: v.initial_value for v in script.world_variables}
    if world_state:
        logger.info(
            f"Director declared {len(world_state)} world variables: "
            f"{list(world_state.keys())}"
        )

    return {
        "vn_script": script,
        "characters": characters,
        "art_direction": art_direction,
        "world_state": world_state,
    }


async def _step1_outline(
    theme: str, max_scenes: int, num_characters: int, output_dir: str, settings,
    *, retry_feedback: str = "",
) -> dict:
    """Step 1: generate scene outlines + characters (no branches/music)."""
    small = _is_small_model(settings.llm_director_model)

    if small:
        system = _SYSTEM_OUTLINE_SIMPLE
        # Simplified prompt with compact JSON example showing 3 scenes
        example = (
            '{{"title":"Story Title","description":"One sentence","start_scene_id":"s1",'
            '"scenes":['
            '{{"id":"s1","title":"Opening","description":"What happens",'
            '"background_id":"bg_place","characters_present":["char_hero"],'
            '"narrative_strategy":"accumulate"}},'
            '{{"id":"s2","title":"Conflict","description":"What happens",'
            '"background_id":"bg_place2","characters_present":["char_hero"],'
            '"narrative_strategy":"erode"}},'
            '{{"id":"s3","title":"Resolution","description":"What happens",'
            '"background_id":"bg_place3","characters_present":["char_hero"],'
            '"narrative_strategy":"rupture"}}],'
            '"characters":[{{"id":"char_hero","name":"Name","color":"#ff9966",'
            '"personality":"Brief","background":"Brief","role":"protagonist"}}]}}'
        )
        user_prompt = f"""Theme: {theme}

Create a visual novel with {max_scenes} scenes and {num_characters} characters.

Return this JSON:
{example}

IMPORTANT: Include exactly {max_scenes} scenes and {num_characters} characters. Output ONLY JSON."""
    else:
        strategies = format_strategies_for_prompt()
        system = _SYSTEM_OUTLINE.format(strategies=strategies)
        user_prompt = f"""Create a visual novel story outline for this theme:

Theme: {theme}

Requirements:
- Up to {max_scenes} scenes total
- {num_characters} characters
- Clear emotional arc: beginning, middle, end

Return ONLY this JSON (no branches, no music yet):
{{
  "title": "Story Title",
  "description": "One-sentence story description",
  "art_direction": "unified visual style, e.g. 'painterly anime, warm lighting'",
  "start_scene_id": "ch1_opening",
  "scenes": [
    {{
      "id": "ch1_opening",
      "title": "Scene Title",
      "description": "1-2 sentences: what happens",
      "background_id": "bg_location",
      "characters_present": ["char_id"],
      "narrative_strategy": "accumulate"
    }}
  ],
  "characters": [
    {{
      "id": "char_protagonist",
      "name": "Display Name",
      "color": "#ff9966",
      "personality": "Brief personality",
      "background": "Brief backstory",
      "role": "protagonist",
      "speech_fingerprint": [
        "speaks in short declarative sentences",
        "uses 'perhaps' instead of 'maybe'",
        "never uses contractions under stress"
      ]
    }}
  ],
  "world_variables": [
    {{
      "name": "manuscript_read",
      "type": "bool",
      "initial_value": false,
      "description": "Whether Mira has read the crucial manuscript"
    }},
    {{
      "name": "affinity_kael_mira",
      "type": "int",
      "initial_value": 3,
      "description": "Emotional closeness between Kael and Mira (0-10)"
    }},
    {{
      "name": "weather",
      "type": "enum",
      "initial_value": "clear",
      "enum_values": ["clear", "storm", "fog"],
      "description": "Current weather — affects travel and mood"
    }}
  ],
  "macro_reference": {{
    "theme_thesis": "duty and memory collide in the three hours before the tide",
    "pacing_arc": "accumulate s01-03 → rupture s04 → uncover s05-06 → resolve s07",
    "foreshadow_plan": [
      {{"planted_in": "ch1_opening", "payoff_in": "ch2_confession", "element": "the watch her father left"}}
    ],
    "character_voice_charter": {{
      "char_protagonist": "short declaratives, sea metaphors for grief",
      "char_other": "question-heavy academic register; fragments under stress"
    }},
    "tone_register": "literary third-person-limited, restrained, elliptical"
  }}
}}

## world_variables (Sprint 9-1)

Declare 0-5 symbolic state variables the story will track across \
scenes. These are NOT for every small detail — use them for:
  - Flags that gate branches ("has_seen_the_truth")
  - Relationship affinity / trust values (0-10 ints)
  - Item/possession flags ("has_key", "has_letter")
  - Mutually-exclusive enum states (e.g. "weather" with \
enum_values ["clear","storm","fog"])

Leave `world_variables: []` for simple linear stories without state \
gating. Only declare variables the story will actually read or write.

## macro_reference (Phase 13-2 Step 1, route-4 prep)

Produce ONE macro_reference object that every downstream Writer worker \
will share. This block enters a CACHED prompt prefix (Phase 13-1 Step 3, \
1-hour tier) used on every Writer call — wasted tokens here get \
multiplied by scene count, so be dense.

- theme_thesis: 1 sentence, the story's central tension
- pacing_arc: dense phrase mapping scene ranges to narrative strategies
- foreshadow_plan: 2-5 MAJOR foreshadow→payoff links only (not minor callbacks)
- character_voice_charter: ONE LINE per character_id — signature register \
cues a parallel Writer worker can read and reproduce
- tone_register: literary / action / mixed, plus POV and tension default

For short/simple stories (≤6 scenes), set foreshadow_plan=[] and \
tone_register=""; they don't need this scaffolding and paying for \
unused tokens is wasteful."""

    # Phase 13-2 Step 4e: APPEND retry feedback at the very end so the
    # cached prefix (system + main user_prompt body) stays byte-identical
    # to the first call. Anthropic's prefix cache is strictly front-to-
    # back — prepending feedback would invalidate the entire cache and
    # cost ~$0.27 per retry instead of ~$0.05 (Gemini design review #f).
    if retry_feedback:
        user_prompt += "\n\n" + retry_feedback

    response = await ainvoke_llm(
        system, user_prompt, model=settings.llm_director_model,
        caller="director/step1", cache_ttl="1h", force_cache=True,
    )
    content = response.content if hasattr(response, "content") else str(response)
    _save_debug_raw(output_dir, "director_step1_raw.txt", content)
    content = strip_thinking(content)

    try:
        return _extract_json(content)
    except Exception as e:
        logger.error(f"Director step1 parse error: {e}\nRaw (first 500): {content[:500]}")
        raise


async def _step2_details(
    outline: dict, output_dir: str, settings,
    *, retry_feedback: str = "",
) -> dict:
    """Step 2: add navigation (next_scene_id/branches) and music mood to each scene.

    Phase 13-2 Step 4f: migrated from raw-text-JSON-parsing to Anthropic
    Tool Use via DirectorStep2Output schema. The prior path emitted Sonnet
    `<thinking>` segments that ate ~7K of the 16K output budget; Tool Use
    suppresses those and returns a strictly-validated Pydantic instance.
    """
    small = _is_small_model(settings.llm_director_model)
    scene_ids = [s["id"] for s in (outline.get("scenes") or [])]
    scene_list = "\n".join(
        f'  - {s["id"]}: {s.get("title", "")} — {s.get("description", "")[:60]}'
        for s in (outline.get("scenes") or [])
    )

    if small:
        # Small models (local 7B-class) don't reliably support Anthropic
        # Tool Use; keep them on the legacy raw-JSON path with simplified
        # schema. They were not the source of the max_tokens truncation.
        system = _SYSTEM_DETAILS_SIMPLE
        example = (
            '{{"scenes":[{{"id":"scene_id","next_scene_id":"next_or_null",'
            '"branches":[],"music_mood":"peaceful","music_description":"soft piano",'
            '"emotional_arc":"calm -> tense"}}]}}'
        )
        user_prompt = f"""Scenes: {json.dumps(scene_ids)}
Start: {outline.get("start_scene_id", "")}

For each scene add next_scene_id, music_mood, and emotional_arc (e.g. "warmth -> anticipation").
Last scene has next_scene_id=null. Add branches (choices) to at least 1 scene.

Return JSON: {example}

Output ONLY JSON."""
        if retry_feedback:
            user_prompt += "\n\n" + retry_feedback

        response = await ainvoke_llm(
            system, user_prompt, model=settings.llm_director_model,
            caller="director/step2", cache_ttl="1h", force_cache=True,
        )
        content = response.content if hasattr(response, "content") else str(response)
        _save_debug_raw(output_dir, "director_step2_raw.txt", content)
        content = strip_thinking(content)
        try:
            return _extract_json(content)
        except Exception as e:
            logger.warning(
                f"Director step2 (small model) parse error: {e}\n"
                f"Raw (first 300): {content[:300]}"
            )
            return {"scenes": []}

    # ── Sonnet-class path: Anthropic Tool Use (Phase 13-2 Step 4f) ─────────
    logger.info(
        "[director/step2] using structured-output (Tool Use) — Phase 13-2 Step 4f"
    )

    system = _SYSTEM_DETAILS
    # Sprint 9-2: thread world_variables through so Director can wire
    # each scene's state_reads / state_writes / branch.requires to the
    # variables it declared in step1.
    world_vars = outline.get("world_variables") or []
    world_vars_block = ""
    if world_vars:
        world_vars_lines = [
            f"  - {v['name']} ({v['type']}, starts {v.get('initial_value')!r}): "
            f"{v.get('description', '')[:80]}"
            for v in world_vars
        ]
        world_vars_block = (
            "\n\nWorld variables declared in step1 (use these in state_reads / "
            "state_writes / branch.requires):\n" + "\n".join(world_vars_lines)
        )

    # Tool Use prompt: NO JSON example (the schema delivers structure via
    # the tool definition). Field-level prose constraints retained because
    # the Pydantic schema can't express "this field is REQUIRED in semantics
    # even though it's Optional in the schema" — Director step1 outline has
    # default_factory on most fields, so LLM omitting them is schema-legal
    # but breaks downstream consumption.
    user_prompt = f"""You have this scene list:
{scene_list}

All valid scene IDs: {json.dumps(scene_ids)}
Start scene: {outline.get("start_scene_id", "")}{world_vars_block}

Call the `DirectorStep2Output` tool exactly once with one entry per scene
above. For EACH scene, specify navigation, music, transition cards, state
I/O, narrative graph deps, and a creative scene_brief.

## Plan first via the `reasoning` field (Phase 13-3 M0-2)

BEFORE filling `scenes`, fill the `reasoning` field with a brief plan
(≤800 chars, prose paragraph form, NOT bullets):
- Which scenes are turning points (need branches), which are linear
- Where to wire `state_reads` / `state_writes` for narrative impact
- Which characters appear physically vs by reference in each scene
- Where to plant foreshadow / arc beats via `context_deps`

The `reasoning` field is YOUR scratchpad — use it to think coherently
before committing to the structural choices in `scenes`. Keep it tight;
this is planning, not prose drafting.

## What every scene MUST include

Each entry in the `scenes` list MUST include:

1. `id` — must match a scene id from the outline above (use ONLY listed IDs)
2. `next_scene_id` — null only for terminal scenes (end of route) or
   branch-only scenes; otherwise the id of the auto-advance target
3. `branches` — empty list OK for non-turning-point scenes; AT LEAST ONE
   branch per turning-point scene where player choice changes outcome.
   Place branches at TURNING POINTS, not cosmetic forks. Each branch:
   `text` (choice shown to player), `next_scene_id` (valid scene id),
   `requires` (symbolic guard, see State I/O below; empty dict = always visible)
4. `music_mood` + `music_description` — required; mood transitions matter
   (peaceful → tense → melancholic / joyful etc.)
5. `entry_context` + `exit_hook` — what player just experienced + setup for
   next scene. 1-2 sentences each, NOT prose. Empty string "" for the
   start scene's entry_context and terminal scenes' exit_hook.
6. `emotional_arc` — short trajectory (e.g. "warmth -> anticipation",
   "hope -> despair")
7. `state_reads` / `state_writes` — list/dict; empty [] / {{}} if scene
   reads/writes no symbolic state, but ALWAYS include the keys. Only
   reference variables from the declared list above. Branch `requires` is
   the same shape — empty dict means always visible.
8. `context_deps` — up to 5 references; PREFER `foreshadow_payoff` or
   `arc_beat` over generic `callback`. Each dep:
   * `ref_type`: one of "scene" / "character_arc" / "world_var" / "motif" /
     "location"
   * `ref_id`: target — bare scene id for "scene"; "character:{{id}}",
     "world_var:{{name}}", "motif:{{tag}}", "location:{{bg_id}}" for the rest
   * `link_type`: "callback" / "foreshadow_payoff" / "arc_beat" /
     "state_dependency" / "motif_recurrence"
   * `reason`: one sentence
   * `inject_as`: "full_dialogue" / "summary" / "state_snapshot" /
     "character_arc_so_far"
   **Backward-only**: scene refs must point to EARLIER scenes, never forward,
   never self. `state_dependency` refs MUST also appear in `state_reads`.
   Be sparing — list only dependencies you are ≥0.7 confident about. Early
   scenes (especially start) typically have `context_deps=[]`.
9. `scene_brief` — REQUIRED tight planning artifact (Phase 13-2 Step 1):
   * `beats`: 3-7 ordered scene events (≤80 chars each) — the creative spine
   * `character_blocking`: {{character_id: position/movement/posture}} per
     character in `characters_present` (from the outline)
   * `emotional_curve`: 2-5 emotion labels tracking the scene's internal arc
   * `tension_target`: one of "low" / "medium" / "high" / "climax"
   * `subtext_notes`: what stays UNSAID between lines (≤400 chars)
   Keep it tight — this is a PLANNING artifact, not prose. Writer workers
   will inflate beats into actual dialogue; they need the skeleton, not
   your draft."""

    # Phase 13-2 Step 4e: APPEND retry feedback (cache-safe; see _step1_outline).
    if retry_feedback:
        user_prompt += "\n\n" + retry_feedback

    expected_count = len(outline.get("scenes") or [])

    try:
        # ainvoke_llm's return type is `T | str`; with schema= it's
        # always the Pydantic instance, but the static signature can't
        # express that conditional. cast() narrows for the rest of the
        # function — runtime contract is enforced by the schema kwarg.
        result = cast(
            DirectorStep2Output,
            await ainvoke_llm(
                system, user_prompt,
                schema=DirectorStep2Output,
                model=settings.llm_director_model,
                caller="director/step2",
                cache_ttl="1h", force_cache=True,
            ),
        )
    except ValidationError as e:
        # Don't swallow silently — exc_info=True lets dev locate schema
        # mismatch quickly. step2 is a graph-critical node so still
        # graceful-degrade to {"scenes": []} for run continuation.
        logger.error(
            f"[director/step2] structured output validation failed: {e}",
            exc_info=True,
        )
        return {"scenes": []}
    except Exception as e:  # noqa: BLE001 — broad catch is intentional for graceful degradation
        logger.warning(
            f"[director/step2] tool_use call failed (using defaults): {e}"
        )
        return {"scenes": []}

    # Persist a JSON dump for debug parity with the legacy raw-text path.
    try:
        _save_debug_raw(
            output_dir, "director_step2_raw.txt",
            result.model_dump_json(indent=2),
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[director/step2] debug dump failed: {e}")

    actual_count = len(result.scenes)

    # Silent-failure guards — schema validity is NOT the same as semantic
    # completeness. LLM may produce a schema-legal-but-empty payload, or
    # skip half the scenes if it interprets the tool spec loosely.
    if actual_count == 0:
        logger.warning(
            f"[director/step2] empty structured output "
            f"(expected {expected_count} scenes)"
        )
    elif actual_count < expected_count:
        logger.warning(
            f"[director/step2] scene shrinkage: got {actual_count}, "
            f"expected {expected_count} — possible Tool Use truncation "
            f"or model omission"
        )

    # Observability log: makes "schema passed but LLM skipped fields"
    # detectable via grep without parsing the dumped JSON.
    total_branches = sum(len(s.branches) for s in result.scenes)
    total_state_writes = sum(len(s.state_writes) for s in result.scenes)
    total_briefs = sum(1 for s in result.scenes if s.scene_brief is not None)
    total_deps = sum(len(s.context_deps) for s in result.scenes)
    # Phase 13-3 M0-2: reasoning_chars tracks whether model uses the
    # scratchpad. If consistently == 0, the field isn't restoring CoT and
    # we'll need to escalate (e.g. raise its priority, add prompt examples).
    reasoning_chars = len(result.reasoning or "")
    logger.info(
        f"[director/step2] tool_use ok: scenes={actual_count} "
        f"branches_total={total_branches} state_writes_total={total_state_writes} "
        f"scene_briefs={total_briefs} context_deps_total={total_deps} "
        f"reasoning_chars={reasoning_chars}"
    )

    return result.model_dump()


def _merge_outline_details(outline: dict, details: dict) -> dict:
    """Merge step2 navigation/music into step1 outline scenes."""
    detail_map = {s["id"]: s for s in (details.get("scenes") or [])}
    merged_scenes = []
    for s in (outline.get("scenes") or []):
        d = detail_map.get(s["id"], {})
        merged = {**s}
        merged["next_scene_id"] = d.get("next_scene_id")
        merged["branches"] = d.get("branches") or []
        merged["music_mood"] = d.get("music_mood", "neutral")
        merged["music_description"] = d.get("music_description", "")
        # Transition cards (Sprint 6-1)
        merged["emotional_arc"] = d.get("emotional_arc") or None
        merged["entry_context"] = d.get("entry_context") or None
        merged["exit_hook"] = d.get("exit_hook") or None
        # Sprint 9-2: state I/O from step2
        merged["state_reads"] = d.get("state_reads") or []
        merged["state_writes"] = d.get("state_writes") or {}
        # Phase 13-1 / Step 5: narrative graph context_deps. Validation
        # (backward-only, existing refs, state_dependency in state_reads)
        # happens in StructureReviewer — merge step just carries the raw
        # list through. Defaults to [] if Director didn't emit.
        merged["context_deps"] = d.get("context_deps") or []
        # Phase 13-2 / Step 1: per-scene creative brief (route-4 prep). Raw
        # dict here; hydration to SceneBrief happens in _build_from_plan
        # so validation failures log+drop instead of killing the pipeline.
        merged["scene_brief"] = d.get("scene_brief") or None
        merged_scenes.append(merged)
    # Filter out invalid branch/next_scene_id references from step2
    valid_ids = {s["id"] for s in merged_scenes}
    for s in merged_scenes:
        s["branches"] = [b for b in s["branches"] if b.get("next_scene_id") in valid_ids]
        if s.get("next_scene_id") and s["next_scene_id"] not in valid_ids:
            logger.warning(f"Scene {s['id']}: next_scene_id '{s['next_scene_id']}' invalid, cleared")
            s["next_scene_id"] = None

    return {**outline, "scenes": merged_scenes}


def _save_debug_raw(output_dir: str, filename: str, content: str) -> None:
    """Save raw LLM response to debug/ directory (best-effort, never raises)."""
    try:
        debug_dir = Path(output_dir) / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / filename).write_text(content, encoding="utf-8")
    except Exception as e:
        logger.debug(f"Could not save debug raw response: {e}")


def _save_checkpoint(output_dir: str, script, characters: dict) -> None:
    """Save vn_script.json + characters.json after Director completes (best-effort)."""
    import json as _json
    try:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "vn_script.json").write_text(
            script.model_dump_json(indent=2), encoding="utf-8"
        )
        chars_data = {k: v.model_dump() for k, v in characters.items()}
        (out / "characters.json").write_text(
            _json.dumps(chars_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(f"Director checkpoint saved to {out}")
    except Exception as e:
        logger.warning(f"Could not save Director checkpoint: {e}")


def _extract_json(content: str) -> dict:
    """Extract JSON from LLM response.

    Phase 13-2 Step 4f: removed truncation salvage path. step2 now uses
    Tool Use (DirectorStep2Output schema) which can't return partial JSON;
    step1 + _attempt_repair retain raw-text JSON parsing because their
    payloads are smaller and they don't currently exhibit truncation. If
    step1 starts truncating, the right fix is migration to Tool Use
    (DirectorStep1Output), not band-aiding with salvage.
    """
    import re

    # Strip markdown code fences to get raw JSON text
    stripped = re.sub(r'^```(?:json)?\s*', '', content.strip(), flags=re.MULTILINE)
    stripped = re.sub(r'\s*```\s*$', '', stripped.strip(), flags=re.MULTILINE)

    # 1. Try raw_decode from first { (handles both complete and inline JSON)
    start = stripped.find('{')
    if start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(stripped, start)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # 2. Try full content as-is
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    raise ValueError(f"Could not extract JSON from response: {content[:200]}")


def _validate_branch_structure(script: VNScript) -> list[str]:
    """Structural check on branch design (Sprint 6-6, Director layer).

    Validates:
      1. Each scene's branches point to distinct `next_scene_id`s — two
         branches leading to the same scene is always cosmetic.
      2. Each branch's downstream reachable set has at least one scene
         exclusive to that path (checked via BFS up to depth 3). If both
         branch paths converge immediately without any independent content,
         the choice is meaningless.

    Returns a list of human-readable issues. Empty list means structure is OK.
    This is pure code, no LLM — it catches the most obvious structural bugs
    before Writer burns tokens on a broken tree.
    """
    issues: list[str] = []
    scene_map = {s.id: s for s in script.scenes}

    for scene in script.scenes:
        if len(scene.branches) < 2:
            continue  # no branch or single branch degenerates to linear

        # Rule 1: branches must target distinct scenes
        targets = [b.next_scene_id for b in scene.branches]
        if len(set(targets)) < len(targets):
            issues.append(
                f"Scene '{scene.id}': branches share the same next_scene_id "
                f"({targets}) — at least two choices lead to the same place."
            )
            continue  # skip rule 2, already broken

        # Rule 2: each branch should have exclusive downstream content
        reachable_sets = [
            _reachable_within(scene_map, b.next_scene_id, max_depth=3)
            for b in scene.branches
        ]
        # Find pairwise intersections — if every scene in one path is also in
        # another path, the choice had no independent consequence.
        for i, ri in enumerate(reachable_sets):
            if not ri:
                continue
            for j, rj in enumerate(reachable_sets):
                if j <= i or not rj:
                    continue
                exclusive_i = ri - rj
                exclusive_j = rj - ri
                if not exclusive_i and not exclusive_j:
                    issues.append(
                        f"Scene '{scene.id}': branches {i} and {j} converge with "
                        f"no exclusive downstream content — cosmetic choice."
                    )
    return issues


def _reachable_within(
    scene_map: dict[str, Scene], start_id: str, max_depth: int = 3,
) -> set[str]:
    """BFS reachable scene ids from start_id up to max_depth hops (inclusive)."""
    if start_id not in scene_map:
        return set()
    reached: set[str] = set()
    frontier: list[tuple[str, int]] = [(start_id, 0)]
    while frontier:
        sid, depth = frontier.pop(0)
        if sid in reached or depth > max_depth:
            continue
        reached.add(sid)
        scene = scene_map.get(sid)
        if not scene:
            continue
        next_ids: list[str] = []
        if scene.next_scene_id:
            next_ids.append(scene.next_scene_id)
        next_ids.extend(b.next_scene_id for b in scene.branches if b.next_scene_id)
        for nid in next_ids:
            if nid not in reached:
                frontier.append((nid, depth + 1))
    return reached


def _degrade_invalid_branches(script: VNScript, issues: list[str]) -> None:
    """Fallback: strip branches from scenes flagged as structurally invalid.

    Picks the first branch as the linear next_scene_id. Preserves the rest of
    the script so the pipeline can continue and Reviewer can report the warning.
    """
    flagged_scenes = {
        # issues start with "Scene '<id>':"
        issue.split("'")[1] for issue in issues if "'" in issue
    }
    for scene in script.scenes:
        if scene.id in flagged_scenes and scene.branches:
            first_target = scene.branches[0].next_scene_id
            scene.branches = []
            if not scene.next_scene_id:
                scene.next_scene_id = first_target


async def _attempt_repair(plan_data: dict, error_msg: str, output_dir: str, settings) -> dict | None:
    """Attempt to repair invalid plan data by feeding the error back to the LLM."""
    try:
        repair_prompt = (
            f"The following JSON plan failed validation with this error:\n{error_msg}\n\n"
            f"Original plan (may be truncated):\n{json.dumps(plan_data, indent=2, ensure_ascii=False)[:3000]}\n\n"
            "Fix the JSON to resolve the error. Return ONLY the corrected JSON."
        )
        response = await ainvoke_llm(
            "You are a JSON repair assistant. Fix the provided JSON to pass validation.",
            repair_prompt,
            model=settings.llm_director_model,
            caller="director/repair",
        )
        content = response.content if hasattr(response, "content") else str(response)
        _save_debug_raw(output_dir, "director_repair_raw.txt", content)
        return _extract_json(content)
    except Exception as e:
        logger.warning(f"LLM repair failed: {e}")
        return None


def _build_from_plan(plan: dict, theme: str) -> tuple[VNScript, dict[str, CharacterProfile]]:
    """Convert plan dict to VNScript and CharacterProfile dict."""
    # Build characters
    characters: dict[str, CharacterProfile] = {}
    # Use `or []` to handle both missing keys AND JSON null values
    for c in plan.get("characters") or []:
        char = CharacterProfile(
            id=c["id"],
            name=c["name"],
            color=c.get("color") or "#ffffff",
            personality=c.get("personality") or "",
            background=c.get("background") or "",
            role=c.get("role") or "supporting",
        )
        characters[char.id] = char

    # Build scenes
    scenes: list[Scene] = []
    for s in plan.get("scenes") or []:
        # Build music cue
        music = None
        if s.get("music_mood"):
            try:
                mood = Mood(s["music_mood"])
            except ValueError:
                mood = Mood.NEUTRAL
            music = MusicCue(
                mood=mood,
                description=s.get("music_description") or f"{mood.value} background music",
            )

        # Build branches — handle null from LLM
        branches = [
            BranchOption(
                text=b["text"],
                next_scene_id=b["next_scene_id"],
                # Sprint 9-1: symbolic guard on visibility
                requires=b.get("requires") or {},
            )
            for b in (s.get("branches") or [])
            if b and b.get("text") and b.get("next_scene_id")
        ]

        # Phase 13-2 Step 1: hydrate scene_brief if present. Validation
        # failures log+drop rather than abort — missing brief is harmless
        # (Writer just doesn't have the extra planning signal yet).
        scene_brief_obj = None
        brief_raw = s.get("scene_brief")
        if brief_raw:
            try:
                scene_brief_obj = SceneBrief.model_validate(brief_raw)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"scene_brief invalid for scene '{s.get('id', '?')}', "
                    f"dropping: {e}"
                )

        scene = Scene(
            id=s["id"],
            title=s.get("title") or s["id"],
            description=s.get("description") or "",
            background_id=s.get("background_id") or f"bg_{s['id']}",
            music=music,
            characters_present=s.get("characters_present") or [],
            dialogue=[],  # Writer fills this in
            branches=branches,
            next_scene_id=s.get("next_scene_id"),
            narrative_strategy=s.get("narrative_strategy"),
            # Transition cards (Sprint 6-1)
            entry_context=s.get("entry_context") or None,
            exit_hook=s.get("exit_hook") or None,
            emotional_arc=s.get("emotional_arc") or None,
            # Sprint 9-1: symbolic state I/O
            state_reads=s.get("state_reads") or [],
            state_writes=s.get("state_writes") or {},
            # Phase 13-2 Step 1
            scene_brief=scene_brief_obj,
        )
        scenes.append(scene)

    # Sprint 9-1: Director-declared world variables
    world_variables: list[WorldVariable] = []
    for v in plan.get("world_variables") or []:
        try:
            world_variables.append(WorldVariable(**v))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Skipped invalid world_variable {v.get('name', '?')}: {e}")

    # Phase 13-2 Step 1: hydrate macro_reference if present. Same log+drop
    # policy as scene_brief — missing macro_reference just means route-4
    # downstream workers fall back to per-run system prompt without the
    # shared voice charter.
    macro_ref = None
    macro_raw = plan.get("macro_reference")
    if macro_raw:
        try:
            macro_ref = MacroReference.model_validate(macro_raw)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"macro_reference invalid, dropping: {e}")

    script = VNScript(
        title=plan.get("title", "Untitled Story"),
        description=plan.get("description", ""),
        theme=theme,
        start_scene_id=plan.get("start_scene_id", scenes[0].id if scenes else ""),
        scenes=scenes,
        characters=list(characters.keys()),
        world_variables=world_variables,
        # Phase 13-2 Step 1
        macro_reference=macro_ref,
    )
    return script, characters


# ---------------------------------------------------------------------------
# Phase 13-2 Step 4e: Director retry nodes
#
# Re-invoked after structure_reviewer flags actionable findings AND the
# routing helper (vn_agent.agents.routing.decide_retry_target) decides
# Director should re-run. Two flavors:
#
#   run_director_step2_redo: re-runs step2 only, reusing step1's outline
#     + chapters + characters + world_vars + macro_reference. Cheaper
#     (~$0.27 vs $0.35 full retry); fixes per-scene wiring issues
#     (branch wiring, strategy assignment, branch_intent_misalign).
#
#   run_director_full_redo: re-runs both step1 and step2 from scratch
#     with feedback. Used when findings include step1-class issues
#     (roster_unused, macro_pacing_misaligned, foreshadow_payoff_missing,
#     world_var_unused) where step2-only retry would either fail or
#     produce a forced cameo.
#
# Both APPEND feedback to the user_prompt (cache-safe; see _step1_outline
# / _step2_details for the rationale on why prepending breaks the
# Anthropic prefix cache).
# ---------------------------------------------------------------------------


def _format_retry_feedback(findings: list) -> str:
    """Render StructureFinding[] as an APPEND-safe block for Director's
    next user_prompt. Groups by category so Director can address each
    family in one pass instead of treating every finding independently.
    Drops requires_retry=False findings — those are advisory, no point
    asking Director to "fix" them.
    """
    actionable = [f for f in findings if getattr(f, "requires_retry", False)]
    if not actionable:
        return ""
    by_cat: dict[str, list] = {}
    for f in actionable:
        by_cat.setdefault(f.category, []).append(f)
    # Phase 13-2 Step 4e/4 (Gemini hardening NIT #d): explicit "modify
    # ONLY flagged" language. Pre-fix Sonnet would helpfully rewrite
    # adjacent unflagged scenes too, which silently regressed
    # well-formed parts of the outline. This wording anchors stability.
    parts = [
        "## RETRY FEEDBACK (Phase 13-2 Step 4e)",
        "",
        "The previous outline had structural issues that must be addressed in",
        "this revision. Re-emit the FULL JSON, modifying ONLY the scenes or",
        "fields flagged below. Preserve all other scenes, characters, IDs,",
        "world variables, and macro_reference exactly as they were.",
        "",
    ]
    for cat, items in by_cat.items():
        parts.append(f"### {cat} ({len(items)} finding{'s' if len(items) > 1 else ''})")
        for f in items:
            scene_marker = (
                f"[scene={f.target_scene_id}] " if getattr(f, "target_scene_id", None)
                else ""
            )
            parts.append(f"  - {scene_marker}{f.message}")
        parts.append("")
    return "\n".join(parts)


def _outline_dict_from_script(
    script: VNScript, characters: dict[str, CharacterProfile],
    art_direction: str,
) -> dict:
    """Reconstruct the step1 `outline` dict from an existing VNScript +
    characters. Used by step2_redo to feed _step2_details without
    re-running step1.
    """
    return {
        "title": script.title,
        "description": script.description,
        "art_direction": art_direction,
        "start_scene_id": script.start_scene_id,
        "scenes": [
            {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "background_id": s.background_id,
                "characters_present": list(s.characters_present),
                "narrative_strategy": s.narrative_strategy,
            }
            for s in script.scenes
        ],
        "characters": [
            {
                "id": c.id,
                "name": c.name,
                "color": getattr(c, "color", "#aabbcc"),
                "personality": c.personality,
                "background": c.background,
                "role": c.role,
            }
            for c in characters.values()
        ],
        "world_variables": [
            {
                "name": v.name,
                "type": v.type,
                "initial_value": v.initial_value,
                "description": v.description,
            }
            for v in script.world_variables
        ],
        "macro_reference": (
            script.macro_reference.model_dump() if script.macro_reference else None
        ),
    }


async def run_director_step2_redo(state: AgentState) -> dict:
    """Phase 13-2 Step 4e: re-run Director step2 only with feedback.

    Triggered by routing.decide_retry_target("step2_only") when
    structure_reviewer flagged step2-class issues (per-scene wiring:
    branch_intent_misalign, branch_target_invalid, etc.). Reuses
    step1's outline + chapters + characters + macro_reference, just
    re-emits per-scene navigation/branches/scene_brief with feedback
    appended to the user prompt.
    """
    settings = get_settings()
    output_dir = state.get("output_dir", ".")
    theme = state["theme"]
    script: VNScript | None = state.get("vn_script")
    characters = state.get("characters", {}) or {}
    art_direction = state.get("art_direction", "")
    findings = state.get("structure_review_findings", []) or []
    rev = state.get("director_revision_count", 0)

    if script is None:
        logger.warning("director_step2_redo: no vn_script in state, skipping")
        return {"director_revision_count": rev + 1}

    feedback = _format_retry_feedback(findings)
    logger.info(
        f"Director step2 redo (revision {rev + 1}): feedback "
        f"covers {sum(1 for f in findings if f.requires_retry)} actionable "
        f"finding(s)"
    )

    outline = _outline_dict_from_script(script, characters, art_direction)
    detail_data = await _step2_details(
        outline, output_dir, settings, retry_feedback=feedback,
    )
    plan_data = _merge_outline_details(outline, detail_data)

    try:
        new_script, new_characters = _build_from_plan(plan_data, theme)
    except Exception as e:
        logger.warning(
            f"Director step2 redo build failed, attempting LLM repair: {e}"
        )
        repaired = await _attempt_repair(plan_data, str(e), output_dir, settings)
        if repaired:
            new_script, new_characters = _build_from_plan(repaired, theme)
        else:
            logger.error(
                f"Director step2 redo failed; keeping prior script: {e}"
            )
            return {"director_revision_count": rev + 1}

    branch_issues = _validate_branch_structure(new_script)
    if branch_issues:
        logger.warning(
            f"director_step2_redo: branch issues after retry "
            f"({len(branch_issues)}) — degrading"
        )
        _degrade_invalid_branches(new_script, branch_issues)

    _save_checkpoint(output_dir, new_script, new_characters)

    # world_state stays seeded from new_script.world_variables (step1
    # outputs are reused via the outline reconstruction, so initial values
    # are unchanged from the prior run; explicit reseed keeps the contract).
    world_state: dict = {v.name: v.initial_value for v in new_script.world_variables}

    return {
        "vn_script": new_script,
        "characters": new_characters,
        "world_state": world_state,
        "director_revision_count": rev + 1,
    }


async def run_director_full_redo(state: AgentState) -> dict:
    """Phase 13-2 Step 4e: re-run Director step1 AND step2 with feedback.

    Triggered by routing.decide_retry_target("step1_step2") when
    structure_reviewer flagged step1-class issues (roster_unused,
    world_var_unused, macro_pacing_misaligned, foreshadow_payoff_missing).
    These can't be fixed by step2-only retry — declarations live in step1.
    """
    settings = get_settings()
    output_dir = state.get("output_dir", ".")
    theme = state["theme"]
    max_scenes = state.get("max_scenes", 10)
    num_characters = state.get("num_characters", 3)
    findings = state.get("structure_review_findings", []) or []
    rev = state.get("director_revision_count", 0)

    feedback = _format_retry_feedback(findings)
    logger.info(
        f"Director full redo (revision {rev + 1}): feedback covers "
        f"{sum(1 for f in findings if f.requires_retry)} actionable finding(s)"
    )

    outline_data = await _step1_outline(
        theme, max_scenes, num_characters, output_dir, settings,
        retry_feedback=feedback,
    )
    detail_data = await _step2_details(
        outline_data, output_dir, settings, retry_feedback=feedback,
    )
    plan_data = _merge_outline_details(outline_data, detail_data)

    try:
        script, characters = _build_from_plan(plan_data, theme)
    except Exception as e:
        logger.warning(f"Director full redo build failed, attempting repair: {e}")
        repaired = await _attempt_repair(plan_data, str(e), output_dir, settings)
        if repaired:
            script, characters = _build_from_plan(repaired, theme)
        else:
            logger.error(
                f"Director full redo failed; keeping prior script: {e}"
            )
            return {"director_revision_count": rev + 1}

    branch_issues = _validate_branch_structure(script)
    if branch_issues:
        logger.warning(
            f"director_full_redo: branch issues after retry "
            f"({len(branch_issues)}) — degrading"
        )
        _degrade_invalid_branches(script, branch_issues)

    _save_checkpoint(output_dir, script, characters)

    art_direction = plan_data.get("art_direction") or state.get("art_direction", "")
    if not art_direction:
        art_direction = (
            "painterly anime style, consistent color palette, atmospheric lighting"
        )

    world_state: dict = {v.name: v.initial_value for v in script.world_variables}

    return {
        "vn_script": script,
        "characters": characters,
        "art_direction": art_direction,
        "world_state": world_state,
        "director_revision_count": rev + 1,
    }
