"""v4 P3-2: chat turn lifecycle. Zero real API — classification is injected
via `llm=`, and the local_regen execute path monkeypatches
`local_regen._write_scene` (the one real LLM call inside `regenerate_scene`)
so the test exercises the actual splice/diff/persist logic without a network
call, mirroring `tests/test_integration/test_resume_flow.py`'s fixture reuse.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from vn_agent.chat_ops.intent_router import IntentClassification
from vn_agent.chat_ops.orchestrator import ChatTurnResult, execute_turn, preview_turn
from vn_agent.schema.script import VNScript

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "pipeline_states"

_BLACKBOARD = {
    "theme": "A Quiet Semester",
    "scene_scripts": [
        {"id": "scene_1_arrival", "title": "The Arrival"},
        {"id": "scene_2_meeting", "title": "The Meeting"},
    ],
    "characters": {"alice": {"name": "Alice"}, "bob": {"name": "Bob"}},
}


def _copy_fixture(tmp_path: Path) -> Path:
    src = _FIXTURES / "post_writer_complete"
    dst = tmp_path / "run"
    shutil.copytree(src, dst)
    return dst


def _fake_classify_llm(classification: IntentClassification):
    async def _llm(system, user, schema=None, model=None, caller=None):  # noqa: ARG001
        return classification
    return _llm


class TestPreviewTurnNonMutating:
    @pytest.mark.asyncio
    async def test_explain_resolves_inline(self, tmp_path):
        classify = IntentClassification(intent="explain", confidence=0.9, instruction="why")

        async def llm(system, user, schema=None, model=None, caller=None):  # noqa: ARG001
            if schema is IntentClassification:
                return classify
            return type("M", (), {"content": "Because the theme calls for it."})()

        result = await preview_turn(str(tmp_path), _BLACKBOARD, "why does it end there?", llm=llm)
        assert result.intent == "explain"
        assert result.requires_confirmation is False
        assert result.executed is True
        assert result.success is True
        assert "theme" in result.result_text.lower()

    @pytest.mark.asyncio
    async def test_unknown_resolves_inline_with_clarification(self, tmp_path):
        classify = IntentClassification(intent="unknown", confidence=0.2, reasoning="ambiguous target")
        llm = _fake_classify_llm(classify)
        result = await preview_turn(str(tmp_path), _BLACKBOARD, "fix that thing", llm=llm)
        assert result.intent == "unknown"
        assert result.requires_confirmation is False
        assert result.executed is False
        assert "ambiguous target" in result.preview_text


class TestPreviewTurnMutatingDoesNotTouchDisk:
    @pytest.mark.asyncio
    async def test_local_regen_preview_leaves_vn_script_untouched(self, tmp_path):
        d = _copy_fixture(tmp_path)
        before = (d / "vn_script.json").read_bytes()

        classify = IntentClassification(
            intent="local_regen", target_scene_id="scene_1_arrival",
            instruction="make it funnier", confidence=0.9,
        )
        result = await preview_turn(str(d), _BLACKBOARD, "make it funnier", llm=_fake_classify_llm(classify))

        assert result.intent == "local_regen"
        assert result.requires_confirmation is True
        assert result.executed is False
        assert "scene_1_arrival" in result.preview_text
        assert (d / "vn_script.json").read_bytes() == before, "preview must never mutate disk"


class TestExecuteTurnLocalRegen:
    @pytest.mark.asyncio
    async def test_execute_regenerates_scene_and_produces_diff(self, tmp_path, monkeypatch):
        d = _copy_fixture(tmp_path)

        from vn_agent.schema.script import DialogueLine, Scene

        async def fake_write_scene(scene, script, char_desc, revision_feedback, output_dir, **kwargs):  # noqa: ARG001
            return scene.model_copy(update={
                "dialogue": [DialogueLine(character_id="alice", text="A much funnier line.", emotion="happy")],
            })

        monkeypatch.setattr("vn_agent.agents.local_regen._write_scene", fake_write_scene)

        preview = ChatTurnResult(
            turn_id="t1", message="make it funnier", intent="local_regen", confidence=0.9,
            target_scene_id="scene_1_arrival", target_character_id=None,
            instruction="make it funnier", reasoning="", preview_text="...",
            requires_confirmation=True,
        )
        result = await execute_turn(str(d), preview)

        assert result.executed is True
        assert result.success is True
        assert result.requires_confirmation is False
        assert "3" in result.result_text and "1" in result.result_text  # 3 → 1 lines
        assert result.diff is not None
        assert "-The Arrival: opening line." in result.diff or "opening line" in result.diff
        assert "+alice: A much funnier line." in result.diff or "funnier line" in result.diff

        # Actually persisted.
        fresh = VNScript.model_validate_json((d / "vn_script.json").read_text(encoding="utf-8"))
        scene = next(s for s in fresh.scenes if s.id == "scene_1_arrival")
        assert len(scene.dialogue) == 1
        assert scene.dialogue[0].text == "A much funnier line."

    @pytest.mark.asyncio
    async def test_execute_logs_to_audit_trail(self, tmp_path, monkeypatch):
        d = _copy_fixture(tmp_path)

        from vn_agent.schema.script import DialogueLine

        async def fake_write_scene(scene, script, char_desc, revision_feedback, output_dir, **kwargs):  # noqa: ARG001
            return scene.model_copy(update={"dialogue": [DialogueLine(character_id="alice", text="x", emotion="neutral")]})

        monkeypatch.setattr("vn_agent.agents.local_regen._write_scene", fake_write_scene)

        preview = ChatTurnResult(
            turn_id="t2", message="shorten it", intent="local_regen", confidence=0.9,
            target_scene_id="scene_1_arrival", target_character_id=None,
            instruction="shorten it", reasoning="", preview_text="...",
            requires_confirmation=True,
        )
        await execute_turn(str(d), preview)

        log_path = d / "chat_ops" / "turns.jsonl"
        assert log_path.exists()
        rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 1
        assert rows[0]["turn_id"] == "t2"
        assert rows[0]["executed"] is True
        assert rows[0]["success"] is True

    @pytest.mark.asyncio
    async def test_execute_missing_scene_id_fails_cleanly(self, tmp_path):
        d = _copy_fixture(tmp_path)
        preview = ChatTurnResult(
            turn_id="t3", message="rewrite it", intent="local_regen", confidence=0.5,
            target_scene_id=None, target_character_id=None,
            instruction="rewrite it", reasoning="", preview_text="...",
            requires_confirmation=True,
        )
        result = await execute_turn(str(d), preview)
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_regen_error_from_missing_script_fails_cleanly(self, tmp_path):
        """No vn_script.json at all in output_dir — RegenError should
        resolve to a failed (not raised) turn."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        preview = ChatTurnResult(
            turn_id="t4", message="rewrite it", intent="local_regen", confidence=0.9,
            target_scene_id="scene_1_arrival", target_character_id=None,
            instruction="rewrite it", reasoning="", preview_text="...",
            requires_confirmation=True,
        )
        result = await execute_turn(str(empty_dir), preview)
        assert result.success is False
        assert "vn_script.json" in result.error


