"""v4 P3-2: chat turn lifecycle — classify → preview → confirm → execute.

L1 fallback (per plan's 4-level intent-router safety net): every mutating
intent returns a preview and waits for an explicit confirm before touching
any file. Non-mutating intents (`explain`) and terminal ones (`unknown`)
resolve immediately — there's nothing to confirm.

Observability (per feedback_observability): every *resolved* turn (executed,
or explain/unknown answered) is appended to
`<output_dir>/chat_ops/turns.jsonl` — one line per turn, mirroring the
existing `rag_retrievals.jsonl` / `api_key_rotations.jsonl` per-run audit
trail convention. Previews that the creator cancels client-side are not
logged (the backend never sees a cancel) — this is a project-state audit
trail, not full UI telemetry.

Extensibility: new intents plug in by adding one entry to `_HANDLERS` and
(if the intent needs it) one branch in `intent_router.py`'s Literal — nothing
else in this module needs to change.
"""
from __future__ import annotations

import difflib
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vn_agent.chat_ops.intent_router import IntentClassification, classify_intent

logger = logging.getLogger(__name__)

_MUTATING_INTENTS = {"local_regen", "add_character", "edit_asset"}


@dataclass
class ChatTurnResult:
    """One chat turn's full lifecycle state. Preview and post-execute results
    share this shape — `executed`/`success`/`diff` are unset on a preview."""

    turn_id: str
    message: str
    intent: str
    confidence: float
    target_scene_id: str | None
    target_character_id: str | None
    instruction: str
    reasoning: str
    preview_text: str
    requires_confirmation: bool
    executed: bool = False
    success: bool | None = None
    result_text: str = ""
    diff: str | None = None
    wall_seconds: float | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


async def preview_turn(output_dir: str, blackboard: dict, message: str, *, llm=None) -> ChatTurnResult:
    """Classify `message` and produce a preview. Non-mutating intents
    (`explain`) are answered here directly — no separate execute round-trip.
    `unknown` gets a clarification prompt back, also terminal.
    Mutating intents return `requires_confirmation=True` and do NOT touch
    any file — the caller must call `execute_turn` with this result's
    classification fields to actually run it.
    """
    turn_id = uuid.uuid4().hex[:10]
    classification = await classify_intent(message, blackboard, llm=llm)

    if classification.intent == "explain":
        t0 = time.perf_counter()
        answer = await _answer_explain(message, blackboard, classification, llm=llm)
        result = ChatTurnResult(
            turn_id=turn_id, message=message, intent="explain",
            confidence=classification.confidence,
            target_scene_id=classification.target_scene_id,
            target_character_id=classification.target_character_id,
            instruction=classification.instruction,
            reasoning=classification.reasoning,
            preview_text=answer, requires_confirmation=False,
            executed=True, success=True, result_text=answer,
            wall_seconds=round(time.perf_counter() - t0, 2),
        )
        _log_turn(output_dir, result)
        return result

    if classification.intent == "unknown":
        clarify = (
            classification.reasoning
            or "I'm not sure which scene or character you mean — could you name it directly?"
        )
        result = ChatTurnResult(
            turn_id=turn_id, message=message, intent="unknown",
            confidence=classification.confidence,
            target_scene_id=None, target_character_id=None,
            instruction=classification.instruction, reasoning=classification.reasoning,
            preview_text=clarify, requires_confirmation=False,
            executed=False, success=None, result_text=clarify,
        )
        _log_turn(output_dir, result)
        return result

    # L2 fallback: a low-confidence mutating intent asks instead of acting.
    # L1 (the confirm card) only protects the creator if they read it — a
    # confident-looking card for a 0.3-confidence guess invites a reflexive
    # yes. Below the threshold we ask what they meant, which is also the
    # honest thing to render.
    from vn_agent.config import get_settings

    threshold = get_settings().chat_intent_confidence_threshold
    if classification.confidence < threshold:
        clarify = _build_low_confidence_clarification(classification, threshold)
        result = ChatTurnResult(
            turn_id=turn_id, message=message, intent=classification.intent,
            confidence=classification.confidence,
            target_scene_id=classification.target_scene_id,
            target_character_id=classification.target_character_id,
            instruction=classification.instruction,
            reasoning=classification.reasoning,
            preview_text=clarify, requires_confirmation=False,
            executed=False, success=None, result_text=clarify,
        )
        _log_turn(output_dir, result)
        return result

    # Mutating intent — build a preview, do not touch disk yet.
    preview_text = _build_mutation_preview(classification, blackboard)
    return ChatTurnResult(
        turn_id=turn_id, message=message, intent=classification.intent,
        confidence=classification.confidence,
        target_scene_id=classification.target_scene_id,
        target_character_id=classification.target_character_id,
        instruction=classification.instruction, reasoning=classification.reasoning,
        preview_text=preview_text, requires_confirmation=True,
    )


