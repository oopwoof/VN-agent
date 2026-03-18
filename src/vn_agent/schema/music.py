"""Music-related schema models."""
from enum import Enum
from pydantic import BaseModel, Field


class Mood(str, Enum):
    PEACEFUL = "peaceful"
    ROMANTIC = "romantic"
    TENSE = "tense"
    MELANCHOLIC = "melancholic"
    JOYFUL = "joyful"
    MYSTERIOUS = "mysterious"
    EPIC = "epic"
    NEUTRAL = "neutral"


class MusicCue(BaseModel):
    mood: Mood = Field(description="Emotional mood of the scene")
    description: str = Field(description="Description of desired music, e.g. 'soft piano, rainy day feeling'")
    track_id: str | None = Field(default=None, description="Track ID from music library or generated track")
    file_path: str | None = Field(default=None, description="Relative path to audio file in Ren'Py project")
    fade_in: float = Field(default=1.0, description="Fade in duration in seconds")
    fade_out: float = Field(default=1.0, description="Fade out duration in seconds")
    volume: float = Field(default=0.7, ge=0.0, le=1.0, description="Volume level 0.0-1.0")
    loop: bool = Field(default=True, description="Whether the track loops")
