"""Character-related schema models."""
from pydantic import BaseModel, Field


class EmotionSprite(BaseModel):
    emotion: str = Field(description="Emotion name, e.g. 'happy', 'sad', 'surprised'")
    image_id: str = Field(description="Identifier for this sprite image")
    file_path: str | None = Field(default=None, description="Path to generated sprite image")
    generation_prompt: str | None = Field(default=None, description="Prompt used to generate this sprite")


class VisualProfile(BaseModel):
    """Anchors visual consistency across scenes."""
    art_style: str = Field(description="Art style description, e.g. 'anime style, soft watercolor'")
    appearance: str = Field(description="Detailed physical description for image generation consistency")
    default_outfit: str = Field(description="Default clothing description")
    sprites: list[EmotionSprite] = Field(default_factory=list)


class CharacterProfile(BaseModel):
    id: str = Field(description="Unique identifier, used as Ren'Py variable name")
    name: str = Field(description="Display name shown in dialogue")
    color: str = Field(default="#ffffff", description="Name color in Ren'Py dialogue box (hex)")
    personality: str = Field(description="Character personality traits")
    background: str = Field(description="Character backstory and motivation")
    role: str = Field(description="Role in the story, e.g. 'protagonist', 'love interest', 'antagonist'")
    visual: VisualProfile | None = Field(default=None, description="Visual design, filled by CharacterDesigner")
    # Sprint 9-1 (immutability constitution): per-attribute lock scores.
    # Higher score = more inviolable. DialogueReviewer (Sprint 9-5) fails
    # scripts where Writer dialogue contradicts a high-score attribute.
    # Keys are attribute names ('name', 'role', 'personality', ...);
    # values in [0, 10]. Missing key = 0 (not protected).
    # Defaults protect the two attributes a Writer must never change.
    immutability_score: dict[str, int] = Field(
        default_factory=lambda: {"name": 10, "role": 10, "background": 6, "personality": 4},
        description="{attribute_name: lock_score 0-10}. 10 = Reviewer FAIL on "
                    "contradiction. 0 = free for Writer to evolve.",
    )
