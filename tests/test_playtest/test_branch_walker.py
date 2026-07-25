"""P4: branch_walker.walk_script — state-aware BFS over hand-built VNScript
objects (no fixture needed; these test the graph-traversal logic in
isolation, no LLM, no filesystem)."""
from __future__ import annotations

from vn_agent.playtest.branch_walker import walk_script
from vn_agent.schema.script import BranchOption, DialogueLine, Scene, VNScript, WorldVariable


def _scene(id: str, **kw) -> Scene:
    defaults = dict(title=id, description=id, background_id="bg_x")
    defaults.update(kw)
    return Scene(id=id, **defaults)


def test_linear_script_visits_every_scene_no_choice_nodes():
    script = VNScript(
        title="t", description="d", theme="th", start_scene_id="s1",
        scenes=[
            _scene("s1", next_scene_id="s2"),
            _scene("s2", next_scene_id="s3"),
            _scene("s3"),
        ],
    )
    plan = walk_script(script)
    assert plan.visited_scene_ids == ["s1", "s2", "s3"]
    assert plan.unreachable_scene_ids == []
    assert all(n.kind == "scene" for n in plan.nodes)
    assert plan.total_declared_branches == 0
    assert plan.reachable_branches == 0


def test_ungated_branch_both_targets_reachable():
    script = VNScript(
        title="t", description="d", theme="th", start_scene_id="s1",
        scenes=[
            _scene("s1", branches=[
                BranchOption(text="go A", next_scene_id="a"),
                BranchOption(text="go B", next_scene_id="b"),
            ]),
            _scene("a"),
            _scene("b"),
        ],
    )
    plan = walk_script(script)
    assert set(plan.visited_scene_ids) == {"s1", "a", "b"}
    assert plan.reachable_branches == 2
    assert plan.total_declared_branches == 2
    choice_node = next(n for n in plan.nodes if n.kind == "choice_menu")
    assert set(choice_node.choice_texts) == {"go A", "go B"}
    assert choice_node.locked_choice_texts == []


def test_gated_branch_met_by_earlier_state_write_is_reachable():
    script = VNScript(
        title="t", description="d", theme="th", start_scene_id="s1",
        world_variables=[WorldVariable(name="flag", type="bool", initial_value=False, description="d")],
        scenes=[
            _scene("s1", next_scene_id="s2", state_writes={"flag": True}),
            _scene("s2", branches=[
                BranchOption(text="locked path", next_scene_id="unlocked", requires={"flag": True}),
            ]),
            _scene("unlocked"),
        ],
    )
    plan = walk_script(script)
    assert "unlocked" in plan.visited_scene_ids
    assert plan.reachable_branches == 1
    choice_node = next(n for n in plan.nodes if n.kind == "choice_menu")
    assert choice_node.choice_texts == ["locked path"]
    assert choice_node.locked_choice_texts == []


def test_gated_branch_not_met_leaves_target_unreachable():
    script = VNScript(
        title="t", description="d", theme="th", start_scene_id="s1",
        world_variables=[WorldVariable(name="flag", type="bool", initial_value=False, description="d")],
        scenes=[
            _scene("s1", branches=[
                BranchOption(text="needs flag", next_scene_id="gated_target", requires={"flag": True}),
            ]),
            _scene("gated_target"),
        ],
    )
    plan = walk_script(script)
    assert "gated_target" not in plan.visited_scene_ids
    assert "gated_target" in plan.unreachable_scene_ids
    assert plan.reachable_branches == 0
    choice_node = next(n for n in plan.nodes if n.kind == "choice_menu")
    assert choice_node.choice_texts == []
    assert choice_node.locked_choice_texts == ["needs flag"]


def test_cyclic_graph_terminates_without_duplicate_nodes():
    script = VNScript(
        title="t", description="d", theme="th", start_scene_id="a",
        scenes=[
            _scene("a", next_scene_id="b"),
            _scene("b", next_scene_id="a"),  # cycle back
        ],
    )
    plan = walk_script(script)
    assert plan.visited_scene_ids == ["a", "b"]
    assert len(plan.nodes) == 2


def test_max_nodes_caps_long_linear_chain():
    scenes = [_scene(f"s{i}", next_scene_id=f"s{i + 1}" if i < 19 else None) for i in range(20)]
    script = VNScript(title="t", description="d", theme="th", start_scene_id="s0", scenes=scenes)
    plan = walk_script(script, max_nodes=5)
    assert len(plan.nodes) == 5
    assert len(plan.visited_scene_ids) == 5


def test_dialogue_excerpt_capped_at_three_lines():
    scene = _scene("s1", dialogue=[
        DialogueLine(character_id="alice", text=f"line {i}", emotion="neutral") for i in range(5)
    ])
    script = VNScript(title="t", description="d", theme="th", start_scene_id="s1", scenes=[scene])
    plan = walk_script(script)
    assert len(plan.nodes[0].dialogue_excerpt) == 3
    assert plan.nodes[0].dialogue_excerpt[0] == "alice (neutral): line 0"
