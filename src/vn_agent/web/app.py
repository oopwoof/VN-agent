"""FastAPI backend for VN-Agent generation.

Endpoints:
    POST   /generate       — start a generation job
    GET    /status/{job_id} — poll job status
    GET    /download/{job_id} — download output as zip
    GET    /jobs           — list recent jobs
    DELETE /jobs/{job_id}  — delete a job and its output
    POST   /generate/stream — SSE streaming outline preview
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from vn_agent.web.store import JobStore

logger = logging.getLogger(__name__)

# ── Configuration from environment ──────────────────────────────────────────

_DB_PATH = os.environ.get("VN_AGENT_DB_PATH", "vn_jobs.db")
_MAX_CONCURRENT = int(os.environ.get("VN_AGENT_MAX_CONCURRENT", "3"))
_OUTPUT_DIR = os.environ.get("VN_AGENT_OUTPUT_DIR", "")
_MOCK_MODE = os.environ.get("VN_AGENT_MOCK", "").lower() in ("1", "true", "yes")


@asynccontextmanager
async def _lifespan(application: FastAPI):  # noqa: ARG001
    """Patch LLM calls with mock responses if VN_AGENT_MOCK is set."""
    logger.info(f"VN_AGENT_MOCK={os.environ.get('VN_AGENT_MOCK')!r}, _MOCK_MODE={_MOCK_MODE}")
    if _MOCK_MODE:
        from unittest.mock import patch as _patch

        from vn_agent.services.mock_llm import mock_ainvoke

        targets = [
            "vn_agent.agents.director.ainvoke_llm",
            "vn_agent.agents.writer.ainvoke_llm",
            "vn_agent.agents.reviewer.ainvoke_llm",
            "vn_agent.agents.character_designer.ainvoke_llm",
            "vn_agent.agents.scene_artist.ainvoke_llm",
        ]
        patches = [_patch(t, side_effect=mock_ainvoke) for t in targets]
        for p in patches:
            p.start()
        logger.info("Mock mode enabled — all LLM calls patched")
        yield
        for p in patches:
            p.stop()
    else:
        yield


app = FastAPI(title="VN-Agent API", version="0.3.0", lifespan=_lifespan)

# CORS — allow frontend dev on different port
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_store: JobStore | None = None
_semaphore: asyncio.Semaphore | None = None


def _get_store() -> JobStore:
    global _store
    if _store is None:
        _store = JobStore(_DB_PATH)
    return _store


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    return _semaphore


# ── Request / response schemas ───────────────────────────────────────────────

class GenerateRequest(BaseModel):
    theme: str = Field(..., min_length=1, max_length=500)
    max_scenes: int = Field(default=10, ge=1, le=50)
    text_only: bool = False
    num_characters: int = Field(default=3, ge=1, le=10)
    # v4 P0-7: per-request mock. Overrides real LLM calls with the fixture
    # dispatcher in `services/mock_llm.py`. Zero API cost, useful for dev
    # + validation dry-runs. Server-wide `VN_AGENT_MOCK=1` (see _lifespan)
    # still short-circuits everything even when this is False.
    mock: bool = False
    # P5 Autopilot: when True, resolve_preset(theme) picks a preset name
    # (M0: always "autopilot_best") stored in the job's config blob and
    # applied via a per-job Settings ContextVar override in generate_setting/
    # _run_script_generation.
    autopilot: bool = False
    # v4 P5 bugfix: pre-existing double-execution bug — this endpoint used
    # to unconditionally fire a background _run_job task that runs the whole
    # graph independently (writing a zip, never touching SSE/blackboard),
    # WHILE the SPA also independently drives generate-setting ->
    # generate-script on the same job_id (the path that actually feeds SSE +
    # VNPreview). Every SPA-driven generation was silently running the full
    # pipeline twice, and _run_job takes the concurrency semaphore while the
    # step-by-step path doesn't — a real race on the same job row, not just
    # wasted API spend. interactive=True (sent by the SPA) skips _run_job
    # entirely. Default False preserves the headless API contract
    # (/generate -> /status -> /download) for any caller that only ever
    # hits this one endpoint.
    interactive: bool = False


class GenerateResponse(BaseModel):
    job_id: str


class StatusResponse(BaseModel):
    status: str  # "pending" | "running" | "completed" | "failed"
    progress: str
    errors: list[str]


class JobSummary(BaseModel):
    job_id: str
    theme: str
    status: str
    progress: str
    created_at: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    store = _get_store()
    job_id = uuid.uuid4().hex[:8]

    if _OUTPUT_DIR:
        output_dir = Path(_OUTPUT_DIR) / f"vn_{job_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = Path(tempfile.mkdtemp(prefix=f"vn_{job_id}_"))

    config = req.model_dump()
    if req.autopilot:
        from vn_agent.autopilot.resolver import resolve_preset
        config["preset"] = resolve_preset(req.theme)
    store.create(job_id, req.theme, config, str(output_dir))
    if not req.interactive:
        asyncio.create_task(_run_job(job_id, req, output_dir))
    return GenerateResponse(job_id=job_id)


@app.get("/status/{job_id}", response_model=StatusResponse)
async def status(job_id: str):
    job = _get_store().get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return StatusResponse(status=job["status"], progress=job["progress"], errors=job["errors"])


@app.get("/download/{job_id}")
async def download(job_id: str):
    job = _get_store().get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Job not completed (status={job['status']})")

    output_dir = job.get("output_dir", "")
    if not output_dir or not Path(output_dir).exists():
        raise HTTPException(status_code=404, detail="Output directory not found")

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    zip_path = Path(tmp.name)
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", output_dir)

    def _cleanup():
        zip_path.unlink(missing_ok=True)

    return FileResponse(
        path=str(zip_path),
        filename=f"vn_{job_id}.zip",
        media_type="application/zip",
        background=BackgroundTask(_cleanup),
    )


@app.get("/jobs", response_model=list[JobSummary])
async def list_jobs(limit: int = 20):
    jobs = _get_store().list_recent(limit)
    return [
        JobSummary(
            job_id=j["job_id"],
            theme=j["theme"],
            status=j["status"],
            progress=j["progress"],
            created_at=j["created_at"],
        )
        for j in jobs
    ]


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    # Validate job_id format to prevent path traversal
    if not re.fullmatch(r"[a-f0-9]{8}", job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id format")

    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Clean up output directory with path containment check
    output_dir = job.get("output_dir", "")
    if output_dir and Path(output_dir).exists():
        resolved = Path(output_dir).resolve()
        if _OUTPUT_DIR:
            base = Path(_OUTPUT_DIR).resolve()
            if not str(resolved).startswith(str(base)):
                raise HTTPException(status_code=403, detail="Output directory outside allowed base")
        shutil.rmtree(resolved, ignore_errors=True)

    store.delete(job_id)
    return {"deleted": job_id}


@app.post("/generate/stream")
async def generate_stream(req: GenerateRequest):
    """Stream a quick LLM response (e.g. story outline) via SSE.

    Useful for real-time feedback during the planning phase.
    Returns Server-Sent Events with token chunks.
    """
    from vn_agent.prompts.templates import DIRECTOR_OUTLINE_SYSTEM
    from vn_agent.services.streaming import astream_sse
    from vn_agent.strategies.narrative import format_strategies_for_prompt

    strategies = format_strategies_for_prompt()
    system = DIRECTOR_OUTLINE_SYSTEM.format(strategies=strategies)
    user_prompt = (
        f"Create a brief visual novel story outline for: {req.theme}\n"
        f"Max scenes: {req.max_scenes}, Characters: {req.num_characters}"
    )

    return StreamingResponse(
        astream_sse(system, user_prompt, caller="web/stream"),
        media_type="text/event-stream",
    )


# ── Step-by-step project APIs (Sprint 2) ────────────────────────────────────


class SettingUpdate(BaseModel):
    """User edits to world setting, characters, or outline."""
    world_setting: dict | None = None
    characters: dict | None = None
    plot_outline: dict | None = None


@app.post("/api/projects/{job_id}/generate-setting")
async def generate_setting(job_id: str):
    """Run Director only — generate world setting, characters, outline. Save to blackboard."""
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    store.update_status(job_id, "running", progress="Director planning story structure")

    # Per-job token tracker for the setting-generation phase
    from vn_agent.services.token_tracker import TokenTracker, current_tracker
    from vn_agent.services.llm import mock_mode_var

    config = job.get("config", {})
    job_tracker = TokenTracker()
    tracker_token = current_tracker.set(job_tracker)
    mock_token = mock_mode_var.set(bool(config.get("mock", False)))
    # P5 Autopilot: per-job Settings override, re-derived from the job's own
    # config blob (ContextVars don't propagate across separate HTTP requests,
    # so this must be re-set here — mirrors mock_token above, not set once
    # at job-creation time).
    preset = config.get("preset")
    settings_token = None
    if preset:
        from vn_agent.autopilot.resolver import build_settings
        from vn_agent.config import _settings_override
        settings_token = _settings_override.set(build_settings(preset))
    if config.get("mock"):
        logger.info(f"[{job_id}/generate-setting] running in per-request mock mode")
    try:
        from vn_agent.agents.director import _merge_outline_details, _step1_outline, _step2_details
        from vn_agent.config import get_settings

        settings = get_settings()
        output_dir = job.get("output_dir", ".")

        outline = await _step1_outline(
            job["theme"],
            config.get("max_scenes", 10),
            config.get("num_characters", 3),
            output_dir,
            settings,
        )

        details = await _step2_details(outline, output_dir, settings)
        plan = _merge_outline_details(outline, details)

        # Build blackboard from Director output
        blackboard = {
            "theme": job["theme"],
            "world_setting": {
                "title": plan.get("title", ""),
                "description": plan.get("description", ""),
            },
            "characters": {
                c.get("id", f"char_{i}"): c
                for i, c in enumerate(plan.get("characters", []))
            },
            "plot_outline": {
                "scenes": plan.get("scenes", []),
                "start_scene_id": plan.get("start_scene_id", ""),
            },
            "raw_plan": plan,
            "token_usage": job_tracker.summary_dict(),
        }

        store.update_blackboard(job_id, blackboard)
        store.update_status(job_id, "setting_generated", progress="Setting ready for review")
        return {"status": "setting_generated", "blackboard": blackboard}

    except Exception as e:
        logger.exception(f"generate-setting failed for {job_id}")
        store.update_status(job_id, "failed", errors=[str(e)])
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        current_tracker.reset(tracker_token)
        mock_mode_var.reset(mock_token)
        if settings_token is not None:
            from vn_agent.config import _settings_override
            _settings_override.reset(settings_token)


@app.get("/api/projects/{job_id}/blackboard")
async def get_blackboard(job_id: str):
    """Return the current blackboard state."""
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"blackboard": job.get("blackboard", {})}


@app.put("/api/projects/{job_id}/setting")
async def update_setting(job_id: str, update: SettingUpdate):
    """User edits setting fields on the blackboard."""
    store = _get_store()
    bb = store.get_blackboard(job_id)
    if not bb:
        raise HTTPException(status_code=404, detail="No blackboard found")

    if update.world_setting is not None:
        bb["world_setting"] = {**bb.get("world_setting", {}), **update.world_setting}
    if update.characters is not None:
        bb["characters"] = update.characters
    if update.plot_outline is not None:
        bb["plot_outline"] = {**bb.get("plot_outline", {}), **update.plot_outline}

    store.update_blackboard(job_id, bb)
    store.update_status(job_id, "setting_confirmed", progress="Setting confirmed by user")
    return {"status": "updated", "blackboard": bb}


@app.post("/api/projects/{job_id}/generate-script")
async def generate_script(job_id: str):
    """Run Writer + Reviewer on the confirmed setting. Returns when complete."""
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    bb = job.get("blackboard", {})
    plan = bb.get("raw_plan")
    if not plan:
        raise HTTPException(status_code=400, detail="No setting generated yet")

    store.update_status(job_id, "running", progress="Writer creating dialogue")
    asyncio.create_task(_run_script_generation(job_id, job, plan))
    return {"status": "script_generating"}


@app.get("/api/projects/{job_id}/stream/scenes")
async def stream_scenes(job_id: str):
    """v4 P2 ⑤: SSE stream of `scene_ready` events as Writer finishes each
    scene, so the frontend can start VN playback before the whole script is
    done. Ends after a `done`/`failed` event. Connect right before calling
    POST .../generate-script — events fired before a subscriber connects are
    not replayed (M0: no buffering), so a late connect just misses early
    scenes and the client falls back to the final blackboard fetch.
    """
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from vn_agent.services import job_events

    async def _gen():
        async for event in job_events.subscribe(job_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


class SceneUpdate(BaseModel):
    """User edits to a single scene's dialogue."""
    dialogue: list[dict] | None = None
    title: str | None = None
    description: str | None = None


