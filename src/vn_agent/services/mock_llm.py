"""Canned LLM responses for --mock mode.

Used by: vn-agent generate --mock
Used by: tests/test_integration/test_pipeline.py (imports dispatch logic)

Dispatch priority: caller tag > system prompt keywords.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Fixture responses ─────────────────────────────────────────────────────────

DIRECTOR_STEP1 = """{
  "title": "The Last Lighthouse",
  "description": "A keeper of a lighthouse on a dying coast must decide whether to stay and keep the light burning, or abandon the post and save themselves.",
  "start_scene_id": "ch1_arrival",
  "scenes": [
    {
      "id": "ch1_arrival",
      "title": "Storm's Eve",
      "description": "The lighthouse keeper Mara arrives at the remote post just as a massive storm rolls in from the sea.",
      "background_id": "bg_lighthouse_exterior",
      "characters_present": ["char_mara", "char_voice"],
      "narrative_strategy": "accumulate"
    },
    {
      "id": "ch1_signal",
      "title": "Distress Signal",
      "description": "A ship's distress signal flickers through the storm. Mara must decide whether to boost the lighthouse beam at personal risk.",
      "background_id": "bg_lighthouse_top",
      "characters_present": ["char_mara", "char_voice"],
      "narrative_strategy": "erode"
    },
    {
      "id": "ch1_sacrifice",
      "title": "The Burning Light",
      "description": "Mara pushes the lighthouse to maximum power. The ship is guided to safety, but the lighthouse is damaged beyond repair.",
      "background_id": "bg_lighthouse_top",
      "characters_present": ["char_mara"],
      "narrative_strategy": "accumulate"
    },
    {
      "id": "ch1_retreat",
      "title": "Into the Storm",
      "description": "Mara abandons the lighthouse to seek shelter. The ship's fate is unknown. Survival feels hollow.",
      "background_id": "bg_cliff_path",
      "characters_present": ["char_mara", "char_voice"],
      "narrative_strategy": "erode"
    }
  ],
  "characters": [
    {
      "id": "char_mara",
      "name": "Mara",
      "color": "#88ccff",
      "personality": "Stoic, duty-bound, haunted by past losses",
      "background": "A former sailor who became a lighthouse keeper after surviving a shipwreck",
      "role": "protagonist"
    },
    {
      "id": "char_voice",
      "name": "The Voice",
      "color": "#ffcc44",
      "personality": "Mysterious, could be conscience, ghost, or radio static",
      "background": "An unknown presence that speaks to Mara through the storm",
      "role": "enigma"
    }
  ]
}"""

DIRECTOR_STEP2 = """{
  "scenes": [
    {
      "id": "ch1_arrival",
      "next_scene_id": null,
      "branches": [
        {"text": "Boost the lighthouse beam", "next_scene_id": "ch1_signal"},
        {"text": "Secure the structure first", "next_scene_id": "ch1_signal"}
      ],
      "music_mood": "mysterious",
      "music_description": "low strings, distant thunder"
    },
    {
      "id": "ch1_signal",
      "next_scene_id": null,
      "branches": [
        {"text": "Risk everything — push to maximum power", "next_scene_id": "ch1_sacrifice"},
        {"text": "Save yourself — the storm is too dangerous", "next_scene_id": "ch1_retreat"}
      ],
      "music_mood": "tense",
      "music_description": "rising strings, urgent rhythm"
    },
    {
      "id": "ch1_sacrifice",
      "next_scene_id": null,
      "branches": [],
      "music_mood": "epic",
      "music_description": "swelling orchestra, bittersweet resolution"
    },
    {
      "id": "ch1_retreat",
      "next_scene_id": null,
      "branches": [],
      "music_mood": "melancholic",
      "music_description": "sparse piano, wind ambience"
    }
  ]
}"""

_WRITER_SCENE_MAP = {
    "ch1_arrival": """[
  {"character_id": null, "text": "The storm arrived before you did. Salt and lightning — the sea's old argument with the sky.", "emotion": "neutral"},
  {"character_id": "char_mara", "text": "Ten years on this post. Never seen anything like this.", "emotion": "thoughtful"},
  {"character_id": "char_voice", "text": "Mara. Can you hear me through the static?", "emotion": "surprised"},
  {"character_id": "char_mara", "text": "Who's there? The radio shouldn't even be working.", "emotion": "scared"},
  {"character_id": "char_voice", "text": "The beam. You need to decide about the beam.", "emotion": "neutral"}
]""",
    "ch1_signal": """[
  {"character_id": null, "text": "Three short pulses. One long. Someone out there is dying.", "emotion": "neutral"},
  {"character_id": "char_mara", "text": "I see it. A container ship — running dark, off course.", "emotion": "determined"},
  {"character_id": "char_voice", "text": "The grid can't handle maximum output. You know what happens if it blows.", "emotion": "thoughtful"},
  {"character_id": "char_mara", "text": "I know exactly what happens.", "emotion": "sad"},
  {"character_id": "char_voice", "text": "So do they. The people on that ship.", "emotion": "neutral"}
]""",
    "ch1_sacrifice": """[
  {"character_id": null, "text": "The light blazed white. Brighter than it had ever burned.", "emotion": "neutral"},
  {"character_id": "char_mara", "text": "Hold together — just a little longer—", "emotion": "determined"},
  {"character_id": null, "text": "Through the rain, far below, the ship turned. Slowly. Just enough.", "emotion": "neutral"},
  {"character_id": "char_mara", "text": "There. They saw it. They saw—", "emotion": "happy"},
  {"character_id": null, "text": "The generator died with a sound like a held breath finally released. But the ship was already safe.", "emotion": "neutral"}
]""",
    "ch1_retreat": """[
  {"character_id": null, "text": "Mara ran. She told herself it was the only rational choice.", "emotion": "neutral"},
  {"character_id": "char_mara", "text": "I can't save everyone. I couldn't save them before.", "emotion": "sad"},
  {"character_id": "char_voice", "text": "And yet you remember every name.", "emotion": "neutral"},
  {"character_id": "char_mara", "text": "Don't.", "emotion": "angry"},
  {"character_id": null, "text": "The storm swallowed the lighthouse light behind her. By morning, no one could say what had happened to the ship.", "emotion": "neutral"}
]""",
}

_REVIEWER_RESPONSE = "PASS"

_CHARACTER_DESIGNER_RESPONSE = """{
  "art_style": "painterly anime style, atmospheric lighting, high quality",
  "appearance": "tall, weathered face, dark circles under storm-grey eyes, salt-and-pepper hair cut short",
  "default_outfit": "heavy canvas work jacket, knit sweater, waterproof trousers"
}"""

_SCENE_ARTIST_RESPONSE = """{
  "prompt": "painterly anime background, lighthouse on rocky cliff at night, massive storm approaching, dramatic lightning, crashing waves far below, atmospheric fog, wide landscape composition"
}"""


# ── Dispatch function (shared by CLI mock mode and tests) ─────────────────────

class _MockMessage:
    def __init__(self, content: str):
        self.content = content
        self.response_metadata = {"stop_reason": "end_turn", "usage": {"input_tokens": 0, "output_tokens": 0}}


async def mock_ainvoke(
    system_prompt: str,
    user_prompt: str,
    schema=None,
    model: str | None = None,
    caller: str = "llm",
) -> _MockMessage:
    """Drop-in replacement for ainvoke_llm that returns canned responses."""
    sys_lower = system_prompt.lower()
    content = _dispatch(sys_lower, user_prompt, caller)
    logger.debug(f"[mock] caller={caller!r} → {len(content)} chars")
    return _MockMessage(content)


def _dispatch(sys_lower: str, user_prompt: str, caller: str) -> str:
    # Director step2: system mentions navigation
    if "director" in sys_lower and ("navigation" in sys_lower or "next_scene_id" in sys_lower):
        return DIRECTOR_STEP2

    # Director step1: system mentions director but not navigation
    if "director" in sys_lower:
        return DIRECTOR_STEP1

    # Reviewer
    if "reviewer" in sys_lower:
        return _REVIEWER_RESPONSE

    # Writer: try to match scene id in caller (e.g. "writer/ch1_arrival")
    if "writer" in sys_lower or "dialogue" in sys_lower:
        for scene_id, response in _WRITER_SCENE_MAP.items():
            if scene_id in caller or scene_id in user_prompt:
                return response
        # fallback: return first scene dialogue
        return next(iter(_WRITER_SCENE_MAP.values()))

    # Character designer
    if "character" in sys_lower and "designer" in sys_lower:
        return _CHARACTER_DESIGNER_RESPONSE

    # Scene artist
    if "background artist" in sys_lower or "scene_artist" in caller:
        return _SCENE_ARTIST_RESPONSE

    # Generic fallback
    return '{"result": "mock response"}'
