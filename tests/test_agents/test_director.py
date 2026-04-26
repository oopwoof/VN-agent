"""Tests for Director branch structural validation (Sprint 6-6)."""
from __future__ import annotations

import pytest

from vn_agent.agents.director import (
    _build_from_plan,
    _degrade_invalid_branches,
    _merge_outline_details,
    _reachable_within,
    _validate_branch_structure,
)
from vn_agent.schema.script import (
    BranchOption,
    MacroReference,
    Scene,
    SceneBrief,
    VNScript,
)


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


# ---------------------------------------------------------------------------
# Phase 13-2 Step 1 (route 4): Director step1/step2 emit macro_reference +
# scene_brief; merge + build_from_plan hydrate them. Validation failures
# must log + drop, never crash the pipeline.
# ---------------------------------------------------------------------------


class TestDirectorStep1PromptContainsMacroReference:
    """Cheap static check — don't call LLM, just verify the user_prompt
    string mentions macro_reference so Director actually asks for it.

    Trick: we call _step1_outline via a stubbed ainvoke_llm that captures
    the prompt and raises. Works because large-model branch is the one
    we care about (small-model branch intentionally skips macro_reference).
    """

    def test_prompt_has_macro_reference_keyword(self, monkeypatch):
        import asyncio

        captured: dict = {}

        async def _fake_invoke(system, user, **kwargs):
            captured["system"] = system
            captured["user"] = user
            raise RuntimeError("stop before real LLM call")

        class _FakeSettings:
            llm_director_model = "claude-sonnet-4-6"  # not "haiku" → large branch
            llm_temperature = 0.7
            llm_max_tokens = 16000
            llm_provider = "anthropic"

        monkeypatch.setattr("vn_agent.agents.director.ainvoke_llm", _fake_invoke)

        from vn_agent.agents.director import _step1_outline

        try:
            asyncio.run(_step1_outline(
                "test theme", max_scenes=5, num_characters=3,
                output_dir=".", settings=_FakeSettings(),
            ))
        except RuntimeError:
            pass  # expected

        assert "user" in captured
        assert "macro_reference" in captured["user"]
        # Sanity: still mentions world_variables — we extended, not replaced
        assert "world_variables" in captured["user"]


class TestDirectorStep2PromptContainsSceneBrief:
    def test_prompt_has_scene_brief_keyword(self, monkeypatch):
        import asyncio

        captured: dict = {}

        async def _fake_invoke(system, user, **kwargs):
            captured["user"] = user
            raise RuntimeError("stop before real LLM call")

        class _FakeSettings:
            llm_director_model = "claude-sonnet-4-6"
            llm_temperature = 0.7
            llm_max_tokens = 16000
            llm_provider = "anthropic"

        monkeypatch.setattr("vn_agent.agents.director.ainvoke_llm", _fake_invoke)

        from vn_agent.agents.director import _step2_details

        outline = {
            "start_scene_id": "s1",
            "scenes": [{"id": "s1", "title": "Start", "description": "open"}],
            "world_variables": [],
        }
        try:
            asyncio.run(_step2_details(outline, output_dir=".", settings=_FakeSettings()))
        except RuntimeError:
            pass

        assert "scene_brief" in captured["user"]
        assert "context_deps" in captured["user"]  # regression guard


class TestMergeOutlineDetailsCarriesSceneBrief:
    def test_scene_brief_dict_preserved(self):
        outline = {
            "scenes": [{"id": "s1", "title": "A", "description": "x"}],
        }
        details = {
            "scenes": [{
                "id": "s1",
                "next_scene_id": None,
                "branches": [],
                "scene_brief": {
                    "beats": ["arrives", "pauses"],
                    "tension_target": "high",
                },
            }],
        }
        merged = _merge_outline_details(outline, details)
        assert merged["scenes"][0]["scene_brief"] == {
            "beats": ["arrives", "pauses"],
            "tension_target": "high",
        }

    def test_scene_brief_absent_becomes_none(self):
        """Director omitting scene_brief → merged gets None, not {}. Matters
        because _build_from_plan checks `if brief_raw:` — {} would truthily
        attempt to hydrate an empty SceneBrief."""
        outline = {"scenes": [{"id": "s1", "title": "A", "description": "x"}]}
        details = {"scenes": [{"id": "s1"}]}
        merged = _merge_outline_details(outline, details)
        assert merged["scenes"][0]["scene_brief"] is None