_NEW_CHARACTER_JSON = json.dumps({
    "id": "mira",
    "name": "Mira",
    "color": "#8899ff",
    "role": "rival",
    "personality": "Competitive, dry-humoured, allergic to sincerity.",
    "background": "Transferred in last spring after quitting a conservatory.",
    "speech_fingerprint": ["clips sentences short", "never says sorry"],
})


def _fake_designer_llm(payload: str):
    """Stands in for the profile-synthesis call. Same signature the router
    fake uses, so both flow through ainvoke_llm's call shape."""
    async def _llm(system, user, schema=None, model=None, caller=None):  # noqa: ARG001
        return type("M", (), {"content": payload})()
    return _llm


class TestExecuteAddCharacter:
    """M1: the intent has a real executor. It writes a full profile into
    characters.json and the script's cast, and deliberately does NOT
    rewrite existing scenes — being in the cast and being on stage are
    different things, and the result text says which one happened."""

    @pytest.mark.asyncio
    async def test_writes_profile_to_disk_and_cast(self, tmp_path, monkeypatch):
        run = _copy_fixture(tmp_path)
        monkeypatch.setattr(
            "vn_agent.services.llm.ainvoke_llm",
            _fake_designer_llm(_NEW_CHARACTER_JSON),
        )
        # Skip the visual designer entirely — covered by its own tests.
        async def _no_visual(profile, output_dir, characters):  # noqa: ARG001
            return profile, "Sprites skipped (test)."
        monkeypatch.setattr(
            "vn_agent.chat_ops.executors.add_character._fill_visual_profile",
            _no_visual,
        )

        preview = ChatTurnResult(
            turn_id="t5", message="add a rival pianist", intent="add_character",
            confidence=0.8, target_scene_id=None, target_character_id=None,
            instruction="add a rival pianist", reasoning="", preview_text="...",
            requires_confirmation=True,
        )
        result = await execute_turn(str(run), preview)

        assert result.success is True, result.result_text
        chars = json.loads((run / "characters.json").read_text(encoding="utf-8"))
        assert chars["mira"]["name"] == "Mira"
        assert chars["mira"]["role"] == "rival"
        script = VNScript.model_validate_json(
            (run / "vn_script.json").read_text(encoding="utf-8"))
        assert "mira" in script.characters
        # Cast membership, not stage presence.
        assert all("mira" not in s.characters_present for s in script.scenes)

        rows = [json.loads(line) for line in
                (run / "chat_ops" / "turns.jsonl").read_text(encoding="utf-8").splitlines()]
        assert rows[0]["intent"] == "add_character"

    @pytest.mark.asyncio
    async def test_duplicate_id_is_refused_not_overwritten(self, tmp_path, monkeypatch):
        """Silently replacing an existing cast member would erase a
        character the creator already wrote scenes around."""
        run = _copy_fixture(tmp_path)
        existing = json.loads((run / "characters.json").read_text(encoding="utf-8"))
        victim = next(iter(existing))
        payload = json.loads(_NEW_CHARACTER_JSON)
        payload["id"] = victim
        monkeypatch.setattr(
            "vn_agent.services.llm.ainvoke_llm",
            _fake_designer_llm(json.dumps(payload)),
        )

        preview = ChatTurnResult(
            turn_id="t5b", message="add someone", intent="add_character",
            confidence=0.8, target_scene_id=None, target_character_id=None,
            instruction="add someone", reasoning="", preview_text="...",
            requires_confirmation=True,
        )
        result = await execute_turn(str(run), preview)

        assert result.success is False
        after = json.loads((run / "characters.json").read_text(encoding="utf-8"))
        assert after[victim] == existing[victim]

    @pytest.mark.asyncio
    async def test_non_ascii_name_still_yields_a_renpy_safe_id(self, tmp_path, monkeypatch):
        """The id becomes a Ren'Py variable name, so a model that returns
        a Chinese id would break the compile, not just the turn."""
        run = _copy_fixture(tmp_path)
        payload = json.loads(_NEW_CHARACTER_JSON)
        payload["id"] = "林晚"
        payload["name"] = "Lin Wan"
        monkeypatch.setattr(
            "vn_agent.services.llm.ainvoke_llm",
            _fake_designer_llm(json.dumps(payload)),
        )
        async def _no_visual(profile, output_dir, characters):  # noqa: ARG001
            return profile, ""
        monkeypatch.setattr(
            "vn_agent.chat_ops.executors.add_character._fill_visual_profile",
            _no_visual,
        )

        preview = ChatTurnResult(
            turn_id="t5c", message="add Lin Wan", intent="add_character",
            confidence=0.8, target_scene_id=None, target_character_id=None,
            instruction="add Lin Wan", reasoning="", preview_text="...",
            requires_confirmation=True,
        )
        result = await execute_turn(str(run), preview)

        assert result.success is True, result.result_text
        chars = json.loads((run / "characters.json").read_text(encoding="utf-8"))
        assert "lin_wan" in chars


