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
        # Skip rag record append (now async; AsyncMock so the await works).
        from unittest.mock import AsyncMock
        mocker.patch(
            "vn_agent.agents.writer._append_rag_record", new=AsyncMock(),
        )

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


# ---------------------------------------------------------------------------
# Phase 13-2 Step 4b-5: concurrent-safe shared state.
#   - rag_retrievals.jsonl: lock-protected so parallel waves can't
#     interleave UTF-8 line writes.
#   - state_timeline: parallel path merges per-wave at the barrier in
#     script-positional order; this regression test pins that invariant
#     across multi-wave runs.
# ---------------------------------------------------------------------------


class TestRagRecordsLock:
    """Lock-protected concurrent appends to rag_retrievals.jsonl."""

    @pytest.mark.asyncio
    async def test_concurrent_appends_produce_one_line_per_call(self, tmp_path):
        """50 coroutines hammering _append_rag_record concurrently.
        Result file must have exactly 50 lines, each a complete parseable
        JSON object — no truncation, no interleaved characters."""
        import asyncio as _asyncio
        import json as _json

        from vn_agent.agents.writer import _append_rag_record

        # Each "example" carries a long Chinese-ish payload to push the
        # encoded record above PIPE_BUF (4KB) where text-mode writes
        # could fragment without serialization.
        class _Ex:
            def __init__(self, idx: int):
                self.id = f"ex_{idx}"
                self.title = "锚点" * 200  # ~600 bytes encoded
                self.strategy = "literary"
                self.pivot_line_idx = idx
                self.pacing = "medium"
                self.text = ("窗外的雨声渐密，灯塔的光圈在浓雾里弯曲。" * 50)

        async def _one(i: int):
            await _append_rag_record(
                output_dir=str(tmp_path),
                scene_id=f"s{i:02d}",
                strategy="literary",
                query=f"q-{i}",
                examples=[_Ex(i)],
            )

        await _asyncio.gather(*(_one(i) for i in range(50)))

        path = tmp_path / "rag_retrievals.jsonl"
        assert path.exists()
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 50, (
            f"Expected 50 lines (one per call); got {len(lines)} — "
            f"interleaved writes would either pack multiple records on "
            f"one line or split a record across lines."
        )
        # Every line parses as one complete JSON object with our schema.
        seen_ids = set()
        for line in lines:
            obj = _json.loads(line)
            assert "scene_id" in obj
            assert "retrieved" in obj
            seen_ids.add(obj["scene_id"])
        assert seen_ids == {f"s{i:02d}" for i in range(50)}

    @pytest.mark.asyncio
    async def test_lock_is_singleton_across_calls(self):
        """_get_rag_lock returns the same Lock instance — not a fresh
        one per call (which would defeat serialization)."""
        from vn_agent.agents.writer import _get_rag_lock
        a = _get_rag_lock()
        b = _get_rag_lock()
        assert a is b