class TestBuildFromPlanHydratesMacroReference:
    def _minimal_plan(self, **extra):
        return {
            "title": "T",
            "description": "d",
            "start_scene_id": "s1",
            "scenes": [{"id": "s1", "title": "A", "description": "x", "background_id": "bg"}],
            "characters": [{"id": "c1", "name": "C", "role": "p"}],
            **extra,
        }

    def test_macro_reference_absent_yields_none(self):
        script, _ = _build_from_plan(self._minimal_plan(), theme="t")
        assert script.macro_reference is None

    def test_macro_reference_populated(self):
        script, _ = _build_from_plan(
            self._minimal_plan(macro_reference={
                "theme_thesis": "duty vs memory",
                "tone_register": "literary third-person-limited",
            }),
            theme="t",
        )
        assert isinstance(script.macro_reference, MacroReference)
        assert script.macro_reference.theme_thesis == "duty vs memory"

    def test_macro_reference_invalid_dropped_not_crashed(self, caplog):
        """Bad macro_reference (wrong type for a field) should log warn +
        drop, NOT crash the pipeline."""
        script, _ = _build_from_plan(
            self._minimal_plan(macro_reference={
                "theme_thesis": 123,  # wrong type — must be str
            }),
            theme="t",
        )
        assert script.macro_reference is None


class TestBuildFromPlanHydratesSceneBrief:
    def _plan_with_scene_brief(self, brief: dict | None):
        plan = {
            "title": "T",
            "description": "d",
            "start_scene_id": "s1",
            "scenes": [{
                "id": "s1", "title": "A", "description": "x",
                "background_id": "bg",
            }],
            "characters": [{"id": "c1", "name": "C", "role": "p"}],
        }
        if brief is not None:
            plan["scenes"][0]["scene_brief"] = brief
        return plan

    def test_scene_brief_absent_yields_none(self):
        script, _ = _build_from_plan(self._plan_with_scene_brief(None), theme="t")
        assert script.scenes[0].scene_brief is None

    def test_scene_brief_populated(self):
        script, _ = _build_from_plan(
            self._plan_with_scene_brief({
                "beats": ["arrival", "recognition"],
                "tension_target": "high",
            }),
            theme="t",
        )
        assert isinstance(script.scenes[0].scene_brief, SceneBrief)
        assert script.scenes[0].scene_brief.beats == ["arrival", "recognition"]
        assert script.scenes[0].scene_brief.tension_target == "high"

    def test_scene_brief_invalid_dropped(self):
        """Invalid tension_target ('extreme') → log warn, scene keeps
        scene_brief=None; scene itself still builds."""
        script, _ = _build_from_plan(
            self._plan_with_scene_brief({"tension_target": "extreme"}),
            theme="t",
        )
        assert script.scenes[0].scene_brief is None
        # Scene still valid:
        assert script.scenes[0].id == "s1"


# ---------------------------------------------------------------------------
# Phase 13-2 Step 4f: Director step2 Tool Use migration tests
#
# Schema tests for DirectorStep2SceneOutput / DirectorStep2Output, agent-
# level tests for _step2_details that verify:
#   - schema=DirectorStep2Output is passed to ainvoke_llm
#   - returns dict (.model_dump()) for downstream _merge_outline_details
#   - graceful degradation on ValidationError (with exc_info)
#   - silent-failure guards (scene shrinkage / empty / observability log)
#   - prompt no longer contains JSON example, but retains field-level
#     prose constraints (GPT-review hardening)
# ---------------------------------------------------------------------------


