# AGENTS.md

## Cursor Cloud specific instructions

This is **VN-Agent** — a multi-agent AI visual novel generator. It has three surfaces sharing one Python core: a Typer **CLI** (`vn-agent`), a **FastAPI web backend**, and a **React/Vite frontend**. See `README.md` for the product/architecture overview and the canonical lint/test/build commands (`## Development` section).

### Environment (already provisioned by the startup update script)
- Python deps are managed by **`uv`** (installed at `~/.local/bin`, on `PATH` via `~/.bashrc`). The update script runs `uv sync --all-extras --dev` (installs `web`, `rag`, `cutout`, `assets` extras + dev tools) and `npm --prefix frontend ci`.
- `uv sync` creates/uses `.venv` with a pinned interpreter — always invoke Python tooling through `uv run ...`, not the system `python3`.

### Running the services (nothing here is auto-started)
- **Backend (FastAPI, port 8000):** `VN_AGENT_MOCK=true uv run uvicorn vn_agent.web.app:app --host 0.0.0.0 --port 8000`
- **Frontend (Vite dev, port 5173):** `cd frontend && npm run dev`. Vite proxies `/generate`, `/status`, `/download`, `/jobs`, `/api` to `http://localhost:8000`, so the backend must be running too.
- **CLI:** e.g. `uv run vn-agent generate "<theme>" --output ./my_vn --mock`.

### Mock mode is the key to zero-cost end-to-end testing
- Set **`VN_AGENT_MOCK=true`** in the backend's environment (or pass `--mock` to the CLI / tick the "Mock (Zero API $)" toggle in the web UI). This routes all LLM/image/music calls to canned fixtures, so **no API keys are needed** to exercise the full pipeline. Without mock mode a preflight check requires `ANTHROPIC_API_KEY` (and possibly `OPENAI_API_KEY`/`GOOGLE_API_KEY`).
- The full mock generate → download flow produces a valid Ren'Py project zip (`game/script.rpy`, `gui.rpy`, `characters.rpy`, audio, images).

### Known pre-existing issues (NOT environment problems — do not attribute to setup)
- **CI on `main` is red**: `uv run ruff check src/ tests/` reports ~39 `F401` (unused import) errors and CI fails at the lint step (so it never reaches pytest). `uv run mypy src/vn_agent/ --ignore-missing-imports` reports ~16 errors. `npm --prefix frontend run lint` reports 2 errors + 1 warning.
- **pytest**: `uv run pytest -m "not slow"` has ~4 pre-existing failures (mock-LLM source assertions in `test_structure_reviewer`/`test_graph_routing`, and `test_resume_flow::test_empty_dir_raises` which needs a git-untracked empty fixture dir). ~846 tests pass. Only touch these if the task is explicitly to fix them.
