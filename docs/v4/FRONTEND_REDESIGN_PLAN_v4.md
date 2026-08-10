# VN-Agent Studio 前端改版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把工作台从"通用 AI SaaS 模板"改造成形态随阶段切换的创作工作台——生成中是可见的多 Agent 流水线剧场，生成后是分支可见的故事板——同时补齐完全缺失的中文界面支持，且迁移全程可一键回退。

**Architecture:** 后端只做两处加法（新增 `node` SSE 事件类型 + 补全节点标签映射）。前端冻结 `api.ts` 与 store action 签名，改动限于表现层，分六层推进；L3 引入新外壳时旧外壳完整保留，通过 `?shell=v1/v2` 切换，任何时候都能退回已知可用状态。

**Tech Stack:** React 19 · Zustand 5 · Tailwind v4 · Vite 8 · TypeScript 5.9 · lucide-react（图标）· framer-motion（动效）· FastAPI + SSE（后端）

**设计依据：** `docs/v4/FRONTEND_REDESIGN_v4.md`（commit `a25e1e2`）

---

## Global Constraints

每个任务的要求都隐含包含本节。

- **契约冻结**：`frontend/src/api.ts` 的方法签名与返回类型、以及 store 的 **action 签名**不得修改，只允许加法（新增可选参数 / 新增 state 字段 / 新增 action）。
- **前端无测试框架**（`package.json` 无 vitest/jest）：`cd frontend && npm run build`（含 `tsc -b`）是唯一的自动化门禁，**每个前端任务必须通过**。
- **零 API 花费**：所有端到端验证一律 `VN_AGENT_MOCK=1` 强制 mock 模式。触发真实 API 需用户明确授权（`feedback_api_approval` 硬约束，不可绕过）。
- **每层独立可回滚**，L3 之后任何时候 `?shell=v1` 都能退回旧界面。
- **不引入整套预制组件库**（shadcn/ui 等），只允许 `lucide-react` 与 `framer-motion` 两个原子库。
- **不做客户端路由**——形态切换由 `AppStep` 驱动。
- **默认语言中文**（`lang: 'zh'`），可切英文。
- 所有动效必须尊重 `prefers-reduced-motion`。
- **不碰这两个已知 bug**：`/compile` 轮询竞态、种子图 CJK 乱码。它们的修复已在工作区但未提交，属独立议题。

### 开工前置检查

工作区里有两个**与本计划无关的未提交改动**（上一轮工作的产物）：

- `frontend/src/store.ts` — `pollInFlight` 互斥修复
- `scripts/seed_opensource_library.py` + `data/assets/opensource/*.png` — CJK 字体修复及重新生成的图

**Task 1 开始前**先与用户确认这两项是单独提交还是保留在工作区。若保留，后续所有 `git add` **必须逐文件指定路径**，禁止 `git add -A` / `git add .`，避免把它们卷进改版提交。

> **2026-08-09 更新**：这两个修复已分别提交为 `645c175`（`store.ts` 轮询互斥）与 `8573753`（种子图 CJK 字体）。工作区剩余的未提交改动仍与本计划无关，逐文件 `git add` 的纪律继续适用。

### `docs/CHANGELOG.md` 会出现在每个代码提交里（预期行为，非违规）

仓库配置了 `core.hooksPath=.githooks`，`.githooks/pre-commit` 会在任何**非文档**文件进入暂存区时运行 `scripts/update_docs.py`，后者自行 `git add docs/CHANGELOG.md`。因此**每个代码提交都会额外包含 `docs/CHANGELOG.md`**，这不是实施者越权。

绕过它需要 `--no-verify`，而跳过钩子是被禁止的。所以：

- 各任务「只允许改动 X、Y 两个文件」一类的约束，**隐含允许 `docs/CHANGELOG.md`**。
- 实施者在报告里应把钩子新增的文件**显式列为一条偏差**，而不是写「无偏差」再在别处补一句。
- 审查者不应把 `docs/CHANGELOG.md` 出现在 diff 里判为违规。

---

## File Structure

**后端（改动 2 个文件）**

| 文件 | 职责 |
|---|---|
| `src/vn_agent/services/job_events.py` | 新增 `publish_node()`——与 `publish_scene_ready()` 同构 |
| `src/vn_agent/web/app.py` | 补全 `_STEP_LABELS`（4→10 节点）；在 `_run_script_generation` 的 astream 循环里调用 `publish_node` |
| `tests/test_services/test_job_events.py` | **新建**——该模块目前零测试覆盖 |

**前端新增**

| 文件 | 职责 |
|---|---|
| `src/design/tokens.css` | 设计 token（CSS 自定义属性），唯一的颜色/字体真值来源 |
| `src/i18n/dict.ts` | 中英文案字典 |
| `src/i18n/useT.ts` | `t(key)` hook，从 store 读 `lang` |
| `src/shell/WorkbenchShell.tsx` | 新外壳：按形态决定渲染哪个主区 |
| `src/shell/useShellVariant.ts` | `?shell=v1/v2` + localStorage 的外壳选择逻辑 |
| `src/components/PipelineGraph.tsx` | 流水线节点脊柱（纯 CSS/flex，非 SVG——见 Task 9 说明） |
| `src/components/PipelineStage.tsx` | 流水线剧场：节点图 + 场景胶片条 + 成本计量 |
| `src/components/SceneCard.tsx` | 单张场景卡 |
| `src/components/StoryboardBoard.tsx` | 场景卡网格 + 分支指示 |

**前端修改**：`index.css`（引入 tokens）、`store.ts`（加 state，纯加法）、`api.ts`（`streamScenes` 加可选 `onNode`）、`App.tsx`（外壳分流）、以及各组件接入 i18n。

**前端删除（仅 L5）**：`PreviewPanel.tsx`、`ProgressBar.tsx`。

---

# L0 · 后端节点事件

### Task 1: `publish_node()` 与 job_events 首批测试

**Files:**
- Modify: `src/vn_agent/services/job_events.py`
- Test: `tests/test_services/test_job_events.py`（新建）

**Interfaces:**
- Consumes: 无（本计划第一个任务）
- Produces: `job_events.publish_node(node: str, label: str) -> None`——向当前 async 上下文的 job 发布 `{"event": "node", "node": <str>, "label": <str>}`；`current_job_id` 未设置时静默 no-op。Task 2 消费。

> **背景**：`services/job_events.py` 目前**零测试覆盖**（`grep -r job_events tests/` 无结果）。本任务顺带补上该模块的第一批测试。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_services/test_job_events.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_services/test_job_events.py -v
```

预期：`test_publish_node_*` 两条 FAIL，报 `AttributeError: module 'vn_agent.services.job_events' has no attribute 'publish_node'`；第三条 `test_scene_ready_and_node_events_share_one_stream` 也 FAIL（同样原因）。

- [ ] **Step 3: 实现**

在 `src/vn_agent/services/job_events.py` 的 `publish_scene_ready` 之后加入：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_services/test_job_events.py -v
```

预期：3 passed。

- [ ] **Step 5: 提交**

```bash
git add src/vn_agent/services/job_events.py tests/test_services/test_job_events.py
git commit -m "feat(events): add publish_node for structured pipeline progress

job_events had no test coverage; adds the module's first tests alongside."
```

---

### Task 2: 补全节点标签并接线到 astream 循环

**Files:**
- Modify: `src/vn_agent/web/app.py:1335-1340`（`_STEP_LABELS`）、`src/vn_agent/web/app.py:1155-1158`（astream 循环）
- Test: `tests/test_web/test_pipeline_labels.py`（新建）

**Interfaces:**
- Consumes: `job_events.publish_node(node, label)`（Task 1）
- Produces: SSE 流中出现 `{"event": "node", "node": <graph 节点名>, "label": <人类可读标签>}`。前端 Task 8 消费。节点名取值范围固定为：`director` / `structure_reviewer` / `director_step2_redo` / `director_full_redo` / `state_orchestrator` / `thinking_fanout` / `cross_ref_sync` / `writer` / `reviewer` / `asset_generation`。

> **只接线一处**：`current_job_id` 仅在 `_run_script_generation` 里设置（`app.py:1124` set / `:1221` reset）。`_run_job`（无头路径，`:1343`）从不设置它、也没有 SSE 订阅者，在那里调用 `publish_node` 是死代码——**不要动 `:1396` 那处**。`_STEP_LABELS` 的补全则对两条路径的 `progress` 字符串都生效。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_web/test_pipeline_labels.py`：

```python
"""Every graph node must have a user-facing label.

Regression guard: _STEP_LABELS used to cover only 4 of the graph's 10
nodes, so the fallback f"Running {node_name}" leaked internal identifiers
straight into the UI — users saw "Running cross_ref_sync".
"""
from __future__ import annotations

from vn_agent.agents.graph import build_graph
from vn_agent.web.app import _STEP_LABELS

_SENTINELS = {"__start__", "__end__"}


def test_every_graph_node_has_a_step_label():
    graph = build_graph()
    node_names = {n for n in graph.get_graph().nodes if n not in _SENTINELS}
    missing = node_names - set(_STEP_LABELS)
    assert not missing, f"graph nodes without a user-facing label: {sorted(missing)}"


def test_no_label_leaks_an_internal_identifier():
    """A label must read as prose, not as a node id."""
    for node, label in _STEP_LABELS.items():
        assert "_" not in label, f"{node!r} label looks like an identifier: {label!r}"
        assert label[:1].isupper(), f"{node!r} label should start capitalised: {label!r}"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web/test_pipeline_labels.py -v
```

预期：`test_every_graph_node_has_a_step_label` FAIL，列出 6 个缺失节点——`director_full_redo`、`director_step2_redo`、`cross_ref_sync`、`state_orchestrator`、`structure_reviewer`、`thinking_fanout`。

- [ ] **Step 3: 补全 `_STEP_LABELS`**

把 `src/vn_agent/web/app.py:1335-1340` 整块替换为：

```python
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
```

- [ ] **Step 4: 接线 `publish_node`**

把 `src/vn_agent/web/app.py:1155-1158` 的循环体：

```python
            for node_name, chunk in update.items():
                if node_name != "__end__":
                    label = _STEP_LABELS.get(node_name, f"Running {node_name}")
                    store.update_status(job_id, "running", progress=label)