class TestDirectorStep2SceneOutputSchema:
    """Schema-level checks on DirectorStep2SceneOutput."""

    def test_id_required(self):
        from pydantic import ValidationError

        from vn_agent.schema.script import DirectorStep2SceneOutput

        with pytest.raises(ValidationError):
            DirectorStep2SceneOutput()  # type: ignore[call-arg]

    def test_minimal_only_id(self):
        from vn_agent.schema.script import DirectorStep2SceneOutput

        out = DirectorStep2SceneOutput(id="s1")
        assert out.id == "s1"
        assert out.next_scene_id is None
        assert out.branches == []
        assert out.music_mood == "neutral"
        assert out.music_description == ""
        assert out.emotional_arc is None
        assert out.entry_context is None
        assert out.exit_hook is None
        assert out.state_reads == []
        assert out.state_writes == {}
        assert out.context_deps == []
        assert out.scene_brief is None

    def test_full_shape_validates(self):
        from vn_agent.schema.script import (
            BranchOption,
            DirectorStep2SceneOutput,
            SceneBrief,
            SceneContextRef,
        )

        out = DirectorStep2SceneOutput(
            id="s1",
            next_scene_id="s2",
            branches=[BranchOption(text="go", next_scene_id="s2")],
            music_mood="tense",
            music_description="strings",
            emotional_arc="calm -> alarm",
            entry_context="prior scene ended at dusk",
            exit_hook="storm hits in the next scene",
            state_reads=["weather"],
            state_writes={"weather": "storm"},
            context_deps=[
                SceneContextRef(
                    ref_type="scene",
                    ref_id="s0",
                    link_type="callback",
                    reason="opening callback",
                )
            ],
            scene_brief=SceneBrief(
                beats=["a", "b", "c"],
                tension_target="high",
            ),
        )
        assert out.id == "s1"
        assert len(out.branches) == 1
        assert isinstance(out.branches[0], BranchOption)
        assert out.scene_brief is not None
        assert out.scene_brief.tension_target == "high"

    def test_branches_compose_branchoption_from_dict(self):
        """LLM Tool Use returns nested dicts; Pydantic must auto-construct
        BranchOption instances from them."""
        from vn_agent.schema.script import BranchOption, DirectorStep2SceneOutput

        out = DirectorStep2SceneOutput(
            id="s1",
            branches=[{"text": "go", "next_scene_id": "s2"}],  # type: ignore[list-item]
        )
        assert isinstance(out.branches[0], BranchOption)
        assert out.branches[0].text == "go"

    def test_context_deps_max_5_enforced(self):
        from pydantic import ValidationError

        from vn_agent.schema.script import DirectorStep2SceneOutput

        deps = [
            {
                "ref_type": "scene",
                "ref_id": f"s{i}",
                "link_type": "callback",
                "reason": "x",
            }
            for i in range(6)
        ]
        with pytest.raises(ValidationError):
            DirectorStep2SceneOutput(id="s1", context_deps=deps)  # type: ignore[arg-type]


class TestDirectorStep2OutputWrapper:
    """Schema-level checks on DirectorStep2Output."""

    def test_empty_scenes_ok(self):
        from vn_agent.schema.script import DirectorStep2Output

        out = DirectorStep2Output()
        assert out.scenes == []
        # Compatible with graceful-degradation path that returns this shape.

    def test_serialized_dump_has_merge_input_keys(self):
        """model_dump() must produce dicts that _merge_outline_details
        consumes — the 11-key contract."""
        from vn_agent.schema.script import DirectorStep2Output, DirectorStep2SceneOutput

        out = DirectorStep2Output(scenes=[DirectorStep2SceneOutput(id="s1")])
        dumped = out.model_dump()
        scene_keys = set(dumped["scenes"][0].keys())
        expected = {
            "id", "next_scene_id", "branches", "music_mood",
            "music_description", "emotional_arc", "entry_context",
            "exit_hook", "state_reads", "state_writes", "context_deps",
            "scene_brief",
        }
        assert expected.issubset(scene_keys)

    def test_reasoning_field_default_empty(self):
        """Phase 13-3 M0-2: reasoning field exists with default empty string
        so legacy code paths that don't fill it stay valid."""
        from vn_agent.schema.script import DirectorStep2Output

        out = DirectorStep2Output()
        assert out.reasoning == ""

    def test_reasoning_field_first_in_schema(self):
        """Phase 13-3 M0-2: reasoning MUST be the FIRST field in the schema —
        Anthropic Tool Use forces field-emission order to follow JSON Schema
        property order, so reasoning-first means model fills it first
        (restoring CoT before structural commit)."""
        from vn_agent.schema.script import DirectorStep2Output

        # Pydantic preserves declaration order in model_fields (Python 3.7+ ordered dicts)
        field_names = list(DirectorStep2Output.model_fields.keys())
        assert field_names[0] == "reasoning", (
            f"reasoning must be first field, got order: {field_names}"
        )

    def test_reasoning_field_max_length_800(self):
        """Bounded scratchpad — without a cap we'd reintroduce the
        token-budget tax we eliminated in Step 4f."""
        from pydantic import ValidationError

        from vn_agent.schema.script import DirectorStep2Output

        # 800 chars exact: pass
        DirectorStep2Output(reasoning="x" * 800)
        # 801 chars: ValidationError
        with pytest.raises(ValidationError):
            DirectorStep2Output(reasoning="x" * 801)