@app.put("/api/projects/{job_id}/script/{scene_id}")
async def update_scene(job_id: str, scene_id: str, update: SceneUpdate):
    """User edits a single scene in the blackboard."""
    store = _get_store()
    bb = store.get_blackboard(job_id)
    scenes = bb.get("scene_scripts", [])

    found = False
    for s in scenes:
        if s.get("id") == scene_id:
            if update.dialogue is not None:
                s["dialogue"] = update.dialogue
            if update.title is not None:
                s["title"] = update.title
            if update.description is not None:
                s["description"] = update.description
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Scene {scene_id} not found")

    bb["scene_scripts"] = scenes
    # Also update the serialized script
    script_json = bb.get("_script_json", {})
    for sj in script_json.get("scenes", []):
        if sj.get("id") == scene_id:
            if update.dialogue is not None:
                sj["dialogue"] = update.dialogue
            if update.title is not None:
                sj["title"] = update.title
            if update.description is not None:
                sj["description"] = update.description
            break
    bb["_script_json"] = script_json

    store.update_blackboard(job_id, bb)
    return {"status": "updated", "scene_id": scene_id}


# ── Chat Ops (v4 P3) ─────────────────────────────────────────────────────────
# Beyond-workflow editing: after a script exists, a creator can address a
# specific scene/character in natural language instead of re-running the
# whole pipeline. L1 safety net (see chat_ops/orchestrator.py docstring):
# every mutating intent returns a preview and waits for an explicit confirm
# via a separate call before touching any file.

