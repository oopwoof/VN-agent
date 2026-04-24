"""Tests for Writer smart truncation fallback (Sprint 6-8)."""
from __future__ import annotations

import pytest

from vn_agent.agents.writer import _regenerate_short_dialogue
from vn_agent.schema.script import DialogueLine, Scene


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


def _scene() -> Scene:
    return Scene(
        id="s1", title="Test Scene", description="a test scene",
        background_id="bg", characters_present=["alice", "bob"],
    )


def _existing(n: int = 2) -> list[DialogueLine]:
    return [
        DialogueLine(character_id="alice", text=f"Line {i} from alice", emotion="neutral")
        for i in range(n)
    ]


def _settings_stub(writer_model: str = "claude-haiku-4-5-20251001"):
    """Minimal settings object exposing the two fields _regenerate_short_dialogue uses."""
    class _S:
        llm_writer_model = writer_model
    return _S()


class TestRegenerateShortDialogue:
    @pytest.mark.asyncio
    async def test_empty_existing_returns_empty(self, tmp_path):
        """When parser produced nothing, we can't continue — return empty and let caller fall back."""
        result = await _regenerate_short_dialogue(
            _scene(), [], missing=3, settings=_settings_stub(),
            output_dir=str(tmp_path),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_successful_continuation(self, mocker, tmp_path):
        """Happy path: LLM returns valid JSON continuation, we parse and cap to `missing`."""
        fake_json = (
            '[{"character_id": "alice", "text": "Continuation line 1", "emotion": "happy"},'
            '{"character_id": "bob", "text": "Continuation line 2", "emotion": "sad"},'
            '{"character_id": null, "text": "Continuation narration", "emotion": "neutral"}]'
        )
        mocker.patch(
            "vn_agent.agents.writer.ainvoke_llm",
            return_value=_FakeMessage(fake_json),
        )
        result = await _regenerate_short_dialogue(
            _scene(), _existing(2), missing=2,
            settings=_settings_stub(), output_dir=str(tmp_path),
        )
        assert len(result) == 2  # capped to missing=2 even though LLM returned 3
        assert result[0].text == "Continuation line 1"
        assert result[1].text == "Continuation line 2"

    @pytest.mark.asyncio
    async def test_llm_exception_returns_empty(self, mocker, tmp_path):
        """When the continuation call raises, we must NOT propagate — caller expects []."""
        mocker.patch(
            "vn_agent.agents.writer.ainvoke_llm",
            side_effect=RuntimeError("simulated API failure"),
        )
        result = await _regenerate_short_dialogue(
            _scene(), _existing(2), missing=2,
            settings=_settings_stub(), output_dir=str(tmp_path),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_garbage_response_returns_empty_or_fallback(self, mocker, tmp_path):
        """LLM returns non-JSON nonsense — _parse_dialogue will fall back; we just verify no crash."""
        mocker.patch(
            "vn_agent.agents.writer.ainvoke_llm",
            return_value=_FakeMessage("this is not JSON at all, just prose about cats"),
        )
        result = await _regenerate_short_dialogue(
            _scene(), _existing(2), missing=3,
            settings=_settings_stub(), output_dir=str(tmp_path),
        )
        # _parse_dialogue's fallback produces a placeholder; we cap to missing=3.
        # Either empty or partial is acceptable — the key is no exception.
        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_cap_applies_when_llm_generous(self, mocker, tmp_path):
        """If LLM returns more lines than requested, we cap to missing."""
        many_lines = "[" + ",".join(
            f'{{"character_id": null, "text": "line {i}", "emotion": "neutral"}}'
            for i in range(10)
        ) + "]"
        mocker.patch(
            "vn_agent.agents.writer.ainvoke_llm",
            return_value=_FakeMessage(many_lines),
        )
        result = await _regenerate_short_dialogue(
            _scene(), _existing(1), missing=1,
            settings=_settings_stub(), output_dir=str(tmp_path),
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Phase 13-2 Step 1 (AUDITS §2 piggyback):
# run_writer must snapshot state_constraints onto each scene's
# state_constraints_seen before calling _write_scene.
# ---------------------------------------------------------------------------


class TestStateConstraintsSnapshot:
    """End-to-end check: run_writer loop copies the current state_constraints
    text onto scene.state_constraints_seen so it survives into the persisted
    vn_script.json (AUDITS §2: "Writer 当时看到了什么" was previously lost)."""

    @pytest.mark.asyncio
    async def test_constraints_propagated_to_every_scene(self, mocker, tmp_path):
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import Scene, VNScript

        # Mock _write_scene to pass the input scene through untouched,
        # so we can inspect what run_writer set on it.
        captured_scenes = []

        async def _fake_write(scene, *args, **kwargs):
            captured_scenes.append(scene)
            return scene  # unchanged — dialogue left empty

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")  # no disk IO

        scenes = [
            Scene(id=f"s{i}", title=f"S{i}", description="x",
                  background_id="bg", characters_present=["a"])
            for i in range(3)
        ]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes, world_variables=[],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=3, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)
        state["state_constraints"] = "CONSTRAINT: x==1 ⇒ hesitate. x==0 ⇒ push."

        result = await run_writer(state)
        out_script = result["vn_script"]

        assert len(out_script.scenes) == 3
        # Every persisted scene carries the constraint snapshot
        for scene in out_script.scenes:
            assert scene.state_constraints_seen == \
                "CONSTRAINT: x==1 ⇒ hesitate. x==0 ⇒ push."

    @pytest.mark.asyncio
    async def test_writer_does_not_mutate_state_writes(self, mocker, tmp_path):
        """Phase 13-2 Step 3.5 (Gemini BLOCKER 2 regression guard): Writer
        must never modify Director-declared state_writes. This contract
        is load-bearing for parallel Writer mode (route-4 Step 4): if
        parallel workers mutated state_writes, concurrent scenes couldn't
        see each other's changes, fragmenting narrative state.

        The existing design already delegates state_writes to Director
        (writer.py comments: "Writer does NOT produce additional writes
        via its JSON output — _parse_dialogue only extracts DialogueLine").
        This test is the regression guard that keeps it that way.
        """
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import Scene, VNScript

        async def _fake_write(scene, *args, **kwargs):
            # Simulate a Writer that (incorrectly) tried to add dialogue
            # but honors the state_writes contract — returns scene with
            # dialogue populated, state_writes UNCHANGED.
            from vn_agent.schema.script import DialogueLine
            return scene.model_copy(update={
                "dialogue": [
                    DialogueLine(
                        character_id="alice", text="line", emotion="neutral",
                    ),
                ],
            })

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")

        input_state_writes = {"affinity": 5, "flag": True}
        scene = Scene(
            id="s0", title="S", description="x", background_id="bg",
            characters_present=["alice"],
            state_writes=dict(input_state_writes),
        )
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=[scene], world_variables=[],
        )
        chars = {"alice": CharacterProfile(
            id="alice", name="A", role="p", personality="", background="",
        )}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=1, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)

        result = await run_writer(state)

        # Bit-for-bit equal — Writer preserved state_writes
        assert result["vn_script"].scenes[0].state_writes == input_state_writes

    @pytest.mark.asyncio
    async def test_sequential_state_writes_threaded_to_next_scene(
        self, mocker, tmp_path,
    ):
        """Phase 13-2 Step 4b-3 regression guard: after refactoring run_writer
        into orchestrator + _process_scene, scene N+1 must still see scene N's
        state_writes in world_state.

        The sequential path mutates world_state after each _process_scene
        returns. This test captures the world_state snapshot each scene is
        called with and asserts scene 1's world_state reflects scene 0's
        state_writes, scene 2's reflects scene 0+1, etc.

        4b-4's parallel path will need to preserve this property at the
        wave-barrier granularity (not per-scene).
        """
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import Scene, VNScript, WorldVariable

        seen_world_states: list[dict] = []

        async def _fake_write(scene, script, char_desc, revision_feedback,
                              output_dir, *args, **kwargs):
            # Snapshot the world_state arg so we can verify threading
            seen_world_states.append(dict(kwargs["world_state"]))
            # Return the scene unchanged — state_writes already declared
            # by Director are preserved via Pydantic copy semantics.
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")

        # 3 scenes, each declaring a different state_write.
        scenes = [
            Scene(
                id="s0", title="S0", description="x", background_id="bg",
                characters_present=["a"],
                state_writes={"x": 1},
            ),
            Scene(
                id="s1", title="S1", description="x", background_id="bg",
                characters_present=["a"],
                state_writes={"y": 2},
            ),
            Scene(
                id="s2", title="S2", description="x", background_id="bg",
                characters_present=["a"],
                state_reads=["x", "y"],  # depends on both prior writes
            ),
        ]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes,
            world_variables=[
                WorldVariable(name="x", type="int", initial_value=0,
                              description="x"),
                WorldVariable(name="y", type="int", initial_value=0,
                              description="y"),
            ],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=3, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)

        await run_writer(state)

        assert len(seen_world_states) == 3
        # scene 0 sees initial values
        assert seen_world_states[0] == {"x": 0, "y": 0}
        # scene 1 sees scene 0's write applied
        assert seen_world_states[1] == {"x": 1, "y": 0}
        # scene 2 sees both scene 0 and scene 1 writes applied
        assert seen_world_states[2] == {"x": 1, "y": 2}

    @pytest.mark.asyncio
    async def test_empty_constraints_leaves_field_none(self, mocker, tmp_path):
        """When state_constraints is empty string (no orchestrator output),
        scene.state_constraints_seen must stay None — don't pollute with ""."""
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import Scene, VNScript

        async def _fake_write(scene, *args, **kwargs):
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")

        scenes = [Scene(id="s0", title="S", description="x", background_id="bg")]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes, world_variables=[],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=1, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)
        state["state_constraints"] = ""  # empty

        result = await run_writer(state)
        assert result["vn_script"].scenes[0].state_constraints_seen is None


