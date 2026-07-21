"""v4 P3: /chat/preview and /chat/execute endpoints. Zero real API — the
underlying classifier/writer calls are patched via unittest.mock.patch on
the ainvoke_llm import sites, matching the existing `test_app.py` style."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from vn_agent.chat_ops.intent_router import IntentClassification
from vn_agent.web.store import JobStore

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "pipeline_states"


@pytest.fixture
def test_app(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = JobStore(db_path)

    import vn_agent.web.app as app_module
    app_module._store = store
    app_module._semaphore = None

    yield app_module.app, store

    store.close()
    app_module._store = None


@pytest.fixture
def client(test_app):
    app, _ = test_app
    return TestClient(app)


@pytest.fixture
def seeded_job(test_app, tmp_path):
    """A job whose output_dir is a real vn_script.json fixture, with a
    blackboard.scene_scripts matching it (as _run_script_generation would
    have left it after a real generation)."""
    _, store = test_app
    output_dir = tmp_path / "run"
    shutil.copytree(_FIXTURES / "post_writer_complete", output_dir)

    job_id = "cafe1234"
    store.create(job_id, "A Quiet Semester", {"mock": False}, str(output_dir))
    script = json.loads((output_dir / "vn_script.json").read_text(encoding="utf-8"))
    bb = {
        "theme": script["theme"],
        "scene_scripts": [
            {"id": s["id"], "title": s["title"], "dialogue": s["dialogue"]}
            for s in script["scenes"]
        ],
        "characters": {"alice": {"name": "Alice"}, "bob": {"name": "Bob"}},
        "_script_json": script,
    }
    store.update_blackboard(job_id, bb)
    return job_id, output_dir


class TestChatPreview:
    def test_404_for_unknown_job(self, client):
        resp = client.post("/api/projects/nonexistent/chat/preview", json={"message": "hi"})
        assert resp.status_code == 404

    def test_explain_resolves_immediately(self, client, seeded_job):
        job_id, _ = seeded_job

        async def fake_ainvoke(system, user, schema=None, model=None, caller=None, **kw):  # noqa: ARG001
            if schema is IntentClassification:
                return IntentClassification(intent="explain", confidence=0.9, instruction="why")
            return type("M", (), {"content": "Because of the theme."})()

        with patch("vn_agent.services.llm.ainvoke_llm", side_effect=fake_ainvoke):
            resp = client.post(f"/api/projects/{job_id}/chat/preview", json={"message": "why does it end?"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "explain"
        assert body["requires_confirmation"] is False
        assert body["executed"] is True

    def test_local_regen_requires_confirmation_and_does_not_touch_disk(self, client, seeded_job):
        job_id, output_dir = seeded_job
        before = (output_dir / "vn_script.json").read_bytes()

        async def fake_ainvoke(system, user, schema=None, model=None, caller=None, **kw):  # noqa: ARG001
            return IntentClassification(
                intent="local_regen", target_scene_id="scene_1_arrival",
                instruction="funnier", confidence=0.9,
            )

        with patch("vn_agent.services.llm.ainvoke_llm", side_effect=fake_ainvoke):
            resp = client.post(f"/api/projects/{job_id}/chat/preview", json={"message": "make scene 1 funnier"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "local_regen"
        assert body["requires_confirmation"] is True
        assert body["executed"] is False
        assert (output_dir / "vn_script.json").read_bytes() == before

    def test_empty_message_rejected(self, client, seeded_job):
        job_id, _ = seeded_job
        resp = client.post(f"/api/projects/{job_id}/chat/preview", json={"message": ""})
        assert resp.status_code == 422


class TestChatExecute:
    def test_404_for_unknown_job(self, client):
        resp = client.post("/api/projects/nonexistent/chat/execute", json={
            "turn_id": "t1", "intent": "local_regen", "confidence": 0.9,
            "target_scene_id": "x",
        })
        assert resp.status_code == 404

    def test_non_mutating_intent_rejected(self, client, seeded_job):
        job_id, _ = seeded_job
        resp = client.post(f"/api/projects/{job_id}/chat/execute", json={
            "turn_id": "t1", "intent": "explain", "confidence": 0.9,
        })
        assert resp.status_code == 400

    def test_execute_local_regen_syncs_blackboard_from_disk(self, client, seeded_job):
        job_id, output_dir = seeded_job

        from vn_agent.schema.script import DialogueLine

        async def fake_write_scene(scene, script, char_desc, revision_feedback, out_dir, **kwargs):  # noqa: ARG001
            return scene.model_copy(update={
                "dialogue": [DialogueLine(character_id="alice", text="Brand new line.", emotion="happy")],
            })

        with patch("vn_agent.agents.local_regen._write_scene", side_effect=fake_write_scene):
            resp = client.post(f"/api/projects/{job_id}/chat/execute", json={
                "turn_id": "t2", "intent": "local_regen", "confidence": 0.9,
                "target_scene_id": "scene_1_arrival", "instruction": "make it different",
                "preview_text": "...",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["diff"]

        # Blackboard re-synced from the on-disk mutation — this is the whole
        # point of the resync step (regenerate_scene writes vn_script.json
        # directly, bypassing the JobStore).
        bb_resp = client.get(f"/api/projects/{job_id}/blackboard")
        scenes = bb_resp.json()["blackboard"]["scene_scripts"]
        scene1 = next(s for s in scenes if s["id"] == "scene_1_arrival")
        assert scene1["dialogue"] == [{"character_id": "alice", "text": "Brand new line.", "emotion": "happy"}]

    def test_execute_add_character_stub_does_not_sync_blackboard(self, client, seeded_job):
        job_id, _ = seeded_job
        resp = client.post(f"/api/projects/{job_id}/chat/execute", json={
            "turn_id": "t3", "intent": "add_character", "confidence": 0.8,
            "instruction": "add a rival", "preview_text": "...",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "M0" in body["result_text"]
