# VN-Agent

**Multi-Agent AI Visual Novel Generator** — from a one-line theme to a fully playable [Ren'Py](https://www.renpy.org/) project with branching storylines, transparent-background character sprites, 16:9 scene backgrounds, and BGM.

**多 Agent 协作的 AI 视觉小说生成器** — 一行主题到可直接在 Ren'Py 上运行的完整游戏：分支剧本、透明底立绘、16:9 场景背景、BGM。

---

## Architecture / 架构

```
User: "A lighthouse keeper must choose between saving a ship or abandoning the post"
用户：「一位灯塔看守人必须在救船与弃塔之间做选择」
                                    │
                           ┌────────▼─────────┐
                           │     Director     │  ← 2-step planning (outline → navigation)
                           │   (CoT reasoning)│     两步规划，防止 max_tokens 截断
                           └────────┬─────────┘
                                    │
                           ┌────────▼─────────┐
                           │ StructureReviewer│  ← pre-Writer outline audit
                           └────────┬─────────┘    (branch intent, arc shape)
                                    │
                           ┌────────▼─────────┐
                           │ StateOrchestrator│  ← world_state → narrative constraints
                           │  (Haiku, cheap)  │    (Sprint 9-6 logic decouple)
                           └────────┬─────────┘
                                    │
                     ┌─────────────►│
                     │     ┌────────▼─────────┐
                     │     │     Writer       │  ← RAG few-shot + state constraints
                     │     │  (Sonnet craft)  │
                     │     └────────┬─────────┘
                     │              │
                     │     ┌────────▼─────────┐
                     │     │  DialogueReviewer│──── revision loop (max 3 rounds)
                     │     │  Python pre-gate │     修订循环，上限 3 轮
                     │     │  + Sonnet judge  │
                     │     └────────┬─────────┘
                     │              │ PASS
                     │   ┌──────────┼──────────┐
                     │   │          │          │     asyncio.gather
                     │   ▼          ▼          ▼     (parallel + fault isolation)
                     │ Character  Scene     Music
                     │ Designer   Artist    Director
                     │   │          │          │
                     │   └──────────┼──────────┘
                     │              │
                     │     ┌────────▼─────────┐
                     └────►│  Ren'Py Compiler │  → Playable game project
                           │  + rembg cutout  │
                           │  + PIL BG resize │
                           └──────────────────┘
```

**Key design decisions / 关键设计决策:**
- **Agent decomposition / Agent 拆分**: each agent owns one decision domain (planning / writing / review / visuals / music); merging them causes prompt scaling + JSON instability. 每个 Agent 独占一个决策域，合并会触发 prompt 膨胀与 JSON 输出不稳定。
- **Symbolic world state (Sprint 9) / 符号化世界状态**: `world_variables` + `state_reads` / `state_writes` + Ren'Py `$ var` emission — state evolves across scenes, not hallucinated. 状态跨场景演化，不由 LLM 幻觉。
- **Creator mode (Sprint 12-3) / 创作者模式**: `--pause-after outline` dumps sidecar; edit `vn_script.json` on disk; `continue-outline` resumes with writer-only graph. 大纲落盘可编辑，续跑只走下半程图。
- **Conditional revision loop / 条件修订循环**: Reviewer↔Writer with Python mechanical pre-gate (format / keywords / state) then Sonnet craft check; hard cap 3 rounds. 纯 Python 机械 gate 先把关，Sonnet craft 后置；上限 3 轮防死循环。
- **Parallel asset generation / 并行资产生成**: Character/Scene/Music have no data deps → `asyncio.gather` with `return_exceptions=True` for fault isolation. 三个资产 Agent 无依赖，并行执行带故障隔离。

---

## Tech Stack / 技术栈

| Layer / 层 | Technology |
|---|---|
| Agent orchestration / Agent 编排 | LangGraph `StateGraph`, conditional edges, writer-only subgraph for creator-mode continue |
| LLM providers / LLM 供应商 | Anthropic Claude / OpenAI GPT / Google Gemini / Ollama local (provider auto-routing by model prefix) |
| RAG retrieval / RAG 检索 | sentence-transformers + FAISS `IndexFlatIP` + BM25 weighted RRF fusion (1,036 annotated corpus) |
| Structured output / 结构化输出 | LLM tool calling (Pydantic schema → function definition) |
| Image generation / 图像生成 | Google Nano Banana (Gemini 2.5 Flash Image) primary + OpenAI gpt-image-1 / Stability fallback chain, aspect ratio plumbing (3:4 sprites, 16:9 BGs) |
| Sprite cutout / 立绘抠图 | rembg u2net_human_seg local ONNX inference → transparent-background PNG (optional `[cutout]` extra) |
| Quality assurance / 质量保证 | Cross-model judge (Sonnet + GPT-4o) + 5-dim rubric + BFS reachability + persona fingerprint drift audit |
| Cost optimization / 成本优化 | Multi-model routing + prompt caching (Anthropic ephemeral) + per-job TokenTracker |
| Web API / Web 接口 | FastAPI async + SQLite job store + SSE streaming |
| CI/CD | GitHub Actions (ruff + mypy + 352 pytest + coverage ≥60%) + Docker |

---

## Quick Start / 快速开始

```bash
# Install / 安装 (requires uv: https://docs.astral.sh/uv/)
uv sync --all-extras    # --extra cutout pulls rembg for transparent sprites

# Configure API keys / 配置密钥
cp .env.example .env
# Edit .env → set ANTHROPIC_API_KEY, GOOGLE_API_KEY (for Nano Banana), OPENAI_API_KEY (for cross-judge)

# Generate a visual novel / 生成一部 VN
vn-agent generate "A lighthouse keeper during a catastrophic storm" --output ./my_vn

# Creator mode: pause after outline to edit manually
# 创作者模式：大纲生成后暂停，手改 vn_script.json 再继续
vn-agent generate "..." --output ./my_vn --pause-after outline
# (edit ./my_vn/vn_script.json, then)
vn-agent continue-outline --output ./my_vn

# Regenerate one scene without re-running pipeline
# 只重写单个场景，不跑全流程
vn-agent regen ch3_the_choice --output ./my_vn --feedback "more subtext"

# Or use a local Ollama model (zero API cost)
# 或切本地 Ollama 模型（零 API 成本）
# Edit config/settings.yaml → set base_url: http://localhost:11434/v1
vn-agent generate "..." --output ./my_vn
```

### Other commands / 其他命令

```bash
vn-agent dry-run "..."                # Preview + cost estimate, no API calls
                                      # 预估 + 成本，不调 API
vn-agent generate "..." --mock         # Offline mode with canned fixtures
                                      # 离线 mock 模式
vn-agent validate ./out/vn_script.json # Validate generated script
                                      # 校验脚本
vn-agent compile ./out/vn_script.json --output ./out --characters ./out/characters.json
                                      # Re-compile Ren'Py project only
                                      # 仅重编 Ren'Py 项目
vn-agent eval strategy --corpus data/final_annotations.csv --mock
                                      # Run strategy classification eval
                                      # 运行策略分类评估
```

---

## Evaluation / 评估数据

### Cross-model judge agreement (Sprint 8-5 rejudge) / 跨模型判分一致性

47 paired scenes across 8 sweep cells, commit `4f1228f`. Refutes the "self-judging echo chamber" critique.
47 个配对场景覆盖 8 个 sweep cell — 直接反驳"自评自答"批评。

| Metric | Value |
|---|---|
| Sonnet mean / Sonnet 均值 | 3.68 |
| GPT-4o mean / GPT-4o 均值 | 3.66 |
| Pearson r | **0.643** |
| ±1-point agreement / ±1 分一致率 | **87%** |

### Mode comparison (8-cell sweep) / 模式对比

| Mode / 模式 | Score | Cost / 成本 |
|---|---|---|
| **literary** (ours) — physics-framework system prompt, zero-shot | **4.17** | ~$0.50 |
| action — raw VN few-shot injection | 3.92 | ~$0.50 |
| baseline_self_refine (single model, self-critique) | 3.45 | ~$0.15 |
| baseline_single (single Sonnet call) | 3.25 | ~$0.05 |

Multi-agent pipeline beats best baseline by +0.72 absolute — complexity earns its cost.
多 Agent pipeline 相对最强 baseline +0.72 绝对分，复杂度值回票价。

### Full-run cost / 完整运行成本

- Showcase demo (Three Hours Before the Tide, 6 scenes / 3 chars / 15 images): **$1.7 / ~30 min** full generate
- Continue-outline only (creator workflow): **$0.46 / ~9 min**（仅下半程 Writer+Reviewer+Assets）

---

## What's in the Ren'Py output / Ren'Py 输出什么

- Scene backgrounds **resized to exact 1920×1080** via PIL LANCZOS at save time — no black bars on any screen. 场景背景保存时强制 1920×1080，任何屏幕无黑边。
- Full-color 3:4 portrait sprites with **transparent alpha** (rembg u2net_human_seg), **9 emotion names aliased** to 3 generated PNGs with filesystem-aware fallback (drop `thoughtful.png` in the sprite dir → next recompile picks it up automatically). 全彩 3:4 立绘带真透明，9 种情感别名到 3 张生成图，创作者后期补图自动生效。
- `zoom 0.45` self-contained ATL transforms for left/center/right positions — industry-standard 49% screen-height sprite framing (Umineko / Fata Morgana / Never7). 三位置独立 ATL transform，行业标准 49% 屏高。
- Dialogue box styled via `define gui.*` on stock Ren'Py `say` screen (dark 80% alpha textbox, gold speaker name, 1560px wrap, punctuation-aware typewriter). 深色半透明对话框 + 米金色说话人名 + 标点节奏 typewriter。
- Floating center-screen choice menu with 50% scene dim (branches don't live inside the textbox). 分支选择浮窗中央大按钮，50% 黑蒙。
- Symbolic world-state emission: `default met_suspect = False` + `$ met_suspect = True` inside scene labels + `menu if met_suspect:` branch guards. 符号化状态 → Ren'Py `$ var` + `if` guards。

---

## Project Structure / 项目结构

```
src/vn_agent/
├── agents/              # LangGraph nodes
│   ├── graph.py         # Full graph + build_writer_graph (creator-mode continue)
│   ├── director.py      # 2-step planning + Director checkpoint
│   ├── structure_reviewer.py
│   ├── state_orchestrator.py   # world_state → narrative constraints
│   ├── writer.py        # literary / action dual-mode + per-scene snapshot
│   ├── reviewer.py      # Python pre-gate + Sonnet judge
│   ├── character_designer.py   # sprite gen + rembg cutout + emotion batch
│   ├── scene_artist.py  # BG gen + PIL 1920×1080 resize
│   ├── music_director.py
│   ├── local_regen.py   # single-scene rewrite (Sprint 12-4)
│   └── unknown_chars.py # creator-mode resolver payload (Sprint 12-5)
├── compiler/
│   ├── renpy_compiler.py    # Jinja2 env + renpy_safe filter + emotion-map
│   ├── project_builder.py   # directory layout + placeholder fallback
│   └── templates/*.j2       # init / gui / script / characters
├── eval/                # Strategy metrics + corpus loader + lore index
├── observability/       # Trace spans, per-agent tokens
├── schema/              # Pydantic models + emotions.py single-source
├── services/            # LLM client + image_gen (4 providers) + bg_remove + token_tracker
├── web/                 # FastAPI + SSE + SQLite job store
├── cli.py               # Typer: generate / continue-outline / regen / eval / ...
└── config.py            # pydantic-settings + YAML + coupled sprite/BG knobs
tests/                   # 352 pytest cases across 11 test modules
```

---

## Development / 开发

```bash
uv run pytest -m "not slow"                         # 352 tests pass
uv run ruff check src/ tests/                       # Lint
uv run mypy src/vn_agent/ --ignore-missing-imports  # Type check (clean)
uv run pytest --cov=src/vn_agent --cov-report=term  # Coverage (66%)
```

CI (`.github/workflows/ci.yml`) runs ruff + mypy + pytest + coverage floor 60% on every push.

---

## Documentation / 文档

- [Development Log / 开发日志](docs/DEV_LOG.md) — sprint-by-sprint record + future architecture routes (4-channel RAG, self-evolving agent)
- [Product Spec / 产品文档](docs/PRODUCT.md) — status, metrics, roadmap
- [Ren'Py Gotchas / Ren'Py 踩坑笔记](~/.claude/projects/.../memory/project_renpy_gotchas.md) — image discovery, text escape, style inheritance, sprite scaling

---

## License

MIT