```

改为：

```python
            for node_name, chunk in update.items():
                if node_name != "__end__":
                    label = _STEP_LABELS.get(node_name, f"Running {node_name}")
                    store.update_status(job_id, "running", progress=label)
                    # v4 P6: publish the node identity structurally so the
                    # frontend can drive the pipeline view off real events
                    # instead of substring-matching the progress string.
                    job_events.publish_node(node_name, label)
```

（`job_events` 已在同函数 `app.py:1101` 局部导入，无需新增 import。）

- [ ] **Step 5: 运行测试确认通过**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web/test_pipeline_labels.py tests/test_services/test_job_events.py -v
```

预期：5 passed。

- [ ] **Step 6: 跑受影响范围的回归**

```bash
.venv/Scripts/python.exe -m pytest tests/test_web/ tests/test_services/ -q
```

预期：全部通过，无新增失败。

- [ ] **Step 7: 提交**

```bash
git add src/vn_agent/web/app.py tests/test_web/test_pipeline_labels.py
git commit -m "fix(web): label all 10 pipeline nodes; publish node events over SSE

_STEP_LABELS covered 4 of 10 graph nodes, so users saw raw identifiers like
'Running cross_ref_sync'. Adds the missing labels, a test that keeps the map
exhaustive against the compiled graph, and publishes each node transition as
a structured SSE event."
```

---

# L1 · 设计基座

### Task 3: 设计 token 与图标/动效依赖

**Files:**
- Create: `frontend/src/design/tokens.css`
- Modify: `frontend/src/index.css`、`frontend/package.json`

**Interfaces:**
- Consumes: 无
- Produces: 全局可用的 CSS 自定义属性——`--ground` `--surface` `--surface-raised` `--rule` `--ink` `--ink-soft` `--ink-faint` `--instrument` `--instrument-wash` `--ok` `--warn` `--crit` `--font-instrument` `--font-narrative`。Task 9-12 消费。同时 `lucide-react` 与 `framer-motion` 可 import。

> 本任务**只定义不消费**——现有组件的 Tailwind 类一律不动，所以界面外观零变化。这是刻意的：让 token 的引入本身不产生任何回归风险。

- [ ] **Step 1: 安装依赖**

```bash
cd frontend && npm install lucide-react framer-motion
```

- [ ] **Step 2: 创建 tokens.css**

创建 `frontend/src/design/tokens.css`：

```css
/* VN-Agent Studio design tokens — single source of truth for colour and
   type. See docs/v4/FRONTEND_REDESIGN_v4.md §3.

   Dark ground is functional, not stylistic: this is an authoring tool for a
   visual medium, and generated art can only be judged against a neutral dark
   surround (same reason Figma / Premiere / Lightroom are dark).

   Saturated colour is reserved for the player — that is the generated work's
   own colour. The workbench stays neutral plus a single brass accent. */

:root {
  /* Ground → raised, cool-shifted neutrals (not pure grey) */
  --ground: #0e1012;
  --surface: #16191c;
  --surface-raised: #1d2125;
  --rule: #282d32;

  /* Text, three levels */
  --ink: #e6e9ec;
  --ink-soft: #9aa3ab;
  --ink-faint: #69727a;

  /* Accent: brass/amber — instrument-panel association. Deliberately not
     the indigo the old shell used, and not "AI purple". */
  --instrument: #c8944a;
  --instrument-wash: #2a2116;

  /* Semantic — independent of the accent, never used for branding */
  --ok: #4a9d6e;
  --warn: #c9873f;
  --crit: #c15550;

  /* Type: the instrument/narrative split is what carries the
     workbench-vs-artifact contrast. Colour alone would not. */
  --font-instrument: ui-sans-serif, -apple-system, "Segoe UI",
    "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-narrative: Georgia, "Songti SC", "Source Han Serif SC",
    "Noto Serif CJK SC", serif;
  --font-numeric: ui-monospace, "SF Mono", Consolas, monospace;
}

/* Instrument surfaces: dense, tabular digits, slightly open tracking. */
.face-instrument {
  font-family: var(--font-instrument);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.01em;
}

/* Narrative surfaces: scene titles, character names, dialogue.
   CJK needs a looser leading and must NOT get letter-spacing. */
.face-narrative {
  font-family: var(--font-narrative);
  line-height: 1.75;
  letter-spacing: normal;
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 3: 引入 tokens**

把 `frontend/src/index.css` 改为：

```css
@import "tailwindcss";
@import "./design/tokens.css";
```

- [ ] **Step 4: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

预期：构建成功，无 TS 错误。

- [ ] **Step 5: 目视确认零变化**

启动 dev server，确认界面与改动前**完全一致**（token 已定义但尚无消费者）。

```bash
cd frontend && npm run dev
```

- [ ] **Step 6: 提交**

```bash
git add frontend/src/design/tokens.css frontend/src/index.css frontend/package.json frontend/package-lock.json
git commit -m "feat(design): add design tokens and icon/motion deps

Tokens are defined but not yet consumed — no visual change by design, so the
introduction itself carries no regression risk."
```

---

# L2 · 中文一等公民

### Task 4: i18n 基础设施与语言开关

**Files:**
- Create: `frontend/src/i18n/dict.ts`、`frontend/src/i18n/useT.ts`
- Modify: `frontend/src/store.ts`、`frontend/src/components/JobHistory.tsx`

**Interfaces:**
- Consumes: 无
- Produces:
  - `useT(): (key: TKey) => string` — 从 store 读 `lang` 的翻译 hook
  - store 新增 state `lang: 'zh' | 'en'`（默认 `'zh'`）与 action `setLang(lang: 'zh' | 'en'): void`
  - `TKey` 类型 = `keyof typeof dict.zh`
  - Task 5、6 消费

> **勘查结论**：界面文案目前 **100% 硬编码英文**，10 个组件无一例外。生成内容（对白、场景标题）走 LLM，中文本身没问题——缺的只是外壳。

- [ ] **Step 1: 创建字典**

创建 `frontend/src/i18n/dict.ts`。本任务先放入 Task 5 两个组件所需的全部 key（其余 key 在 Task 6 补入）：

```ts
// UI chrome copy only. Generated content (dialogue, scene titles) comes from
// the LLM and is never routed through here.
//
// Chinese is the default: the primary demo audience is Chinese-speaking, and
// the CJK-first constraint in docs/v4/PRODUCT_v4.md applies to the shell too.
export const dict = {
  zh: {
    // ── ChatPanel ──
    'chat.settings': '生成设置',
    'chat.scenes': '场景数',
    'chat.characters': '角色数',
    'chat.textOnly': '仅文本',
    'chat.fastMode': '快速模式',
    'chat.mock': 'Mock（零 API 花费）',
    'chat.mockNotice': 'Mock 模式已开启——本次生成使用预置样例数据，不会产生任何真实 API 调用或花费。',
    'chat.feedback': '反馈',
    'chat.placeholderTheme': '输入你的故事主题…',
    'chat.placeholderChatOps': '提问，或要求改写某一场…',
    'chat.send': '发送',
    'chat.sending': '处理中…',
    'chat.autopilot': '一键生成',
    'chat.autopilotHint': '跳过所有确认步骤，直接进入播放器',
    'chat.retry': '重新生成',
    'chat.confirm': '确认执行',
    'chat.cancel': '取消',
    'chat.running': '执行中…',
    'chat.confidence': '置信度',
    'intent.local_regen': '改写场景',
    'intent.add_character': '新增角色',
    'intent.edit_asset': '修改素材',
    'intent.unknown': '未识别意图',
    // ── VNPreview ──
    'vn.backToEditor': '返回工作台',
    'vn.clickToStart': '点击开始',
    'vn.clickToContinue': '点击继续',
    'vn.fin': '完',
    'vn.scene': '场景',
    'vn.line': '对白',
    // ── 语言开关 ──
    'lang.toggle': 'EN',
    'lang.toggleHint': 'Switch to English',
  },
  en: {
    // ── ChatPanel ──
    'chat.settings': 'Settings',
    'chat.scenes': 'Scenes',
    'chat.characters': 'Characters',
    'chat.textOnly': 'Text Only',
    'chat.fastMode': 'Fast Mode',
    'chat.mock': 'Mock (Zero API $)',
    'chat.mockNotice': 'Mock mode is on — this generation uses canned fixture responses; no real API calls, no token spend.',
    'chat.feedback': 'Feedback',
    'chat.placeholderTheme': 'Enter your story theme…',
    'chat.placeholderChatOps': 'Ask a question, or ask to rewrite a scene…',
    'chat.send': 'Send',
    'chat.sending': 'Working…',
    'chat.autopilot': 'Autopilot',
    'chat.autopilotHint': 'Skip review steps and jump straight into the player',
    'chat.retry': 'Retry generation',
    'chat.confirm': 'Confirm',
    'chat.cancel': 'Cancel',
    'chat.running': 'Running…',
    'chat.confidence': 'confidence',
    'intent.local_regen': 'Rewrite scene',
    'intent.add_character': 'Add character',
    'intent.edit_asset': 'Edit asset',
    'intent.unknown': 'Unrecognised intent',
    // ── VNPreview ──
    'vn.backToEditor': 'Back to Editor',
    'vn.clickToStart': 'Click to start',
    'vn.clickToContinue': 'Click to continue',
    'vn.fin': 'Fin',
    'vn.scene': 'Scene',
    'vn.line': 'Line',
    // ── language switch ──
    'lang.toggle': '中',
    'lang.toggleHint': '切换到中文',
  },
} as const

export type Lang = keyof typeof dict
export type TKey = keyof (typeof dict)['zh']
```

- [ ] **Step 2: 创建 useT hook**

创建 `frontend/src/i18n/useT.ts`：

```ts
import useStore from '../store'
import { dict, type TKey } from './dict'

/** Translate a UI-chrome key using the language currently in the store.
 *  Falls back to the Chinese string if a key is somehow missing from the
 *  active language, so a gap shows up as the wrong language rather than as
 *  a blank button. */
export function useT(): (key: TKey) => string {
  const lang = useStore(s => s.lang)
  return (key: TKey) => dict[lang][key] ?? dict.zh[key]
}
```

- [ ] **Step 3: 在 store 里加 lang（纯加法）**

在 `frontend/src/store.ts` 中：

1. 顶部加 import：

```ts
import type { Lang } from './i18n/dict'
```

2. `interface AppState` 里，`chatBusy: boolean` 之后加：

```ts
  // v4 P6: UI-chrome language. Chinese is the default (primary demo
  // audience); generated content language is driven by the theme, not this.
  lang: Lang
