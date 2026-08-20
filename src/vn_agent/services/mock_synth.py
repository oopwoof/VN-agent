"""Scene-count-aware synthetic mock fixtures (50-scene dry run).

The hand-written fixtures in mock_llm.py are 4 scenes (EN) / 3 (CN) and
carry none of the long-form fields, so a mock run can never exercise
chapter rollup, thinking fanout, cross-ref sync, DAG waves, or the state
timeline — every ≥10-scene gate stays closed. This module synthesizes a
deterministic N-scene plan (and matching per-scene writer/thinking/summary
responses) so the long-form orchestration can be dry-run at zero cost.

Gate: the VN_MOCK_SYNTH env var, checked lazily per call. NOT gated on
requested scene count — the default pipeline already asks for
max_scenes=10 (above fixture size) through the real dispatch, so
count-triggered synthesis would silently rewire existing tests and demos.
Gate off ⇒ every try_* function returns None and mock_llm serves the
fixtures byte-identical.

Everything here is deterministic (no randomness, no clock): same prompt →
same output, which keeps mock runs reproducible and diffable.

The synthetic plan is engineered to pass every deterministic gate that
would otherwise burn director-redo cycles (see test_mock_synth.py):
  - director._validate_branch_structure: diamond branches (distinct
    targets, exclusive depth-3 downstream) every ~10 scenes
  - structure_reviewer._local_structural_audit: all characters used,
    ≥3 strategies ending on an ending-type, context_deps strictly
    backward with existing ids
  - reviewer._mechanical_check: speakers ⊆ cast, valid emotions, typed
    state_writes against the declared world_variables
  - writer_orchestrator.compute_waves: block-anchored deps yield
    topological waves of width 5 so parallel writing actually fans out
"""
from __future__ import annotations

import json
import os
import re

_ENV_VAR = "VN_MOCK_SYNTH"

# The EN step1 fixture has 4 scenes; a request for exactly that count keeps
# the fixture (short-circuit) so synth-on small runs stay comparable.
_FIXTURE_SCENE_COUNT = 4

# Prompt markers — mirrors of the real agent prompts. If director.py or
# writer.py rewords these lines, parsing fails and the fixture path serves
# (visible in the dry run as a 4-scene script, loudly failing its
# scene-count assertion — never a silent partial synth).
_STEP1_COUNT_RE = re.compile(r"(?:Up to|with) (\d+) scenes")
_STEP1_CHARS_RE = re.compile(r"(\d+) characters")
_STEP2_IDS_RE = re.compile(r"All valid scene IDs: (\[[^\]]*\])")
_WRITER_CAST_RE = re.compile(r"^Characters present: (.*)$", re.MULTILINE)
_DEP_SCENE_RE = re.compile(r"→ scene:(\S+)")
_SYNTH_SCENE_ID_RE = re.compile(r"^s\d{2,}$")

_STRATEGY_CYCLE = ("accumulate", "erode", "contest", "escalate", "uncover", "drift")
_EMOTION_CYCLE = (
    "neutral", "thoughtful", "surprised", "determined",
    "sad", "happy", "scared", "loving", "angry",
)
_BACKGROUND_CYCLE = ("bg_shoreline", "bg_signal_tower", "bg_archive_room", "bg_cliff_walk")
_MOOD_CYCLE = ("peaceful", "mysterious", "tense", "melancholic", "joyful", "epic")
_TENSION_CYCLE = ("low", "medium", "high")

_CHARACTER_POOL = (
    ("char_asha", "Asha", "#88ccff", "Steady, methodical, keeps lists", "Signal keeper on her last posted winter"),
    ("char_bren", "Bren", "#ffcc44", "Restless, jokes to deflect", "Supply runner who stayed past the season"),
    ("char_corin", "Corin", "#99dd88", "Precise, archival, quietly loyal", "Keeper of the station logbooks"),
    ("char_dessa", "Dessa", "#dd88aa", "Blunt, weather-worn, protective", "Retired pilot who never left the coast"),
    ("char_eli", "Eli", "#ccaaff", "Curious, too young for the post", "Apprentice sent up from the mainland"),
    ("char_fen", "Fen", "#ffaa88", "Guarded, speaks in half-answers", "Stranger the tide brought in"),
)

