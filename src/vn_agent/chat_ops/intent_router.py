"""v4 P3-1: classify a free-form chat message into a dispatchable intent.

Haiku, not Sonnet — classification-flavored, matches `feedback_model_selection`
(same call already made in `feedback/reflection.py` and
`assets/web_search_agent.py::plan_queries`; this module mirrors that pattern:
testable `llm=None` injection point, `get_settings().llm_haiku_model` with a
hardcoded fallback, structured Pydantic output via `ainvoke_llm(schema=...)`).

Four dispatchable intents (M0 scope — see `orchestrator.py` for which ones
have a live handler vs a "not wired up yet" stub):
  - local_regen   — rewrite one existing scene's dialogue
  - add_character — introduce a new character (M0: classified, not executed)
  - edit_asset    — swap/regenerate a background/sprite/bgm (M0: classified,
                    not executed)
  - explain       — answer a question about the story/setting, no mutation
  - unknown       — message doesn't map to any of the above; caller should
                    surface it as "I'm not sure what you're asking" rather
                    than guessing
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

Intent = Literal["local_regen", "add_character", "edit_asset", "explain", "unknown"]


class IntentClassification(BaseModel):
    """Structured output of the classifier — also the "intent preview" the
    frontend renders for L1 confirm-before-execute (see `orchestrator.py`)."""

    intent: Intent = Field(description="Which of the 5 dispatchable buckets this message falls into")
    target_scene_id: str | None = Field(
        default=None, description="Scene id this message refers to, if any (must be one of the ids given in context)"
    )
    target_character_id: str | None = Field(
        default=None, description="Character id this message refers to, if any"
    )
    instruction: str = Field(
        default="", description="The specific ask, rewritten as a concise directive a Writer/handler can act on"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="0-1 confidence in this classification")
    reasoning: str = Field(default="", description="One sentence on why this intent was chosen")


_SYSTEM = """You are the intent router for a visual novel authoring chat interface. \
A creator sends free-form messages about a story that has ALREADY been generated. \
Classify each message into exactly one of these intents:

- local_regen: creator wants a specific EXISTING scene's dialogue rewritten \
(different tone, fix pacing, "make this scene funnier", etc.). Requires target_scene_id.
- add_character: creator wants to introduce a NEW character not currently in the cast.
- edit_asset: creator wants to swap/regenerate a background, sprite, or music cue \
for something that already exists. Requires target_scene_id or target_character_id \
when identifiable.
- explain: creator is asking a QUESTION about the story/setting/characters — no \
mutation requested (e.g. "why does the ending branch here", "who is char_yuki").
- unknown: message doesn't clearly map to any of the above, or is missing \
information needed to act (e.g. references a scene that isn't in the provided list).

Only reference scene_id / character_id values that appear in the context below — \
never invent one. If the message is ambiguous about WHICH scene/character, prefer \
"unknown" over guessing, and say why in `reasoning`.

Rewrite the ask into `instruction`: a concise, actionable directive (not a \
restatement of the raw message) that a downstream Writer call or explainer can \
use directly as revision feedback / a question to answer."""


def _build_context(blackboard: dict) -> str:
    """Compact, token-cheap summary of the current project state for the
    classifier prompt — scene ids + titles, character ids + names. Full
    dialogue/description text is deliberately excluded; the classifier only
    needs enough to resolve references, not to write prose."""
    lines: list[str] = []

    theme = blackboard.get("theme") or blackboard.get("world_setting", {}).get("title")
    if theme:
        lines.append(f"Story: {theme}")

    scenes = blackboard.get("scene_scripts") or []
    if scenes:
        lines.append("Scenes:")
        for s in scenes:
            sid = s.get("id", "?") if isinstance(s, dict) else getattr(s, "id", "?")
            title = s.get("title", "") if isinstance(s, dict) else getattr(s, "title", "")
            lines.append(f"  - {sid}: {title}")

    characters = blackboard.get("characters") or {}
    if characters:
        lines.append("Characters:")
        for cid, c in characters.items():
            name = c.get("name", cid) if isinstance(c, dict) else getattr(c, "name", cid)
            lines.append(f"  - {cid}: {name}")

    return "\n".join(lines) if lines else "(no project context available)"


async def classify_intent(
    message: str,
    blackboard: dict,
    *,
    llm=None,
) -> IntentClassification:
    """Classify one chat message against the current project's blackboard.

    Callers may inject an alternate `llm` callable for tests that don't want
    to touch the API — signature matches `ainvoke_llm`:
    `(system, user, schema=None, model=None, caller=None) -> T | str`.

    Never raises on LLM/parse failure — falls back to `intent="unknown"` with
    the failure reason in `reasoning`, so a flaky classification degrades to
    "ask the user to clarify" rather than crashing the chat turn.
    """
    message = (message or "").strip()
    if not message:
        return IntentClassification(intent="unknown", confidence=0.0, reasoning="Empty message")

    context = _build_context(blackboard)
    user = f"Project context:\n{context}\n\nCreator message: {message!r}"

    if llm is None:
        from vn_agent.services.llm import ainvoke_llm as _ainvoke
        try:
            from vn_agent.config import get_settings
            model = getattr(get_settings(), "llm_haiku_model", None) or "claude-haiku-4-5-20251001"
        except Exception:  # noqa: BLE001
            model = "claude-haiku-4-5-20251001"
        llm = _ainvoke
    else:
        model = None

    try:
        result = await llm(
            _SYSTEM, user, schema=IntentClassification, model=model, caller="chat_ops/intent_router",
        )
    except Exception as e:  # noqa: BLE001 — classification failure must not crash the chat turn
        logger.warning(f"classify_intent LLM call failed: {e}")
        return IntentClassification(
            intent="unknown", confidence=0.0,
            reasoning=f"Classifier call failed ({e}); ask the creator to rephrase",
        )

    if not isinstance(result, IntentClassification):
        # Defensive: a misbehaving mock/llm callable returned raw text instead
        # of the parsed schema instance ainvoke_llm(schema=...) promises.
        logger.warning(f"classify_intent got non-schema result: {type(result)!r}")
        return IntentClassification(
            intent="unknown", confidence=0.0, reasoning="Classifier returned unparseable output",
        )

    # Guard against hallucinated ids — never trust an id the classifier
    # invented that isn't actually in this project's scenes/characters.
    valid_scene_ids = {
        (s.get("id") if isinstance(s, dict) else getattr(s, "id", None))
        for s in (blackboard.get("scene_scripts") or [])
    }
    valid_char_ids = set((blackboard.get("characters") or {}).keys())

    if result.target_scene_id and result.target_scene_id not in valid_scene_ids:
        logger.info(f"classify_intent dropped hallucinated scene_id {result.target_scene_id!r}")
        result = result.model_copy(update={"target_scene_id": None})
        if result.intent == "local_regen":
            result = result.model_copy(update={
                "intent": "unknown",
                "reasoning": f"{result.reasoning} (scene id not found in project — dropped)".strip(),
            })

    if result.target_character_id and result.target_character_id not in valid_char_ids:
        logger.info(f"classify_intent dropped hallucinated character_id {result.target_character_id!r}")
        result = result.model_copy(update={"target_character_id": None})

    return result