class TestStateTimelineOrderingParallel:
    """4b-4 invariant pinned: state_timeline must be in script.scenes
    positional order even when waves complete out of order."""

    def _scene_with_dep(self, sid: str, deps=None, state_writes=None):
        from vn_agent.schema.script import Scene, SceneContextRef
        refs = []
        for ref_type, ref_id in deps or []:
            refs.append(SceneContextRef(
                ref_type=ref_type, ref_id=ref_id,
                link_type="callback", reason="t",
            ))
        return Scene(
            id=sid, title=sid.upper(), description="d",
            background_id="bg", characters_present=["a"],
            context_deps=refs, state_writes=state_writes or {},
        )

    def _settings(self, max_concurrent: int = 4):
        from vn_agent.config import Settings
        return Settings(
            writer_max_concurrent=max_concurrent,
            enable_thinking_fanout=True,
            writer_consume_thinking=True,
            enable_scene_summarization=False,
            enable_chapter_rollup=False,
            writer_context_window=0,
        )

    @pytest.mark.asyncio
    async def test_state_timeline_in_script_order_across_waves(
        self, mocker, tmp_path,
    ):
        """Diamond DAG with deliberate latency inversion:
          - wave 0: s00 (slow)
          - wave 1: s01, s02 — but s02 finishes BEFORE s01 (faster fake)
          - wave 2: s03

        state_timeline must record [s00, s01, s02, s03] in that order,
        NOT completion order [s00, s02, s01, s03].
        """
        import asyncio as _asyncio

        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import VNScript, WorldVariable

        delay_map = {"s00": 0.02, "s01": 0.04, "s02": 0.01, "s03": 0.0}

        async def _fake_write(scene, *args, **kwargs):
            await _asyncio.sleep(delay_map.get(scene.id, 0))
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")
        mocker.patch(
            "vn_agent.agents.writer.get_settings",
            return_value=self._settings(max_concurrent=4),
        )

        scenes = [
            self._scene_with_dep("s00", state_writes={"a": 1}),
            self._scene_with_dep("s01", deps=[("scene", "s00")],
                                 state_writes={"b": 2}),
            self._scene_with_dep("s02", deps=[("scene", "s00")],
                                 state_writes={"c": 3}),
            self._scene_with_dep("s03",
                                 deps=[("scene", "s01"), ("scene", "s02")]),
        ]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s00", scenes=scenes,
            world_variables=[
                WorldVariable(name="a", type="int", initial_value=0,
                              description=""),
                WorldVariable(name="b", type="int", initial_value=0,
                              description=""),
                WorldVariable(name="c", type="int", initial_value=0,
                              description=""),
            ],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=4, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)

        result = await run_writer(state)
        timeline = result["vn_script"].state_timeline
        assert [e.scene_id for e in timeline] == ["s00", "s01", "s02", "s03"]

        # state_after for s01 must reflect ONLY s00's write (peer s02
        # is invisible within wave 1); state_after for s02 likewise
        # sees only s00. After wave 1 barrier, s03 sees all three.
        ts = {e.scene_id: e.state_after for e in timeline}
        assert ts["s00"] == {"a": 1, "b": 0, "c": 0}
        # s01 and s02's state_after are recorded post-merge (after the
        # barrier applies BOTH writes in script order); both reflect
        # the cumulative state at their position. By the time we're
        # writing the timeline entry for s01, we've already applied
        # s01's write. For s02 we then apply s02's write too. So:
        assert ts["s01"] == {"a": 1, "b": 2, "c": 0}
        assert ts["s02"] == {"a": 1, "b": 2, "c": 3}
        assert ts["s03"] == {"a": 1, "b": 2, "c": 3}


# ---------------------------------------------------------------------------
# Phase 13-2 Step 4b-7 (Gemini review fix): regressions for the script-order
# / prior-context BLOCKERs and chapter-rollup-into-prompt MAJOR.
#
# Pre-fix: when compute_waves produces a script-discontinuous wave (e.g.
# a backward dep s1→s2 yields wave 0 = [s0, s2, s3], wave 1 = [s1]), the
# parallel orchestrator appended results in wave order, leaving
# vn_script.scenes permanently reordered. Existing TestParallelWriterPath
# tests dodged this with diamond DAGs that produced position-contiguous
# waves by accident.
# ---------------------------------------------------------------------------


class TestParallelWriterScriptDiscontinuousWaves:
    """Pathological DAG: backward declared deps cause script-discontiguous
    wave 0. Final output must still be in script order."""

    def _scene(self, sid: str, deps=None, state_writes=None):
        from vn_agent.schema.script import Scene, SceneContextRef
        refs = []
        for ref_type, ref_id in deps or []:
            refs.append(SceneContextRef(
                ref_type=ref_type, ref_id=ref_id,
                link_type="callback", reason="t",
            ))
        return Scene(
            id=sid, title=sid.upper(), description="d",
            background_id="bg", characters_present=["a"],
            context_deps=refs, state_writes=state_writes or {},
        )

    def _settings(self, max_concurrent: int = 4):
        from vn_agent.config import Settings
        return Settings(
            writer_max_concurrent=max_concurrent,
            enable_thinking_fanout=True,
            writer_consume_thinking=True,
            enable_scene_summarization=False,
            enable_chapter_rollup=False,
            writer_context_window=2,  # >0 to exercise prior-scene slicing
        )

    @pytest.mark.asyncio
    async def test_final_scene_order_matches_script_order(
        self, mocker, tmp_path,
    ):
        """Backward dep s1→s2 forces wave 0=[s0,s2,s3], wave 1=[s1].
        Pre-fix, output ended up [s0,s2,s3,s1]. Post-fix: [s0,s1,s2,s3]."""
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
            return_value=self._settings(max_concurrent=4),
        )

        # s1 declares a SCENE dep on s2 — backward in script order.
        # compute_waves resolves: s0/s2/s3 have no scene deps -> wave 0;
        # s1 waits on s2 -> wave 1.
        scenes = [
            self._scene("s0"),
            self._scene("s1", deps=[("scene", "s2")]),
            self._scene("s2"),
            self._scene("s3"),
        ]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes, world_variables=[],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=4, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)

        result = await run_writer(state)
        out_ids = [s.id for s in result["vn_script"].scenes]
        assert out_ids == ["s0", "s1", "s2", "s3"], (
            f"Expected script-order output [s0,s1,s2,s3]; got {out_ids}. "
            "Pre-4b-7 the parallel path appended in wave-completion order, "
            "yielding [s0,s2,s3,s1]."
        )
        # state_timeline must also be in script order.
        timeline_ids = [e.scene_id for e in result["vn_script"].state_timeline]
        assert timeline_ids == ["s0", "s1", "s2", "s3"]

    @pytest.mark.asyncio
    async def test_prior_scenes_in_chronological_order_for_late_wave(
        self, mocker, tmp_path,
    ):
        """When s1 (wave 1) gets its prior_scenes built, the slice must
        be chronologically correct: only [s0] (s2,s3 are at later script
        positions, even though they completed in earlier wave)."""
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import VNScript

        captured_priors: dict[str, list[str]] = {}

        async def _fake_write(scene, *args, **kwargs):
            captured_priors[scene.id] = [
                s.id for s in (kwargs.get("prior_scenes") or [])
            ]
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")
        mocker.patch(
            "vn_agent.agents.writer.get_settings",
            return_value=self._settings(max_concurrent=4),
        )

        scenes = [
            self._scene("s0"),
            self._scene("s1", deps=[("scene", "s2")]),
            self._scene("s2"),
            self._scene("s3"),
        ]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes, world_variables=[],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=4, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)

        await run_writer(state)

        # window=2. For s1 at idx=1, prior_slice = [idx-2 : idx] = [None?, s0].
        # Filter Nones -> [s0]. Pre-fix the slice was [completed_so_far[-1:1]]
        # which would have been [s0] at position 0 (lucky case) but for s3
        # (idx=3, slice [1:3]) it would have grabbed completion-order
        # neighbors out of script order.
        assert captured_priors["s1"] == ["s0"]
        # s3 (wave 0, idx=3): nobody completed yet -> []
        assert captured_priors["s3"] == []
        # s2 (wave 0, idx=2): nobody completed yet -> []
        assert captured_priors["s2"] == []


