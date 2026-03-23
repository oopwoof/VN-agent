"""Core VN script schema models."""
from pydantic import BaseModel, Field

from .music import MusicCue


class DialogueLine(BaseModel):
    character_id: str | None = Field(default=None, description="Speaker ID, None for narration")
    text: str = Field(description="Dialogue or narration text")
    emotion: str = Field(default="neutral", description="Speaker emotion for this line")


class BranchOption(BaseModel):
    text: str = Field(description="Choice text shown to player")
    next_scene_id: str = Field(description="Scene to jump to when this option is chosen")
    condition: str | None = Field(default=None, description="Optional condition expression")


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


class VNScript(BaseModel):
    title: str = Field(description="Visual novel title")
    description: str = Field(description="Story premise and overview")
    theme: str = Field(description="Original theme/prompt from user")
    start_scene_id: str = Field(description="ID of the first scene")
    scenes: list[Scene] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list, description="Character IDs referenced in this script")
    revision_count: int = Field(default=0, description="Number of revision rounds completed")
    revision_notes: list[str] = Field(default_factory=list, description="Feedback from each revision round")
