"""State-aware branch walker: BFS over a VNScript's scene graph, gating each
BranchOption by its `requires` dict against a per-path world_state — unlike
`agents/reviewer.py::_find_reachable_scenes` (which treats every declared
branch as reachable), this only enqueues a branch's target scene when its
`requires` guard is actually satisfied.

Known limitation (documented, not solved at M0): this carries ONE world_state
value per scene (whichever path visits it first), not full per-path state.
A scene reachable via two branches with contradictory state_writes is only
evaluated under the first-visiting path. Full combinatorial path-state
exploration is out of scope for M0.
"""
from __future__ import annotations

from vn_agent.playtest.schema import WalkNode, WalkPlan
from vn_agent.schema.script import BranchOption, Scene, VNScript

_DEFAULT_MAX_NODES = 60
_EXCERPT_LINES = 3


def _initial_world_state(script: VNScript) -> dict:
    return {v.name: v.initial_value for v in script.world_variables}


def _branch_gated_ok(branch: BranchOption, world_state: dict) -> bool:
    return all(world_state.get(k) == v for k, v in branch.requires.items())


def _dialogue_excerpt(scene: Scene, limit: int = _EXCERPT_LINES) -> list[str]:
    excerpt = []
    for line in scene.dialogue[:limit]:
        speaker = line.character_id or "Narration"
        excerpt.append(f"{speaker} ({line.emotion}): {line.text}")
    return excerpt


def walk_script(script: VNScript, *, max_nodes: int = _DEFAULT_MAX_NODES) -> WalkPlan:
    """Bounded forward BFS from `start_scene_id`. Produces one `WalkNode` per
    visited scene, plus one `choice_menu` WalkNode per scene that has
    branches (listing gated-in options as `choice_texts` and gated-off ones
    as `locked_choice_texts` — both on the same node, not as separate
    per-branch nodes)."""
    scene_map = {s.id: s for s in script.scenes}
    nodes: list[WalkNode] = []
    visited_scene_ids: list[str] = []
    seen_scene_ids: set[str] = set()
    total_declared_branches = sum(len(s.branches) for s in script.scenes)
    reachable_branches = 0

    queue: list[tuple[str, dict]] = [(script.start_scene_id, _initial_world_state(script))]

    while queue and len(nodes) < max_nodes:
        scene_id, world_state = queue.pop(0)
        if scene_id in seen_scene_ids or scene_id not in scene_map:
            continue
        seen_scene_ids.add(scene_id)
        visited_scene_ids.append(scene_id)
        scene = scene_map[scene_id]

        scene_world_state = dict(world_state)
        scene_world_state.update(scene.state_writes)

        nodes.append(WalkNode(
            node_id=scene_id,
            scene_id=scene_id,
            scene_title=scene.title,
            kind="scene",
            dialogue_excerpt=_dialogue_excerpt(scene),
            world_state=dict(scene_world_state),
        ))
        if len(nodes) >= max_nodes:
            break

        if scene.branches:
            choice_texts: list[str] = []
            locked_choice_texts: list[str] = []
            for branch in scene.branches:
                if _branch_gated_ok(branch, scene_world_state):
                    choice_texts.append(branch.text)
                    reachable_branches += 1
                    queue.append((branch.next_scene_id, dict(scene_world_state)))
                else:
                    locked_choice_texts.append(branch.text)
            nodes.append(WalkNode(
                node_id=f"{scene_id}::choice",
                scene_id=scene_id,
                scene_title=scene.title,
                kind="choice_menu",
                choice_texts=choice_texts,
                locked_choice_texts=locked_choice_texts,
                world_state=dict(scene_world_state),
            ))
        elif scene.next_scene_id:
            queue.append((scene.next_scene_id, dict(scene_world_state)))

    unreachable_scene_ids = sorted(set(scene_map.keys()) - seen_scene_ids)

    return WalkPlan(
        nodes=nodes,
        visited_scene_ids=visited_scene_ids,
        unreachable_scene_ids=unreachable_scene_ids,
        total_scenes=len(script.scenes),
        total_declared_branches=total_declared_branches,
        reachable_branches=reachable_branches,
    )
