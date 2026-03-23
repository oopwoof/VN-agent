"""Tests for the Reviewer agent structural checks and Director merge logic."""
from vn_agent.agents.director import _merge_outline_details
from vn_agent.agents.reviewer import (
    _find_reachable_scenes,
    _structural_check,
    check_strategy_consistency,
)
from vn_agent.schema.script import BranchOption, DialogueLine, Scene, VNScript


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


class TestReviewerPassJudgement:
    """Tests for the improved PASS detection logic in _quality_check."""

    def _judge(self, content: str) -> bool:
        """Simulate the PASS judgement logic from reviewer.py."""
        stripped = content.strip()
        first_line = stripped.split("\n", 1)[0].strip().upper()
        has_issues = "\n-" in stripped or "\n*" in stripped or "\n1." in stripped
        return first_line.startswith("PASS") and not has_issues

    def test_reviewer_verbose_pass(self):
        """Verbose PASS responses like 'PASS - coherent and well-paced' should be PASS."""
        assert self._judge("PASS - the story is coherent and well-paced") is True

    def test_reviewer_simple_pass(self):
        assert self._judge("PASS") is True

    def test_reviewer_pass_with_issues(self):
        """PASS followed by bullet-point issues should be FAIL."""
        content = "PASS\n- but pacing is off\n- characters inconsistent"
        assert self._judge(content) is False

    def test_reviewer_fail_content(self):
        assert self._judge("The script has several issues:\n- Missing transitions") is False

    def test_reviewer_pass_numbered_issues(self):
        content = "PASS\n1. Scene transitions are abrupt"
        assert self._judge(content) is False


class TestMergeDropsInvalidBranches:
    def test_merge_drops_invalid_branches(self):
        """Step2 referencing nonexistent scene_id should be filtered out."""
        outline = {
            "scenes": [
                {"id": "s1", "title": "S1"},
                {"id": "s2", "title": "S2"},
            ]
        }
        details = {
            "scenes": [
                {
                    "id": "s1",
                    "next_scene_id": None,
                    "branches": [
                        {"text": "Go to S2", "next_scene_id": "s2"},
                        {"text": "Go to S99", "next_scene_id": "s99_nonexistent"},
                    ],
                },
                {
                    "id": "s2",
                    "next_scene_id": "s99_nonexistent",
                    "branches": [],
                },
            ]
        }
        result = _merge_outline_details(outline, details)
        s1 = result["scenes"][0]
        s2 = result["scenes"][1]
        # Invalid branch to s99 should be dropped
        assert len(s1["branches"]) == 1
        assert s1["branches"][0]["next_scene_id"] == "s2"
        # Invalid next_scene_id should be cleared
        assert s2["next_scene_id"] is None


class TestStrategyConsistency:
    def test_no_warning_when_keywords_match(self):
        script = VNScript(
            title="Test", description="", theme="test", start_scene_id="s1",
            scenes=[
                Scene(
                    id="s1", title="S1", description="", background_id="bg",
                    narrative_strategy="rupture",
                    dialogue=[
                        DialogueLine(character_id=None, text="A sudden shock breaks the silence", emotion="neutral"),
                        DialogueLine(character_id=None, text="Everything shattered in an instant", emotion="neutral"),
                        DialogueLine(character_id=None, text="The explosion rocked the room", emotion="neutral"),
                    ],
                ),
            ],
            characters=[],
        )
        warnings = check_strategy_consistency(script)
        assert len(warnings) == 0

    def test_warning_when_no_keywords_match(self):
        script = VNScript(
            title="Test", description="", theme="test", start_scene_id="s1",
            scenes=[
                Scene(
                    id="s1", title="S1", description="", background_id="bg",
                    narrative_strategy="rupture",
                    dialogue=[
                        DialogueLine(character_id=None, text="They chatted about the weather", emotion="neutral"),
                        DialogueLine(character_id=None, text="It was a calm afternoon", emotion="neutral"),
                        DialogueLine(character_id=None, text="Nothing happened", emotion="neutral"),
                    ],
                ),
            ],
            characters=[],
        )
        warnings = check_strategy_consistency(script)
        assert len(warnings) == 1
        assert "rupture" in warnings[0]

    def test_no_warning_for_short_dialogue(self):
        """Scenes with fewer than 3 lines are not checked."""
        script = VNScript(
            title="Test", description="", theme="test", start_scene_id="s1",
            scenes=[
                Scene(
                    id="s1", title="S1", description="", background_id="bg",
                    narrative_strategy="rupture",
                    dialogue=[
                        DialogueLine(character_id=None, text="Just one line", emotion="neutral"),
                    ],
                ),
            ],
            characters=[],
        )
        warnings = check_strategy_consistency(script)
        assert len(warnings) == 0

    def test_no_warning_when_strategy_is_none(self):
        script = VNScript(
            title="Test", description="", theme="test", start_scene_id="s1",
            scenes=[
                Scene(
                    id="s1", title="S1", description="", background_id="bg",
                    narrative_strategy=None,
                    dialogue=[
                        DialogueLine(character_id=None, text="Line 1", emotion="neutral"),
                        DialogueLine(character_id=None, text="Line 2", emotion="neutral"),
                        DialogueLine(character_id=None, text="Line 3", emotion="neutral"),
                    ],
                ),
            ],
            characters=[],
        )
        warnings = check_strategy_consistency(script)
        assert len(warnings) == 0


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
