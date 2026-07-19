"""v4 P0-7: mock_mode_var ContextVar routing in ainvoke_llm."""
from __future__ import annotations

import asyncio

import pytest

from vn_agent.services.llm import ainvoke_llm, mock_mode_var


@pytest.mark.asyncio
async def test_default_off_does_not_short_circuit(monkeypatch):
    """ContextVar defaults to False → ainvoke_llm should NOT touch mock."""
    # Sabotage mock_ainvoke so we notice if it's mistakenly invoked.
    called = {"n": 0}

    async def _sabotage(*a, **kw):  # noqa: ARG001
        called["n"] += 1
        raise AssertionError("mock_ainvoke should not have been called")

    monkeypatch.setattr("vn_agent.services.mock_llm.mock_ainvoke", _sabotage)

    # Sabotage the real path too so we don't burn money if the guard broke.
    async def _fake_invoke(*a, **kw):  # noqa: ARG001
        return "REAL"

    monkeypatch.setattr("vn_agent.services.llm._invoke_once_async", _fake_invoke)

    out = await ainvoke_llm("sys", "user", caller="test")
    assert out == "REAL"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_context_true_routes_to_mock(monkeypatch):
    """Setting mock_mode_var → ainvoke_llm reaches mock_ainvoke, skips real."""
    async def _sabotage_real(*a, **kw):  # noqa: ARG001
        raise AssertionError("real _invoke_once_async should not be called under mock ContextVar")

    monkeypatch.setattr("vn_agent.services.llm._invoke_once_async", _sabotage_real)

    async def _fake_mock(*a, **kw):  # noqa: ARG001
        return "MOCK"

    monkeypatch.setattr("vn_agent.services.mock_llm.mock_ainvoke", _fake_mock)

    token = mock_mode_var.set(True)
    try:
        out = await ainvoke_llm("sys", "user", caller="test")
        assert out == "MOCK"
    finally:
        mock_mode_var.reset(token)


@pytest.mark.asyncio
async def test_context_isolated_across_concurrent_tasks(monkeypatch):
    """Two concurrent asyncio tasks with different mock flags don't collide."""
    async def _fake_real(*a, **kw):  # noqa: ARG001
        return "REAL"

    async def _fake_mock(*a, **kw):  # noqa: ARG001
        return "MOCK"

    monkeypatch.setattr("vn_agent.services.llm._invoke_once_async", _fake_real)
    monkeypatch.setattr("vn_agent.services.mock_llm.mock_ainvoke", _fake_mock)

    async def _mock_task():
        token = mock_mode_var.set(True)
        try:
            # Give the other task a chance to run in between the set and the
            # ainvoke_llm call; if ContextVar leaks, this is where it would.
            await asyncio.sleep(0)
            return await ainvoke_llm("sys", "user", caller="mock_task")
        finally:
            mock_mode_var.reset(token)

    async def _real_task():
        await asyncio.sleep(0)
        return await ainvoke_llm("sys", "user", caller="real_task")

    results = await asyncio.gather(_mock_task(), _real_task())
    assert results == ["MOCK", "REAL"]


@pytest.mark.asyncio
async def test_mock_ainvoke_receives_schema_kwarg(monkeypatch):
    """When called with schema=T under mock ContextVar, the schema is forwarded."""
    received = {}

    async def _capturing_mock(system, user, schema=None, **kw):  # noqa: ARG001
        received["schema"] = schema
        received["caller"] = kw.get("caller")
        return "CAPTURED"

    monkeypatch.setattr("vn_agent.services.mock_llm.mock_ainvoke", _capturing_mock)

    class DummySchema:
        pass

    token = mock_mode_var.set(True)
    try:
        out = await ainvoke_llm(
            "sys", "user",
            schema=DummySchema,
            caller="unit_test",
        )
    finally:
        mock_mode_var.reset(token)

    assert out == "CAPTURED"
    assert received["schema"] is DummySchema
    assert received["caller"] == "unit_test"
