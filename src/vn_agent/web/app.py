"""FastAPI backend for VN-Agent generation.

Endpoints:
    POST   /generate       — start a generation job
    GET    /status/{job_id} — poll job status
    GET    /download/{job_id} — download output as zip
    GET    /jobs           — list recent jobs
    DELETE /jobs/{job_id}  — delete a job and its output
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from vn_agent.web.store import JobStore

# ── Configuration from environment ──────────────────────────────────────────

_DB_PATH = os.environ.get("VN_AGENT_DB_PATH", "vn_jobs.db")
_MAX_CONCURRENT = int(os.environ.get("VN_AGENT_MAX_CONCURRENT", "3"))
_OUTPUT_DIR = os.environ.get("VN_AGENT_OUTPUT_DIR", "")

app = FastAPI(title="VN-Agent API", version="0.2.0")
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


# ── Background runner ────────────────────────────────────────────────────────

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

            store.update_status(job_id, "running", progress="running pipeline")
            result = await graph.ainvoke(state)

            script = result.get("vn_script")
            characters = result.get("characters", {})

            if not script:
                store.update_status(job_id, "failed", errors=["No script produced"])
                return

            store.update_status(job_id, "running", progress="building project")
            build_project(script, characters, output_dir)

            store.update_status(
                job_id,
                "completed",
                progress=f"done - {len(script.scenes)} scenes",
                errors=result.get("errors", []),
            )

        except Exception as e:
            store.update_status(job_id, "failed", errors=[str(e)])
