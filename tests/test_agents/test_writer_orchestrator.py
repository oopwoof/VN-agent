"""Tests for vn_agent.agents.writer_orchestrator (Phase 13-2 Step 4b-2).

Pure functions: group_scenes_by_chapter + compute_waves. No LLM, no I/O.
"""
from __future__ import annotations

from vn_agent.agents.writer_orchestrator import (
    compute_waves,
    group_scenes_by_chapter,
)
from vn_agent.schema.script import (
    Chapter,
    Scene,
    SceneContextRef,
    VNScript,
)


def _scene(sid: str, deps: list[tuple[str, str]] | None = None) -> Scene:
    """Deps as [(ref_type, ref_id), ...] for brevity."""
    refs: list[SceneContextRef] = []
    for ref_type, ref_id in deps or []:
        refs.append(SceneContextRef(
            ref_type=ref_type, ref_id=ref_id,
            link_type="callback", reason="test",
        ))
    return Scene(
        id=sid, title=sid.upper(), description=f"scene {sid}",
        background_id=f"bg_{sid}", characters_present=["alice"],
        context_deps=refs,
    )


def _script(scenes: list[Scene], chapters: list[Chapter] | None = None) -> VNScript:
    return VNScript(
        title="T", description="d", theme="th",
        start_scene_id=scenes[0].id if scenes else "",
        scenes=scenes,
        world_variables=[],
        chapters=chapters or [],
    )


# ---------------------------------------------------------------------------
# group_scenes_by_chapter
# ---------------------------------------------------------------------------


class TestGroupScenesByChapter:
    def test_no_chapters_single_bucket(self):
        """Short demos without chapter declarations become one bucket."""
        scenes = [_scene(f"s{i:02d}") for i in range(6)]
        groups = group_scenes_by_chapter(_script(scenes))
        assert len(groups) == 1
        assert [s.id for s in groups[0]] == [s.id for s in scenes]

    def test_chapters_split_in_declared_order(self):
        scenes = [_scene(f"s{i:02d}") for i in range(6)]
        chapters = [
            Chapter(chapter_id="ch01", scene_ids=["s00", "s01", "s02"]),
            Chapter(chapter_id="ch02", scene_ids=["s03", "s04", "s05"]),
        ]
        groups = group_scenes_by_chapter(_script(scenes, chapters))
        assert len(groups) == 2
        assert [s.id for s in groups[0]] == ["s00", "s01", "s02"]
        assert [s.id for s in groups[1]] == ["s03", "s04", "s05"]

    def test_orphan_scene_id_in_chapter_silently_skipped(self):
        """Chapter refers to a scene_id that doesn't exist; skipped."""
        scenes = [_scene("s00"), _scene("s01")]
        chapters = [
            Chapter(chapter_id="ch01", scene_ids=["s00", "s99_missing", "s01"]),
        ]
        groups = group_scenes_by_chapter(_script(scenes, chapters))
        assert len(groups) == 1
        assert [s.id for s in groups[0]] == ["s00", "s01"]

    def test_scene_not_in_any_chapter_appended_as_trailing_bucket(self):
        """Defensive: a scene not claimed by any chapter is not dropped."""
        scenes = [_scene("s00"), _scene("s01"), _scene("s02_unclaimed")]
        chapters = [Chapter(chapter_id="ch01", scene_ids=["s00", "s01"])]
        groups = group_scenes_by_chapter(_script(scenes, chapters))
        assert len(groups) == 2
        assert [s.id for s in groups[0]] == ["s00", "s01"]
        assert [s.id for s in groups[1]] == ["s02_unclaimed"]


# ---------------------------------------------------------------------------
# compute_waves
# ---------------------------------------------------------------------------


class TestComputeWaves:
    def test_empty_chapter_returns_empty(self):
        assert compute_waves([]) == []

    def test_no_deps_all_in_wave_0(self):
        """Short-demo pattern: Director didn't declare context_deps → all
        scenes can run concurrently in wave 0."""
        scenes = [_scene(f"s{i:02d}") for i in range(5)]
        waves = compute_waves(scenes)
        assert len(waves) == 1
        assert [s.id for s in waves[0]] == [s.id for s in scenes]

    def test_linear_chain_n_waves(self):
        """Each scene depends on its predecessor → N waves of 1 scene each."""
        s00 = _scene("s00")
        s01 = _scene("s01", [("scene", "s00")])
        s02 = _scene("s02", [("scene", "s01")])
        s03 = _scene("s03", [("scene", "s02")])
        waves = compute_waves([s00, s01, s02, s03])
        assert [[s.id for s in w] for w in waves] == [["s00"], ["s01"], ["s02"], ["s03"]]

    def test_diamond_dag_three_waves(self):
        """s00 → {s01, s02} → s03.

        Wave 0: s00
        Wave 1: s01, s02 (both depend only on s00)
        Wave 2: s03 (depends on both s01 and s02)
        """
        s00 = _scene("s00")
        s01 = _scene("s01", [("scene", "s00")])
        s02 = _scene("s02", [("scene", "s00")])
        s03 = _scene("s03", [("scene", "s01"), ("scene", "s02")])
        waves = compute_waves([s00, s01, s02, s03])
        assert len(waves) == 3
        assert [s.id for s in waves[0]] == ["s00"]
        assert sorted(s.id for s in waves[1]) == ["s01", "s02"]
        assert [s.id for s in waves[2]] == ["s03"]

    def test_cross_chapter_deps_ignored(self):
        """Dep to a scene NOT in the current chapter is silently satisfied
        (chapter barrier handles it). Such scenes still go in wave 0."""
        s10 = _scene("s10", [("scene", "s05_in_prior_chapter")])
        s11 = _scene("s11", [("scene", "s10")])
        waves = compute_waves([s10, s11])
        assert [s.id for s in waves[0]] == ["s10"]
        assert [s.id for s in waves[1]] == ["s11"]

    def test_non_scene_deps_ignored(self):
        """context_deps can refer to character_arcs / world_vars / motifs —
        wave calc only cares about ref_type='scene'."""
        scenes = [
            _scene("s00"),
            Scene(
                id="s01", title="S01", description="x",
                background_id="bg", characters_present=["alice"],
                context_deps=[
                    SceneContextRef(
                        ref_type="character_arc", ref_id="alice",
                        link_type="arc_beat", reason="r",
                    ),
                    SceneContextRef(
                        ref_type="world_var", ref_id="flag",
                        link_type="state_dependency", reason="r",
                    ),
                ],
            ),
        ]
        waves = compute_waves(scenes)
        # s01 has no SCENE deps → wave 0 with s00
        assert len(waves) == 1
        assert sorted(s.id for s in waves[0]) == ["s00", "s01"]

    def test_within_wave_deterministic_order(self):
        """Within a wave, order follows input list position — for reproducible
        debugging / parallel-vs-sequential comparison."""
        scenes = [_scene(f"s{i:02d}") for i in range(3)]
        # All in wave 0; order should match input order.
        waves = compute_waves(scenes)
        assert [s.id for s in waves[0]] == ["s00", "s01", "s02"]

    def test_cycle_defensive_fallback_no_deadlock(self):
        """If Director somehow produced a cycle, compute_waves should NOT
        deadlock. Remaining scenes flush as final wave with a warning."""
        s00 = _scene("s00", [("scene", "s01")])
        s01 = _scene("s01", [("scene", "s00")])
        waves = compute_waves([s00, s01])
        # One wave, both scenes flushed together (after cycle detection)
        assert len(waves) == 1
        assert sorted(s.id for s in waves[0]) == ["s00", "s01"]