class TestExecuteEditAsset:
    """M1: library-swap first, regeneration second, and an honest answer
    when neither is available."""

    @pytest.mark.asyncio
    async def test_library_hit_swaps_without_generation(self, tmp_path, monkeypatch):
        run = _copy_fixture(tmp_path)
        script = VNScript.model_validate_json(
            (run / "vn_script.json").read_text(encoding="utf-8"))
        scene_id = script.scenes[0].id

        class _Hit:
            id = "dusk_rooftop"
            license = "CC0"
            attribution = "opengameart"

        called = {"regen": False}
        monkeypatch.setattr(
            "vn_agent.assets.library.try_library_hit",
            lambda *a, **k: _Hit(),
        )
        monkeypatch.setattr(
            "vn_agent.assets.library.record_library_hit", lambda *a, **k: None,
        )

        async def _regen(*a, **k):
            called["regen"] = True
            raise AssertionError("must not regenerate after a library hit")
        monkeypatch.setattr(
            "vn_agent.chat_ops.executors.edit_asset._regenerate", _regen,
        )

        preview = ChatTurnResult(
            turn_id="t6", message="make it dusk", intent="edit_asset",
            confidence=0.75, target_scene_id=scene_id, target_character_id=None,
            instruction="make it dusk", reasoning="", preview_text="...",
            requires_confirmation=True,
        )
        result = await execute_turn(str(run), preview)

        assert result.success is True, result.result_text
        assert called["regen"] is False
        assert "CC0" in result.result_text
        after = VNScript.model_validate_json(
            (run / "vn_script.json").read_text(encoding="utf-8"))
        assert "[library:dusk_rooftop" in (after.scenes[0].background_prompt or "")

    @pytest.mark.asyncio
    async def test_mock_mode_miss_reports_the_manual_route(self, tmp_path, monkeypatch):
        """Mock mode blocks image generation by design, so a library miss
        has no automated path. Saying so is a useful answer — failing the
        turn would read as a bug."""
        from vn_agent.services.llm import mock_mode_var

        run = _copy_fixture(tmp_path)
        script = VNScript.model_validate_json(
            (run / "vn_script.json").read_text(encoding="utf-8"))
        monkeypatch.setattr(
            "vn_agent.assets.library.try_library_hit", lambda *a, **k: None,
        )

        preview = ChatTurnResult(
            turn_id="t6b", message="make it dusk", intent="edit_asset",
            confidence=0.75, target_scene_id=script.scenes[0].id,
            target_character_id=None, instruction="make it dusk", reasoning="",
            preview_text="...", requires_confirmation=True,
        )
        token = mock_mode_var.set(True)
        try:
            result = await execute_turn(str(run), preview)
        finally:
            mock_mode_var.reset(token)

        assert result.success is True
        assert "Asset panel" in result.result_text

    @pytest.mark.asyncio
    async def test_sprite_request_is_declined_with_a_reason(self, tmp_path):
        run = _copy_fixture(tmp_path)
        preview = ChatTurnResult(
            turn_id="t6c", message="redraw Alice smiling", intent="edit_asset",
            confidence=0.8, target_scene_id=None, target_character_id="alice",
            instruction="redraw Alice smiling", reasoning="", preview_text="...",
            requires_confirmation=True,
        )
        result = await execute_turn(str(run), preview)
        assert result.success is True
        assert "sprite" in result.result_text.lower()


