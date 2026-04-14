"""Tests for the Reviewer agent structural checks and Director merge logic."""
from vn_agent.agents.director import _merge_outline_details
from vn_agent.agents.reviewer import (
    _check_branch_divergence,
    _find_reachable_scenes,
    _jaccard,
    _parse_scores,
    _structural_check,
    _tokenize_for_jaccard,
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


class TestThresholdBasedVerdict:
    """Parsed rubric scores + configurable threshold override the LLM's stated verdict."""

    @staticmethod
    def _decide(content: str, threshold: float = 3.5) -> bool:
        """Replicate _quality_check's score-authoritative decision."""
        stripped = content.strip()
        first_line = stripped.split("\n", 1)[0].strip().upper()
        scores = _parse_scores(stripped)
        has_issues = "\n-" in stripped or "\n*" in stripped or "\n1." in stripped
        llm_said_pass = first_line.startswith("PASS") and not has_issues
        if scores and "avg" in scores:
            return scores["avg"] >= threshold
        return llm_said_pass

    def test_scores_override_incorrect_llm_pass(self):
        # LLM says PASS but rubric average is 2.4 → FAIL
        content = "PASS\nScores: coherence=2 voice=3 arc=2 branches=3 pacing=2"
        assert self._decide(content) is False

    def test_scores_override_incorrect_llm_fail(self):
        # LLM says FAIL but rubric average is 4.2 → PASS
        content = "FAIL\nScores: coherence=4 voice=5 arc=4 branches=4 pacing=4"
        assert self._decide(content) is True

    def test_scores_missing_falls_back_to_llm_string(self):
        # No numeric scores parseable → trust the LLM's string verdict
        assert self._decide("PASS") is True
        assert self._decide("FAIL\n- issue 1") is False

    def test_exactly_at_threshold_passes(self):
        content = "PASS\ncoherence=4 voice=3 arc=4 branches=3 pacing=3.5"
        scores = _parse_scores(content)
        assert scores is not None and scores["avg"] == 3.5
        assert self._decide(content, threshold=3.5) is True

    def test_just_below_threshold_fails(self):
        content = "PASS\ncoherence=3 voice=3 arc=3 branches=4 pacing=4"
        scores = _parse_scores(content)
        assert scores is not None and scores["avg"] == 3.4
        assert self._decide(content, threshold=3.5) is False

    def test_threshold_is_configurable(self):
        # avg=3.4 — fails at 3.5, passes at 3.0
        content = "PASS\ncoherence=3 voice=3 arc=3 branches=4 pacing=4"
        assert self._decide(content, threshold=3.5) is False
        assert self._decide(content, threshold=3.0) is True


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


# ── Sprint 6-7: Branch Divergence Tests ─────────────────────────────────────

def _dl(text: str, emotion: str = "neutral", character_id: str | None = None) -> DialogueLine:
    return DialogueLine(character_id=character_id, text=text, emotion=emotion)


def _divergence_script(scenes: list[Scene]) -> VNScript:
    return VNScript(
        title="T", description="", theme="test",
        start_scene_id=scenes[0].id if scenes else "",
        scenes=scenes, characters=[],
    )


class TestJaccardHelpers:
    def test_tokenize_drops_punctuation(self):
        assert _tokenize_for_jaccard("Hello, world!") == {"hello", "world"}

    def test_tokenize_drops_short_words(self):
        # words <= 2 chars dropped (reduces noise from "a", "of", "to")
        tokens = _tokenize_for_jaccard("a big cat is on the mat")
        assert "big" in tokens
        assert "cat" in tokens
        assert "a" not in tokens
        assert "is" not in tokens

    def test_jaccard_identical(self):
        s = {"a", "b", "c"}
        assert _jaccard(s, s) == 1.0

    def test_jaccard_disjoint(self):
        assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0

    def test_jaccard_empty_both(self):
        assert _jaccard(set(), set()) == 1.0

    def test_jaccard_one_empty(self):
        assert _jaccard({"a"}, set()) == 0.0


class TestBranchDivergence:
    def test_no_branches_no_warnings(self):
        script = _divergence_script([
            Scene(id="a", title="A", description="", background_id="bg",
                  dialogue=[_dl("Hello there"), _dl("Goodbye friend")], next_scene_id="b"),
            Scene(id="b", title="B", description="", background_id="bg"),
        ])
        assert _check_branch_divergence(script) == []

    def test_divergent_branches_pass(self):
        # Branches lead to genuinely different content — no warning
        script = _divergence_script([
            Scene(id="a", title="A", description="", background_id="bg",
                  dialogue=[_dl("Start")],
                  branches=[
                      BranchOption(text="path1", next_scene_id="b"),
                      BranchOption(text="path2", next_scene_id="c"),
                  ]),
            Scene(id="b", title="B", description="", background_id="bg",
                  dialogue=[_dl("Walking through sunny meadows with flowers blooming"),
                            _dl("The birds sang loudly above")],
                  characters_present=["alice"]),
            Scene(id="c", title="C", description="", background_id="bg",
                  dialogue=[_dl("Creeping through dark caverns in utter silence"),
                            _dl("Something moved in the shadows ahead")],
                  characters_present=["bob"]),
        ])
        warnings = _check_branch_divergence(script)
        assert warnings == []

    def test_cosmetic_branches_flagged(self):
        # Both branches lead to scenes with IDENTICAL dialogue, characters, emotions
        same_dialogue = [_dl("The exact same words"), _dl("Repeated verbatim")]
        script = _divergence_script([
            Scene(id="a", title="A", description="", background_id="bg",
                  branches=[
                      BranchOption(text="accept", next_scene_id="b"),
                      BranchOption(text="decline", next_scene_id="c"),
                  ]),
            Scene(id="b", title="B", description="", background_id="bg",
                  dialogue=same_dialogue, characters_present=["alice"]),
            Scene(id="c", title="C", description="", background_id="bg",
                  dialogue=same_dialogue, characters_present=["alice"]),
        ])
        warnings = _check_branch_divergence(script)
        assert len(warnings) == 1
        assert "cosmetic" in warnings[0]
        assert "'a'" in warnings[0]

    def test_partial_overlap_passes(self):
        # Branches share some tokens but have different enough content
        script = _divergence_script([
            Scene(id="a", title="A", description="", background_id="bg",
                  branches=[
                      BranchOption(text="x", next_scene_id="b"),
                      BranchOption(text="y", next_scene_id="c"),
                  ]),
            Scene(id="b", title="B", description="", background_id="bg",
                  dialogue=[_dl("happy celebration party everyone laughing music dancing")]),
            Scene(id="c", title="C", description="", background_id="bg",
                  dialogue=[_dl("quiet funeral mourning everyone silent tears falling")]),
        ])
        # Only "everyone" overlaps; Jaccard well below threshold
        warnings = _check_branch_divergence(script)
        assert warnings == []

    def test_same_content_different_characters_passes(self):
        # Jaccard high BUT characters differ → not flagged
        script = _divergence_script([
            Scene(id="a", title="A", description="", background_id="bg",
                  branches=[
                      BranchOption(text="x", next_scene_id="b"),
                      BranchOption(text="y", next_scene_id="c"),
                  ]),
            Scene(id="b", title="B", description="", background_id="bg",
                  dialogue=[_dl("Generic dialogue with common words")],
                  characters_present=["alice"]),
            Scene(id="c", title="C", description="", background_id="bg",
                  dialogue=[_dl("Generic dialogue with common words")],
                  characters_present=["bob"]),  # different character
        ])
        warnings = _check_branch_divergence(script)
        assert warnings == []  # character difference saves it


# ── Sprint 9-7: state type/enum validation via _mechanical_check ─────────
class TestWorldStateValidation:
    """_mechanical_check rejects state writes/requires that violate declared types."""

    def _make_script_with_var(self, var, scene_extra=None):
        from vn_agent.schema.script import DialogueLine, Scene, VNScript
        scene_kwargs = dict(
            id="s1", title="s1", description="", background_id="bg",
            characters_present=["alice"],
            dialogue=[DialogueLine(character_id="alice", text="Hi.")],
            next_scene_id=None,
        )
        if scene_extra:
            scene_kwargs.update(scene_extra)
        return VNScript(
            title="T", description="", theme="", start_scene_id="s1",
            scenes=[Scene(**scene_kwargs)],
            world_variables=[var],
        )

    def _run(self, script, characters=None):
        from vn_agent.agents.reviewer import _mechanical_check

        class _FakeSettings:
            min_dialogue_lines = 1
            max_dialogue_lines = 20
        return _mechanical_check(script, characters or {"alice": _MkChar()}, _FakeSettings())

    def test_bool_write_accepts_bool(self):
        from vn_agent.schema.script import WorldVariable
        wv = WorldVariable(name="has_key", type="bool", initial_value=False, description="x")
        script = self._make_script_with_var(wv, {"state_writes": {"has_key": True}})
        r = self._run(script)
        assert r.passed

    def test_bool_write_rejects_int(self):
        from vn_agent.schema.script import WorldVariable
        wv = WorldVariable(name="has_key", type="bool", initial_value=False, description="x")
        script = self._make_script_with_var(wv, {"state_writes": {"has_key": 1}})
        r = self._run(script)
        assert not r.passed
        assert any("type mismatch" in i for i in r.issues)

    def test_int_write_accepts_int(self):
        from vn_agent.schema.script import WorldVariable
        wv = WorldVariable(name="affinity", type="int", initial_value=3, description="x")
        script = self._make_script_with_var(wv, {"state_writes": {"affinity": 7}})
        r = self._run(script)
        assert r.passed

    def test_int_write_rejects_bool(self):
        """bool technically is int in Python — catch as a type contract violation."""
        from vn_agent.schema.script import WorldVariable
        wv = WorldVariable(name="affinity", type="int", initial_value=3, description="x")
        script = self._make_script_with_var(wv, {"state_writes": {"affinity": True}})
        r = self._run(script)
        assert not r.passed
        assert any("got bool" in i for i in r.issues)

    def test_enum_write_accepts_member(self):
        from vn_agent.schema.script import WorldVariable
        wv = WorldVariable(
            name="weather", type="enum", initial_value="clear",
            description="x", enum_values=["clear", "storm", "fog"],
        )
        script = self._make_script_with_var(wv, {"state_writes": {"weather": "storm"}})
        r = self._run(script)
        assert r.passed

    def test_enum_write_rejects_non_member(self):
        from vn_agent.schema.script import WorldVariable
        wv = WorldVariable(
            name="weather", type="enum", initial_value="clear",
            description="x", enum_values=["clear", "storm", "fog"],
        )
        script = self._make_script_with_var(wv, {"state_writes": {"weather": "rainbow"}})
        r = self._run(script)
        assert not r.passed
        assert any("not in enum_values" in i for i in r.issues)

    def test_undeclared_state_read_flagged(self):
        from vn_agent.schema.script import WorldVariable
        wv = WorldVariable(name="affinity", type="int", initial_value=3, description="x")
        script = self._make_script_with_var(wv, {"state_reads": ["nonexistent"]})
        r = self._run(script)
        assert not r.passed
        assert any("undeclared" in i for i in r.issues)

    def test_no_world_vars_no_checks(self):
        """Scripts without world_variables pass trivially."""
        from vn_agent.schema.script import DialogueLine, Scene, VNScript
        script = VNScript(
            title="T", description="", theme="", start_scene_id="s1",
            scenes=[Scene(
                id="s1", title="s", description="", background_id="bg",
                characters_present=["alice"],
                dialogue=[DialogueLine(character_id="alice", text="Hi.")],
                next_scene_id=None,
            )],
        )
        r = self._run(script)
        assert r.passed


class _MkChar:
    """Minimal CharacterProfile stand-in for mechanical check tests."""
    def __init__(self):
        self.id = "alice"
        self.name = "Alice"
        self.role = "protagonist"
        self.personality = "curious"
        self.background = "young"
        self.immutability_score = {"name": 10, "role": 10}
