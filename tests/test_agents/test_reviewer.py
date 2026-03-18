"""Tests for the Reviewer agent structural checks."""
import pytest
from vn_agent.schema.script import VNScript, Scene, DialogueLine, BranchOption
from vn_agent.agents.reviewer import _structural_check, _find_reachable_scenes


def make_valid_script() -> VNScript:
    return VNScript(
        title="Valid Story",
        description="A valid story",
        theme="test",
        start_scene_id="scene_1",
        scenes=[
            Scene(
                id="scene_1",
                title="Scene 1",
                description="First scene",
                background_id="bg_1",
                branches=[
                    BranchOption(text="Option A", next_scene_id="scene_2"),
                    BranchOption(text="Option B", next_scene_id="scene_3"),
                ],
            ),
            Scene(
                id="scene_2",
                title="Scene 2",
                description="Second scene",
                background_id="bg_2",
                next_scene_id=None,
            ),
            Scene(
                id="scene_3",
                title="Scene 3",
                description="Third scene",
                background_id="bg_3",
                next_scene_id=None,
            ),
        ],
        characters=["char_hero"],
    )


class TestStructuralCheck:
    def test_valid_script_passes(self):
        script = make_valid_script()
        result = _structural_check(script)
        assert result.passed

    def test_missing_start_scene(self):
        script = make_valid_script()
        script = script.model_copy(update={"start_scene_id": "nonexistent"})
        result = _structural_check(script)
        assert not result.passed
        assert "nonexistent" in result.feedback

    def test_broken_branch_reference(self):
        script = make_valid_script()
        bad_scenes = list(script.scenes)
        bad_scenes[0] = bad_scenes[0].model_copy(update={
            "branches": [
                BranchOption(text="Bad choice", next_scene_id="does_not_exist"),
            ]
        })
        script = script.model_copy(update={"scenes": bad_scenes})
        result = _structural_check(script)
        assert not result.passed
        assert "does_not_exist" in result.feedback

    def test_unreachable_scene_detected(self):
        script = make_valid_script()
        # Add orphan scene
        orphan = Scene(
            id="orphan_scene",
            title="Orphan",
            description="Nobody reaches here",
            background_id="bg_orphan",
            next_scene_id=None,
        )
        script = script.model_copy(update={"scenes": script.scenes + [orphan]})
        result = _structural_check(script)
        assert not result.passed
        assert "orphan_scene" in result.feedback

    def test_broken_next_scene_id(self):
        script = make_valid_script()
        bad_scenes = list(script.scenes)
        bad_scenes[1] = bad_scenes[1].model_copy(update={"next_scene_id": "bad_target"})
        script = script.model_copy(update={"scenes": bad_scenes})
        result = _structural_check(script)
        assert not result.passed


class TestReachability:
    def test_all_scenes_reachable(self):
        script = make_valid_script()
        reachable = _find_reachable_scenes(script)
        assert reachable == {"scene_1", "scene_2", "scene_3"}

    def test_orphan_not_reachable(self):
        script = make_valid_script()
        orphan = Scene(
            id="orphan",
            title="Orphan",
            description="Not reachable",
            background_id="bg",
        )
        script = script.model_copy(update={"scenes": script.scenes + [orphan]})
        reachable = _find_reachable_scenes(script)
        assert "orphan" not in reachable
        assert "scene_1" in reachable