_WORLD_VARIABLES = [
    {
        "name": "trust_level", "type": "int", "initial_value": 0,
        "description": "How far the cast trusts the protagonist's judgment (0-10).",
    },
    {
        "name": "beacon_lit", "type": "bool", "initial_value": False,
        "description": "Whether the station beacon has been relit this winter.",
    },
    {
        "name": "route_stage", "type": "enum", "initial_value": "intro",
        "enum_values": ["intro", "midgame", "finale"],
        "description": "Coarse story stage used to gate late-route branches.",
    },
]


def enabled() -> bool:
    return os.environ.get(_ENV_VAR, "").strip().lower() in {"1", "true", "yes"}


def _scene_ids(n: int) -> list[str]:
    return [f"s{i + 1:02d}" for i in range(n)]


def _diamond_indices(n: int) -> set[int]:
    """Branch-scene indices (0-based): one diamond per ~10 scenes.

    Scene d branches to d+1 / d+2 (the arms), both arms converge on d+3.
    Placed at i % 10 == 4 so a 10-scene run still gets one diamond, and
    kept ≥3 from the end so the converge target exists.
    """
    return {i for i in range(n) if i % 10 == 4 and i + 3 <= n - 1}


def _cast(n_chars: int) -> list[tuple[str, str, str, str, str]]:
    k = max(2, min(n_chars, len(_CHARACTER_POOL)))
    return list(_CHARACTER_POOL[:k])


# ── Director step1 ────────────────────────────────────────────────────────────

def try_step1(user_prompt: str) -> str | None:
    """Synthesize an N-scene step1 outline, or None to serve the fixture."""
    if not enabled():
        return None
    count_m = _STEP1_COUNT_RE.search(user_prompt)
    if not count_m:
        return None
    n = int(count_m.group(1))
    if n == _FIXTURE_SCENE_COUNT or n < 2:
        return None
    chars_m = _STEP1_CHARS_RE.search(user_prompt)
    cast = _cast(int(chars_m.group(1)) if chars_m else 3)
    ids = _scene_ids(n)
    diamonds = _diamond_indices(n)

    scenes = []
    for i, sid in enumerate(ids):
        if i == n - 1:
            strategy = "resolve"          # ending-type, last (audit 2c)
        elif i == n - 2 and n >= 6:
            strategy = "rupture"          # pre-finale spike
        else:
            strategy = _STRATEGY_CYCLE[i % len(_STRATEGY_CYCLE)]
        # rotate a 2-person spotlight so every declared character is used
        present = sorted({cast[i % len(cast)][0], cast[(i + 1) % len(cast)][0]})
        kind = "turning point" if i in diamonds else "waypoint"
        scenes.append({
            "id": sid,
            "title": f"Waypoint {i + 1:02d}",
            "description": (
                f"Beat {i + 1} of {n} ({kind}): the station's winter question "
                f"tightens around {present[0]} while the coast keeps its own count."
            ),
            "background_id": _BACKGROUND_CYCLE[i % len(_BACKGROUND_CYCLE)],
            "characters_present": present,
            "narrative_strategy": strategy,
        })

    macro: dict = {
        "theme_thesis": f"Duty against a failing coast, measured across {n} scenes of one winter.",
        "pacing_arc": (
            f"accumulate s01-s{max(n // 3, 1):02d} → contest/escalate through "
            f"s{max(2 * n // 3, 2):02d} → rupture s{n - 1:02d} → resolve s{n:02d}"
        ),
        "foreshadow_plan": [],
        "character_voice_charter": {
            cid: f"{name}: {personality.lower()}"
            for cid, name, _, personality, _ in cast
        },
        "tone_register": "literary, close third person, low simmer with late spikes",
    }
    if n >= 6:
        macro["foreshadow_plan"] = [
            {"planted_in": ids[1], "payoff_in": ids[-2], "element": "the unanswered radio question"},
            {"planted_in": ids[2], "payoff_in": ids[-1], "element": "the logbook's missing winter"},
        ]

    plan = {
        "title": "The Long Signal",
        "description": (
            f"A {n}-scene winter at a coastal signal station: keeping the "
            "light means deciding, scene by scene, who it burns for."
        ),
        "start_scene_id": ids[0],
        "scenes": scenes,
        "characters": [
            {
                "id": cid, "name": name, "color": color,
                "personality": personality, "background": background,
                "role": "protagonist" if idx == 0 else "supporting",
            }
            for idx, (cid, name, color, personality, background) in enumerate(cast)
        ],
        "world_variables": _WORLD_VARIABLES,
        "macro_reference": macro,
    }
    return json.dumps(plan, ensure_ascii=False, indent=2)


