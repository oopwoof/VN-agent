# VN-Agent

**Multi-Agent AI Visual Novel Generator** — from a one-line theme to a fully playable [Ren'Py](https://www.renpy.org/) project with branching storylines, character sprites, scene backgrounds, and BGM.

## Architecture

```
User: "A lighthouse keeper must choose between saving a ship or abandoning the post"
                                    │
                           ┌────────▼────────┐
                           │    Director      │  ← 2-step planning (outline → navigation)
                           │  (CoT reasoning) │     Prevents max_tokens truncation
                           └────────┬────────┘
                                    │
                           ┌────────▼────────┐
                     ┌────►│     Writer       │◄────┐
                     │     │  (RAG few-shot)  │     │  Revision loop
                     │     └────────┬────────┘     │  (max 3 rounds)
                     │              │               │
                     │     ┌────────▼────────┐     │
                     │     │    Reviewer      │─────┘
                     │     │ (LLM-as-Judge)   │
                     │     │  5-dim rubric    │
                     │     └────────┬────────┘
                     │              │ PASS
                     │   ┌──────────┼──────────┐
                     │   │          │          │     asyncio.gather
                     │   ▼          ▼          ▼     (parallel + fault isolation)
                     │ Character  Scene     Music
                     │ Designer   Artist    Director
                     │   │          │          │
                     │   └──────────┼──────────┘
                     │              │
                     │     ┌────────▼────────┐
                     │     │  Ren'Py Compiler │  → Playable game project
                     │     └─────────────────┘
```

**Key design decisions:**
- **Agent decomposition**: Each agent owns an independent decision domain (planning / writing / review / visuals / music). Merging them would cause prompt scaling issues and unstable JSON output.
- **Conditional revision loop**: Reviewer↔Writer loop with hard cap (3 rounds) prevents infinite cycles while improving generation quality.
- **Parallel asset generation**: Character/Scene/Music agents have no data dependencies → `asyncio.gather` with `return_exceptions=True` for fault isolation.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent orchestration | LangGraph `StateGraph`, conditional edges, parallel nodes |
| LLM providers | Anthropic Claude / OpenAI GPT / **Ollama local** (one-line config switch) |
| RAG retrieval | sentence-transformers + FAISS `IndexFlatIP` (1,036 annotated corpus) |
| Structured output | **LLM Tool Calling** (Pydantic schema → function definition) |
| Quality assurance | **LLM-as-Judge** 5-dimension rubric + BFS reachability structural checks |
| Cost optimization | Multi-model routing (Sonnet planning / Haiku review, ~73% savings in budget mode) |
| Web API | FastAPI async + SQLite job store + SSE streaming |
| CI/CD | GitHub Actions (ruff + mypy + 140 pytest + coverage ≥65%) + Docker |

## Quick Start

```bash
# Install (requires uv: https://docs.astral.sh/uv/)
uv sync

# Configure API key
cp .env.example .env
# Edit .env → set ANTHROPIC_API_KEY

# Generate a visual novel
vn-agent generate --theme "A lighthouse keeper during a catastrophic storm" --output ./my_vn

# Or use a local model (zero cost)
# Edit config/settings.yaml → set base_url: http://localhost:11434/v1
vn-agent generate --theme "..." --output ./my_vn
```

### Other commands

```bash
vn-agent dry-run --theme "..."          # Preview without API calls
vn-agent generate --mock --output ./out # Offline mode with canned responses
vn-agent validate ./out                 # Validate generated script
vn-agent compile ./out                  # Re-compile Ren'Py project
vn-agent eval strategy --corpus data/final_annotations.csv --mock  # Run eval
```

## Evaluation Results

### Strategy Classification (1,036 COLX_523 samples)

| Method | Accuracy | Macro F1 |
|--------|----------|----------|
| Random baseline | 16.7% | — |
| Keyword rules | 23.0% | 0.21 |
| **qwen2.5:7b LLM** | **35.0%** | **0.34 (+57%)** |

### Structural Validation

4-type defect detection (start scene / branch references / BFS reachability / character consistency) — **100% detection rate** on adversarial test suite.

### Cost Analysis (Anthropic pricing)

| Mode | Cost vs All-Sonnet |
|------|--------------------|
| Default routing (Sonnet + Haiku) | ~80% |
| Budget mode (all Haiku) | **~27% (−73%)** |

## Project Structure

```
src/vn_agent/
├── agents/           # LangGraph nodes: director, writer, reviewer, etc.
│   └── graph.py      # DAG topology + parallel asset generation
├── compiler/         # Ren'Py project builder + Jinja2 templates
├── eval/             # Strategy eval + embedding index + corpus loader
├── observability/    # Trace spans + per-node timing
├── prompts/          # CoT prompt templates + strip_thinking()
├── schema/           # Pydantic models (VNScript, Scene, DialogueLine, etc.)
├── services/         # LLM client, image gen, music gen, streaming, tool calling
├── strategies/       # Narrative strategy system (7 types)
├── web/              # FastAPI app + SSE streaming endpoint
├── cli.py            # Typer CLI (generate/validate/compile/eval)
└── config.py         # Pydantic-settings + YAML config loader
tests/                # 140 pytest cases across 10 test modules
```

## Development

```bash
uv run pytest                    # Run all tests
uv run ruff check src/ tests/    # Lint
uv run mypy src/vn_agent/ --ignore-missing-imports  # Type check
```

## Documentation

- [Resume / Project Description](docs/RESUME.md)
- [Development Log](docs/DEV_LOG.md)
- [Product Spec](docs/PRODUCT.md)

## License

MIT
