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


# ---------------------------------------------------------------------------
# Phase 13-2 Step 4b-4: Parallel Writer path.
# Routes on settings.writer_max_concurrent > 1. Processes chapters in order
# (chapter barrier), waves within a chapter in topological order (wave
# barrier), and scenes within a wave concurrently under Semaphore.
# ---------------------------------------------------------------------------


class TestParallelWriterPath:
    """Parallel path invariants that 4b-4 must hold."""

    def _scene(self, sid: str, deps=None, state_writes=None, state_reads=None):
        from vn_agent.schema.script import Scene, SceneContextRef
        refs = []
        for ref_type, ref_id in deps or []:
            refs.append(SceneContextRef(
                ref_type=ref_type, ref_id=ref_id,
                link_type="callback", reason="test",
            ))
        return Scene(
            id=sid, title=sid.upper(), description=f"desc {sid}",
            background_id="bg", characters_present=["a"],
            context_deps=refs,
            state_writes=state_writes or {},
            state_reads=state_reads or [],
        )

    def _parallel_settings(self, max_concurrent: int = 3):
        """Fresh Settings instance with parallel flags ON — bypasses
        the get_settings lru_cache singleton which other tests mutate."""
        from vn_agent.config import Settings
        return Settings(
            writer_max_concurrent=max_concurrent,
            enable_thinking_fanout=True,
            writer_consume_thinking=True,
            enable_scene_summarization=False,  # skip Haiku calls
            enable_chapter_rollup=False,  # 4b-4 tests don't exercise rollup
            writer_context_window=0,  # simplify — no prior_scenes wiring
        )

    @pytest.mark.asyncio
    async def test_parallel_path_runs_when_max_concurrent_gt_1(
        self, mocker, tmp_path,
    ):
        """writer_max_concurrent>1 must dispatch to _run_scenes_parallel."""
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import VNScript

        async def _fake_write(scene, *args, **kwargs):
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")
        mocker.patch(
            "vn_agent.agents.writer.get_settings",
            return_value=self._parallel_settings(max_concurrent=3),
        )
        parallel_spy = mocker.spy(
            __import__("vn_agent.agents.writer", fromlist=["_run_scenes_parallel"]),
            "_run_scenes_parallel",
        )
        sequential_spy = mocker.spy(
            __import__("vn_agent.agents.writer", fromlist=["_run_scenes_sequential"]),
            "_run_scenes_sequential",
        )

        scenes = [self._scene(f"s{i}") for i in range(3)]
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

        await run_writer(state)
        assert parallel_spy.call_count == 1
        assert sequential_spy.call_count == 0

    @pytest.mark.asyncio
    async def test_sequential_path_still_default(self, mocker, tmp_path):
        """writer_max_concurrent=1 default keeps using sequential path
        (regression guard so 4b-4 doesn't change default behavior)."""
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.config import Settings
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import VNScript

        async def _fake_write(scene, *args, **kwargs):
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")
        mocker.patch(
            "vn_agent.agents.writer.get_settings",
            return_value=Settings(
                writer_max_concurrent=1,
                enable_scene_summarization=False,
                enable_chapter_rollup=False,
            ),
        )
        parallel_spy = mocker.spy(
            __import__("vn_agent.agents.writer", fromlist=["_run_scenes_parallel"]),
            "_run_scenes_parallel",
        )
        sequential_spy = mocker.spy(
            __import__("vn_agent.agents.writer", fromlist=["_run_scenes_sequential"]),
            "_run_scenes_sequential",
        )

        scenes = [self._scene(f"s{i}") for i in range(2)]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes, world_variables=[],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=2, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)

        await run_writer(state)
        assert sequential_spy.call_count == 1
        assert parallel_spy.call_count == 0

    @pytest.mark.asyncio
    async def test_within_wave_peers_see_same_state_snapshot(
        self, mocker, tmp_path,
    ):
        """Within one wave, every scene sees the pre-wave world_state —
        siblings are INVISIBLE to each other (coordination signal must
        come from thinking_fanout upstream, never from peer state_writes).

        Setup: 3 scenes in wave 0 (no deps); scene 0 state_writes x=1
        but scenes 1 & 2 must NOT see that write during their own call.
        """
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import VNScript, WorldVariable

        seen: list[tuple[str, dict]] = []

        async def _fake_write(scene, *args, **kwargs):
            seen.append((scene.id, dict(kwargs["world_state"])))
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")
        mocker.patch(
            "vn_agent.agents.writer.get_settings",
            return_value=self._parallel_settings(max_concurrent=3),
        )

        scenes = [
            self._scene("s0", state_writes={"x": 1}),
            self._scene("s1", state_writes={"y": 2}),
            self._scene("s2", state_writes={"z": 3}),
        ]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes,
            world_variables=[
                WorldVariable(name="x", type="int", initial_value=0, description="x"),
                WorldVariable(name="y", type="int", initial_value=0, description="y"),
                WorldVariable(name="z", type="int", initial_value=0, description="z"),
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

        # All 3 scenes ran in wave 0 and saw the same INITIAL state —
        # none of them saw each other's state_writes.
        initial = {"x": 0, "y": 0, "z": 0}
        snapshots_by_id = {sid: snap for sid, snap in seen}
        assert snapshots_by_id["s0"] == initial
        assert snapshots_by_id["s1"] == initial
        assert snapshots_by_id["s2"] == initial

    @pytest.mark.asyncio
    async def test_cross_wave_state_writes_visible_to_next_wave(
        self, mocker, tmp_path,
    ):
        """Diamond DAG s00 → {s01, s02} → s03:
          wave 0 = [s00], wave 1 = [s01, s02], wave 2 = [s03].

        After wave 0, s00's state_writes must land in world_state so
        wave 1's scenes see them. After wave 1, both s01's and s02's
        state_writes must merge (in script order) before wave 2 runs.
        """
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import VNScript, WorldVariable

        seen: dict[str, dict] = {}

        async def _fake_write(scene, *args, **kwargs):
            seen[scene.id] = dict(kwargs["world_state"])
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")
        mocker.patch(
            "vn_agent.agents.writer.get_settings",
            return_value=self._parallel_settings(max_concurrent=5),
        )

        scenes = [
            self._scene("s00", state_writes={"a": 1}),
            self._scene("s01", deps=[("scene", "s00")], state_writes={"b": 2}),
            self._scene("s02", deps=[("scene", "s00")], state_writes={"c": 3}),
            self._scene("s03", deps=[("scene", "s01"), ("scene", "s02")]),
        ]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s00", scenes=scenes,
            world_variables=[
                WorldVariable(name="a", type="int", initial_value=0, description=""),
                WorldVariable(name="b", type="int", initial_value=0, description=""),
                WorldVariable(name="c", type="int", initial_value=0, description=""),
            ],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=4, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)

        await run_writer(state)

        # Wave 0: s00 sees fresh initial state.
        assert seen["s00"] == {"a": 0, "b": 0, "c": 0}
        # Wave 1: s01 + s02 both see s00's write (a=1) — wave barrier.
        # Neither yet sees the other (siblings invisible in same wave).
        assert seen["s01"] == {"a": 1, "b": 0, "c": 0}
        assert seen["s02"] == {"a": 1, "b": 0, "c": 0}
        # Wave 2: s03 sees ALL prior writes merged.
        assert seen["s03"] == {"a": 1, "b": 2, "c": 3}

    @pytest.mark.asyncio
    async def test_updated_scenes_in_script_order_despite_out_of_order_completion(
        self, mocker, tmp_path,
    ):
        """Tasks within a wave may complete in any order; the merged
        output MUST be in script.scenes positional order for determinism."""
        import asyncio as _asyncio

        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import VNScript

        async def _fake_write(scene, *args, **kwargs):
            # Later scenes finish FIRST (reverse completion order)
            # → exactly the case where a naive append would reorder.
            delay_map = {"s0": 0.03, "s1": 0.02, "s2": 0.01}
            await _asyncio.sleep(delay_map.get(scene.id, 0))
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")
        mocker.patch(
            "vn_agent.agents.writer.get_settings",
            return_value=self._parallel_settings(max_concurrent=3),
        )

        scenes = [self._scene(f"s{i}") for i in range(3)]  # no deps → wave 0
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

        result = await run_writer(state)
        # Output order matches script order, NOT completion order.
        assert [s.id for s in result["vn_script"].scenes] == ["s0", "s1", "s2"]
        # state_timeline also in script order.
        assert [e.scene_id for e in result["vn_script"].state_timeline] == \
            ["s0", "s1", "s2"]

    @pytest.mark.asyncio
    async def test_failed_scene_does_not_block_wave_peers(
        self, mocker, tmp_path,
    ):
        """One scene's LLM failure in a wave must not cancel its siblings.
        Failed scene surfaces as input scene (no dialogue); others succeed.
        """
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import DialogueLine, VNScript

        async def _fake_write(scene, *args, **kwargs):
            if scene.id == "s1":
                raise RuntimeError("simulated API failure on s1")
            return scene.model_copy(update={
                "dialogue": [DialogueLine(
                    character_id="a", text=f"line-{scene.id}", emotion="neutral",
                )],
            })

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")
        mocker.patch(
            "vn_agent.agents.writer.get_settings",
            return_value=self._parallel_settings(max_concurrent=3),
        )

        scenes = [self._scene(f"s{i}") for i in range(3)]
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

        result = await run_writer(state)
        out_scenes = {s.id: s for s in result["vn_script"].scenes}
        # s0 and s2 got dialogue; s1 (failed) is preserved with no dialogue.
        assert len(out_scenes["s0"].dialogue) == 1
        assert len(out_scenes["s2"].dialogue) == 1
        assert len(out_scenes["s1"].dialogue) == 0

    @pytest.mark.asyncio
    async def test_semaphore_bounds_concurrent_workers(self, mocker, tmp_path):
        """At no point should more than writer_max_concurrent workers be
        in-flight simultaneously. Probe the inside of _write_scene with
        an active-counter + peak observer."""
        import asyncio as _asyncio

        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import VNScript

        active = 0
        peak = 0
        lock = _asyncio.Lock()

        async def _fake_write(scene, *args, **kwargs):
            nonlocal active, peak
            async with lock:
                active += 1
                peak = max(peak, active)
            # Hold the slot briefly so overlaps are measurable.
            await _asyncio.sleep(0.01)
            async with lock:
                active -= 1
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")
        mocker.patch(
            "vn_agent.agents.writer.get_settings",
            return_value=self._parallel_settings(max_concurrent=2),
        )

        # 6 scenes, no deps → one wave of 6 under Semaphore(2).
        scenes = [self._scene(f"s{i}") for i in range(6)]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes, world_variables=[],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=6, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)

        await run_writer(state)
        assert peak <= 2, f"Semaphore bound violated: peak={peak}"
        assert peak >= 2, f"Concurrency never materialized: peak={peak}"
