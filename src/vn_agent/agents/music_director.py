"""Music Director Agent: Analyzes scenes and assigns BGM tracks."""
from __future__ import annotations

import logging

from vn_agent.agents.state import AgentState
from vn_agent.schema.music import Mood
from vn_agent.schema.script import Scene, VNScript
from vn_agent.services.music_gen import resolve_music_cue

logger = logging.getLogger(__name__)


async def run_music_director(state: AgentState) -> dict:
    """MusicDirector node: assigns BGM tracks to all scenes."""
    script = state["vn_script"]
    if not script:
        return {}

    logger.info(f"MusicDirector: processing {len(script.scenes)} scenes")

    updated_scenes = _assign_music(script)
    updated_script = script.model_copy(update={"scenes": updated_scenes})

    return {"vn_script": updated_script}


def _assign_music(script: VNScript) -> list[Scene]:
    """
    Assign music tracks to scenes.
    Adjacent scenes with the same mood share a track (reduces repetition).
    """
    # Resolve music cues with track IDs
    prev_mood: Mood | None = None
    prev_track_id: str | None = None
    prev_file_path: str | None = None

    updated_scenes = []
    for scene in script.scenes:
        if scene.music is None:
            updated_scenes.append(scene)
            continue

        current_mood = scene.music.mood

        # Reuse previous track if same mood (no jarring transitions)
        if current_mood == prev_mood and prev_track_id:
            resolved_cue = scene.music.model_copy(update={
                "track_id": prev_track_id,
                "file_path": prev_file_path,
            })
            logger.debug(f"Scene {scene.id}: reusing track {prev_track_id} for mood {current_mood}")
        else:
            # Resolve new track
            try:
                resolved_cue = resolve_music_cue(scene.music)
                prev_mood = current_mood
                prev_track_id = resolved_cue.track_id
                prev_file_path = resolved_cue.file_path
                logger.info(f"Scene {scene.id}: assigned track {resolved_cue.track_id} ({current_mood})")
            except Exception as e:
                logger.warning(f"Scene {scene.id}: could not resolve music ({e}), keeping unresolved")
                resolved_cue = scene.music

        updated_scenes.append(scene.model_copy(update={"music": resolved_cue}))

    return updated_scenes
