"""Tests for FastAPI web endpoints."""
from __future__ import annotations

from unittest.mock import patch

import pytest

# Guard: skip if fastapi/httpx not installed
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from vn_agent.web.store import JobStore


@pytest.fixture
def test_app(tmp_path):
    """Create app with a temp SQLite database."""
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


class TestEndpoints:
    def test_list_jobs_empty(self, client):
        resp = client.get("/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_status_not_found(self, client):
        resp = client.get("/status/nonexistent")
        assert resp.status_code == 404

    def test_delete_not_found(self, client):
        resp = client.delete("/jobs/deadbeef")
        assert resp.status_code == 404

    def test_download_not_found(self, client):
        resp = client.get("/download/nonexistent")
        assert resp.status_code == 404

    def test_generate_validation(self, client):
        # Empty theme should fail validation
        resp = client.post("/generate", json={"theme": ""})
        assert resp.status_code == 422

    def test_generate_creates_job(self, test_app):
        app, store = test_app
        client = TestClient(app)

        # Mock the background task to avoid running the full pipeline
        with patch("vn_agent.web.app._run_job"):
            resp = client.post("/generate", json={"theme": "test story"})
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]
        assert len(job_id) == 8

        # Job should exist in store
        job = store.get(job_id)
        assert job is not None
        assert job["theme"] == "test story"

    def test_status_returns_job(self, test_app):
        _, store = test_app
        store.create("abc123", "theme", {}, "/tmp")
        store.update_status("abc123", "running", progress="writing")

        client = TestClient(test_app[0])
        resp = client.get("/status/abc123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["progress"] == "writing"

    def test_list_jobs_returns_entries(self, test_app):
        _, store = test_app
        store.create("j1", "theme1", {}, "/tmp/1")
        store.create("j2", "theme2", {}, "/tmp/2")

        client = TestClient(test_app[0])
        resp = client.get("/jobs")
        assert resp.status_code == 200
        jobs = resp.json()
        assert len(jobs) == 2

    def test_delete_job(self, test_app):
        _, store = test_app
        store.create("aabbccdd", "theme", {}, "/tmp/del")

        client = TestClient(test_app[0])
        resp = client.delete("/jobs/aabbccdd")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == "aabbccdd"
        assert store.get("aabbccdd") is None