class _FakeStep2Settings:
    """Minimal settings stub used by the step2 agent-level tests below.
    `claude-sonnet-4` triggers the Tool Use branch (NOT the small-model
    raw-text fallback)."""
    llm_director_model = "claude-sonnet-4-6"
    llm_temperature = 0.2
    llm_max_tokens = 16000
    llm_provider = "anthropic"


class TestStep2ToolUseInvocation:
    """Verify _step2_details routes through Tool Use (Phase 13-2 Step 4f)."""

    def _outline(self, n_scenes: int = 3):
        return {
            "start_scene_id": "s1",
            "scenes": [
                {"id": f"s{i+1}", "title": f"S{i+1}", "description": "x"}
                for i in range(n_scenes)
            ],
            "world_variables": [],
        }

    def test_step2_passes_schema_kwarg(self, monkeypatch, tmp_path):
        import asyncio
        from unittest.mock import AsyncMock

        from vn_agent.agents.director import _step2_details
        from vn_agent.schema.script import DirectorStep2Output, DirectorStep2SceneOutput

        mock_invoke = AsyncMock(
            return_value=DirectorStep2Output(
                scenes=[DirectorStep2SceneOutput(id="s1"),
                        DirectorStep2SceneOutput(id="s2"),
                        DirectorStep2SceneOutput(id="s3")],
            )
        )
        monkeypatch.setattr("vn_agent.agents.director.ainvoke_llm", mock_invoke)

        asyncio.run(_step2_details(self._outline(3), str(tmp_path), _FakeStep2Settings()))

        assert mock_invoke.called
        kwargs = mock_invoke.call_args.kwargs
        assert kwargs["schema"] is DirectorStep2Output
        assert kwargs["caller"] == "director/step2"
        assert kwargs["cache_ttl"] == "1h"
        assert kwargs["force_cache"] is True

    def test_step2_returns_dict_from_pydantic(self, monkeypatch, tmp_path):
        import asyncio
        from unittest.mock import AsyncMock

        from vn_agent.agents.director import _step2_details
        from vn_agent.schema.script import DirectorStep2Output, DirectorStep2SceneOutput

        mock_invoke = AsyncMock(
            return_value=DirectorStep2Output(
                scenes=[
                    DirectorStep2SceneOutput(id="s1", music_mood="peaceful"),
                    DirectorStep2SceneOutput(id="s2", music_mood="tense"),
                    DirectorStep2SceneOutput(id="s3"),
                ]
            )
        )
        monkeypatch.setattr("vn_agent.agents.director.ainvoke_llm", mock_invoke)

        result = asyncio.run(
            _step2_details(self._outline(3), str(tmp_path), _FakeStep2Settings())
        )

        assert isinstance(result, dict)
        assert len(result["scenes"]) == 3
        assert result["scenes"][0]["id"] == "s1"
        assert result["scenes"][0]["music_mood"] == "peaceful"
        # Confirm key contract for _merge_outline_details
        for s in result["scenes"]:
            assert {"id", "next_scene_id", "branches", "scene_brief"}.issubset(s.keys())

    def test_step2_validation_error_returns_empty_with_exc_info(
        self, monkeypatch, tmp_path, caplog
    ):
        import asyncio
        import logging
        from unittest.mock import AsyncMock

        from pydantic import BaseModel, ValidationError

        from vn_agent.agents.director import _step2_details

        # Build a real ValidationError to mimic LangChain parser failure
        class _Stub(BaseModel):
            x: int

        try:
            _Stub(x="not an int")  # type: ignore[arg-type]
            verr: ValidationError | None = None
        except ValidationError as e:
            verr = e
        assert verr is not None

        mock_invoke = AsyncMock(side_effect=verr)
        monkeypatch.setattr("vn_agent.agents.director.ainvoke_llm", mock_invoke)

        with caplog.at_level(logging.ERROR, logger="vn_agent.agents.director"):
            result = asyncio.run(
                _step2_details(self._outline(2), str(tmp_path), _FakeStep2Settings())
            )

        assert result == {"scenes": []}
        # GPT review #5: do not silently swallow — exc_info must be logged.
        validation_records = [
            r for r in caplog.records
            if "structured output validation failed" in r.message
        ]
        assert validation_records, "Expected validation-failure error log"
        assert validation_records[0].exc_info is not None

    def test_step2_does_not_invoke_extract_json(self, monkeypatch, tmp_path):
        """Tool Use returns a Pydantic instance directly; the legacy
        _extract_json path must NOT be hit on the Sonnet branch."""
        import asyncio
        from unittest.mock import AsyncMock

        from vn_agent.agents.director import _step2_details
        from vn_agent.schema.script import DirectorStep2Output, DirectorStep2SceneOutput

        mock_invoke = AsyncMock(
            return_value=DirectorStep2Output(
                scenes=[DirectorStep2SceneOutput(id="s1"),
                        DirectorStep2SceneOutput(id="s2")]
            )
        )
        monkeypatch.setattr("vn_agent.agents.director.ainvoke_llm", mock_invoke)

        # If _extract_json gets called, raise immediately so test fails.
        def _boom(_content: str) -> dict:
            raise AssertionError("_extract_json must not be called on Tool Use path")

        monkeypatch.setattr("vn_agent.agents.director._extract_json", _boom)

        # Should complete without hitting _extract_json
        asyncio.run(
            _step2_details(self._outline(2), str(tmp_path), _FakeStep2Settings())
        )


