"""Phase 13-2 Step 2 (route 4): thinking_fanout agent coverage.

Covers:
- Disabled config → no-op pass-through (no scene.thinking populated)
- Below min_scenes → skipped (short-demo cost guard)
- Happy path with mocked thinking LLM → every scene gets a SceneThinking
- Thinking LLM failure on one scene → that scene.thinking stays None,
  others still succeed (non-blocking)
- _parse_thinking_json tolerates code-fence-wrapped JSON
- Prompt includes scene_brief + macro_reference + context_deps
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from vn_agent.agents.thinking import (
    _build_director_authority_map,
    _build_resync_prompt,
    _build_thinking_prompt,
    _cross_ref_peer_subset,
    _parse_thinking_json,
    detect_cross_ref_conflicts,
    resolve_callback_conflicts,
    run_cross_ref_sync,
    run_thinking_fanout,
)
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import (
    CallbackItem,
    MacroReference,
    Scene,
    SceneBrief,
    SceneContextRef,
    SceneThinking,
    VNScript,
    WorldVariable,
)


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


def _scene(sid: str, chars: list[str] | None = None,
           deps: list[SceneContextRef] | None = None,
           brief: SceneBrief | None = None,
           summary: str | None = None) -> Scene:
    return Scene(
        id=sid, title=sid.upper(), description=f"scene {sid}",
        background_id=f"bg_{sid}",
        characters_present=chars or ["alice"],
        context_deps=deps or [],
        scene_brief=brief,
        summary=summary,
    )


def _script(scenes: list[Scene], macro: MacroReference | None = None) -> VNScript:
    return VNScript(
        title="T", description="d", theme="th",
        start_scene_id=scenes[0].id if scenes else "",
        scenes=scenes,
        world_variables=[],
        macro_reference=macro,
    )


def _state(script: VNScript) -> dict:
    return {
        "theme": "t",
        "vn_script": script,
        "characters": {
            "alice": CharacterProfile(
                id="alice", name="Alice", role="main",
                personality="k", background="bg",
            ),
        },
        "revision_count": 0,
        "review_passed": False,
        "review_feedback": "",
        "structure_review_passed": True,
        "structure_review_feedback": "",
        "structure_review_issues": [],
        "assets_generated": False,
        "output_dir": "",
        "messages": [],
        "errors": [],
        "text_only": True,
        "max_scenes": 3,
        "num_characters": 1,
        "art_direction": "",
        "world_state": {},
        "state_constraints": "",
    }


_VALID_THINKING_JSON = (
    '{"writing_intent":"resolve callback with restraint",'
    '"key_beats_expanded":["beat a","beat b","beat c"],'
    '"callback_plan":[{"ref_scene_id":"s01","what_lands":"reveal"}],'
    '"opening_hook":"silence, then a door","closing_beat":"cut to black",'
    '"voice_notes":{"alice":"tighter cadence"},"risks":["no melodrama"]}'
)


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------


class TestThinkingFanoutGating:
    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self):
        script = _script([_scene(f"s{i}") for i in range(15)])
        with patch("vn_agent.agents.thinking.get_settings") as mock_s:
            mock_s.return_value.enable_thinking_fanout = False
            mock_s.return_value.thinking_fanout_min_scenes = 10

            result = await run_thinking_fanout(_state(script))

        # No-op — return empty dict (no vn_script override)
        assert result == {}

    @pytest.mark.asyncio
    async def test_below_min_scenes_skipped(self):
        """6-scene demo: enabled but below 10-scene floor → skip."""
        script = _script([_scene(f"s{i}") for i in range(6)])
        with patch("vn_agent.agents.thinking.get_settings") as mock_s:
            mock_s.return_value.enable_thinking_fanout = True
            mock_s.return_value.thinking_fanout_min_scenes = 10

            result = await run_thinking_fanout(_state(script))

        assert result == {}

    @pytest.mark.asyncio
    async def test_missing_vn_script_skipped(self):
        state = _state(_script([_scene("s1")]))
        state["vn_script"] = None

        with patch("vn_agent.agents.thinking.get_settings") as mock_s:
            mock_s.return_value.enable_thinking_fanout = True
            mock_s.return_value.thinking_fanout_min_scenes = 1

            result = await run_thinking_fanout(state)

        assert result == {}


# ---------------------------------------------------------------------------
# Happy path + error handling
# ---------------------------------------------------------------------------


class TestThinkingFanoutExecution:
    @pytest.mark.asyncio
    async def test_every_scene_gets_thinking(self):
        """Enabled + ≥ min: every scene should end up with SceneThinking."""
        scenes = [_scene(f"s{i:02d}") for i in range(3)]
        script = _script(scenes)

        mock_ainvoke = AsyncMock(return_value=_FakeResponse(_VALID_THINKING_JSON))

        with patch("vn_agent.agents.thinking.get_settings") as mock_s, \
             patch("vn_agent.agents.thinking.ainvoke_llm", mock_ainvoke):
            mock_s.return_value.enable_thinking_fanout = True
            mock_s.return_value.thinking_fanout_min_scenes = 1
            mock_s.return_value.llm_thinking_model = "claude-sonnet-4-6"

            result = await run_thinking_fanout(_state(script))

        assert "vn_script" in result
        new_script = result["vn_script"]
        assert len(new_script.scenes) == 3
        for scene in new_script.scenes:
            assert isinstance(scene.thinking, SceneThinking)
            assert scene.thinking.writing_intent == "resolve callback with restraint"

        # thinking LLM called once per scene
        assert mock_ainvoke.call_count == 3

    @pytest.mark.asyncio
    async def test_single_thinking_failure_non_blocking(self):
        """thinking LLM failing on scene 2 must leave scene 2.thinking=None
        but still produce thinking for scenes 1 and 3."""
        scenes = [_scene(f"s{i:02d}") for i in range(3)]
        script = _script(scenes)

        call_count = {"n": 0}

        async def _side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("thinking LLM is cranky today")
            return _FakeResponse(_VALID_THINKING_JSON)

        with patch("vn_agent.agents.thinking.get_settings") as mock_s, \
             patch("vn_agent.agents.thinking.ainvoke_llm", side_effect=_side_effect):
            mock_s.return_value.enable_thinking_fanout = True
            mock_s.return_value.thinking_fanout_min_scenes = 1
            mock_s.return_value.llm_thinking_model = "claude-sonnet-4-6"

            result = await run_thinking_fanout(_state(script))

        scenes_out = result["vn_script"].scenes
        assert scenes_out[0].thinking is not None
        assert scenes_out[1].thinking is None  # failed scene
        assert scenes_out[2].thinking is not None

    @pytest.mark.asyncio
    async def test_garbage_response_non_blocking(self):
        """Non-JSON thinking output → scene.thinking stays None (pipeline continues)."""
        scenes = [_scene("s01")]
        script = _script(scenes)

        mock_ainvoke = AsyncMock(return_value=_FakeResponse("not json at all"))

        with patch("vn_agent.agents.thinking.get_settings") as mock_s, \
             patch("vn_agent.agents.thinking.ainvoke_llm", mock_ainvoke):
            mock_s.return_value.enable_thinking_fanout = True
            mock_s.return_value.thinking_fanout_min_scenes = 1
            mock_s.return_value.llm_thinking_model = "claude-sonnet-4-6"

            result = await run_thinking_fanout(_state(script))

        assert result["vn_script"].scenes[0].thinking is None


# ---------------------------------------------------------------------------
# JSON parsing tolerance
# ---------------------------------------------------------------------------


class TestParseThinkingJson:
    def test_plain_json(self):
        data = _parse_thinking_json('{"writing_intent": "x"}')
        assert data == {"writing_intent": "x"}

    def test_fenced_json(self):
        """Models often wrap in ```json ... ```"""
        raw = '```json\n{"writing_intent": "x"}\n```'
        data = _parse_thinking_json(raw)
        assert data == {"writing_intent": "x"}

    def test_json_with_prose_prefix(self):
        """Fallback: find first {...} block when prose leaks through."""
        raw = 'Sure! Here is the plan:\n\n{"writing_intent": "x", "risks": []}'
        data = _parse_thinking_json(raw)
        assert data == {"writing_intent": "x", "risks": []}

    def test_not_json_returns_none(self):
        assert _parse_thinking_json("just prose, no braces") is None


# ---------------------------------------------------------------------------
# Prompt shape
# ---------------------------------------------------------------------------


class TestBuildThinkingPrompt:
    def test_prompt_includes_scene_brief(self):
        brief = SceneBrief(
            beats=["arrive", "pause", "speak"],
            tension_target="high",
        )
        scene = _scene("s02", brief=brief)
        script = _script([_scene("s01"), scene])

        prompt = _build_thinking_prompt(
            scene=scene,
            script=script,
            prior_scenes=[script.scenes[0]],
            world_state_at_entry={"affinity": 3},
        )

        assert "Scene brief" in prompt
        assert "arrive" in prompt  # beat leaks through
        assert "affinity" in prompt  # world_state included

    def test_prompt_includes_macro_reference(self):
        macro = MacroReference(theme_thesis="duty vs memory")
        scene = _scene("s01")
        script = _script([scene], macro=macro)

        prompt = _build_thinking_prompt(
            scene=scene,
            script=script,
            prior_scenes=[],
            world_state_at_entry={},
        )

        assert "Macro reference" in prompt
        assert "duty vs memory" in prompt

    def test_prompt_includes_relevant_prior_summaries(self):
        """Only summaries of scenes referenced in context_deps should appear."""
        s1 = _scene("s01", summary="alice learned the truth")
        s2 = _scene("s02", summary="unrelated event")
        s3 = _scene(
            "s03",
            deps=[SceneContextRef(
                ref_type="scene", ref_id="s01",
                link_type="callback", reason="callback to truth reveal",
            )],
        )
        script = _script([s1, s2, s3])

        prompt = _build_thinking_prompt(
            scene=s3,
            script=script,
            prior_scenes=[s1, s2],
            world_state_at_entry={},
        )

        # s01 callback — should appear
        assert "alice learned the truth" in prompt
        # s02 NOT referenced — should NOT appear
        assert "unrelated event" not in prompt


# ---------------------------------------------------------------------------
# World_state threading through the sequential pass
# ---------------------------------------------------------------------------


class TestWorldStateThreading:
    @pytest.mark.asyncio
    async def test_world_state_walks_forward(self):
        """Each scene's thinking prompt must see the post-previous-writes state."""
        s1 = _scene("s01")
        s1 = s1.model_copy(update={"state_writes": {"flag": True}})
        s2 = _scene("s02")

        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s01",
            scenes=[s1, s2],
            world_variables=[
                WorldVariable(
                    name="flag", type="bool", initial_value=False,
                    description="test flag",
                ),
            ],
        )

        captured_prompts: list[str] = []

        async def _capture(system, user, **kwargs):
            captured_prompts.append(user)
            return _FakeResponse(_VALID_THINKING_JSON)

        with patch("vn_agent.agents.thinking.get_settings") as mock_s, \
             patch("vn_agent.agents.thinking.ainvoke_llm", side_effect=_capture):
            mock_s.return_value.enable_thinking_fanout = True
            mock_s.return_value.thinking_fanout_min_scenes = 1
            mock_s.return_value.llm_thinking_model = "claude-sonnet-4-6"

            await run_thinking_fanout(_state(script))

        # s1 sees flag=False (initial)
        assert "'flag': False" in captured_prompts[0]
        # s2 sees flag=True (after s1's state_writes)
        assert "'flag': True" in captured_prompts[1]


