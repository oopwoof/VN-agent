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
      "music_description": "low strings, distant thunder",
      "emotional_arc": "duty -> foreboding",
      "entry_context": "",
      "exit_hook": "A mysterious voice on the radio warns about the beam."
    },
    {
      "id": "ch1_signal",
      "next_scene_id": null,
      "branches": [
        {"text": "Risk everything — push to maximum power", "next_scene_id": "ch1_sacrifice"},
        {"text": "Save yourself — the storm is too dangerous", "next_scene_id": "ch1_retreat"}
      ],
      "music_mood": "tense",
      "music_description": "rising strings, urgent rhythm",
      "emotional_arc": "foreboding -> dread",
      "entry_context": "The voice has primed the keeper; the storm is intensifying.",
      "exit_hook": "A distress signal forces a life-or-death choice."
    },
    {
      "id": "ch1_sacrifice",
      "next_scene_id": null,
      "branches": [],
      "music_mood": "epic",
      "music_description": "swelling orchestra, bittersweet resolution",
      "emotional_arc": "resolve -> bittersweet triumph",
      "entry_context": "The keeper chose to risk everything for the ship.",
      "exit_hook": ""
    },
    {
      "id": "ch1_retreat",
      "next_scene_id": null,
      "branches": [],
      "music_mood": "melancholic",
      "music_description": "sparse piano, wind ambience",
      "emotional_arc": "guilt -> hollow survival",
      "entry_context": "The keeper abandoned the post to save themselves.",
      "exit_hook": ""
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

_STRUCTURE_REVIEWER_RESPONSE = """{
  "verdict": "PASS",
  "branch_alignment_score": 1.0,
  "aligned_branches": [],
  "narrative_issues": [],
  "summary": "mock: outline passes structure audit"
}"""

_STATE_ORCHESTRATOR_RESPONSE = """Scene ch1:
  - Characters begin on first-name terms (affinity 3/10)
  - Nothing disclosed yet — all world flags default"""

_SUMMARIZER_RESPONSE = (
    "The scene opens with the characters present, follows the assigned "
    "narrative strategy, and ends with an emotional pivot. No new named "
    "entities are introduced; state remains as declared."
)

_CHARACTER_DESIGNER_RESPONSE = """{
  "art_style": "painterly anime style, atmospheric lighting, high quality",
  "appearance": "tall, weathered face, dark circles under storm-grey eyes, salt-and-pepper hair cut short",
  "default_outfit": "heavy canvas work jacket, knit sweater, waterproof trousers"
}"""

_SCENE_ARTIST_RESPONSE = """{
  "prompt": "painterly anime background, lighthouse on rocky cliff at night, massive storm approaching, dramatic lightning, crashing waves far below, atmospheric fog, wide landscape composition"
}"""

# ── Chinese fixtures ─────────────────────────────────────────────────────────

DIRECTOR_STEP1_CN = """{
  "title": "樱花树下的约定",
  "description": "一段关于青春与承诺的校园恋爱故事",
  "start_scene_id": "ch1_meeting",
  "scenes": [
    {
      "id": "ch1_meeting",
      "title": "初次相遇",
      "description": "主角在樱花树下遇见了转学生小雪",
      "background_id": "bg_school_yard",
      "characters_present": ["char_yuki", "char_hero"],
      "narrative_strategy": "accumulate"
    },
    {
      "id": "ch1_talk",
      "title": "午后对话",
      "description": "两人在教室里聊起了各自的梦想",
      "background_id": "bg_classroom",
      "characters_present": ["char_yuki", "char_hero"],
      "narrative_strategy": "accumulate"
    },
    {
      "id": "ch1_promise",
      "title": "樱花下的约定",
      "description": "放学后两人在樱花树下许下了约定",
      "background_id": "bg_school_yard",
      "characters_present": ["char_yuki", "char_hero"],
      "narrative_strategy": "resolve"
    }
  ],
  "characters": [
    {
      "id": "char_yuki",
      "name": "小雪",
      "color": "#ffaacc",
      "personality": "温柔害羞，喜欢画画",
      "background": "从外地转来的转学生",
      "role": "love interest"
    },
    {
      "id": "char_hero",
      "name": "小明",
      "color": "#6699ff",
      "personality": "开朗热心，班长",
      "background": "普通高中生，从小在这所学校读书",
      "role": "protagonist"
    }
  ]
}"""

DIRECTOR_STEP2_CN = """{
  "scenes": [
    {
      "id": "ch1_meeting",
      "next_scene_id": null,
      "branches": [
        {"text": "主动搭话", "next_scene_id": "ch1_talk"},
        {"text": "默默离开", "next_scene_id": "ch1_promise"}
      ],
      "music_mood": "peaceful",
      "music_description": "轻柔的钢琴曲",
      "emotional_arc": "好奇 -> 心动",
      "entry_context": "",
      "exit_hook": "在樱花树下初次相遇，是否开口决定接下来的故事。"
    },
    {
      "id": "ch1_talk",
      "next_scene_id": "ch1_promise",
      "branches": [],
      "music_mood": "joyful",
      "music_description": "明快的弦乐",
      "emotional_arc": "陌生 -> 亲近",
      "entry_context": "主角选择了主动搭话，两人开始交谈。",
      "exit_hook": "对话为放学后的约定埋下伏笔。"
    },
    {
      "id": "ch1_promise",
      "next_scene_id": null,
      "branches": [],
      "music_mood": "romantic",
      "music_description": "温暖的吉他旋律",
      "emotional_arc": "期待 -> 承诺",
      "entry_context": "两人走到樱花树下，一天即将结束。",
      "exit_hook": ""
    }
  ]
}"""

_WRITER_SCENE_MAP_CN = {
    "ch1_meeting": """[
  {"character_id": null, "text": "春天的校园里，樱花正在盛开。", "emotion": "neutral"},
  {"character_id": "char_hero", "text": "今天的樱花开得真美啊。", "emotion": "happy"},
  {"character_id": "char_yuki", "text": "你好……请问图书馆怎么走？", "emotion": "neutral"},
  {"character_id": "char_hero", "text": "你是新来的转学生吧？我带你去！", "emotion": "happy"},
  {"character_id": "char_yuki", "text": "谢谢你……我叫小雪。", "emotion": "happy"}
]""",
    "ch1_talk": """[
  {"character_id": null, "text": "午后的阳光洒进教室。", "emotion": "neutral"},
  {"character_id": "char_yuki", "text": "小明同学，你的梦想是什么？", "emotion": "thoughtful"},
  {"character_id": "char_hero", "text": "我想成为一名老师，像我们班主任那样。", "emotion": "determined"},
  {"character_id": "char_yuki", "text": "真好呢……我想成为一名画家。", "emotion": "happy"},
  {"character_id": "char_hero", "text": "那你一定要给我画一幅画！", "emotion": "happy"}
]""",
    "ch1_promise": """[
  {"character_id": null, "text": "放学后，两人又来到了那棵樱花树下。", "emotion": "neutral"},
  {"character_id": "char_yuki", "text": "小明同学……谢谢你今天的帮助。", "emotion": "happy"},
  {"character_id": "char_hero", "text": "别客气，以后我们就是朋友了！", "emotion": "happy"},
  {"character_id": "char_yuki", "text": "那……我们约定，毕业那天在这里再见。", "emotion": "loving"},
  {"character_id": "char_hero", "text": "一言为定！", "emotion": "determined"}
]""",
}


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
    **kwargs,  # absorb Phase 13-1 kwargs (cache_ttl, force_cache) without caring
):
    """Drop-in replacement for ainvoke_llm.

    Two return contracts, matching real ainvoke_llm's `T | str` signature:
      - schema=None    → _MockMessage with `.content` (raw text path)
      - schema=T       → T instance parsed from the canned JSON (Phase 13-2
                         Step 4f tool-use / structured-output path). Callers
                         that pass a Pydantic schema expect a validated
                         instance, NOT a _MockMessage. Before this fix the
                         mock always returned _MockMessage → director step2
                         (Sonnet-class tool-use path) crashed with
                         "'_MockMessage' object has no attribute 'scenes'".
    """
    import json
    from pydantic import BaseModel

    sys_lower = system_prompt.lower()
    content = _dispatch(sys_lower, user_prompt, caller)
    logger.debug(f"[mock] caller={caller!r} → {len(content)} chars")

    if schema is not None and isinstance(schema, type) and issubclass(schema, BaseModel):
        try:
            data = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError as e:
            raise ValueError(
                f"[mock] caller={caller!r} schema={schema.__name__} but canned "
                f"content is not JSON: {e}. First 200 chars: {content[:200]!r}"
            ) from e
        return schema.model_validate(data)

    return _MockMessage(content)