```

3. 同 interface 的 action 区，`cancelChatTurn: () => void` 之后加：

```ts
  setLang: (lang: Lang) => void
```

4. 初始 state 里 `chatBusy: false,` 之后加：

```ts
  lang: 'zh',
```

5. 实现区 `cancelChatTurn` 之后加：

```ts
  setLang: (lang) => set({ lang }),
```

- [ ] **Step 4: 在侧栏加语言开关**

修改 `frontend/src/components/JobHistory.tsx`。顶部加 import：

```ts
import { useT } from '../i18n/useT'
```

组件内取值（在现有 `const { jobs, ... } = useStore()` 之后）：

```ts
  const t = useT()
  const lang = useStore(s => s.lang)
  const setLang = useStore(s => s.setLang)
```

把标题区块替换为：

```tsx
      <div className="p-4 border-b border-gray-800 flex items-start justify-between gap-2">
        <div>
          <h1 className="text-lg font-bold text-indigo-400">VN-Agent Studio</h1>
          <p className="text-[10px] text-gray-500 mt-0.5">AI Visual Novel Generator</p>
        </div>
        <button
          onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
          title={t('lang.toggleHint')}
          className="text-[10px] px-2 py-1 rounded border border-gray-700 text-gray-400
            hover:text-gray-200 hover:border-gray-500 transition-colors shrink-0
            focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
        >
          {t('lang.toggle')}
        </button>
      </div>
```

- [ ] **Step 5: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

预期：构建成功。

- [ ] **Step 6: 手工验证开关**

启动 dev server，点击侧栏右上角的语言按钮，确认按钮文字在「EN」与「中」之间切换、无报错。（此时其余文案仍是硬编码英文，属预期——Task 5/6 才接入。）

- [ ] **Step 7: 提交**

```bash
git add frontend/src/i18n/ frontend/src/store.ts frontend/src/components/JobHistory.tsx
git commit -m "feat(i18n): add zh/en dictionary, useT hook and language toggle

UI chrome was 100% hardcoded English across all 10 components; this adds the
infrastructure and the switch. Components are converted in the next tasks."
```

---

### Task 5: 演示关键界面接入 i18n（ChatPanel + VNPreview）

**Files:**
- Modify: `frontend/src/components/ChatPanel.tsx`、`frontend/src/components/VNPreview.tsx`

**Interfaces:**
- Consumes: `useT()`（Task 4）、Task 4 字典里的 `chat.*` / `vn.*` / `intent.*` key
- Produces: 无新接口

- [ ] **Step 1: ChatPanel 接入**

在 `frontend/src/components/ChatPanel.tsx`：

1. 加 import：`import { useT } from '../i18n/useT'`
2. 组件内加：`const t = useT()`
3. 把 `INTENT_META` 常量替换为——图标留在模块级，标签改走字典：

```tsx
// v4 P3: icon per dispatchable intent. Labels come from i18n (see
// dict.ts `intent.*`) so the confirm card reads in the creator's language.
const INTENT_ICON: Record<string, string> = {
  local_regen: '✏️',
  add_character: '👤',
  edit_asset: '🖼️',
}
```

4. 意图确认卡里的标签行改为：

```tsx
            <span className="font-medium text-indigo-300">
              {t(`intent.${pendingChatTurn.intent}` as TKey)}
            </span>
            <span className="text-gray-500 ml-auto">
              {Math.round(pendingChatTurn.confidence * 100)}% {t('chat.confidence')}
            </span>
```

图标行改为 `{INTENT_ICON[pendingChatTurn.intent] ?? '❓'}`。顶部 import 补 `import type { TKey } from '../i18n/dict'`。

5. 逐处替换字面量：`Settings`→`{t('chat.settings')}`、`Scenes:`→`{t('chat.scenes')}:`、`Characters:`→`{t('chat.characters')}:`、`Text Only`→`{t('chat.textOnly')}`、`Fast Mode`→`{t('chat.fastMode')}`、`Mock (Zero API $)`→`{t('chat.mock')}`、mock 提示段→`{t('chat.mockNotice')}`、`Feedback`→`{t('chat.feedback')}`、`Retry generation`→`{t('chat.retry')}`、`Confirm`→`{t('chat.confirm')}`、`Cancel`→`{t('chat.cancel')}`、`Running...`→`{t('chat.running')}`、`Send`→`{t('chat.send')}`、`...`（busy 态）→`{t('chat.sending')}`、`⚡ Autopilot`→`⚡ {t('chat.autopilot')}`、`title=`→`title={t('chat.autopilotHint')}`。

6. placeholder 改为：

```tsx
            placeholder={chatOps ? t('chat.placeholderChatOps') : t('chat.placeholderTheme')}
```

- [ ] **Step 2: VNPreview 接入**

在 `frontend/src/components/VNPreview.tsx`：

1. 加 import：`import { useT } from '../i18n/useT'`，组件内 `const t = useT()`
2. 替换：两处 `Back to Editor`→`{t('vn.backToEditor')}`、`Click to start`→`{t('vn.clickToStart')}`、`Click to continue`→`{t('vn.clickToContinue')}`、`Fin`→`{t('vn.fin')}`
3. 底部状态条改为：

```tsx
        <span>{t('vn.scene')} {sceneIdx + 1}/{scenes.length}: {scene.title}</span>
        <span>{t('vn.line')} {Math.max(lineIdx + 1, 0)}/{scene.dialogue.length}</span>
```

4. 场景标题与对白挂上叙事排版类（Task 3 的 `.face-narrative`）：

```tsx
              <h2 className="face-narrative text-2xl font-bold text-white mb-2">{scene.title}</h2>
```

```tsx
            <p className="face-narrative text-base text-white">{line.text}</p>
