"""Sprint 11-3: persona fingerprint audit (zero-LLM, pure Python).

In long-form (20+ scene) runs, Writer's dialogue can "OAI-standard
style" drift — characters start sounding uniform, losing their
Director-declared signature traits. This module checks whether each
character's speech_fingerprint traits still show up in their dialogue,
flagging drift for Reviewer feedback.

Cheap by design: substring + keyword matching, no NLI, no LLM. False
positives preferred to false negatives — "voice drift warning" is a
non-blocking nudge to the human reviewer, not a revision trigger.

Only runs when:
  - script has >= `persona_audit_min_scenes` scenes (default 10)
  - at least one character declared a non-empty speech_fingerprint

In short runs, drift isn't an issue and the fingerprint traits are
usually absent (Director was lazy), so the audit short-circuits.
"""
from __future__ import annotations

import logging
import re
from collections import Counter

from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import VNScript

logger = logging.getLogger(__name__)


def audit_personas(
    script: VNScript,
    characters: dict[str, CharacterProfile],
    min_scenes: int = 10,
    min_hit_rate: float = 0.3,
) -> list[str]:
    """Return a list of voice-drift warnings. Empty list == no drift.

    Algorithm:
      1. Collect all dialogue lines per character across the whole script.
      2. For each character with a non-empty speech_fingerprint:
         - extract keywords from each fingerprint trait (heuristic: words
           in quotes, or distinctive content words ≥ 4 chars)
         - count matches across that character's lines
         - compute hit_rate = matched_lines / total_lines
         - flag if hit_rate < min_hit_rate
      3. Return a warning per drifted character.

    Short-circuits with [] when:
      - script has fewer than min_scenes scenes
      - no character has a speech_fingerprint
      - no character has any dialogue lines
    """
    if len(script.scenes) < min_scenes:
        return []

    fingerprinted = {
        cid: char for cid, char in characters.items()
        if char.speech_fingerprint
    }
    if not fingerprinted:
        return []

    # Gather dialogue lines per character_id
    char_lines: dict[str, list[str]] = {cid: [] for cid in fingerprinted}
    for scene in script.scenes:
        for line in scene.dialogue:
            if line.character_id in char_lines:
                char_lines[line.character_id].append(line.text)

    warnings: list[str] = []
    for cid, char in fingerprinted.items():
        lines = char_lines[cid]
        if len(lines) < 3:
            continue  # character barely speaks; not drift, just not around

        # Extract keyword seeds from each fingerprint trait
        trait_keywords = [_extract_keywords(t) for t in char.speech_fingerprint]

        # For each trait, count how many lines contain >= 1 of its keywords
        matched_by_trait = []
        for keywords in trait_keywords:
            if not keywords:
                continue  # no extractable signal
            matches = sum(
                1 for line in lines
                if _line_matches_keywords(line, keywords)
            )
            matched_by_trait.append(matches / len(lines))

        if not matched_by_trait:
            # All traits had no extractable keywords — unusable fingerprint
            continue
        # Best trait hit rate (any one trait showing up is fine)
        best_rate = max(matched_by_trait)
        if best_rate < min_hit_rate:
            warnings.append(
                f"Persona audit: {char.name} ({cid}) — best fingerprint hit "
                f"rate is {best_rate:.0%} across {len(lines)} lines "
                f"(threshold {min_hit_rate:.0%}). "
                f"Traits: {char.speech_fingerprint[:3]}. "
                f"Voice may have drifted from Director's declaration."
            )
            logger.info(warnings[-1])

    return warnings


# ── Keyword extraction + matching helpers ────────────────────────────────

_QUOTED_PHRASE = re.compile(r"['\"]([^'\"]+)['\"]")
_TOKEN = re.compile(r"\b\w+\b")


def _extract_keywords(trait: str) -> set[str]:
    """Pull a set of keywords from a single speech_fingerprint string.

    Prefers quoted phrases ('says "bloody hell"'); falls back to content
    words ≥ 4 chars (skipping common stop-like words).
    """
    quoted = _QUOTED_PHRASE.findall(trait)
    if quoted:
        return {q.lower() for q in quoted if q.strip()}
    # No quoted phrase — pull content words ≥ 4 chars, skip meta words
    stop = {
        "uses", "never", "often", "sometimes", "under", "when",
        "speaks", "says", "prefers", "hates", "loves", "with",
        "word", "words", "phrase", "phrases", "sentence", "sentences",
        "most", "some", "this", "that", "they", "their", "there",
        "stress", "pressure", "formal", "informal", "casual",
    }
    return {
        t.lower() for t in _TOKEN.findall(trait)
        if len(t) >= 4 and t.lower() not in stop
    }


def _line_matches_keywords(line: str, keywords: set[str]) -> bool:
    """True iff any keyword appears as a substring in the line (case-insensitive)."""
    lower = line.lower()
    return any(k in lower for k in keywords)


def token_frequency(text: str) -> Counter[str]:
    """Exposed for external diagnostics — per-text token count."""
    return Counter(_TOKEN.findall(text.lower()))
