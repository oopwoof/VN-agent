"""BM25-driven few-shot injection of negative feedback into Writer prompts.

Design decisions
---------------
- Down-votes ONLY. Up-votes carry no actionable "avoid" signal for the
  Writer prompt — they matter for the Reflection Agent (P1-3) as anchors
  for positive rule extraction, but not here.
- BM25 not embeddings. Feedback reasons are short (≤200 chars typical),
  keyword-heavy, and per-language. BM25 punches above its weight on that
  distribution and needs no model download. Reuses v3 Sprint 6-4's
  rank_bm25 dependency.
- Retrieval query is scene-shaped, not just theme-shaped. We concatenate
  scene.description + narrative_strategy + characters_present so the
  matched down-votes are relevant to what Writer is about to draft, not
  just what genre it's writing.
- Injection format is prose. Writer expects "AVOID: X. AVOID: Y." lines
  in the user prompt just above the "write N dialogue lines" instruction
  — matches how Sprint 8 dynamic prompt sections read to Sonnet.
- Graceful degrade to empty string when either rank_bm25 or a corpus of
  down-vote reasons is missing. Callers can always cat the result into
  their prompt without a None-check.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from vn_agent.feedback import store as fb_store

logger = logging.getLogger(__name__)


try:
    from rank_bm25 import BM25Okapi  # type: ignore
    _HAS_BM25 = True
except ImportError:  # pragma: no cover — rank_bm25 is a base dep, this is defensive
    _HAS_BM25 = False


# Sizing knobs. Kept module-level so tests and future config can override.
_DEFAULT_TOP_K = 3
# BM25's IDF term goes NEGATIVE on tiny corpora (a term present in the
# only doc yields log(0.5/1.5) ≈ -1.1). At M0 our feedback corpus is
# small by design; a strict positive floor would gate out every hit for
# the first few dozen records. Use a modest negative default so the
# top_k selector + basic BM25 ranking do the actual work. As the corpus
# grows past ~30 records the IDF normalizes and scores go positive again.
_DEFAULT_MIN_SCORE = -1.0
_DEFAULT_CORPUS_CAP = 500         # cap on down-vote reasons scanned per call
_MAX_REASON_CHARS = 240           # trim per-reason to keep prompt bounded

# CJK-aware token split: single CJK chars each count as tokens; latin words
# tokenize by whitespace + strip punctuation. Good enough for BM25 on the
# short mixed-language corpus we expect.
_CJK_RANGE = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
_LATIN_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    toks: list[str] = []
    latin_tokens = _LATIN_TOKEN.findall(text.lower())
    toks.extend(latin_tokens)
    for ch in text:
        if _CJK_RANGE.match(ch):
            toks.append(ch)
    return toks


@dataclass
class InjectionResult:
    """What P1-2 injects — carried alongside the prompt so downstream
    can log / audit which feedback drove which generation."""
    text: str = ""                  # rendered prose ready to concat into prompt
    matched: list[str] = field(default_factory=list)  # reason strings that hit
    matched_ids: list[str] = field(default_factory=list)  # feedback ids
    score: float = 0.0              # sum of BM25 scores (running signal)

    @property
    def is_empty(self) -> bool:
        return not self.text


def _load_down_reasons(cap: int) -> tuple[list[str], list[str]]:
    """Return (reasons[], ids[]) parallel arrays for BM25 indexing.

    We truncate long reasons at `_MAX_REASON_CHARS` so BM25 stays sane
    even if a creator paste-dumps a huge critique into one record.
    """
    records = fb_store.load_by_verdict("down")
    if cap > 0:
        records = records[-cap:]
    reasons: list[str] = []
    ids: list[str] = []
    for r in records:
        if not r.reason:
            continue
        clean = r.reason.strip()
        if not clean:
            continue
        if len(clean) > _MAX_REASON_CHARS:
            clean = clean[:_MAX_REASON_CHARS].rstrip() + "…"
        reasons.append(clean)
        ids.append(r.id)
    return reasons, ids


def build_scene_query(
    scene: Any,
    characters: dict | None = None,
    extra: Iterable[str] | None = None,
) -> str:
    """Assemble a rich query string from Writer's scene context.

    Args:
        scene: object with `.description`, `.narrative_strategy`,
               `.characters_present` (typically a `schema.script.Scene`).
        characters: id→CharacterProfile dict; used to add personality hints.
        extra: additional tokens the caller wants weighted (e.g. theme).

    Returns a plain string suitable for tokenization by `_tokenize`.
    """
    parts: list[str] = []
    for attr in ("description", "title", "narrative_strategy"):
        val = getattr(scene, attr, None)
        if val:
            parts.append(str(val))
    present = getattr(scene, "characters_present", None) or []
    if present and characters:
        for cid in present:
            char = characters.get(cid)
            if char is None:
                continue
            for attr in ("role", "personality"):
                v = getattr(char, attr, None)
                if v:
                    parts.append(str(v))
    if extra:
        parts.extend(str(x) for x in extra if x)
    return "\n".join(parts)


def build_injection(
    scene: Any = None,
    characters: dict | None = None,
    *,
    extra_query: Iterable[str] | None = None,
    top_k: int = _DEFAULT_TOP_K,
    min_score: float = _DEFAULT_MIN_SCORE,
    corpus_cap: int = _DEFAULT_CORPUS_CAP,
) -> InjectionResult:
    """Retrieve top-k down-vote reasons relevant to `scene` and format them.

    Returns an `InjectionResult` whose `.text` is empty when:
      - rank_bm25 isn't installed (degrade cleanly)
      - the feedback JSONL is missing or has no down-votes with reasons
      - no matched reason clears `min_score`

    Callers append `.text` verbatim to the Writer prompt; empty is safe.
    """
    if not _HAS_BM25:
        return InjectionResult()

    reasons, ids = _load_down_reasons(corpus_cap)
    if not reasons:
        return InjectionResult()

    query = build_scene_query(scene, characters, extra_query) if scene is not None else ""
    if not query.strip():
        return InjectionResult()

    tokenized_corpus = [_tokenize(r) for r in reasons]
    query_tokens = _tokenize(query)
    if not query_tokens:
        return InjectionResult()

    # BM25 needs a corpus of ≥ 3 documents to produce meaningful IDF-driven
    # scores. With 1-2 docs the term dominance normalizer flattens
    # everything to zero and we lose ranking signal. Under that floor,
    # fall back to plain query-token overlap count — same ordering
    # intuition, no ML voodoo, and it's positive so `min_score` handling
    # stays consistent.
    if len(tokenized_corpus) < 3:
        query_set = set(query_tokens)
        scores = [
            float(sum(1 for t in doc if t in query_set))
            for doc in tokenized_corpus
        ]
    else:
        bm25 = BM25Okapi(tokenized_corpus)
        scores = list(bm25.get_scores(query_tokens))
    ranked = sorted(zip(scores, reasons, ids, strict=True), reverse=True)

    hits = [(s, r, i) for s, r, i in ranked if s >= min_score][:top_k]
    if not hits:
        return InjectionResult()

    lines = ["AVOID (based on past reader feedback):"]
    matched_reasons: list[str] = []
    matched_ids: list[str] = []
    total_score = 0.0
    for score, reason, rid in hits:
        lines.append(f"- {reason}")
        matched_reasons.append(reason)
        matched_ids.append(rid)
        total_score += float(score)

    logger.info(
        f"Feedback injection: {len(hits)} down-vote match(es) "
        f"(sum-score={total_score:.2f})"
    )
    return InjectionResult(
        text="\n".join(lines),
        matched=matched_reasons,
        matched_ids=matched_ids,
        score=total_score,
    )