class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ChatTurnRequest(BaseModel):
    """Echo of a previously-returned preview turn, sent back to /chat/execute
    to confirm it. The client is not trusted to invent a turn's classification
    fields — this is the FULL preview payload round-tripped, not just an id,
    so execute_turn always acts on exactly what was previewed."""
    turn_id: str
    intent: str
    confidence: float
    target_scene_id: str | None = None
    target_character_id: str | None = None
    instruction: str = ""
    reasoning: str = ""
    preview_text: str = ""


@app.post("/api/projects/{job_id}/chat/preview")
async def chat_preview(job_id: str, req: ChatMessageRequest):
    """Classify a chat message and return a preview. Non-mutating intents
    (explain/unknown) are already resolved in the response — nothing more
    to call. Mutating intents (local_regen/add_character/edit_asset) need a
    follow-up POST to /chat/execute with this response's fields to actually run."""
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from vn_agent.chat_ops.orchestrator import preview_turn
    from vn_agent.services.llm import mock_mode_var

    bb = job.get("blackboard", {})
    output_dir = job.get("output_dir", ".")
    # v4 P0-7 pattern: per-request mock, scoped to this call only.
    mock_token = mock_mode_var.set(bool(job.get("config", {}).get("mock", False)))
    try:
        result = await preview_turn(output_dir, bb, req.message)
    finally:
        mock_mode_var.reset(mock_token)
    return result.to_dict()


@app.post("/api/projects/{job_id}/chat/execute")
async def chat_execute(job_id: str, req: ChatTurnRequest):
    """Execute a previously-previewed mutating turn. Re-syncs the blackboard
    from disk afterward for local_regen, since regenerate_scene() writes
    vn_script.json directly rather than going through the JobStore."""
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if req.intent not in ("local_regen", "add_character", "edit_asset"):
        raise HTTPException(status_code=400, detail=f"'{req.intent}' has no execute step — it resolves in preview")

    from vn_agent.chat_ops.orchestrator import ChatTurnResult
    from vn_agent.chat_ops.orchestrator import execute_turn as _execute_turn
    from vn_agent.services.llm import mock_mode_var

    output_dir = job.get("output_dir", ".")
    preview = ChatTurnResult(
        turn_id=req.turn_id, message="", intent=req.intent, confidence=req.confidence,
        target_scene_id=req.target_scene_id, target_character_id=req.target_character_id,
        instruction=req.instruction, reasoning=req.reasoning,
        preview_text=req.preview_text, requires_confirmation=True,
    )
    mock_token = mock_mode_var.set(bool(job.get("config", {}).get("mock", False)))
    try:
        result = await _execute_turn(output_dir, preview)
    finally:
        mock_mode_var.reset(mock_token)

    if result.success and req.intent == "local_regen":
        try:
            from vn_agent.schema.script import VNScript
            script_path = Path(output_dir) / "vn_script.json"
            fresh_script = VNScript.model_validate_json(script_path.read_text(encoding="utf-8"))
            bb = store.get_blackboard(job_id)
            bb["scene_scripts"] = _scenes_to_blackboard(fresh_script)
            bb["_script_json"] = fresh_script.model_dump()
            store.update_blackboard(job_id, bb)
        except Exception as e:
            logger.warning(f"chat_execute: blackboard re-sync from disk failed for {job_id}: {e}")

    return result.to_dict()


# ── PlaytestAgent (P4 M0) ────────────────────────────────────────────────────
# Opt-in post-generation health check: composites Pillow frames (no real
# Ren'Py execution — see playtest/frame_compositor.py docstring for why),
# judges each with a vision LLM, writes a report. Report-only in M0 —
# nothing here writes back into the generation pipeline.