# ===========================================================================
# Phase 13-2 Step 3 + 3.5: cross_ref_sync (two-tier deterministic resolver
# + opt-in Director arbitration, legacy Haiku revision behind a flag)
# ===========================================================================


def _thinking(
    intent: str = "do the thing",
    callback_plan: list[dict] | None = None,
) -> SceneThinking:
    """Factory. callback_plan is a list of dicts; Pydantic validates into
    CallbackItem on construction."""
    return SceneThinking(
        writing_intent=intent,
        key_beats_expanded=["beat a", "beat b"],
        callback_plan=callback_plan or [],
        opening_hook="hook",
        closing_beat="beat",
    )


class TestCrossRefPeerSubset:
    """Still used by the Tier-3 legacy LLM revision path."""

    def test_returns_only_dep_scenes_with_thinking(self):
        s1 = _scene("s01").model_copy(update={"thinking": _thinking("s1 draft")})
        s2 = _scene("s02").model_copy(update={"thinking": _thinking("s2 draft")})
        s3 = _scene(
            "s03",
            deps=[SceneContextRef(
                ref_type="scene", ref_id="s01",
                link_type="callback", reason="r",
            )],
        )
        peers = _cross_ref_peer_subset(s3, [s1, s2, s3])
        assert len(peers) == 1
        assert peers[0].id == "s01"

    def test_skips_dep_without_thinking(self):
        s1 = _scene("s01")  # thinking=None
        s2 = _scene(
            "s02",
            deps=[SceneContextRef(
                ref_type="scene", ref_id="s01",
                link_type="callback", reason="r",
            )],
        )
        peers = _cross_ref_peer_subset(s2, [s1, s2])
        assert peers == []

    def test_ignores_non_scene_deps(self):
        s1 = _scene("s01").model_copy(update={"thinking": _thinking()})
        s2 = _scene(
            "s02",
            deps=[SceneContextRef(
                ref_type="world_var", ref_id="world_var:flag",
                link_type="state_dependency", reason="r",
            )],
        )
        peers = _cross_ref_peer_subset(s2, [s1, s2])
        assert peers == []