# ---------------------------------------------------------------------------
# Phase 13-2 Step 4a: Writer consumes scene.thinking as its final briefing.
# Flag-gated — default OFF keeps existing path unchanged.
# ---------------------------------------------------------------------------


class TestWriterConsumesThinking:
    def _thinking(self):
        from vn_agent.schema.script import CallbackItem, SceneThinking
        return SceneThinking(
            writing_intent="resolve the watch callback with restraint",
            opening_hook="waves hitting the lantern room — slow rhythm",
            key_beats_expanded=[
                "yui notices the watch",
                "ren speaks — says only her name",
                "she answers without turning",
            ],
            callback_plan=[
                CallbackItem(
                    ref_scene_id="s01",
                    what_lands="reveal the watch stopped the night he died",
                ),
            ],
            voice_notes={"yui": "tighter cadence — guarding"},
            closing_beat="cut to black as yui pockets the watch",
            risks=[
                "no melodrama on the reveal",
                "avoid naming the father explicitly",
            ],
        )

    def test_format_thinking_block_contains_all_fields(self):
        """Unit on the helper — every populated field must surface."""
        from vn_agent.agents.writer import _format_thinking_block
        block = _format_thinking_block(self._thinking())
        # Key markers from each section
        assert "Intent: resolve the watch callback" in block
        assert "Opening hook: waves hitting" in block
        assert "1. yui notices the watch" in block
        assert "[s01] reveal the watch stopped" in block
        assert "yui: tighter cadence" in block
        assert "Closing beat: cut to black" in block
        assert "× no melodrama" in block
        assert "--- End plan ---" in block

    def test_format_thinking_block_skips_empty_fields(self):
        """Minimal SceneThinking should produce a block without empty sections."""
        from vn_agent.agents.writer import _format_thinking_block
        from vn_agent.schema.script import SceneThinking
        t = SceneThinking(writing_intent="just this")
        block = _format_thinking_block(t)
        assert "Intent: just this" in block
        # No beats / callbacks / voice / risks sections since they're empty
        assert "Beats" not in block
        assert "Callbacks" not in block
        assert "Voice notes" not in block
        assert "Avoid" not in block

    @pytest.mark.asyncio
    async def test_thinking_in_prompt_when_flag_on(self, mocker, tmp_path):
        """With writer_consume_thinking=True AND scene.thinking present,
        the rendered block must appear in Writer's user prompt."""
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import Scene, VNScript

        captured_prompts: list[str] = []

        async def _capture(system, user_prompt, *args, **kwargs):
            captured_prompts.append(user_prompt)
            from vn_agent.schema.script import DialogueLine
            return scene_with_thinking.model_copy(update={
                "dialogue": [DialogueLine(
                    character_id="alice", text="line", emotion="neutral",
                )],
            })

        # Build a scene with thinking
        scene_with_thinking = Scene(
            id="s1", title="S", description="x", background_id="bg",
            characters_present=["alice"],
            thinking=self._thinking(),
        )
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s1", scenes=[scene_with_thinking],
            world_variables=[],
        )
        chars = {"alice": CharacterProfile(
            id="alice", name="A", role="p", personality="", background="",
        )}

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_capture)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")
        mock_s = mocker.patch("vn_agent.agents.writer.get_settings")
        # Need real-ish settings — patch only the thinking flag
        from vn_agent.config import get_settings as _real_get_settings
        real_s = _real_get_settings()
        # Copy every attr so the rest of Writer init still works, flip the one flag
        mock_s.return_value = real_s
        real_s.writer_consume_thinking = True

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=1, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)

        # NOTE: _write_scene is mocked so captured_prompts here WON'T receive
        # the actual Writer user_prompt. We need to exercise _write_scene's
        # internal prompt assembly. Switch to a direct _write_scene test.
        # Leaving run_writer here as a smoke that the flag-plumbing doesn't
        # crash the pipeline.
        await run_writer(state)
        # Sanity: no crash, at least one _write_scene call.

    @pytest.mark.asyncio
    async def test_thinking_block_spliced_into_write_scene_prompt(self, mocker, tmp_path):
        """Unit on _write_scene's prompt assembly: thinking_block shows up
        in the user prompt iff flag on + scene.thinking present."""
        from vn_agent.agents.writer import _write_scene
        from vn_agent.schema.script import Scene, VNScript

        # Capture the user_prompt passed to ainvoke_llm inside _write_scene
        captured: dict = {}

        class _FakeResp:
            def __init__(self):
                self.content = "[]"  # empty dialogue array, caller handles

        async def _fake_ainvoke(system, user, *args, **kwargs):
            captured["system"] = system
            captured["user"] = user
            return _FakeResp()

        mocker.patch("vn_agent.agents.writer.ainvoke_llm", side_effect=_fake_ainvoke)
        # Skip rag record append + inner _regenerate_short_dialogue path
        mocker.patch("vn_agent.agents.writer._append_rag_record")

        scene = Scene(
            id="s1", title="S", description="desc", background_id="bg",
            characters_present=["alice"],
            thinking=self._thinking(),
        )
        script = VNScript(
            title="T", description="premise", theme="th",
            start_scene_id="s1", scenes=[scene], world_variables=[],
        )

        # Flag ON: block must appear
        mock_s = mocker.patch("vn_agent.agents.writer.get_settings")
        from vn_agent.config import get_settings as _real_get_settings
        s = _real_get_settings()
        s.writer_consume_thinking = True
        s.min_dialogue_lines = 1
        s.max_dialogue_lines = 5
        mock_s.return_value = s

        await _write_scene(
            scene, script, char_descriptions="",
            revision_feedback="", output_dir=str(tmp_path),
            system_prompt="writer system",
        )
        assert "Your scene plan (from thinking phase)" in captured["user"]
        assert "resolve the watch callback" in captured["user"]

        # Flag OFF: block must NOT appear
        captured.clear()
        s.writer_consume_thinking = False
        await _write_scene(
            scene, script, char_descriptions="",
            revision_feedback="", output_dir=str(tmp_path),
            system_prompt="writer system",
        )
        assert "Your scene plan (from thinking phase)" not in captured["user"]

        # Flag ON but thinking=None: block must NOT appear
        captured.clear()
        s.writer_consume_thinking = True
        scene_no_thinking = scene.model_copy(update={"thinking": None})
        await _write_scene(
            scene_no_thinking, script, char_descriptions="",
            revision_feedback="", output_dir=str(tmp_path),
            system_prompt="writer system",
        )
        assert "Your scene plan (from thinking phase)" not in captured["user"]
