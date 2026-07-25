"""v4 P4: /playtest/run and /playtest/report endpoints. Uses job
config.mock=True so the whole request routes through mock_llm.py's
'playtest/judge' fixture — zero real API calls, matching test_chat_endpoints.py's style."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from vn_agent.compiler.project_builder import build_project
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import VNScript
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
    """A job whose output_dir is a REAL built Ren'Py project (game/images/*
    placeholder PNGs on disk) — playtest needs actual asset files to
    composite against, unlike chat_ops which only reads vn_script.json."""
    _, store = test_app
    src = _FIXTURES / "post_writer_complete"
    script = VNScript.model_validate_json((src / "vn_script.json").read_text(encoding="utf-8"))
    raw_chars = json.loads((src / "characters.json").read_text(encoding="utf-8"))
    characters = {k: CharacterProfile.model_validate(v) for k, v in raw_chars.items()}

    output_dir = tmp_path / "run"
    build_project(script, characters, output_dir)

    job_id = "play1234"
    store.create(job_id, script.theme, {"mock": True}, str(output_dir))
    return job_id, output_dir


class TestPlaytestRun:
    def test_404_for_unknown_job(self, client):
        resp = client.post("/api/projects/nonexistent/playtest/run", json={})
        assert resp.status_code == 404

    def test_400_when_no_script_yet(self, client, test_app, tmp_path):
        _, store = test_app
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        store.create("no-script", "theme", {"mock": True}, str(empty_dir))
        resp = client.post("/api/projects/no-script/playtest/run", json={})
        assert resp.status_code == 400

    def test_mock_mode_end_to_end(self, client, seeded_job):
        job_id, output_dir = seeded_job
        resp = client.post(f"/api/projects/{job_id}/playtest/run", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_scenes"] == 5
        assert body["frames_judged"] > 0
        assert all(f["judgment"] is not None for f in body["frames"])
        assert (output_dir / "playtest" / "report.json").exists()
        assert len(list((output_dir / "playtest" / "frames").glob("*.png"))) == len(body["frames"])

    def test_max_frames_override_is_respected(self, client, seeded_job):
        job_id, _ = seeded_job
        resp = client.post(f"/api/projects/{job_id}/playtest/run", json={"max_frames": 2})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["frames"]) <= 2


class TestPlaytestReport:
    def test_404_for_unknown_job(self, client):
        resp = client.get("/api/projects/nonexistent/playtest/report")
        assert resp.status_code == 404

    def test_404_before_any_run(self, client, seeded_job):
        job_id, _ = seeded_job
        resp = client.get(f"/api/projects/{job_id}/playtest/report")
        assert resp.status_code == 404

    def test_200_after_run_matches_run_response(self, client, seeded_job):
        job_id, _ = seeded_job
        run_resp = client.post(f"/api/projects/{job_id}/playtest/run", json={})
        report_resp = client.get(f"/api/projects/{job_id}/playtest/report")

        assert report_resp.status_code == 200
        assert report_resp.json()["generated_at"] == run_resp.json()["generated_at"]
