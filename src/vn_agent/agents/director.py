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

    response = await ainvoke_llm(system, user_prompt)

    # Parse response
    content = response.content if hasattr(response, 'content') else str(response)

    # Extract JSON from response
    plan_data = _extract_json(content)

    # Build VNScript from plan
    script, characters = _build_from_plan(plan_data, theme)

    logger.info(f"Director created: '{script.title}' with {len(script.scenes)} scenes, {len(characters)} characters")

    return {
        "vn_script": script,
        "characters": characters,
    }


def _extract_json(content: str) -> dict:
    """Extract JSON from LLM response."""
    import re
    # Try to find JSON block
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))
    # Try to parse entire content as JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Find outermost braces
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1:
            return json.loads(content[start:end+1])
        raise ValueError(f"Could not extract JSON from response: {content[:200]}")


def _build_from_plan(plan: dict, theme: str) -> tuple[VNScript, dict[str, CharacterProfile]]:
    """Convert plan dict to VNScript and CharacterProfile dict."""
    # Build characters
    characters: dict[str, CharacterProfile] = {}
    for c in plan.get("characters", []):
        char = CharacterProfile(
            id=c["id"],
            name=c["name"],
            color=c.get("color", "#ffffff"),
            personality=c.get("personality", ""),
            background=c.get("background", ""),
            role=c.get("role", "supporting"),
        )
        characters[char.id] = char

    # Build scenes
    scenes: list[Scene] = []
    for s in plan.get("scenes", []):
        # Build music cue
        music = None
        if s.get("music_mood"):
            try:
                mood = Mood(s["music_mood"])
            except ValueError:
                mood = Mood.NEUTRAL
            music = MusicCue(
                mood=mood,
                description=s.get("music_description", f"{mood.value} background music"),
            )

        # Build branches
        branches = [
            BranchOption(text=b["text"], next_scene_id=b["next_scene_id"])
            for b in s.get("branches", [])
        ]

        scene = Scene(
            id=s["id"],
            title=s.get("title", s["id"]),
            description=s.get("description", ""),
            background_id=s.get("background_id", f"bg_{s['id']}"),
            music=music,
            characters_present=s.get("characters_present", []),
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