class PlaytestRunRequest(BaseModel):
    max_frames: int | None = None


@app.post("/api/projects/{job_id}/playtest/run")
async def run_playtest_endpoint(job_id: str, req: PlaytestRunRequest = PlaytestRunRequest()):
    """Run PlaytestAgent against the job's current on-disk script. Requires
    vn_script.json to already exist (i.e. build_project() has run at least once)."""
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    output_dir = job.get("output_dir", "")
    if not output_dir or not (Path(output_dir) / "vn_script.json").exists():
        raise HTTPException(status_code=400, detail="No compiled script yet — generate first")

    from vn_agent.playtest.agent import PlaytestError, run_playtest
    from vn_agent.services.llm import mock_mode_var

    mock_token = mock_mode_var.set(bool(job.get("config", {}).get("mock", False)))
    try:
        report = await run_playtest(output_dir, max_frames=req.max_frames)
    except PlaytestError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        mock_mode_var.reset(mock_token)

    return report.model_dump()


@app.get("/api/projects/{job_id}/playtest/report")
async def get_playtest_report(job_id: str):
    """Return the most recent playtest report for this job, if one exists."""
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    output_dir = Path(job.get("output_dir", ""))
    report_path = output_dir / "playtest" / "report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No playtest report yet — run playtest first")
    return json.loads(report_path.read_text(encoding="utf-8"))


@app.get("/api/projects/{job_id}/export-script")
async def export_script(job_id: str):
    """Export the current script as JSON."""
    store = _get_store()
    bb = store.get_blackboard(job_id)
    script_json = bb.get("_script_json")
    if not script_json:
        raise HTTPException(status_code=400, detail="No script generated yet")
    return script_json


# ── Asset management (Sprint 4) ─────────────────────────────────────────────

_PLACEHOLDER_PNG_SIZE = 67
_PLACEHOLDER_OGG_SIZE = 44
_IMG_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_AUDIO_EXTENSIONS = {".ogg", ".mp3", ".wav"}
# v4 P0: text upload extensions (md/txt/pdf/docx). Pipeline chunks these
# into user_upload-scope AnnotatedSessions and feeds them into the lore
# RAG pool. See assets/text_ingest.py.
_TEXT_EXTENSIONS = {".md", ".txt", ".markdown", ".pdf", ".docx"}
_MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
_MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB
_MAX_TEXT_SIZE = 20 * 1024 * 1024  # 20MB (world-lore docs can be long)

_MIME_MAP = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".webp": "image/webp", ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav"}


def _is_placeholder(file_path: Path) -> bool:
    if not file_path.exists():
        return True
    size = file_path.stat().st_size
    return size <= _PLACEHOLDER_PNG_SIZE or size <= _PLACEHOLDER_OGG_SIZE


def _asset_url(job_id: str, rel_path: str) -> str:
    return f"/api/projects/{job_id}/assets/file/{rel_path}"


@app.get("/api/projects/{job_id}/assets")
async def list_assets(job_id: str):
    """List all assets in the project with placeholder detection."""
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    output_dir = Path(job.get("output_dir", ""))
    bb = job.get("blackboard", {})
    scenes = bb.get("scene_scripts", [])
    chars = bb.get("characters", bb.get("_characters_json", {}))

    backgrounds = []
    bg_seen: set[str] = set()
    for s in scenes:
        bg_id = s.get("background_id", "")
        if bg_id and bg_id not in bg_seen:
            bg_seen.add(bg_id)
            rel = f"game/images/backgrounds/{bg_id}.png"
            backgrounds.append({
                "id": bg_id, "path": rel,
                "is_placeholder": _is_placeholder(output_dir / rel),
                "url": _asset_url(job_id, rel),
            })

    characters = []
    for char_id in chars:
        for emotion in ["neutral", "happy", "sad"]:
            rel = f"game/images/characters/{char_id}/{emotion}.png"
            characters.append({
                "char_id": char_id, "emotion": emotion, "path": rel,
                "is_placeholder": _is_placeholder(output_dir / rel),
                "url": _asset_url(job_id, rel),
            })

    bgm_list = []
    bgm_seen: set[str] = set()
    for s in scenes:
        music = s.get("music") or {}
        mood = music.get("mood") if isinstance(music, dict) else None
        if not mood:
            strategy = s.get("narrative_strategy", "neutral")
            mood = strategy if strategy else "neutral"
        if mood and mood not in bgm_seen:
            bgm_seen.add(mood)
            rel = f"game/audio/bgm/{mood}.ogg"
            bgm_list.append({
                "mood": mood, "path": rel,
                "is_placeholder": _is_placeholder(output_dir / rel),
                "url": _asset_url(job_id, rel),
            })

    return {"backgrounds": backgrounds, "characters": characters, "bgm": bgm_list}


@app.get("/api/projects/{job_id}/assets/file/{path:path}")
async def serve_asset(job_id: str, path: str):
    """Serve an asset file from the project output directory."""
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    output_dir = Path(job.get("output_dir", ""))
    file_path = (output_dir / path).resolve()

    if not str(file_path).startswith(str(output_dir.resolve())):
        raise HTTPException(status_code=403, detail="Path traversal denied")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    ext = file_path.suffix.lower()
    media_type = _MIME_MAP.get(ext, "application/octet-stream")
    return FileResponse(str(file_path), media_type=media_type)