class TestDetectCrossRefConflictsIDOnly:
    """Step 3.5: conflict = same ref_scene_id claimed by ≥2 scenes. No text
    similarity. Paraphrased collisions that difflib missed are now caught."""

    def test_no_conflicts_when_ref_ids_unique(self):
        s1 = _scene("s01").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "a"}],
        )})
        s2 = _scene("s02").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s99", "what_lands": "b"}],  # different ref
        )})
        assert detect_cross_ref_conflicts([s1, s2]) == []

    def test_conflict_by_shared_ref_id_regardless_of_text(self):
        """Paraphrased duplicates are STILL caught under ID-only rule."""
        s1 = _scene("s01").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "Explain the betrayal"}],
        )})
        # difflib ratio < 0.3 but semantically same payoff
        s2 = _scene("s02").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "Reveal that he was the traitor"}],
        )})
        conflicts = detect_cross_ref_conflicts([s1, s2])
        assert len(conflicts) == 1
        assert conflicts[0]["ref_scene_id"] == "s00"
        assert set(conflicts[0]["claimants"]) == {"s01", "s02"}
        assert conflicts[0]["what_lands_by_scene"] == {
            "s01": "Explain the betrayal",
            "s02": "Reveal that he was the traitor",
        }

    def test_no_thinking_means_no_conflicts(self):
        s1 = _scene("s01")
        s2 = _scene("s02")
        assert detect_cross_ref_conflicts([s1, s2]) == []

    def test_three_way_collision_reported_once(self):
        s1 = _scene("s01").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "a"}],
        )})
        s2 = _scene("s02").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "b"}],
        )})
        s3 = _scene("s03").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "c"}],
        )})
        conflicts = detect_cross_ref_conflicts([s1, s2, s3])
        assert len(conflicts) == 1
        assert set(conflicts[0]["claimants"]) == {"s01", "s02", "s03"}


