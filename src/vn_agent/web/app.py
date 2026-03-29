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
import logging
import os
import re
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

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
    store.create(job_id, req.theme, config, str(output_dir))
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

    try:
        from vn_agent.agents.director import _merge_outline_details, _step1_outline, _step2_details
        from vn_agent.config import get_settings

        settings = get_settings()
        config = job.get("config", {})
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
        }

        store.update_blackboard(job_id, blackboard)
        store.update_status(job_id, "setting_generated", progress="Setting ready for review")
        return {"status": "setting_generated", "blackboard": blackboard}

    except Exception as e:
        logger.exception(f"generate-setting failed for {job_id}")
        store.update_status(job_id, "failed", errors=[str(e)])
        raise HTTPException(status_code=500, detail=str(e))


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
_MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
_MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB

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
):
    """Upload an asset file to replace a placeholder."""
    store = _get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not re.fullmatch(r"[a-zA-Z0-9_/.-]+", asset_id):
        raise HTTPException(status_code=400, detail="Invalid asset_id format")

    output_dir = Path(job.get("output_dir", ""))

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
    else:
        raise HTTPException(status_code=400, detail=f"Unknown asset_type: {asset_type}")

    # Path traversal check
    if not str(target.resolve()).startswith(str(output_dir.resolve())):
        raise HTTPException(status_code=403, detail="Path traversal denied")

    # Extension check
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"Invalid file format {ext}, allowed: {allowed_ext}")

    # Size check
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail=f"File too large ({len(content)} bytes), max {max_size}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    return {"status": "uploaded", "asset_type": asset_type, "asset_id": asset_id, "size": len(content)}


@app.get("/api/projects/{job_id}/token-usage")
async def get_token_usage(job_id: str):
    """Return token usage and estimated cost for this project."""
    from vn_agent.services.token_tracker import tracker

    return {
        "total_input": tracker.total_input(),
        "total_output": tracker.total_output(),
        "estimated_cost_usd": round(tracker.estimated_cost(), 4),
        "calls": len(tracker.calls),
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
                if isinstance(chunk, dict):
                    final_state.update(chunk)

        result_script = final_state.get("vn_script")
        result_chars = final_state.get("characters", {})

        if not result_script:
            store.update_status(job_id, "failed", errors=["No script produced"])
            return

        # Update blackboard with full script + reviewer data
        bb = store.get_blackboard(job_id)
        bb["scene_scripts"] = [
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
            for s in result_script.scenes
        ]
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
    except Exception as e:
        logger.exception(f"Script generation failed for {job_id}")
        store.update_status(job_id, "failed", errors=[str(e)])


# ── Background runner ────────────────────────────────────────────────────────

_STEP_LABELS = {
    "director": "Director planning story structure",
    "writer": "Writer creating dialogue",
    "reviewer": "Reviewer checking quality",
    "asset_generation": "Generating assets (characters, scenes, music)",
}


async def _run_job(job_id: str, req: GenerateRequest, output_dir: Path) -> None:
    store = _get_store()
    sem = _get_semaphore()

    async with sem:
        store.update_status(job_id, "running", progress="starting pipeline")
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


# ── Static frontend (must be AFTER all API route definitions) ───────────────

# Serve built React app from frontend/dist/, or raw frontend/ for dev
_FRONTEND_DIR = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
if not _FRONTEND_DIR.is_dir():
    _FRONTEND_DIR = Path(__file__).parent.parent.parent.parent / "frontend"
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
