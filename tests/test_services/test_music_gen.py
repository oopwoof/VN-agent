"""Tests for music generation service."""
from unittest.mock import patch

import pytest

from vn_agent.schema.music import Mood, MusicCue
from vn_agent.services.music_gen import MusicNotFoundError, _resolve_from_library

SAMPLE_LIBRARY = {
    "tracks": {
        "peaceful": [
            {"id": "peaceful_morning", "title": "Peaceful Morning", "filename": "peaceful_morning.ogg"},
        ],
        "tense": [
            {"id": "tense_confrontation", "title": "Tense Confrontation", "filename": "tense_confrontation.ogg"},
        ],
        "neutral": [
            {"id": "ambient_space", "title": "Ambient Space", "filename": "ambient_space.ogg"},
        ],
    }
}


class TestLibraryResolution:
    def test_resolves_known_mood(self):
        cue = MusicCue(mood=Mood.PEACEFUL, description="soft piano")
        with patch("vn_agent.services.music_gen.get_music_library", return_value=SAMPLE_LIBRARY):
            resolved = _resolve_from_library(cue)
        assert resolved.track_id == "peaceful_morning"
        assert resolved.file_path == "audio/bgm/peaceful_morning.ogg"

    def test_fallback_to_neutral(self):
        cue = MusicCue(mood=Mood.EPIC, description="epic music")
        with patch("vn_agent.services.music_gen.get_music_library", return_value=SAMPLE_LIBRARY):
            resolved = _resolve_from_library(cue)
        assert resolved.track_id == "ambient_space"

    def test_raises_when_no_tracks(self):
        cue = MusicCue(mood=Mood.JOYFUL, description="happy")
        empty_library = {"tracks": {}}
        with patch("vn_agent.services.music_gen.get_music_library", return_value=empty_library):
            with pytest.raises(MusicNotFoundError):
                _resolve_from_library(cue)

    def test_preserves_cue_properties(self):
        cue = MusicCue(
            mood=Mood.TENSE,
            description="test",
            fade_in=2.0,
            fade_out=3.0,
            volume=0.5,
        )
        with patch("vn_agent.services.music_gen.get_music_library", return_value=SAMPLE_LIBRARY):
            resolved = _resolve_from_library(cue)
        assert resolved.fade_in == 2.0
        assert resolved.fade_out == 3.0
        assert resolved.volume == 0.5