```

- [ ] **Step 3: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

预期：构建成功。若 `t(\`intent.${...}\` as TKey)` 报类型错，确认 `TKey` 已 import。

- [ ] **Step 4: mock 端到端验证**

后端（仓库根目录）：

```bash
VN_AGENT_MOCK=1 .venv/Scripts/python.exe -m uvicorn vn_agent.web.app:app --port 8000
```

前端：

```bash
cd frontend && npm run dev
```

浏览器打开 `http://localhost:5173`，主题输入「校园恋爱」，验证：

1. 默认中文——输入框 placeholder 是「输入你的故事主题…」，按钮是「发送」「⚡ 一键生成」
2. 点语言开关切到 EN，同样位置变回英文，**无需刷新**
3. 走一遍生成，进播放器，确认「点击继续」「完」「场景 1/6」为中文且渲染正常（无方框）
4. 中文对白使用衬线排版且不掉字

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/ChatPanel.tsx frontend/src/components/VNPreview.tsx
git commit -m "feat(i18n): localise ChatPanel and VNPreview

Also applies the narrative type face to scene titles and dialogue."
```

---

### Task 6: 其余组件接入 i18n

**Files:**
- Modify: `frontend/src/i18n/dict.ts`（补 key）、`frontend/src/components/StatusBar.tsx`、`PreviewPanel.tsx`、`JobHistory.tsx`、`AssetPanel.tsx`、`PlaytestPane.tsx`、`SettingPanel.tsx`、`ScriptPanel.tsx`、`FeedbackWidget.tsx`

**Interfaces:**
- Consumes: `useT()`（Task 4）
- Produces: 字典新增 `status.*` / `steps.*` / `preview.*` / `history.*` 组 key，Task 10-13 复用

- [ ] **Step 1: 补充字典 key**

在 `frontend/src/i18n/dict.ts` 的 `zh` 块尾部追加：

```ts
    // ── StatusBar ──
    'status.idle': '就绪',
    'status.generating_setting': '构思中…',
    'status.setting_review': '待确认设定',
    'status.generating_script': '写作中…',
    'status.script_review': '待确认剧本',
    'status.compiling': '编译中…',
    'status.asset_management': '素材管理',
    'status.completed': '已完成',
    'status.failed': '失败',
    'status.fast': '快速',
    // ── 进度阶段 ──
    'steps.setting': '设定',
    'steps.script': '剧本',
    'steps.review': '审校',
    'steps.assets': '素材',
    'steps.done': '完成',
    // ── PreviewPanel ──
    'preview.empty': '输入一个主题开始生成',
    'preview.working': '处理中…',
    'preview.elapsed': '已用时',
    'preview.live': '直播',
    'preview.watchLive': '边生成边看',
    'preview.scenesReady': '个场景就绪',
    'preview.failed': '生成失败',
    'preview.unknownError': '未知错误',
    // ── JobHistory ──
    'history.title': '历史记录',
    'history.empty': '暂无记录',
    'history.salvage': '抢救',
    'history.salvaging': '抢救中…',
    'history.delete': '删除',
    'history.salvageFailed': '抢救失败：',
```

在 `en` 块尾部追加对应项：

```ts
    // ── StatusBar ──
    'status.idle': 'Ready',
    'status.generating_setting': 'Planning…',
    'status.setting_review': 'Review setting',
    'status.generating_script': 'Writing…',
    'status.script_review': 'Review script',
    'status.compiling': 'Compiling…',
    'status.asset_management': 'Manage assets',
    'status.completed': 'Done',
    'status.failed': 'Failed',
    'status.fast': 'Fast',
    // ── progress steps ──
    'steps.setting': 'Setting',
    'steps.script': 'Script',
    'steps.review': 'Review',
    'steps.assets': 'Assets',
    'steps.done': 'Done',
    // ── PreviewPanel ──
    'preview.empty': 'Enter a theme to start generating',
    'preview.working': 'Working…',
    'preview.elapsed': 'Elapsed',
    'preview.live': 'Live',
    'preview.watchLive': 'Watch Live',
    'preview.scenesReady': 'scenes ready',
    'preview.failed': 'Generation failed',
    'preview.unknownError': 'Unknown error',
    // ── JobHistory ──
    'history.title': 'History',
    'history.empty': 'No jobs yet',
    'history.salvage': 'salvage',
    'history.salvaging': 'salvaging…',
    'history.delete': 'delete',
    'history.salvageFailed': 'Salvage failed: ',
```

- [ ] **Step 2: StatusBar 接入**

在 `frontend/src/components/StatusBar.tsx`：删除模块级 `STEP_LABELS` 常量，加 `import { useT } from '../i18n/useT'` 与 `import type { TKey } from '../i18n/dict'`，组件内 `const t = useT()`，状态文字改为：

```tsx
        {busy ? '⏳' : step === 'completed' ? '✅' : step === 'failed' ? '❌' : '○'}{' '}
        {t(`status.${step}` as TKey)}
```

`Fast` 改为 `{t('status.fast')}`。

- [ ] **Step 3: PreviewPanel 接入**

在 `frontend/src/components/PreviewPanel.tsx`：模块级 `STEPS` 常量改为 key 数组，组件内翻译：

```tsx
const STEP_KEYS = ['steps.setting', 'steps.script', 'steps.review', 'steps.assets', 'steps.done'] as const
```

组件内：

```tsx
  const t = useT()
  const STEPS = STEP_KEYS.map(k => t(k))
```

替换：`Enter a theme to start generating`→`{t('preview.empty')}`、`Working...`→`{t('preview.working')}`、`Elapsed: {elapsed}s`→`{t('preview.elapsed')}: {elapsed}s`、`Live`→`{t('preview.live')}`、`Generation failed`→`{t('preview.failed')}`、`Unknown error`→`{t('preview.unknownError')}`。Watch Live 按钮改为：

```tsx
                  ▶ {t('preview.watchLive')}（{(blackboard.scene_scripts as unknown[]).length} {t('preview.scenesReady')}）
```

- [ ] **Step 4: JobHistory 接入**

在 `frontend/src/components/JobHistory.tsx`（Task 4 已引入 `t`）：`History`→`{t('history.title')}`、`No jobs yet`→`{t('history.empty')}`、`delete`→`{t('history.delete')}`、salvage 按钮的 `salvaging…`/`salvage`→`{salvaging[j.job_id] ? t('history.salvaging') : t('history.salvage')}`、`alert('Salvage failed: ' + String(err))`→`alert(t('history.salvageFailed') + String(err))`。

- [ ] **Step 5: SettingPanel 与 ScriptPanel**

先补字典。`zh` 块追加：

```ts
    // ── SettingPanel ──
    'setting.world': '世界观设定',
    'setting.edit': '编辑',
    'setting.save': '保存',
    'setting.cancel': '取消',
    'setting.title': '标题',
    'setting.description': '简介',
    'setting.characters': '角色',
    'setting.name': '姓名',
    'setting.role': '定位',
    'setting.personality': '性格',
    'setting.outline': '剧情大纲',
    'setting.scenesUnit': '场',
    'setting.confirm': '确认并生成剧本',
    'setting.regenerate': '重新生成设定',
    'setting.saveFailed': '保存失败：',
    // ── ScriptPanel ──
    'script.reviewPass': '✅ 审校通过',
    'script.reviewRevisions': '⚠️ 审校修订',
    'script.revisionsUnit': '轮',
    'script.linesUnit': '句对白',
    'script.narrator': '旁白',
    'script.choices': '玩家选项：',
    'script.confirm': '确认并继续',
    'script.regenerate': '重新生成剧本',
    'script.preview': '预览播放',
    'script.export': '导出 JSON',
    'script.backToSetting': '返回设定',
    'script.exportFailed': '导出失败：',
```

`en` 块追加：

```ts
    // ── SettingPanel ──
    'setting.world': 'World Setting',
    'setting.edit': 'Edit',
    'setting.save': 'Save',
    'setting.cancel': 'Cancel',
    'setting.title': 'Title',
    'setting.description': 'Description',
    'setting.characters': 'Characters',
    'setting.name': 'Name',
    'setting.role': 'Role',
    'setting.personality': 'Personality',
    'setting.outline': 'Plot Outline',
    'setting.scenesUnit': 'scenes',
    'setting.confirm': 'Confirm & Generate Script',
    'setting.regenerate': 'Regenerate',
    'setting.saveFailed': 'Save failed: ',
    // ── ScriptPanel ──
    'script.reviewPass': '✅ Reviewer: PASS',
    'script.reviewRevisions': '⚠️ Reviewer:',
    'script.revisionsUnit': 'revision(s)',
    'script.linesUnit': 'lines',
    'script.narrator': 'Narrator',
    'script.choices': 'Player Choices:',
    'script.confirm': 'Confirm & Continue',
    'script.regenerate': 'Regenerate Script',
    'script.preview': 'Preview VN',
    'script.export': 'Export JSON',
    'script.backToSetting': 'Back to Setting',
    'script.exportFailed': 'Export failed: ',
```

然后逐处替换：

- `SettingPanel.tsx` — `World Setting`、三处 `Edit`/`Save`/`Cancel`、placeholder `Title`/`Description`、`Title: `/`Description: `、`Characters ({n})`→`{t('setting.characters')}（{n}）`、placeholder `Name`/`Role`/`Personality`、`Plot Outline ({n} scenes)`→`{t('setting.outline')}（{n} {t('setting.scenesUnit')}）`、`Confirm & Generate Script`、`Regenerate`、`alert(\`Save failed: ${e}\`)`→`alert(t('setting.saveFailed') + e)`
- `ScriptPanel.tsx` — reviewer 横幅两个分支、`Edit`/`Save`/`Cancel`、`{n} lines`、placeholder `narrator`、`Narrator`、`Player Choices:`、底部五个按钮、两处 `alert(...)`

- [ ] **Step 6: AssetPanel、PlaytestPane、FeedbackWidget**

这三个文件本计划未逐行列出，实施时**先完整读一遍再动手**：把每一处面向用户的英文字面量（JSX 文本节点、`placeholder=`、`title=`、`alert()` 参数、按钮文案、表头）提成 key，前缀分别用 `asset.` / `playtest.` / `feedback.`，中英两份同步补进 `dict.ts`。

**完成判据**（对全部组件生效，必须输出为空）：

```bash
cd frontend && grep -rnE '>[A-Z][a-z]+ [a-z]+|placeholder="[A-Z]|title="[A-Z]|alert\(.[A-Z]' src/components/ src/shell/
```

命中项逐个转换后重跑，直到无输出。

- [ ] **Step 7: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

- [ ] **Step 8: mock 端到端验证**

按 Task 5 Step 4 的方式起服务，中文模式下走完 P2→P5 四条链路（生成 → Watch Live → Chat Ops 改写 → Playtest → Autopilot），确认**没有任何英文残留**、无方框、无 JS 报错。切到 EN 再走一遍关键界面。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/i18n/dict.ts frontend/src/components/
git commit -m "feat(i18n): localise remaining components

Completes the shell's zh/en coverage; Chinese is now a first-class UI
language rather than only a generated-content language."
```

---

# L3 · 新外壳（旧壳并存）

### Task 7: 外壳选择机制与 WorkbenchShell 骨架

**Files:**
- Create: `frontend/src/shell/useShellVariant.ts`、`frontend/src/shell/WorkbenchShell.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: 无
- Produces:
  - `useShellVariant(): 'v1' | 'v2'` — 读 `?shell=` 参数（读到即写入 localStorage 持久化），否则读 localStorage，否则返回默认值
  - `WorkbenchShell` 组件——Task 13 在此接入新主区
  - Task 13、14 消费

> **这是整个迁移的安全阀。** 本任务结束时 `v2` 渲染的内容与 `v1` **完全相同**，纯粹把切换机制立起来。默认值在 L5 之前保持 `'v1'`。

- [ ] **Step 1: 创建外壳选择器**

创建 `frontend/src/shell/useShellVariant.ts`：

```ts
import { useState } from 'react'

export type ShellVariant = 'v1' | 'v2'

const STORAGE_KEY = 'vn-agent.shell'

// Stays 'v1' until the L5 cutover task flips it. Keeping the old shell as
// the default through L3/L4 means an in-progress redesign can never break
// the working UI — including during a live demo.
const DEFAULT_VARIANT: ShellVariant = 'v1'

function isVariant(value: string | null): value is ShellVariant {
  return value === 'v1' || value === 'v2'
}

function resolve(): ShellVariant {
  // URL wins and is sticky: ?shell=v1 is the one-parameter escape hatch, and
  // persisting it means the user does not have to re-append it on reload.
  const fromUrl = new URLSearchParams(window.location.search).get('shell')
  if (isVariant(fromUrl)) {
    try {
      window.localStorage.setItem(STORAGE_KEY, fromUrl)
    } catch {
      /* private mode / storage disabled — URL still applies for this load */
    }
    return fromUrl
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (isVariant(stored)) return stored
  } catch {
    /* ignore */
  }

  return DEFAULT_VARIANT
}

/** Which shell to render. Resolved once per mount — switching variants is a
 *  reload, which is what we want: the two shells do not share layout state. */
export function useShellVariant(): ShellVariant {
  const [variant] = useState<ShellVariant>(resolve)
  return variant
}
```

- [ ] **Step 2: 抽出旧外壳**

创建 `frontend/src/shell/LegacyShell.tsx`，内容为现有 `App.tsx` 的逐字搬迁（仅改组件名与 import 路径）：

```tsx
import { useState } from 'react'
import ChatPanel from '../components/ChatPanel'
import PreviewPanel from '../components/PreviewPanel'
import JobHistory from '../components/JobHistory'
import StatusBar from '../components/StatusBar'

/** The shell as it shipped through v4 P5. Kept intact and reachable via
 *  ?shell=v1 for the whole redesign, and deleted only after the v2 default
 *  has soaked (see FRONTEND_REDESIGN_v4.md §6.2 L5). Do not refactor — its
 *  entire value is being a known-good fallback. */
export default function LegacyShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100 overflow-hidden">
      {/* Mobile sidebar toggle */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="md:hidden fixed top-3 left-3 z-50 p-2 bg-gray-800 rounded-lg text-gray-400"
      >
        {sidebarOpen ? '✕' : '☰'}
      </button>

      {/* Sidebar */}
      <aside className={`
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        md:translate-x-0 fixed md:static z-40
        w-64 bg-gray-900 border-r border-gray-800 shrink-0 flex flex-col h-full
        transition-transform duration-200
      `}>
        <JobHistory />
      </aside>

      {/* Overlay for mobile sidebar */}
      {sidebarOpen && (
        <div className="md:hidden fixed inset-0 z-30 bg-black/50" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Main area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Left: Chat */}
          <div className="h-1/2 md:h-auto md:w-1/2 border-b md:border-b-0 md:border-r border-gray-800 flex flex-col">
            <ChatPanel />
          </div>
          {/* Right: Preview */}
          <div className="h-1/2 md:h-auto md:w-1/2 overflow-y-auto custom-scrollbar">
            <PreviewPanel />
          </div>
        </div>
        <StatusBar />
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 创建 WorkbenchShell 骨架**

创建 `frontend/src/shell/WorkbenchShell.tsx`。**本步先原样复用旧布局**，Task 13 才替换主区：

```tsx
import { useState } from 'react'
import ChatPanel from '../components/ChatPanel'
import PreviewPanel from '../components/PreviewPanel'
import JobHistory from '../components/JobHistory'
import StatusBar from '../components/StatusBar'

/** v4 P6 workbench. Task 7 stands the shell up rendering exactly what
 *  LegacyShell renders, so the variant switch itself is provably a no-op;
 *  Task 13 swaps the main region for the form-driven panes. */
export default function WorkbenchShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--ground)', color: 'var(--ink)' }}>
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="md:hidden fixed top-3 left-3 z-50 p-2 rounded-lg
          focus-visible:outline focus-visible:outline-2"
        style={{ background: 'var(--surface-raised)', color: 'var(--ink-soft)' }}
      >
        {sidebarOpen ? '✕' : '☰'}
      </button>

      <aside
        className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0 fixed md:static z-40 w-64 shrink-0 flex flex-col h-full
          border-r transition-transform duration-200`}
        style={{ background: 'var(--surface)', borderColor: 'var(--rule)' }}
      >
        <JobHistory />
      </aside>

      {sidebarOpen && (
        <div className="md:hidden fixed inset-0 z-30 bg-black/50" onClick={() => setSidebarOpen(false)} />
      )}

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          <div
            className="h-1/2 md:h-auto md:w-1/2 border-b md:border-b-0 md:border-r flex flex-col"
            style={{ borderColor: 'var(--rule)' }}
          >
            <ChatPanel />
          </div>
          <div className="h-1/2 md:h-auto md:w-1/2 overflow-y-auto custom-scrollbar">
            <PreviewPanel />
          </div>
        </div>
        <StatusBar />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: App.tsx 改为分流**

把 `frontend/src/App.tsx` 整个替换为：

```tsx
import LegacyShell from './shell/LegacyShell'
import WorkbenchShell from './shell/WorkbenchShell'
import { useShellVariant } from './shell/useShellVariant'

export default function App() {
  const variant = useShellVariant()
  return variant === 'v2' ? <WorkbenchShell /> : <LegacyShell />
}
```

- [ ] **Step 5: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

- [ ] **Step 6: 并排验证两套外壳**

起 mock 后端 + dev server，开两个标签页：

- `http://localhost:5173/?shell=v1` — 必须与改动前**完全一致**
- `http://localhost:5173/?shell=v2` — 布局相同，底色改用 token（近黑）

分别在两边完成一次 mock 生成，确认行为一致、无 JS 报错。再验证：`?shell=v2` 访问后直接访问 `http://localhost:5173/`（不带参数）仍停在 v2（localStorage 生效），随后 `?shell=v1` 能切回。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/App.tsx frontend/src/shell/
git commit -m "feat(shell): add v1/v2 shell switch with legacy shell preserved

v2 currently renders the same layout as v1, so the switch is provably a
no-op. ?shell=v1 remains a one-parameter path back to the known-good UI for
the rest of the redesign."
```

---

# L4 · 流水线剧场与故事板

### Task 8: 流水线状态接入 store

**Files:**
- Modify: `frontend/src/api.ts`、`frontend/src/store.ts`

**Interfaces:**
- Consumes: Task 2 的 SSE `node` 事件
- Produces:
  - `api.streamScenes(jobId, handlers)` 的 `handlers` 新增**可选** `onNode?: (node: string, label: string) => void`（签名加法，现有调用点零改动）
  - store 新增 state：`pipelineNodes: Record<string, PipelineNodeState>`、`pipelineActive: string | null`、`pipelineLabel: string`
  - 导出类型 `PipelineNodeState = 'pending' | 'active' | 'done'`
  - Task 9、10 消费

- [ ] **Step 1: api.ts 加可选 handler**

在 `frontend/src/api.ts` 的 `streamScenes` 中，把 handlers 类型改为：

```ts
  streamScenes(jobId: string, handlers: {
    onScene: (scene: Record<string, unknown>) => void
    // v4 P6: graph-node transitions, published alongside scene_ready on the
    // same stream. Optional so existing callers are unaffected.
    onNode?: (node: string, label: string) => void
    onDone?: () => void
    onError?: (error?: string) => void
  }): EventSource {
```

并在事件分发链里，`scene_ready` 分支之后加一支：

```ts
        if (data.event === 'scene_ready') {
          handlers.onScene(data.scene)
        } else if (data.event === 'node') {
          handlers.onNode?.(data.node, data.label)
        } else if (data.event === 'done') {
```

- [ ] **Step 2: store 加流水线 state（纯加法）**

在 `frontend/src/store.ts`：

1. 文件顶部（`interface AppState` 之前）加类型导出：

```ts
// v4 P6: per-node state for the pipeline view. 'active' is the node the
// graph is currently executing; loop-backs (the director redo nodes) can
// re-activate a node already marked 'done', which is the correct display
// for a revision round.
export type PipelineNodeState = 'pending' | 'active' | 'done'
```

2. `interface AppState` 里 `lang: Lang` 之后加：

```ts
  pipelineNodes: Record<string, PipelineNodeState>
  pipelineActive: string | null
  pipelineLabel: string
```

3. 初始 state 里 `lang: 'zh',` 之后加：

```ts
  pipelineNodes: {},
  pipelineActive: null,
  pipelineLabel: '',
```

4. `generate()` 里现有的重置 `set({ step: 'generating_setting', ... })` 调用中，追加三个字段以免上一次运行的状态残留：

```ts
    set({
      step: 'generating_setting', progress: 'Creating project...', errors: [], blackboard: {},
      assets: null, vnPreview: false, streamActive: false,
      pipelineNodes: {}, pipelineActive: null, pipelineLabel: '',
    })
```

5. `confirmSetting()` 里 `api.streamScenes(currentJobId, { ... })` 的 handlers 对象中，`onScene` 之后加：

```ts
      onNode: (node, label) => {
        const next: Record<string, PipelineNodeState> = { ...get().pipelineNodes }
        // The graph only ever runs one node at a time, so whatever was
        // active has finished by the time the next node reports in.
        for (const key of Object.keys(next)) {
          if (next[key] === 'active') next[key] = 'done'
        }
        next[node] = 'active'
        set({ pipelineNodes: next, pipelineActive: node, pipelineLabel: label })
      },
```

6. `onDone` 改为在收尾时把最后一个 active 收成 done：

```ts
      onDone: () => {
        const next: Record<string, PipelineNodeState> = { ...get().pipelineNodes }
        for (const key of Object.keys(next)) {
          if (next[key] === 'active') next[key] = 'done'
        }
        set({ streamActive: false, pipelineNodes: next, pipelineActive: null })
      },
```

- [ ] **Step 3: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: 验证事件真的到了前端**

在 `onNode` 里临时加 `console.log('[node]', node, label)`，起 mock 后端 + dev server 跑一次生成，浏览器 console 应按序打印 director → structure_reviewer → state_orchestrator → thinking_fanout → cross_ref_sync → writer → reviewer（`text_only` 勾选时无 asset_generation）。确认后删除该 `console.log`。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api.ts frontend/src/store.ts
git commit -m "feat(pipeline): track graph-node transitions in the store

Additive only: streamScenes gains an optional onNode handler and the store
gains three new fields; no existing signature changes."
```

---

### Task 9: PipelineGraph 组件

**Files:**
- Create: `frontend/src/components/PipelineGraph.tsx`
- Modify: `frontend/src/i18n/dict.ts`（补节点名 key）

**Interfaces:**
- Consumes: store 的 `pipelineNodes` / `pipelineActive`（Task 8）、`useT()`（Task 4）
- Produces: 默认导出组件 `PipelineGraph`（无 props，纯 store 消费者）。Task 10 消费。

> **偏离 spec 的说明**：spec §4.2 写的是「手写 SVG 节点图」。实测用 flex + CSS 连接线更简单、天然响应式、且不需要坐标计算，因此改用 CSS 实现。这是实现手段的简化，不改变设计意图。

- [ ] **Step 1: 补节点名字典**

在 `frontend/src/i18n/dict.ts` 的 `zh` 块追加：

```ts
    // ── 流水线节点（对应 agents/graph.py 的节点名）──
    'node.director': '导演',
    'node.structure_reviewer': '结构审校',
    'node.state_orchestrator': '状态编排',
    'node.thinking_fanout': '分场推理',
    'node.cross_ref_sync': '交叉引用',
    'node.writer': '编剧',
    'node.reviewer': '质量审校',
    'node.asset_generation': '素材生成',
    'pipeline.revising': '修订中',
    'pipeline.scenes': '场景',
    'pipeline.cost': '花费',
```

`en` 块追加：

```ts
    // ── pipeline nodes (mirrors agents/graph.py node names) ──
    'node.director': 'Director',
    'node.structure_reviewer': 'Structure',
    'node.state_orchestrator': 'State',
    'node.thinking_fanout': 'Reasoning',
    'node.cross_ref_sync': 'Cross-ref',
    'node.writer': 'Writer',
    'node.reviewer': 'Review',
    'node.asset_generation': 'Assets',
    'pipeline.revising': 'revising',
    'pipeline.scenes': 'Scenes',
    'pipeline.cost': 'Cost',
```

- [ ] **Step 2: 创建组件**

创建 `frontend/src/components/PipelineGraph.tsx`：

```tsx
import { motion } from 'framer-motion'
import useStore from '../store'
import { useT } from '../i18n/useT'
import type { TKey } from '../i18n/dict'

// Display spine, mirroring the linear path in src/vn_agent/agents/graph.py
// (set_entry_point("director") … add_edge("asset_generation", END)).
//
// director_step2_redo / director_full_redo are deliberately NOT columns:
// they are loop-backs from structure_reviewer, so they surface as a
// "revising" badge on that node instead of as extra steps that would make
// the pipeline look longer than it is.
const SPINE = [
  'director',
  'structure_reviewer',
  'state_orchestrator',
  'thinking_fanout',
  'cross_ref_sync',
  'writer',
  'reviewer',
  'asset_generation',
] as const

const REDO_NODES = ['director_step2_redo', 'director_full_redo'] as const

export default function PipelineGraph() {
  const t = useT()
  const pipelineNodes = useStore(s => s.pipelineNodes)
  const revising = REDO_NODES.some(n => pipelineNodes[n] === 'active')

  return (
    <ol className="face-instrument flex flex-wrap items-center gap-y-3" aria-label="pipeline">
      {SPINE.map((node, i) => {
        const state = pipelineNodes[node] ?? 'pending'
        const isActive = state === 'active'
        const isDone = state === 'done'
        const color = isActive || isDone ? 'var(--instrument)' : 'var(--ink-faint)'

        return (
          <li key={node} className="flex items-center">
            {i > 0 && (
              <span
                aria-hidden="true"
                className="w-5 h-px mx-1.5 shrink-0"
                style={{ background: isDone || isActive ? 'var(--instrument)' : 'var(--rule)' }}
              />
            )}
            <motion.span
              className="relative px-2.5 py-1 rounded text-[11px] border whitespace-nowrap"
              style={{
                color,
                borderColor: isActive ? 'var(--instrument)' : 'var(--rule)',
                background: isActive ? 'var(--instrument-wash)' : 'transparent',
                fontWeight: isActive ? 600 : 400,
              }}
              animate={isActive ? { opacity: [1, 0.55, 1] } : { opacity: 1 }}
              transition={isActive ? { duration: 1.6, repeat: Infinity, ease: 'easeInOut' } : { duration: 0.2 }}
            >
              {t(`node.${node}` as TKey)}
              {node === 'structure_reviewer' && revising && (
                <span className="ml-1.5 text-[9px]" style={{ color: 'var(--warn)' }}>
                  ↻ {t('pipeline.revising')}
                </span>
              )}
            </motion.span>
          </li>
        )
      })}
    </ol>
  )
}
```

- [ ] **Step 3: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

预期：构建成功（组件此时尚无挂载点，仅验证可编译）。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/PipelineGraph.tsx frontend/src/i18n/dict.ts
git commit -m "feat(pipeline): add PipelineGraph node spine

CSS/flex rather than hand-authored SVG — responsive for free and no
coordinate math; same design intent as the spec's SVG sketch."
```

---

### Task 10: PipelineStage（流水线剧场主区）

**Files:**
- Create: `frontend/src/components/PipelineStage.tsx`
- Modify: `frontend/src/store.ts`（token 用量上收到 store）、`frontend/src/components/StatusBar.tsx`

**Interfaces:**
- Consumes: `PipelineGraph`（Task 9）、store 的 `pipelineLabel` / `blackboard.scene_scripts` / `elapsed`（Task 8 及既有）
- Produces:
  - store 新增 state `tokenUsage: { tokens: number; cost: number } | null` 与 action `refreshTokenUsage(): Promise<void>`
  - 默认导出组件 `PipelineStage`。Task 13 消费。

> `StatusBar` 目前自己 `fetch` token 用量并每 5 秒轮询。本任务把它上收到 store，让 StatusBar 与 PipelineStage 共用**一个**轮询源，而不是各开一个 interval。

- [ ] **Step 1: token 用量上收到 store**

在 `frontend/src/store.ts`：

1. `interface AppState` 的 state 区加：

```ts
  tokenUsage: { tokens: number; cost: number } | null
```

2. action 区加：

```ts
  refreshTokenUsage: () => Promise<void>
```

3. 初始 state 加 `tokenUsage: null,`
4. 实现区加：

```ts
  refreshTokenUsage: async () => {
    const { currentJobId } = get()
    if (!currentJobId) { set({ tokenUsage: null }); return }
    try {
      const resp = await fetch(`/api/projects/${currentJobId}/token-usage`)
      if (!resp.ok) return
      const data = await resp.json()
      if (data.calls > 0) {
        set({ tokenUsage: { tokens: data.total_input + data.total_output, cost: data.estimated_cost_usd } })
      }
    } catch { /* transient — keep the last known value */ }
  },
```

5. `generate()` 的重置 `set({...})` 中追加 `tokenUsage: null,`

- [ ] **Step 2: StatusBar 改为消费 store**

在 `frontend/src/components/StatusBar.tsx`，把本地 `tokenInfo` state 与其 `useEffect` 整块替换为：

```tsx
  const tokenInfo = useStore(s => s.tokenUsage)
  const refreshTokenUsage = useStore(s => s.refreshTokenUsage)

  useEffect(() => {
    if (!currentJobId || step === 'idle') return
    refreshTokenUsage()
    const timer = setInterval(refreshTokenUsage, 5000)
    return () => clearInterval(timer)
  }, [currentJobId, step, refreshTokenUsage])
```

（`useState` 若因此不再被使用，从 import 中移除以免 tsc 报未使用变量。）

- [ ] **Step 3: 创建 PipelineStage**

创建 `frontend/src/components/PipelineStage.tsx`：

```tsx
import useStore from '../store'
import PipelineGraph from './PipelineGraph'
import { useT } from '../i18n/useT'
import { dict, type TKey } from '../i18n/dict'

interface SceneLike { id: string; title?: string }

/** v4 P6 pipeline theatre: what the workbench shows while the graph runs.
 *  Replaces the old spinner-plus-one-string placeholder — the multi-agent
 *  pipeline is the product's differentiator and was previously invisible. */
export default function PipelineStage() {
  const t = useT()
  const { pipelineActive, pipelineLabel, progress, elapsed, blackboard, tokenUsage, streamActive, toggleVNPreview } = useStore()
  const scenes = (blackboard.scene_scripts as SceneLike[] | undefined) ?? []
  const maxScenes = useStore(s => s.config.max_scenes)
  const slots = Math.max(maxScenes, scenes.length)

  // Prefer the locally translated node name over the backend's label: the
  // backend emits English prose (it also feeds `progress`, which non-UI
  // consumers read), but the shell defaults to Chinese. Falls back to the
  // raw label for nodes with no dictionary entry (the director redo nodes).
  const headline =
    (pipelineActive && dict.zh[`node.${pipelineActive}` as TKey] !== undefined
      ? t(`node.${pipelineActive}` as TKey)
      : '') || pipelineLabel || progress || t('preview.working')

  return (
    <div className="flex flex-col h-full p-6 gap-6">
      {/* Live pipeline */}
      <div
        className="rounded-lg border p-5"
        style={{ background: 'var(--surface)', borderColor: 'var(--rule)' }}
      >
        <div className="flex items-center gap-2 mb-4">
          {streamActive && (
            <span
              className="w-1.5 h-1.5 rounded-full animate-pulse"
              style={{ background: 'var(--crit)' }}
              aria-hidden="true"
            />
          )}
          <span className="face-instrument text-[11px] uppercase tracking-wider" style={{ color: 'var(--ink-faint)' }}>
            {headline}
          </span>
          <span className="face-instrument text-[11px] ml-auto" style={{ color: 'var(--ink-faint)' }}>
            {elapsed}s
          </span>
        </div>
        <PipelineGraph />
      </div>

      {/* Scene filmstrip */}
      <div className="flex flex-col gap-2">
        <span className="face-instrument text-[10px] uppercase tracking-wider" style={{ color: 'var(--ink-faint)' }}>
          {t('pipeline.scenes')} {scenes.length}/{slots}
        </span>
        <div className="flex flex-wrap gap-1.5">
          {Array.from({ length: slots }).map((_, i) => (
            <div
              key={i}
              className="h-1.5 w-10 rounded-full transition-colors duration-300"
              style={{ background: i < scenes.length ? 'var(--instrument)' : 'var(--rule)' }}
            />
          ))}
        </div>
      </div>

      {/* Cost meter */}
      {tokenUsage && (
        <div className="face-instrument flex items-baseline gap-4 text-[12px]" style={{ color: 'var(--ink-soft)' }}>
          <span>{tokenUsage.tokens.toLocaleString()} tok</span>
          <span style={{ color: 'var(--instrument)' }}>
            {t('pipeline.cost')} ${tokenUsage.cost.toFixed(4)}
          </span>
        </div>
      )}

      {/* Watch live — unchanged behaviour, restyled */}
      {scenes.length > 0 && (
        <button
          onClick={toggleVNPreview}
          className="self-start px-4 py-2 rounded-lg text-sm font-medium transition-opacity hover:opacity-90
            focus-visible:outline focus-visible:outline-2"
          style={{ background: 'var(--instrument)', color: 'var(--ground)' }}
        >
          ▶ {t('preview.watchLive')}（{scenes.length} {t('preview.scenesReady')}）
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 4: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: 验证 StatusBar 未回归**

起 mock 后端 + dev server，`?shell=v1` 跑一次生成，确认底部状态条的 token 数与花费仍正常显示、正常刷新（本步只改了数据来源，显示应无变化）。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/PipelineStage.tsx frontend/src/components/StatusBar.tsx frontend/src/store.ts
git commit -m "feat(pipeline): add PipelineStage; lift token polling into the store

StatusBar and PipelineStage now share one 5s poll instead of each owning an
interval."
```

---

### Task 11: SceneCard 组件

**Files:**
- Create: `frontend/src/components/SceneCard.tsx`
- Modify: `frontend/src/i18n/dict.ts`

**Interfaces:**
- Consumes: `useT()`（Task 4）
- Produces: 默认导出组件 `SceneCard`，props：

```ts
interface SceneCardProps {
  scene: { id: string; title: string; background_id: string; dialogue: unknown[]; branches: { text: string; next_scene_id: string }[] }
  index: number
  jobId: string | null
  onPlay: (index: number) => void
  onRewrite: (sceneId: string) => void
}
```

Task 12 消费。

- [ ] **Step 1: 补字典**

`zh` 块追加：

```ts
    'card.lines': '句对白',
    'card.branches': '个分支',
    'card.play': '从这里播放',
    'card.rewrite': '改写这一场',
```

`en` 块追加：

```ts
    'card.lines': 'lines',
    'card.branches': 'branches',
    'card.play': 'Play from here',
    'card.rewrite': 'Rewrite this scene',
```

- [ ] **Step 2: 创建组件**

创建 `frontend/src/components/SceneCard.tsx`：

```tsx
import { Play, Pencil } from 'lucide-react'
import { useT } from '../i18n/useT'

export interface SceneCardScene {
  id: string
  title: string
  background_id: string
  dialogue: unknown[]
  branches: { text: string; next_scene_id: string }[]
}

interface SceneCardProps {
  scene: SceneCardScene
  index: number
  jobId: string | null
  onPlay: (index: number) => void
  onRewrite: (sceneId: string) => void
}

export default function SceneCard({ scene, index, jobId, onPlay, onRewrite }: SceneCardProps) {
  const t = useT()
  const bgUrl = jobId
    ? `/api/projects/${jobId}/assets/file/game/images/backgrounds/${scene.background_id}.png`
    : ''

  return (
    <div
      className="group relative flex flex-col rounded-lg border overflow-hidden transition-colors"
      style={{ background: 'var(--surface)', borderColor: 'var(--rule)' }}
    >
      <div className="relative h-20 overflow-hidden" style={{ background: 'var(--surface-raised)' }}>
        {bgUrl && (
          <img
            src={bgUrl}
            alt=""
            className="w-full h-full object-cover opacity-60"
            onError={e => (e.currentTarget.style.display = 'none')}
          />
        )}
        <span
          className="face-instrument absolute top-1.5 left-2 text-[10px] px-1.5 py-0.5 rounded"
          style={{ background: 'var(--ground)', color: 'var(--ink-faint)' }}
        >
          {index + 1}
        </span>
      </div>

      <div className="flex flex-col gap-1 p-3 flex-1">
        <h3 className="face-narrative text-sm" style={{ color: 'var(--ink)', lineHeight: 1.4 }}>
          {scene.title || scene.id}
        </h3>
        <span className="face-instrument text-[10px]" style={{ color: 'var(--ink-faint)' }}>
          {scene.dialogue.length} {t('card.lines')}
          {scene.branches.length > 0 && ` · ${scene.branches.length} ${t('card.branches')}`}
        </span>
      </div>

      <div className="flex border-t" style={{ borderColor: 'var(--rule)' }}>
        <button
          onClick={() => onPlay(index)}
          title={t('card.play')}
          className="flex-1 flex items-center justify-center gap-1 py-1.5 text-[11px] transition-colors
            hover:opacity-80 focus-visible:outline focus-visible:outline-2"
          style={{ color: 'var(--ink-soft)' }}
        >
          <Play size={11} aria-hidden="true" /> {t('card.play')}
        </button>
        <button
          onClick={() => onRewrite(scene.id)}
          title={t('card.rewrite')}
          className="flex items-center justify-center gap-1 px-3 py-1.5 text-[11px] border-l transition-colors
            hover:opacity-80 focus-visible:outline focus-visible:outline-2"
          style={{ color: 'var(--instrument)', borderColor: 'var(--rule)' }}
        >
          <Pencil size={11} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/SceneCard.tsx frontend/src/i18n/dict.ts
git commit -m "feat(storyboard): add SceneCard"
```

---

### Task 12: StoryboardBoard（故事板主区）

**Files:**
- Create: `frontend/src/components/StoryboardBoard.tsx`
- Modify: `frontend/src/store.ts`（新增 `jumpToScene` action）

**Interfaces:**
- Consumes: `SceneCard`（Task 11）、`ScriptPanel`（既有）、store `blackboard.scene_scripts`
- Produces:
  - store 新增 state `playFromScene: number`、`scriptFocusIndex: number`
  - store 新增 action `jumpToScene(index: number): void`（置 `playFromScene` 并进播放器）、`focusScene(index: number): void`
  - 默认导出组件 `StoryboardBoard`。Task 13 消费。

> **⚠ 必须保住既有操作入口。** `ScriptPanel.tsx:221-254` 是 `Confirm & Continue` / `Regenerate Script` / `Preview VN` / `Export JSON` / `Back to Setting` 五个按钮的**唯一**宿主，且逐场对白编辑器也只在那里。故事板**不能**简单取代它，否则 `script_review` 阶段用户将无法确认剧本——整条非 fast_mode 流程会断掉。本任务的做法是：故事板 = 卡片网格 + 原有操作栏，点卡片标题进入该场景的 `ScriptPanel` 详情态（即 spec §4.4 所说的"吸收为卡片详情态"）。

- [ ] **Step 1: store 加跳场与聚焦**

在 `frontend/src/store.ts`：

1. state 区加：

```ts
  playFromScene: number
  scriptFocusIndex: number
```

2. action 区加：

```ts
  jumpToScene: (index: number) => void
  focusScene: (index: number) => void
```

3. 初始 state 加：

```ts
  playFromScene: 0,
  scriptFocusIndex: 0,
```

4. 实现区加：

```ts
  jumpToScene: (index) => set({ playFromScene: index, vnPreview: true }),
  focusScene: (index) => set({ scriptFocusIndex: index }),
```

- [ ] **Step 2: VNPreview / ScriptPanel 读取初始索引**

`frontend/src/components/VNPreview.tsx`，把 `const [sceneIdx, setSceneIdx] = useState(0)` 改为：

```tsx
  const playFromScene = useStore(s => s.playFromScene)
  const [sceneIdx, setSceneIdx] = useState(playFromScene)
```

`frontend/src/components/ScriptPanel.tsx`，把 `const [activeScene, setActiveScene] = useState(0)` 改为：

```tsx
  const scriptFocusIndex = useStore(s => s.scriptFocusIndex)
  const [activeScene, setActiveScene] = useState(scriptFocusIndex)
```

- [ ] **Step 3: SceneCard 加标题点击**

在 `frontend/src/components/SceneCard.tsx` 的 props 接口加 `onOpen: (index: number) => void`，并把标题包成按钮：

```tsx
        <button
          onClick={() => onOpen(index)}
          className="face-narrative text-sm text-left hover:underline
            focus-visible:outline focus-visible:outline-2"
          style={{ color: 'var(--ink)', lineHeight: 1.4 }}
        >
          {scene.title || scene.id}
        </button>
```

（同时把 props 解构处补上 `onOpen`。）

- [ ] **Step 4: 创建 StoryboardBoard**

创建 `frontend/src/components/StoryboardBoard.tsx`：

```tsx
import { useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import useStore from '../store'
import SceneCard, { type SceneCardScene } from './SceneCard'
import ScriptPanel from './ScriptPanel'
import { useT } from '../i18n/useT'

/** v4 P6 storyboard: the workbench form once a script exists. Makes the
 *  branching structure legible at a glance and turns Chat Ops scene
 *  targeting from "describe which scene" into a spatial pick.
 *
 *  ScriptPanel is not replaced — it becomes the card detail view, because it
 *  owns the only per-scene dialogue editor AND the only script_review action
 *  bar (Confirm & Continue / Regenerate / Export / Back to Setting). */
export default function StoryboardBoard() {
  const t = useT()
  const { blackboard, currentJobId, jumpToScene, focusScene, sendChatMessage } = useStore()
  const scenes = (blackboard.scene_scripts as SceneCardScene[] | undefined) ?? []
  const [detail, setDetail] = useState(false)

  if (scenes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full" style={{ color: 'var(--ink-faint)' }}>
        <p className="text-sm">{t('preview.empty')}</p>
      </div>
    )
  }

  if (detail) {
    return (
      <div className="flex flex-col h-full">
        <button
          onClick={() => setDetail(false)}
          className="face-instrument flex items-center gap-1.5 px-4 py-2 text-[11px] border-b self-start
            focus-visible:outline focus-visible:outline-2"
          style={{ color: 'var(--ink-soft)', borderColor: 'var(--rule)' }}
        >
          <ArrowLeft size={12} aria-hidden="true" /> {t('board.backToBoard')}
        </button>
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <ScriptPanel />
        </div>
      </div>
    )
  }

  const openDetail = (index: number) => {
    focusScene(index)
    setDetail(true)
  }

  const handleRewrite = (sceneId: string) => {
    const scene = scenes.find(s => s.id === sceneId)
    // Reuses the existing P3 chat-ops chain end to end: this message goes
    // through intent classification and the preview/confirm card exactly as
    // a typed request would. No new execution path.
    sendChatMessage(`改写场景「${scene?.title || sceneId}」`)
  }

  return (
    <div className="p-6">
      <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(180px,1fr))]">
        {scenes.map((scene, i) => (
          <SceneCard
            key={scene.id}
            scene={scene}
            index={i}
            jobId={currentJobId}
            onPlay={jumpToScene}
            onOpen={openDetail}
            onRewrite={handleRewrite}
          />
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: 补字典**

`zh` 块追加 `'board.backToBoard': '返回故事板',`；`en` 块追加 `'board.backToBoard': 'Back to board',`。

- [ ] **Step 6: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

- [ ] **Step 7: 验证操作入口未丢失**

起 mock 后端 + dev server，`?shell=v1` 下跑到 `script_review`，记下 ScriptPanel 底部的五个按钮。稍后 Task 13 完成后在 `?shell=v2` 下点开任一卡片详情，确认**同样五个按钮都在且可用**。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/components/StoryboardBoard.tsx frontend/src/components/SceneCard.tsx frontend/src/components/ScriptPanel.tsx frontend/src/components/VNPreview.tsx frontend/src/store.ts frontend/src/i18n/dict.ts
git commit -m "feat(storyboard): add StoryboardBoard with card detail view

ScriptPanel becomes the detail view rather than being replaced — it owns the
only per-scene dialogue editor and the only script_review action bar, so
routing around it would have made the non-fast-mode flow unconfirmable."
```

---

### Task 13: 按形态接入 WorkbenchShell

**Files:**
- Modify: `frontend/src/shell/WorkbenchShell.tsx`

**Interfaces:**
- Consumes: `PipelineStage`（Task 10）、`StoryboardBoard`（Task 12）、`VNPreview` / `SettingPanel` / `AssetPanel`（既有）、store `step` / `vnPreview`
- Produces: 无新接口

> **两处关键点：**
>
> 1. **`setting_review` 必须路由到 `SettingPanel`。** 它是 `Confirm & Generate Script` / `Regenerate` 两个按钮的唯一宿主（`SettingPanel.tsx:140-151`）；漏掉这条路由会让非 fast_mode 流程无法确认设定。
> 2. **主区宽度随形态变化**，而不是恒定五五分栏——五五分栏正是「像通用模板」的来源（见 `FRONTEND_REDESIGN_v4.md` §1.2 缺陷 A）。播放器形态下对话栏完全隐藏，作品全幅铺满。

- [ ] **Step 1: 主区与布局改为形态驱动**

把 `frontend/src/shell/WorkbenchShell.tsx` 整体替换为：

```tsx
import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import ChatPanel from '../components/ChatPanel'
import JobHistory from '../components/JobHistory'
import StatusBar from '../components/StatusBar'
import PipelineStage from '../components/PipelineStage'
import StoryboardBoard from '../components/StoryboardBoard'
import SettingPanel from '../components/SettingPanel'
import AssetPanel from '../components/AssetPanel'
import VNPreview from '../components/VNPreview'
import useStore from '../store'
import { useT } from '../i18n/useT'

type Form = 'player' | 'pipeline' | 'setting' | 'assets' | 'failed' | 'board'

/** Workbench form follows AppStep — see FRONTEND_REDESIGN_v4.md §2.
 *  vnPreview wins over everything so Autopilot's zero-click path into the
 *  player is unaffected. */
function resolveForm(step: string, vnPreview: boolean): Form {
  if (vnPreview) return 'player'
  if (step === 'generating_setting' || step === 'generating_script' || step === 'compiling') return 'pipeline'
  // SettingPanel owns the only Confirm & Generate Script / Regenerate
  // buttons — routing this step anywhere else breaks the non-fast-mode flow.
  if (step === 'setting_review') return 'setting'
  if (step === 'asset_management' || step === 'completed') return 'assets'
  if (step === 'failed') return 'failed'
  return 'board'
}

// The chat column is not a fixed half. A constant 50/50 split is exactly what
// made the old shell read as a generic template; here the workbench yields
// space to whatever the current form is actually about.
const CHAT_WIDTH: Record<Form, string> = {
  player: '0',       // full-bleed artifact, workbench out of the way
  pipeline: '20rem', // narrow — the stage is the subject
  setting: '24rem',
  assets: '24rem',
  failed: '24rem',
  board: '24rem',
}

export default function WorkbenchShell() {
  const t = useT()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const step = useStore(s => s.step)
  const vnPreview = useStore(s => s.vnPreview)
  const errors = useStore(s => s.errors)

  const form = resolveForm(step, vnPreview)

  const main =
    form === 'player' ? <VNPreview />
    : form === 'pipeline' ? <PipelineStage />
    : form === 'setting' ? <SettingPanel />
    : form === 'assets' ? <AssetPanel />
    : form === 'failed' ? (
      <div className="p-6">
        <div className="rounded-lg border p-5" style={{ background: 'var(--surface)', borderColor: 'var(--crit)' }}>
          <p className="face-instrument text-sm mb-3" style={{ color: 'var(--crit)' }}>{t('preview.failed')}</p>
          <pre
            className="text-xs rounded p-3 overflow-x-auto whitespace-pre-wrap"
            style={{ background: 'var(--ground)', color: 'var(--ink-soft)' }}
          >
            {errors.join('\n') || t('preview.unknownError')}
          </pre>
        </div>
      </div>
    ) : <StoryboardBoard />

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--ground)', color: 'var(--ink)' }}>
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="md:hidden fixed top-3 left-3 z-50 p-2 rounded-lg
          focus-visible:outline focus-visible:outline-2"
        style={{ background: 'var(--surface-raised)', color: 'var(--ink-soft)' }}
      >
        {sidebarOpen ? '✕' : '☰'}
      </button>

      <aside
        className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0 fixed md:static z-40 w-64 shrink-0 flex flex-col h-full
          border-r transition-transform duration-200`}
        style={{ background: 'var(--surface)', borderColor: 'var(--rule)' }}
      >
        <JobHistory />
      </aside>

      {sidebarOpen && (
        <div className="md:hidden fixed inset-0 z-30 bg-black/50" onClick={() => setSidebarOpen(false)} />
      )}

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Chat column — width follows the form; fully collapsed in player */}
          <div
            className="flex flex-col overflow-hidden border-b md:border-b-0 md:border-r
              transition-[width] duration-300 shrink-0"
            style={{
              borderColor: 'var(--rule)',
              width: CHAT_WIDTH[form],
              display: form === 'player' ? 'none' : undefined,
            }}
          >
            <ChatPanel />
          </div>

          {/* Main region — cross-dissolve between forms */}
          <div className="flex-1 overflow-y-auto custom-scrollbar relative">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={form}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25 }}
                className="h-full"
              >
                {main}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
        <StatusBar />
      </div>
    </div>
  )
}
```

> `prefers-reduced-motion` 由 Task 3 的 `tokens.css` 全局压制过渡时长，`AnimatePresence` 的淡入淡出在该偏好下会退化为瞬时切换，无需额外分支。

- [ ] **Step 2: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: v2 全链路 mock 烟测**

起 mock 后端 + dev server，访问 `http://localhost:5173/?shell=v2`，逐条验证：

1. **空态**：进入即见故事板空态提示
2. **流水线剧场**：输入「校园恋爱」→ 发送 → 对话栏收窄、主区出现流水线节点，节点按序点亮（导演 → 结构审校 → 状态编排 → 分场推理 → 交叉引用 → 编剧 → 质量审校），场景胶片条逐格填充，花费数字跳动
3. **设定确认**（**不勾选 Fast Mode**）：生成设定后主区是 `SettingPanel`，「Confirm & Generate Script」「Regenerate」两个按钮都在且可用
4. **故事板**：剧本生成完成后主区变为场景卡网格
5. **卡片详情**：点卡片标题 → 进入 ScriptPanel 详情，确认底部**五个按钮**（Confirm & Continue / Regenerate Script / Preview VN / Export JSON / Back to Setting）都在且可用 → 点「返回故事板」能回到网格
6. **从卡片播放**：点某张卡的「从这里播放」→ 从该场进播放器，且**对话栏完全隐藏、播放器全幅**
7. **就地改写**：点卡片的铅笔图标 → 左侧出现意图确认卡 → 确认 → 场景更新
8. **Autopilot**：刷新后输入新主题点「⚡ 一键生成」→ 零点击直达全幅播放器
9. 形态切换时有约 250ms 交叉溶解，不闪烁
10. 全程 console 无报错

- [ ] **Step 4: 与 v1 并排对照**

同时开 `?shell=v1`，确认旧壳**行为完全未变**。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/shell/WorkbenchShell.tsx
git commit -m "feat(shell): drive v2 layout and main region by workbench form

Chat column width follows the form instead of a constant 50/50 split, and
collapses entirely in the player so the artifact runs full-bleed. Routes
setting_review to SettingPanel, which owns the only setting-confirm actions."
```

---

# L5 · 切换与清理

### Task 14: 默认切到 v2

**Files:**
- Modify: `frontend/src/shell/useShellVariant.ts`

**Interfaces:**
- Consumes: 无
- Produces: 无

- [ ] **Step 1: 翻转默认值**

在 `frontend/src/shell/useShellVariant.ts` 中：

```ts
// L5 cutover: v2 is now the default. ?shell=v1 still reaches the legacy
// shell until Task 15 removes it.
const DEFAULT_VARIANT: ShellVariant = 'v2'
```

- [ ] **Step 2: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: 验证默认与逃生口**

清空 localStorage（DevTools → Application → Local Storage 删 `vn-agent.shell`），访问不带参数的 `http://localhost:5173/`，应直接进 v2；再访问 `?shell=v1` 应能退回旧壳。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/shell/useShellVariant.ts
git commit -m "feat(shell): make the v2 workbench the default"
```

---

### Task 15: 移除旧外壳（观察期后）

**Files:**
- Delete: `frontend/src/shell/LegacyShell.tsx`、`frontend/src/components/PreviewPanel.tsx`、`frontend/src/components/ProgressBar.tsx`
- Modify: `frontend/src/App.tsx`、`frontend/src/shell/useShellVariant.ts`

**Interfaces:**
- Consumes: 无
- Produces: 无

> **前置条件**：Task 14 之后至少完整走过一轮 P2→P5 四条链路 mock 烟测且无问题。**若用户近期有面试演示安排，本任务应推迟**——保留逃生口的成本几乎为零。

- [ ] **Step 1: 确认无残留引用**

```bash
cd frontend && grep -rn "PreviewPanel\|ProgressBar\|LegacyShell" src/
```

预期：仅 `App.tsx` 与待删文件自身命中。若 `ProgressBar` 仍被其他组件引用，先处理该引用再继续。

- [ ] **Step 2: 删除文件**

```bash
cd frontend && rm src/shell/LegacyShell.tsx src/components/PreviewPanel.tsx src/components/ProgressBar.tsx
```

- [ ] **Step 3: 简化 App.tsx**

```tsx
import WorkbenchShell from './shell/WorkbenchShell'

export default function App() {
  return <WorkbenchShell />
}
```

- [ ] **Step 4: 删除外壳选择器**

```bash
cd frontend && rm src/shell/useShellVariant.ts
```

- [ ] **Step 5: 类型检查 + 构建**

```bash
cd frontend && npm run build
```

预期：构建成功，无未解析 import。

- [ ] **Step 6: 最终全链路 mock 烟测**

起 mock 后端 + dev server，完整走一遍 P2→P5 四条链路 + 中英文切换，确认无 JS 报错。

- [ ] **Step 7: 提交**

```bash
git add -u frontend/src/
git commit -m "chore(shell): remove the legacy shell after v2 soak

Deletes LegacyShell, PreviewPanel and ProgressBar. ProgressBar's
stepIndex() substring-matching is fully superseded by real node events."
```

---

## 完成后

- 更新 `docs/v4/FRONTEND_REDESIGN_v4.md`，把 §6.2 的迁移表标注为已完成并记录实际偏差（如 Task 9 的 CSS-vs-SVG 决定）。
- 建议向用户提出跑一次 `/gemini-review` 或 `senior-code-reviewer` 复审新增组件（`feedback_delegation_reminders`）。
- `docs/v4/RESUME_BRIEF_v4.md` / `_CN.md` 可新增一条 P6 交付记录——注意那两个文件目前是**未跟踪**状态，需与用户确认后再动。