@app.post("/api/projects/{job_id}/assets/upload")
async def upload_asset(
    job_id: str,
    file: UploadFile,
    asset_type: str = Form(...),
    asset_id: str = Form(...),
    # v4 P0: optional provenance for text uploads — creator declares
    # license so the export gate can trust it. Defaults keep the endpoint
    # backwards-compatible for existing image/audio callers.
    license: str = Form("user_owned"),
):
    """Upload an asset file.

    - `background` / `character_sprite` / `bgm`  → image/audio placeholder replace
    - `text` (v4 P0)                             → md/txt/pdf/docx chunked into
                                                    user_upload RAG pool
    """
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not re.fullmatch(r"[a-zA-Z0-9_/.-]+", asset_id):
        raise HTTPException(status_code=400, detail="Invalid asset_id format")

    output_dir = Path(job.get("output_dir", ""))
    ext = Path(file.filename or "").suffix.lower()

    if asset_type == "background":
        target = output_dir / "game" / "images" / "backgrounds" / f"{asset_id}.png"
        allowed_ext = _IMG_EXTENSIONS
        max_size = _MAX_IMAGE_SIZE
    elif asset_type == "character_sprite":
        target = output_dir / "game" / "images" / "characters" / f"{asset_id}.png"
        allowed_ext = _IMG_EXTENSIONS
        max_size = _MAX_IMAGE_SIZE
    elif asset_type == "bgm":
        target = output_dir / "game" / "audio" / "bgm" / f"{asset_id}.ogg"
        allowed_ext = _AUDIO_EXTENSIONS
        max_size = _MAX_AUDIO_SIZE
    elif asset_type == "text":
        # Text uploads don't write to output_dir — they persist to
        # data/uploads/{job_id}/ and feed the lore RAG at generation time.
        if ext not in _TEXT_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid text format {ext}, allowed: {sorted(_TEXT_EXTENSIONS)}",
            )
        content = await file.read()
        if len(content) > _MAX_TEXT_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Text file too large ({len(content)} bytes), max {_MAX_TEXT_SIZE}",
            )

        from vn_agent.assets import text_ingest, upload_store

        try:
            chunks = text_ingest.ingest_upload(
                content,
                file.filename or asset_id,
                source="upload",
                license=license,
            )
        except ImportError as exc:
            # Missing optional dep (pypdf / python-docx) — actionable message.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).exception(
                "Text ingest failed for job %s filename=%r", job_id, file.filename,
            )
            raise HTTPException(
                status_code=500, detail=f"Text ingest failed: {exc}"
            ) from exc

        if not chunks:
            raise HTTPException(status_code=400, detail="Uploaded document produced zero chunks (empty or unreadable)")

        upload_store.save_raw(job_id, file.filename or asset_id, content)
        jsonl_path = upload_store.save_chunks(job_id, chunks)
        summary = upload_store.summarize(job_id)

        return {
            "status": "uploaded",
            "asset_type": "text",
            "asset_id": asset_id,
            "size": len(content),
            "chunks": len(chunks),
            "cjk_dominant": chunks[0].source_meta.get("cjk_dominant", False),
            "jsonl_path": str(jsonl_path),
            "summary": summary,
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unknown asset_type: {asset_type}")

    # Path traversal check (image/audio branches only)
    if not str(target.resolve()).startswith(str(output_dir.resolve())):
        raise HTTPException(status_code=403, detail="Path traversal denied")

    # Extension check
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"Invalid file format {ext}, allowed: {allowed_ext}")

    # Size check
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail=f"File too large ({len(content)} bytes), max {max_size}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    return {"status": "uploaded", "asset_type": asset_type, "asset_id": asset_id, "size": len(content)}


class FeedbackRequest(BaseModel):
    """v4 P1-1: creator 👍/👎 payload. Reason is optional but strongly
    encouraged — reason-less records skip the BM25 index because they have
    no signal, only counter increment."""
    verdict: Literal["up", "down"]
    job_id: str | None = None
    scene_id: str | None = None
    reason: str | None = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    context: dict = Field(default_factory=dict)


@app.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest):
    """Persist a feedback record to the flywheel JSONL. Returns id + summary
    so the frontend can update its running counter without a second call."""
    from vn_agent.feedback import store as fb_store

    try:
        record = fb_store.FeedbackRecord(
            verdict=req.verdict,
            job_id=req.job_id,
            scene_id=req.scene_id,
            reason=req.reason,
            tags=req.tags,
            context=req.context,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        fb_store.append(record)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Feedback persist failed: {e}") from e

    return {
        "status": "recorded",
        "id": record.id,
        "summary": fb_store.summarize(),
    }


@app.get("/api/feedback/summary")
async def feedback_summary():
    """Dashboard-friendly counters. Used by the frontend widget to show
    total feedback + rough ratio of up/down."""
    from vn_agent.feedback import store as fb_store
    return fb_store.summarize()


@app.delete("/api/projects/{job_id}/assets/upload")
async def delete_upload(job_id: str, filename: str | None = None):
    """v4 P0-upload-delete: remove uploaded doc chunks from the RAG pool.

    Two modes:
      - `?filename=<name>` deletes just that file's chunks (byte-exact
        match on `source_meta.filename`). Returns per-file count + summary.
      - No query param → clears ALL chunks + raw/ bytes for the job.
        Returns total count + empty summary. Used by the frontend's
        "Clear all uploads" affordance.

    Idempotent: deleting a filename that no longer exists returns 0
    with a 200. Callers can refresh their UI unconditionally.
    """
    store = _get_store()
    if not store.get(job_id):
        raise HTTPException(status_code=404, detail="Job not found")

    from vn_agent.assets import upload_store

    if filename is None:
        removed = upload_store.clear_all(job_id)
        return {
            "status": "cleared",
            "removed": removed,
            "summary": upload_store.summarize(job_id),
        }

    removed = upload_store.delete_by_filename(job_id, filename)
    return {
        "status": "deleted" if removed else "noop",
        "removed": removed,
        "filename": filename,
        "summary": upload_store.summarize(job_id),
    }


@app.post("/api/projects/{job_id}/resume")
async def resume_project(
    job_id: str,
    dry_run: bool = False,
    force: bool = False,
    compile_after: bool = True,
):
    """v4 P0-resume: rescue a stuck / crashed job from on-disk artifacts.

    - Runs `salvage_run` on the job's output_dir (merges snapshots into
      vn_script if needed).
    - When compile_after=True and text_only is set in the job config,
      immediately compiles Ren'Py so the creator can download without
      re-generating dialogue.
    - Flips the job status to `completed` (with a `(salvaged)` suffix in
      progress) so the UI stops showing it as running.

    Query params:
      - `dry_run`: report only, no writes
      - `force`: overlay snapshots even for scenes that already have dialogue
      - `compile_after`: run build_project after salvage (default True)
    """
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    output_dir = job.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=400, detail="Job has no output_dir")

    from vn_agent.salvage import SalvageError, salvage_run

    try:
        report = salvage_run(output_dir, write=not dry_run, force=force)
    except SalvageError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    response = {"salvage": report.to_dict()}

    if dry_run or report.action in {"noop", "failed"}:
        return response

    # For text_only runs the salvage output is already a valid script;
    # compile immediately so the job flips to completed. For non-text_only
    # runs (assets pending), advise CLI --resume rather than trying to
    # spin the whole graph back up here — that's local_regen's territory.
    config = job.get("config", {}) or {}
    text_only = bool(config.get("text_only", False))

    if compile_after and text_only:
        try:
            from vn_agent.compiler.project_builder import build_project
            from vn_agent.schema.character import CharacterProfile
            from vn_agent.schema.script import VNScript

            out = Path(output_dir)
            script = VNScript.model_validate_json((out / "vn_script.json").read_text(encoding="utf-8"))
            chars_raw = json.loads((out / "characters.json").read_text(encoding="utf-8"))
            characters = {k: CharacterProfile.model_validate(v) for k, v in chars_raw.items()}
            build_project(script, characters, out)
            response["compiled"] = True
            store.update_status(
                job_id, "completed",
                progress=f"done - {len(script.scenes)} scenes (salvaged)",
            )
        except Exception as e:  # noqa: BLE001 — return the salvage result even on compile fail
            response["compiled"] = False
            response["compile_error"] = str(e)
            logger.exception(f"Compile after salvage failed for {job_id}")
    elif compile_after and not text_only:
        response["next_step"] = (
            "Salvage merged snapshots. For non-text_only runs, drop to CLI: "
            f"vn-agent generate 'placeholder' --resume -o {output_dir}"
        )
        # Still mark completed since salvage recovered content; assets
        # regeneration is the user's next decision.
        store.update_status(
            job_id, "completed",
            progress="script recovered; assets pending — run CLI --resume",
        )
    else:
        # dry_run or explicit compile_after=False.
        store.update_status(job_id, "completed", progress="script salvaged (compile skipped)")

    return response


