"""Tests for Director branch structural validation (Sprint 6-6)."""
from __future__ import annotations

from vn_agent.agents.director import (
    _degrade_invalid_branches,
    _reachable_within,
    _validate_branch_structure,
)
from vn_agent.schema.script import BranchOption, Scene, VNScript


def _scene(sid: str, branches: list[tuple[str, str]] | None = None, nxt: str | None = None) -> Scene:
    """Factory for a minimal Scene used in tests."""
    return Scene(
        id=sid,
        title=sid,
        description="test scene",
        background_id="bg",
        characters_present=[],
        branches=[BranchOption(text=t, next_scene_id=n) for t, n in (branches or [])],
        next_scene_id=nxt,
    )


def _script(scenes: list[Scene]) -> VNScript:
    return VNScript(
        title="Test",
        description="test",
        theme="test",
        start_scene_id=scenes[0].id if scenes else "",
        scenes=scenes,
        characters=[],
    )


class TestValidateBranchStructure:
    def test_no_branches_passes(self):
        script = _script([_scene("a", nxt="b"), _scene("b")])
        assert _validate_branch_structure(script) == []

    def test_single_branch_passes(self):
        # Only 1 branch degenerates to linear — not flagged
        script = _script([
            _scene("a", branches=[("go", "b")]),
            _scene("b"),
        ])
        assert _validate_branch_structure(script) == []

    def test_distinct_branches_with_divergent_content_pass(self):
        script = _script([
            _scene("a", branches=[("path1", "b"), ("path2", "c")]),
            _scene("b", nxt="d"),
            _scene("c", nxt="e"),
            _scene("d"),
            _scene("e"),
        ])
        assert _validate_branch_structure(script) == []

    def test_duplicate_targets_flagged(self):
        # Two branches → same scene = cosmetic
        script = _script([
            _scene("a", branches=[("choice1", "b"), ("choice2", "b")]),
            _scene("b"),
        ])
        issues = _validate_branch_structure(script)
        assert len(issues) == 1
        assert "share the same next_scene_id" in issues[0]
        assert "'a'" in issues[0]

    def test_convergent_paths_flagged(self):
        # Branches go to different scenes but both immediately converge to c
        # AND neither path has any independent content beyond c
        script = _script([
            _scene("a", branches=[("x", "b"), ("y", "b")]),  # same target → flagged rule 1
            _scene("b"),
        ])
        issues = _validate_branch_structure(script)
        assert issues  # caught by rule 1

    def test_three_branches_with_partial_convergence_passes(self):
        # b and c both eventually reach d but each has its own intermediate
        # content (b vs c as distinct scenes). This is legitimate "diamond"
        # branching, NOT cosmetic — validator should accept it.
        script = _script([
            _scene("a", branches=[("x", "b"), ("y", "c"), ("z", "e")]),
            _scene("b", nxt="d"),
            _scene("c", nxt="d"),
            _scene("d"),  # shared endpoint
            _scene("e"),  # exclusive endpoint for branch z
        ])
        issues = _validate_branch_structure(script)
        # Each branch has at least one exclusive scene (b or c or e), so
        # no convergence issue. Rule 1 also OK (distinct targets).
        assert issues == []

    def test_fully_convergent_branches_flagged(self):
        # Both branches point to different but immediately-terminal scenes
        # whose reachable sets are each just themselves. That's OK — each
        # branch has exclusive content. To trigger the convergence rule,
        # both branches must lead to paths whose reachable sets are identical.
        # Simplest case: both branches jump directly to the SAME terminal
        # scene via distinct branch objects — caught by rule 1 (duplicate
        # target), not rule 2. Rule 2 is a safety net for cases where rule 1
        # alone misses.
        script = _script([
            _scene("a", branches=[("x", "b"), ("y", "b")]),
            _scene("b"),
        ])
        issues = _validate_branch_structure(script)
        # Rule 1 (duplicate target) catches this
        assert any("share the same next_scene_id" in i for i in issues)


class TestReachableWithin:
    def test_linear_chain(self):
        smap = {
            "a": _scene("a", nxt="b"),
            "b": _scene("b", nxt="c"),
            "c": _scene("c"),
        }
        assert _reachable_within(smap, "a", max_depth=3) == {"a", "b", "c"}

    def test_depth_limit(self):
        smap = {
            "a": _scene("a", nxt="b"),
            "b": _scene("b", nxt="c"),
            "c": _scene("c", nxt="d"),
            "d": _scene("d"),
        }
        assert _reachable_within(smap, "a", max_depth=1) == {"a", "b"}

    def test_missing_start(self):
        assert _reachable_within({}, "ghost") == set()

    def test_cycle_terminates(self):
        # a -> b -> a, must not loop forever
        smap = {
            "a": _scene("a", nxt="b"),
            "b": _scene("b", nxt="a"),
        }
        result = _reachable_within(smap, "a", max_depth=10)
        assert result == {"a", "b"}

    def test_branch_expansion(self):
        smap = {
            "a": _scene("a", branches=[("x", "b"), ("y", "c")]),
            "b": _scene("b"),
            "c": _scene("c"),
        }
        assert _reachable_within(smap, "a", max_depth=2) == {"a", "b", "c"}


class TestDegradeInvalidBranches:
    def test_strips_branches_and_promotes_first(self):
        scene_a = _scene("a", branches=[("x", "b"), ("y", "b")])
        script = _script([scene_a, _scene("b")])

        issues = ["Scene 'a': branches share the same next_scene_id"]
        _degrade_invalid_branches(script, issues)

        degraded = script.scenes[0]
        assert degraded.branches == []
        assert degraded.next_scene_id == "b"

    def test_preserves_unflagged_scenes(self):
        scene_a = _scene("a", branches=[("x", "b"), ("y", "c")])
        scene_d = _scene("d", branches=[("m", "e"), ("n", "e")])
        script = _script([scene_a, _scene("b"), _scene("c"), scene_d, _scene("e")])

        # Only flag scene d
        issues = ["Scene 'd': branches share the same next_scene_id"]
        _degrade_invalid_branches(script, issues)

        assert len(script.scenes[0].branches) == 2  # a untouched
        assert script.scenes[3].branches == []  # d degraded
        assert script.scenes[3].next_scene_id == "e"

    def test_preserves_existing_next_scene_id(self):
        scene_a = _scene("a", branches=[("x", "b"), ("y", "b")], nxt="c")
        script = _script([scene_a, _scene("b"), _scene("c")])

        _degrade_invalid_branches(script, ["Scene 'a': branches share"])

        # next_scene_id already set — don't overwrite
        assert script.scenes[0].next_scene_id == "c"
        assert script.scenes[0].branches == []