async def execute_turn(output_dir: str, preview: ChatTurnResult) -> ChatTurnResult:
    """Run the mutating intent described by `preview` (as returned by
    `preview_turn`). Only called after the creator confirms. Always returns
    a resolved (non-confirmation-pending) ChatTurnResult and logs it."""
    if preview.intent not in _MUTATING_INTENTS:
        raise ValueError(f"execute_turn called on non-mutating intent {preview.intent!r}")

    handler = _HANDLERS.get(preview.intent, _handle_unimplemented)
    t0 = time.perf_counter()
    try:
        success, result_text, diff = await handler(output_dir, preview)
    except Exception as e:  # noqa: BLE001 — a handler failure is a resolved-but-failed turn, not a 500
        logger.exception(f"chat_ops execute_turn failed for intent={preview.intent!r}")
        success, result_text, diff = False, f"Failed: {e}", None

    resolved = ChatTurnResult(
        **{**preview.to_dict(), "requires_confirmation": False},
    )
    resolved.executed = True
    resolved.success = success
    resolved.result_text = result_text
    resolved.diff = diff
    resolved.wall_seconds = round(time.perf_counter() - t0, 2)
    if not success:
        resolved.error = result_text

    _log_turn(output_dir, resolved)
    return resolved


# ── Preview text builders ───────────────────────────────────────────────────

def _build_mutation_preview(c: IntentClassification, blackboard: dict) -> str:
    if c.intent == "local_regen":
        title = _scene_title(blackboard, c.target_scene_id) or c.target_scene_id
        return f"Rewrite scene '{title}' ({c.target_scene_id}) with: {c.instruction or '(no specific direction given)'}"
    if c.intent == "add_character":
        return (
            f"Add a new character — {c.instruction or '(no description given)'}. "
            "This writes a full profile into characters.json and adds them to "
            "the cast. Existing scenes are not rewritten: they'll be available "
            "to put on stage, not on stage yet."
        )
    if c.intent == "edit_asset":
        target = c.target_scene_id or c.target_character_id or "(unspecified)"
        return (
            f"Edit asset for {target} — {c.instruction or '(no description given)'}. "
            "Tries the open-source asset library first (free, licence-clean); "
            "falls back to regenerating the image when the job generates images."
        )
    return c.instruction or "(no preview available)"


def _build_low_confidence_clarification(
    c: IntentClassification, threshold: float,
) -> str:
    """Say what we think was asked and what's missing, so the creator can
    answer in one reply rather than guess what confused us."""
    guesses = {
        "local_regen": "rewrite a scene",
        "add_character": "add a character",
        "edit_asset": "change an image",
    }
    guess = guesses.get(c.intent, "change the project")
    missing = []
    if c.intent in ("local_regen", "edit_asset") and not c.target_scene_id:
        missing.append("which scene")
    if c.intent == "edit_asset" and not (c.target_scene_id or c.target_character_id):
        missing.append("which asset")
    if not c.instruction:
        missing.append("what to change")

    text = (
        f"I think you want to {guess}, but I'm only {c.confidence:.0%} sure "
        f"(I act on {threshold:.0%} or better)."
    )
    if missing:
        text += " Could you say " + " and ".join(missing) + "?"
    else:
        text += " Could you rephrase, naming the scene or character directly?"
    return text


def _scene_title(blackboard: dict, scene_id: str | None) -> str | None:
    if not scene_id:
        return None
    for s in blackboard.get("scene_scripts") or []:
        sid = s.get("id") if isinstance(s, dict) else getattr(s, "id", None)
        if sid == scene_id:
            return s.get("title") if isinstance(s, dict) else getattr(s, "title", None)
    return None


# ── explain (non-mutating, resolved inline in preview_turn) ────────────────

