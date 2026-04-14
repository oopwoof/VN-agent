"""Core VN script schema models."""
from typing import Any, Literal

from pydantic import BaseModel, Field

from .music import MusicCue


class DialogueLine(BaseModel):
    character_id: str | None = Field(default=None, description="Speaker ID, None for narration")
    text: str = Field(description="Dialogue or narration text")
    emotion: str = Field(default="neutral", description="Speaker emotion for this line")


class WorldVariable(BaseModel):
    """Symbolic state variable declared by Director, read/written by scenes.

    Sprint 9-1: turns cross-scene continuity from "hope Sonnet remembers"
    into "hard symbolic state that survives long context." Flags, items,
    affinity, key-and-lock mechanics all live here. Ren'Py compiler
    (Sprint 9-4) emits `default var_name = initial_value` at init time
    and `$ var_name = value` inside scene labels where writes happen.
    """
    name: str = Field(description="Python-identifier-valid variable name")
    type: Literal["bool", "int", "string", "enum"] = Field(
        description="Type hint for the Ren'Py compiler and consistency check"
    )
    initial_value: Any = Field(
        description="Value at story start. Type must match `type` field."
    )
    description: str = Field(
        description="What this variable tracks, human-readable. Used by "
                    "StateOrchestrator (Sprint 9-6) to compile narrative constraints."
    )
    enum_values: list[str] | None = Field(
        default=None,
        description="For type='enum', the allowed values. Ignored otherwise.",
    )


class BranchOption(BaseModel):
    text: str = Field(description="Choice text shown to player")
    next_scene_id: str = Field(description="Scene to jump to when this option is chosen")
    condition: str | None = Field(default=None, description="Optional condition expression")
    # Sprint 9-1: symbolic guard on branch visibility. Rendered as Ren'Py
    # `if requires_key == value:` wrapping the menu option. Empty dict
    # (default) means "always visible."
    requires: dict[str, Any] = Field(
        default_factory=dict,
        description="Symbolic guard: {var_name: expected_value} — branch only "
                    "shown when all conditions match world_state.",
    )


class Scene(BaseModel):
    id: str = Field(description="Unique scene identifier, used as Ren'Py label")
    title: str = Field(description="Human-readable scene title")
    description: str = Field(description="Scene description for asset generation")
    background_id: str = Field(description="Background image identifier")
    music: MusicCue | None = Field(default=None, description="BGM for this scene")
    characters_present: list[str] = Field(default_factory=list, description="Character IDs present in scene")
    dialogue: list[DialogueLine] = Field(default_factory=list)
    branches: list[BranchOption] = Field(default_factory=list, description="Player choices at end of scene")
    next_scene_id: str | None = Field(default=None, description="Auto-advance to scene, None if branches exist")
    narrative_strategy: str | None = Field(default=None, description="Narrative strategy used in this scene")
    background_prompt: str | None = Field(default=None, description="Image generation prompt for background")
    # Transition cards for cross-scene coherence (Sprint 6-1)
    entry_context: str | None = Field(
        default=None,
        description="What the player just experienced before this scene — given to Writer for continuity",
    )
    exit_hook: str | None = Field(
        default=None,
        description="How this scene should end to set up the next one — given to Writer",
    )
    emotional_arc: str | None = Field(
        default=None,
        description="Emotional arc of this scene, e.g. 'warmth → anticipation'",
    )
    # Sprint 9-1: symbolic state I/O. state_reads declares which variables
    # this scene's dialogue depends on — Writer prompt injects their
    # current values. state_writes declares {var: new_value} that takes
    # effect when this scene ends (emitted as `$ var = value` in Ren'Py).
    state_reads: list[str] = Field(
        default_factory=list,
        description="Names of world_variables this scene's dialogue depends on. "
                    "StateOrchestrator pulls current values from world_state.",
    )
    state_writes: dict[str, Any] = Field(
        default_factory=dict,
        description="World-state updates this scene makes when it completes. "
                    "Ren'Py compiler emits `$ var_name = value` lines.",
    )


class VNScript(BaseModel):
    title: str = Field(description="Visual novel title")
    description: str = Field(description="Story premise and overview")
    theme: str = Field(description="Original theme/prompt from user")
    start_scene_id: str = Field(description="ID of the first scene")
    scenes: list[Scene] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list, description="Character IDs referenced in this script")
    revision_count: int = Field(default=0, description="Number of revision rounds completed")
    revision_notes: list[str] = Field(default_factory=list, description="Feedback from each revision round")
    # Sprint 9-1: Director declares world variables up front. Empty list
    # (default) = story has no symbolic state; all continuity is textual.
    # Having any entry here switches on Ren'Py compiler's state emission
    # (Sprint 9-4) and the StateOrchestrator pre-Writer node (Sprint 9-6).
    world_variables: list[WorldVariable] = Field(
        default_factory=list,
        description="Typed symbolic state declared by Director. "
                    "Read/written by scenes, enforced by DialogueReviewer, "
                    "emitted into Ren'Py $ var = value.",
    )