class TestStep2PromptShape:
    """User prompt construction tests for the Tool Use branch."""

    def _capture_prompt(self, monkeypatch, outline, tmp_path):
        import asyncio

        captured: dict = {}

        async def _fake_invoke(system, user, **kwargs):
            captured["system"] = system
            captured["user"] = user
            captured["kwargs"] = kwargs
            raise RuntimeError("stop before real LLM call")

        monkeypatch.setattr("vn_agent.agents.director.ainvoke_llm", _fake_invoke)

        from vn_agent.agents.director import _step2_details

        try:
            asyncio.run(
                _step2_details(outline, str(tmp_path), _FakeStep2Settings())
            )
        except RuntimeError:
            pass
        return captured

    def test_prompt_no_longer_contains_json_example(self, monkeypatch, tmp_path):
        outline = {
            "start_scene_id": "s1",
            "scenes": [{"id": "s1", "title": "A", "description": "x"}],
            "world_variables": [],
        }
        captured = self._capture_prompt(monkeypatch, outline, tmp_path)
        # The legacy prompt had a JSON example block starting with "scenes": [
        # That block should be GONE in the Tool Use prompt.
        assert '"scenes": [' not in captured["user"]
        assert '"music_mood": "peaceful"' not in captured["user"]

    def test_prompt_retains_field_level_constraints(self, monkeypatch, tmp_path):
        """GPT review #2: deleting JSON examples without keeping
        prose-level field constraints would let the LLM skip optional
        fields. The MUST-include block + key field names must remain."""
        outline = {
            "start_scene_id": "s1",
            "scenes": [{"id": "s1", "title": "A", "description": "x"}],
            "world_variables": [],
        }
        captured = self._capture_prompt(monkeypatch, outline, tmp_path)
        user = captured["user"]
        assert "Each entry in the `scenes` list MUST include" in user
        # Key fields the LLM is most likely to skip without explicit prose
        for field in ("scene_brief", "context_deps", "state_writes",
                      "branches", "entry_context"):
            assert field in user

    def test_prompt_instructs_using_reasoning_field(self, monkeypatch, tmp_path):
        """Phase 13-3 M0-2: prompt must explicitly tell the model to fill
        the `reasoning` field BEFORE `scenes`. Without this hint the model
        can still skip it (Pydantic default ='' is schema-legal)."""
        outline = {
            "start_scene_id": "s1",
            "scenes": [{"id": "s1", "title": "A", "description": "x"}],
            "world_variables": [],
        }
        captured = self._capture_prompt(monkeypatch, outline, tmp_path)
        user = captured["user"]
        assert "reasoning" in user.lower()
        # Must be sequenced BEFORE scenes (instruction order matters for
        # tool-use field-emission order)
        assert "BEFORE filling `scenes`" in user or "before filling" in user.lower()


