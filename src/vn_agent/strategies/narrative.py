"""Narrative strategy system for visual novels.

Strategy taxonomy aligned with the COLX_523 annotation guideline
(sprint3/Annotation_Guideline_3.0.pdf) so Director-emitted labels can
be used directly for few-shot RAG lookup into the annotated corpus.

Six strategies are *dataset-aligned* — they have annotated examples in
final_annotations.csv and therefore support few-shot retrieval:
  accumulate, erode, rupture, uncover, contest, drift

Two strategies are *generation-only* — kept for richer Director guidance
but have no corpus support, so Writer falls back to the non-few-shot
path when these are selected:
  escalate, resolve

The semantic definitions mirror the annotator "physics framework" so a
Director-emitted strategy and a corpus-tagged strategy mean the same
thing to downstream agents.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StrategyType(StrEnum):
    # ── Dataset-aligned (annotated in final_annotations.csv) ───────────────
    ACCUMULATE = "accumulate"   # Buildup / co-directional vectors crossing a threshold
    ERODE = "erode"             # Wear-down / slow entropy of support, facade, or hope
    RUPTURE = "rupture"         # Shock / step function, discontinuous jump in state
    UNCOVER = "uncover"         # Revelation that invalidates prior understanding
    CONTEST = "contest"         # Fight / opposing vectors between characters
    DRIFT = "drift"             # Vibe shift / undirected Brownian motion

    # ── Generation-only (no corpus examples — Writer skips few-shot) ───────
    ESCALATE = "escalate"       # Continuously raise the stakes
    RESOLVE = "resolve"         # Bring closure to accumulated tension


# Labels that have annotated examples and can drive few-shot retrieval.
DATASET_ALIGNED: frozenset[str] = frozenset({
    StrategyType.ACCUMULATE.value,
    StrategyType.ERODE.value,
    StrategyType.RUPTURE.value,
    StrategyType.UNCOVER.value,
    StrategyType.CONTEST.value,
    StrategyType.DRIFT.value,
})


def is_dataset_aligned(strategy: str) -> bool:
    """True when RAG few-shot lookup can be expected to find corpus examples."""
    return strategy in DATASET_ALIGNED


@dataclass
class NarrativeStrategy:
    type: StrategyType
    description: str
    guidance: str
    suggested_moods: list[str]


STRATEGIES: dict[str, NarrativeStrategy] = {
    # ── Accumulate: co-directional buildup crossing a threshold ────────────
    StrategyType.ACCUMULATE: NarrativeStrategy(
        type=StrategyType.ACCUMULATE,
        description="Same-direction buildup that crosses a clear threshold",
        guidance=(
            "Forces stack in the same direction until a tipping point is reached. "
            "Each beat adds weight without reversal — support, pressure, urgency, "
            "or admiration escalates until one line clearly crosses into a "
            "stronger committed state (concrete offer, accepted help, a stronger "
            "stance, or an overwhelming moment). Buildup without a threshold is Drift."
        ),
        suggested_moods=["peaceful", "romantic", "tense"],
    ),

    # ── Erode: wear-down of support, facade, or composure ──────────────────
    StrategyType.ERODE: NarrativeStrategy(
        type=StrategyType.ERODE,
        description="Entropy: slow wearing down of support, facade, or emotional restraint",
        guidance=(
            "A maintained positive — trust, patience, stamina, confidence, hope, "
            "composure, a social mask — gradually gives way. The dominant movement "
            "is loss, drain, or collapse rather than escalation. Prefer Erode over "
            "Contest when the wearing-down is internal; prefer Erode over Accumulate "
            "when the change is defenses dissolving, not pressure building."
        ),
        suggested_moods=["melancholic", "tense", "mysterious"],
    ),

    # ── Rupture: discontinuous jump / shock ────────────────────────────────
    StrategyType.RUPTURE: NarrativeStrategy(
        type=StrategyType.RUPTURE,
        description="Step function: discontinuous jump that breaks the current flow",
        guidance=(
            "A sudden break — interruption, unmotivated behavior, institutional "
            "denial, hard scene cut ('The next day…', 'I find myself…'). The main "
            "effect is discontinuity itself, not a reinterpretation of the past. "
            "If the surprise *invalidates prior understanding*, use Uncover instead."
        ),
        suggested_moods=["tense", "epic", "mysterious"],
    ),

    # ── Uncover: revelation that rewires meaning ───────────────────────────
    StrategyType.UNCOVER: NarrativeStrategy(
        type=StrategyType.UNCOVER,
        description="Revelation / coordinate transformation — prior understanding is invalidated",
        guidance=(
            "A disclosure (fact, ability, motive, identity, or evaluative recognition) "
            "forces a cognitive reset: what the reader thought was happening now "
            "means something different. Requires a clear cause, negation of the old "
            "frame, and meaningful impact on what follows. Mere announcements or "
            "refusals that only redirect the next action are Rupture, not Uncover."
        ),
        suggested_moods=["mysterious", "tense", "melancholic"],
    ),

    # ── Contest: interpersonal opposition ──────────────────────────────────
    StrategyType.CONTEST: NarrativeStrategy(
        type=StrategyType.CONTEST,
        description="Opposing vectors between characters with clearly different stances",
        guidance=(
            "Movement comes from active opposition — argument, refusal, strategic "
            "disagreement, coercive pressure, quiet pushback, cold resistance, "
            "forced handoff. Shouting is not required; a curt exit or passive "
            "resistance counts when it functions as opposition to another party's "
            "demand. If there are no genuinely opposing positions, it's not Contest."
        ),
        suggested_moods=["tense", "epic", "melancholic"],
    ),

    # ── Drift: undirected vibe shift ───────────────────────────────────────
    StrategyType.DRIFT: NarrativeStrategy(
        type=StrategyType.DRIFT,
        description="Low-stakes Brownian motion: atmosphere and banter without a decisive turn",
        guidance=(
            "A quiet afternoon that meanders — casual banter, mild teasing, "
            "atmosphere, a routine handoff. No line produces a decisive "
            "threshold-crossing. Default for slice-of-life and conversational "
            "scenes. If the scene ends with a clear commitment, alliance, or "
            "stronger stance than it began with, use Accumulate instead."
        ),
        suggested_moods=["peaceful", "romantic", "neutral"],
    ),

    # ── Escalate: generation-only composite strategy ───────────────────────
    StrategyType.ESCALATE: NarrativeStrategy(
        type=StrategyType.ESCALATE,
        description="Continuously raise the stakes across multiple beats",
        guidance=(
            "Each scene presents a higher-stakes version of the conflict — what "
            "starts personal becomes consequential, then universal. "
            "Generation-only: no corpus examples, so Writer relies on guidance alone."
        ),
        suggested_moods=["tense", "epic", "mysterious"],
    ),

    # ── Resolve: generation-only composite strategy ────────────────────────
    StrategyType.RESOLVE: NarrativeStrategy(
        type=StrategyType.RESOLVE,
        description="Bring closure and healing to accumulated tension",
        guidance=(
            "Allow characters to finally say what they couldn't. Address unresolved "
            "threads; let the ending feel earned, not rushed. "
            "Generation-only: no corpus examples."
        ),
        suggested_moods=["peaceful", "romantic", "melancholic"],
    ),
}


def get_strategy(strategy_type: str) -> NarrativeStrategy | None:
    """Get a NarrativeStrategy by type string."""
    try:
        key = StrategyType(strategy_type)
        return STRATEGIES.get(key)
    except ValueError:
        return None


def get_all_strategies() -> list[NarrativeStrategy]:
    return list(STRATEGIES.values())


def format_strategies_for_prompt() -> str:
    """Format all strategies as a prompt-friendly description."""
    lines = ["Available narrative strategies:\n"]
    for strategy in STRATEGIES.values():
        lines.append(f"- **{strategy.type.value}**: {strategy.description}")
        lines.append(f"  Guidance: {strategy.guidance}")
        lines.append(f"  Suggested moods: {', '.join(strategy.suggested_moods)}\n")
    return "\n".join(lines)
