# Changelog

> 每日 commit 流水自动追加至此（由 `scripts/update_docs.py` 在 pre-commit hook 维护）。
> 稳定区文档（架构 / 决策 / 审计 / 产品路线）请看：
> - [PRODUCT.md](./PRODUCT.md) — 北极星 + 当前 backlog
> - [ARCHITECTURE.md](./ARCHITECTURE.md) — 未来架构路线
> - [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md) — 关键决策的"为什么"
> - [AUDITS.md](./AUDITS.md) — 已知技术债分析
>
> 历史每日流水（2026-04-23 切分前）归档在 [archive/DEV_LOG_legacy.md](./archive/DEV_LOG_legacy.md)。

遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格。版本号暂不严格遵循 SemVer（项目为研究型原型）。

---

## [Unreleased]

### 2026-08-20 | 实现 - 2026-08-20 11:11

**变更文件** (3 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/local_regen.py`
  - `src/vn_agent/agents/writer.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_writer.py`

**变更统计**:
```
src/vn_agent/agents/local_regen.py |  1 +
 src/vn_agent/agents/writer.py      | 26 ++++++++++++++++-
 tests/test_agents/test_writer.py   | 59 ++++++++++++++++++++++++++++++++++++++
 3 files changed, 85 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-20 | 实现 - 2026-08-20 11:11

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/director.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_director.py`

**变更统计**:
```
src/vn_agent/agents/director.py    | 18 ++++++++++++++++
 tests/test_agents/test_director.py | 42 ++++++++++++++++++++++++++++++++++++++
 2 files changed, 60 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-20 | 实现 - 2026-08-20 11:11

**变更文件** (4 个):
**源码变更** (2 文件):
  - `src/vn_agent/services/mock_llm.py`
  - `src/vn_agent/services/mock_synth.py`

**测试变更** (2 文件):
  - `tests/test_services/test_mock_llm.py`
  - `tests/test_services/test_mock_synth.py`

**变更统计**:
```
src/vn_agent/services/mock_llm.py      | 118 +++++++++-
 src/vn_agent/services/mock_synth.py    | 383 +++++++++++++++++++++++++++++++++
 tests/test_services/test_mock_llm.py   |  76 +++++++
 tests/test_services/test_mock_synth.py | 266 +++++++++++++++++++++++
 4 files changed, 837 insertions(+), 6 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-13 | 文档 - 2026-08-13 00:54

**变更文件** (5 个):
**其他变更** (1 文件):
  - `README.md`

**变更统计**:
```
README.md                     | 6 +++---
 docs/PRODUCT.md               | 2 +-
 docs/v4/RESUME_BRIEF_v4.md    | 8 +++++---
 docs/v4/RESUME_BRIEF_v4_CN.md | 8 +++++---
 docs/v4/SHOWCASE_v4.md        | 2 +-
 5 files changed, 15 insertions(+), 11 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-13 | 杂项 - 2026-08-13 00:38

**变更文件** (2 个):
**其他变更** (2 文件):
  - `data/autopilot/runs.jsonl`
  - `scripts/update_docs.py`

**变更统计**:
```
data/autopilot/runs.jsonl |  6 ++++
 scripts/update_docs.py    | 85 +++++++++++++++--------------------------------
 2 files changed, 33 insertions(+), 58 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-13 | 测试 - 2026-08-13 00:35

**变更文件** (9 个):
**测试变更** (9 文件):
  - `tests/conftest.py`
  - `tests/test_agents/test_graph_routing.py`
  - `tests/test_agents/test_structure_reviewer.py`
  - `tests/test_cli/test_mock_patch.py`
  - `tests/test_integration/test_real_api.py`

**变更统计**:
```
tests/conftest.py                                  | 102 ++++++++++++++
 tests/test_agents/test_graph_routing.py            |   8 +-
 tests/test_agents/test_structure_reviewer.py       |  10 +-
 tests/test_cli/test_mock_patch.py                  |   7 +
 tests/test_integration/test_real_api.py            |   6 +
 tests/test_services/test_image_gen.py              |   6 +
 tests/test_services/test_llm.py                    |   5 +
 tests/test_services/test_llm_mock_context.py       |   5 +
 .../test_no_billable_calls_in_tests.py             | 153 +++++++++++++++++++++
 9 files changed, 299 insertions(+), 3 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-13 | 实现 - 2026-08-13 00:35

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/eval/embedder.py`

**测试变更** (1 文件):
  - `tests/test_eval/test_embedder.py`

**变更统计**:
```
src/vn_agent/eval/embedder.py    | 25 ++++++++++++++++++++++++-
 tests/test_eval/test_embedder.py | 40 ++++++++++++++++++++++++++++++++++++++++
 2 files changed, 64 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-12 | 文档 - 2026-08-12 02:04

**变更文件** (5 个):
**其他变更** (1 文件):
  - `README.md`

**变更统计**:
```
README.md                     | 6 +++---
 docs/PRODUCT.md               | 2 +-
 docs/v4/RESUME_BRIEF_v4.md    | 4 +++-
 docs/v4/RESUME_BRIEF_v4_CN.md | 4 +++-
 docs/v4/SHOWCASE_v4.md        | 2 +-
 5 files changed, 11 insertions(+), 7 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-12 | 文档 - 2026-08-12 01:48

**变更文件** (5 个):
**其他变更** (1 文件):
  - `.gitignore`

**变更统计**:
```
.gitignore                    |   4 ++
 docs/PRODUCT.md               |   2 +-
 docs/v4/RESUME_BRIEF_v4.md    |   8 +++-
 docs/v4/RESUME_BRIEF_v4_CN.md |   8 +++-
 docs/v4/SHOWCASE_v4.md        | 100 ++++++++++++++++++++++++++++++++++--------
 5 files changed, 99 insertions(+), 23 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-12 | 实现 - 2026-08-12 01:48

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/web/app.py`

**测试变更** (1 文件):
  - `tests/test_web/test_mock_floor.py`

**变更统计**:
```
src/vn_agent/web/app.py           | 11 +++++++++++
 tests/test_web/test_mock_floor.py | 28 ++++++++++++++++++++++++++++
 2 files changed, 39 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-11 | 文档 - 2026-08-11 02:26

**变更文件** (4 个):
**其他变更** (1 文件):
  - `README.md`

**变更统计**:
```
README.md                                     |  17 +++++++++++++++--
 docs/v4/SHOWCASE_v4.md                        |  14 ++++++++++++--
 docs/v4/assets/workbench-pipeline-theatre.jpg | Bin 0 -> 59296 bytes
 docs/v4/assets/workbench-player.jpg           | Bin 0 -> 36232 bytes
 4 files changed, 27 insertions(+), 4 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-11 | 文档 - 2026-08-11 02:09

**变更文件** (21 个):
**其他变更** (8 文件):
  - `.claude/settings.local.json`
  - `.gitignore`
  - `README.md`
  - `data/autopilot/runs.jsonl`
  - `eval_ollama_results.json`

**变更统计**:
```
.claude/settings.local.json                |  35 --
 .gitignore                                 |  21 ++
 README.md                                  |  73 +++-
 data/autopilot/runs.jsonl                  |   6 +
 docs/ARCHITECTURE.md                       | 464 ++++++++++++++++++++++++
 docs/AUDITS.md                             | 103 ++++++
 docs/DESIGN_DECISIONS.md                   | 212 +++++++++++
 docs/archive/DEV_LOG_legacy.md             | 407 +--------------------
 docs/v3/BYTE_AI_PLATFORM_EVAL_INTERVIEW.md | 351 ++++++++++++++++++
 docs/v3/SHOWCASE_v3.md                     | 293 +++++++++++++++
 docs/v3/pipeline_graph.mmd                 |  36 ++
 docs/v3/pipeline_graph.png                 | Bin 0 -> 42612 bytes
 docs/v3/pipeline_writer_graph.mmd          |  24 ++
 docs/v3/pipeline_writer_graph.png          | Bin 0 -> 20564 bytes
 docs/v4/RESUME_BRIEF_v4.md                 | 564 +++++++++++++++++++++++++++++
 docs/v4/RESUME_BRIEF_v4_CN.md              | 564 +++++++++++++++++++++++++++++
 docs/v4/SHOWCASE_v4.md                     | 151 ++++++++
 eval_ollama_results.json                   | 158 --------
 eval_strategy_results.json                 |  93 -----
 eval_structural_results.json               |  66 ----
 scripts/dump_langgraph_diagram.py          |  52 +++
 21 files changed, 2912 insertions(+), 761 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-11 | 实现 - 2026-08-11 01:55

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/web/app.py`

**测试变更** (1 文件):
  - `tests/test_web/test_mock_floor.py`

**变更统计**:
```
src/vn_agent/web/app.py           |  37 ++++++++++---
 tests/test_web/test_mock_floor.py | 110 ++++++++++++++++++++++++++++++++++++++
 2 files changed, 141 insertions(+), 6 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-11 | 杂项 - 2026-08-11 00:21

**变更文件** (1 个):
**其他变更** (1 文件):
  - `frontend/src/shell/useShellVariant.ts`

**变更统计**:
```
frontend/src/shell/useShellVariant.ts | 7 +++----
 1 file changed, 3 insertions(+), 4 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-11 | 杂项 - 2026-08-11 00:10

**变更文件** (6 个):
**其他变更** (6 文件):
  - `frontend/src/components/ChatPanel.tsx`
  - `frontend/src/components/PipelineStage.tsx`
  - `frontend/src/components/PreviewPanel.tsx`
  - `frontend/src/i18n/dict.ts`
  - `frontend/src/i18n/useT.ts`

**变更统计**:
```
frontend/src/components/ChatPanel.tsx     | 11 ++++++++---
 frontend/src/components/PipelineStage.tsx | 13 ++++---------
 frontend/src/components/PreviewPanel.tsx  | 13 ++++---------
 frontend/src/i18n/dict.ts                 | 22 ++++++++++++++++++++++
 frontend/src/i18n/useT.ts                 | 27 +++++++++++++++++++++++++++
 frontend/src/store.ts                     | 26 ++++++++++++++++----------
 6 files changed, 81 insertions(+), 31 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-10 | 杂项 - 2026-08-10 23:35

**变更文件** (5 个):
**其他变更** (5 文件):
  - `frontend/package-lock.json`
  - `frontend/package.json`
  - `frontend/src/components/PipelineGraph.tsx`
  - `frontend/src/design/tokens.css`
  - `frontend/src/shell/WorkbenchShell.tsx`

**变更统计**:
```
frontend/package-lock.json                | 43 +++----------------------------
 frontend/package.json                     |  1 -
 frontend/src/components/PipelineGraph.tsx | 15 ++++-------
 frontend/src/design/tokens.css            | 32 +++++++++++++++++++++++
 frontend/src/shell/WorkbenchShell.tsx     | 20 +++++---------
 5 files changed, 46 insertions(+), 65 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-10 | 杂项 - 2026-08-10 23:26

**变更文件** (1 个):
**其他变更** (1 文件):
  - `frontend/src/shell/WorkbenchShell.tsx`

**变更统计**:
```
frontend/src/shell/WorkbenchShell.tsx | 92 ++++++++++++++++++++++++++++++++---
 1 file changed, 84 insertions(+), 8 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-10 | 杂项 - 2026-08-10 23:25

**变更文件** (6 个):
**其他变更** (6 文件):
  - `frontend/src/components/SceneCard.tsx`
  - `frontend/src/components/ScriptPanel.tsx`
  - `frontend/src/components/StoryboardBoard.tsx`
  - `frontend/src/components/VNPreview.tsx`
  - `frontend/src/i18n/dict.ts`

**变更统计**:
```
frontend/src/components/SceneCard.tsx       | 12 +++--
 frontend/src/components/ScriptPanel.tsx     |  5 +-
 frontend/src/components/StoryboardBoard.tsx | 79 +++++++++++++++++++++++++++++
 frontend/src/components/VNPreview.tsx       |  5 +-
 frontend/src/i18n/dict.ts                   |  6 +++
 frontend/src/store.ts                       | 11 ++++
 6 files changed, 113 insertions(+), 5 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-10 | 杂项 - 2026-08-10 23:22

**变更文件** (2 个):
**其他变更** (2 文件):
  - `frontend/src/components/SceneCard.tsx`
  - `frontend/src/i18n/dict.ts`

**变更统计**:
```
frontend/src/components/SceneCard.tsx | 84 +++++++++++++++++++++++++++++++++++
 frontend/src/i18n/dict.ts             | 10 +++++
 2 files changed, 94 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-10 | 杂项 - 2026-08-10 23:20

**变更文件** (4 个):
**其他变更** (4 文件):
  - `frontend/src/components/PipelineStage.tsx`
  - `frontend/src/components/PreviewPanel.tsx`
  - `frontend/src/components/StatusBar.tsx`
  - `frontend/src/store.ts`

**变更统计**:
```
frontend/src/components/PipelineStage.tsx | 89 +++++++++++++++++++++++++++++++
 frontend/src/components/PreviewPanel.tsx  | 39 ++++++++++----
 frontend/src/components/StatusBar.tsx     | 25 ++++-----
 frontend/src/store.ts                     | 25 ++++++++-
 4 files changed, 151 insertions(+), 27 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-10 | 杂项 - 2026-08-10 23:12

**变更文件** (8 个):
**其他变更** (8 文件):
  - `frontend/src/components/ChatPanel.tsx`
  - `frontend/src/components/JobHistory.tsx`
  - `frontend/src/components/PreviewPanel.tsx`
  - `frontend/src/i18n/dict.ts`
  - `frontend/src/i18n/interpolate.ts`

**变更统计**:
```
frontend/src/components/ChatPanel.tsx    | 18 +++++--
 frontend/src/components/JobHistory.tsx   |  2 +-
 frontend/src/components/PreviewPanel.tsx | 14 ++++-
 frontend/src/i18n/dict.ts                | 76 ++++++++++++++++++++++++++++
 frontend/src/i18n/interpolate.ts         | 19 +++++++
 frontend/src/i18n/useT.ts                | 42 +++++++++++++++
 frontend/src/store.ts                    | 87 +++++++++++++++++++++++---------
 frontend/src/types.ts                    | 10 ++++
 8 files changed, 239 insertions(+), 29 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-10 | 杂项 - 2026-08-10 22:59

**变更文件** (3 个):
**其他变更** (3 文件):
  - `frontend/src/components/PipelineGraph.tsx`
  - `frontend/src/i18n/dict.ts`
  - `frontend/src/store.ts`

**变更统计**:
```
frontend/src/components/PipelineGraph.tsx | 88 +++++++++++++++++++++++++++++++
 frontend/src/i18n/dict.ts                 | 26 +++++++++
 frontend/src/store.ts                     | 11 +++-
 3 files changed, 124 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-10 | 杂项 - 2026-08-10 22:56

**变更文件** (2 个):
**其他变更** (2 文件):
  - `frontend/src/api.ts`
  - `frontend/src/store.ts`

**变更统计**:
```
frontend/src/api.ts   |  5 +++++
 frontend/src/store.ts | 36 ++++++++++++++++++++++++++++++++++--
 2 files changed, 39 insertions(+), 2 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-10 | 杂项 - 2026-08-10 22:48

**变更文件** (4 个):
**其他变更** (4 文件):
  - `frontend/src/App.tsx`
  - `frontend/src/shell/LegacyShell.tsx`
  - `frontend/src/shell/WorkbenchShell.tsx`
  - `frontend/src/shell/useShellVariant.ts`

**变更统计**:
```
frontend/src/App.tsx                  | 53 ++++-----------------------------
 frontend/src/shell/LegacyShell.tsx    | 55 +++++++++++++++++++++++++++++++++++
 frontend/src/shell/WorkbenchShell.tsx | 53 +++++++++++++++++++++++++++++++++
 frontend/src/shell/useShellVariant.ts | 44 ++++++++++++++++++++++++++++
 4 files changed, 157 insertions(+), 48 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-10 | 杂项 - 2026-08-10 00:06

**变更文件** (9 个):
**其他变更** (9 文件):
  - `frontend/src/components/AssetPanel.tsx`
  - `frontend/src/components/FeedbackWidget.tsx`
  - `frontend/src/components/JobHistory.tsx`
  - `frontend/src/components/PlaytestPane.tsx`
  - `frontend/src/components/PreviewPanel.tsx`

**变更统计**:
```
frontend/src/components/AssetPanel.tsx     |  97 +++++-----
 frontend/src/components/FeedbackWidget.tsx |  12 +-
 frontend/src/components/JobHistory.tsx     |  14 +-
 frontend/src/components/PlaytestPane.tsx   |  47 ++---
 frontend/src/components/PreviewPanel.tsx   |  19 +-
 frontend/src/components/ScriptPanel.tsx    |  32 ++--
 frontend/src/components/SettingPanel.tsx   |  34 ++--
 frontend/src/components/StatusBar.tsx      |  19 +-
 frontend/src/i18n/dict.ts                  | 274 +++++++++++++++++++++++++++++
 9 files changed, 411 insertions(+), 137 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-09 | 杂项 - 2026-08-09 21:50

**变更文件** (2 个):
**其他变更** (2 文件):
  - `frontend/src/components/ChatPanel.tsx`
  - `frontend/src/components/VNPreview.tsx`

**变更统计**:
```
frontend/src/components/ChatPanel.tsx | 51 ++++++++++++++++++-----------------
 frontend/src/components/VNPreview.tsx | 20 +++++++-------
 2 files changed, 38 insertions(+), 33 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-09 | 杂项 - 2026-08-09 21:24

**变更文件** (4 个):
**其他变更** (4 文件):
  - `frontend/src/components/JobHistory.tsx`
  - `frontend/src/i18n/dict.ts`
  - `frontend/src/i18n/useT.ts`
  - `frontend/src/store.ts`

**变更统计**:
```
frontend/src/components/JobHistory.tsx | 21 +++++++--
 frontend/src/i18n/dict.ts              | 82 ++++++++++++++++++++++++++++++++++
 frontend/src/i18n/useT.ts              | 11 +++++
 frontend/src/store.ts                  |  8 ++++
 4 files changed, 119 insertions(+), 3 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-09 | 杂项 - 2026-08-09 21:13

**变更文件** (4 个):
**其他变更** (4 文件):
  - `frontend/package-lock.json`
  - `frontend/package.json`
  - `frontend/src/design/tokens.css`
  - `frontend/src/index.css`

**变更统计**:
```
frontend/package-lock.json     | 53 ++++++++++++++++++++++++++++++++--
 frontend/package.json          |  2 ++
 frontend/src/design/tokens.css | 65 ++++++++++++++++++++++++++++++++++++++++++
 frontend/src/index.css         |  1 +
 4 files changed, 118 insertions(+), 3 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-09 | 实现 - 2026-08-09 21:05

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/web/app.py`

**测试变更** (1 文件):
  - `tests/test_web/test_pipeline_labels.py`

**变更统计**:
```
src/vn_agent/web/app.py                | 13 +++++++++++++
 tests/test_web/test_pipeline_labels.py | 26 ++++++++++++++++++++++++++
 2 files changed, 39 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-09 | 实现 - 2026-08-09 20:55

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/services/job_events.py`

**测试变更** (1 文件):
  - `tests/test_services/test_job_events.py`

**变更统计**:
```
src/vn_agent/services/job_events.py    | 17 +++++++
 tests/test_services/test_job_events.py | 87 ++++++++++++++++++++++++++++++++++
 2 files changed, 104 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-09 | 杂项 - 2026-08-09 20:50

**变更文件** (12 个):
**其他变更** (12 文件):
  - `data/assets/opensource/cafe_warm.png`
  - `data/assets/opensource/forest_dawn.png`
  - `data/assets/opensource/rooftop_day.png`
  - `data/assets/opensource/rooftop_night.png`
  - `data/assets/opensource/school_day.png`

**变更统计**:
```
data/assets/opensource/cafe_warm.png              | Bin 16841 -> 20679 bytes
 data/assets/opensource/forest_dawn.png            | Bin 17332 -> 21449 bytes
 data/assets/opensource/rooftop_day.png            | Bin 16376 -> 19440 bytes
 data/assets/opensource/rooftop_night.png          | Bin 16259 -> 20454 bytes
 data/assets/opensource/school_day.png             | Bin 16732 -> 19426 bytes
 data/assets/opensource/school_dusk.png            | Bin 17830 -> 20753 bytes
 data/assets/opensource/school_night.png           | Bin 16556 -> 20503 bytes
 data/assets/opensource/shrine_cool.png            | Bin 16546 -> 19145 bytes
 data/assets/opensource/student_female_neutral.png | Bin 14338 -> 14206 bytes
 data/assets/opensource/student_male_neutral.png   | Bin 14854 -> 14845 bytes
 data/assets/opensource/teacher_neutral.png        | Bin 11034 -> 10757 bytes
 scripts/seed_opensource_library.py                |  31 +++++++++++++++++-----
 12 files changed, 25 insertions(+), 6 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-09 | 杂项 - 2026-08-09 20:50

**变更文件** (1 个):
**其他变更** (1 文件):
  - `frontend/src/store.ts`

**变更统计**:
```
frontend/src/store.ts | 9 +++++++++
 1 file changed, 9 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-08-04 | 实现 - 2026-08-04 00:53

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/services/image_gen.py`

**测试变更** (1 文件):
  - `tests/test_services/test_image_gen.py`

**变更统计**:
```
src/vn_agent/services/image_gen.py    | 21 +++++++++++++
 tests/test_services/test_image_gen.py | 58 +++++++++++++++++++++++++++++++++++
 2 files changed, 79 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-27 | 实现 - 2026-07-27 00:57

**变更文件** (19 个):
**源码变更** (6 文件):
  - `src/vn_agent/autopilot/__init__.py`
  - `src/vn_agent/autopilot/outcomes.py`
  - `src/vn_agent/autopilot/resolver.py`
  - `src/vn_agent/cli.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/web/app.py`

**测试变更** (7 文件):
  - `tests/test_autopilot/__init__.py`
  - `tests/test_autopilot/test_outcomes.py`
  - `tests/test_autopilot/test_resolver.py`
  - `tests/test_cli/test_mock_patch.py`
  - `tests/test_config_override/__init__.py`

**配置变更** (1 文件):
  - `config/presets/autopilot_best.yaml`

**其他变更** (4 文件):
  - `frontend/src/api.ts`
  - `frontend/src/components/ChatPanel.tsx`
  - `frontend/src/store.ts`
  - `frontend/src/types.ts`

**变更统计**:
```
config/presets/autopilot_best.yaml                 |  51 +++++
 docs/v4/PRODUCT_v4.md                              |   9 +-
 frontend/src/api.ts                                |   8 +-
 frontend/src/components/ChatPanel.tsx              |  29 ++-
 frontend/src/store.ts                              |  15 +-
 frontend/src/types.ts                              |   5 +
 src/vn_agent/autopilot/__init__.py                 |  11 ++
 src/vn_agent/autopilot/outcomes.py                 | 139 ++++++++++++++
 src/vn_agent/autopilot/resolver.py                 |  55 ++++++
 src/vn_agent/cli.py                                |  27 ++-
 src/vn_agent/config.py                             |  38 +++-
 src/vn_agent/web/app.py                            | 135 +++++++++++++-
 tests/test_autopilot/__init__.py                   |   0
 tests/test_autopilot/test_outcomes.py              |  62 +++++++
 tests/test_autopilot/test_resolver.py              |  53 ++++++
 tests/test_cli/test_mock_patch.py                  |  71 +++++++
 tests/test_config_override/__init__.py             |   0
 .../test_config_override/test_settings_override.py |  86 +++++++++
 tests/test_web/test_autopilot_flow.py              | 206 +++++++++++++++++++++
 19 files changed, 988 insertions(+), 12 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-25 | 实现 - 2026-07-25 17:04

**变更文件** (24 个):
**源码变更** (11 文件):
  - `src/vn_agent/cli.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/playtest/__init__.py`
  - `src/vn_agent/playtest/agent.py`
  - `src/vn_agent/playtest/branch_walker.py`
  - `src/vn_agent/playtest/frame_compositor.py`
  - `src/vn_agent/playtest/schema.py`
  - `src/vn_agent/playtest/vision_judge.py`
  - `src/vn_agent/services/llm.py`
  - `src/vn_agent/services/mock_llm.py`
  - ...及其他 1 个文件

**测试变更** (6 文件):
  - `tests/test_playtest/__init__.py`
  - `tests/test_playtest/test_agent.py`
  - `tests/test_playtest/test_branch_walker.py`
  - `tests/test_playtest/test_frame_compositor.py`
  - `tests/test_playtest/test_vision_judge.py`

**配置变更** (1 文件):
  - `config/settings.yaml`

**其他变更** (5 文件):
  - `frontend/src/api.ts`
  - `frontend/src/components/AssetPanel.tsx`
  - `frontend/src/components/PlaytestPane.tsx`
  - `frontend/src/types.ts`
  - `scripts/smoke_longvn.py`

**变更统计**:
```
config/settings.yaml                         |   7 +
 docs/v4/PRODUCT_v4.md                        |   5 +-
 frontend/src/api.ts                          |  23 ++-
 frontend/src/components/AssetPanel.tsx       |   9 +-
 frontend/src/components/PlaytestPane.tsx     | 163 ++++++++++++++++++
 frontend/src/types.ts                        |  42 +++++
 scripts/smoke_longvn.py                      |  25 ++-
 src/vn_agent/cli.py                          |  45 +++++
 src/vn_agent/config.py                       |   9 +
 src/vn_agent/playtest/__init__.py            |  13 ++
 src/vn_agent/playtest/agent.py               | 169 +++++++++++++++++++
 src/vn_agent/playtest/branch_walker.py       | 106 ++++++++++++
 src/vn_agent/playtest/frame_compositor.py    | 244 +++++++++++++++++++++++++++
 src/vn_agent/playtest/schema.py              |  91 ++++++++++
 src/vn_agent/playtest/vision_judge.py        | 105 ++++++++++++
 src/vn_agent/services/llm.py                 |  51 +++++-
 src/vn_agent/services/mock_llm.py            |  15 +-
 src/vn_agent/web/app.py                      |  52 ++++++
 tests/test_playtest/__init__.py              |   0
 tests/test_playtest/test_agent.py            | 103 +++++++++++
 tests/test_playtest/test_branch_walker.py    | 122 ++++++++++++++
 tests/test_playtest/test_frame_compositor.py |  89 ++++++++++
 tests/test_playtest/test_vision_judge.py     |  75 ++++++++
 tests/test_web/test_playtest_endpoint.py     | 113 +++++++++++++
 24 files changed, 1655 insertions(+), 21 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-22 | 实现 - 2026-07-22 00:35

**变更文件** (14 个):
**源码变更** (5 文件):
  - `src/vn_agent/chat_ops/__init__.py`
  - `src/vn_agent/chat_ops/intent_router.py`
  - `src/vn_agent/chat_ops/orchestrator.py`
  - `src/vn_agent/services/mock_llm.py`
  - `src/vn_agent/web/app.py`

**测试变更** (5 文件):
  - `tests/test_chat_ops/__init__.py`
  - `tests/test_chat_ops/test_intent_router.py`
  - `tests/test_chat_ops/test_orchestrator.py`
  - `tests/test_services/test_mock_llm.py`
  - `tests/test_web/test_chat_endpoints.py`

**其他变更** (3 文件):
  - `frontend/src/api.ts`
  - `frontend/src/components/ChatPanel.tsx`
  - `frontend/src/store.ts`

**变更统计**:
```
docs/v4/PRODUCT_v4.md                     |   3 +-
 frontend/src/api.ts                       |  49 +++++
 frontend/src/components/ChatPanel.tsx     |  74 +++++++-
 frontend/src/store.ts                     |  71 ++++++-
 src/vn_agent/chat_ops/__init__.py         |   8 +
 src/vn_agent/chat_ops/intent_router.py    | 177 ++++++++++++++++++
 src/vn_agent/chat_ops/orchestrator.py     | 298 ++++++++++++++++++++++++++++++
 src/vn_agent/services/mock_llm.py         |  70 +++++++
 src/vn_agent/web/app.py                   | 145 +++++++++++++--
 tests/test_chat_ops/__init__.py           |   0
 tests/test_chat_ops/test_intent_router.py | 111 +++++++++++
 tests/test_chat_ops/test_orchestrator.py  | 224 ++++++++++++++++++++++
 tests/test_services/test_mock_llm.py      |  68 +++++++
 tests/test_web/test_chat_endpoints.py     | 172 +++++++++++++++++
 14 files changed, 1439 insertions(+), 31 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-21 | 文档 - 2026-07-21 23:36

**变更文件** (2 个):
**其他变更** (1 文件):
  - `scripts/smoke_longvn.py`

**变更统计**:
```
docs/v4/PRODUCT_v4.md   | 11 +++++++++++
 scripts/smoke_longvn.py | 10 ++++++++++
 2 files changed, 21 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-21 | 实现 - 2026-07-21 23:31

**变更文件** (11 个):
**源码变更** (3 文件):
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/services/job_events.py`
  - `src/vn_agent/web/app.py`

**其他变更** (8 文件):
  - `frontend/package-lock.json`
  - `frontend/package.json`
  - `frontend/src/api.ts`
  - `frontend/src/components/PreviewPanel.tsx`
  - `frontend/src/index.css`

**变更统计**:
```
frontend/package-lock.json               | 334 ++++++++++++++++++++++++++++++-
 frontend/package.json                    |   2 +
 frontend/src/api.ts                      |  36 ++++
 frontend/src/components/PreviewPanel.tsx |  19 +-
 frontend/src/index.css                   |   1 +
 frontend/src/main.tsx                    |   1 +
 frontend/src/store.ts                    |  57 +++++-
 frontend/vite.config.ts                  |   3 +-
 src/vn_agent/agents/writer.py            |  15 ++
 src/vn_agent/services/job_events.py      |  78 ++++++++
 src/vn_agent/web/app.py                  |  32 +++
 11 files changed, 565 insertions(+), 13 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-19 | 实现 - 2026-07-19 22:22

**变更文件** (16 个):
**源码变更** (7 文件):
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/cli.py`
  - `src/vn_agent/feedback/__init__.py`
  - `src/vn_agent/feedback/injector.py`
  - `src/vn_agent/feedback/reflection.py`
  - `src/vn_agent/feedback/store.py`
  - `src/vn_agent/web/app.py`

**测试变更** (5 文件):
  - `tests/test_feedback/__init__.py`
  - `tests/test_feedback/test_injector.py`
  - `tests/test_feedback/test_reflection.py`
  - `tests/test_feedback/test_store.py`
  - `tests/test_integration/test_flywheel_e2e.py`

**其他变更** (4 文件):
  - `frontend/src/api.ts`
  - `frontend/src/components/ChatPanel.tsx`
  - `frontend/src/components/FeedbackWidget.tsx`
  - `frontend/src/components/VNPreview.tsx`

**变更统计**:
```
frontend/src/api.ts                         |  34 ++++
 frontend/src/components/ChatPanel.tsx       |  13 +-
 frontend/src/components/FeedbackWidget.tsx  |  96 +++++++++
 frontend/src/components/VNPreview.tsx       |  10 +
 src/vn_agent/agents/writer.py               |  38 ++++
 src/vn_agent/cli.py                         |  17 ++
 src/vn_agent/feedback/__init__.py           |  10 +
 src/vn_agent/feedback/injector.py           | 220 ++++++++++++++++++++
 src/vn_agent/feedback/reflection.py         | 306 ++++++++++++++++++++++++++++
 src/vn_agent/feedback/store.py              | 211 +++++++++++++++++++
 src/vn_agent/web/app.py                     |  51 +++++
 tests/test_feedback/__init__.py             |   0
 tests/test_feedback/test_injector.py        | 164 +++++++++++++++
 tests/test_feedback/test_reflection.py      | 202 ++++++++++++++++++
 tests/test_feedback/test_store.py           | 156 ++++++++++++++
 tests/test_integration/test_flywheel_e2e.py | 169 +++++++++++++++
 16 files changed, 1696 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-19 | 实现 - 2026-07-19 20:46

**变更文件** (6 个):
**源码变更** (4 文件):
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/agents/structure_reviewer.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/services/pending_debug.py`

**测试变更** (1 文件):
  - `tests/test_services/test_pending_debug.py`

**其他变更** (1 文件):
  - `.claude/agents/run-analyzer.md`

**变更统计**:
```
.claude/agents/run-analyzer.md            |   8 ++
 src/vn_agent/agents/reviewer.py           |  48 ++++++-
 src/vn_agent/agents/structure_reviewer.py |  11 +-
 src/vn_agent/config.py                    |   6 +
 src/vn_agent/services/pending_debug.py    | 198 ++++++++++++++++++++++++++
 tests/test_services/test_pending_debug.py | 228 ++++++++++++++++++++++++++++++
 6 files changed, 495 insertions(+), 4 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-19 | 实现 - 2026-07-19 20:31

**变更文件** (5 个):
**源码变更** (2 文件):
  - `src/vn_agent/assets/upload_store.py`
  - `src/vn_agent/web/app.py`

**测试变更** (1 文件):
  - `tests/test_assets/test_upload_delete.py`

**其他变更** (2 文件):
  - `frontend/src/api.ts`
  - `frontend/src/components/AssetPanel.tsx`

**变更统计**:
```
frontend/src/api.ts                     |  10 +++
 frontend/src/components/AssetPanel.tsx  | 129 ++++++++++++++++++++++++++++++--
 src/vn_agent/assets/upload_store.py     |  87 +++++++++++++++++++++
 src/vn_agent/web/app.py                 |  37 +++++++++
 tests/test_assets/test_upload_delete.py | 118 +++++++++++++++++++++++++++++
 5 files changed, 373 insertions(+), 8 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-19 | 实现 - 2026-07-19 19:27

**变更文件** (40 个):
**源码变更** (4 文件):
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/cli.py`
  - `src/vn_agent/salvage.py`
  - `src/vn_agent/web/app.py`

**测试变更** (34 文件):
  - `tests/fixtures/pipeline_states/README.md`
  - `tests/fixtures/pipeline_states/_regenerate.py`
  - `tests/fixtures/pipeline_states/corrupt_vn_script/characters.json`
  - `tests/fixtures/pipeline_states/corrupt_vn_script/snapshots/scene_1_arrival.json`
  - `tests/fixtures/pipeline_states/corrupt_vn_script/snapshots/scene_2_meeting.json`

**其他变更** (2 文件):
  - `frontend/src/api.ts`
  - `frontend/src/components/JobHistory.tsx`

**变更统计**:
```
frontend/src/api.ts                                |  26 +++
 frontend/src/components/JobHistory.tsx             |  55 ++++-
 src/vn_agent/agents/writer.py                      |  86 +++++++
 src/vn_agent/cli.py                                |  46 ++++
 src/vn_agent/salvage.py                            | 260 +++++++++++++++++++++
 src/vn_agent/web/app.py                            |  89 +++++++
 tests/fixtures/pipeline_states/README.md           |  18 ++
 tests/fixtures/pipeline_states/_regenerate.py      | 164 +++++++++++++
 .../corrupt_vn_script/characters.json              |  34 +++
 .../snapshots/scene_1_arrival.json                 |  27 +++
 .../snapshots/scene_2_meeting.json                 |  27 +++
 .../corrupt_vn_script/snapshots/scene_3_lunch.json |  27 +++
 .../snapshots/scene_4_choice.json                  |  27 +++
 .../corrupt_vn_script/snapshots/scene_5_dusk.json  |  27 +++
 .../corrupt_vn_script/vn_script.json               |   1 +
 .../pipeline_states/post_director/characters.json  |  34 +++
 .../pipeline_states/post_director/vn_script.json   | 150 ++++++++++++
 .../post_writer_complete/characters.json           |  34 +++
 .../snapshots/scene_1_arrival.json                 |  27 +++
 .../snapshots/scene_2_meeting.json                 |  27 +++
 .../snapshots/scene_3_lunch.json                   |  27 +++
 .../snapshots/scene_4_choice.json                  |  27 +++
 .../snapshots/scene_5_dusk.json                    |  27 +++
 .../post_writer_complete/vn_script.json            | 230 ++++++++++++++++++
 .../post_writer_no_flush/characters.json           |  34 +++
 .../snapshots/scene_1_arrival.json                 |  27 +++
 .../snapshots/scene_2_meeting.json                 |  27 +++
 .../snapshots/scene_3_lunch.json                   |  27 +++
 .../snapshots/scene_4_choice.json                  |  27 +++
 .../snapshots/scene_5_dusk.json                    |  27 +++
 .../post_writer_no_flush/vn_script.json            | 150 ++++++++++++
 .../post_writer_partial/characters.json            |  34 +++
 .../snapshots/scene_1_arrival.json                 |  27 +++
 .../snapshots/scene_2_meeting.json                 |  27 +++
 .../snapshots/scene_3_lunch.json                   |  27 +++
 .../snapshots/scene_4_choice.json                  |  27 +++
 .../snapshots/scene_5_dusk.json                    |  27 +++
 .../post_writer_partial/vn_script.json             | 198 ++++++++++++++++
 tests/test_assets/test_dedup.py                    |  26 ++-
 tests/test_integration/test_resume_flow.py         | 150 ++++++++++++
 40 files changed, 2342 insertions(+), 17 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-19 | 实现 - 2026-07-19 18:51

**变更文件** (9 个):
**源码变更** (2 文件):
  - `src/vn_agent/services/llm.py`
  - `src/vn_agent/web/app.py`

**测试变更** (1 文件):
  - `tests/test_services/test_llm_mock_context.py`

**其他变更** (5 文件):
  - `.claude/agents/run-analyzer.md`
  - `frontend/package-lock.json`
  - `frontend/src/components/ChatPanel.tsx`
  - `frontend/src/store.ts`
  - `frontend/src/types.ts`

**变更统计**:
```
.claude/agents/run-analyzer.md               | 147 +++++++++
 docs/v4/PRODUCT_v4.md                        |  60 ++++
 frontend/package-lock.json                   | 460 ++++++++++++++-------------
 frontend/src/components/ChatPanel.tsx        |  14 +
 frontend/src/store.ts                        |   2 +-
 frontend/src/types.ts                        |   4 +
 src/vn_agent/services/llm.py                 |  31 ++
 src/vn_agent/web/app.py                      |  27 +-
 tests/test_services/test_llm_mock_context.py | 112 +++++++
 9 files changed, 631 insertions(+), 226 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-19 | 杂项 - 2026-07-19 17:27

**变更文件** (14 个):
**其他变更** (14 文件):
  - `.gitignore`
  - `data/assets/opensource/cafe_warm.png`
  - `data/assets/opensource/forest_dawn.png`
  - `data/assets/opensource/manifest.json`
  - `data/assets/opensource/rooftop_day.png`

**变更统计**:
```
.gitignore                                        |   6 +-
 data/assets/opensource/cafe_warm.png              | Bin 0 -> 16841 bytes
 data/assets/opensource/forest_dawn.png            | Bin 0 -> 17332 bytes
 data/assets/opensource/manifest.json              | 198 +++++++++++++++++++++-
 data/assets/opensource/rooftop_day.png            | Bin 0 -> 16376 bytes
 data/assets/opensource/rooftop_night.png          | Bin 0 -> 16259 bytes
 data/assets/opensource/school_day.png             | Bin 0 -> 16732 bytes
 data/assets/opensource/school_dusk.png            | Bin 0 -> 17830 bytes
 data/assets/opensource/school_night.png           | Bin 0 -> 16556 bytes
 data/assets/opensource/shrine_cool.png            | Bin 0 -> 16546 bytes
 data/assets/opensource/student_female_neutral.png | Bin 0 -> 14338 bytes
 data/assets/opensource/student_male_neutral.png   | Bin 0 -> 14854 bytes
 data/assets/opensource/teacher_neutral.png        | Bin 0 -> 11034 bytes
 scripts/seed_opensource_library.py                | 178 +++++++++++++++++++
 14 files changed, 372 insertions(+), 10 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-19 | 实现 - 2026-07-19 17:13

**变更文件** (5 个):
**源码变更** (1 文件):
  - `src/vn_agent/assets/web_search_agent.py`

**测试变更** (2 文件):
  - `tests/test_assets/test_web_search_agent.py`
  - `tests/test_integration/test_v4_upload_flow.py`

**其他变更** (2 文件):
  - `frontend/src/api.ts`
  - `frontend/src/components/AssetPanel.tsx`

**变更统计**:
```
frontend/src/api.ts                           |  23 +-
 frontend/src/components/AssetPanel.tsx        | 192 +++++++++-
 src/vn_agent/assets/web_search_agent.py       | 483 ++++++++++++++++++++++++++
 tests/test_assets/test_web_search_agent.py    | 278 +++++++++++++++
 tests/test_integration/test_v4_upload_flow.py | 311 +++++++++++++++++
 5 files changed, 1269 insertions(+), 18 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-07-15 | 实现 - 2026-07-15 00:35

**变更文件** (30 个):
**源码变更** (16 文件):
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/scene_artist.py`
  - `src/vn_agent/agents/state.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/assets/__init__.py`
  - `src/vn_agent/assets/dedup.py`
  - `src/vn_agent/assets/library.py`
  - `src/vn_agent/assets/license_gate.py`
  - `src/vn_agent/assets/text_ingest.py`
  - `src/vn_agent/assets/upload_store.py`
  - ...及其他 6 个文件

**测试变更** (7 文件):
  - `tests/test_assets/__init__.py`
  - `tests/test_assets/test_dedup.py`
  - `tests/test_assets/test_library.py`
  - `tests/test_assets/test_license_gate.py`
  - `tests/test_assets/test_text_ingest.py`

**配置变更** (1 文件):
  - `pyproject.toml`

**其他变更** (3 文件):
  - `.gitignore`
  - `data/assets/opensource/manifest.json`
  - `uv.lock`

**变更统计**:
```
.gitignore                                |  13 +-
 data/assets/opensource/manifest.json      |  13 +
 docs/PRODUCT.md                           |  17 +-
 docs/v4/PRODUCT_v4.md                     | 452 ++++++++++++++++++++++++++++++
 docs/v4/README_v4.md                      |  61 ++++
 pyproject.toml                            |   9 +
 src/vn_agent/agents/character_designer.py |  46 ++-
 src/vn_agent/agents/scene_artist.py       |  25 ++
 src/vn_agent/agents/state.py              |   7 +
 src/vn_agent/agents/writer.py             |  29 +-
 src/vn_agent/assets/__init__.py           |  13 +
 src/vn_agent/assets/dedup.py              | 249 ++++++++++++++++
 src/vn_agent/assets/library.py            | 388 +++++++++++++++++++++++++
 src/vn_agent/assets/license_gate.py       | 166 +++++++++++
 src/vn_agent/assets/text_ingest.py        | 293 +++++++++++++++++++
 src/vn_agent/assets/upload_store.py       | 159 +++++++++++
 src/vn_agent/eval/corpus.py               |  29 +-
 src/vn_agent/eval/lore.py                 |  26 +-
 src/vn_agent/metrics/__init__.py          |   1 +
 src/vn_agent/metrics/diversity.py         | 184 ++++++++++++
 src/vn_agent/services/mock_llm.py         |  29 +-
 src/vn_agent/web/app.py                   |  75 ++++-
 tests/test_assets/__init__.py             |   0
 tests/test_assets/test_dedup.py           | 173 ++++++++++++
 tests/test_assets/test_library.py         | 214 ++++++++++++++
 tests/test_assets/test_license_gate.py    | 143 ++++++++++
 tests/test_assets/test_text_ingest.py     | 245 ++++++++++++++++
 tests/test_metrics/__init__.py            |   0
 tests/test_metrics/test_diversity.py      | 168 +++++++++++
 uv.lock                                   | 222 ++++++++++++++-
 30 files changed, 3413 insertions(+), 36 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-26 | 测试 - 2026-04-26 01:00

**变更文件** (2 个):
**测试变更** (1 文件):
  - `tests/test_scripts/test_smoke_longvn.py`

**其他变更** (1 文件):
  - `scripts/smoke_longvn.py`

**变更统计**:
```
scripts/smoke_longvn.py                 | 95 +++++++++++++++++++++++++++++++++
 tests/test_scripts/test_smoke_longvn.py | 75 ++++++++++++++++++++++++++
 2 files changed, 170 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-26 | 实现 - 2026-04-26 00:57

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/services/llm.py`

**测试变更** (1 文件):
  - `tests/test_services/test_llm.py`

**变更统计**:
```
src/vn_agent/services/llm.py    |  42 +++++++++---
 tests/test_services/test_llm.py | 146 ++++++++++++++++++++++++++++++++++++++--
 2 files changed, 175 insertions(+), 13 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-26 | 实现 - 2026-04-26 00:51

**变更文件** (4 个):
**源码变更** (3 文件):
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/services/llm.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py    |  11 ++++
 src/vn_agent/config.py           |  16 ++++++
 src/vn_agent/services/llm.py     |  62 ++++++++++++++++++---
 tests/test_agents/test_writer.py | 114 +++++++++++++++++++++++++++++++++++++++
 4 files changed, 195 insertions(+), 8 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-26 | 实现 - 2026-04-26 00:32

**变更文件** (3 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/schema/script.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_director.py`

**变更统计**:
```
src/vn_agent/agents/director.py    | 20 +++++++++++-
 src/vn_agent/schema/script.py      | 20 ++++++++++++
 tests/test_agents/test_director.py | 63 ++++++++++++++++++++++++++++++++++++--
 3 files changed, 100 insertions(+), 3 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-25 | 实现 - 2026-04-25 23:05

**变更文件** (5 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/schema/script.py`

**测试变更** (3 文件):
  - `tests/test_agents/test_director.py`
  - `tests/test_integration/test_pipeline.py`
  - `tests/test_services/test_llm.py`

**变更统计**:
```
src/vn_agent/agents/director.py         | 395 ++++++++++++++---------------
 src/vn_agent/schema/script.py           |  86 +++++++
 tests/test_agents/test_director.py      | 436 ++++++++++++++++++++++++++++++++
 tests/test_integration/test_pipeline.py |  17 ++
 tests/test_services/test_llm.py         | 159 ++++++++++++
 5 files changed, 887 insertions(+), 206 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 23:33

**变更文件** (4 个):
**源码变更** (3 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/structure_reviewer.py`
  - `src/vn_agent/agents/writer.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_graph_routing.py`

**变更统计**:
```
src/vn_agent/agents/director.py           |   9 +-
 src/vn_agent/agents/structure_reviewer.py |  54 +++++-
 src/vn_agent/agents/writer.py             |  16 +-
 tests/test_agents/test_graph_routing.py   | 301 ++++++++++++++++++++++++++++++
 4 files changed, 367 insertions(+), 13 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 22:47

**变更文件** (5 个):
**源码变更** (4 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/graph.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/config.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_graph_routing.py`

**变更统计**:
```
src/vn_agent/agents/director.py         | 280 +++++++++++++++++++++++++++++++-
 src/vn_agent/agents/graph.py            |  73 ++++++++-
 src/vn_agent/agents/writer.py           |   9 +-
 src/vn_agent/config.py                  |   7 +
 tests/test_agents/test_graph_routing.py | 206 +++++++++++++++++++++++
 5 files changed, 568 insertions(+), 7 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 22:20

**变更文件** (5 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/state.py`
  - `src/vn_agent/agents/structure_reviewer.py`

**测试变更** (2 文件):
  - `tests/test_agents/test_narrative_graph.py`
  - `tests/test_agents/test_structure_reviewer.py`

**其他变更** (1 文件):
  - `scripts/smoke_longvn.py`

**变更统计**:
```
scripts/smoke_longvn.py                      |  16 +-
 src/vn_agent/agents/state.py                 |  19 +-
 src/vn_agent/agents/structure_reviewer.py    | 479 +++++++++++++++++++--------
 tests/test_agents/test_narrative_graph.py    |  44 ++-
 tests/test_agents/test_structure_reviewer.py | 392 ++++++++++++++++++++++
 5 files changed, 789 insertions(+), 161 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 21:44

**变更文件** (3 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/routing.py`
  - `src/vn_agent/schema/script.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_routing.py`

**变更统计**:
```
src/vn_agent/agents/routing.py    | 126 ++++++++++++++++++++++++
 src/vn_agent/schema/script.py     |  63 ++++++++++++
 tests/test_agents/test_routing.py | 201 ++++++++++++++++++++++++++++++++++++++
 3 files changed, 390 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 21:07

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py    | 249 +++++++++++++++++++++++++++++++--------
 tests/test_agents/test_writer.py | 182 ++++++++++++++++++++++++++++
 2 files changed, 384 insertions(+), 47 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 18:50

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/thinking.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_thinking.py`

**变更统计**:
```
src/vn_agent/agents/thinking.py    | 174 ++++++++++++++++++++++++++---
 tests/test_agents/test_thinking.py | 218 +++++++++++++++++++++++++++++++++++++
 2 files changed, 379 insertions(+), 13 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 18:30

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py    |  13 ++++-
 tests/test_agents/test_writer.py | 102 +++++++++++++++++++++++++++++++++++++++
 2 files changed, 114 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 18:10

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py    | 234 +++++++++++++++++++++++++----------
 tests/test_agents/test_writer.py | 259 +++++++++++++++++++++++++++++++++++++++
 2 files changed, 426 insertions(+), 67 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 测试 - 2026-04-24 17:19

**变更文件** (3 个):
**测试变更** (2 文件):
  - `tests/test_scripts/__init__.py`
  - `tests/test_scripts/test_smoke_longvn.py`

**其他变更** (1 文件):
  - `scripts/smoke_longvn.py`

**变更统计**:
```
scripts/smoke_longvn.py                 | 170 +++++++++++++++++++++++++++++++-
 tests/test_scripts/__init__.py          |   0
 tests/test_scripts/test_smoke_longvn.py |  79 +++++++++++++++
 3 files changed, 244 insertions(+), 5 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 16:55

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py    |  85 ++++++++++++------
 tests/test_agents/test_writer.py | 190 ++++++++++++++++++++++++++++++++++++++-
 2 files changed, 244 insertions(+), 31 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 16:19

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py    | 394 +++++++++++++++++++++++++++++--------
 tests/test_agents/test_writer.py | 413 +++++++++++++++++++++++++++++++++++++++
 2 files changed, 724 insertions(+), 83 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 12:45

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py    | 226 ++++++++++++++++++++++++---------------
 tests/test_agents/test_writer.py |  81 ++++++++++++++
 2 files changed, 223 insertions(+), 84 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 11:24

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer_orchestrator.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_writer_orchestrator.py`

**变更统计**:
```
src/vn_agent/agents/writer_orchestrator.py    | 128 ++++++++++++++++++
 tests/test_agents/test_writer_orchestrator.py | 181 ++++++++++++++++++++++++++
 2 files changed, 309 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 11:21

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/config.py`

**测试变更** (1 文件):
  - `tests/test_config.py`

**变更统计**:
```
src/vn_agent/config.py | 52 ++++++++++++++++++++++++++++++-
 tests/test_config.py   | 83 ++++++++++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 134 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 10:54

**变更文件** (3 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/thinking.py`
  - `src/vn_agent/config.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_thinking.py`

**变更统计**:
```
src/vn_agent/agents/thinking.py    | 29 +++++++++++++++++------------
 src/vn_agent/config.py             | 22 ++++++++++++++--------
 tests/test_agents/test_thinking.py | 26 +++++++++++++-------------
 3 files changed, 44 insertions(+), 33 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 02:12

**变更文件** (3 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/config.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py    |  65 +++++++++++++-
 src/vn_agent/config.py           |   9 ++
 tests/test_agents/test_writer.py | 189 +++++++++++++++++++++++++++++++++++++++
 3 files changed, 262 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 01:37

**变更文件** (6 个):
**源码变更** (3 文件):
  - `src/vn_agent/agents/thinking.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/schema/script.py`

**测试变更** (3 文件):
  - `tests/test_agents/test_thinking.py`
  - `tests/test_agents/test_writer.py`
  - `tests/test_schema.py`

**变更统计**:
```
src/vn_agent/agents/thinking.py    | 520 +++++++++++++++++++++++++++++--------
 src/vn_agent/config.py             |  11 +
 src/vn_agent/schema/script.py      |  36 ++-
 tests/test_agents/test_thinking.py | 476 +++++++++++++++++++++++----------
 tests/test_agents/test_writer.py   |  59 +++++
 tests/test_schema.py               |  28 +-
 6 files changed, 890 insertions(+), 240 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 01:07

**变更文件** (4 个):
**源码变更** (3 文件):
  - `src/vn_agent/agents/graph.py`
  - `src/vn_agent/agents/thinking.py`
  - `src/vn_agent/config.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_thinking.py`

**变更统计**:
```
src/vn_agent/agents/graph.py       |  46 +++--
 src/vn_agent/agents/thinking.py    | 345 ++++++++++++++++++++++++++++++++++---
 src/vn_agent/config.py             |  10 ++
 tests/test_agents/test_thinking.py | 282 ++++++++++++++++++++++++++++++
 4 files changed, 644 insertions(+), 39 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 00:40

**变更文件** (6 个):
**源码变更** (4 文件):
  - `src/vn_agent/agents/graph.py`
  - `src/vn_agent/agents/thinking.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/schema/script.py`

**测试变更** (2 文件):
  - `tests/test_agents/test_thinking.py`
  - `tests/test_schema.py`

**变更统计**:
```
src/vn_agent/agents/graph.py       |  40 +++--
 src/vn_agent/agents/thinking.py    | 290 ++++++++++++++++++++++++++++++
 src/vn_agent/config.py             |  12 ++
 src/vn_agent/schema/script.py      |  77 ++++++++
 tests/test_agents/test_thinking.py | 359 +++++++++++++++++++++++++++++++++++++
 tests/test_schema.py               |  73 ++++++++
 6 files changed, 841 insertions(+), 10 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-24 | 实现 - 2026-04-24 00:29

**变更文件** (7 个):
**源码变更** (3 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/schema/script.py`

**测试变更** (3 文件):
  - `tests/test_agents/test_director.py`
  - `tests/test_agents/test_writer.py`
  - `tests/test_schema.py`

**变更统计**:
```
docs/{DEV_LOG.md => archive/DEV_LOG_legacy.md} |   0
 src/vn_agent/agents/director.py                | 106 ++++++++++++-
 src/vn_agent/agents/writer.py                  |  11 ++
 src/vn_agent/schema/script.py                  | 132 ++++++++++++++++
 tests/test_agents/test_director.py             | 208 ++++++++++++++++++++++++-
 tests/test_agents/test_writer.py               |  92 +++++++++++
 tests/test_schema.py                           | 136 +++++++++++++++-
 7 files changed, 678 insertions(+), 7 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

<!-- hook 在此标题之后插入新条目；手动编辑的"待补充"注释可以留在条目内，后续发版时整理为 Added / Changed / Fixed / Removed 归类 -->
