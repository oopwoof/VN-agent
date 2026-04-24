"""Phase 13-1 Step 3: cached prefix assembly + 1024-token threshold gating."""
from __future__ import annotations

from types import SimpleNamespace

from vn_agent.prompts.cached_prefix import build_monolithic_prefix


def test_enables_cache_when_above_threshold():
    """Anthropic Sonnet requires ≥1024 tokens (~3.2 chars/token ≈ 3280 chars)
    for cache write. A large system prompt alone should cross it."""
    big_system = "SYSTEM PROMPT: " + ("A" * 10000)  # ~3000+ tokens conservatively
    text, enabled = build_monolithic_prefix(
        system_prompt=big_system,
        always_lore="",
        chapter_lore="",
    )
    assert enabled is True
    assert text.startswith("SYSTEM PROMPT:")


def test_disables_cache_when_below_threshold():
    """Short prompt falls below 2048 (our conservative Haiku threshold)
    → caching explicitly disabled. Keeps us from paying 1.25× write with
    no cache-read discount payoff."""
    short_system = "short system"
    text, enabled = build_monolithic_prefix(
        system_prompt=short_system,
        always_lore="tiny always lore",
        chapter_lore="tiny chapter lore",
    )
    assert enabled is False
    assert "short system" in text
    assert "tiny always lore" in text
    assert "tiny chapter lore" in text


def test_concatenation_order():
    """Parts must appear in the order: system → always → chapter → chapters."""
    text, _ = build_monolithic_prefix(
        system_prompt="[SYSTEM]",
        always_lore="[ALWAYS]",
        chapter_lore="[CHAPTER]",
        finalized_chapters=[SimpleNamespace(chapter_id="ch01", summary="[CH01 SUMMARY]")],
    )
    assert text.find("[SYSTEM]") < text.find("[ALWAYS]")
    assert text.find("[ALWAYS]") < text.find("[CHAPTER]")
    assert text.find("[CHAPTER]") < text.find("[CH01 SUMMARY]")


def test_empty_finalized_chapters_omitted():
    """No finalized_chapters → that section not rendered at all (no dangling
    header that would waste prefix tokens on empty content)."""
    text, _ = build_monolithic_prefix(
        system_prompt="[SYS]",
        always_lore="",
        chapter_lore="",
        finalized_chapters=None,
    )
    assert "Prior chapter summaries" not in text


def test_min_tokens_override_enables_cache_on_short_prefix():
    """Callers can relax the threshold (test-only; production uses 2048)."""
    _, enabled = build_monolithic_prefix(
        system_prompt="x" * 500,  # ~156 tokens
        min_tokens=100,  # force lower bar
    )
    assert enabled is True