def _has_cjk(text: str) -> bool:
    """Check if text contains CJK characters."""
    import re
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def _mock_intent_classification(user_prompt: str) -> str:
    """Keyword-sniff the raw chat message (embedded in intent_router's user
    prompt as `Creator message: '...'`) to pick which of the 4 dispatchable
    intents to fake \u2014 makes mock mode a real interactive demo of Chat Ops
    instead of a single frozen classification regardless of what's typed.

    `classify_intent()`'s hallucination guard drops any scene/character id
    that isn't actually in the project, so we scrape the first real scene id
    out of the "Scenes:" context block this mock is given rather than
    inventing one \u2014 otherwise local_regen would always get demoted to
    "unknown" in mock mode.
    """
    import json
    import re

    msg_match = re.search(r"Creator message: ['\"](.+?)['\"]\s*$", user_prompt, re.DOTALL)
    message = (msg_match.group(1) if msg_match else user_prompt).lower()

    scene_match = re.search(r"- (\S+?): ", user_prompt)
    scene_id = scene_match.group(1) if scene_match else None

    explain_kw = ("why", "explain", "who is", "\u4e3a\u4ec0\u4e48", "\u89e3\u91ca", "\u662f\u8c01", "\u600e\u4e48\u56de\u4e8b")
    add_char_kw = ("add a character", "new character", "add character", "\u65b0\u89d2\u8272", "\u52a0\u4e2a\u89d2\u8272", "\u589e\u52a0\u89d2\u8272")
    regen_kw = ("rewrite", "regenerate", "redo", "change the dialogue", "\u91cd\u5199", "\u6539\u5199", "\u91cd\u65b0\u751f\u6210")
    asset_kw = ("swap", "change the background", "change the music", "\u6362\u4e2a\u80cc\u666f", "\u6362\u5f20\u56fe", "\u6362\u97f3\u4e50")

    if any(k in message for k in explain_kw):
        payload = {
            "intent": "explain", "confidence": 0.9,
            "instruction": message.strip() or "explain the story", "reasoning": "mock: explain keyword matched",
        }
    elif any(k in message for k in add_char_kw):
        payload = {
            "intent": "add_character", "confidence": 0.85,
            "instruction": message.strip(), "reasoning": "mock: add-character keyword matched",
        }
    elif any(k in message for k in asset_kw):
        payload = {
            "intent": "edit_asset", "confidence": 0.8, "target_scene_id": scene_id,
            "instruction": message.strip(), "reasoning": "mock: asset-edit keyword matched",
        }
    elif any(k in message for k in regen_kw) or scene_id:
        payload = {
            "intent": "local_regen", "confidence": 0.85, "target_scene_id": scene_id,
            "instruction": message.strip() or "revise this scene", "reasoning": "mock: regen keyword / scene reference matched",
        }
    else:
        payload = {
            "intent": "unknown", "confidence": 0.3,
            "reasoning": "mock: no keyword matched any of the 4 intents",
        }

    return json.dumps(payload, ensure_ascii=False)


