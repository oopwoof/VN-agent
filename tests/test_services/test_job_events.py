"""Tests for the per-job event bus.

Covers publish_node (v4 P6 pipeline visibility) and the subscribe/close
contract it rides on. This module had no test coverage before P6.
"""
from __future__ import annotations

import asyncio

from vn_agent.services import job_events


async def _wait_for_subscriber(job_id: str) -> None:
    """subscribe() registers its queue lazily on first __anext__, so a bare
    sleep(0) is not enough to guarantee the subscriber is live."""
    for _ in range(100):
        if job_events._queues.get(job_id):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"no subscriber registered for {job_id}")


async def _drain(job_id: str, n: int) -> list[dict]:
    """Collect exactly n events from a fresh subscriber."""
    out: list[dict] = []
    async for event in job_events.subscribe(job_id):
        out.append(event)
        if len(out) >= n:
            break
    return out


async def test_publish_node_emits_node_event():
    job_id = "job-node-1"
    task = asyncio.create_task(_drain(job_id, 1))
    await _wait_for_subscriber(job_id)

    token = job_events.current_job_id.set(job_id)
    try:
        job_events.publish_node("writer", "Writer creating dialogue")
    finally:
        job_events.current_job_id.reset(token)

    events = await asyncio.wait_for(task, timeout=1.0)
    assert events == [
        {"event": "node", "node": "writer", "label": "Writer creating dialogue"}
    ]


async def test_publish_node_is_noop_without_job_context():
    """No current_job_id (CLI runs, tests) must not raise and must not
    deliver — same contract as publish_scene_ready."""
    job_id = "job-node-2"
    task = asyncio.create_task(_drain(job_id, 1))
    await _wait_for_subscriber(job_id)

    job_events.publish_node("writer", "must not be delivered")

    token = job_events.current_job_id.set(job_id)
    try:
        job_events.publish_node("reviewer", "sentinel")
    finally:
        job_events.current_job_id.reset(token)

    events = await asyncio.wait_for(task, timeout=1.0)
    assert events == [
        {"event": "node", "node": "reviewer", "label": "sentinel"}
    ]


async def test_scene_ready_and_node_events_share_one_stream():
    """The SSE endpoint is a generic forwarder; both event types must arrive
    in publish order on the same subscriber."""
    job_id = "job-node-3"
    task = asyncio.create_task(_drain(job_id, 2))
    await _wait_for_subscriber(job_id)

    token = job_events.current_job_id.set(job_id)
    try:
        job_events.publish_node("writer", "Writer creating dialogue")
        job_events.publish_scene_ready({"id": "s1", "title": "开场"})
    finally:
        job_events.current_job_id.reset(token)

    events = await asyncio.wait_for(task, timeout=1.0)
    assert events[0]["event"] == "node"
    assert events[1] == {"event": "scene_ready", "scene": {"id": "s1", "title": "开场"}}
