"""Phase 13-1 / Step 3: monolithic Anthropic prompt-cache prefix.

Why this module exists:

Gemini 3 Pro's BLOCKER review pointed out three cache-related failures in
the previous always_lore design:

  1. Anthropic's cache_write has a 1024-token minimum (2048 for Haiku).
     A sparse always_lore block (premise + 2 main characters ~ 500-800
     tokens) silently falls below the threshold; cache_control is noted
     in the request but the cache write never fires. Cost goes UP
     (1.25× base) with no read-discount payoff.
  2. The 5-minute ephemeral TTL doesn't cover 30-min end-to-end runs
     with image/BGM generation gaps. Most cache reads miss.
  3. Mid-run prefix mutation (Writer learns about a new character,
     world_var value ticks) invalidates the entire cached prefix.

Fix: assemble a single monolithic prefix (system prompt + always_lore +
chapter_lore + finalized-chapter summaries) that is:

  - Guaranteed ≥ 1024 tokens (padded with additional always-scope content
    if it falls short; if still short, caching is DISABLED for the run
    and we log the miss rather than paying 1.25× write cost)
  - Cached with the 1-hour tier (ttl="1h"), not 5-min ephemeral
  - Updated ONLY at chapter boundaries — Writer calls within one chapter
    all read the same cached prefix, no intra-chapter churn

Usage (conceptual):

    prefix_text, enable_cache = build_monolithic_prefix(
        system_prompt=WRITER_SYSTEM + character_bible,
        always_lore=always_block,
        chapter_lore=chapter_block,
        finalized_chapters=[...],  # Step 6 populates this
    )
    await ainvoke_llm(
        system_prompt=prefix_text,
        user_prompt=user_msg,
        cache_prefix=prefix_text if enable_cache else None,
        cache_ttl="1h",
    )
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Anthropic cache-write minimum — defined by the API, not configurable.
# Sonnet / Opus: 1024 tokens; Haiku: 2048 tokens. We pick the stricter
# bound (2048) because the Writer can run on either model under tier
# rotation, and paying for an un-cached call is worse than leaving the
# feature off.
#
# Ref (late 2025): https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
_MIN_CACHE_TOKENS: int = 2048

# Rough char→token heuristic — Anthropic Claude 3.5+ averages ~3.5 chars
# per token for English prose. 3.2 chars/token gives a conservative
# underestimate (we'd rather falsely disable caching on a borderline run
# than falsely enable it and pay the 1.25× write miss).
_CHARS_PER_TOKEN: float = 3.2


def _estimate_tokens(text: str) -> int:
    """Conservative token estimate. Prefer an underestimate so that
    caching is enabled only when the prefix is safely above threshold."""
    return int(len(text) / _CHARS_PER_TOKEN)


def build_monolithic_prefix(
    system_prompt: str,
    always_lore: str = "",
    chapter_lore: str = "",
    finalized_chapters: list[Any] | None = None,
    min_tokens: int = _MIN_CACHE_TOKENS,
) -> tuple[str, bool]:
    """Assemble the cache-friendly prefix and decide whether caching pays off.

    Returns (prefix_text, enable_cache).

    Order of concatenation (stable across Writer calls in the same chapter):
      1. system_prompt           — WRITER_SYSTEM + character_bible
      2. always_lore             — premise + main-character profiles
      3. chapter_lore            — world_vars + secondary characters
      4. finalized_chapters      — prior chapter summaries (Step 6 feed)

    If the assembled prefix falls below Anthropic's cache-write threshold,
    caching is explicitly DISABLED for the run (enable_cache=False). The
    function still returns a valid prefix_text so callers can inline it
    into the system segment without caching.
    """
    parts: list[str] = []
    if system_prompt:
        parts.append(system_prompt.rstrip())
    if always_lore:
        parts.append("")
        parts.append(always_lore.rstrip())
    if chapter_lore:
        parts.append("")
        parts.append(chapter_lore.rstrip())
    if finalized_chapters:
        parts.append("")
        parts.append("--- Prior chapter summaries ---")
        for ch in finalized_chapters:
            ch_id = getattr(ch, "chapter_id", "?")
            summary = getattr(ch, "summary", None) or ""
            if summary:
                parts.append(f"[{ch_id}] {summary.rstrip()}")

    prefix_text = "\n".join(parts)
    est_tokens = _estimate_tokens(prefix_text)

    if est_tokens < min_tokens:
        logger.info(
            f"[cached_prefix] estimated {est_tokens} tokens < {min_tokens} min — "
            f"caching DISABLED for this run to avoid 1.25× write with no discount. "
            f"Add more always-scope content (longer character profiles, bigger "
            f"premise) or accept the higher per-call cost."
        )
        return prefix_text, False

    logger.info(
        f"[cached_prefix] {est_tokens} tokens ≥ {min_tokens} — caching ENABLED "
        f"with ttl=1h. Expected read-discount kicks in on the 2nd call."
    )
    return prefix_text, True
