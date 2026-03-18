"""Director Agent: Plans story structure, scenes, and characters."""
from __future__ import annotations

import json
import logging
from pydantic import BaseModel, Field

from vn_agent.agents.state import AgentState
from vn_agent.schema.character import CharacterProfile, VisualProfile
from vn_agent.schema.script import VNScript, Scene, DialogueLine, BranchOption
from vn_agent.schema.music import Mood, MusicCue
from vn_agent.services.llm import ainvoke_llm
from vn_agent.strategies.narrative import format_strategies_for_prompt
from vn_agent.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Director of a visual novel project. Your job is to plan the overall story structure.

Given a theme, you will:
1. Create a compelling story outline with 5-15 scenes
2. Design 2-5 interesting characters
3. Assign narrative strategies to scenes
4. Determine BGM mood for each scene
5. Define branching points that make the story interactive

Output a complete story plan as structured JSON.

{strategies}

Rules:
- Every branch option MUST reference a valid scene ID
- The story must have exactly one start scene
- Every scene must be reachable from the start
- Use scene IDs like: ch1_scene_name (lowercase, underscores)
- Character IDs must be valid Python identifiers (lowercase, underscores)
- Include at least 2 meaningful branch points
"""

class StoryPlan(BaseModel):
    title: str
    description: str
    start_scene_id: str
    scenes: list[dict] = Field(description="List of scene plans")
    characters: list[dict] = Field(description="List of character plans")


async def run_director(state: AgentState) -> dict:
    """Director node: generates story plan from theme."""
    theme = state["theme"]
    settings = get_settings()
    logger.info(f"Director starting for theme: {theme[:50]}...")

    system = SYSTEM_PROMPT.format(strategies=format_strategies_for_prompt())

    max_scenes = state.get("max_scenes", 10)
    num_characters = state.get("num_characters", 3)

    user_prompt = f"""Create a visual novel story plan for this theme:

Theme: {theme}

Requirements:
- Up to {max_scenes} scenes total
- {num_characters} characters
- At least 2 meaningful player choices (branches)
- Clear emotional arc with beginning, middle, and end
- Assign a BGM mood (peaceful/romantic/tense/melancholic/joyful/mysterious/epic/neutral) to each scene

Return a JSON object with this exact structure:
{{
  "title": "Story Title",
  "description": "Brief story description",
  "start_scene_id": "ch1_opening",
  "scenes": [
    {{
      "id": "ch1_opening",
      "title": "Scene Title",
      "description": "What happens in this scene",
      "background_id": "bg_location_name",
      "music_mood": "peaceful",
      "music_description": "soft piano, gentle morning",
      "characters_present": ["char_id"],
      "next_scene_id": "ch1_next" or null,
      "branches": [
        {{"text": "Choice text", "next_scene_id": "ch1_option_a"}}
      ],
      "narrative_strategy": "accumulate"
    }}
  ],
  "characters": [
    {{
      "id": "char_protagonist",
      "name": "Display Name",
      "color": "#ff9966",
      "personality": "Personality description",
      "background": "Character backstory",
      "role": "protagonist"
    }}
  ]
}}"""

    response = await ainvoke_llm(system, user_prompt, model=settings.llm_director_model)

    # Parse response
    content = response.content if hasattr(response, 'content') else str(response)

    try:
        plan_data = _extract_json(content)
        script, characters = _build_from_plan(plan_data, theme)
    except Exception as e:
        logger.error(f"Director failed to parse LLM response: {e}\nRaw content (first 500 chars): {content[:500]}")
        raise

    if not script.scenes:
        logger.warning("Director produced 0 scenes — LLM may have returned empty/null scenes list")

    logger.info(f"Director created: '{script.title}' with {len(script.scenes)} scenes, {len(characters)} characters")

    return {
        "vn_script": script,
        "characters": characters,
    }


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
    Attempt to fix a truncated JSON string by progressively trimming incomplete
    trailing content and closing brackets until it parses.
    """
    # Walk backwards removing characters until we find valid JSON
    # This handles truncation at arbitrary points inside arrays/objects
    bracket_stack = []
    for i, ch in enumerate(text):
        if ch in ('{', '['):
            bracket_stack.append(ch)
        elif ch in ('}', ']'):
            if bracket_stack:
                bracket_stack.pop()

    if not bracket_stack:
        # Already balanced — try parsing as-is
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Find the last position where the JSON was "more complete"
    # Strategy: strip from the end until we can close all open brackets cleanly
    closing = {'{': '}', '[': ']'}
    candidate = text.rstrip()
    # Remove trailing comma if present (common at truncation boundary)
    while candidate.endswith(',') or candidate.endswith('"') or (
        candidate and candidate[-1] not in ('}', ']', '"', '0123456789', 'e', 'n')
    ):
        candidate = candidate[:-1].rstrip()
        if len(candidate) < 10:
            return None

    # Close all unclosed brackets
    open_stack = []
    for ch in candidate:
        if ch in ('{', '['):
            open_stack.append(closing[ch])
        elif ch in ('}', ']'):
            if open_stack and open_stack[-1] == ch:
                open_stack.pop()

    candidate += ''.join(reversed(open_stack))

    try:
        result = json.loads(candidate)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

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
