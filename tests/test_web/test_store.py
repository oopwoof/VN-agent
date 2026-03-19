"""Tests for SQLite job store."""
from __future__ import annotations

import pytest

from vn_agent.web.store import JobStore


@pytest.fixture
def store(tmp_path):
    s = JobStore(tmp_path / "test_jobs.db")
    yield s
    s.close()


class TestJobStore:
    def test_create_and_get(self, store):
        store.create("job1", "test theme", {"max_scenes": 5}, "/tmp/out")
        job = store.get("job1")
        assert job is not None
        assert job["job_id"] == "job1"
        assert job["theme"] == "test theme"
        assert job["status"] == "pending"
        assert job["config"]["max_scenes"] == 5

    def test_get_nonexistent(self, store):
        assert store.get("nonexistent") is None

    def test_update_status(self, store):
        store.create("job1", "theme", {}, "/tmp")
        store.update_status("job1", "running", progress="step 1")
        job = store.get("job1")
        assert job["status"] == "running"
        assert job["progress"] == "step 1"

    def test_update_errors(self, store):
        store.create("job1", "theme", {}, "/tmp")
        store.update_status("job1", "failed", errors=["something broke"])
        job = store.get("job1")
        assert job["errors"] == ["something broke"]

    def test_list_recent(self, store):
        store.create("job1", "theme1", {}, "/tmp/1")
        store.create("job2", "theme2", {}, "/tmp/2")
        store.create("job3", "theme3", {}, "/tmp/3")
        jobs = store.list_recent(limit=2)
        assert len(jobs) == 2
        # Most recent first
        assert jobs[0]["job_id"] == "job3"

    def test_list_empty(self, store):
        assert store.list_recent() == []

    def test_delete(self, store):
        store.create("job1", "theme", {}, "/tmp")
        assert store.delete("job1") is True
        assert store.get("job1") is None

    def test_delete_nonexistent(self, store):
        assert store.delete("nonexistent") is False

    def test_errors_deserialized_as_list(self, store):
        store.create("job1", "theme", {}, "/tmp")
        job = store.get("job1")
        assert isinstance(job["errors"], list)
        assert job["errors"] == []
