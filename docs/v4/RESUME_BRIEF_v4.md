# VN-Agent — Resume Brief (v4, updated 2026-08-10 — adds P6 frontend redesign; supersedes 2026-07-19 draft's P2-P5 status)

> **Purpose**: source-of-truth briefing document for a downstream LLM that will produce JD-tailored resume bullets and interview talking points for an **AI Product Manager (校招/campus)** application. This file is self-contained; the downstream LLM should not need to open the repo.
>
> **Style constraint**: every quantitative claim is annotated with an evidence path or commit hash. Aspirational / not-yet-measured claims are flagged `(aspirational)`. Mixed Chinese/English is intentional — Chinese carries 校招 idioms and interview quotes that lose weight in translation.

---

## 0. TL;DR (LLM header context)

**Project positioning (one sentence)**: VN-Agent 是一个用 LangGraph 多 Agent 流水线把"一句话故事主题"变成"可玩视觉小说"的 AI 工作台产品，从工程 demo 出发、v4 阶段升级为面向创作者的 Chat Ops 平台，全程作为 AI 产品经理校招的**产品决策 + AgentOps + 数据飞轮**叙事载体。

**Role**: individual contributor / owner. **This is a personal project, built AI-augmented with Claude Code + Gemini as pair-programmers**. The PM decisions (方向优先级、alternatives-considered、成本模型) are the candidate's; the code was implemented with heavy AI assistance. Honesty about this is a strength, not a liability — the interviewer's real question is "can you drive an AI product end-to-end", and shipping 166 commits + 15.8K LoC solo (with tools) is a stronger signal than pretending to hand-write it all.

**Elevator pitch anchors (pick one per JD)**:
- **AgentOps 评测底座** — 3 层 Reviewer + token/cost 观测 + Pearson r 跨模型 judge (r=0.643)
- **数据飞轮 M0 已跑通** — 👍/👎 → BM25 injector → Reflection Agent (Haiku)，闭环存在但用户数据薄
- **多源素材融合避免同质化** — 上传 + 网检 (search-agent) + 本地开源库 + LLM 生成 4 通道 + 版权白名单 gate
- **成本模型经过量化** — 6-scene ~$1.7 实测 + prompt caching 0.1× 复用 + 单元经济性 sheet (Pro $29 with usage limits)
- **全 6 阶段路线闭环（P0→P5，2026-07-27，M0 级别全部交付）** — 一句话主题到"实时流式播放 + 对话式编辑 + 一键体检 + 一键 Autopilot 播放"的完整工作台，不是单点 demo
- **AI 安全自纠错的真实案例** — 自己在做 P5 时的一次 CLI 冒烟测试意外触发了 5 次真实 API 调用（$0.12），当场识别根因、披露、修复并加回归测试锁死；这是 AgentOps 诚实文化的活案例，不是编的故事
- **P6 前端改版：把不可见的多 Agent 流水线做成产品主舞台**（2026-08-10，17 commits）— 后端 `graph.astream()` 每个节点的事件此前被压成一个字符串、前端再用子串匹配猜回来；改成 `publish_node` → SSE `node` 事件 → `pipelineNodes` → `PipelineGraph` 的结构化链路，顺带补齐 10 个节点里缺的 6 个标签、修掉一个"进度条第 2 格永远走不到"的潜伏 bug，并做了 zh/en 全量 i18n（209 键对齐）

---

## 1. Product context

