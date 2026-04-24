"""Phase 13-2 Step 4b (route 4): Writer parallel orchestration helpers.

Pure functions (no LLM, no async, no side effects) used by the parallel
Writer path to decide which scenes can run concurrently. Split from
writer.py so the topology decisions are testable in isolation.

Design:

  group_scenes_by_chapter(script)
    returns [[scene, ...], [scene, ...], ...]
    one bucket per chapter in declared order. Short-demo scripts with
    no chapters get a single bucket containing every scene.

  compute_waves(chapter_scenes)
    returns [[scene, ...], [scene, ...], ...]
    topological waves WITHIN one chapter, computed from scene.context_deps
    (ref_type="scene", same-chapter only). Wave 0 = no in-chapter deps;
    Wave N+1 = deps all satisfied by waves 0..N.

The parallel Writer path runs chapter-by-chapter (chapter barrier), and
within each chapter processes waves in order — each wave runs under
asyncio.Semaphore(writer_max_concurrent). Cross-chapter coordination
flows through the natural sequential chapter ordering; within-wave
peers coordinate through scene.thinking (computed upstream by
thinking_fanout + cross_ref_sync).
"""
from __future__ import annotations

import logging

from vn_agent.schema.script import Scene, VNScript

logger = logging.getLogger(__name__)


def group_scenes_by_chapter(script: VNScript) -> list[list[Scene]]:
    """Partition script.scenes into per-chapter buckets in declared order.

    Scripts without chapters (short demos, pre-Phase-13-1 artifacts) get
    a single bucket containing every scene — the parallel path treats
    the whole script as one chapter in that case.

    Defensive behaviors:
      - Scenes referenced by a chapter.scene_ids but absent from
        script.scenes are silently skipped (orphan id).
      - Scenes present in script.scenes but not claimed by any chapter
        become a final trailing bucket so they don't get dropped. This
        shouldn't happen under normal Director output, but a regression
        in chapter assignment should not silently lose scenes.
    """
    if not script.chapters:
        return [list(script.scenes)]

    scene_by_id: dict[str, Scene] = {s.id: s for s in script.scenes}
    groups: list[list[Scene]] = []
    covered: set[str] = set()
    for ch in script.chapters:
        bucket = [scene_by_id[sid] for sid in ch.scene_ids if sid in scene_by_id]
        if bucket:
            groups.append(bucket)
            covered.update(s.id for s in bucket)

    stragglers = [s for s in script.scenes if s.id not in covered]
    if stragglers:
        logger.warning(
            f"group_scenes_by_chapter: {len(stragglers)} scenes not claimed "
            f"by any chapter ({[s.id for s in stragglers]}); appending as "
            f"trailing bucket"
        )
        groups.append(stragglers)

    return groups


def compute_waves(chapter_scenes: list[Scene]) -> list[list[Scene]]:
    """Topological sort of chapter_scenes by intra-chapter context_deps.

    Each returned wave is a list of scenes that can run concurrently —
    none of them declare a scene dependency on another member of the
    same wave, and all their scene dependencies within this chapter are
    satisfied by prior waves.

    Cross-chapter context_deps (ref_id pointing outside chapter_scenes)
    are ignored here: the chapter barrier in the orchestrator already
    guarantees prior chapters finished before this chapter starts, so
    cross-chapter deps are satisfied by construction.

    Defensive fallback: if context_deps form a cycle (which should be
    impossible under Director's backward-only declaration discipline),
    the remaining scenes are flushed as a single final wave with a
    logged warning rather than deadlocking.

    Determinism: within each wave, scenes are ordered by their position
    in the input chapter_scenes list. This keeps parallel-path output
    comparable to sequential-path output for debugging.
    """
    if not chapter_scenes:
        return []

    ids_in_chapter: set[str] = {s.id for s in chapter_scenes}
    order_key: dict[str, int] = {s.id: i for i, s in enumerate(chapter_scenes)}
    deps: dict[str, set[str]] = {
        s.id: {
            d.ref_id for d in s.context_deps
            if d.ref_type == "scene" and d.ref_id in ids_in_chapter
        }
        for s in chapter_scenes
    }
    remaining: dict[str, Scene] = {s.id: s for s in chapter_scenes}
    waves: list[list[Scene]] = []

    while remaining:
        ready: list[Scene] = [
            s for sid, s in remaining.items()
            if not (deps[sid] & remaining.keys())
        ]
        if not ready:
            logger.warning(
                f"compute_waves: context_deps cycle among "
                f"{sorted(remaining.keys())}; flushing as final wave"
            )
            ready = list(remaining.values())
        ready.sort(key=lambda s: order_key[s.id])
        waves.append(ready)
        for s in ready:
            remaining.pop(s.id)

    return waves
