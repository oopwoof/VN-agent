"""Sprint 8-3 baseline runners — single-shot and self-refine.

These are intentionally dumb. They bypass the Director → StructureReviewer
→ StateOrchestrator → Writer → DialogueReviewer graph entirely and make
raw Sonnet calls to produce a VNScript directly. Their purpose is to
make the full pipeline's value falsifiable: if literary/action mode
doesn't statistically beat these, the multi-agent complexity is
unjustified.

Both return a `VNScript` (plus light metadata) parseable by the same
eval pipeline that scores the full-graph runs.

**baseline_single**: one Sonnet call, strict JSON schema in the prompt,
output parsed into VNScript. ~$0.05/call.

**baseline_self_refine**: first Sonnet call produces the draft;
second Sonnet call asked to critique its own draft against the physics
rubric and produce a single revision. ~$0.15/call.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from vn_agent.config import get_settings
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import (
    BranchOption,
    DialogueLine,
    Scene,
    VNScript,
)
from vn_agent.services.llm import ainvoke_llm
from vn_agent.strategies.narrative import DATASET_ALIGNED

logger = logging.getLogger(__name__)


@dataclass
class BaselineResult:
    script: VNScript
    characters: dict[str, CharacterProfile]
    errors: list[str]


_BASELINE_SINGLE_SYSTEM = """You are a visual-novel author. Given a theme, \
produce a complete VN script with characters, scenes, and dialogue in a \
single response. Return ONLY the JSON object in the schema below.

## Strategy taxonomy (required field for each scene)

- accumulate: same-direction buildup crossing a threshold
- erode: slow wearing-down of support, facade, or composure
- rupture: step function, discontinuous jump
- uncover: disclosure that invalidates prior understanding
- contest: opposing vectors between characters
- drift: low-stakes atmospheric meandering
- escalate: continuously raise stakes
- resolve: closure on accumulated tension

## Output schema

{{
  "title": "...",
  "description": "one-sentence story",
  "theme": "<echo back the theme>",
  "start_scene_id": "ch1_...",
  "characters": [
    {{"id": "...", "name": "...", "color": "#rrggbb",
      "personality": "...", "background": "...", "role": "..."}}
  ],
  "scenes": [
    {{"id": "ch1_...", "title": "...", "description": "1-2 sentences",
      "background_id": "bg_...", "characters_present": ["id1", "id2"],
      "narrative_strategy": "accumulate|...",
      "next_scene_id": "ch1_next" or null,
      "branches": [],
      "dialogue": [
        {{"character_id": "id1" or null,
          "text": "...",
          "emotion": "neutral|happy|sad|angry|surprised|scared|thoughtful|loving|determined"}}
      ]
    }}
  ]
}}

Target: {max_scenes} scenes, {num_characters} characters, 12-20 dialogue \
lines per scene. No <thinking> tags. Return ONLY JSON."""


_SELF_REFINE_CRITIQUE_SYSTEM = """You just wrote a visual novel script. Now \
critique YOUR OWN draft using the physics rubric:

- Is each scene's narrative_strategy actually EXECUTED in the dialogue \
(not just stated by label)? rupture should contain a real step function, \
erode real entropy, contest real opposing vectors.
- Do characters have distinct voice?
- Does each scene end on a hook, not a summary?