**What VN-Agent is**: A tool that turns "one line of theme" into a runnable Visual Novel (Ren'Py project + Web-playable output). Under the hood: LangGraph state machine → Director (outline) → StructureReviewer (Sonnet, non-blocking) → StateOrchestrator (Haiku, symbolic state → NL constraints) → Thinking-fanout (per-scene) → Writer (Sonnet, wave-barrier parallel) → DialogueReviewer (3-layer: structural + mechanical + 5-dim quality) → Asset agents (parallel, Nano Banana + rembg) → Ren'Py compiler. Multimodal output: script, sprites, backgrounds, BGM cues.

**Why it fits AI PM roles**: 
- Not another chatbot demo. This is a **multi-Agent production pipeline** with actual observability, cost tracking, and quality gates — the surface area is closer to Cursor / Perplexity / Notion AI than to "wrap ChatGPT".
- Every AI PM interview canonical question (avoiding homogeneous output, human-AI collaboration UX, evaluation/AgentOps, commercialization under LLM cost pressure, data flywheel) has a shipped-code answer here, not just a slide.
- Long-form (50-scene) generation forces you to confront **long-context consistency** — the interviewer's real signal for whether you understand LLM limitations vs "prompt harder" thinking.

**User + use case (one paragraph)**: The primary user is an **independent VN creator / student UP-主** who has a story idea but neither engine skills nor art resources. Current pain: Ren'Py has a steep learning curve, custom art is expensive, and there is no fast feedback loop. VN-Agent lets them chat with a workbench that runs the full 6-Agent pipeline; they can upload their own worldview notes, retrieve open-source assets, and export a runnable Ren'Py project or a web-playable share link. A secondary "Autopilot" entry serves potential *players* who input one line and get a playable output in ~8 minutes (aspirational target).

---

## 2. What actually shipped (verified from repo)

### 2.1 v3 (pre-v4) — the technical spine (Phase 1 → Phase 13-3)

| Feature | Product motivation | Technical approach | Evidence |
|---|---|---|---|
| 6-Agent LangGraph DAG (Director / StructureReviewer / StateOrch / Thinking / Writer / DialogueReviewer / Assets) | Single-prompt generation truncates + JSON breaks | Conditional edges, 3-round revision loop, `asyncio.gather` + `return_exceptions=True` for asset stage fault isolation | `src/vn_agent/agents/graph.py` |
| Two-layer Reviewer + smart routing | Reviewer used to fire "回 Writer" on every FAIL — but graph-class fails (unreachable scene) aren't Writer's job | `ReviewResult.can_writer_fix` field; `decide_retry_target` pure fn dispatches to Director/Writer/Accept | `src/vn_agent/agents/reviewer.py:30`, `src/vn_agent/agents/routing.py`, commit `8a2ac88` |
| Symbolic World State + StateOrchestrator | Long VNs drift ("Mira reads the manuscript again despite reading it in ch2") | Director declares boolean/int vars; Haiku translates to NL constraint, injected into Writer prompt | `src/vn_agent/agents/state_orchestrator.py` (Sprint 9-6) |
| 3-layer memory for long-form (**global cache + chapter folding + local retrieval**) | Sonnet context isn't infinite; naive full-history injection wastes cache | ① Global cache: Character Bible → `cache_control=ephemeral` (`enable_prompt_caching=True`, first 1.25×, 5min reuse 0.1×). ② Chapter folding: `enable_chapter_rollup=True` (async rollup every 10 scenes, dynamic 200–800 words, skipped under 10 scenes); per-scene `enable_scene_summarization=False` is opt-in at ≥15 scenes. ③ Local retrieval: `use_lore_retrieval=True`, `lore_k=4` (`eval/lore.py`, always/chapter/scene scopes). **The sliding window `writer_context_window` is a fourth knob, default 0 (off)** — earlier docs wrongly listed it as one of the three at "default N=2"; the code is authoritative | `config.py:166/199-223`, `src/vn_agent/agents/summarizer.py`, `eval/lore.py`, `state_orchestrator.py`, Sprint 11-1/11-2/11-3 |
| Dual-Judge cross-validation (Sonnet + GPT-4o) | Sonnet grading Sonnet is echo-chamber — 4.17 self-score would be dismissed | Sonnet 3.68 vs GPT-4o 3.66, **Pearson r=0.643, ±1-pt agreement=87%** | `docs/PRODUCT.md` §关键指标, commit `4f1228f` |
| 8-cell writer_mode sweep (data-driven default flip) | `writer_mode=action` (few-shot RAG) was default, but data hadn't been checked | 8-cell sweep {literary, action, baseline_self_refine, baseline_single} × {lighthouse, dragon} → **literary 4.17 > action 3.92 > self_refine 3.45 > baseline 3.25** — flipped default to literary | Sprint 8-5, sweep result JSONL logs, `config.py` writer_mode comment |
| RAG pivot (dialogue → lore/entity retrieval) | "RAG became a flower vase" after literary mode disabled dialogue few-shots | Same FAISS + sentence-transformers infra, retrieve character/location/world-var entities instead. Per-run in-memory index, no LLM added | `src/vn_agent/eval/lore.py`, Sprint 10-2 |
| BM25 + weighted RRF hybrid retrieval | Pure FAISS misses lexical matches on strategy tags | `rank_bm25` at 0.3 weight + FAISS 0.7 weight | Sprint 6-4, `rank_bm25` dep |
| Per-request `TokenTracker` via `ContextVar` | Module-level singleton polluted across concurrent jobs | ContextVar-scoped tracker persisted with blackboard | `src/vn_agent/services/token_tracker.py`, Sprint 6-5 |
| Anthropic Key Pool + exponential backoff + Sonnet/Haiku split pools | Single-key 429 killed the whole pipeline | round-robin + per-key cooldown + tenacity jitter | `src/vn_agent/services/llm.py:_pool_for`, commit `95b8b97` |
| Health-signal gate on stress runner | 50-scene tier was burning $15 even after cheap tier showed degradation | `_compute_health_signals` on retry-density/key-rotation/wall-time; `--abort-on-degradation` | `scripts/smoke_longvn.py:109`, `scripts/stress_runner.sh`, commit `745e03d` |
| Structured output via Anthropic Tool Use + 3-tier Writer recovery chain | max_tokens truncation was 89% (16/18) on M0 run | Tool Use for schema; recovery = JSON array → per-object brace scan → continuation call | `src/vn_agent/schema/script.py:418`, `writer.py:_parse_dialogue`, commits `05db6d8`, `441fbc6` |
| Ren'Py compiler (Jinja2) + rembg u2net_human_seg portrait masking + Nano Banana image provider | 全流程输出到 Ren'Py 工程可直接 `renpy launch` | See Phase 13 Sprint 10-1 (Nano Banana + fallback chain), Sprint 12-3b (rembg), Sprint 12-3c (visual layer) | `src/vn_agent/compiler/`, `character_designer.py`, `scene_artist.py` |

**v3 aggregate**: 166 total commits · ~15.8K LoC src · ~12.4K LoC tests · **659 unit tests passing** (docs/v3/SHOWCASE_v3.md — the exact number may drift +/- 20 as v4 P0/P1 added tests, but the order is the same).

### 2.2 v4 P0 (multi-source material fusion M0) — just landed

| Feature | Product motivation | Technical approach | Evidence (commit) |
|---|---|---|---|
| Text upload channel (md/pdf/docx → chunk + embed → `user_upload` scope in lore RAG) | Creators have their own worldview notes; v3 had nowhere to put them | `assets/text_ingest.py` + reuse `eval/embedder.py` + new scope in `eval/lore.py`; frontend upload wired | commits `d1746d4`, `eed2c2d` |
| Local open-source asset library (manifest-driven, 11 CC0 seed assets) | Content homogeneity root cause = "only theme in, only LLM out" | `assets/library.py` — manifest JSON as source of truth (NOT filesystem scan, would silently include unlicensed files); tag intersection + optional sentence-transformer cosine; 3 background + 5 sprite + 3 BGM CC0 seed | commit `1957158`, `data/assets/opensource/manifest.json` |
| Web-search agent (topic → planned queries → search → chunk → RAG) | Simple URL fetch dead-end; wanted "AI planner over multiple sources" | Provider protocol: `SerperProvider` (prod), `StaticFixtureProvider` (test), `GeminiGroundingProvider` (M1 stub). Haiku for query planning. Hard cost gate: **5 queries max, 8k tokens max**. Every chunk carries `source_url` + `retrieved_at` + `search_query` | commit `eed2c2d`, `src/vn_agent/assets/web_search_agent.py` |
| Cross-source dedup (image pHash + text embedding cosine) | Web results overlap heavily (Wiki + Fandom + Reddit mirror each other) | `assets/dedup.py` — reuse `imagehash` lib; text via cosine | commit `d1746d4`, `src/vn_agent/assets/dedup.py` |
| License gate (whitelist: **CC0 / CC-BY / CC-BY-SA / user_owned / derived**) | Marketplace direction needs legal-safe defaults | `assets/license_gate.py::audit()` (report-mode) + `enforce()` (raise `LicenseGateError`). Whitelist not blacklist — anything else needs explicit review | `src/vn_agent/assets/license_gate.py` |
| Diversity index metric | v4 首要产品指标 #3 (non-LLM material share ≥ 30%) | `metrics/diversity.py` counts non-LLM asset share, writes to `vn_script.json.metrics` | `src/vn_agent/metrics/diversity.py` |
| Salvage (Writer partial-flush + web resume endpoint) | Real run 3cbbf260 hung 52 min at Reviewer with zero artifacts | `salvage.py`: pick most-complete between `vn_script.json` and `snapshots/*.json`. `POST /api/projects/{id}/resume` on the web side | commit `d52261c`, `src/vn_agent/salvage.py` |
| Reviewer pending-debug flush + hard timeout | Same 52-min hang: no way to grep which prompt was stuck | `services/pending_debug.py`: write `debug/{name}.pending.txt` before every wrapped LLM call; rename to `.done.txt` / `.error.txt` after. `asyncio.wait_for` with `settings.reviewer_timeout_seconds` (default 300s) | commit `47d50fa`, `src/vn_agent/services/pending_debug.py` |
| Per-request mock toggle + `run-analyzer` subagent + docs §9 commercialization | v3 mock was env-var only (leaky in multi-job); commercialization section was missing | Per-request `mock=true` flag + docs §9 (3-path business model + 7-layer cost table + Pro/Team unit economics) | commit `383a982` |
| Upload delete + cancel-selection UX | Uploaded wrong file → no way out | Frontend delete + cancel button; server-side unlink | commit `1602ddd` |

### 2.3 v4 P1 (data flywheel M0) — just landed

| Feature | Product motivation | Technical approach | Evidence |
|---|---|---|---|
| `feedback/store.py` — append-only JSONL (`data/feedback/all.jsonl`) | Data flywheel needs single source of truth across jobs, not per-job silos | Record schema frozen at M0: `{id, job_id, scene_id, verdict, reason, tags, context, created_at}`. Immutable — edit = new record + `supersedes: id` | commit `49baaf2`, `src/vn_agent/feedback/store.py` |
| `feedback/injector.py` — BM25 few-shot injection into Writer prompt | Down-votes need to actionably shape next generation | `rank_bm25` (reuses Sprint 6-4 dep), top_k=3, min_score=-1.0 (tuned for small M0 corpus where IDF goes negative). Query is scene-shaped (`description + strategy + characters_present`), not theme-shaped. **Down-votes only** (up-votes have no "AVOID" signal for prompt injection; they matter as anchors in Reflection). Injection format = prose `"AVOID: ..."` lines above Writer's "write N dialogue lines" instruction | `src/vn_agent/feedback/injector.py` |
| `feedback/reflection.py` — Reflection Agent (batch job → `dynamic_guidelines.json`) | L2 layer: proximate rules to structural rules | Haiku (not Sonnet — classification-flavored, ~$0.01/run at 1k records). `--min-samples` default 20 (running on 3 records = nonsense). Atomic write (tmp + rename). Emits polarity + confidence per rule. Writer picks it up on next boot as a prompt-cached suffix | `src/vn_agent/feedback/reflection.py` |
| **NOT shipped at M0**: DPO fine-tuning (L3) | Needs ≥1k labeled records + training compute; M0 has neither | Explicitly excluded — "M1.5 when data lands" | plan file §"P1 数据飞轮 · 真实用户数据补齐路径" |

**v4 P0/P1 aggregate test posture**: `tests/test_assets/` (7 files: dedup, library, license_gate, text_ingest, upload_delete, web_search_agent) + `tests/test_feedback/` (3 files: store, injector, reflection). Every module has isolated unit tests; integration test for upload → generate → diversity flow exists (`test_upload_flow.py`).

### 2.4 v4 P2 (frontend polish + JIT streaming) — shipped

| Feature | Product motivation | Technical approach | Evidence (commit) |
|---|---|---|---|
| Tailwind v4 + design system fix | `className` referenced Tailwind classes but the dep chain was never installed — every screenshot looked unstyled | `tailwindcss` + `@tailwindcss/vite` wired into `frontend/vite.config.ts`; verified via real `npm run build` | commit `a309058` |
| SSE just-in-time scene streaming | Player had to wait for the whole script before seeing anything — no "watch it get written" moment | `services/job_events.py` per-job pub/sub (ContextVar-scoped like `TokenTracker`), `/api/projects/{id}/stream/scenes` SSE endpoint, `VNPreview.tsx` consumes as scenes land | commit `a309058`, `src/vn_agent/services/job_events.py` |

**Not done**: manual browser click-through of the streaming UX (unit/integration tests cover the SSE pipeline and store state machine, not the actual rendered "Watch Live" experience) — explicitly deferred by the user (2026-07-21) to keep building; still open as of 2026-07-29.

### 2.5 v4 P3 (Chat Ops M0) — shipped

| Feature | Product motivation | Technical approach | Evidence (commit) |
|---|---|---|---|
| 4-intent classifier (local_regen / add_character / edit_asset / explain) | Post-generation editing was CLI-only and form-based, not conversational | `chat_ops/intent_router.py`, Haiku classifier, bilingual mock-mode keyword fixtures for zero-cost demo | commit `47d59e4` |
| L1 preview-before-execute confirm card | Misclassified intent silently mutating a scene is worse than a slow UX | Every mutating intent returns a `requires_confirmation` preview first; `POST /chat/{preview,execute}`; only executes after explicit frontend confirm | commit `47d59e4`, `ChatPanel.tsx` |
| `local_regen` real executor (only fully-wired intent) | Honest M0 scoping — better to ship 1 real executor than 4 fake ones | Reuses `agents/local_regen.py::regenerate_scene` (not reinvented); `regenerate_scene` writes `vn_script.json` directly (bypasses the web JobStore), so `chat_execute` re-reads from disk and re-syncs the SQLite blackboard — a real consistency edge case, covered by `test_execute_local_regen_syncs_blackboard_from_disk` | commit `47d59e4` |
| Audit trail per resolved turn | Needed project-state auditability, not full UI telemetry | One JSONL line per *resolved* turn (mutating intents only log after confirm; cancelled turns log nothing) to `<output_dir>/chat_ops/turns.jsonl`, same convention as `rag_retrievals.jsonl` | commit `47d59e4` |

**Honest M0 scoping**: all 4 intents classify correctly, but only `local_regen` has a real executor. `add_character`/`edit_asset` return an honest "not implemented in M0" message — not a silent failure. L2 confidence threshold / L3 top-K options / L4 feedback-into-P1-flywheel are roadmap, not built. Browser click-through not done.

### 2.6 v4 P4 (PlaytestAgent + Vision LLM Judge M0) — shipped

| Feature | Product motivation | Technical approach | Evidence (commit) |
|---|---|---|---|
| Branch walker | Need to auto-traverse every reachable path, not just the happy path | `playtest/branch_walker.py` respects `BranchOption.requires` state-gating — stricter than `reviewer.py`'s existing BFS reachability check | commit `c4793a5` |
| Pillow frame compositor (scope-cut from real Ren'Py headless execution) | Original plan assumed real engine screenshots (`--warp` + `renpy.screenshot()`) | Repo research found **zero existing headless-execution infra** — no subprocess wrapper, no `--test` flag, no screenshot automation anywhere. User-confirmed M0 scope cut to Pillow-composited representative frames from the pipeline's own real/placeholder PNGs; real engine screenshots deferred to M1 | commit `c4793a5`, documented scope note |
| Vision LLM Judge, 5-dim scoring | Need "is this actually fun/coherent", not just "does it compile" | `playtest/vision_judge.py` feeds composited frames + dialogue log to Claude vision; `services/llm.py` gained an `images` param — **repo's first vision-LLM call site** | commit `c4793a5` |
| CJK rendering bug found + fixed en route | Pillow's default font has no CJK glyphs — Chinese text rendered as tofu boxes | Switched to a system CJK font + character-level (not word-level) line wrapping; verified visually on both English and Chinese mock-generated screenshots | commit `c4793a5` |

**Not done**: real engine headless screenshots (M1, needs a Ren'Py `--warp` harness that doesn't exist yet); Vision Judge cost/score not yet measured on a real API run (mock-verified only); browser click-through of the Playtest report UI.

### 2.7 v4 P5 (Autopilot M0) — shipped, plus two real bugs found and fixed en route

| Feature | Product motivation | Technical approach | Evidence (commit) |
|---|---|---|---|
| One-click "⚡ Autopilot" button | Every prior phase shipped a capability but nothing assembled them into "type a theme, get a playable VN" | Reuses the pre-existing `fast_mode` auto-skip-review chain; adds preset resolution + auto-entry into the SSE-streamed player on first scene | commit `5e8d621` |
| Per-job settings override via `ContextVar` | `get_settings()` was `@lru_cache`'d process-wide singleton called from ~20 agent/graph sites — Autopilot needed a per-job preset without touching all 20 call sites | `config.py::get_settings()` split into `_load_default_settings()` (cached) + a `_settings_override: ContextVar[Settings\|None]` checked first; every existing call site gets per-job overrides for free | commit `5e8d621`, `src/vn_agent/config.py` |
| **Bug found + fixed (user-confirmed)**: `/generate` double-execution + status-write race | Discovered while designing Autopilot's success-rate KPI — the metric would have been measuring a race condition | `POST /generate` fired an independent background `_run_job` task on *every* real generation, while the SPA's own `generate-setting → generate-script` chain ran the *same* job concurrently; `_run_job` took the concurrency semaphore, the other path didn't. Fixed with a new `interactive` request field (SPA sends `true` and skips `_run_job`; headless API callers default `false`, unchanged contract) | commit `5e8d621` |
| **Bug found + fixed (user-confirmed after full disclosure)**: real API spend during a `--mock` CLI smoke test | Routine sanity check (`vn-agent generate --mock`) made **5 real Anthropic calls, ~$0.12** | Root cause: `agents/reviewer.py` / `structure_reviewer.py` route their real LLM call through `services/pending_debug.py::ainvoke_with_pending_debug()`, which does its own fresh `ainvoke_llm` import — bypassing the CLI's static per-module mock patch entirely. Fixed: `_patch_mock_llm()` now also sets the `mock_mode_var` ContextVar that `ainvoke_llm` itself checks internally, closing the gap for *every* call path, not just the patched ones. Verified safe (sub-second dispatch, no network round-trip) + permanent regression test added (`tests/test_cli/test_mock_patch.py`) | same commit `5e8d621`, disclosed to the user in full before any fix was applied |
| `autopilot/outcomes.py` — M0 records, does not yet rank | Roadmap needs a data source for M1's "rank presets by past success" | Append-only JSONL (`data/autopilot/runs.jsonl`), same shape as `feedback/store.py`; M0 only appends, no consumption logic yet | commit `5e8d621` |

**Scope note (user-confirmed)**: `docs/v4/PRODUCT_v4.md` originally described Autopilot as a standalone URL/API entry point; `App.tsx` has no client-side routing today, so M0 shipped as a button inside the existing workbench SPA instead — same scope-cut pattern as P3/P4, documented not hidden.

**v4 P0-P5 aggregate**: 939 tests collected (2026-07-29 `pytest --collect-only`), last full regression 937 passed / 1 skipped / 1 deselected, exit 0. **Not done across all four of P2-P5**: manual browser click-through — deferred by the user on 2026-07-21 to keep building, still open as of 2026-07-29 (a browser smoke-test session was attempted this date but blocked on the Claude-in-Chrome extension not being connected; servers were left running for a retry). **Partially closed by P6**: Tasks 5/6/7/8 of the redesign each ran a real mock-mode browser pass, which is the first browser verification of any of P2-P5's UX; see §2.8 for exactly what is and is not verified.

### 2.8 v4 P6 (frontend redesign — structure, not palette) — default shell, branch not yet merged

Branch `feat/frontend-redesign-v4`, **19 commits** (`fa68464`..`1ac8ebf`, verified `git rev-list --count main..feat/frontend-redesign-v4`; 17 of them are the redesign proper, `fa68464`..`3730936`). Spec `docs/v4/FRONTEND_REDESIGN_v4.md` (`a25e1e2`), plan `docs/v4/FRONTEND_REDESIGN_PLAN_v4.md` (`5a8a0b8`), engineering ledger `.superpowers/sdd/FRONTEND_REDESIGN_PLAN_v4/progress.md`.

| Feature | Product motivation | Technical approach | Evidence (commit) |
|---|---|---|---|
| Reframed the problem from "pick a palette" to **two structural defects** | The first proposal offered three "visual directions"; the user killed it in one line — *"这三个的区别感觉只是颜色而已，本质上是一样的。"* Correct: all three shared one layout | Re-surveyed and named the real defects. **A**: a constant 50/50 chat-vs-panel split — the default shape of every AI SaaS, unrelated to the subject matter. **B (worse)**: the multi-Agent pipeline, the product's entire differentiator, was invisible — `PreviewPanel` rendered a spinner and one line of text while the graph streamed real per-node events that were all discarded | `docs/v4/FRONTEND_REDESIGN_v4.md` §1.2-1.3, spec commit `a25e1e2` |
| **Structured pipeline signal, end to end** (the headline fix) | `graph.astream()` emits one update per graph node; the web layer collapsed that into a single progress *string*, and the frontend substring-matched that string back to guess a 5-step bar. A structured signal downgraded to prose and guessed back out of it | `services/job_events.py::publish_node()` (ContextVar pattern mirroring `publish_scene_ready`) → SSE `node` event → store `pipelineNodes` / `pipelineOrder` → `PipelineGraph.tsx` hand-written SVG spine. SSE endpoint was already a generic forwarder and the frontend ignores unknown event types, so **no version negotiation and no breaking change for existing clients** | `fa68464`, `7c8a339`, `5fe971d`, `0315aad`; `src/vn_agent/services/job_events.py:56` |
| Real UX bug fixed en route: **6 of 10 node labels were missing** | Users were shown raw internal identifiers — literally `Running cross_ref_sync` | `_STEP_LABELS` went from 4 entries to 10 (verified: `git show 6f7a285:src/vn_agent/web/app.py` has 4, current has 10). Guarded by `tests/test_web/test_pipeline_labels.py`, which walks the **compiled graph** and fails if any node lacks a label — so a future node can't silently regress it | `7c8a339` |
| Latent bug nobody had noticed: **progress step 2 was unreachable** | The old `stepIndex()` matched `p.includes('script')` before `p.includes('review')`, so every step name containing "script" claimed the match and 审校/Review was skipped — the bar silently never showed that stage | Replaced prose matching with a `Record<AppStep, number>` table plus a live `pipelineActive === 'reviewer'` check. Found *because* the i18n work could not translate the progress strings without breaking the bar — the translation blocker exposed the logic bug | `782b5de`; `frontend/src/components/PreviewPanel.tsx:10-37` (the comment documents the defect) |
| Full zh/en i18n where UI chrome had been **100% hardcoded English** | The demo audience is a Chinese-speaking interviewer, and the chat column is the most-read region of the screen | No third-party library. `i18n/dict.ts` + `useT.ts`; **209 keys in zh and 209 in en, key sets identical** (verified by parsing the file). `tsc` enforces parity structurally — `dict[lang][key]` means a missing `en` key fails the build. Chat log stores **key + vars** and resolves at paint time, so toggling the language **retranslates the entire history**, not just new messages. Node labels localise client-side because the SSE event already carries the structured node id; the backend keeps emitting stable English | `bfdf963`, `b046835`, `da5659a`, `5b1ebeb`; `frontend/src/i18n/dict.ts` |
| **Six-layer migration with independent rollback** | The frontend has **no test framework** (`package.json` has no vitest/jest), so stability could not be bought with tests — it had to come from architecture | L0 backend events → L1 tokens → L2 i18n → L3 shell switch → L4 pipeline+board → L5 cutover. Contract freeze: `api.ts` signatures and store **action** signatures unchanged, additive only. Old and new shells coexist; `?shell=v1` / `?shell=v2` wins and persists to localStorage | `8113a7f`; `frontend/src/shell/useShellVariant.ts` |
| Form-follows-`AppStep`: the 50/50 split is dead | Defect A | `WorkbenchShell.resolveForm()` maps `AppStep` → one of 6 forms; chat column width follows the form — `player: 0` (full-bleed artifact), `pipeline: 20rem` (the stage is the subject), others `24rem` | `4f26c00`; `frontend/src/shell/WorkbenchShell.tsx:13-39` |
| Storyboard **without orphaning the action bar** | A redesign that replaced `ScriptPanel` would have orphaned the only 5 script-review confirm buttons and the per-scene dialogue editor | `StoryboardBoard` + `SceneCard`; `ScriptPanel` is kept as the **card detail view**, not replaced. In-place rewrite feeds the P3 Chat Ops intent router, turning "type which scene you mean" into spatial selection | `7319a3a`, `0470352`; `frontend/src/components/StoryboardBoard.tsx:12` |
| Bundle regression caught, weighed, then removed | L4 pulled framer-motion into the module graph for exactly two effects | `4f26c00` recorded the cost honestly in the commit message (270→406 kB raw, **81→125 kB gzipped**) rather than shipping it silently; `717c203` then replaced framer-motion with CSS `@keyframes` (405→280 kB raw, **125→84 kB gzipped**, ~3 kB above the pre-L4 baseline). Secondary win: `prefers-reduced-motion` now applies automatically, whereas a JS library animating inline styles bypasses it | `4f26c00`, `717c203` |
| `director` never reports over the node stream — **found by browser verification, not by reading code** | A spine rendering all 10 nodes from `pipelineNodes` alone would show `director` stuck on `pending` for the whole run — the first node, the most conspicuous possible place for a wrong state | `publish_node` is wired only into `_run_script_generation`, which enters the graph with the outline already built; `director` runs earlier inside `generate_setting()`, which has no `publish_node` call. Fix: seed `director: 'done'` in `confirmSetting()` (reaching that call means the outline exists by definition). Same pass: `asset_generation` renders as legitimately **skipped** while `text_only` is on, not pending-forever | ledger §"INPUT REQUIRED BY TASK 9"; resolved in `0315aad` |

**P6 verified-in-browser vs not** (this distinction matters — see §9.2):
- ✅ Verified in a real mock-mode browser session: language toggle switching the whole chrome live with no reload (Task 6); `?shell=v1`/`?shell=v2` switching plus localStorage stickiness in both directions, and a full Autopilot run inside the v2 shell reaching the compiled project (Task 7); the live `node` event sequence `structure_reviewer → director_step2_redo → structure_reviewer → state_orchestrator → thinking_fanout → cross_ref_sync → writer → reviewer`, which also proved the revision loop-back is real and observable (Task 8).
- ✅ **Also verified (2026-08-11)**: the full 10-point walkthrough of the final v2 shell passed **10/10** in a mock-mode browser session — empty state, pipeline theatre lighting nodes in order, `setting_review` routing to SettingPanel with both confirm buttons present (Fast Mode off), storyboard grid, card detail with all five script actions and `focusScene` opening the picked scene rather than the first, play-from-card entering at that scene with the chat column collapsed, in-place rewrite through the Chat Ops intent card, Autopilot zero-click to the full-bleed player, `?shell=v1` behaviourally unchanged, and no application console errors. The walkthrough also **caught two defects the type checker could not**: the activity line rendering English during the two phases with no active graph node, and the chat buttons wrapping/clipping at the 20rem pipeline width — both fixed in `4e7c370`.
- ✅ **Task 14 done** (`3730936`): `DEFAULT_VARIANT` is now `'v2'` in `frontend/src/shell/useShellVariant.ts`, flipped only after the walkthrough passed, and verified with localStorage cleared so it tests what a genuine first-time visitor sees. **Demos now work on a bare `/`.** `?shell=v1` remains the escape hatch.
- ❌ **Not done, on purpose**: Task 15 (delete the legacy shell). Deferred past the interview season — losing `?shell=v1` costs a live-demo fallback, while keeping it costs three files of dead code.
- ❌ **Still not verified**: the ~250ms form-change fade (needs frame timing, not stills), and the P2-P5 UX walkthrough on the *legacy* shell (a pre-existing item from 2026-07-21, unrelated to this redesign).

---

## 3. Metrics that hold up under interview questioning

**Categorization**: (M) = measured on real API run, (K) = measured on mock/computed, (T) = target not yet hit.

### Real-run measurements (M)
- **6-scene demo end-to-end**: ~$1.7 real API, ~30 min wall (`docs/PRODUCT.md` 关键指标 line 429; Phase 12-3 Showcase demo with Sonnet + Nano Banana + Haiku)
- **Continue-outline (creator-mode second half)**: ~$0.46, ~9 min (same source)
- **M0 baseline (6-scene, real API, with assets)**: 38.1 min, $2.04 (`docs/v3/SHOWCASE_v3.md` §6, 2026-04-26)
  > ⚠️ **Reconciling $1.7 vs $2.04** (an interviewer will spot two different 6-scene costs): both are **asset-inclusive** real runs — this is not a text-vs-assets difference. $2.04 is the 2026-04-26 M0 baseline, which `SHOWCASE_v3.md` §6 explicitly ran to "reveal the routing optimisation headroom"; $1.7 is the Phase 12-3 Showcase demo taken after that optimisation landed.
  > **Standard answer**: "Two real runs with the `can_writer_fix` routing fix landing between them, so the ordering holds. But they are not a controlled A/B — different theme, different config — so I won't present the $0.34 delta as the routing saving. That saving was measured separately at ~$1.10/run in §4.1."
  > **Never say**: $2.04 − $1.10 = $1.7. The arithmetic doesn't work and they are two different things.
  > Also note: earlier docs labelled this run "text-only" — a mistake. `SHOWCASE_v3.md:45` shows it produced 6 scenes / 3 characters / **4 BGM cues**.
- **mini smoke #1 (3-scene)**: 10.4 min, $0.57 — validated routing optimization (~70% cost drop vs pre-fix)
- **mini smoke #2 (3-scene)**: 20.5 min, $1.13 — validated cap/schema length behavior (Sonnet treated `max_tokens=8000` as target: 3/3 hit cap, out tokens 7999/8000/8000 → **single scene cost +54%**, negative learning that cap is NOT a quality lever)
- **Cross-Judge Pearson r = 0.643, ±1-pt agreement = 87%** (Sonnet 3.68 / GPT-4o 3.66 on 8-cell sweep, commit `4f1228f`)
- **8-cell writer_mode sweep**: literary 4.17 > action 3.92 > baseline_self_refine 3.45 > baseline_single 3.25 (5-dim rubric, Sprint 8-5, `docs/v2/RESUME_v2.md` §评估实测数据)
- **Strategy F1 improvement**: keyword 0.21 -> LLM (qwen2.5:7b) 0.34, **+62% relative** (`docs/v2/RESUME_v2.md` section 评估实测数据). NOTE: `RESUME_v2.md` records this as "+57%"; 0.21->0.34 on the displayed (rounded) values is +62%, so the original figure was presumably computed from unrounded values whose raw eval JSON is no longer in the repo. Quote **0.21 -> 0.34** and, if pressed for a percentage, say "about +60%, computed from the rounded values" — do not quote +57% next to 0.21/0.34, an interviewer can compute the mismatch.
- **Reviewer avg passing threshold**: 3.5/5.0 (`settings.reviewer_pass_threshold` = 3.5, `docs/PRODUCT.md` Sprint 6-fix)

### Computed / structural (K)
- **166 total commits** (real `git log | wc -l`), **~15.8K LoC src / ~12.4K LoC tests** (`docs/v3/SHOWCASE_v3.md` §6 quotes 15,851 / 12,382)
- **659 unit tests passing** (v3 snapshot; count has grown with v4 P0/P1 additions)
- **Test-to-src ratio ~78%** (docs/v3/SHOWCASE_v3.md)
- **Cost reduction with budget preset (all-Haiku)**: ~73% vs baseline routing (`docs/v2/RESUME_v2.md`, computed from Sonnet $3/$15 vs Haiku $0.80/$4)
- **Prompt caching factor**: first 1.25×, 5-min reuse 0.1× (Anthropic ephemeral cache spec + Sprint 8-4 verified)
- **can_writer_fix routing savings**: ~$1.10 per 6-scene run avoided in wasted Writer cycles (`docs/v3/SHOWCASE_v3.md` §4.1)
- **Real API smoke total spend**: ~$3.74 across 3 verified runs (M0 + mini #1 + mini #2)
- **957 passed / 959 collected** (2026-08-12, executed on `main` in per-directory batches; 1 known flake `test_graph_routing.py::TestWarningsDedup`, 1 skipped). History: 939 (2026-07-29) → 947 (2026-08-10) → 959.
  > ⚠️ **Which number is which**: 939 and 947 were `--collect-only` *collection* counts, not pass counts; earlier docs rendering "947 passed" were wrong. 959 is collected, 957 is the measured pass count. **Say "~950 tests, 957 passing on the last run" — do not mix the two.**
  > Also note: running the whole suite in one process trips a torch/transformers Windows access violation partway (during `eval/embedder.py` index build); **run per directory and everything passes**, so it is single-process accumulated state, not a broken test. Confirmed unrelated to code changes by stashing and reproducing on pristine code.
- **195 commits on the P6 branch / 176 on `main`** (2026-08-11 `git rev-list --count`). ⚠️ The older "166 commits" figure in this file and the "170 commits" figure in `docs/v3/SHOWCASE_v3.md` §6 and `docs/v4/PRODUCT_v4.md` §7.3 disagree with each other and are both stale; quote the current count or say "~190 commits"
- **P6 pipeline labels**: 4 of 10 graph nodes labelled → 10 of 10 (`git show 6f7a285:src/vn_agent/web/app.py` vs current `src/vn_agent/web/app.py:1342`), exhaustiveness enforced by `tests/test_web/test_pipeline_labels.py`
- **P6 i18n coverage**: 209 zh keys / 209 en keys, key sets identical, 10 of them `nodeLabel.*` (parsed from `frontend/src/i18n/dict.ts`); parity is enforced by `tsc`, not by discipline
- **P6 bundle**: 81 kB gzipped pre-L4 → 125 kB after framer-motion entered the graph (`4f26c00`) → **84 kB after replacing it with CSS** (`717c203`), i.e. ~3 kB net over baseline for the whole redesign
- **P6 branch size**: 19 commits (`git rev-list --count main..feat/frontend-redesign-v4`, 2026-08-11)

### Targets — flag as aspirational (T)
- **50-scene end-to-end**: wall ≤ 30 min, cost ≤ $15 (T, target of Phase 13-1; 6-scene baseline is 38 min so ratio-projection is $13-19 range)
- **cache_read_ratio ≥ 0.5** on scene 10+ (T, infrastructure in place, needs long run)
- **First-scene TTFS ≤ 60s** (T, Sprint 12-1 north-star for streaming pipeline, not yet built)
- **Autopilot success rate ≥ 85%, ≤ 8 min end-to-end** (T, P5 M0)
- **Diversity index ≥ 30%** (T, v4 P0 metric — computed at export but no run has hit 30% yet because seed library is only 11 CC0 assets)
- **Chat Ops chat operations per session ≥ 8** (T, P3 not shipped)
- **Vision Judge cost ≤ $0.20/run** (T, P4 not shipped; estimated from 6 scene × 3 screenshots × Sonnet vision pricing)
- **Creator completion rate ≥ 40% (beta)** (T, no data — CLI can't measure)

**Interview truth-serum**: whenever the interviewer asks a metric, be ready to answer "measured on N=1 real run vs mock vs projection from baseline" — pretending mock numbers are production numbers is the fastest way to fail an AI PM interview.

---

## 4. Product decisions I made and why

Format: **Decision** · **Alternatives considered** · **Trade-off reasoning** · **Retrospective assessment**.

### 4.1 优先级方案 Y (10-14 weeks, simple 爆点 maximization)
- **Decision**: Order P0 (multi-source fusion) → P1 (data flywheel) → P2 (frontend + streaming, parallel) → P3 (Chat Ops) → P4 (PlaytestAgent) → P5 (Autopilot).
- **Alternatives**: Plan X (put frontend P2 first for demo面子); Plan Z (Autopilot first for player-side stickiness); "just polish v3" (no v4).
- **Trade-off reasoning**: 3-axis scoring (**resume-点 · demo-面 · product-落地**) put P0-③ (14) > P0-② (13) > ①/⑤/④ (12) > B (11) > C (9). Starting with multi-source (③) answers the highest-frequency AI PM question first ("how do you avoid content homogeneity") and unblocks P5 Autopilot's fallback ordering. Starting with frontend would have looked prettier but produced no differentiation story.
- **Retrospective**: P0 shipped in ~2 weeks as planned. Confirmed decision — the first thing interviewers ask when you show a VN generator is "how is this not just prompting Claude with a bigger context window?" and having "text upload + web search + open-source library + LLM 4-channel fusion with license gate" as an answer is genuinely differentiated.

### 4.2 v3 shelved B (self-evolving Agent) + C (PlaytestAgent) pulled back into v4
- **Decision**: v3 had two `P2 backlog` items that were "AI Ops / evaluation flywheel" and "PlaytestAgent + Vision LLM Judge". Both were shelved for time. In v4 they were pulled back as **P1** and **P4** respectively.
- **Alternatives**: leave them in v3 shelved as long-term architecture; move only one; do neither and finish frontend.
- **Trade-off reasoning**: **Both** map directly to top-3 AI PM interview questions (data flywheel + evaluation/AgentOps). Not pulling them back = throwing away the strongest resume-scoring opportunities the codebase already primes. And they're not free — B needs alpha users, C needs vision judge validation — but both leverage v3 infrastructure heavily (BM25, prompt caching, Pearson r cross-judge validation) so marginal engineering cost is 1-2 weeks each.
- **Retrospective**: B M0 shipped (49baaf2). Data is thin (作者自用 + 3-5 alpha planned), but **the closed-loop is provably running**, which is exactly what "M0" is supposed to demonstrate. The 校招 language is: "M0 数据是薄的，但闭环已跑通" — this reframes the honest gap as intentional scope.

### 4.3 Pivot from "player + creator dual UI" to "creator-centric + Autopilot"
- **Decision**: v3 mixed player and creator UI. v4 hard-splits: creator = workbench (P2/P3), player = Autopilot (P5).
- **Alternatives**: keep dual UI, split by preset (player = default preset, creator = custom).
- **Trade-off reasoning**: dual UI made both sides shallow. The engine knowledge required for creator flow leaked into player flow (needing Ren'Py SDK install) and vice versa. Autopilot as a **totally separate URL/API** removes the coupling and lets each side be deep. Also aligns with market data (Cursor split "user" and "developer" pricing, Perplexity split "regular" and "Pro"; single-tier products under LLM cost pressure die).
- **Retrospective**: correct call — see §9 unit economics table where dual-mode SaaS breaks and split usage-tier + Autopilot separate math survives.

### 4.4 License gate = whitelist, not blacklist
- **Decision**: `ACCEPTED_LICENSES = {CC0, CC-BY, CC-BY-SA, user_owned, derived}`. Anything else fails.
- **Alternatives**: blacklist NSFW / commercial-restricted; require reviewer approval on all sources; skip gate at M0.
- **Trade-off reasoning**: marketplace direction (§9 path B) needs legal-safe defaults. Whitelist forces the curator to justify inclusion; blacklist silently ships anything not-yet-blocked. Cost is 1-2 hours per new license type to review — acceptable insurance premium for avoiding "we accidentally shipped copyrighted assets in a paid product".
- **Retrospective**: correct — this is the kind of decision that reads as **PM instinct not engineer instinct** in an interview, because you're trading throughput (fewer assets pass) for downstream option (marketplace / commercial path).

### 4.5 Per-request `mock` toggle (not env-var-only)
- **Decision**: v3 mock was `VN_AGENT_MOCK=1` env var — process-wide. v4 added per-request `mock=true` in the API payload.
- **Alternatives**: keep env-var only; per-workspace toggle.
- **Trade-off reasoning**: multi-tenant testing (some jobs real API, some jobs mock in the same server process) is impossible with env-var. Per-request also enables Autopilot's cost gating ("free tier gets mock images").
- **Retrospective**: shipped (383a982). Enables the §9 "free user 3 works/mo mock images → Pro real images" tier design.

### 4.6 Web search = search-agent, NOT crawler
- **Decision**: Provider protocol (Serper prod / StaticFixture test / Gemini grounding M1 stub). Haiku plans 3-5 queries. Hard cost caps: 5 queries + 8k tokens per generation. Every chunk keeps `source_url` + `retrieved_at` + `search_query`.
- **Alternatives**: httpx + user-pasted URL (v3 crude version); build headless-browser crawler; use full Playwright.
- **Trade-off reasoning**: crawlers = compliance nightmare + brittle DOM parsing + rate-limit ban risk. Search-agent piggybacks on Google/Serper's compliance work and delegates DOM parsing to the API. Query planning by Haiku ($/1M input tokens is 6× less than Sonnet) keeps cost < $0.01 per generation. Hard cost gates prevent runaway topics from blowing budget silently.
- **Retrospective**: shipped (eed2c2d). Provider protocol pays off for testability — `StaticFixtureProvider` makes CI green without hitting network.

### 4.7 Reviewer pending-debug + hard timeout (defensive move after 52-min hang)
- **Decision**: Wrap every reviewer LLM call in `pending-debug` (writes `debug/{name}.pending.txt` before call, renames to `.done.txt` / `.error.txt` after) + `asyncio.wait_for` with 300s default timeout.
- **Alternatives**: rely on existing trace log (didn't fire on the hang case); add global request timeout only; skip and hope.
- **Trade-off reasoning**: real incident (job 3cbbf260) — 52-min hang on Reviewer with **zero on-disk artifacts**. Post-mortem: existing trace wrote nothing because the LLM SDK internally awaited a hung stream. Solution needed to be **before** the LLM call, not after. Pending files let operators grep for stuck prompts. Hard timeout is a floor on how long a single agent can consume; 300s > worst-case healthy Reviewer call (~120s) but < unreasonable.
- **Retrospective**: shipped (47d50fa) alongside salvage (d52261c). Classic "we found a bug, the fix produces observability for the whole class of hangs" outcome — the salvage utility itself is the receipt.

### 4.8 M0 scoping for P1 data flywheel: do L1+L2, NOT L3 (DPO)
- **Decision**: Ship 👍/👎 → BM25 injector (L1) + Reflection Agent (L2). Explicitly defer DPO fine-tuning (L3) to M1.5.
- **Alternatives**: Ship L3 stub; ship L1 only; ship no flywheel.
- **Trade-off reasoning**: DPO needs ≥1k labeled records + training compute. At M0 we have neither (3-5 alpha users planned). Attempting L3 would either fake data (dishonest) or produce a stub agent that never runs (dead code that would need to be defended in interview). L1+L2 is provably-running with just the author's own feedback — the flywheel *exists*, it just doesn't spin fast yet.
- **Retrospective**: shipped (49baaf2). The 校招口径 is: "M0 数据是薄的，但闭环已跑通；数据来源不只 alpha，还包括 P5 Autopilot 玩家 + P4 Vision Judge 三条自然沉淀源 — 我把这三个方向做在一起，就是为了让数据飞轮不靠单一入口" (see plan §"产品盲点后续跟进方案").

### 4.9 Autopilot M0 as a workbench button, not a standalone URL
- **Decision**: `docs/v4/PRODUCT_v4.md` originally specified Autopilot as an independent entry point (its own URL/API). M0 shipped as a "⚡ Autopilot" button inside the existing workbench SPA instead.
- **Alternatives**: build the client-side routing infra needed for a real standalone page; ship a bare API endpoint with no UI and call it "done" for M0.
- **Trade-off reasoning**: `App.tsx` has no router today. Building one to serve a single new entry point would have blown the 3-5 day M0 budget on infrastructure, not on the actual feature. A button that sets `autopilot: true` and reuses the already-built streaming player gets the same user-facing outcome (one input, one click, immediately playing) for a fraction of the cost.
- **Retrospective**: shipped, same session. This is the third of three v4 phases (with P3, P4) where the original plan document's scope got cut for an honest infrastructure reason discovered mid-build, not a quality shortcut — the pattern itself ("plan named a scope-cut reason before shipping, not after being asked") is worth naming as a process signal in interview.

### 4.10 Own dogfooding caught a real cost-safety bug — disclose before fixing
- **Decision**: when a routine `--mock` CLI regression check unexpectedly made 5 real paid API calls, stop immediately, do not attempt any further "let me just check" calls (which would spend more), root-cause using only safe/offline evidence (timing, ContextVar state), and disclose the full incident to the user before writing a single line of fix.
- **Alternatives**: quietly fix it and mention it in passing; fix first then explain; treat it as a minor detail not worth a dedicated disclosure.
- **Trade-off reasoning**: this project's own working agreement (`feedback_api_approval`) requires explicit confirmation before any real API spend — an *accidental* spend during what was supposed to be a zero-cost sanity check is exactly the failure mode that rule exists to catch, even though it wasn't a deliberate rule violation. Fixing quietly would have been faster but would have hidden a real gap in the safety mechanism from the person who owns the cost.
- **Retrospective**: user explicitly chose "fix it now" after the disclosure. The fix itself (closing the gap for *every* call path via the ContextVar the LLM client already checks, not just patching the two call sites that got caught) is the more defensible engineering outcome specifically because there was time to think it through rather than firefighting silently. Good interview material for "tell me about a mistake you made" — this one has a clean incident → disclosure → root cause → systemic (not point) fix → regression test arc.

### 4.11 Rejected my own first redesign proposal: the problem was structural, not chromatic

- **Decision**: The first frontend-redesign proposal offered three "visual directions". The user rejected it in one sentence — *"这三个的区别感觉只是颜色而已，本质上是一样的。"* Rather than produce a fourth palette, I re-surveyed the app and re-stated the problem as **two structural defects**: (A) a constant 50/50 split that is the default shape of every AI SaaS and has nothing to do with visual novels, and (B) the multi-Agent pipeline — the product's whole differentiator — being completely invisible in the UI while the backend streamed real per-node events that were thrown away.
- **Alternatives**: ship one of the three palettes and move on; adopt a component library (shadcn/ui) so it at least looks professional; treat "it looks like a template" as a taste complaint and defer it.
- **Trade-off reasoning**: a palette change is unfalsifiable — you cannot argue in an interview that indigo beats amber. A structural change is defensible: **the information architecture now exposes a process that genuinely exists in the system but had no representation in the product**. That is also why a component library was explicitly rejected (§7 of the spec) — a prefab kit *is* where the template feeling comes from; the differentiation is in information architecture, not in button radii.
- **Retrospective**: correct, and the receipts are concrete rather than aesthetic — the same work that made the pipeline visible also fixed 6 missing node labels, an unreachable progress step, and a signal-downgrade path. Interview framing: **"改的不是皮肤，是信息架构"** — making the AI's working process legible is a core AI PM problem, not a decorating job. Source: `docs/v4/FRONTEND_REDESIGN_v4.md` §1.2, §7, §9.

### 4.12 Stability by architecture, not by tests, because the frontend has no test framework

- **Decision**: Migrate in **six layers, each independently rollback-able**, with the old shell kept byte-for-byte alive behind a `?shell=v1` URL escape hatch that persists to localStorage, and a hard contract freeze: `api.ts` method signatures, return types and store **action** signatures may only gain optional parameters / additive fields.
- **Alternatives**: introduce vitest first and buy safety with tests (weeks of work before any visible progress); rewrite the shell in place and rely on manual clicking; feature-flag inside the existing components rather than running two shells.
- **Trade-off reasoning**: `frontend/package.json` has no vitest/jest — that is a fact, not a preference, and pretending otherwise would have been the dishonest option. So the safety had to be structural: if the contract layer cannot change, regression risk is confined to the render layer; if both shells coexist, any failure is one URL parameter away from a working UI — **including on interview day**.
- **Retrospective**: the escape hatch earned its keep as a *policy*, not just a mechanism: `DEFAULT_VARIANT` stayed `'v1'` until the walkthrough passed, and only then moved to `'v2'` (`3730936`), because the L5 cutover was deliberately gated on a browser walkthrough. The walkthrough then passed 10/10 and caught two defects the type checker could not, which is exactly why the gate existed. The honest version of "we shipped a redesign" here is "the redesign is the default, the escape hatch is retained, and I did not flip the default on a type-check alone."

### 4.13 Recorded a bundle regression in the commit message, then removed it

- **Decision**: When L4 pulled `framer-motion` into the module graph, the commit message (`4f26c00`) stated the cost in the open — 270→406 kB raw, 81→125 kB gzipped — and flagged it against the plan's TTI ≤ 3s target as a decision to make *before* cutover. A follow-up commit (`717c203`) then replaced the library with CSS `@keyframes`, landing at 84 kB gzipped, ~3 kB over the pre-redesign baseline.
- **Alternatives**: keep framer-motion (it was already installed and working); silently accept the +44 kB; drop the animations entirely.
- **Trade-off reasoning**: the library was buying exactly two effects — a pulse on the running pipeline node and a form cross-fade. Both are a few lines of CSS. A 44 kB gzipped dependency for two keyframe animations fails a straightforward cost/benefit test. There was also a correctness argument that only surfaced on inspection: `tokens.css` already has a `prefers-reduced-motion` block, but **a JS library animating inline styles bypasses it entirely**, while `@keyframes` honour it automatically — so the cheaper option was also the more accessible one.
- **Retrospective**: one deliberate behavioural loss is documented rather than hidden — `AnimatePresence mode="wait"` did exit-then-enter; the CSS version only fades the incoming form in. Reproducing the exit half would mean keeping the outgoing tree mounted, and the wait introduced dead time between forms. The transferable interview point is the *process*: state the regression in the commit at the moment you incur it, so the decision to keep or remove it is made on data instead of being discovered later by a user.

---

## 5. Data flywheel + AgentOps evidence (校招 爆点)

The single strongest AI PM narrative in this project is the **4-blind-spot mesh**: rather than 4 independent gaps, they're designed as a network where each blind spot's follow-up plan feeds the others.

### 5.1 The 4-blind-spot mesh (from plan file §"产品盲点后续跟进方案")

```
        P5 Autopilot                          P1 Data flywheel
      (success rate / cost)                 (creator 👍/👎)
              │                                      │
              │            ┌───────────┐              │
              └─── params ─▶│           │◀─── feedback ┘
                            │  联动池   │
              ┌── scores ──▶│           │◀── intent-corrections ┐
              │            └───────────┘                        │
       P4 PlaytestAgent                                 P3 Chat Ops
     (Vision Judge score)                          (intent-router sampling)
```

Cross-linkages:
- **P3 intent-router L4 fallback** (misclassifications become training data) → **P1 dynamic_guidelines.json**
- **P4 Vision Judge score** (M0.5) → **P5 Autopilot** preset selection (M1)
- **P5 Autopilot completion rate** (M0.5) → **P1 flywheel** as implicit feedback (M1)
- **P1 dynamic_guidelines** (M1) → **P3 intent-router prompt** + **P4 Vision Judge scoring baseline**

**校招 one-liner**: "四个盲点不是并列，而是一张网 — 每个盲点的解决方案都是别的方向的输入。这是数据飞轮的产品设计思维，不是模块化实现思维。"

### 5.2 P1 M0 concrete flywheel (what's actually running today)

```
creator 👍/👎 (frontend chat/preview)
    │
    ▼
feedback/store.py — append data/feedback/all.jsonl (immutable)
    │
    ├──────────────────┐
    │                  │
    ▼                  ▼
Injector             Reflection Agent (batch, Haiku)
(BM25 top_k=3        (--min-samples 20, ~$0.01/run)
 down-votes only,        │
 scene-shaped query)     ▼
    │              dynamic_guidelines.json (atomic write)
    │                    │
    ▼                    ▼
Writer prompt          Writer system prompt suffix
"AVOID: X. AVOID: Y."  (goes through prompt cache, 0.1× on reuse)
```

Design choices that reveal PM discipline:
- **Down-votes only in the injector**: up-votes carry no actionable "AVOID" signal for prompt injection. They matter as anchors in Reflection (positive rule extraction), but injecting "PREFER" prose into a scene-generation prompt confuses the model. Reading the interviewer's face after saying this — they will nod, because this is the kind of taste-not-hype signal PMs need.
- **BM25 not embeddings**: feedback reasons are short (≤200 chars), keyword-heavy, per-language. BM25 punches above weight on that distribution and needs no model download. Reuses Sprint 6-4 dep — **not-inventing-wheels evidence**.
- **`min_score = -1.0`**: BM25 IDF goes negative on tiny corpora (M0 corpus is small by design). A strict positive floor gates every hit for the first ~30 records; as the corpus grows past ~30 records IDF normalizes. This is the kind of implementation detail that proves you understood the algorithm.

### 5.3 AgentOps observability layer (v3 → v4 continuous)

- **`run_metrics.json`** per job: `wall_seconds`, `total_cost_usd`, `cache_read_ratio`, `key_rotation_count`, `health_status`, `degradation_signals` (v3 Phase 13)
- **`rag_retrievals.jsonl`** per scene: query, retrieved_ids, similarity — turns "why did ch3 mention Aldric" from black box to grep-able
- **`snapshots/{scene}.json`** per scene — v3 Sprint 11-4 basis for single-scene regen + v4 salvage
- **`debug/{name}.pending.txt`** — v4 P0 tell-you-which-prompt-is-stuck flush layer
- **`trace.json`** — v3 Sprint 9 timing + token per node
- **Reviewer 3-layer classification** (structural / mechanical / LLM quality) → `can_writer_fix` bit → `decide_retry_target` routing decision
- **Health-signal abort** on `--abort-on-degradation`: `retry > 5` or `key_rotation_density > 1.0` or `wall_minutes > 2× expected` triggers red → stress runner aborts before burning the 50-scene tier's $15

This is the AgentOps stack you'd expect at a product like Anthropic Claude / OpenAI Assistants / ByteDance Coze — and every module has a repo path.

---

## 6. Commercialization + cost model (PRODUCT_v4 §9 distilled)

### 6.1 Three-path business model (they layer, not compete)

| Path | Description | Priority | v4 dependency |
|---|---|---|---|
| **A · SaaS 订阅** (creator tier) | Free tier (3 works/mo, ≤10 scene, mock images) → Pro (unlimited/real images/priority/private asset lib) → Team (multi-seat + shared Chat Ops sessions) | **P0** (v4 natural shape) | ① frontend + ② Autopilot + ④ Chat Ops |
| **B · 素材市场** (marketplace 抽成) | Creators upload custom sprites/BG/BGM; 15-20% platform take. Buyers = other creators, direct-load to local library | **P1** (needs P0-2 library + P0-4 gate before payments) | ③ + P0-4 |
| **C · to-B 工具链授权** (whitelabel) | Sell the Multi-Agent + AgentOps stack (evaluation / observability / diversity metrics) to game studios for internal content production. Per-seat / per-call pricing | **P2** (needs P4 PlaytestAgent stable to be defensible) | v3 eval + P4 + Chat Ops |

**Not doing**: ad monetization (VN audience too small, CPM won't cover LLM cost); one-time perpetual license (LLM backend is continuous cost, one-time = margin bleed).

### 6.2 7-layer cost breakdown (variable per work)

| Layer | 6-scene demo | 50-scene target | Source |
|---|---|---|---|
| ① LLM API (Director + Writer + Reviewer) | ~$0.49 → $1.7* | ≤ $15 | v3 Phase 10 Sprint 6-fix + Sprint 8-4 caching; Sonnet + Haiku split; prompt cache 5-min TTL (cache hit ≥ 50% on scene 10+) |
| ② Image gen (Nano Banana / DALL-E 3) | included in ① (~$1.2 / demo) | ~$8-12 / 50 | Sprint 12-3b~c; **P0-2 library hit saves $0.02-0.05 by avoiding both prompt LLM + image API** |
| ③ Storage (S3-compatible / R2) | ~$0.001 | ~$0.008 | Each work ~40MB packed (image + BGM), CDN long-tail negligible |
| ④ Bandwidth | ~$0.001 | ~$0.01 | Web VN player (v4 ⑤) uses SSE + JIT scene delivery, much less than one-shot ZIP |
| ⑤ Human review (P0-4 gate backstop + NSFW) | ~$0 (M0 whitelist gate only) | $0.20-0.50 | Alpha creators self-review; Beta introduces Vision LLM pre-screen + human backstop (~5% needs human, $0.5/each × 5%) |
| ⑥ Web search (Serper fallback) | ~$0 (default off) | ~$0.02 | Serper free tier 2500/mo covers first 500 works; over-quota $0.30 / 1k queries |
| ⑦ Support/refund/exceptions | — | ~5% AOV | Beta empirical |

*$1.7 measured on v3 Phase 12-3 Showcase demo (real Sonnet + Nano Banana + Haiku + Character Bible).

### 6.3 Unit economics (Pro tier survival math)

| Scenario | Cost | Assumed price | Margin | Note |
|---|---|---|---|---|
| Free user (3 works/mo, mock images) | ~$0.05 | 0 | -$0.05 | Loss leader; subsidized by paid conversions |
| **Naive Pro (10 works/mo, real images 50-scene)** | ~$150/mo | **$29/mo** | **-$121/mo ❌** | Naive single-tier SaaS math **breaks** |
| Pro w/ 3 works/mo cap only | ~$45/mo | $29/mo | -$16/mo | Still negative; LLM cost dominates |
| **Pro w/ usage tiering** (3 × 10-scene real + 40 × mock) | ~$18/mo | $29/mo | **~$11/mo (38%) ✅** | Usage tiering makes math work |
| Team tier (Chat Ops + 5 seats) | ~$95/mo | $199/mo | ~$104/mo (52%) | Chat Ops delivers human-AI collab, willing to pay |
| Marketplace commission | ~$0 | 15% of $3 avg | ~$0.45/item | Volume-driven; needs 6mo for flywheel |
| To-B whitelabel | v3+v4 stack | $2k-10k/mo/client | > 80% | Single client covers platform opex |

### 6.4 The insight (interview anchor)

> **"LLM cost dominance → naive single-tier SaaS math breaks → usage-tiering is mandatory, not optional."**

Same shape as Cursor (subscription + backend API metered), Perplexity (free search + Pro on-demand), Poe (bundled credit). The differentiator VN-Agent has is that the **preset骨架 was already there in v3** — `config/presets/budget.yaml` (all-Haiku, $0.01-0.02/run) and `literary.yaml` (all-Sonnet + Nano Banana, $1.5/6-scene) already implement the usage-tiering primitive. So the commercialization path isn't a slide — it's a wiring change.

**Anticipated follow-up questions**:
- **"Is Pro at $29 pulled from a hat?"** → Anchors: Cursor Pro $20 / Perplexity Pro $20 / Poe $20 are the AI SaaS psychological ceiling. The usage caps are what make the math work, not the price point.
- **"Why subsidize free users?"** → LTV assumption: mock-image free users have 3-5% Pro conversion, Pro ARPU $116 (4 mo avg). CAC ≈ $0.05 × 30 / 4% ≈ $37.5, well below LTV $116.
- **"Marketplace copyright risk?"** → Triple defense: P0-4 license gate + upload-time TOS attestation + platform-is-not-a-relicensor (marketplace = matchmaking only). Alpha only supports CC0/CC-BY + user-verified-own-work.

---

## 7. Interview questions the user should expect

### 7.1 "个人项目还是团队项目?" (highest-frequency)
- **Answer**: **Personal project, AI-augmented development.** 166 commits, ~15.8K LoC source. Development toolchain = Claude Code (Anthropic's coding CLI) + Gemini CLI (via MCP for second-opinion review). The **AI product decisions** (方向优先级 scoring, alternatives-considered, cost model, license whitelist) were mine; the code was implemented with heavy AI assistance.
- **Reframe**: The interviewer is not testing whether you can hand-write 15K LoC — they're testing whether you can drive an AI product end-to-end. Being explicit about AI-augmented workflow is itself a signal — Claude Code / Cursor / Continue are how modern AI PMs will build. Hiding it looks worse than owning it.

### 7.2 "竞品差异化?"
- **Answer**: NovelAI / AI Dungeon / Charat are all "generate stories with an LLM" — none of them export Ren'Py projects, none of them run multi-Agent evaluation loops, none of them expose per-run cost/observability. VN-Agent's differentiation is **platform + evaluation**, not **generation quality** (Claude/GPT-4 will always out-generate what I can prompt-engineer). The moat is the AgentOps底座 + multi-source fusion + Chat Ops workflow — which are exactly the things that don't get commoditized when OpenAI ships the next model.

### 7.3 "能商业化吗?"
- **Answer**: See §6. Three paths (SaaS + marketplace + to-B whitelabel), not one. Single-tier SaaS math breaks under LLM cost dominance ($150 backend cost vs $29 psychological ceiling). Usage-tiering (per-work quota + mock/real image split) makes Pro tier ~38% margin; Team tier at $199 gets ~52% margin; to-B whitelabel gets 80%+ but needs P4 stable. **The v3 preset骨架 already implements usage-tiering primitives** so this isn't slideware.

### 7.4 "为什么不用 Cursor / OpenAI 直接生成完整 VN?"
- **Answer**: Try it — you'll hit two walls immediately. (1) **Prompt膨胀**: asking for scene + characters + branches + Ren'Py code in one shot triggers max_tokens truncation (v3 M0 real-run hit 89% truncation rate on Writer). (2) **一致性**: 20-scene VN needs cross-scene character voice consistency + symbolic world state (`manuscript_read=True` across chapters); a single-shot LLM has no explicit state anchor. Multi-Agent DAG + Character Bible + Symbolic World State + StructureReviewer are engineered responses to these walls, not architectural showing-off.

### 7.5 "怎么衡量 AI 产品成功?"
- **Answer**: North Star = **creator completion rate ≥ 40% (beta)** + **median session ≤ 45 min (10-scene)**. Not "generation quality" (unfalsifiable), not "tokens used" (vanity). Supporting metrics: **diversity index ≥ 30%** (non-LLM material share, the anti-homogeneity metric), **Chat Ops NPS ≥ 40** (does human-AI collaboration actually feel good), and technical底座 metrics (cache read ratio ≥ 50%, 50-scene end-to-end ≤ 30 min wall / ≤ $15).

### 7.6 Blind-spot follow-ups (rehearsed answers from plan §"面试可辩护性自审")

- **"P0 diversity index 怎么算才不作弊?"** → Non-LLM material has byte-level source tags. Diversity computed at export from source tags, not self-reported.
- **"P1 没有真实用户怎么飞轮?"** → M0 = alpha + author self-use; core signal is **闭环 exists**, not corpus size. Data sources are 3 natural streams (alpha + Autopilot players + Vision Judge implicit) not one.
- **"P1 L3 DPO 不做是不是缩水?"** → M0 explicit scope; L3 needs ≥1k records + training compute — neither exists at M0. **This is scope discipline, not缩水**.
- **"P3 Chat Ops vs Cursor 差异化?"** → Cursor / Continue / Cody are **generic chat ops on code**. VN-Agent is **vertical chat ops on VN pipeline** — each intent (edit dialogue / add character / adjust branch) dispatches to the specific Agent (Writer/Character/Director). Vertical depth ≠ replaceable by generic tools.
- **"P3 intent router LLM 塌房怎么办?"** → 4-level fallback: L1 preview card (M0 default) → L2 confidence threshold → L3 top-K options → L4 misclassification-corrections feed P1 flywheel. **L4 loops back to P1 — 这就是数据飞轮**.
- **"P4 M0 只报告不闭环有啥用?"** → Report itself is product value ("一键体检卡" pre-publish). M0.5 = feed Director prompt as soft constraint. M1 = 3rd Reviewer layer with revision loop (cost-gated). M1.5 = Vision Judge validated with Pearson r vs human (reuses v3 Sprint 8-1 cross-judge pattern).
- **"P5 Autopilot 最优参数从哪来?"** → M0 = human-curated preset. M0.5 = every run writes `data/autopilot_runs.jsonl`. M1 = P4 Vision score + completion rate sort. M2 = theme embedding → nearest-neighbor run preset (approach recommender-system shape).

### 7.7 P6 redesign follow-ups (from `FRONTEND_REDESIGN_v4.md` §9, extended with what shipping actually surfaced)

- **"改 UI 算产品工作吗?"** → 改的不是皮肤，是**信息架构**——把系统里已经存在但不可见的多 Agent 协作过程暴露给用户。"让 AI 的工作过程可解释"是 AI PM 的核心命题，这是它的一次具体落地。
- **"流水线可视化是不是花架子?"** → 它消费的是**真实的 LangGraph 节点事件**，不是假动画。证据：浏览器里观察到的事件序列包含 `structure_reviewer → director_step2_redo → structure_reviewer` 这段**真实的修订回环**——假动画编不出回环。而且顺带修掉了两个真实缺陷：10 个节点里 6 个的内部标识符会直接漏给用户（`Running cross_ref_sync`），以及进度条第 2 格永远走不到。
- **"为什么不直接用组件库?"** → 图标用 lucide，但拒绝整套预制组件——差异化在信息架构，不在按钮圆角；预制组件库正是"模板感"的来源。动效连图标库都没用，用 CSS：framer-motion 为两个效果收 44 kB gzipped，不值。
- **"怎么保证不把能跑的东西改坏?"** → 前端**没有测试框架**，这是事实，所以不能靠测试兜底：契约冻结（`api.ts` 与 store action 签名只加不改）+ 六层迁移 + 新旧外壳并存，`?shell=v1` 一个 URL 参数退回可用状态。
- **"那你怎么知道新界面真的能跑?"**（最该主动答的一问）→ 分开讲：语言切换、v1/v2 切换、完整 Autopilot 跑通、节点事件序列——**这四项在真实 mock 浏览器会话里验证过**；Task 10-13 之后的最终 v2 外壳走查**没做**，因为浏览器插件中途掉线，之后只有构建 + 类型检查 + 静态检查。所以默认外壳至今没翻到 v2——翻默认值这种改动，不能只靠类型检查交付。
- **"i18n 不就是查字典替换吗?"** → 难点不在字典，在**状态**：聊天记录如果只存渲染后的文本，切语言就只能翻译新消息，历史还是旧语言。所以消息存 key + vars、在渲染时解析，切换会重译整段历史。另外节点标签放在**前端**翻译而不是后端，因为 SSE 事件本来就带结构化 node id，后端保持稳定英文标识——这也回到同一个原则：结构化信号别降级成散文。
- **"209 个 key 怎么保证中英不漏?"** → 不靠人盯：`dict[lang][key]` 的类型定义让 `tsc` 在 en 缺 key 时直接构建失败。纪律做不到的事情，交给类型系统。

---

## 8. Resume bullet seeds (structured for LLM regeneration)

Format: **Claim** · **Quantification** · **Evidence path/commit**. Ordered strongest-first.

1. **Designed and shipped a 6-Agent LangGraph DAG for end-to-end VN generation** (Director / StructureReviewer / StateOrchestrator / Thinking / Writer / DialogueReviewer / Assets), with `can_writer_fix` typed routing to skip无效重写 saving ~$1.10 per 6-scene run — `src/vn_agent/agents/graph.py`, `src/vn_agent/agents/routing.py`, commit `8a2ac88`.

2. **Built cross-model evaluation harness** (Sonnet self-judge + GPT-4o independent judge) achieving **Pearson r = 0.643, ±1-pt agreement = 87%**, defusing the "same-model self-scoring" echo-chamber critique — Sprint 8-1, commit `4f1228f`, `docs/PRODUCT.md` §关键指标.

3. **Ran data-driven writer_mode 8-cell sweep**, flipping default from `action` (few-shot RAG) to `literary` (physics prompt) after finding **literary 4.17 > action 3.92 on both themes including the action-leaning dragon theme (4.5 vs 4.17)** — Sprint 8-5, `docs/v2/RESUME_v2.md` §评估实测数据.

4. **Shipped v4 P1 M0 data flywheel** (creator 👍/👎 → JSONL append-only store → BM25 injector `top_k=3, down-votes-only` → Haiku Reflection Agent producing `dynamic_guidelines.json`), closing "user feedback → system改进" loop that v3 was missing — commit `49baaf2`, `src/vn_agent/feedback/{store,injector,reflection}.py`.

5. **Shipped v4 P0 M0 multi-source material fusion** (text upload + Serper web-search agent + 11-asset CC0 seed library + cross-source pHash/embedding dedup + license whitelist gate CC0/CC-BY/CC-BY-SA/user_owned/derived) targeting **diversity index ≥ 30%** — commits `d1746d4`, `eed2c2d`, `1957158`, `src/vn_agent/assets/`.

6. **Pivoted RAG from dialogue few-shot (style contamination) to lore entity retrieval**, keeping the same FAISS + sentence-transformers infrastructure but changing the queried entity type — Sprint 10-2, `src/vn_agent/eval/lore.py`.

7. **Engineered 3-layer long-form memory**: Character Bible as `cache_control=ephemeral` prompt-cached suffix (first 1.25×, reuse 0.1×) + Haiku recursive scene summarization gated ≥15 scenes + sliding window `writer_context_window` — Sprint 11-1/11-2/11-3.

8. **Made cost/observability first-class**: per-request `TokenTracker` via ContextVar (multi-job safe) + `run_metrics.json` (wall / cost / cache_read_ratio / health_status / degradation_signals) + `rag_retrievals.jsonl` per-scene audit + `--abort-on-degradation` on stress runner — Sprint 6-5, Phase 13 M0-4.

9. **Diagnosed and fixed a 52-min silent Reviewer hang** by adding `pending-debug` flush (writes `debug/{name}.pending.txt` **before** LLM call, renames after) + hard `asyncio.wait_for` timeout + `salvage` utility recovering completed scenes from `vn_script.json` / `snapshots/*.json` for stuck runs — commits `d52261c`, `47d50fa`, `src/vn_agent/salvage.py`, `src/vn_agent/services/pending_debug.py`.

10. **Designed 4-blind-spot mesh** where each M0 gap (thin user data / LLM misclassification / no closed-loop / manual params) is the input to another blind-spot's follow-up — reframes the honest gap into "数据飞轮的产品设计思维" — `plans/cached-wibbling-karp.md` §"产品盲点后续跟进方案".

11. **Prioritized方案 Y (10-14 weeks)** among 3 alternative orderings using 3-axis scoring (resume-点 · demo-面 · product-落地); P0 multi-source shipped in ~2 weeks as predicted — plan file §"Context", scoring matrix.

12. **Built 3-path commercialization model** (SaaS + marketplace + to-B whitelabel) with 7-layer variable-cost breakdown and unit-economics sheet showing single-tier Pro at $29 loses $121/mo but usage-tiered Pro (3 real-image + 40 mock) yields ~$11/mo (38%) margin — `docs/v4/PRODUCT_v4.md` §9.

13. **Structured output via Anthropic Tool Use + 3-tier Writer recovery chain** (JSON array parse → per-object brace scan → continuation call), rescuing 100% scenes to ≥5 dialogue lines despite 89% max_tokens hit rate on M0 real run — `src/vn_agent/schema/script.py:418`, commits `05db6d8`, `441fbc6`.

14. **API resilience with Anthropic Key Pool + exponential backoff + Sonnet/Haiku split pools** + Health gate on stress runner (`retry > 5` / `key_rotation_density > 1.0` / `wall_minutes > 2× expected` → red → abort before burning 50-scene tier's $15) — commits `95b8b97`, `745e03d`.

15. **Cost engineering with model tiering** (Sonnet for creative Director/Writer, Haiku for translation-flavored Reviewer/summarizer/asset agents) + prompt caching = ~73% cost reduction on budget preset ($3/$15 vs $0.80/$4 per MTok) — Phase 6, Sprint 8-4.

16. **Made Chinese VN a first-class横切 constraint** (CJK detection + langchain-text-splitters chunk_size=300 for CJK + `character_id/scene_id` English but display-layer Chinese + P0 quality gate: Chinese 6-scene end-to-end Reviewer avg ≥ 3.5) — `docs/v4/PRODUCT_v4.md` §8.

17. **Shipped Chat Ops M0 with 4-level intent-router fallback plan, L1 built** (preview-before-execute confirm card default; L2 confidence threshold / L3 top-K / L4 feedback-into-flywheel are explicit roadmap, not built) — commit `47d59e4`, `src/vn_agent/chat_ops/`, plan file §"P3 intent router · LLM 塌房 4 级 fallback".

18. **166 commits (v3 baseline) · ~15.8K LoC src · ~12.4K LoC tests · 659 unit tests passing (v3) · 939 tests collected as of v4 P0-P5 (2026-07-29) · 3 verified real API smoke runs pre-v4 (~$3.74 total spend)** — solo project with Claude Code + Gemini AI-augmented development, campus-recruit honest framing.

19. **Shipped SSE just-in-time scene streaming** (`services/job_events.py` per-job pub/sub, ContextVar-scoped like `TokenTracker`) so the player shows scenes as the pipeline writes them instead of waiting for the full script — turns "submit and wait" into a visible generation process — commit `a309058`.

20. **Shipped PlaytestAgent + Vision LLM Judge M0**, including an honest scope-cut documented mid-flight: research found zero existing Ren'Py headless-execution infrastructure, so M0 pivoted from real engine screenshots to a Pillow frame compositor over the pipeline's own generated art, with real engine screenshots deferred to M1 — `services/llm.py` gained the repo's first vision-LLM call site — commit `c4793a5`.

21. **Found and fixed a real correctness bug while building Autopilot's success-rate KPI**: `POST /generate` was silently double-executing every real (non-mock) generation through two independently-racing code paths, one of which held a concurrency semaphore the other didn't — fixed with a request-scoped `interactive` flag before the KPI could ship on top of a race condition — commit `5e8d621`.

22. **Found, disclosed, and fixed a real cost-safety gap during a routine `--mock` CLI smoke test**: the flag silently let 2 of 8 agent modules bypass the mock patch and make 5 real Anthropic API calls (~$0.12) via an internal helper that re-imported the LLM client fresh. Stopped immediately, root-caused via safe (non-network) inspection, disclosed in full before any fix, then closed the gap for every call path (not just the ones caught) by setting the same `ContextVar` the LLM client checks internally, plus a permanent regression test — commit `5e8d621`, `tests/test_cli/test_mock_patch.py`.

23. **Designed a `ContextVar`-based per-job settings override** (`config.py::get_settings()`) so Autopilot could give each generation job its own tuned preset without touching the ~20 existing call sites across the agent graph — the same pattern already used by the codebase's mock-mode and token-tracker scoping, extended rather than reinvented — commit `5e8d621`.

24. **Completed the full 6-phase v4 roadmap (P0→P5) at M0 scope** — multi-source fusion, data flywheel, streaming UI, Chat Ops, PlaytestAgent, Autopilot — each phase shipped with tests, each phase's honest gaps (thin data / LLM misclassification risk / report-not-loop / manual params / undemoed UX) documented rather than hidden, three of six phases required an explicit, user-confirmed scope cut from the original plan (P3/P4/P5) — plan file `cached-wibbling-karp.md`.

25. **Fixed a structured-signal-downgrade defect end to end (v4 P6)**: the LangGraph pipeline emitted one event per node, but the web layer collapsed it into a progress *string* that the frontend then substring-matched back into a 5-step bar. Replaced with `publish_node` → SSE `node` event → store `pipelineNodes` → `PipelineGraph`, making the multi-Agent pipeline — the product's core differentiator — visible in the product for the first time. The same change fixed two latent defects: **6 of 10 graph nodes had no label** (users saw `Running cross_ref_sync`) and **display step 2 (Review) was unreachable** because the `'script'` substring test fired first — commits `fa68464`, `7c8a339`, `5fe971d`, `0315aad`, `782b5de`, `tests/test_web/test_pipeline_labels.py`.

26. **Rejected my own first design proposal and re-scoped it from palette to information architecture**: three "visual directions" were killed by one user sentence ("这三个的区别感觉只是颜色而已"), so I re-surveyed and named two structural defects — a constant 50/50 split that reads as a generic AI-SaaS template, and a multi-Agent pipeline invisible in the UI. Shipped `WorkbenchShell` with a form-follows-`AppStep` layout where the chat column width is a function of what the current stage is *about* (player 0, pipeline 20rem, others 24rem) — commit `4f26c00`, `docs/v4/FRONTEND_REDESIGN_v4.md` §1.2.

27. **Migrated a live UI in six independently-rollback-able layers with zero test framework to lean on**: contract freeze on `api.ts` and store action signatures (additive only), old and new shells coexisting behind a `?shell=v1` URL escape hatch that persists to localStorage, and the default deliberately left on the legacy shell until a browser walkthrough gates the cutover — commits `8113a7f`, `frontend/src/shell/useShellVariant.ts`.

28. **Shipped zh/en internationalisation over a UI that had been 100% hardcoded English, with parity enforced by the type system**: 209 keys per language, sets identical, `tsc` fails the build on a missing key; the chat log stores key + vars and resolves at paint time so switching language retranslates the **entire history**, not just new messages; node labels localise client-side because the SSE event already carries a structured node id — commits `bfdf963`, `b046835`, `da5659a`, `5b1ebeb`, `frontend/src/i18n/dict.ts`.

29. **Declared a bundle regression in the commit that caused it, then removed it**: L4 pulled framer-motion in for two animations (81 → 125 kB gzipped, stated openly in `4f26c00` against the plan's TTI ≤ 3s target), then replaced it with CSS `@keyframes` for 84 kB — ~3 kB net over the pre-redesign baseline, and strictly more accessible since a JS library animating inline styles bypasses `prefers-reduced-motion` while `@keyframes` honour it — commit `717c203`.

---

## 9. Cautionary notes for the LLM downstream

### 9.1 Strong claims (safe to inflate語調 but not数字)
- The eval infrastructure (cross-Judge Pearson r, 8-cell sweep, 5-dim rubric, deterministic structural checks) is real. Every number is repo-grounded.
- The v3 shipped features (multi-Agent DAG, RAG pivot, 3-layer memory, symbolic state, prompt caching) are code-verified.
- The v4 P0/P1 M0 features (multi-source fusion + data flywheel L1+L2) are just-landed commits with tests.
- The commercialization thinking (3-path, 7-layer, unit economics) has arithmetic backing.

### 9.2 Do NOT inflate these claims
- **User base**: this project has no real users beyond the author. Do NOT write "supported 100+ creators" — write "designed for creators, alpha planned 3-5 users".
- **Data flywheel scale**: L1 + L2 are running but the corpus is small. Do NOT write "trained on 10k+ feedback records". Write "closed-loop shipped, data collection ongoing".
- **All 6 phases (P0-P5) have shipped as M0 code + tests as of 2026-07-27** (see §2.4-2.7). This is a change from the 2026-07-19 draft of this file, which said P2-P5 had not shipped — that line is now stale, do not use it. But "shipped" here means **M0-level, unit/integration-tested, mock-verified** — it does NOT mean "measured on real production traffic". Keep these two claims separate:
  - ✅ Safe to claim present-tense: "Chat Ops M0 is implemented and tested" / "the streaming player, PlaytestAgent, and Autopilot are built and pass their test suites".
  - ❌ Not yet true, do not claim: **manual browser click-through verification** of any of P2-P5's UX has been done (explicitly deferred since 2026-07-21, still open 2026-07-29) — say "code-complete and test-covered, UI walkthrough pending" not "demoed live".
  - ❌ Not yet true: Autopilot's own KPIs (success rate ≥ 85%, ≤ 8 min wall clock) have **not been measured on a real run** — only mock-mode + unit tests. Say "instrumented to measure X, first real-run validation pending".
  - ❌ Not yet true: Chat Ops "≥ 8 ops/session" and Vision Judge "≤ $0.20/run" are still unmeasured targets (no real users, no real API run for Vision Judge yet) — same treatment as the pre-existing 50-scene/diversity-index targets below.
- **50-scene long-form**: infrastructure in place, but full 50-scene wall / cost claims are **projections from 6-scene baseline**, not measured. Say "on track for 50-scene under $15" not "achieved 50-scene at $15".
- **Diversity index ≥ 30%**: **target**, not measured. Say "target 30%+" not "achieved 30%+".
- **Vision Judge validity**: built (P4 M0), but only mock-verified (visual inspection of English + Chinese mock-generated screenshots). Do NOT claim Vision-Judge Pearson r or a real cost-per-run figure; only claim the cross-Sonnet-vs-GPT-4o r=0.643 which IS measured (that's a different, v3-era judge pair).
- **P6 frontend redesign (2026-08-10)**: same M0-vs-production discipline applies, with one extra axis — this work lives on an **unmerged branch** (`feat/frontend-redesign-v4`) and its **default is still the legacy shell**.
  - ✅ Safe to claim: the redesign is code-complete through L4, builds clean, and is reachable at `?shell=v2`; the backend `node` event path, the 10/10 node labels, the step-2 fix, and the 209-key zh/en dictionary are all in the tree with the type system enforcing key parity.
  - ✅ Safe to claim, and worth claiming precisely: **four things were verified in a real mock-mode browser session** — live language toggle, `?shell=v1`/`v2` switching with localStorage stickiness both directions, a full Autopilot run inside the v2 shell reaching a compiled project, and the live node-event sequence including a genuine `structure_reviewer → director_step2_redo → structure_reviewer` revision loop-back.
  - ✅ Safe to claim: the **final** v2 shell (Tasks 10-13 — storyboard, card detail, form-driven layout) passed a **10/10 browser walkthrough** on 2026-08-11, and the walkthrough itself caught two defects the type checker could not (English activity line, chat-button wrapping), both fixed. Say "walked through end to end in mock mode, 10/10".
  - ✅ Safe to claim: the redesign **is the default** (`DEFAULT_VARIANT = 'v2'`, `3730936`), flipped only after the walkthrough. ❌ Not true: that it is merged — the branch `feat/frontend-redesign-v4` is still unmerged, and Task 15 (deleting the legacy shell) is deliberately deferred. Say "default shell, escape hatch retained, branch pending merge".
  - ❌ Do **not** claim a TTI number. TTI ≤ 3s is still a target; bundle size is measured (84 kB gzipped after `717c203`), TTI is not.
- **The mock-safety incident (P5, 2026-07-27) is safe to tell in full** — it is a genuine positive signal for an AI PM interview (found via own dogfooding, disclosed before fixing, root-caused precisely, fixed with a permanent regression test), not something to downplay. Do not inflate the dollar figure (it was $0.12 / 5 calls) and do not imply it happened in a production/user-facing context — it was the candidate's own CLI smoke test.

### 9.3 AI-augmented dev framing (say this way, not that way)
- ✅ "Built with Claude Code + Gemini as pair-programmers; the PM decisions (方向优先级, cost model, license gate whitelist) were mine, code was implemented AI-augmented."
- ❌ "Wrote 15K lines of production Python solo in 8 months" (dishonest, and interviewer will not believe it anyway)
- ✅ "Solo owner of the product; 166 commits reflect end-to-end ownership from spec to shipping."
- ❌ "Team of one" — doesn't communicate anything.

### 9.4 Chinese phrases worth preserving verbatim in Chinese resumes
- "简历爆点" — untranslatable idiom for "resume standout"
- "AI PM 高频题" — evaluation vocab
- "数据飞轮" (data flywheel) — has slightly different connotation than English DIY translation
- "面试可辩护性自审" — this whole phrase carries an ownership signal
- "闭环已跑通" — critical framing for M0-scale shipping
- "北极星指标" (North Star metric) — standard PM term but reads authentic in Chinese

### 9.5 Regeneration priority hints for downstream LLM
If forced to compress to 3-5 bullets: seeds 1 + 2 + 3 + 4 + 12. If compressing to a single line: seed 4 + 5 (v4 P0/P1 just shipped + AgentOps evaluation底座) because those are the freshest evidence AND the highest AI PM interview-question coverage.

If JD emphasizes **evaluation / AgentOps**: lead with 2 + 8 + 9 + 3.
If JD emphasizes **product / user**: lead with 4 + 5 + 10 + 11 + 12.
If JD emphasizes **AI-native infrastructure**: lead with 1 + 6 + 7 + 13 + 14.
If JD emphasizes **human-AI interaction / explainability / frontend-adjacent PM**: lead with 25 + 26 + 28 + 17 — seed 25 is the strongest single "I made the AI's process legible" story in the whole project because it is a *defect narrative* (structured signal → prose → guessed back) rather than a feature list.
If JD emphasizes **shipping discipline / quality under constraint**: lead with 27 + 29 + 22 + 9.

---

_End of brief. Downstream LLM should treat this as authoritative source; anything not in this file should be verified against the repo before including in resume bullets._