class TestStep2ObservabilityLogs:
    """Silent-failure guards from GPT review (#1, #3)."""

    def _outline(self, n_scenes: int):
        return {
            "start_scene_id": "s1",
            "scenes": [
                {"id": f"s{i+1}", "title": f"S{i+1}", "description": "x"}
                for i in range(n_scenes)
            ],
            "world_variables": [],
        }

    def test_logs_warning_on_scene_shrinkage(self, monkeypatch, tmp_path, caplog):
        import asyncio
        import logging
        from unittest.mock import AsyncMock

        from vn_agent.agents.director import _step2_details
        from vn_agent.schema.script import DirectorStep2Output, DirectorStep2SceneOutput

        # Outline expects 5; LLM returns only 3.
        mock_invoke = AsyncMock(
            return_value=DirectorStep2Output(
                scenes=[DirectorStep2SceneOutput(id=f"s{i+1}") for i in range(3)]
            )
        )
        monkeypatch.setattr("vn_agent.agents.director.ainvoke_llm", mock_invoke)

        with caplog.at_level(logging.WARNING, logger="vn_agent.agents.director"):
            asyncio.run(
                _step2_details(self._outline(5), str(tmp_path), _FakeStep2Settings())
            )

        msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("scene shrinkage" in m and "got 3, expected 5" in m for m in msgs)

    def test_logs_warning_on_empty_scenes(self, monkeypatch, tmp_path, caplog):
        import asyncio
        import logging
        from unittest.mock import AsyncMock

        from vn_agent.agents.director import _step2_details
        from vn_agent.schema.script import DirectorStep2Output

        mock_invoke = AsyncMock(return_value=DirectorStep2Output(scenes=[]))
        monkeypatch.setattr("vn_agent.agents.director.ainvoke_llm", mock_invoke)

        with caplog.at_level(logging.WARNING, logger="vn_agent.agents.director"):
            asyncio.run(
                _step2_details(self._outline(5), str(tmp_path), _FakeStep2Settings())
            )

        msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("empty structured output" in m for m in msgs)

    def test_logs_observability_stats_on_success(self, monkeypatch, tmp_path, caplog):
        """Structure stats line must be emitted for grep-friendly silent-
        degradation detection (e.g. branches_total=0). Phase 13-3 M0-2:
        reasoning_chars also appears in the line for CoT-usage tracking."""
        import asyncio
        import logging
        from unittest.mock import AsyncMock

        from vn_agent.agents.director import _step2_details
        from vn_agent.schema.script import (
            BranchOption,
            DirectorStep2Output,
            DirectorStep2SceneOutput,
        )

        mock_invoke = AsyncMock(
            return_value=DirectorStep2Output(
                reasoning="brief plan: s1 is opener, s2 is resolution",
                scenes=[
                    DirectorStep2SceneOutput(
                        id="s1",
                        branches=[BranchOption(text="a", next_scene_id="s2")],
                    ),
                    DirectorStep2SceneOutput(id="s2"),
                ],
            )
        )
        monkeypatch.setattr("vn_agent.agents.director.ainvoke_llm", mock_invoke)

        with caplog.at_level(logging.INFO, logger="vn_agent.agents.director"):
            asyncio.run(
                _step2_details(self._outline(2), str(tmp_path), _FakeStep2Settings())
            )

        msgs = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any(
            "tool_use ok: scenes=2" in m and "branches_total=1" in m
            for m in msgs
        )
        # Phase 13-3 M0-2: reasoning_chars must appear so M1 can detect
        # whether the model is actually using the scratchpad. 0 across
        # many runs would signal the field isn't restoring CoT and we'd
        # need to escalate the prompt.
        assert any("reasoning_chars=" in m for m in msgs)
        # And the actual length should match (42 chars for our fixture)
        assert any("reasoning_chars=42" in m for m in msgs)