class TestBuildDirectorAuthorityMap:
    def test_empty_macro_reference_empty_map(self):
        script = _script([_scene("s01")])
        assert _build_director_authority_map(script) == {}

    def test_foreshadow_plan_populates(self):
        macro = MacroReference(foreshadow_plan=[
            {"planted_in": "s01", "payoff_in": "s08", "element": "the watch"},
            {"planted_in": "s02", "payoff_in": "s07"},
        ])
        script = _script([_scene("s01")], macro=macro)
        owners = _build_director_authority_map(script)
        assert owners == {"s01": "s08", "s02": "s07"}

    def test_malformed_foreshadow_entries_skipped(self):
        macro = MacroReference(foreshadow_plan=[
            {"planted_in": "s01", "payoff_in": "s08"},
            {"planted_in": "s02"},  # no payoff_in
            {"element": "orphan"},  # no scenes
        ])
        script = _script([_scene("s01")], macro=macro)
        owners = _build_director_authority_map(script)
        assert owners == {"s01": "s08"}


class TestResolveCallbackConflictsTier1:
    """Step 3.5 Tier 1: deterministic resolver — Director authority first,
    latest-claimant fallback."""

    def test_director_authority_wins_over_latest(self):
        """Director declared payoff_in=s08. Even if s02 is LATER-listed
        than s08 (impossible in order, but hypothetically), s08 owns."""
        macro = MacroReference(foreshadow_plan=[
            {"planted_in": "s00", "payoff_in": "s08"},
        ])
        s1 = _scene("s01").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "reveal"}],
        )})
        s8 = _scene("s08").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "reveal"}],
        )})
        script = _script([s1, s8], macro=macro)

        resolved, log = resolve_callback_conflicts([s1, s8], script)

        assert len(log) == 1
        assert log[0]["winner"] == "s08"
        assert log[0]["authority"] == "director_foreshadow"
        # s01 lost → callback dropped from its plan
        assert resolved[0].thinking.callback_plan == []
        # s08 kept its callback
        assert len(resolved[1].thinking.callback_plan) == 1
        assert resolved[1].thinking.callback_plan[0].ref_scene_id == "s00"

    def test_fallback_latest_when_no_foreshadow_declared(self):
        """No macro_reference.foreshadow_plan entry for this ref → LATEST
        claimant wins (payoffs land in the back half of the arc, not front)."""
        s1 = _scene("s01").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "early hint"}],
        )})
        s8 = _scene("s08").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "climactic payoff"}],
        )})
        script = _script([s1, s8])  # no macro

        resolved, log = resolve_callback_conflicts([s1, s8], script)

        assert log[0]["winner"] == "s08"  # latest wins
        assert log[0]["authority"] == "fallback_latest"
        assert resolved[0].thinking.callback_plan == []
        assert len(resolved[1].thinking.callback_plan) == 1

    def test_no_conflicts_no_changes(self):
        s1 = _scene("s01").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "a"}],
        )})
        s2 = _scene("s02").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s99", "what_lands": "b"}],
        )})
        script = _script([s1, s2])

        resolved, log = resolve_callback_conflicts([s1, s2], script)

        assert log == []
        # Everybody keeps their callbacks
        assert len(resolved[0].thinking.callback_plan) == 1
        assert len(resolved[1].thinking.callback_plan) == 1

    def test_director_authority_for_scene_not_in_claimants(self):
        """Director declared s09 as payoff_in, but s09 isn't among claimants.
        Director's intent still honored — ALL claimants drop the callback;
        it's up to downstream re-planning to repopulate s09's plan."""
        macro = MacroReference(foreshadow_plan=[
            {"planted_in": "s00", "payoff_in": "s09"},
        ])
        s1 = _scene("s01").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "a"}],
        )})
        s2 = _scene("s02").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "b"}],
        )})
        script = _script([s1, s2], macro=macro)

        resolved, log = resolve_callback_conflicts([s1, s2], script)

        assert log[0]["winner"] == "s09"
        assert log[0]["authority"] == "director_foreshadow"
        # Both claimants dropped (neither was Director's choice)
        assert resolved[0].thinking.callback_plan == []
        assert resolved[1].thinking.callback_plan == []


