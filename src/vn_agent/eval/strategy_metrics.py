"""Sprint 8-2: rule-based strategy metrics (zero LLM calls).

Each narrative strategy gets a concrete, deterministic signal computed
from DialogueLine fields alone (text + emotion + speaker). Serves two
roles:

1. **Triangulation** — if Sonnet judge says rupture=5 but the rule-based
   rupture signal is near zero, that's a flag for investigation, not a
   PASS. Lets us catch judge hallucinations without needing a third LLM.
2. **Baseline-independent evaluation** — baseline modes (single-shot,
   self-refine) are judged by the same Sonnet + GPT-4o judges as the
   full pipeline, but these rule-based metrics don't care about judge
   identity. They measure what's ACTUALLY in the text.

The physics definitions (from the COLX_523 annotation guideline) are
the source of truth. Each metric returns a float in [0, 1] where
higher = stronger signal for that strategy.

These are **signals**, not verdicts. A high rupture signal doesn't
prove a scene is a rupture; a zero signal doesn't prove it isn't. But
persistent disagreement between rule signal and judge score is
diagnostic.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from vn_agent.schema.script import Scene

# ── Emotion intensity ordering (for rupture / accumulate / erode) ─────────
# Approximate "energy" level; ties are fine.
_EMOTION_ENERGY: dict[str, int] = {
    "neutral": 0,
    "thoughtful": 1,
    "sad": 2,
    "scared": 3,
    "surprised": 3,
    "loving": 4,
    "happy": 4,
    "determined": 4,
    "angry": 5,
}

# Emotion groups for rupture divergence detection.
_EMOTION_GROUP: dict[str, str] = {
    "neutral": "calm",
    "thoughtful": "calm",
    "sad": "down",
    "scared": "down",
    "surprised": "shock",
    "angry": "shock",
    "determined": "up",
    "happy": "up",
    "loving": "up",
}


# ── Sentiment keyword lists (coarse) ──────────────────────────────────────
_POS_WORDS = {
    "love", "hope", "trust", "warm", "smile", "laugh", "peace", "joy",
    "tender", "beautiful", "safe", "gentle", "together", "forgive",
}
_NEG_WORDS = {
    "fear", "doubt", "lose", "lost", "die", "dying", "dead", "alone",
    "cold", "cruel", "hate", "grief", "wound", "break", "broken",
    "empty", "fail", "failure", "ruin",
}


@dataclass
class StrategySignals:
    """All six signals for a single scene. Higher = stronger signal."""
    accumulate: float
    erode: float
    rupture: float
    uncover: float
    contest: float
    drift: float

    def as_dict(self) -> dict[str, float]:
        return {
            "accumulate": round(self.accumulate, 3),
            "erode": round(self.erode, 3),
            "rupture": round(self.rupture, 3),
            "uncover": round(self.uncover, 3),
            "contest": round(self.contest, 3),
            "drift": round(self.drift, 3),
        }

    def best_match(self) -> str:
        """Strategy with the highest rule-based signal."""
        items = [
            ("accumulate", self.accumulate), ("erode", self.erode),
            ("rupture", self.rupture), ("uncover", self.uncover),
            ("contest", self.contest), ("drift", self.drift),
        ]
        return max(items, key=lambda kv: kv[1])[0]


def compute_signals(scene: Scene) -> StrategySignals:
    """Compute all six strategy signals for a scene."""
    lines = scene.dialogue
    if len(lines) < 2:
        # Too short to compute anything meaningful
        return StrategySignals(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    return StrategySignals(
        accumulate=_accumulate_signal(lines),
        erode=_erode_signal(lines),
        rupture=_rupture_signal(lines),
        uncover=_uncover_signal(lines),
        contest=_contest_signal(lines),
        drift=_drift_signal(lines),
    )


# ── Individual signals ────────────────────────────────────────────────────

def _rupture_signal(lines) -> float:
    """ONE large emotion-energy jump in the middle of the scene.

    Physics: step function, discontinuous jump. Distinguished from
    contest (many small alternations between two agents) by looking
    for the MAX single-beat energy delta — rupture should have one
    dramatic shift, not steady back-and-forth.

    Scoring: normalize the max jump by max energy range (5) and weight
    by position — late-middle pivots (idx 3..n-2) get full credit,
    line-1 / line-last jumps count for less (early/tail boundary effects).
    """
    energies = [_EMOTION_ENERGY.get(d.emotion, 0) for d in lines]
    if len(energies) < 3:
        return 0.0
    # Jumps: abs(energy[i+1] - energy[i])
    jumps = [abs(b - a) for a, b in zip(energies[:-1], energies[1:])]
    # Position weight: pivot should not be first or last line
    n = len(jumps)
    def _pos_weight(i: int) -> float:
        if n <= 2:
            return 1.0
        # Full weight in middle third, half at boundaries
        if i < 1 or i >= n - 1:
            return 0.5
        return 1.0
    weighted = [_pos_weight(i) * jumps[i] for i in range(n)]
    max_weighted_jump = max(weighted)
    # Normalize: energy range is 0-5, so max delta is 5
    base = min(1.0, max_weighted_jump / 5.0)
    # Penalize scenes with MANY large jumps (those are contest, not rupture)
    large_jump_count = sum(1 for j in jumps if j >= 3)
    if large_jump_count >= 3:
        base *= 0.5
    return base


def _accumulate_signal(lines) -> float:
    """Monotonic emotion-intensity increase toward a peak.

    Physics: co-directional buildup crossing a threshold. Measure fit
    to a rising ramp: early energies should be low, late energies high.
    """
    energies = [_EMOTION_ENERGY.get(d.emotion, 0) for d in lines]
    if not energies or max(energies) == 0:
        return 0.0
    # Correlation between line index and energy — positive slope = accumulate
    n = len(energies)
    xs = list(range(n))
    mx = sum(xs) / n
    me = sum(energies) / n
    num = sum((x - mx) * (e - me) for x, e in zip(xs, energies))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    de = math.sqrt(sum((e - me) ** 2 for e in energies))
    if dx == 0 or de == 0:
        return 0.0
    r = num / (dx * de)  # Pearson r in [-1, 1]
    # Positive correlation = ramp up. Only positive half counts.
    return max(0.0, r)


def _erode_signal(lines) -> float:
    """Sentence length decline + ellipsis frequency + sentiment decay.

    Physics: entropy / wearing down. Earlier lines are longer and more
    positive; later lines shorter, more negative, more ellipsis.
    """
    if len(lines) < 3:
        return 0.0
    texts = [d.text for d in lines]
    # Ellipsis count per line (weighted toward later lines)
    ellipsis_rate = sum(
        (i / len(texts)) * (t.count("...") + t.count("…"))
        for i, t in enumerate(texts)
    ) / len(texts)
    # Sentence-length slope — negative slope is erode signal
    lengths = [len(t.split()) for t in texts]
    xs = list(range(len(lengths)))
    mx = sum(xs) / len(xs)
    ml = sum(lengths) / len(lengths)
    num = sum((x - mx) * (ln - ml) for x, ln in zip(xs, lengths))
    dx = sum((x - mx) ** 2 for x in xs)
    slope = num / dx if dx else 0
    # Normalize slope to [0, 1] — negative slope of ~1 word/line counts
    slope_signal = max(0.0, min(1.0, -slope / 2.0))
    # Sentiment decay: late half more negative than early half
    half = len(texts) // 2
    early_sent = _sentiment(" ".join(texts[:half]))
    late_sent = _sentiment(" ".join(texts[half:]))
    sent_signal = max(0.0, min(1.0, (early_sent - late_sent) / 2.0))
    return min(1.0, slope_signal * 0.4 + sent_signal * 0.4 + ellipsis_rate * 0.2)


def _uncover_signal(lines) -> float:
    """Information-reveal rate: new proper nouns introduced after line 2.

    Physics: coordinate transformation — something said in the middle
    forces reinterpretation. Proxy: density of new capitalized tokens
    in the back half of the scene.
    """
    tokens_per_line = [_extract_proper_nouns(d.text) for d in lines]
    seen: set[str] = set()
    # Line-by-line: what fraction of proper nouns are NEW at each position?
    newness_curve = []
    for i, tokens in enumerate(tokens_per_line):
        if not tokens:
            newness_curve.append(0.0)
            continue
        new = [t for t in tokens if t not in seen]
        newness_curve.append(len(new) / len(tokens))
        seen.update(tokens)
    if not newness_curve:
        return 0.0
    # Weight later positions more heavily (uncover pivot should be
    # middle-to-late, not line 1 which is always "new")
    n = len(newness_curve)
    weights = [min(1.0, max(0.0, (i - 1) / max(1, n - 3))) for i in range(n)]
    weighted = sum(w * v for w, v in zip(weights, newness_curve))
    total_weight = sum(weights) or 1
    return min(1.0, weighted / total_weight)


def _contest_signal(lines) -> float:
    """Speaker-alternation rate where emotion differs between turns.

    Physics: opposing vectors between agents. Signal is strong when
    speaker changes AND their emotion differs AND both are non-narration.
    """
    turns = [(d.character_id, d.emotion) for d in lines if d.character_id is not None]
    if len(turns) < 3:
        return 0.0
    diff_alternations = 0
    for (a_char, a_em), (b_char, b_em) in zip(turns[:-1], turns[1:]):
        if a_char != b_char and a_em != b_em:
            diff_alternations += 1
    return min(1.0, diff_alternations / (len(turns) - 1))


def _drift_signal(lines) -> float:
    """Low variance across all dimensions + absence of proper-noun reveals.

    Physics: Brownian motion / low-stakes. The inverse of rupture +
    contest + uncover; also needs absence of accumulation.
    """
    rup = _rupture_signal(lines)
    con = _contest_signal(lines)
    unc = _uncover_signal(lines)
    acc = _accumulate_signal(lines)
    # Drift = 1 - max(other decisive signals)
    decisive = max(rup, con, unc, acc)
    return max(0.0, 1.0 - decisive)


# ── Helpers ───────────────────────────────────────────────────────────────

# Mid-sentence capitalized tokens (high-precision named-entity signal).
# "He met Caelen yesterday" → {"Caelen"}; "Saw a cat" → {} (sentence-initial).
_MID_SENTENCE_PN_RE = re.compile(r"(?<=[a-z]\s)[A-Z][a-z]{2,}")
# Dramatic single-word reveal lines like "Caelen." or "Thorne. The man..."
# where the proper noun opens the line but is clearly a name (length ≥ 5,
# not followed by a common sentence continuation).
_DRAMATIC_REVEAL_RE = re.compile(r"^([A-Z][a-z]{4,})(?:[\s.!?,]|$)")


def _extract_proper_nouns(text: str) -> set[str]:
    """Capitalized tokens that look like named entities.

    Two rules:
      1. Capitalized token mid-sentence (after a lowercase word).
      2. Line-initial capitalized 5+ char word (dramatic single-word
         reveal like "Caelen." or "Thorne. The man...").
    False-positive rate stays low because sentence-initial short words
    ("Yes", "Just", "Sure") are excluded by the ≥5 char bar of rule 2.
    """
    found = set(_MID_SENTENCE_PN_RE.findall(text))
    m = _DRAMATIC_REVEAL_RE.match(text.strip())
    if m:
        found.add(m.group(1))
    return found


def _sentiment(text: str) -> float:
    """Very coarse positive-minus-negative word count, [-1, 1]."""
    tokens = Counter(w.lower().strip(".,!?\"'") for w in text.split())
    pos = sum(tokens[w] for w in _POS_WORDS if w in tokens)
    neg = sum(tokens[w] for w in _NEG_WORDS if w in tokens)
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total
