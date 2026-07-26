"""v4 P5 M0: Autopilot entry point + the double-execution/race bugfix.

Zero real API — mock=True routes every LLM call through
services/mock_llm.py fixtures (checked inside ainvoke_llm itself via
mock_mode_var), matching the existing test_app.py / test_chat_endpoints.py
style. No patching of director/writer internals needed.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from vn_agent.autopilot import outcomes as ap_outcomes
from vn_agent.web.store import JobStore


@pytest.fixture(autouse=True)
def _iso_autopilot_root(tmp_path_factory, monkeypatch):
    # Isolate from the real data/autopilot/runs.jsonl for every test in this
    # file, matching the tests/test_feedback convention.
    monkeypatch.setenv(ap_outcomes._DEFAULT_ROOT_ENV, str(tmp_path_factory.mktemp("autopilot_root")))
    yield


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


class TestDoubleExecBugfix:
    """v4 P5: /generate used to unconditionally fire a background _run_job
    task that re-runs the whole graph independently of the SPA's own
    generate-setting/generate-script chain on the same job_id — a real
    double-execution + status-write race (_run_job takes the concurrency
    semaphore, the step-by-step path never does). interactive=True (sent by
    the SPA) must skip _run_job entirely; the default (False) must preserve
    the existing headless-API contract."""

    def test_interactive_true_skips_run_job(self, client):
        with patch("vn_agent.web.app._run_job") as mock_run_job:
            resp = client.post("/generate", json={"theme": "test story", "interactive": True})
        assert resp.status_code == 200
        mock_run_job.assert_not_called()

    def test_interactive_default_false_still_fires_run_job(self, client):
        with patch("vn_agent.web.app._run_job") as mock_run_job:
            resp = client.post("/generate", json={"theme": "test story"})
        assert resp.status_code == 200
        mock_run_job.assert_called_once()


class TestAutopilotPresetResolution:
    def test_autopilot_flag_resolves_preset_into_job_config(self, test_app):
        app, store = test_app
        client = TestClient(app)
        with patch("vn_agent.web.app._run_job"):
            resp = client.post("/generate", json={
                "theme": "a school romance", "autopilot": True, "interactive": True, "mock": True,
            })
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]
        job = store.get(job_id)
        assert job["config"]["preset"] == "autopilot_best"

    def test_no_autopilot_flag_no_preset_in_config(self, test_app):
        app, store = test_app
        client = TestClient(app)
        with patch("vn_agent.web.app._run_job"):
            resp = client.post("/generate", json={"theme": "test story", "interactive": True})
        job_id = resp.json()["job_id"]
        job = store.get(job_id)
        assert "preset" not in job["config"]

    def test_generate_setting_applies_preset_settings_override(self, test_app, tmp_path):
        """The strongest available assertion short of patching every graph
        node: generate_setting() does `settings = get_settings()` and passes
        it straight into _step1_outline's 5th positional arg. Spy on
        _step1_outline to capture exactly the object the endpoint saw."""
        app, store = test_app
        client = TestClient(app)
        job_id = "presetjob1"
        output_dir = tmp_path / "run"
        output_dir.mkdir()
        store.create(job_id, "a lighthouse story", {"mock": True, "preset": "autopilot_best"}, str(output_dir))

        from vn_agent.agents.director import _step1_outline as real_step1

        captured = {}

        async def spy_step1(*args, **kwargs):
            captured["settings"] = args[4] if len(args) > 4 else kwargs.get("settings")
            return await real_step1(*args, **kwargs)

        with patch("vn_agent.agents.director._step1_outline", side_effect=spy_step1):
            resp = client.post(f"/api/projects/{job_id}/generate-setting")

        assert resp.status_code == 200
        assert captured["settings"] is not None
        assert captured["settings"].max_scenes == 10  # autopilot_best override, not the ambient 20
        assert captured["settings"].llm_director_model == "claude-sonnet-4-6"


class _FakeGraph:
    """Stand-in for build_graph() that skips Writer/Reviewer entirely —
    real Writer runs a RAG/lore embedding-model load (sentence-transformers)
    on the first call, which is slow (or hangs with no network access) and
    is unrelated to what these tests need to verify. _run_script_generation's
    own control flow (blackboard building, auto-compile, status updates,
    the settings-override hook, and the new run_meta/outcomes writer) all
    still run for real."""
    async def astream(self, state, stream_mode="updates"):  # noqa: ARG002
        yield {"writer": {"vn_script": state["vn_script"], "characters": state["characters"]}}


class TestAutopilotRunMetaAndOutcomes:
    def test_full_mock_flow_writes_run_meta_and_outcome(self, test_app, tmp_path):
        app, store = test_app
        client = TestClient(app)

        with patch("vn_agent.web.app._run_job"):
            resp = client.post("/generate", json={
                "theme": "a school romance", "autopilot": True, "interactive": True, "mock": True,
                "max_scenes": 4, "num_characters": 2, "text_only": True,
            })
        job_id = resp.json()["job_id"]

        setting_resp = client.post(f"/api/projects/{job_id}/generate-setting")
        assert setting_resp.status_code == 200
        plan = setting_resp.json()["blackboard"]["raw_plan"]

        import asyncio

        import vn_agent.web.app as app_module
        job = store.get(job_id)
        with patch("vn_agent.agents.graph.build_graph", return_value=_FakeGraph()):
            asyncio.run(app_module._run_script_generation(job_id, job, plan))

        status = client.get(f"/status/{job_id}").json()
        assert status["status"] == "completed", status

        job = store.get(job_id)
        output_dir = job["output_dir"]
        meta = json.loads((Path(output_dir) / "run_meta.json").read_text(encoding="utf-8"))
        assert meta["preset"] == "autopilot_best"
        assert meta["job_id"] == job_id
        assert meta["wall_time_seconds"] >= 0
        assert meta["script"]["scene_count"] > 0

        records = ap_outcomes.load_all()
        assert len(records) == 1
        assert records[0].job_id == job_id
        assert records[0].preset_used == "autopilot_best"
        assert records[0].success is True
        assert records[0].scene_count > 0

    def test_no_preset_skips_run_meta_write(self, test_app, tmp_path):
        """Non-Autopilot jobs (no config['preset']) must not get a
        run_meta.json/outcomes row — this is scoped to preset-flagged jobs
        only, not a blanket change to every job's behavior."""
        app, store = test_app
        client = TestClient(app)

        with patch("vn_agent.web.app._run_job"):
            resp = client.post("/generate", json={
                "theme": "a school romance", "interactive": True, "mock": True,
                "max_scenes": 4, "num_characters": 2, "text_only": True,
            })
        job_id = resp.json()["job_id"]

        setting_resp = client.post(f"/api/projects/{job_id}/generate-setting")
        plan = setting_resp.json()["blackboard"]["raw_plan"]

        import asyncio

        import vn_agent.web.app as app_module
        job = store.get(job_id)
        with patch("vn_agent.agents.graph.build_graph", return_value=_FakeGraph()):
            asyncio.run(app_module._run_script_generation(job_id, job, plan))

        output_dir = store.get(job_id)["output_dir"]
        assert not (Path(output_dir) / "run_meta.json").exists()
        assert ap_outcomes.load_all() == []