async def _answer_explain(message: str, blackboard: dict, c: IntentClassification, *, llm=None) -> str:
    from vn_agent.chat_ops.intent_router import _build_context

    system = (
        "You answer a visual novel creator's question about their own project. "
        "Use ONLY the context given — do not invent plot details, character traits, "
        "or scenes that aren't listed. If the context doesn't contain the answer, "
        "say so plainly rather than guessing. Keep the answer to 2-4 sentences."
    )
    context = _build_context(blackboard)
    user = f"Project context:\n{context}\n\nQuestion: {message}"

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
        raw = await llm(system, user, model=model, caller="chat_ops/explain")
        content = getattr(raw, "content", raw) if not isinstance(raw, str) else raw
        return str(content).strip()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"chat_ops explain call failed: {e}")
        return f"I couldn't answer that right now ({e}). Try again in a moment."


# ── local_regen handler (live — reuses agents/local_regen.py) ──────────────

async def _handle_local_regen(output_dir: str, preview: ChatTurnResult) -> tuple[bool, str, str | None]:
    from vn_agent.agents.local_regen import RegenError, regenerate_scene

    if not preview.target_scene_id:
        return False, "No target scene identified — rephrase naming the scene directly.", None

    old_text = _read_scene_dialogue_text(output_dir, preview.target_scene_id)
    try:
        summary = await regenerate_scene(
            Path(output_dir), preview.target_scene_id, revision_feedback=preview.instruction,
        )
    except RegenError as e:
        return False, str(e), None

    new_text = _read_scene_dialogue_text(output_dir, preview.target_scene_id)
    diff = "\n".join(difflib.unified_diff(
        old_text.splitlines(), new_text.splitlines(),
        fromfile=f"{preview.target_scene_id} (before)",
        tofile=f"{preview.target_scene_id} (after)",
        lineterm="",
    ))
    result_text = (
        f"Regenerated '{preview.target_scene_id}': "
        f"{summary['old_dialogue_count']} → {summary['new_dialogue_count']} lines "
        f"in {summary['wall_seconds']}s."
    )
    if summary["state_writes_changed"]:
        result_text += " Warning: state_writes changed — downstream scenes may need re-running."
    return True, result_text, diff


def _read_scene_dialogue_text(output_dir: str, scene_id: str) -> str:
    """Best-effort dialogue text dump for diffing. Returns '' if the script
    or scene can't be read (e.g. first call before any regen has ever run —
    diff against empty is still a valid, if uninteresting, diff)."""
    try:
        from vn_agent.schema.script import VNScript
        path = Path(output_dir) / "vn_script.json"
        script = VNScript.model_validate_json(path.read_text(encoding="utf-8"))
        for s in script.scenes:
            if s.id == scene_id:
                return "\n".join(f"{d.character_id or '(narration)'}: {d.text}" for d in s.dialogue)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Could not read scene dialogue for diff: {e}")
    return ""


# ── executors ────────────────────────────────────────────────────────────────

async def _handle_unimplemented(output_dir: str, preview: ChatTurnResult) -> tuple[bool, str, str | None]:  # noqa: ARG001
    """Default for an intent with no executor. Nothing routes here today —
    it stays as the honest landing spot for a future intent added to the
    router before its handler exists."""
    return (
        False,
        f"'{preview.intent}' is classified correctly but has no executor yet — "
        "recorded to the chat log; use the Asset panel or CLI tools in the meantime.",
        None,
    )


async def _handle_add_character(output_dir: str, preview: ChatTurnResult) -> tuple[bool, str, str | None]:
    from vn_agent.chat_ops.executors import add_character

    return await add_character.execute(output_dir, preview)


async def _handle_edit_asset(output_dir: str, preview: ChatTurnResult) -> tuple[bool, str, str | None]:
    from vn_agent.chat_ops.executors import edit_asset

    return await edit_asset.execute(output_dir, preview)


_HANDLERS: dict[str, Any] = {
    "local_regen": _handle_local_regen,
    "add_character": _handle_add_character,
    "edit_asset": _handle_edit_asset,
}


# ── audit trail ──────────────────────────────────────────────────────────────

def _log_turn(output_dir: str, turn: ChatTurnResult) -> None:
    """Append one resolved turn to <output_dir>/chat_ops/turns.jsonl.
    Best-effort — a logging failure must never break the chat response."""
    try:
        path = Path(output_dir) / "chat_ops" / "turns.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(turn.to_dict(), ensure_ascii=False))
            f.write("\n")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"chat_ops turn log write failed: {e}")
