"""v4 P0-review-hang unit tests for services/pending_debug.py."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from vn_agent.services import pending_debug


class TestSerializePending:
    def test_body_contains_prompt_model_caller_timeout(self):
        body = pending_debug._serialize_pending(
            "sys prompt", "user prompt",
            model="claude-sonnet-4", caller="reviewer", timeout=120.0,
        )
        assert "sys prompt" in body
        assert "user prompt" in body
        assert "claude-sonnet-4" in body
        assert "reviewer" in body
        assert "120.0" in body

    def test_schema_name_included_when_given(self):
        body = pending_debug._serialize_pending(
            "sys", "user",
            model=None, caller="test", timeout=60.0, schema_name="MySchema",
        )
        assert "MySchema" in body

    def test_no_schema_line_when_absent(self):
        body = pending_debug._serialize_pending(
            "sys", "user", model=None, caller="test", timeout=60.0,
        )
        assert "schema:" not in body


class TestPendingLifecycle:
    def test_success_deletes_pending_writes_done(self, tmp_path):
        pending = pending_debug._pending_path(tmp_path, "reviewer_r0")
        pending_debug._write_pending(pending, "PENDING BODY")
        assert pending.exists()

        pending_debug._finalize_success(pending, "the response content")

        assert not pending.exists()
        done = pending.with_name("reviewer_r0.txt")
        assert done.exists()
        assert "the response content" in done.read_text(encoding="utf-8")

    def test_error_renames_to_error_with_traceback(self, tmp_path):
        pending = pending_debug._pending_path(tmp_path, "reviewer_r0")
        pending_debug._write_pending(pending, "PENDING BODY")

        try:
            raise RuntimeError("simulated hang / crash")
        except RuntimeError as e:
            pending_debug._finalize_error(pending, e)

        assert not pending.exists()
        err = pending.with_name("reviewer_r0.error.txt")
        assert err.exists()
        text = err.read_text(encoding="utf-8")
        assert "PENDING BODY" in text
        assert "simulated hang / crash" in text
        assert "RuntimeError" in text


class TestPendingFilesEnumerator:
    def test_returns_only_pending_files(self, tmp_path):
        debug = tmp_path / "debug"
        debug.mkdir()
        (debug / "a.pending.txt").write_text("x")
        (debug / "b.pending.txt").write_text("y")
        (debug / "c.txt").write_text("z")
        (debug / "d.error.txt").write_text("w")

        pending_files = pending_debug.pending_files(tmp_path)
        names = sorted(p.name for p in pending_files)
        assert names == ["a.pending.txt", "b.pending.txt"]

    def test_missing_debug_dir_returns_empty(self, tmp_path):
        assert pending_debug.pending_files(tmp_path) == []


class _Msg:
    def __init__(self, content: str):
        self.content = content


class TestAinvokeWithPendingDebug:
    @pytest.mark.asyncio
    async def test_success_path_returns_response(self, tmp_path, monkeypatch):
        async def fake_ainvoke(sys, user, schema=None, **kwargs):  # noqa: ARG001
            return _Msg("hello world")

        monkeypatch.setattr("vn_agent.services.llm.ainvoke_llm", fake_ainvoke)

        result = await pending_debug.ainvoke_with_pending_debug(
            "sys", "user",
            output_dir=tmp_path,
            name="reviewer_r0",
            model="fake-model",
            caller="test",
            timeout=5.0,
        )
        assert result.content == "hello world"
        # Pending deleted; done file written.
        assert not (tmp_path / "debug" / "reviewer_r0.pending.txt").exists()
        assert (tmp_path / "debug" / "reviewer_r0.txt").exists()

    @pytest.mark.asyncio
    async def test_timeout_leaves_error_file(self, tmp_path, monkeypatch):
        async def slow_ainvoke(sys, user, **kwargs):  # noqa: ARG001
            await asyncio.sleep(10)   # will never finish before timeout
            return _Msg("late")

        monkeypatch.setattr("vn_agent.services.llm.ainvoke_llm", slow_ainvoke)

        with pytest.raises(asyncio.TimeoutError):
            await pending_debug.ainvoke_with_pending_debug(
                "sys prompt (kept small so the assert reads cleanly)",
                "user prompt",
                output_dir=tmp_path,
                name="reviewer_r0",
                caller="test",
                timeout=0.05,
            )

        assert not (tmp_path / "debug" / "reviewer_r0.pending.txt").exists()
        err = tmp_path / "debug" / "reviewer_r0.error.txt"
        assert err.exists()
        text = err.read_text(encoding="utf-8")
        # The pending body is preserved inside the error file for post-mortem.
        assert "user prompt" in text
        assert "TimeoutError" in text or "CancelledError" in text

    @pytest.mark.asyncio
    async def test_arbitrary_exception_captured(self, tmp_path, monkeypatch):
        async def failing_ainvoke(sys, user, **kwargs):  # noqa: ARG001
            raise ValueError("api key rejected")

        monkeypatch.setattr("vn_agent.services.llm.ainvoke_llm", failing_ainvoke)

        with pytest.raises(ValueError):
            await pending_debug.ainvoke_with_pending_debug(
                "sys", "user",
                output_dir=tmp_path,
                name="reviewer_r0",
                caller="test",
                timeout=5.0,
            )

        err = tmp_path / "debug" / "reviewer_r0.error.txt"
        assert err.exists()
        assert "api key rejected" in err.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_default_timeout_falls_back_to_settings(self, tmp_path, monkeypatch):
        """When timeout=None, we consult settings.reviewer_timeout_seconds."""
        recorded = {}

        async def fake_ainvoke(sys, user, **kwargs):  # noqa: ARG001
            return _Msg("ok")

        # Sabotage `asyncio.wait_for` to capture the timeout value.
        real_wait_for = asyncio.wait_for

        async def spying_wait_for(coro, timeout):
            recorded["timeout"] = timeout
            return await real_wait_for(coro, timeout)

        monkeypatch.setattr("vn_agent.services.llm.ainvoke_llm", fake_ainvoke)
        monkeypatch.setattr("vn_agent.services.pending_debug.asyncio.wait_for", spying_wait_for)

        await pending_debug.ainvoke_with_pending_debug(
            "sys", "user",
            output_dir=tmp_path,
            name="reviewer_r0",
            caller="test",
            timeout=None,
        )

        # Whatever settings.reviewer_timeout_seconds resolves to should be
        # a positive float; the default is 300.
        assert isinstance(recorded["timeout"], (int, float))
        assert recorded["timeout"] > 0


class TestConcurrentCallsIsolated:
    @pytest.mark.asyncio
    async def test_two_calls_write_distinct_pending_files(self, tmp_path, monkeypatch):
        """Two concurrent wrapped calls must not stomp each other's pending
        files. Distinct `name` slugs guarantee different filenames."""
        seen_pending_at_time_of_call: dict[str, set[str]] = {"a": set(), "b": set()}

        async def snapshot_ainvoke(sys, user, **kwargs):  # noqa: ARG001
            # At call-time snapshot which pending files exist on disk.
            debug_dir = tmp_path / "debug"
            names = {p.name for p in debug_dir.glob("*.pending.txt")}
            caller_name = kwargs.get("caller", "")
            if caller_name.endswith("a"):
                seen_pending_at_time_of_call["a"] |= names
            elif caller_name.endswith("b"):
                seen_pending_at_time_of_call["b"] |= names
            await asyncio.sleep(0)  # let other coroutine progress
            return _Msg(f"resp-{caller_name}")

        monkeypatch.setattr("vn_agent.services.llm.ainvoke_llm", snapshot_ainvoke)

        async def call(name: str, caller: str):
            return await pending_debug.ainvoke_with_pending_debug(
                "sys", "user",
                output_dir=tmp_path,
                name=name,
                caller=caller,
                timeout=5.0,
            )

        results = await asyncio.gather(
            call("reviewer_a", "reviewer_a"),
            call("reviewer_b", "reviewer_b"),
        )
        assert [r.content for r in results] == ["resp-reviewer_a", "resp-reviewer_b"]
        assert "reviewer_a.pending.txt" in seen_pending_at_time_of_call["a"]
        assert "reviewer_b.pending.txt" in seen_pending_at_time_of_call["b"]
        # Both cleaned up after success.
        assert list((tmp_path / "debug").glob("*.pending.txt")) == []