@app.get("/api/projects/{job_id}/token-usage")
async def get_token_usage(job_id: str):
    """Return token usage and estimated cost for this specific job.

    Reads from the job's blackboard where per-job token_usage is persisted
    at the end of each pipeline phase. This is isolated per job — concurrent
    jobs do not cross-contaminate costs.
    """
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    usage = (job.get("blackboard") or {}).get("token_usage") or {}
    return {
        "total_input": usage.get("total_input", 0),
        "total_output": usage.get("total_output", 0),
        "estimated_cost_usd": usage.get("estimated_cost_usd", 0.0),
        "calls": usage.get("calls", 0),
        "by_model": usage.get("by_model", {}),
    }


@app.post("/api/projects/{job_id}/compile")
async def compile_project(job_id: str):
    """Compile the Ren'Py project from the current blackboard state."""
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    output_dir = job.get("output_dir", "")
    if not output_dir:
        raise HTTPException(status_code=400, detail="No output directory")

    try:
        from vn_agent.compiler.project_builder import build_project
        from vn_agent.schema.character import CharacterProfile
        from vn_agent.schema.script import VNScript

        bb = job.get("blackboard", {})
        script_json = bb.get("_script_json")
        chars_json = bb.get("_characters_json", {})

        if not script_json:
            raise HTTPException(status_code=400, detail="No script generated yet")

        script = VNScript.model_validate(script_json)
        characters = {k: CharacterProfile.model_validate(v) for k, v in chars_json.items()}

        build_project(script, characters, Path(output_dir))
        store.update_status(job_id, "completed", progress=f"done - {len(script.scenes)} scenes")
        return {"status": "completed"}
    except Exception as e:
        store.update_status(job_id, "failed", errors=[str(e)])
        raise HTTPException(status_code=500, detail=str(e))