class TestLowConfidenceFallback:
    """L2: below the confidence threshold a mutating intent asks instead of
    offering a confirm card. L1 alone only protects a creator who reads the
    card — a confident-looking card for a 0.3 guess invites a reflexive yes."""

    @pytest.mark.asyncio
    async def test_low_confidence_becomes_a_question(self, tmp_path):
        classify = IntentClassification(
            intent="local_regen", confidence=0.3,
            target_scene_id="scene_1_arrival", instruction="",
        )
        result = await preview_turn(
            str(tmp_path), _BLACKBOARD, "make it better",
            llm=_fake_classify_llm(classify),
        )
        assert result.requires_confirmation is False
        assert result.executed is False
        assert "30%" in result.result_text
        # The guess is preserved for the audit trail even though we didn't act.
        assert result.intent == "local_regen"

    @pytest.mark.asyncio
    async def test_confident_intent_still_gets_a_confirm_card(self, tmp_path):
        classify = IntentClassification(
            intent="local_regen", confidence=0.85,
            target_scene_id="scene_1_arrival", instruction="make it rain",
        )
        result = await preview_turn(
            str(tmp_path), _BLACKBOARD, "make it rain in the arrival scene",
            llm=_fake_classify_llm(classify),
        )
        assert result.requires_confirmation is True

    @pytest.mark.asyncio
    async def test_threshold_is_configurable(self, tmp_path):
        import vn_agent.config as config_module

        classify = IntentClassification(
            intent="local_regen", confidence=0.7,
            target_scene_id="scene_1_arrival", instruction="make it rain",
        )
        token = config_module._settings_override.set(
            config_module.Settings(chat_intent_confidence_threshold=0.9),
        )
        try:
            result = await preview_turn(
                str(tmp_path), _BLACKBOARD, "make it rain",
                llm=_fake_classify_llm(classify),
            )
        finally:
            config_module._settings_override.reset(token)
        assert result.requires_confirmation is False

    @pytest.mark.asyncio
    async def test_clarification_names_what_is_missing(self, tmp_path):
        classify = IntentClassification(
            intent="local_regen", confidence=0.4, target_scene_id=None,
            instruction="",
        )
        result = await preview_turn(
            str(tmp_path), _BLACKBOARD, "fix it",
            llm=_fake_classify_llm(classify),
        )
        assert "which scene" in result.result_text
        assert "what to change" in result.result_text


class TestExecuteTurnGuards:
    @pytest.mark.asyncio
    async def test_execute_rejects_non_mutating_intent(self, tmp_path):
        preview = ChatTurnResult(
            turn_id="t7", message="why?", intent="explain", confidence=0.9,
            target_scene_id=None, target_character_id=None,
            instruction="", reasoning="", preview_text="...",
            requires_confirmation=False,
        )
        with pytest.raises(ValueError, match="non-mutating"):
            await execute_turn(str(tmp_path), preview)