def _dispatch(sys_lower: str, user_prompt: str, caller: str) -> str:
    is_chinese = _has_cjk(user_prompt)

    # v4 P3: Chat Ops intent classifier. Checked before other caller-tag
    # matches — "chat_ops/" is a distinctive prefix that can't collide with
    # director/writer/reviewer keyword checks below. Keyword-sniffs the raw
    # message so mock mode can demo all 4 dispatchable intents interactively
    # instead of always returning the same canned classification.
    if caller.startswith("chat_ops/intent_router"):
        return _mock_intent_classification(user_prompt)
    if caller.startswith("chat_ops/explain"):
        return (
            "（模拟回答）根据现有设定，这个问题的答案取决于具体场景细节——真实生成时会引用实际剧本内容作答。"
            if is_chinese else
            "(mock answer) Based on the current setting, the answer depends on the specific scene "
            "details — a real run would cite the actual script content here."
        )

    # Director step2: detected by caller tag or system prompt content
    if "director" in sys_lower and (
        "step2" in caller or "details" in caller
        or ("navigation" in sys_lower and "plan the overall" not in sys_lower)
    ):
        return DIRECTOR_STEP2_CN if is_chinese else DIRECTOR_STEP2

    # Director step1
    if "director" in sys_lower:
        return DIRECTOR_STEP1_CN if is_chinese else DIRECTOR_STEP1

    # Summarizer (per-scene ≤100 words). Check before other reviewer
    # matches since the system prompt says "summarizer" and "concise".
    if "summarizer" in caller or "scene summarizer" in sys_lower:
        return _SUMMARIZER_RESPONSE

    # State orchestrator (check before other "reviewer" / "director" matches
    # because the system prompt mentions "compile" / "state" keywords)
    if "state_orchestrator" in caller or "compile symbolic world state" in sys_lower:
        return _STATE_ORCHESTRATOR_RESPONSE

    # Structure reviewer (check caller first since sys_lower also contains
    # "architect" / narrative keywords that might confuse later matchers)
    if "structure_reviewer" in caller or "narrative architect" in sys_lower:
        return _STRUCTURE_REVIEWER_RESPONSE

    # Reviewer
    if "reviewer" in sys_lower:
        return _REVIEWER_RESPONSE

    # Writer: try to match scene id in caller (e.g. "writer/ch1_arrival")
    if "writer" in sys_lower or "dialogue" in sys_lower:
        scene_map = _WRITER_SCENE_MAP_CN if is_chinese else _WRITER_SCENE_MAP
        for scene_id, response in scene_map.items():
            if scene_id in caller or scene_id in user_prompt:
                return response
        # fallback: return first scene dialogue
        return next(iter(scene_map.values()))

    # Character designer
    if "character" in sys_lower and "designer" in sys_lower:
        return _CHARACTER_DESIGNER_RESPONSE

    # Scene artist
    if "background artist" in sys_lower or "scene_artist" in caller:
        return _SCENE_ARTIST_RESPONSE

    # Generic fallback
    return '{"result": "mock response"}'