async def _run_script_generation(job_id: str, job: dict, plan: dict) -> None:
    """Background task: run Writer + Reviewer pipeline from plan data."""
    store = _get_store()
    from vn_agent.services.token_tracker import TokenTracker, current_tracker
    from vn_agent.services.llm import mock_mode_var
    from vn_agent.services import job_events

    # Continue accumulating into the same per-job tracker if already active
    # (covers the case where generate-setting ran first), otherwise create fresh.
    existing_bb = store.get_blackboard(job_id)
    existing_usage = existing_bb.get("token_usage") or {}
    job_tracker = TokenTracker()
    tracker_token = current_tracker.set(job_tracker)
    config = job.get("config", {})
    mock_token = mock_mode_var.set(bool(config.get("mock", False)))
    # P5 Autopilot: same per-job Settings override as generate_setting() —
    # graph.astream() below runs entirely within this coroutine (no nested
    # create_task), so the ContextVar propagates correctly through
    # writer.py/reviewer.py/structure_reviewer.py/graph.py's conditional edges.
    preset = config.get("preset")
    settings_token = None
    if preset:
        from vn_agent.autopilot.resolver import build_settings
        from vn_agent.config import _settings_override
        settings_token = _settings_override.set(build_settings(preset))
    # v4 P2 ⑤: scope scene_ready SSE events to this job for the duration of
    # the run — writer.py publishes via this ContextVar without needing
    # job_id threaded through every call.
    job_id_token = job_events.current_job_id.set(job_id)
    if config.get("mock"):
        logger.info(f"[{job_id}/generate-script] running in per-request mock mode")
    run_start = datetime.now(UTC)
    try:
        from vn_agent.agents.director import _build_from_plan
        from vn_agent.agents.graph import build_graph
        from vn_agent.agents.state import initial_state
        from vn_agent.compiler.project_builder import build_project

        theme = job["theme"]
        config = job.get("config", {})
        output_dir = job.get("output_dir", ".")

        script, characters = _build_from_plan(plan, theme)

        # Run Writer + Reviewer via the graph
        graph = build_graph()
        state = initial_state(
            theme=theme,
            output_dir=output_dir,
            text_only=config.get("text_only", True),
            max_scenes=config.get("max_scenes", 10),
            num_characters=config.get("num_characters", 3),
        )
        state["vn_script"] = script
        state["characters"] = characters

        # Stream through writer → reviewer (skip director since we already have plan)
        final_state: dict = dict(state)
        async for update in graph.astream(state, stream_mode="updates"):
            for node_name, chunk in update.items():
                if node_name != "__end__":
                    label = _STEP_LABELS.get(node_name, f"Running {node_name}")
                    store.update_status(job_id, "running", progress=label)
                    # v4 P6: publish the node identity structurally so the
                    # frontend can drive the pipeline view off real events
                    # instead of substring-matching the progress string.
                    job_events.publish_node(node_name, label)
                if isinstance(chunk, dict):
                    final_state.update(chunk)

        result_script = final_state.get("vn_script")
        result_chars = final_state.get("characters", {})

        if not result_script:
            store.update_status(job_id, "failed", errors=["No script produced"])
            job_events.close(job_id, ok=False, error="No script produced")
            return

        # Update blackboard with full script + reviewer data
        bb = store.get_blackboard(job_id)
        bb["scene_scripts"] = _scenes_to_blackboard(result_script)
        bb["reviewer"] = {
            "passed": final_state.get("review_passed", False),
            "feedback": final_state.get("review_feedback", ""),
            "revision_count": final_state.get("revision_count", 0),
            "scores": final_state.get("review_scores"),
        }
        # Serialize Pydantic objects for later use
        bb["_script_json"] = result_script.model_dump()
        bb["_characters_json"] = {k: v.model_dump() for k, v in result_chars.items()}
        store.update_blackboard(job_id, bb)

        # Auto-compile
        store.update_status(job_id, "running", progress="building project")
        build_project(result_script, result_chars, Path(output_dir))

        store.update_status(
            job_id, "completed",
            progress=f"done - {len(result_script.scenes)} scenes",
            errors=final_state.get("errors", []),
        )
        job_events.close(job_id, ok=True)
    except Exception as e:
        logger.exception(f"Script generation failed for {job_id}")
        store.update_status(job_id, "failed", errors=[str(e)])
        job_events.close(job_id, ok=False, error=str(e))
    finally:
        # Merge this phase's tracker into any existing usage from generate-setting
        try:
            bb = store.get_blackboard(job_id)
            phase_usage = job_tracker.summary_dict()
            # Accumulate totals: previous setting phase + current script phase
            merged = _merge_token_usage(existing_usage, phase_usage)
            bb["token_usage"] = merged
            store.update_blackboard(job_id, bb)
        except Exception as e:
            logger.debug(f"Could not persist token usage for {job_id}: {e}")

        # P5 Autopilot: run_meta.json + outcomes log, scoped to preset-flagged
        # jobs only (closes the run_meta.json gap run-analyzer.md already
        # documents expecting — the web job path never wrote one before this).
        if preset:
            try:
                _write_autopilot_run_meta(job_id, preset, run_start)
            except Exception as e:
                logger.warning(f"Could not write autopilot run_meta/outcome for {job_id}: {e}")

        current_tracker.reset(tracker_token)
        mock_mode_var.reset(mock_token)
        job_events.current_job_id.reset(job_id_token)
        if settings_token is not None:
            from vn_agent.config import _settings_override
            _settings_override.reset(settings_token)


def _scenes_to_blackboard(script) -> list[dict]:
    """Serialize a VNScript's scenes into the blackboard["scene_scripts"] shape
    the frontend (VNPreview.tsx) consumes. Shared by the initial generation
    finalize step and by chat_ops (v4 P3) re-syncing the blackboard after a
    local_regen mutates vn_script.json directly on disk — without this, the
    frontend's cached blackboard would drift from what's actually on disk
    after a chat-ops edit."""
    return [
        {
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "background_id": s.background_id,
            "characters_present": s.characters_present,
            "narrative_strategy": s.narrative_strategy,
            "dialogue": [
                {"character_id": d.character_id, "text": d.text, "emotion": d.emotion}
                for d in s.dialogue
            ],
            "branches": [
                {"text": b.text, "next_scene_id": b.next_scene_id}
                for b in s.branches
            ],
            "next_scene_id": s.next_scene_id,
        }
        for s in script.scenes
    ]


def _merge_token_usage(prev: dict, new: dict) -> dict:
    """Sum two token_usage summary_dicts into a combined total."""
    if not prev:
        return new
    if not new:
        return prev
    merged_by_model: dict[str, dict[str, int]] = {}
    for src in (prev.get("by_model") or {}, new.get("by_model") or {}):
        for model, stats in src.items():
            m = merged_by_model.setdefault(model, {"in": 0, "out": 0, "calls": 0})
            m["in"] += stats.get("in", 0)
            m["out"] += stats.get("out", 0)
            m["calls"] += stats.get("calls", 0)
    return {
        "total_input": prev.get("total_input", 0) + new.get("total_input", 0),
        "total_output": prev.get("total_output", 0) + new.get("total_output", 0),
        "estimated_cost_usd": round(
            prev.get("estimated_cost_usd", 0.0) + new.get("estimated_cost_usd", 0.0), 4,
        ),
        "calls": prev.get("calls", 0) + new.get("calls", 0),
        "by_model": merged_by_model,
    }


