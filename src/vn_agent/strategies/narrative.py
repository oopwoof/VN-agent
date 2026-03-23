"""Narrative strategy system for visual novels."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StrategyType(StrEnum):
    ACCUMULATE = "accumulate"   # Gradually build up emotion/tension
    ERODE = "erode"             # Gradually wear down character/relationship
    RUPTURE = "rupture"         # Sudden break or revelation
    WEAVE = "weave"             # Interleave multiple storylines
    REVEAL = "reveal"           # Slowly uncover hidden truth
    CONTRAST = "contrast"       # Juxtapose conflicting elements
    ESCALATE = "escalate"       # Continuously raise stakes
    RESOLVE = "resolve"         # Bring closure to tension


@dataclass
class NarrativeStrategy:
    type: StrategyType
    description: str
    guidance: str
    suggested_moods: list[str]


STRATEGIES: dict[str, NarrativeStrategy] = {
    StrategyType.ACCUMULATE: NarrativeStrategy(
        type=StrategyType.ACCUMULATE,
        description="Gradually build emotional intensity",
        guidance=(
            "Start with calm, everyday interactions. "
            "Each scene should add a small emotional weight. "
            "By the midpoint, the accumulated feelings become undeniable."
        ),
        suggested_moods=["peaceful", "romantic", "melancholic"],
    ),
    StrategyType.ERODE: NarrativeStrategy(
        type=StrategyType.ERODE,
        description="Steadily wear down a relationship or belief",
        guidance=(
            "Begin with something solid—trust, hope, a conviction. "
            "Introduce small cracks through misunderstandings and disappointments. "
            "Each scene removes another layer until the foundation crumbles."
        ),
        suggested_moods=["melancholic", "tense", "mysterious"],
    ),
    StrategyType.RUPTURE: NarrativeStrategy(
        type=StrategyType.RUPTURE,
        description="Sudden revelation or break that changes everything",
        guidance=(
            "Build normalcy, then shatter it. "
            "A revelation, betrayal, or event should recontextualize everything before it. "
            "The scene after the rupture is a new world."
        ),
        suggested_moods=["tense", "epic", "mysterious"],
    ),
    StrategyType.WEAVE: NarrativeStrategy(
        type=StrategyType.WEAVE,
        description="Interleave multiple storylines that converge",
        guidance=(
            "Track two or more separate narrative threads. "
            "Each thread has its own emotional arc. "
            "Convergence should feel both surprising and inevitable."
        ),
        suggested_moods=["mysterious", "tense", "romantic"],
    ),
    StrategyType.REVEAL: NarrativeStrategy(
        type=StrategyType.REVEAL,
        description="Slowly uncover a hidden truth",
        guidance=(
            "The player suspects something is off from early on. "
            "Clues accumulate across scenes. "
            "The full truth, when revealed, transforms earlier scenes' meaning."
        ),
        suggested_moods=["mysterious", "tense", "melancholic"],
    ),
    StrategyType.CONTRAST: NarrativeStrategy(
        type=StrategyType.CONTRAST,
        description="Juxtapose light and dark, joy and sorrow",
        guidance=(
            "Place beautiful moments adjacent to painful ones. "
            "Use environment contrast—sunny scenes before tragedy, "
            "warmth before cold. The contrast amplifies both sides."
        ),
        suggested_moods=["joyful", "melancholic", "peaceful"],
    ),
    StrategyType.ESCALATE: NarrativeStrategy(
        type=StrategyType.ESCALATE,
        description="Continuously raise the stakes",
        guidance=(
            "Each scene should present a higher-stakes version of the conflict. "
            "What begins personal becomes universal. "
            "The final confrontation should feel both inevitable and overwhelming."
        ),
        suggested_moods=["tense", "epic", "mysterious"],
    ),
    StrategyType.RESOLVE: NarrativeStrategy(
        type=StrategyType.RESOLVE,
        description="Bring closure and healing to accumulated tension",
        guidance=(
            "Allow characters to finally say what they couldn't. "
            "Address unresolved threads from earlier. "
            "Ending should feel earned, not rushed."
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
