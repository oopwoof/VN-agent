"""Phase 13-2 Step 2 (route 4): thinking_fanout agent coverage.

Covers:
- Disabled config → no-op pass-through (no scene.thinking populated)
- Below min_scenes → skipped (short-demo cost guard)
- Happy path with mocked Haiku → every scene gets a SceneThinking
- Haiku failure on one scene → that scene.thinking stays None,
  others still succeed (non-blocking)
- _parse_thinking_json tolerates code-fence-wrapped JSON
- Prompt includes scene_brief + macro_reference + context_deps
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from vn_agent.agents.thinking import (
    _build_thinking_prompt,
    _parse_thinking_json,
    run_thinking_fanout,
)
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import (
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
            mock_s.return_value.llm_thinking_model = "claude-haiku-4-5-20251001"

            result = await run_thinking_fanout(_state(script))

        assert "vn_script" in result
        new_script = result["vn_script"]
        assert len(new_script.scenes) == 3
        for scene in new_script.scenes:
            assert isinstance(scene.thinking, SceneThinking)
            assert scene.thinking.writing_intent == "resolve callback with restraint"

        # Haiku called once per scene
        assert mock_ainvoke.call_count == 3

    @pytest.mark.asyncio
    async def test_single_haiku_failure_non_blocking(self):
        """Haiku failing on scene 2 must leave scene 2.thinking=None but
        still produce thinking for scenes 1 and 3."""
        scenes = [_scene(f"s{i:02d}") for i in range(3)]
        script = _script(scenes)

        call_count = {"n": 0}

        async def _side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("Haiku is cranky today")
            return _FakeResponse(_VALID_THINKING_JSON)

        with patch("vn_agent.agents.thinking.get_settings") as mock_s, \
             patch("vn_agent.agents.thinking.ainvoke_llm", side_effect=_side_effect):
            mock_s.return_value.enable_thinking_fanout = True
            mock_s.return_value.thinking_fanout_min_scenes = 1
            mock_s.return_value.llm_thinking_model = "claude-haiku-4-5-20251001"

            result = await run_thinking_fanout(_state(script))

        scenes_out = result["vn_script"].scenes
        assert scenes_out[0].thinking is not None
        assert scenes_out[1].thinking is None  # failed scene
        assert scenes_out[2].thinking is not None

    @pytest.mark.asyncio
    async def test_garbage_response_non_blocking(self):
        """Non-JSON Haiku output → scene.thinking stays None (pipeline continues)."""
        scenes = [_scene("s01")]
        script = _script(scenes)

        mock_ainvoke = AsyncMock(return_value=_FakeResponse("not json at all"))

        with patch("vn_agent.agents.thinking.get_settings") as mock_s, \
             patch("vn_agent.agents.thinking.ainvoke_llm", mock_ainvoke):
            mock_s.return_value.enable_thinking_fanout = True
            mock_s.return_value.thinking_fanout_min_scenes = 1
            mock_s.return_value.llm_thinking_model = "claude-haiku-4-5-20251001"

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
        """Haiku often wraps in ```json ... ```"""
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
            mock_s.return_value.llm_thinking_model = "claude-haiku-4-5-20251001"

            await run_thinking_fanout(_state(script))

        # s1 sees flag=False (initial)
        assert "'flag': False" in captured_prompts[0]
        # s2 sees flag=True (after s1's state_writes)
        assert "'flag': True" in captured_prompts[1]
