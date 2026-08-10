"""Per-job event bus for streaming pipeline progress (v4 P2 ⑤ streaming playback).

Publish side (writer.py): best-effort `publish_scene_ready(scene_dict)` call
after each scene is finalized, using the ContextVar-scoped job_id set by the
web layer for the duration of a generation run. Mirrors token_tracker's
per-job ContextVar pattern (see `services/token_tracker.py`).

Subscribe side (web/app.py SSE endpoint): `subscribe(job_id)` returns an
async generator that yields events as they're published, ending after a
terminal `done`/`failed` event.

In-process only (module-level dict of asyncio.Queue) — fine for the current
single-process FastAPI deployment; would need Redis pub/sub or similar to
scale beyond one worker.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# Set by the web layer for the duration of a generation run so pipeline code
# (writer.py) can publish without threading job_id through every call site.
current_job_id: ContextVar[str | None] = ContextVar("current_job_id", default=None)

_queues: dict[str, list[asyncio.Queue]] = {}


def publish(job_id: str, event: dict) -> None:
    """Fan out `event` to every active subscriber of `job_id`.

    Best-effort — never raises. No-op if nobody has subscribed yet (no
    buffering/replay in M0; a client that connects after a scene fired
    simply doesn't get that event and falls back to the final blackboard
    fetch, same as before streaming existed).
    """
    for q in list(_queues.get(job_id, [])):
        try:
            q.put_nowait(event)
        except Exception as e:  # noqa: BLE001 — best-effort, never break the pipeline
            logger.debug(f"job_events publish failed for {job_id}: {e}")


def publish_scene_ready(scene: dict) -> None:
    """Publish a scene_ready event to whichever job is active in this async
    context. No-op if `current_job_id` was never set (CLI runs, tests)."""
    job_id = current_job_id.get()
    if not job_id:
        return
    publish(job_id, {"event": "scene_ready", "scene": scene})


def publish_node(node: str, label: str) -> None:
    """Publish a graph-node transition to whichever job is active in this
    async context.

    v4 P6: the pipeline already emits one `graph.astream()` update per node,
    but the web layer used to collapse that into a single `progress` string
    which the frontend then had to substring-match to guess where it was.
    This publishes the node identity structurally instead. No-op if
    `current_job_id` was never set (CLI runs, tests, the headless
    `_run_job` path) — same contract as `publish_scene_ready`.
    """
    job_id = current_job_id.get()
    if not job_id:
        return
    publish(job_id, {"event": "node", "node": node, "label": label})


async def subscribe(job_id: str) -> AsyncGenerator[dict, None]:
    """Yield events for `job_id` as they're published; stops after a
    terminal `done`/`failed` event."""
    q: asyncio.Queue = asyncio.Queue()
    _queues.setdefault(job_id, []).append(q)
    try:
        while True:
            event = await q.get()
            yield event
            if event.get("event") in ("done", "failed"):
                break
    finally:
        subs = _queues.get(job_id)
        if subs and q in subs:
            subs.remove(q)
        if subs is not None and not subs:
            _queues.pop(job_id, None)


def close(job_id: str, *, ok: bool = True, error: str | None = None) -> None:
    """Publish the terminal event and drop the job's queue registry."""
    publish(job_id, {"event": "done" if ok else "failed", "error": error})
    _queues.pop(job_id, None)