class TestRunCrossRefSyncTier1Default:
    """Tier 1 (deterministic) is the DEFAULT path — no LLM calls,
    opt-in flags all off."""

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self):
        s1 = _scene("s01").model_copy(update={"thinking": _thinking()})
        s2 = _scene("s02").model_copy(update={"thinking": _thinking()})
        script = _script([s1, s2])
        with patch("vn_agent.agents.thinking.get_settings") as mock_s:
            mock_s.return_value.enable_cross_ref_sync = False
            mock_s.return_value.cross_ref_sync_min_scenes = 1

            result = await run_cross_ref_sync(_state(script))

        assert result == {}

    @pytest.mark.asyncio
    async def test_no_thinking_skipped(self):
        """No scene has thinking populated → skip entirely."""
        s1 = _scene("s01")  # thinking=None
        s2 = _scene("s02")
        script = _script([s1, s2])
        with patch("vn_agent.agents.thinking.get_settings") as mock_s:
            mock_s.return_value.enable_cross_ref_sync = True
            mock_s.return_value.cross_ref_sync_min_scenes = 1
            mock_s.return_value.enable_director_arbitration = False
            mock_s.return_value.enable_cross_ref_sync_llm_revise = False

            result = await run_cross_ref_sync(_state(script))

        assert result == {}

    @pytest.mark.asyncio
    async def test_default_path_no_llm_called(self):
        """Default (both flags off) — resolver is pure Python, no ainvoke_llm."""
        s1 = _scene("s01").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "a"}],
        )})
        s2 = _scene("s02").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "b"}],
        )})
        script = _script([s1, s2])

        mock_ainvoke = AsyncMock()

        with patch("vn_agent.agents.thinking.get_settings") as mock_s, \
             patch("vn_agent.agents.thinking.ainvoke_llm", mock_ainvoke):
            mock_s.return_value.enable_cross_ref_sync = True
            mock_s.return_value.cross_ref_sync_min_scenes = 1
            mock_s.return_value.enable_director_arbitration = False
            mock_s.return_value.enable_cross_ref_sync_llm_revise = False
            mock_s.return_value.llm_thinking_model = "haiku"
            mock_s.return_value.llm_director_model = "sonnet"

            result = await run_cross_ref_sync(_state(script))

        # Zero LLM calls — Tier 1 is pure Python.
        assert mock_ainvoke.call_count == 0
        # Conflict resolved deterministically: s02 (latest) wins.
        out = result["vn_script"]
        assert out.scenes[0].thinking.callback_plan == []  # s01 dropped
        assert len(out.scenes[1].thinking.callback_plan) == 1  # s02 kept


