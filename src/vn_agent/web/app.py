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
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
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

_FRONTEND_DIR = Path(__file__).parent.parent.parent.parent / "frontend"
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