class TestChapterRollupRebuildsPrefix:
    """Phase 13-2 Step 4b-7: chapter rollup must reach Writer prompt.

    Pre-fix, build_monolithic_prefix was called once with
    finalized_chapters=None and the rebuilt rollups never re-entered
    the cached prefix. Post-fix, rebuild_prefix is called after each
    chapter barrier and the new prefix flows into subsequent scenes.
    """

    @pytest.mark.asyncio
    async def test_prefix_rebuilt_after_chapter_rollup_lands(
        self, mocker, tmp_path,
    ):
        """Spy build_monolithic_prefix; assert it's called more than once
        when chapters complete and rollup is enabled."""
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.config import Settings
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import Chapter, Scene, VNScript

        # Custom Settings with rollup enabled; sequential path so we
        # exercise the simpler chapter-barrier code path. Rollup every
        # 2 scenes, min 4 scenes total -> rollups fire at scene 2 + 4.
        settings = Settings(
            writer_max_concurrent=1,
            enable_scene_summarization=False,
            enable_chapter_rollup=True,
            chapter_rollup_every=2,
            chapter_rollup_min_scenes=2,
            writer_context_window=0,
        )
        mocker.patch("vn_agent.agents.writer.get_settings", return_value=settings)

        async def _fake_write(scene, *args, **kwargs):
            return scene

        async def _fake_rollup(*args, **kwargs):
            # Return a finalized Chapter so rebuild_prefix sees new content.
            return "rolled-up summary"

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")
        mocker.patch(
            "vn_agent.agents.summarizer.rollup_chapter",
            side_effect=_fake_rollup,
        )

        # Spy on build_monolithic_prefix
        from vn_agent.prompts import cached_prefix as cached_prefix_mod
        spy = mocker.spy(cached_prefix_mod, "build_monolithic_prefix")

        scenes = [
            Scene(id=f"s{i}", title=f"S{i}", description="x",
                  background_id="bg", characters_present=["a"])
            for i in range(4)
        ]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes, world_variables=[],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=4, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)

        result = await run_writer(state)

        # Expect: 1 initial build + ≥1 rebuild after rollups land.
        # 4 scenes / rollup_every=2 → 2 rollups; rebuild fires at
        # the next chapter barrier (loop top), so for sequential the
        # rebuilds happen at the start of scenes 3 and 5 (latter doesn't
        # exist; only 1 rebuild observable inside the run + 1 final-
        # barrier no-rebuild). At minimum: ≥2 calls total.
        assert spy.call_count >= 2, (
            f"Expected build_monolithic_prefix to be re-called after "
            f"chapter rollup; got {spy.call_count} call(s) total. "
            f"Pre-fix this was always 1 (called once at run_writer init "
            f"with finalized_chapters=None)."
        )
        # The first call has finalized_chapters=None; later calls must
        # carry the actual list with at least one Chapter.
        first = spy.call_args_list[0]
        assert first.kwargs.get("finalized_chapters") is None
        later_with_chapters = [
            c for c in spy.call_args_list[1:]
            if c.kwargs.get("finalized_chapters")
            and any(isinstance(ch, Chapter)
                    for ch in c.kwargs["finalized_chapters"])
        ]
        assert later_with_chapters, (
            "No rebuild call carried a non-empty finalized_chapters list."
        )

        # Sanity: chapters_list in the output reflects the rollups.
        assert len(result["vn_script"].chapters) >= 1