def _write_autopilot_run_meta(job_id: str, preset: str, run_start: datetime) -> None:
    """Write run_meta.json + append an autopilot outcomes.jsonl row.

    Scoped to preset-flagged (Autopilot) jobs only. Also closes a
    pre-existing gap: the web job path never wrote run_meta.json before this
    — only standalone CLI scripts (scripts/run_real_demo.py) did, even
    though .claude/agents/run-analyzer.md already documents expecting one
    alongside trace.json/vn_script.json/library_hits.jsonl in every run's
    output_dir.
    """
    from vn_agent.autopilot.outcomes import AutopilotOutcome
    from vn_agent.autopilot.outcomes import append as append_outcome

    store = _get_store()
    fresh_job = store.get(job_id) or {}
    output_dir = Path(fresh_job.get("output_dir") or ".")
    bb = store.get_blackboard(job_id)
    usage = bb.get("token_usage") or {}
    scene_scripts = bb.get("scene_scripts") or []
    success = fresh_job.get("status") == "completed"
    errors = fresh_job.get("errors") or []
    wall_time_seconds = round((datetime.now(UTC) - run_start).total_seconds(), 1)

    meta = {
        "timestamp": datetime.now(UTC).isoformat(),
        "job_id": job_id,
        "theme": fresh_job.get("theme", ""),
        "preset": preset,
        "wall_time_seconds": wall_time_seconds,
        "actual": {
            "token_usage": usage,
            "estimated_cost_usd": usage.get("estimated_cost_usd", 0.0),
        },
        "script": {"scene_count": len(scene_scripts)},
        "errors": errors,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    append_outcome(AutopilotOutcome(
        job_id=job_id,
        theme=fresh_job.get("theme", ""),
        preset_used=preset,
        success=success,
        wall_time_seconds=wall_time_seconds,
        estimated_cost_usd=usage.get("estimated_cost_usd", 0.0),
        scene_count=len(scene_scripts),
        error=errors[0] if errors and not success else None,
    ))


# ── Background runner ────────────────────────────────────────────────────────

# One entry per node in agents/graph.py's compiled graph. Kept exhaustive by
# tests/test_web/test_pipeline_labels.py — an unlabelled node falls back to
# f"Running {node_name}", which leaks the internal identifier to users.
_STEP_LABELS = {
    "director": "Director planning story structure",
    "structure_reviewer": "Auditing story structure",
    "director_step2_redo": "Director revising the scene plan",
    "director_full_redo": "Director replanning the story",
    "state_orchestrator": "Resolving scene state",
    "thinking_fanout": "Planning scene-by-scene reasoning",
    "cross_ref_sync": "Syncing cross-scene references",
    "writer": "Writer creating dialogue",
    "reviewer": "Reviewer checking quality",
    "asset_generation": "Generating assets (characters, scenes, music)",
}


async def _run_job(job_id: str, req: GenerateRequest, output_dir: Path) -> None:
    store = _get_store()
    sem = _get_semaphore()

    async with sem:
        store.update_status(job_id, "running", progress="starting pipeline")
        # Per-job token tracker: isolate cost accounting across concurrent jobs
        from vn_agent.services.token_tracker import TokenTracker, current_tracker

        # v4 P0-7: per-request mock gate. Setting it inside the semaphore
        # scope means concurrent jobs — one mock, one real — coexist
        # cleanly. Reset in finally to avoid leaks into the next task.
        from vn_agent.services.llm import mock_mode_var

        job_tracker = TokenTracker()
        tracker_token = current_tracker.set(job_tracker)
        mock_token = mock_mode_var.set(bool(req.mock))
        # P5 Autopilot: headless-caller parity with generate_setting/
        # _run_script_generation. The SPA never reaches this function
        # (interactive=True skips it) — this only matters for a caller that
        # hits /generate directly with autopilot=True and no follow-up.
        job = store.get(job_id) or {}
        preset = job.get("config", {}).get("preset")
        settings_token = None
        if preset:
            from vn_agent.autopilot.resolver import build_settings
            from vn_agent.config import _settings_override
            settings_token = _settings_override.set(build_settings(preset))
        if req.mock:
            logger.info(f"[{job_id}] running in per-request mock mode (fixtures, zero API)")
        run_start = datetime.now(UTC)
        try:
            from vn_agent.agents.graph import build_graph
            from vn_agent.agents.state import initial_state
            from vn_agent.compiler.project_builder import build_project

            graph = build_graph()
            state = initial_state(
                theme=req.theme,
                output_dir=str(output_dir),
                text_only=req.text_only,
                max_scenes=req.max_scenes,
                num_characters=req.num_characters,
                # v4 P0: propagate the web job id so downstream agents can
                # look up user-uploaded material chunks via upload_store.
                job_id=job_id,
            )

            # Use astream for per-node progress updates
            final_state: dict = {}
            async for update in graph.astream(state, stream_mode="updates"):
                for node_name, output_chunk in update.items():
                    if node_name != "__end__":
                        label = _STEP_LABELS.get(node_name, f"Running {node_name}")
                        store.update_status(job_id, "running", progress=label)
                    if isinstance(output_chunk, dict):
                        final_state.update(output_chunk)

            script = final_state.get("vn_script")
            characters = final_state.get("characters", {})

            if not script:
                store.update_status(job_id, "failed", errors=["No script produced"])
                return

            store.update_status(job_id, "running", progress="building project")
            build_project(script, characters, output_dir)

            store.update_status(
                job_id,
                "completed",
                progress=f"done - {len(script.scenes)} scenes",
                errors=final_state.get("errors", []),
            )

        except Exception as e:
            logger.exception(f"Job {job_id} failed")
            store.update_status(job_id, "failed", errors=[str(e)])
        finally:
            # Persist token usage to blackboard and reset context
            try:
                bb = store.get_blackboard(job_id)
                bb["token_usage"] = job_tracker.summary_dict()
                store.update_blackboard(job_id, bb)
            except Exception as e:
                logger.debug(f"Could not persist token usage for {job_id}: {e}")
            if preset:
                try:
                    _write_autopilot_run_meta(job_id, preset, run_start)
                except Exception as e:
                    logger.warning(f"Could not write autopilot run_meta/outcome for {job_id}: {e}")
            current_tracker.reset(tracker_token)
            mock_mode_var.reset(mock_token)
            if settings_token is not None:
                from vn_agent.config import _settings_override
                _settings_override.reset(settings_token)


# ── Static frontend (must be AFTER all API route definitions) ───────────────

# Serve built React app from frontend/dist/, or raw frontend/ for dev
_FRONTEND_DIR = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
if not _FRONTEND_DIR.is_dir():
    _FRONTEND_DIR = Path(__file__).parent.parent.parent.parent / "frontend"
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