class TestRunCrossRefSyncTier2Arbitration:
    """Tier 2 (opt-in Director arbitration) — reuses Director model, not a
    new agent. Only re-arbitrates fallback_latest decisions."""

    @pytest.mark.asyncio
    async def test_director_overrides_latest_fallback(self):
        """Tier 1 picks s02 (latest); Director arbitration overrides to s01."""
        s1 = _scene("s01").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "planted hint"}],
        )})
        s2 = _scene("s02").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "later mention"}],
        )})
        script = _script([s1, s2])  # no foreshadow_plan → Tier 1 falls back

        # Director arbitration says: s01 actually owns
        arbitration_response = (
            '{"decisions":[{"ref_scene_id":"s00","winner":"s01",'
            '"reason":"s01 is the planting moment"}]}'
        )
        mock_ainvoke = AsyncMock(return_value=_FakeResponse(arbitration_response))

        with patch("vn_agent.agents.thinking.get_settings") as mock_s, \
             patch("vn_agent.agents.thinking.ainvoke_llm", mock_ainvoke):
            mock_s.return_value.enable_cross_ref_sync = True
            mock_s.return_value.cross_ref_sync_min_scenes = 1
            mock_s.return_value.enable_director_arbitration = True
            mock_s.return_value.enable_cross_ref_sync_llm_revise = False
            mock_s.return_value.llm_director_model = "claude-sonnet-4-6"

            result = await run_cross_ref_sync(_state(script))

        # Director reversed the decision: s01 now owns
        out = result["vn_script"]
        assert len(out.scenes[0].thinking.callback_plan) == 1
        assert out.scenes[0].thinking.callback_plan[0].ref_scene_id == "s00"
        # s02's callback dropped
        assert out.scenes[1].thinking.callback_plan == []

    @pytest.mark.asyncio
    async def test_director_not_invoked_when_no_fallback_cases(self):
        """If Tier 1 used only director_foreshadow authority (no fallback
        cases), Tier 2 skips the LLM call entirely."""
        macro = MacroReference(foreshadow_plan=[
            {"planted_in": "s00", "payoff_in": "s02"},
        ])
        s1 = _scene("s01").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "a"}],
        )})
        s2 = _scene("s02").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "b"}],
        )})
        script = _script([s1, s2], macro=macro)

        mock_ainvoke = AsyncMock()

        with patch("vn_agent.agents.thinking.get_settings") as mock_s, \
             patch("vn_agent.agents.thinking.ainvoke_llm", mock_ainvoke):
            mock_s.return_value.enable_cross_ref_sync = True
            mock_s.return_value.cross_ref_sync_min_scenes = 1
            mock_s.return_value.enable_director_arbitration = True
            mock_s.return_value.enable_cross_ref_sync_llm_revise = False
            mock_s.return_value.llm_director_model = "sonnet"

            await run_cross_ref_sync(_state(script))

        # No LLM call — Director's foreshadow_plan covered everything.
        assert mock_ainvoke.call_count == 0


