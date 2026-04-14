"""Director Agent: Plans story structure, scenes, and characters."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from vn_agent.agents.state import AgentState
from vn_agent.config import get_settings
from vn_agent.prompts.templates import (
    DIRECTOR_DETAILS_SYSTEM,
    DIRECTOR_OUTLINE_SYSTEM,
    strip_thinking,
)
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.music import Mood, MusicCue
from vn_agent.schema.script import BranchOption, Scene, VNScript, WorldVariable
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
    theme: str, max_scenes: int, num_characters: int, output_dir: str, settings
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
  ]
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
gating. Only declare variables the story will actually read or write."""

    response = await ainvoke_llm(system, user_prompt, model=settings.llm_director_model, caller="director/step1")
    content = response.content if hasattr(response, "content") else str(response)
    _save_debug_raw(output_dir, "director_step1_raw.txt", content)
    content = strip_thinking(content)

    try:
        return _extract_json(content)
    except Exception as e:
        logger.error(f"Director step1 parse error: {e}\nRaw (first 500): {content[:500]}")
        raise


async def _step2_details(outline: dict, output_dir: str, settings) -> dict:
    """Step 2: add navigation (next_scene_id/branches) and music mood to each scene."""
    small = _is_small_model(settings.llm_director_model)
    scene_ids = [s["id"] for s in (outline.get("scenes") or [])]
    scene_list = "\n".join(
        f'  - {s["id"]}: {s.get("title", "")} — {s.get("description", "")[:60]}'
        for s in (outline.get("scenes") or [])
    )

    if small:
        system = _SYSTEM_DETAILS_SIMPLE
        # Small model: require only emotional_arc (lightweight transition signal)
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
    else:
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

        user_prompt = f"""You have this scene list:
{scene_list}

All valid scene IDs: {json.dumps(scene_ids)}
Start scene: {outline.get("start_scene_id", "")}{world_vars_block}

For EACH scene, specify navigation, music, transition cards, AND state I/O. Return this JSON:
{{
  "scenes": [
    {{
      "id": "ch1_opening",
      "next_scene_id": "ch1_next_or_null",
      "branches": [
        {{"text": "Choice text", "next_scene_id": "valid_scene_id",
          "requires": {{}}}}
      ],
      "music_mood": "peaceful",
      "music_description": "soft piano",
      "emotional_arc": "curiosity -> unease",
      "entry_context": "What the player just experienced (for non-start scenes)",
      "exit_hook": "How this scene should end to set up the next",
      "state_reads": [],
      "state_writes": {{}}
    }}
  ]
}}

Rules:
- Use ONLY scene IDs from the list above
- A scene with branches should have next_scene_id=null
- Terminal scenes: next_scene_id=null, branches=[]
- Include at least 2 scenes with meaningful branches
- **Transition cards**: entry_context describes the prior scene's ending mood/event \
(leave empty "" for the start scene). exit_hook describes what this scene sets up \
(leave empty "" for terminal scenes with no successor). emotional_arc is short, \
like "warmth -> anticipation" or "hope -> despair".
- **State I/O (Sprint 9-1)**: state_reads lists world_variables this scene's \
dialogue depends on (empty [] if none). state_writes maps variable → new value \
for changes made by this scene (empty {{}} if none). branch.requires maps \
variable → expected value as a symbolic visibility guard (empty {{}} = always \
visible). Only reference variables from the declared list above. If no \
world_variables were declared, all three stay empty."""

    response = await ainvoke_llm(
        system, user_prompt, model=settings.llm_director_model, caller="director/step2",
    )
    content = response.content if hasattr(response, "content") else str(response)
    _save_debug_raw(output_dir, "director_step2_raw.txt", content)
    content = strip_thinking(content)

    try:
        return _extract_json(content)
    except Exception as e:
        logger.warning(f"Director step2 parse error (will use defaults): {e}\nRaw (first 300): {content[:300]}")
        return {"scenes": []}


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
    """Extract JSON from LLM response, handling truncated responses."""
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

    # 3. Response was truncated mid-JSON — try to salvage it
    # Find the last complete scene object and close the JSON structure
    if start != -1:
        salvaged = _salvage_truncated_json(stripped[start:])
        if salvaged:
            logger.warning("LLM response was truncated — salvaged partial JSON. Consider increasing max_tokens.")
            return salvaged

    raise ValueError(f"Could not extract JSON from response: {content[:200]}")


def _salvage_truncated_json(text: str) -> dict | None:
    """
    Attempt to fix a truncated JSON string using two strategies:
    1. Backward scan: find the last '}'/']' and close from there.
    2. Forward scan: find the last root-level comma and close the root object.

    Handles Unicode (e.g. Chinese) text safely — never strips by character value.
    """
    closing = {'{': '}', '[': ']'}

    def _close_and_parse(candidate: str) -> dict | None:
        """Close unclosed brackets on `candidate` and try json.loads."""
        candidate = candidate.rstrip().rstrip(',').rstrip()
        open_stack: list[str] = []
        in_str = False
        escape = False
        for ch in candidate:
            if escape:
                escape = False
                continue
            if ch == '\\' and in_str:
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch in closing:
                open_stack.append(closing[ch])
            elif ch in ('}', ']'):
                if open_stack and open_stack[-1] == ch:
                    open_stack.pop()
        suffix = ''.join(reversed(open_stack))
        try:
            result = json.loads(candidate + suffix)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        return None

    # Strategy 1: scan backward for '}' or ']' and attempt to complete from there.
    # Works when truncation happens inside a nested object/array.
    for i in range(len(text) - 1, -1, -1):
        if text[i] in ('}', ']'):
            result = _close_and_parse(text[:i + 1])
            if result:
                return result

    # Strategy 2: scan forward tracking JSON structure to find the last
    # root-level comma (between top-level fields). Cut there and close.
    # Works when truncation happens so early that no '}' exists yet.
    last_root_comma = -1
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == '\\' and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in closing:
            depth += 1
        elif ch in ('}', ']'):
            depth -= 1
        elif ch == ',' and depth == 1:
            last_root_comma = i

    if last_root_comma > 0:
        return _close_and_parse(text[:last_root_comma])

    return None


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
        )
        scenes.append(scene)

    # Sprint 9-1: Director-declared world variables
    world_variables: list[WorldVariable] = []
    for v in plan.get("world_variables") or []:
        try:
            world_variables.append(WorldVariable(**v))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Skipped invalid world_variable {v.get('name', '?')}: {e}")

    script = VNScript(
        title=plan.get("title", "Untitled Story"),
        description=plan.get("description", ""),
        theme=theme,
        start_scene_id=plan.get("start_scene_id", scenes[0].id if scenes else ""),
        scenes=scenes,
        characters=list(characters.keys()),
        world_variables=world_variables,
    )
    return script, characters
