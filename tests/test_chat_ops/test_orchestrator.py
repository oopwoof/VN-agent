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


class TestExecuteTurnUnimplemented:
    @pytest.mark.asyncio
    async def test_add_character_resolves_as_unsuccessful_but_logged(self, tmp_path):
        preview = ChatTurnResult(
            turn_id="t5", message="add a rival character", intent="add_character", confidence=0.8,
            target_scene_id=None, target_character_id=None,
            instruction="add a rival character", reasoning="", preview_text="...",
            requires_confirmation=True,
        )
        result = await execute_turn(str(tmp_path), preview)
        assert result.executed is True
        assert result.success is False
        assert "M0" in result.result_text

        rows = [json.loads(line) for line in (tmp_path / "chat_ops" / "turns.jsonl").read_text(encoding="utf-8").splitlines()]
        assert rows[0]["intent"] == "add_character"

    @pytest.mark.asyncio
    async def test_edit_asset_resolves_as_unsuccessful_but_logged(self, tmp_path):
        preview = ChatTurnResult(
            turn_id="t6", message="swap the background", intent="edit_asset", confidence=0.75,
            target_scene_id="scene_1_arrival", target_character_id=None,
            instruction="swap the background", reasoning="", preview_text="...",
            requires_confirmation=True,
        )
        result = await execute_turn(str(tmp_path), preview)
        assert result.success is False
        assert result.executed is True


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