Write a short critique (~150 words) identifying the 2-3 weakest scenes \
and the specific craft-level fix for each. Then produce the COMPLETE \
revised JSON (same schema as before). Return ONLY JSON after a one-line \
"Critique:" header summary."""


async def run_baseline_single(
    theme: str,
    max_scenes: int = 6,
    num_characters: int = 3,
) -> BaselineResult:
    """One-shot Sonnet baseline. No agent choreography, no revision loop."""
    settings = get_settings()

    system = _BASELINE_SINGLE_SYSTEM.format(
        max_scenes=max_scenes, num_characters=num_characters,
    )
    user = f"Theme: {theme}"

    logger.info(f"baseline_single: one Sonnet call for theme={theme!r}")
    response = await ainvoke_llm(
        system, user,
        model=settings.llm_writer_model,
        caller="baseline_single",
    )
    content = response.content if hasattr(response, "content") else str(response)
    script, characters, errors = _parse_baseline_json(content, theme)

    return BaselineResult(script=script, characters=characters, errors=errors)


async def run_baseline_self_refine(
    theme: str,
    max_scenes: int = 6,
    num_characters: int = 3,
) -> BaselineResult:
    """Draft → self-critique → revise. Two Sonnet calls, one revision."""
    settings = get_settings()

    # Phase 1: draft (same as baseline_single)
    system1 = _BASELINE_SINGLE_SYSTEM.format(
        max_scenes=max_scenes, num_characters=num_characters,
    )
    user1 = f"Theme: {theme}"
    logger.info(f"baseline_self_refine: draft call for theme={theme!r}")
    draft_response = await ainvoke_llm(
        system1, user1,
        model=settings.llm_writer_model,
        caller="baseline_self_refine/draft",
    )
    draft_content = (
        draft_response.content if hasattr(draft_response, "content")
        else str(draft_response)
    )

    # Phase 2: self-critique + revise
    logger.info("baseline_self_refine: self-critique + revise")
    refine_user = (
        f"Your original draft:\n```json\n{draft_content[:12000]}\n```\n\n"
        f"Critique it and produce a revised JSON that fixes the weakest scenes. "
        f"Return the complete revised JSON."
    )
    refine_response = await ainvoke_llm(
        _SELF_REFINE_CRITIQUE_SYSTEM, refine_user,
        model=settings.llm_writer_model,
        caller="baseline_self_refine/revise",
    )
    refine_content = (
        refine_response.content if hasattr(refine_response, "content")
        else str(refine_response)
    )
    script, characters, errors = _parse_baseline_json(refine_content, theme)

    return BaselineResult(script=script, characters=characters, errors=errors)


def _parse_baseline_json(
    content: str, theme: str,
) -> tuple[VNScript, dict[str, CharacterProfile], list[str]]:
    """Parse single-shot JSON into VNScript + characters. Tolerant of prelude."""
    errors: list[str] = []
    # Strip common wrappers (markdown code fence, preamble like "Critique: ...")
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1)
    else:
        start = content.find("{")
        if start == -1:
            raise ValueError("No JSON object found in baseline output")
        try:
            obj, _ = json.JSONDecoder().raw_decode(content, start)
            raw = json.dumps(obj)
        except json.JSONDecodeError as e:
            raise ValueError(f"Baseline JSON parse failed: {e}") from e

    data = json.loads(raw)

    # Characters
    characters: dict[str, CharacterProfile] = {}
    for c in data.get("characters") or []:
        try:
            cp = CharacterProfile(
                id=c["id"], name=c["name"],
                color=c.get("color") or "#ffffff",
                personality=c.get("personality") or "",
                background=c.get("background") or "",
                role=c.get("role") or "supporting",
            )
            characters[cp.id] = cp
        except Exception as e:  # noqa: BLE001
            errors.append(f"baseline: skipped character {c.get('id', '?')}: {e}")

    # Scenes
    scenes: list[Scene] = []
    scene_ids_seen: set[str] = set()
    for s in data.get("scenes") or []:
        try:
            strat = s.get("narrative_strategy", "drift")
            if strat and strat not in DATASET_ALIGNED and strat not in {
                "escalate", "resolve",
            }:
                errors.append(
                    f"baseline: scene {s.get('id', '?')} has non-canonical "
                    f"strategy '{strat}' — coerced to 'drift'"
                )
                strat = "drift"

            dialogue = []
            for d in s.get("dialogue") or []:
                dialogue.append(DialogueLine(
                    character_id=d.get("character_id") or None,
                    text=d.get("text", ""),
                    emotion=d.get("emotion") or "neutral",
                ))

            branches = []
            for b in s.get("branches") or []:
                branches.append(BranchOption(
                    text=b.get("text", ""),
                    next_scene_id=b.get("next_scene_id") or "",
                ))

            scene = Scene(
                id=s["id"],
                title=s.get("title", s["id"]),
                description=s.get("description", ""),
                background_id=s.get("background_id", "bg_default"),
                characters_present=s.get("characters_present") or [],
                dialogue=dialogue,
                narrative_strategy=strat,
                next_scene_id=s.get("next_scene_id") or None,
                branches=branches,
            )
            scenes.append(scene)
            scene_ids_seen.add(scene.id)
        except Exception as e:  # noqa: BLE001
            errors.append(f"baseline: skipped scene {s.get('id', '?')}: {e}")

    start_id = data.get("start_scene_id") or (scenes[0].id if scenes else "")
    script = VNScript(
        title=data.get("title", "Untitled"),
        description=data.get("description", ""),
        theme=data.get("theme") or theme,
        start_scene_id=start_id,
        scenes=scenes,
        characters=list(characters.keys()),
    )
    return script, characters, errors
