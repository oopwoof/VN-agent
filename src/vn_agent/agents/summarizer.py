"""Sprint 11-1: recursive scene summarization (Haiku).

Long-form VN generation (20+ scenes) can't keep full dialogue of every
prior scene in Writer's context. Sprint 7-2's `writer_context_window`
handles the last 1-2 scenes verbatim; everything older needs a bounded-
size summary.

This module produces per-scene ≤100-word summaries via Haiku — cheap
translation work, fits the project's model-selection rule. Summaries
are called AFTER the scene is written + reviewed (not during writing)
so they describe what actually landed, not what was planned.

Deferred (Sprint 11+ if run sizes justify):
  - Chapter-level rollups every N scene summaries (500-word meta-summary)
  - LLM-as-judge quality check on summaries
  - Human-editable summary overrides for creator mode

Design notes:
  - Temperature 0.2 (low) so regenerations are near-deterministic,
    limiting drift across retries
  - Failure is non-blocking — scene.summary stays None on Haiku error,
    downstream Writer just skips the older-scene block
  - Gated by settings.enable_scene_summarization (default False) so
    existing 6-10 scene demos don't pay the per-scene Haiku cost
"""
from __future__ import annotations

import logging

from vn_agent.config import get_settings
from vn_agent.schema.script import Scene
from vn_agent.services.llm import ainvoke_llm

logger = logging.getLogger(__name__)


SUMMARIZER_SYSTEM = """You are a scene summarizer for long-form visual novels. \
Given the full dialogue of one scene, produce a concise ≤100-word summary \
that captures:

1. Who appears and what they do
2. The scene's emotional pivot (what shifts from start to end)
3. Any concrete facts introduced that later scenes might reference \
(new character, new location, revealed secret, item changing hands)
4. Any state changes declared (if state_writes is in the input)

Write in present tense, third person, plain English. No flowery \
language, no quotes from the dialogue — this is reference material, \
not prose. Return ONLY the summary, no preamble, no <thinking> tags."""


async def summarize_scene(scene: Scene) -> str | None:
    """Return a ≤100-word summary of the scene, or None on error.

    Non-blocking: any failure (Haiku down, scene empty, parse issue)
    logs at DEBUG and returns None. Caller treats None as "no summary
    available" and skips the prior-scene summary injection for this one.
    """
    if not scene.dialogue:
        return None

    settings = get_settings()
    dialogue_text = "\n".join(
        f"{d.character_id or 'NARRATION'} ({d.emotion}): {d.text}"
        for d in scene.dialogue
    )
    state_note = ""
    if scene.state_writes:
        state_note = (
            f"\n\nState changes this scene declares: {scene.state_writes}"
        )
    user_prompt = (
        f"Scene id: {scene.id}\n"
        f"Scene title: {scene.title}\n"
        f"Strategy: {scene.narrative_strategy or 'unspecified'}\n"
        f"Characters present: {scene.characters_present}\n"
        f"Dialogue:\n{dialogue_text}"
        f"{state_note}\n\n"
        "Summarize in ≤100 words."
    )
    try:
        response = await ainvoke_llm(
            SUMMARIZER_SYSTEM,
            user_prompt,
            model=settings.llm_summarizer_model,
            caller=f"summarizer/{scene.id}",
        )
        content = (
            response.content if hasattr(response, "content") else str(response)
        ).strip()
        if not content:
            return None
        return content
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Summarizer failed for scene '{scene.id}': {e}")
        return None
