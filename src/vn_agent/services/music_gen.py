"""Music acquisition: library lookup or Suno API generation."""
from __future__ import annotations

import logging
import random

from vn_agent.config import get_music_library, get_settings
from vn_agent.schema.music import Mood, MusicCue

logger = logging.getLogger(__name__)


class MusicNotFoundError(Exception):
    pass


def resolve_music_cue(cue: MusicCue) -> MusicCue:
    """
    Resolve a MusicCue by assigning track_id and file_path.
    Strategy is determined by settings.music_strategy.
    """
    settings = get_settings()
    strategy = settings.music_strategy

    if strategy == "library":
        return _resolve_from_library(cue)
    elif strategy == "suno":
        return _resolve_from_suno(cue)
    else:  # hybrid
        try:
            return _resolve_from_suno(cue)
        except Exception as e:
            logger.warning(f"Suno API failed ({e}), falling back to library")
            return _resolve_from_library(cue)


def _resolve_from_library(cue: MusicCue) -> MusicCue:
    """Pick a track from the local music library matching the mood."""
    library = get_music_library()
    tracks = library.get("tracks", {})
    mood_tracks = tracks.get(cue.mood.value, [])

    if not mood_tracks:
        # Fallback to neutral
        mood_tracks = tracks.get(Mood.NEUTRAL.value, [])

    if not mood_tracks:
        raise MusicNotFoundError(f"No tracks found for mood: {cue.mood}")

    track = random.choice(mood_tracks)

    return cue.model_copy(update={
        "track_id": track["id"],
        "file_path": f"audio/bgm/{track['filename']}",
    })


def _resolve_from_suno(cue: MusicCue) -> MusicCue:
    """Generate music via Suno API (placeholder - requires Suno API access)."""
    settings = get_settings()
    if not settings.suno_api_key:
        raise MusicNotFoundError("SUNO_API_KEY not configured")
    # TODO: Implement Suno API call when API is publicly available
    raise NotImplementedError("Suno API integration pending API availability")
