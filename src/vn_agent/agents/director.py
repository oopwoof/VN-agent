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
from vn_agent.schema.script import BranchOption, Scene, VNScript
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

    logger.info(f"Director created: '{script.title}' with {len(script.scenes)} scenes, {len(characters)} characters")

    # Checkpoint: save immediately so --resume works if Writer crashes
    _save_checkpoint(output_dir, script, characters)

    # Extract art direction from plan (set by Director for style consistency)
    art_direction = plan_data.get("art_direction", "")
    if not art_direction:
        art_direction = "painterly anime style, consistent color palette, atmospheric lighting"

    return {
        "vn_script": script,
        "characters": characters,
        "art_direction": art_direction,
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
      "role": "protagonist"
    }}
  ]
}}"""

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
        example = (
            '{{"scenes":[{{"id":"scene_id","next_scene_id":"next_or_null",'
            '"branches":[],"music_mood":"peaceful","music_description":"soft piano"}}]}}'
        )
        user_prompt = f"""Scenes: {json.dumps(scene_ids)}
Start: {outline.get("start_scene_id", "")}

For each scene add next_scene_id and music_mood. Last scene has next_scene_id=null.
Add branches (choices) to at least 1 scene.

Return JSON: {example}

Output ONLY JSON."""
    else:
        system = _SYSTEM_DETAILS
        user_prompt = f"""You have this scene list:
{scene_list}

All valid scene IDs: {json.dumps(scene_ids)}
Start scene: {outline.get("start_scene_id", "")}

For EACH scene, specify navigation and music. Return this JSON:
{{
  "scenes": [
    {{
      "id": "ch1_opening",
      "next_scene_id": "ch1_next_or_null",
      "branches": [{{"text": "Choice text", "next_scene_id": "valid_scene_id"}}],
      "music_mood": "peaceful",
      "music_description": "soft piano"
    }}
  ]
}}

Rules:
- Use ONLY scene IDs from the list above
- A scene with branches should have next_scene_id=null
- Terminal scenes: next_scene_id=null, branches=[]
- Include at least 2 scenes with meaningful branches"""

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
            BranchOption(text=b["text"], next_scene_id=b["next_scene_id"])
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
        )
        scenes.append(scene)

    script = VNScript(
        title=plan.get("title", "Untitled Story"),
        description=plan.get("description", ""),
        theme=theme,
        start_scene_id=plan.get("start_scene_id", scenes[0].id if scenes else ""),
        scenes=scenes,
        characters=list(characters.keys()),
    )
    return script, characters