class TestCrossRefSyncAuditLog:
    """cross_ref_conflicts.jsonl must record authority so creator-pause
    debug can trace decision chain."""

    @pytest.mark.asyncio
    async def test_authority_labels_written_to_jsonl(self, tmp_path):
        macro = MacroReference(foreshadow_plan=[
            {"planted_in": "s00", "payoff_in": "s01"},
        ])
        s1 = _scene("s01").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "s00", "what_lands": "director's choice"}],
        )})
        s2 = _scene("s02").model_copy(update={"thinking": _thinking(
            callback_plan=[
                {"ref_scene_id": "s00", "what_lands": "first collision"},
                {"ref_scene_id": "sXX", "what_lands": "fallback collision"},
            ],
        )})
        s3 = _scene("s03").model_copy(update={"thinking": _thinking(
            callback_plan=[{"ref_scene_id": "sXX", "what_lands": "also claims sXX"}],
        )})
        script = _script([s1, s2, s3], macro=macro)

        state = _state(script)
        state["output_dir"] = str(tmp_path)

        with patch("vn_agent.agents.thinking.get_settings") as mock_s:
            mock_s.return_value.enable_cross_ref_sync = True
            mock_s.return_value.cross_ref_sync_min_scenes = 1
            mock_s.return_value.enable_director_arbitration = False
            mock_s.return_value.enable_cross_ref_sync_llm_revise = False

            await run_cross_ref_sync(state)

        path = tmp_path / "cross_ref_conflicts.jsonl"
        assert path.exists()
        import json as _json
        rows = [
            _json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        by_ref = {r["ref_scene_id"]: r for r in rows}
        # s00 collision → Director authority (foreshadow_plan says s01 owns)
        assert by_ref["s00"]["authority"] == "director_foreshadow"
        assert by_ref["s00"]["winner"] == "s01"
        # sXX collision → latest-fallback (no foreshadow)
        assert by_ref["sXX"]["authority"] == "fallback_latest"
        assert by_ref["sXX"]["winner"] == "s03"


class TestResyncLegacyPath:
    """Tier 3 (enable_cross_ref_sync_llm_revise=True) is the legacy Haiku
    self-revision path. Kept behind a flag for research. Default OFF."""

    @pytest.mark.asyncio
    async def test_legacy_path_calls_haiku_when_enabled(self):
        s1 = _scene("s01").model_copy(update={"thinking": _thinking("s1 draft")})
        s2 = _scene(
            "s02",
            deps=[SceneContextRef(
                ref_type="scene", ref_id="s01",
                link_type="callback", reason="r",
            )],
        ).model_copy(update={"thinking": _thinking("s2 draft")})
        script = _script([s1, s2])

        revised_json = (
            '{"writing_intent":"revised intent","key_beats_expanded":["a"],'
            '"callback_plan":[{"ref_scene_id":"s01","what_lands":"fresh angle"}],'
            '"opening_hook":"h","closing_beat":"b","voice_notes":{},"risks":[]}'
        )
        mock_ainvoke = AsyncMock(return_value=_FakeResponse(revised_json))

        with patch("vn_agent.agents.thinking.get_settings") as mock_s, \
             patch("vn_agent.agents.thinking.ainvoke_llm", mock_ainvoke):
            mock_s.return_value.enable_cross_ref_sync = True
            mock_s.return_value.cross_ref_sync_min_scenes = 1
            mock_s.return_value.enable_director_arbitration = False
            mock_s.return_value.enable_cross_ref_sync_llm_revise = True
            mock_s.return_value.llm_thinking_model = "haiku"
            mock_s.return_value.llm_director_model = "sonnet"

            result = await run_cross_ref_sync(_state(script))

        # Haiku called for s02 (has peer deps); s01 has no deps → skipped
        assert mock_ainvoke.call_count == 1
        # s02 revised
        assert result["vn_script"].scenes[1].thinking.writing_intent == "revised intent"


class TestResyncPrompt:
    def test_prompt_shows_current_thinking_and_peer(self):
        s1 = _scene("s01").model_copy(update={"thinking": _thinking("peer plan")})
        s2 = _scene(
            "s02",
            deps=[SceneContextRef(
                ref_type="scene", ref_id="s01",
                link_type="callback", reason="r",
            )],
        ).model_copy(update={"thinking": _thinking("my plan")})
        script = _script([s1, s2])

        prompt = _build_resync_prompt(s2, script, peers=[s1])
        assert "CURRENT thinking plan" in prompt
        assert "my plan" in prompt
        assert "Peer [s01" in prompt
        assert "peer plan" in prompt


# Sanity unit checks on CallbackItem (in thinking tests because that's the
# primary consumer).
class TestCallbackItemInvariants:
    def test_hydrated_from_dict_on_thinking_build(self):
        t = SceneThinking(callback_plan=[
            {"ref_scene_id": "s01", "what_lands": "reveal"},
        ])
        assert isinstance(t.callback_plan[0], CallbackItem)
        assert t.callback_plan[0].ref_scene_id == "s01"

    def test_missing_key_rejects_at_thinking_build(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            SceneThinking(callback_plan=[{"target_scene": "s01"}])  # bad key