# ── Director step2 ────────────────────────────────────────────────────────────

def try_step2(user_prompt: str) -> str | None:
    """Synthesize step2 details for a synthetic id list, or None."""
    if not enabled():
        return None
    ids_m = _STEP2_IDS_RE.search(user_prompt)
    if not ids_m:
        return None
    try:
        ids = json.loads(ids_m.group(1))
    except json.JSONDecodeError:
        return None
    if not ids or not all(
        isinstance(s, str) and _SYNTH_SCENE_ID_RE.match(s) for s in ids
    ):
        return None  # fixture ids (ch1_*) or garbage → fixture path

    n = len(ids)
    diamonds = _diamond_indices(n)
    arm_of = {d + 1: d for d in diamonds} | {d + 2: d for d in diamonds}

    scenes = []
    for i, sid in enumerate(ids):
        # ── navigation: linear chain, except diamonds (d → arms → d+3) ──
        branches: list[dict] = []
        if i in diamonds:
            next_id = None
            branches = [
                {"text": f"Hold the line through {ids[i + 1]}", "next_scene_id": ids[i + 1], "requires": {}},
                {"text": f"Cut away toward {ids[i + 2]}", "next_scene_id": ids[i + 2], "requires": {}},
            ]
        elif i in arm_of:
            next_id = ids[arm_of[i] + 3]
        elif i == n - 1:
            next_id = None
        else:
            next_id = ids[i + 1]

        # ── typed state I/O against _WORLD_VARIABLES ──
        state_writes: dict = {}
        state_reads: list[str] = []
        if i % 3 == 1:
            state_writes["trust_level"] = min(i // 3 + 1, 10)
        if i == n // 2:
            state_writes["beacon_lit"] = True
        if n >= 6 and i == n // 3:
            state_writes["route_stage"] = "midgame"
        if n >= 6 and i == (2 * n) // 3:
            state_writes["route_stage"] = "finale"
        if i % 3 == 2:
            state_reads.append("trust_level")
        if i > n // 2:
            state_reads.append("beacon_lit")

        # ── backward-only deps: block anchor (waves of 5) + shared callback ──
        deps: list[dict] = []
        block_anchor = (i // 5) * 5 - 1
        if block_anchor >= 0:
            deps.append({
                "ref_type": "scene", "ref_id": ids[block_anchor],
                "link_type": "arc_beat",
                "reason": f"Continues the thread {ids[block_anchor]} closed its block on.",
                "inject_as": "summary",
            })
        if i >= 5 and i % 5 == 0:
            # many scenes share ref s01 → genuine callback collisions for
            # cross_ref_sync's Tier-1 resolver to arbitrate
            deps.append({
                "ref_type": "scene", "ref_id": ids[0],
                "link_type": "callback",
                "reason": "Echoes the opening image of the unlit beacon.",
                "inject_as": "summary",
            })
        if i == n - 2 and n >= 6:
            deps.append({
                "ref_type": "scene", "ref_id": ids[1],
                "link_type": "foreshadow_payoff",
                "reason": "Pays off the radio question planted early.",
                "inject_as": "summary",
            })

        scenes.append({
            "id": sid,
            "next_scene_id": next_id,
            "branches": branches,
            "music_mood": _MOOD_CYCLE[i % len(_MOOD_CYCLE)],
            "music_description": f"scene {i + 1} underscore, {_MOOD_CYCLE[i % len(_MOOD_CYCLE)]} register",
            "emotional_arc": "steady → strained" if i % 2 == 0 else "guarded → opening",
            "entry_context": None if i == 0 else f"Carries the exit weight of {ids[i - 1]}.",
            "exit_hook": None if next_id is None and not branches else "Hands the tension forward unresolved.",
            "state_reads": state_reads,
            "state_writes": state_writes,
            "context_deps": deps[:5],
            "scene_brief": {
                "beats": [
                    f"{sid}: open at the declared location, mid-task",
                    f"{sid}: press the block's open question",
                    f"{sid}: exit on the forward hook",
                ],
                "character_blocking": {},
                "emotional_curve": ["calm", "strain"],
                "tension_target": "climax" if i in diamonds else _TENSION_CYCLE[i % len(_TENSION_CYCLE)],
                "subtext_notes": "What stays unsaid: who the light is actually kept for.",
            },
        })

    out = {
        "reasoning": (
            "mock synth: linear spine with one diamond per ten scenes, "
            "block-anchored deps for width-5 waves, typed state I/O."
        ),
        "scenes": scenes,
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


# ── Writer ────────────────────────────────────────────────────────────────────

def try_writer(user_prompt: str, caller: str) -> str | None:
    """Synthesize distinct per-scene dialogue for synthetic scene ids."""
    if not enabled():
        return None
    sid = caller.removeprefix("writer/").removesuffix("/continuation")
    if not _SYNTH_SCENE_ID_RE.match(sid):
        return None  # fixture scene ids keep their hand-written dialogue

    cast_m = _WRITER_CAST_RE.search(user_prompt)
    cast = [c.strip() for c in cast_m.group(1).split(",") if c.strip()] if cast_m else []
    idx = int(re.sub(r"\D", "", sid) or 0)
    n_lines = 7 + (idx % 3)  # 7-9: clears min_dialogue_lines=5 with margin

    lines = []
    for k in range(n_lines):
        speaker = None if k % 3 == 0 or not cast else cast[k % len(cast)]
        emotion = _EMOTION_CYCLE[(idx + k) % len(_EMOTION_CYCLE)]
        if speaker is None:
            text = (
                f"[{sid}] The coast keeps its own count; beat {k + 1} of this "
                f"scene passes through the station like weather."
            )
        else:
            text = (
                f"({sid}:{k + 1}) We hold this line because someone has to "
                f"answer the water — that's the whole argument, isn't it?"
            )
        lines.append({"character_id": speaker, "text": text, "emotion": emotion})
    return json.dumps(lines, ensure_ascii=False, indent=2)


# ── Thinking / resync ─────────────────────────────────────────────────────────

def try_thinking(user_prompt: str, caller: str) -> str | None:
    """Synthesize a per-scene SceneThinking whose callback_plan mirrors the
    scene's declared context_deps — shared deps then produce genuine
    collisions for cross_ref_sync's deterministic resolver."""
    if not enabled():
        return None
    sid = caller.split("/", 1)[1] if "/" in caller else caller
    dep_ids = list(dict.fromkeys(_DEP_SCENE_RE.findall(user_prompt)))  # ordered dedup
    thinking = {
        "writing_intent": f"mock({sid}): land this scene's pivot and pay its declared callbacks",
        "key_beats_expanded": [
            f"{sid} beat 1 — re-anchor place and cast without restating",
            f"{sid} beat 2 — press the open question one turn tighter",
            f"{sid} beat 3 — exit on the declared hook, unresolved",
        ],
        "callback_plan": [
            {"ref_scene_id": d, "what_lands": f"callback to {d} lands as a spoken echo"}
            for d in dep_ids[:4]
        ],
        "opening_hook": f"{sid}: open mid-motion at the declared location",
        "closing_beat": f"{sid}: close on the forward hook",
        "voice_notes": {},
        "risks": ["do not over-explain — subtext only"],
    }
    return json.dumps(thinking, ensure_ascii=False, indent=2)


# ── Scene summaries ───────────────────────────────────────────────────────────

def try_summary(caller: str) -> str | None:
    """Distinct per-scene summary so prior-scene context blocks differ."""
    if not enabled():
        return None
    sid = caller.split("/", 1)[1] if "/" in caller else caller
    return (
        f"Scene {sid}: the spotlight pair advances the block's open question "
        f"one turn; declared state changes from {sid} are canon going forward."
    )