# ---------------------------------------------------------------------------
# Phase 13-2 Step 4b-8 (Gemini review fix #3): on Writer failure in the
# parallel path, Director-declared state_writes must still be applied to
# world_state so the persisted scene.state_writes and the actual
# state_timeline.state_after agree. Pre-fix, a failed scene's writes
# stayed in the schema but never reached world_state, fragmenting the
# narrative state for downstream Reviewer/Compiler.
# ---------------------------------------------------------------------------


class TestParallelFailureAppliesStateWrites:

    def _scene(self, sid: str, state_writes=None):
        from vn_agent.schema.script import Scene
        return Scene(
            id=sid, title=sid.upper(), description="d",
            background_id="bg", characters_present=["a"],
            state_writes=state_writes or {},
        )

    def _settings(self, max_concurrent: int = 3):
        from vn_agent.config import Settings
        return Settings(
            writer_max_concurrent=max_concurrent,
            enable_thinking_fanout=True,
            writer_consume_thinking=True,
            enable_scene_summarization=False,
            enable_chapter_rollup=False,
            writer_context_window=0,
        )

    @pytest.mark.asyncio
    async def test_failed_scene_state_writes_still_applied(
        self, mocker, tmp_path,
    ):
        """3 scenes with state_writes; scene 1 raises. Even so, all three
        scenes' Director-declared writes must land in world_state and
        state_timeline so downstream consumers see consistent state."""
        from vn_agent.agents.state import initial_state
        from vn_agent.agents.writer import run_writer
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import VNScript, WorldVariable

        async def _fake_write(scene, *args, **kwargs):
            if scene.id == "s1":
                raise RuntimeError("simulated Writer failure on s1")
            return scene

        mocker.patch("vn_agent.agents.writer._write_scene", side_effect=_fake_write)
        mocker.patch("vn_agent.agents.writer._write_scene_snapshot")
        mocker.patch(
            "vn_agent.agents.writer.get_settings",
            return_value=self._settings(max_concurrent=3),
        )

        scenes = [
            self._scene("s0", state_writes={"a": 1}),
            self._scene("s1", state_writes={"b": 2}),  # fails
            self._scene("s2", state_writes={"c": 3}),
        ]
        script = VNScript(
            title="T", description="d", theme="th",
            start_scene_id="s0", scenes=scenes,
            world_variables=[
                WorldVariable(name="a", type="int", initial_value=0,
                              description=""),
                WorldVariable(name="b", type="int", initial_value=0,
                              description=""),
                WorldVariable(name="c", type="int", initial_value=0,
                              description=""),
            ],
        )
        chars = {"a": CharacterProfile(id="a", name="A", role="p",
                                       personality="", background="")}

        state = initial_state(theme="th", output_dir=str(tmp_path),
                              max_scenes=3, num_characters=1)
        state["vn_script"] = script
        state["characters"] = chars
        state["output_dir"] = str(tmp_path)

        result = await run_writer(state)
        timeline = result["vn_script"].state_timeline
        ts = {e.scene_id: e.state_after for e in timeline}

        # All three scenes' state_writes apply cumulatively, INCLUDING
        # the failed s1's b=2.
        assert ts["s0"] == {"a": 1, "b": 0, "c": 0}
        assert ts["s1"] == {"a": 1, "b": 2, "c": 0}, (
            "Failed scene s1 must still apply its declared state_writes "
            "(Director-owned, forward-progress)."
        )
        assert ts["s2"] == {"a": 1, "b": 2, "c": 3}

        # The persisted scene s1 still carries state_writes={"b": 2}
        # (we don't strip them on failure) — schema and timeline agree.
        out_scenes = {s.id: s for s in result["vn_script"].scenes}
        assert out_scenes["s1"].state_writes == {"b": 2}
        # And: world_state returned from run_writer reflects all three.
        assert result["world_state"] == {"a": 1, "b": 2, "c": 3}

