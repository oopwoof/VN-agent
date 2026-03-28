# VN-Agent 开发日志

> 记录开发过程、技术决策、反思与学习

---

## 项目概述

**目标**: 构建多 Agent 协作的 AI 视觉小说生成器，输出可在 Ren'Py 引擎运行的完整项目。

**核心技术栈**:
- LangGraph (多 Agent 编排)
- LangChain + Claude/GPT (LLM 推理)
- Pydantic v2 (数据模型)
- Ren'Py (视觉小说引擎)

---

## 技术路线

```
用户输入主题
    ↓
[Director Agent] - 规划故事结构、场景列表、角色阵容
    ↓
[Writer Agent] - 根据场景大纲创作对白和分支
    ↓
[Reviewer Agent] - 检查一致性、分支可达性（最多3次修订循环）
    ↓
[CharacterDesigner Agent] - 为每个角色生成立绘 prompt / 图像
    ↓
[SceneArtist Agent] - 为每个背景生成场景图
    ↓
[MusicDirector Agent] - 分析场景情绪，分配 BGM
    ↓
[RenPy Compiler] - 将 JSON 编译为 .rpy 文件，组装完整项目
    ↓
输出: 可运行的 Ren'Py 项目
```

---

## 开发记录

### 2026-03-28 | 实现 - 2026-03-28 13:19

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/director.py`

**变更统计**:
```
src/vn_agent/agents/director.py | 77 ++++++++++++++++++++++++++++++++++++++---
 1 file changed, 72 insertions(+), 5 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-28 | 实现 - 2026-03-28 11:38

**变更文件** (4 个):
**源码变更** (1 文件):
  - `src/vn_agent/web/app.py`

**其他变更** (3 文件):
  - `.dockerignore`
  - `.env.docker`
  - `docker-compose.yml`

**变更统计**:
```
.dockerignore           | 1 +
 .env.docker             | 8 ++++++++
 docker-compose.yml      | 5 ++---
 src/vn_agent/web/app.py | 1 +
 4 files changed, 12 insertions(+), 3 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-28 | 配置 - 2026-03-28 10:35

**变更文件** (2 个):
**配置变更** (1 文件):
  - `pyproject.toml`

**其他变更** (1 文件):
  - `Dockerfile`

**变更统计**:
```
Dockerfile     | 8 ++++----
 pyproject.toml | 3 +++
 2 files changed, 7 insertions(+), 4 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-28 | 实现 - 2026-03-28 10:25

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/web/app.py`

**变更统计**:
```
src/vn_agent/web/app.py | 3 +--
 1 file changed, 1 insertion(+), 2 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-28 | 实现 - 2026-03-28 10:22

**变更文件** (9 个):
**源码变更** (1 文件):
  - `src/vn_agent/web/app.py`

**其他变更** (8 文件):
  - `.dockerignore`
  - `Dockerfile`
  - `docker-compose.yml`
  - `frontend/css/style.css`
  - `frontend/index.html`

**变更统计**:
```
.dockerignore           |  12 +++
 Dockerfile              |   8 +-
 docker-compose.yml      |  30 ++++++++
 frontend/css/style.css  |  81 ++++++++++++++++++++
 frontend/index.html     | 147 +++++++++++++++++++++++++++++++++++++
 frontend/js/api.js      |  85 +++++++++++++++++++++
 frontend/js/app.js      | 191 ++++++++++++++++++++++++++++++++++++++++++++++++
 frontend/js/ui.js       | 116 +++++++++++++++++++++++++++++
 src/vn_agent/web/app.py |  80 ++++++++++++++++++--
 9 files changed, 743 insertions(+), 7 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-23 | 测试 - 2026-03-23 19:54

**变更文件** (1 个):
**测试变更** (1 文件):
  - `tests/test_services/test_llm.py`

**变更统计**:
```
tests/test_services/test_llm.py | 2 --
 1 file changed, 2 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-23 | 测试 - 2026-03-23 19:51

**变更文件** (8 个):
**测试变更** (4 文件):
  - `tests/test_agents/test_callbacks.py`
  - `tests/test_services/test_llm.py`
  - `tests/test_services/test_mock_llm.py`
  - `tests/test_services/test_token_tracker.py`

**配置变更** (1 文件):
  - `pyproject.toml`

**其他变更** (2 文件):
  - `.github/workflows/ci.yml`
  - `README.md`

**变更统计**:
```
.github/workflows/ci.yml                  |  2 +-
 README.md                                 |  2 +-
 docs/RESUME.md                            |  2 +-
 pyproject.toml                            |  7 +++
 tests/test_agents/test_callbacks.py       |  6 +++
 tests/test_services/test_llm.py           | 80 +++++++++++++++++++++++++++++++
 tests/test_services/test_mock_llm.py      | 71 +++++++++++++++++++++++++++
 tests/test_services/test_token_tracker.py | 63 ++++++++++++++++++++++++
 8 files changed, 230 insertions(+), 3 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-23 | 杂项 - 2026-03-23 19:46

**变更文件** (1 个):
**其他变更** (1 文件):
  - `README.md`

**变更统计**:
```
README.md | 140 ++++++++++++++++++++++++++++++++++++++++++++++++++++----------
 1 file changed, 118 insertions(+), 22 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-23 | 实现 - 2026-03-23 19:44

**变更文件** (9 个):
**源码变更** (7 文件):
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/graph.py`
  - `src/vn_agent/agents/scene_artist.py`
  - `src/vn_agent/cli.py`
  - `src/vn_agent/eval/embedder.py`
  - `src/vn_agent/eval/retriever.py`
  - `src/vn_agent/services/llm.py`

**配置变更** (1 文件):
  - `pyproject.toml`

**其他变更** (1 文件):
  - `uv.lock`

**变更统计**:
```
pyproject.toml                            |  1 +
 src/vn_agent/agents/character_designer.py |  2 +-
 src/vn_agent/agents/graph.py              | 12 ++++++------
 src/vn_agent/agents/scene_artist.py       |  4 ++--
 src/vn_agent/cli.py                       | 10 +++++-----
 src/vn_agent/eval/embedder.py             |  8 ++++----
 src/vn_agent/eval/retriever.py            |  2 +-
 src/vn_agent/services/llm.py              | 13 +++++++------
 uv.lock                                   | 11 +++++++++++
 9 files changed, 38 insertions(+), 25 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-22 | 文档 - 2026-03-22 19:17

**变更文件** (3 个):
**其他变更** (2 文件):
  - `eval_ollama_results.json`
  - `scripts/eval_ollama.py`

**变更统计**:
```
docs/RESUME.md           |  33 ++++---
 eval_ollama_results.json | 158 +++++++++++++++++++++++++++++++++
 scripts/eval_ollama.py   | 226 +++++++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 406 insertions(+), 11 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-22 | 实现 - 2026-03-22 19:05

**变更文件** (6 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/graph.py`

**其他变更** (4 文件):
  - `eval_strategy_results.json`
  - `eval_structural_results.json`
  - `scripts/eval_real_api.py`
  - `scripts/eval_structural.py`

**变更统计**:
```
docs/RESUME.md               | 143 +++++++++++++++++++++++++++++
 eval_strategy_results.json   |  93 +++++++++++++++++++
 eval_structural_results.json |  66 ++++++++++++++
 scripts/eval_real_api.py     | 167 ++++++++++++++++++++++++++++++++++
 scripts/eval_structural.py   | 210 +++++++++++++++++++++++++++++++++++++++++++
 src/vn_agent/agents/graph.py |  69 +++++++++++---
 6 files changed, 735 insertions(+), 13 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-22 | 实现 - 2026-03-22 17:18

**变更文件** (27 个):
**源码变更** (15 文件):
  - `src/vn_agent/agents/callbacks.py`
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/music_director.py`
  - `src/vn_agent/agents/state.py`
  - `src/vn_agent/cli.py`
  - `src/vn_agent/compiler/project_builder.py`
  - `src/vn_agent/compiler/renpy_compiler.py`
  - `src/vn_agent/compiler/templates/script.rpy.j2`
  - `src/vn_agent/schema/music.py`
  - `src/vn_agent/schema/script.py`
  - ...及其他 5 个文件

**测试变更** (7 文件):
  - `tests/test_agents/test_reviewer.py`
  - `tests/test_cli/test_cli.py`
  - `tests/test_compiler/test_renpy_compiler.py`
  - `tests/test_integration/test_pipeline.py`
  - `tests/test_integration/test_real_api.py`

**配置变更** (2 文件):
  - `config/settings.yaml`
  - `pyproject.toml`

**其他变更** (1 文件):
  - `uv.lock`

**变更统计**:
```
config/settings.yaml                          |   3 +
 docs/DEV_LOG.md                               |  48 ++
 docs/PRODUCT.md                               |   7 +-
 pyproject.toml                                |   5 +-
 src/vn_agent/agents/callbacks.py              |   3 +-
 src/vn_agent/agents/director.py               |   4 +-
 src/vn_agent/agents/music_director.py         |   5 +-
 src/vn_agent/agents/state.py                  |   6 +-
 src/vn_agent/cli.py                           |  10 +-
 src/vn_agent/compiler/project_builder.py      |  39 +-
 src/vn_agent/compiler/renpy_compiler.py       |   2 +-
 src/vn_agent/compiler/templates/script.rpy.j2 |  14 +-
 src/vn_agent/schema/music.py                  |   5 +-
 src/vn_agent/schema/script.py                 |   1 +
 src/vn_agent/services/llm.py                  |  32 +-
 src/vn_agent/services/mock_llm.py             | 122 ++++-
 src/vn_agent/services/music_gen.py            |   5 +-
 src/vn_agent/services/token_tracker.py        |   2 +-
 src/vn_agent/strategies/narrative.py          |   4 +-
 tests/test_agents/test_reviewer.py            |   8 +-
 tests/test_cli/test_cli.py                    |   1 -
 tests/test_compiler/test_renpy_compiler.py    |  77 ++-
 tests/test_integration/test_pipeline.py       |  34 +-
 tests/test_integration/test_real_api.py       |   1 +
 tests/test_schema.py                          |   5 +-
 tests/test_services/test_music_gen.py         |   7 +-
 uv.lock                                       | 690 +++++++++++++++++++++++++-
 27 files changed, 1078 insertions(+), 62 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-22 | 实现 - 2026-03-22 16:42

**变更文件** (4 个):
**源码变更** (3 文件):
  - `src/vn_agent/cli.py`
  - `src/vn_agent/services/streaming.py`
  - `src/vn_agent/web/app.py`

**测试变更** (1 文件):
  - `tests/test_services/test_streaming.py`

**变更统计**:
```
src/vn_agent/cli.py                   |  63 ++++++++++++-------
 src/vn_agent/services/streaming.py    | 110 ++++++++++++++++++++++++++++++++++
 src/vn_agent/web/app.py               |  25 ++++++++
 tests/test_services/test_streaming.py |  98 ++++++++++++++++++++++++++++++
 4 files changed, 273 insertions(+), 23 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-22 | 实现 - 2026-03-22 16:36

**变更文件** (5 个):
**源码变更** (4 文件):
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/scene_artist.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/services/tools.py`

**测试变更** (1 文件):
  - `tests/test_services/test_tools.py`

**变更统计**:
```
src/vn_agent/agents/character_designer.py |  36 ++++++++--
 src/vn_agent/agents/scene_artist.py       |  58 +++++++++++----
 src/vn_agent/config.py                    |   3 +
 src/vn_agent/services/tools.py            |  89 +++++++++++++++++++++++
 tests/test_services/test_tools.py         | 115 ++++++++++++++++++++++++++++++
 5 files changed, 280 insertions(+), 21 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-22 | 实现 - 2026-03-22 16:31

**变更文件** (6 个):
**源码变更** (4 文件):
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/eval/embedder.py`
  - `src/vn_agent/eval/retriever.py`

**测试变更** (1 文件):
  - `tests/test_eval/test_embedder.py`

**配置变更** (1 文件):
  - `pyproject.toml`

**变更统计**:
```
pyproject.toml                   |   1 +
 src/vn_agent/agents/writer.py    |  56 ++++++++++++--
 src/vn_agent/config.py           |  11 ++-
 src/vn_agent/eval/embedder.py    | 163 +++++++++++++++++++++++++++++++++++++++
 src/vn_agent/eval/retriever.py   |  27 ++++++-
 tests/test_eval/test_embedder.py | 122 +++++++++++++++++++++++++++++
 6 files changed, 368 insertions(+), 12 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-22 | 实现 - 2026-03-22 16:21

**变更文件** (7 个):
**源码变更** (5 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/prompts/__init__.py`
  - `src/vn_agent/prompts/templates.py`

**测试变更** (2 文件):
  - `tests/test_prompts/__init__.py`
  - `tests/test_prompts/test_templates.py`

**变更统计**:
```
src/vn_agent/agents/director.py      |  35 ++++-------
 src/vn_agent/agents/reviewer.py      |  20 ++-----
 src/vn_agent/agents/writer.py        |  19 +-----
 src/vn_agent/prompts/__init__.py     |   1 +
 src/vn_agent/prompts/templates.py    | 111 +++++++++++++++++++++++++++++++++++
 tests/test_prompts/__init__.py       |   0
 tests/test_prompts/test_templates.py |  59 +++++++++++++++++++
 7 files changed, 191 insertions(+), 54 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-22 | 实现 - 2026-03-22 15:35

**变更文件** (3 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/web/app.py`

**测试变更** (1 文件):
  - `tests/test_web/test_app.py`

**变更统计**:
```
src/vn_agent/agents/writer.py | 70 ++++++++++++++++++++++++++++++-------------
 src/vn_agent/web/app.py       | 28 ++++++++++++++---
 tests/test_web/test_app.py    | 10 +++----
 3 files changed, 78 insertions(+), 30 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-18 | 实现 - 2026-03-18 22:19

**变更文件** (35 个):
**源码变更** (17 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/graph.py`
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/cli.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/eval/__init__.py`
  - `src/vn_agent/eval/corpus.py`
  - `src/vn_agent/eval/pipeline_eval.py`
  - `src/vn_agent/eval/retriever.py`
  - ...及其他 7 个文件

**测试变更** (11 文件):
  - `tests/test_agents/test_reviewer.py`
  - `tests/test_eval/__init__.py`
  - `tests/test_eval/test_corpus.py`
  - `tests/test_eval/test_retriever.py`
  - `tests/test_eval/test_strategy_eval.py`

**配置变更** (2 文件):
  - `config/presets/budget.yaml`
  - `pyproject.toml`

**其他变更** (3 文件):
  - `.github/workflows/ci.yml`
  - `Dockerfile`
  - `uv.lock`

**变更统计**:
```
.github/workflows/ci.yml                 |  22 ++
 Dockerfile                               |   9 +
 config/presets/budget.yaml               |  28 ++
 docs/DEV_LOG.md                          | 245 ++++++++++++++++-
 docs/PRODUCT.md                          | 195 ++++++++++---
 pyproject.toml                           |   5 +
 src/vn_agent/agents/director.py          |  39 ++-
 src/vn_agent/agents/graph.py             |  54 +++-
 src/vn_agent/agents/reviewer.py          |  67 ++++-
 src/vn_agent/agents/writer.py            |  42 +++
 src/vn_agent/cli.py                      |  97 +++++++
 src/vn_agent/config.py                   |   5 +
 src/vn_agent/eval/__init__.py            |   1 +
 src/vn_agent/eval/corpus.py              |  91 ++++++
 src/vn_agent/eval/pipeline_eval.py       | 140 ++++++++++
 src/vn_agent/eval/retriever.py           |  41 +++
 src/vn_agent/eval/strategy_eval.py       | 146 ++++++++++
 src/vn_agent/observability/__init__.py   |   4 +
 src/vn_agent/observability/tracing.py    | 116 ++++++++
 src/vn_agent/services/token_tracker.py   |  76 ++++++
 src/vn_agent/web/__init__.py             |   1 +
 src/vn_agent/web/app.py                  | 197 +++++++++++++
 src/vn_agent/web/store.py                |  98 +++++++
 tests/test_agents/test_reviewer.py       | 154 ++++++++++-
 tests/test_eval/__init__.py              |   0
 tests/test_eval/test_corpus.py           | 115 ++++++++
 tests/test_eval/test_retriever.py        |  64 +++++
 tests/test_eval/test_strategy_eval.py    | 137 ++++++++++
 tests/test_integration/test_real_api.py  |  40 +++
 tests/test_observability/__init__.py     |   0
 tests/test_observability/test_tracing.py | 118 ++++++++
 tests/test_web/__init__.py               |   0
 tests/test_web/test_app.py               | 110 ++++++++
 tests/test_web/test_store.py             |  66 +++++
 uv.lock                                  | 456 +++++++++++++++++++++++++++++++
 35 files changed, 2911 insertions(+), 68 deletions(-)
```

**技术决策与反思**:
- `DELETE /jobs/{job_id}` 端点加入 `re.fullmatch(r"[a-f0-9]{8}", job_id)` 路径参数校验，防止路径遍历攻击；job_id 由 `uuid.uuid4().hex[:8]` 生成，始终为合法 hex 格式，校验不会影响正常调用。
- 测试中原本使用 `"del1"` / `"nonexistent"` 等非 hex 字符串作为 job_id，与端点校验逻辑不一致，统一改为 `"aabbccdd"` / `"deadbeef"` 等合法格式，保持测试与生产行为一致。
- `writer.py` 导入块清理：`pydantic.BaseModel`、`pydantic.Field`、`_extract_json` 三个未使用导入遗留自重构前，本次清除；同时将局部 `import json, re` 提升至文件顶层，消除 E401/I001 lint 警告。
- `app.py` 中 `import re` 被误放在 stdlib 块与第三方块之间，移入 stdlib 块后 ruff I001 消除。
- **代码质量**: ruff 扫描 14 错误 → 0 错误；pytest 122 passed, 1 skipped，与修复前完全一致（无回归）。

---

### 2026-03-18 | Phase 7 工业化迭代（Sprint 7-11）

**目标**: 从"功能 demo"升级为**工业级原型** — 补齐评估框架、可观测性、服务基础设施、CI/CD。集成 COLX_523 语料（1,036 条标注 VN 会话）提升算法深度。

#### Sprint 7: 评估框架 + 策略分类基准

**语料导入** (`eval/corpus.py`):
- `load_corpus()` 加载 COLX_523 `final_annotations.csv`（1,036 行），自动清理 trailing whitespace
- `STRATEGY_MAP` 实现 COLX_523 7 策略 → VN-Agent 6 策略映射（Accumulate→accumulate, Uncover→reveal, Contest→contrast, Drift→weave, Other→None）
- `load_reasoning()` 加载 JSONL 推理数据（gist/strategy_reasoning/pivot_span/pacing_reasoning）

**策略分类评估器** (`eval/strategy_eval.py`):
- `evaluate_strategy_classification()` — 异步评估，支持任意 `async (text) -> str` 分类器
- `keyword_classifier()` — 规则 baseline（关键词匹配），用于 `--mock` 模式
- 输出 accuracy、per-class precision/recall/F1、confusion matrix
- `format_report()` 生成 classification_report 风格文本

**端到端质量指标** (`eval/pipeline_eval.py`):
- 结构完整性：场景可达率、分支有效性
- 对话质量：平均行数/场景、CJK 比率、语言一致性检测
- 策略覆盖：分配率、策略多样性
- 成本效率：tokens/scene

**CLI 子命令** (`cli.py`):
- `vn-agent eval strategy --corpus <path> --sample 100 [--mock]`
- `vn-agent eval summary` — 显示上次评估结果

**新增测试**: 22 个（corpus 加载/清洗/映射 9 个 + 分类器/指标 13 个）

#### Sprint 8: Few-shot 检索 + Reviewer 策略一致性

**Few-shot 检索器** (`eval/retriever.py`):
- `retrieve_examples(corpus, strategy, k=2)` — 按策略匹配，不足时从其他策略补充
- `format_examples()` — 格式化为 prompt 文本块（含 pacing 信息）

**Writer 集成** (`writer.py`):
- 当 `config.corpus_path` 非空时，在 `_write_scene()` 中自动注入 few-shot 示例
- 失败时静默降级（`logger.debug`），不影响主流程

**Reviewer 策略一致性检查** (`reviewer.py`):
- `check_strategy_consistency()` — 关键词匹配检测对话是否符合指定策略
- 非阻塞（warning only），记入 review feedback，不影响 PASS/FAIL 判定
- 8 种策略各配 6 个关键词，仅对 ≥3 行对话的场景检查

**配置项** (`config.py`):
- `corpus_path: str = ""` — 语料路径（空=禁用）
- `few_shot_k: int = 2` — 注入示例数

**新增测试**: 11 个（retriever 7 个 + reviewer strategy consistency 4 个）

#### Sprint 9: 可观测性 + 结构化日志

**TraceContext + Span** (`observability/tracing.py`):
- 模块级单例模式（同 TokenTracker）: `get_trace()`, `reset_trace()`
- `TraceContext.span(name)` → `SpanContext` 上下文管理器，自动记录耗时
- `SpanContext.set_attribute()` 附加 token 用量等元数据
- `trace.summary()` 输出人可读的 trace 表格
- `trace.save(output_dir)` 持久化为 `trace.json`

**Graph 集成** (`graph.py`):
- `_make_traced_node(name, func)` 包装器：span 内执行 agent，自动记录 input/output tokens
- 所有 6 个 agent node 均自动追踪

**CLI 集成** (`cli.py`):
- 生成开始时 `reset_trace()`，完成后输出 trace summary + 保存 `trace.json`

**新增测试**: 15 个（Span 计算/序列化 3 个 + SpanContext 2 个 + TraceContext 7 个 + 模块单例 2 个 + JSON 持久化 1 个）

#### Sprint 10: 服务基础设施增强

**SQLite JobStore** (`web/store.py`):
- 替换内存 dict，进程重启后任务不丢失
- CRUD: `create()`, `get()`, `update_status()`, `list_recent()`, `delete()`
- JSON 序列化 config/errors 字段，UTC 时间戳

**Web API 升级** (`web/app.py`):
- 新增 `GET /jobs` — 列出最近任务（分页 limit 参数）
- 新增 `DELETE /jobs/{job_id}` — 清理任务 + 输出目录
- `asyncio.Semaphore` 并发控制（默认 max=3）
- 环境变量配置: `VN_AGENT_DB_PATH`, `VN_AGENT_MAX_CONCURRENT`, `VN_AGENT_OUTPUT_DIR`
- Pydantic `Field` 请求验证（theme 1-500 字符，max_scenes 1-50，num_characters 1-10）

**新增测试**: 18 个（store CRUD 9 个 + FastAPI 端点 9 个）

#### Sprint 11: CI/CD + 可靠性约束

**GitHub Actions CI** (`.github/workflows/ci.yml`):
- 触发: push/PR to main
- 步骤: `uv sync → ruff check → mypy → pytest --cov-fail-under=70`

**Dockerfile**:
- `python:3.11-slim` 基础镜像，uv 安装，暴露 8000 端口

**Schema 验证 + LLM repair** (`director.py`):
- `_build_from_plan()` 失败时自动调用 `_attempt_repair()`
- 将 Pydantic 错误信息反馈给 LLM，尝试一次修复
- 修复失败则抛出原始错误

**Writer 输出验证** (`writer.py`):
- 每条 DialogueLine 通过 `model_validate()` 验证

**依赖**: `pytest-cov>=5.0` 加入 dev 组

**变更文件**:

| Sprint | 新增文件 | 修改文件 |
|--------|---------|---------|
| 7 | `eval/__init__.py`, `corpus.py`, `strategy_eval.py`, `pipeline_eval.py`, `tests/test_eval/` | `cli.py` |
| 8 | `eval/retriever.py`, `tests/test_eval/test_retriever.py` | `writer.py`, `reviewer.py`, `config.py` |
| 9 | `observability/__init__.py`, `tracing.py`, `tests/test_observability/` | `graph.py`, `cli.py` |
| 10 | `web/store.py`, `tests/test_web/` | `web/app.py` |
| 11 | `.github/workflows/ci.yml`, `Dockerfile` | `director.py`, `writer.py`, `pyproject.toml` |

**测试结果**: 122 passed, 1 deselected (real API test)

**技术学习**:
- SQLite `check_same_thread=False` 在 FastAPI async 环境中必需，因为请求可能在不同线程处理
- `time.monotonic()` 在 Windows 上分辨率有时不足 10ms，CI 定时测试应用 `>=` 而非 `>`
- Pydantic `model_validate()` 可作为轻量 schema 校验网，在 LLM 输出解析后加一层防御
- `asyncio.Semaphore` 是 Web API 限制并发生成的最简方案，无需引入 Celery/Redis

---

### 2026-03-18 | Phase 6 迭代体验开发（5 个 Sprint）

**目标**: 消除阻断性 bug，增强 Ren'Py 视觉表现力，支持中文，追踪成本，提供 Web API。

#### Sprint 1: 管线可靠性

**Reviewer PASS 判断修复** (`reviewer.py:178`):
- 旧逻辑: `"PASS" in content.upper() and len(content.strip()) < 20` — 字符数阈值太严
- 新逻辑: 首行前缀匹配 + 检测是否有结构化反馈（`\n-`, `\n*`, `\n1.`）
- `"PASS - the story is coherent"` 现在正确判为 PASS
- `"PASS\n- pacing is off"` 正确判为 FAIL（有具体问题需修订）

**Director 分支校验** (`director.py:191`):
- `_merge_outline_details()` 末尾新增 `valid_ids` 过滤
- step2 LLM 返回不存在的 scene_id 时静默清除，不再导致 Reviewer 结构检查失败

**选择性重试** (`llm.py:20`):
- `retry_if_exception_type(Exception)` 改为 `retry_if_exception_type(_RETRIABLE)`
- `_RETRIABLE` 仅包含: `TimeoutError`, `ConnectionError`, `APIConnectionError`, `RateLimitError`, `InternalServerError`
- 认证错误、模型不存在等立即抛出，不浪费 3 次重试

**新增测试**: 5 个 Reviewer PASS 判断测试 + 1 个 Director 分支校验测试

#### Sprint 2: Ren'Py 视觉体验

**表情切换** (`script.rpy.j2`):
- 用 `namespace(map={})` + `update()` 在 Jinja2 循环内跟踪每角色当前表情
- 表情变化时插入 `show char_id emotion`，不变化时不重复指令
- 解决了 `DialogueLine.emotion` 字段完全被忽略的问题

**场景转场**:
- 首场景 `scene bg with fade`，后续 `scene bg with dissolve`
- Ren'Py 表现从突变切换改为平滑过渡

**角色位置编排**:
- 1 人: `at center`
- 2 人: `at left`, `at right`
- 3+ 人: `at left`, `at center`, `at right`（取模循环）

**新增测试**: 3 个编译器测试（表情切换、转场、角色位置）

#### Sprint 3: Writer 鲁棒性 + 中文支持

**中文感知 Writer** (`writer.py`):
- `re.search(r'[\u4e00-\u9fff]', script.description)` 检测 CJK 字符
- 检测到时自动追加: `IMPORTANT: Write ALL dialogue text in Chinese (简体中文). Keep character_id as English identifiers.`

**对话行数约束**:
- `len(dialogue) < min_dialogue_lines` → 填充占位行
- `len(dialogue) > max_dialogue_lines` → 截断

**中文 mock fixture** (`mock_llm.py`):
- "校园恋爱" 主题: 3 场景（初次相遇/午后对话/樱花下的约定），2 角色（小雪/小明）
- `_dispatch()` 根据 user_prompt 中 CJK 字符自动路由到中文 fixture
- 新增集成测试 `test_chinese_theme_pipeline` 验证中文输出

#### Sprint 4: 成本监控

**TokenTracker** (`token_tracker.py`):
- 模块级单例 `tracker`，每次 `_log_stop_reason()` 自动累加
- `summary()` 输出总 token 数、按模型分类、估算成本（基于 _COST_PER_M 字典）
- CLI 生成完成后自动输出

**reviewer_skip_llm** (`config.py`, `reviewer.py`):
- 新配置项 `generation.reviewer_skip_llm: false`
- 为 `true` 时跳过 LLM 质检，结构检查通过即 PASS，省一次 API 调用

**Budget preset** (`config/presets/budget.yaml`):
- 全部用 Haiku，max_scenes=4，reviewer_skip_llm=true，max_revision_rounds=1
- 预估成本 ~$0.01-0.02/次

**真实 API 烟雾测试** (`test_real_api.py`):
- `@pytest.mark.slow` + `skipif(not ANTHROPIC_API_KEY)`
- 3 场景、2 角色、text_only 的最小真实 API 测试

#### Sprint 5: 打磨 + Web API

**OGG 占位音频** (`project_builder.py`):
- 内联 44 字节 WAV 格式静音文件（8000Hz mono PCM，0 采样）
- Ren'Py/SDL_mixer 按文件头检测格式，.ogg 扩展名不影响播放
- 无需 ffmpeg/pydub 依赖

**FastAPI 后端** (`web/app.py`):
- `POST /generate` → 接收 `{theme, max_scenes, text_only}`，返回 `{job_id}`
- `GET /status/{job_id}` → 返回 `{status, progress, errors}`
- `GET /download/{job_id}` → 返回输出目录的 zip 文件
- `asyncio.create_task` 异步执行 pipeline，内存 dict 存 job 状态

**pyproject.toml**:
- `[project.optional-dependencies] web = ["fastapi>=0.110", "uvicorn[standard]>=0.30"]`
- `markers = ["slow"]` 注册自定义 pytest mark

**变更文件**:

| Sprint | 修改文件 | 新增文件 |
|--------|---------|---------|
| 1 | `reviewer.py`, `director.py`, `llm.py`, `test_reviewer.py` | — |
| 2 | `script.rpy.j2`, `test_renpy_compiler.py` | — |
| 3 | `writer.py`, `mock_llm.py`, `test_pipeline.py` | — |
| 4 | `llm.py`, `reviewer.py`, `config.py`, `cli.py`, `settings.yaml` | `token_tracker.py`, `presets/budget.yaml`, `test_real_api.py` |
| 5 | `project_builder.py`, `pyproject.toml` | `web/__init__.py`, `web/app.py` |

**测试结果**: 56 passed, 1 skipped (real API test)

**技术学习**:
- Jinja2 `namespace()` 是唯一绕过 for 循环作用域限制的方法；`set` 在循环内对外部变量的赋值会被丢弃
- `dict.update()` 在 Jinja2 namespace 中仍然可以原地修改字典，因为 Python dict 是引用类型
- SDL_mixer 按文件头（RIFF/OggS）检测格式，不依赖扩展名，所以 .ogg 文件可以包含 WAV 内容
- `tenacity` 的 `retry_if_exception_type` 接受元组，可以在模块级构建异常类型集合

---

### 2026-03-18 | 开发日总结

**今天完成的核心工作**（8 个 commit）：

#### 1. 成本优化：按 Agent 分配模型
- 默认从 claude-opus-4-6 切到 claude-sonnet-4-6，约节省 80% 成本
- Director/Writer 用 Sonnet（JSON 复杂度高），Reviewer/CharacterDesigner/SceneArtist 用 Haiku
- `get_llm()` 新增 model 参数，lru_cache 按 (provider, model, temperature, max_tokens, api_key, base_url) 缓存

#### 2. JSON 截断问题的完整诊断与修复
**问题根源**（通过 stop_reason 日志确认）：
- 如果 stop_reason=max_tokens → LLM 输出被截断，需要调大 max_tokens 或缩小请求
- 如果 stop_reason=end_turn + 解析失败 → 模型返回格式异常，是解析 bug

**_salvage_truncated_json 重写**：
- 旧逻辑：逐字符向后剥离，中文字符（不在 ASCII 集合）会被无限剥离到空字符串
- 新逻辑双策略：
  - Strategy 1：从末尾向前找 `}` 或 `]`，关闭剩余括号，尝试解析
  - Strategy 2：前向扫描找最后一个根级逗号（深度=1 的 `,`），截断后关闭根对象
  - 全程用字符串感知扫描（跟踪 in_string/escape 状态），对 Unicode 安全

**Director 两步走**：
- Step1：只生成场景大纲（id/title/description/background_id/characters_present/strategy）
- Step2：补全导航（branches/next_scene_id）和音乐（music_mood）
- 单次响应体积降低约 50-60%，大幅降低截断概率

#### 3. 本地/免费模型支持
- 新增 `llm_base_url` + `llm_api_key` 配置字段
- 任意 OpenAI 协议兼容端点（Ollama/LM Studio/Groq/OpenRouter）直接对接
- `config/presets/` 提供开箱即用配置

#### 4. --mock 开发模式
- `vn-agent generate "主题" --mock --text-only` → 零 API 调用，~1 秒，输出真实 Ren'Py 项目
- fixture："The Last Lighthouse"（4 场景，2 角色，2 分支点，真实对话）
- `_dispatch()` 按 caller tag + system prompt 关键词路由

#### 5. 占位 PNG 自动生成
- build_project 为所有缺失的背景/立绘写入最小透明 PNG（67 字节，纯内联，无需 Pillow）
- Ren'Py 可正常运行，不报 missing file 错误

**技术学习**：
- `unittest.mock.patch()` 可以在运行时替换已 import 的函数引用，CLI 层用这个实现 mock 模式非常干净
- Ollama 在 Windows 上的安装需要 GUI 交互，`/S` 静默安装不生效
- RTX 3070 Laptop 8GB 在其他任务占用时可用 VRAM/RAM 不足以加载 7B 模型，需用 1.5B 或先释放资源

**变更文件** (2 文件):
  - `src/vn_agent/compiler/project_builder.py`
  - `docs/PRODUCT.md` + `docs/DEV_LOG.md`

---

### 2026-03-18 | 实现 - 2026-03-18 01:35

**变更文件** (7 个):
**源码变更** (4 文件):
  - `src/vn_agent/cli.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/services/llm.py`
  - `src/vn_agent/services/mock_llm.py`

**配置变更** (3 文件):
  - `config/presets/groq_free.yaml`
  - `config/presets/ollama_local.yaml`
  - `config/settings.yaml`

**变更统计**:
```
config/presets/groq_free.yaml     |  25 +++++
 config/presets/ollama_local.yaml  |  25 +++++
 config/settings.yaml              |   9 ++
 src/vn_agent/cli.py               |  40 +++++++-
 src/vn_agent/config.py            |   6 ++
 src/vn_agent/services/llm.py      |  38 +++++--
 src/vn_agent/services/mock_llm.py | 209 ++++++++++++++++++++++++++++++++++++++
 7 files changed, 341 insertions(+), 11 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-18 | 实现 - 2026-03-18 01:25

**变更文件** (7 个):
**源码变更** (6 文件):
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/agents/scene_artist.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/services/llm.py`

**测试变更** (1 文件):
  - `tests/test_integration/test_pipeline.py`

**变更统计**:
```
src/vn_agent/agents/character_designer.py |   2 +-
 src/vn_agent/agents/director.py           | 187 ++++++++++++++++++++----------
 src/vn_agent/agents/reviewer.py           |   2 +-
 src/vn_agent/agents/scene_artist.py       |   2 +-
 src/vn_agent/agents/writer.py             |   2 +-
 src/vn_agent/services/llm.py              |  30 ++++-
 tests/test_integration/test_pipeline.py   |  59 ++++++----
 7 files changed, 193 insertions(+), 91 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-18 | 实现 - 2026-03-18 01:21

**变更文件** (2 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/writer.py`

**变更统计**:
```
src/vn_agent/agents/director.py | 147 ++++++++++++++++++++++++++++------------
 src/vn_agent/agents/writer.py   |   8 ++-
 2 files changed, 111 insertions(+), 44 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-18 | 实现 - 2026-03-18 01:10

**变更文件** (10 个):
**源码变更** (8 文件):
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/agents/scene_artist.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/cli.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/services/llm.py`

**测试变更** (1 文件):
  - `tests/test_integration/test_pipeline.py`

**配置变更** (1 文件):
  - `config/settings.yaml`

**变更统计**:
```
config/settings.yaml                      | 12 ++++-
 src/vn_agent/agents/character_designer.py |  4 +-
 src/vn_agent/agents/director.py           | 87 ++++++++++++++++++++++++++-----
 src/vn_agent/agents/reviewer.py           |  3 +-
 src/vn_agent/agents/scene_artist.py       |  4 +-
 src/vn_agent/agents/writer.py             |  2 +-
 src/vn_agent/cli.py                       |  3 +-
 src/vn_agent/config.py                    | 12 ++++-
 src/vn_agent/services/llm.py              | 57 +++++++++++++-------
 tests/test_integration/test_pipeline.py   |  2 +-
 10 files changed, 143 insertions(+), 43 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-18 | 实现 - 2026-03-18 00:52

**变更文件** (3 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/cli.py`

**其他变更** (1 文件):
  - `.claude/settings.local.json`

**变更统计**:
```
.claude/settings.local.json     |  5 ++++-
 src/vn_agent/agents/director.py | 40 +++++++++++++++++++++++-----------------
 src/vn_agent/cli.py             | 13 ++++++++++++-
 3 files changed, 39 insertions(+), 19 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-18 | 实现 - 2026-03-18 00:30

**变更文件** (7 个):
**源码变更** (6 文件):
  - `src/vn_agent/agents/callbacks.py`
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/scene_artist.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/cli.py`

**测试变更** (1 文件):
  - `tests/test_cli/test_cli.py`

**变更统计**:
```
src/vn_agent/agents/callbacks.py          | 11 ++++
 src/vn_agent/agents/character_designer.py | 55 ++++++++++++++----
 src/vn_agent/agents/director.py           | 30 +++++++---
 src/vn_agent/agents/scene_artist.py       | 21 +++++--
 src/vn_agent/agents/writer.py             | 40 +++++++++++--
 src/vn_agent/cli.py                       | 97 ++++++++++++++++++++++++++++++-
 tests/test_cli/test_cli.py                | 55 ++++++++++++++++++
 7 files changed, 277 insertions(+), 32 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-18 | 实现 - 2026-03-18 00:26

**变更文件** (5 个):
**源码变更** (3 文件):
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/scene_artist.py`
  - `src/vn_agent/cli.py`

**测试变更** (2 文件):
  - `tests/test_cli/__init__.py`
  - `tests/test_cli/test_cli.py`

**变更统计**:
```
src/vn_agent/agents/character_designer.py |  20 ++-
 src/vn_agent/agents/scene_artist.py       |  40 +++++-
 src/vn_agent/cli.py                       | 103 ++++++++++++++
 tests/test_cli/__init__.py                |   0
 tests/test_cli/test_cli.py                | 221 ++++++++++++++++++++++++++++++
 5 files changed, 373 insertions(+), 11 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-18 | 实现 - 2026-03-18 00:22

**变更文件** (14 个):
**源码变更** (7 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/graph.py`
  - `src/vn_agent/agents/state.py`
  - `src/vn_agent/cli.py`
  - `src/vn_agent/compiler/renpy_compiler.py`
  - `src/vn_agent/compiler/templates/init.rpy.j2`
  - `src/vn_agent/compiler/templates/script.rpy.j2`

**测试变更** (3 文件):
  - `tests/test_compiler/test_renpy_compiler.py`
  - `tests/test_integration/__init__.py`
  - `tests/test_integration/test_pipeline.py`

**配置变更** (1 文件):
  - `pyproject.toml`

**其他变更** (3 文件):
  - `.claude/settings.local.json`
  - `.githooks/pre-commit`
  - `uv.lock`

**变更统计**:
```
.claude/settings.local.json                   |   32 +
 .githooks/pre-commit                          |   10 +-
 pyproject.toml                                |    4 +-
 src/vn_agent/agents/director.py               |    7 +-
 src/vn_agent/agents/graph.py                  |   27 +-
 src/vn_agent/agents/state.py                  |   17 +-
 src/vn_agent/cli.py                           |   50 +-
 src/vn_agent/compiler/renpy_compiler.py       |    6 +
 src/vn_agent/compiler/templates/init.rpy.j2   |    9 +
 src/vn_agent/compiler/templates/script.rpy.j2 |   12 +-
 tests/test_compiler/test_renpy_compiler.py    |    6 +
 tests/test_integration/__init__.py            |    0
 tests/test_integration/test_pipeline.py       |  177 +++
 uv.lock                                       | 1770 +++++++++++++++++++++++++
 14 files changed, 2096 insertions(+), 31 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-18 | 实现 - 2026-03-18 00:02

**变更文件** (46 个):
**源码变更** (28 文件):
  - `src/vn_agent/__init__.py`
  - `src/vn_agent/agents/__init__.py`
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/graph.py`
  - `src/vn_agent/agents/music_director.py`
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/agents/scene_artist.py`
  - `src/vn_agent/agents/state.py`
  - `src/vn_agent/agents/writer.py`
  - ...及其他 18 个文件

**测试变更** (8 文件):
  - `tests/__init__.py`
  - `tests/test_agents/__init__.py`
  - `tests/test_agents/test_reviewer.py`
  - `tests/test_compiler/__init__.py`
  - `tests/test_compiler/test_renpy_compiler.py`

**配置变更** (4 文件):
  - `config/music_library.yaml`
  - `config/settings.yaml`
  - `examples/sample_input.yaml`
  - `pyproject.toml`

**其他变更** (4 文件):
  - `.env.example`
  - `.githooks/pre-commit`
  - `README.md`
  - `scripts/update_docs.py`

**变更统计**:
```
.env.example                                      |   4 +
 .githooks/pre-commit                              |  24 ++
 README.md                                         |  46 +++-
 config/music_library.yaml                         |  78 ++++++
 config/settings.yaml                              |  24 ++
 docs/DEV_LOG.md                                   | 300 ++++++++++++++++++++++
 docs/PRODUCT.md                                   | 140 ++++++++++
 examples/sample_input.yaml                        |   6 +
 pyproject.toml                                    |  48 ++++
 scripts/update_docs.py                            | 181 +++++++++++++
 src/vn_agent/__init__.py                          |   3 +
 src/vn_agent/agents/__init__.py                   |   0
 src/vn_agent/agents/character_designer.py         | 125 +++++++++
 src/vn_agent/agents/director.py                   | 196 ++++++++++++++
 src/vn_agent/agents/graph.py                      |  74 ++++++
 src/vn_agent/agents/music_director.py             |  68 +++++
 src/vn_agent/agents/reviewer.py                   | 180 +++++++++++++
 src/vn_agent/agents/scene_artist.py               |  83 ++++++
 src/vn_agent/agents/state.py                      |  54 ++++
 src/vn_agent/agents/writer.py                     | 137 ++++++++++
 src/vn_agent/cli.py                               | 137 ++++++++++
 src/vn_agent/compiler/__init__.py                 |   0
 src/vn_agent/compiler/project_builder.py          |  64 +++++
 src/vn_agent/compiler/renpy_compiler.py           |  64 +++++
 src/vn_agent/compiler/templates/characters.rpy.j2 |   6 +
 src/vn_agent/compiler/templates/gui.rpy.j2        |   7 +
 src/vn_agent/compiler/templates/script.rpy.j2     |  41 +++
 src/vn_agent/config.py                            |  74 ++++++
 src/vn_agent/schema/__init__.py                   |   0
 src/vn_agent/schema/character.py                  |  27 ++
 src/vn_agent/schema/music.py                      |  25 ++
 src/vn_agent/schema/script.py                     |  40 +++
 src/vn_agent/services/__init__.py                 |   0
 src/vn_agent/services/image_gen.py                |  78 ++++++
 src/vn_agent/services/llm.py                      | 106 ++++++++
 src/vn_agent/services/music_gen.py                |  67 +++++
 src/vn_agent/strategies/__init__.py               |   0
 src/vn_agent/strategies/narrative.py              | 131 ++++++++++
 tests/__init__.py                                 |   0
 tests/test_agents/__init__.py                     |   0
 tests/test_agents/test_reviewer.py                | 110 ++++++++
 tests/test_compiler/__init__.py                   |   0
 tests/test_compiler/test_renpy_compiler.py        | 123 +++++++++
 tests/test_schema.py                              | 128 +++++++++
 tests/test_services/__init__.py                   |   0
 tests/test_services/test_music_gen.py             |  56 ++++
 46 files changed, 3054 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-18 | 实现 - 2026-03-18 00:01

**变更文件** (46 个):
**源码变更** (28 文件):
  - `src/vn_agent/__init__.py`
  - `src/vn_agent/agents/__init__.py`
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/graph.py`
  - `src/vn_agent/agents/music_director.py`
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/agents/scene_artist.py`
  - `src/vn_agent/agents/state.py`
  - `src/vn_agent/agents/writer.py`
  - ...及其他 18 个文件

**测试变更** (8 文件):
  - `tests/__init__.py`
  - `tests/test_agents/__init__.py`
  - `tests/test_agents/test_reviewer.py`
  - `tests/test_compiler/__init__.py`
  - `tests/test_compiler/test_renpy_compiler.py`

**配置变更** (4 文件):
  - `config/music_library.yaml`
  - `config/settings.yaml`
  - `examples/sample_input.yaml`
  - `pyproject.toml`

**其他变更** (4 文件):
  - `.env.example`
  - `.githooks/pre-commit`
  - `README.md`
  - `scripts/update_docs.py`

**变更统计**:
```
.env.example                                      |   4 +
 .githooks/pre-commit                              |  24 +++
 README.md                                         |  46 ++++-
 config/music_library.yaml                         |  78 ++++++++
 config/settings.yaml                              |  24 +++
 docs/DEV_LOG.md                                   | 210 ++++++++++++++++++++++
 docs/PRODUCT.md                                   | 140 +++++++++++++++
 examples/sample_input.yaml                        |   6 +
 pyproject.toml                                    |  48 +++++
 scripts/update_docs.py                            | 181 +++++++++++++++++++
 src/vn_agent/__init__.py                          |   3 +
 src/vn_agent/agents/__init__.py                   |   0
 src/vn_agent/agents/character_designer.py         | 125 +++++++++++++
 src/vn_agent/agents/director.py                   | 196 ++++++++++++++++++++
 src/vn_agent/agents/graph.py                      |  74 ++++++++
 src/vn_agent/agents/music_director.py             |  68 +++++++
 src/vn_agent/agents/reviewer.py                   | 180 +++++++++++++++++++
 src/vn_agent/agents/scene_artist.py               |  83 +++++++++
 src/vn_agent/agents/state.py                      |  54 ++++++
 src/vn_agent/agents/writer.py                     | 137 ++++++++++++++
 src/vn_agent/cli.py                               | 137 ++++++++++++++
 src/vn_agent/compiler/__init__.py                 |   0
 src/vn_agent/compiler/project_builder.py          |  64 +++++++
 src/vn_agent/compiler/renpy_compiler.py           |  64 +++++++
 src/vn_agent/compiler/templates/characters.rpy.j2 |   6 +
 src/vn_agent/compiler/templates/gui.rpy.j2        |   7 +
 src/vn_agent/compiler/templates/script.rpy.j2     |  41 +++++
 src/vn_agent/config.py                            |  74 ++++++++
 src/vn_agent/schema/__init__.py                   |   0
 src/vn_agent/schema/character.py                  |  27 +++
 src/vn_agent/schema/music.py                      |  25 +++
 src/vn_agent/schema/script.py                     |  40 +++++
 src/vn_agent/services/__init__.py                 |   0
 src/vn_agent/services/image_gen.py                |  78 ++++++++
 src/vn_agent/services/llm.py                      | 106 +++++++++++
 src/vn_agent/services/music_gen.py                |  67 +++++++
 src/vn_agent/strategies/__init__.py               |   0
 src/vn_agent/strategies/narrative.py              | 131 ++++++++++++++
 tests/__init__.py                                 |   0
 tests/test_agents/__init__.py                     |   0
 tests/test_agents/test_reviewer.py                | 110 ++++++++++++
 tests/test_compiler/__init__.py                   |   0
 tests/test_compiler/test_renpy_compiler.py        | 123 +++++++++++++
 tests/test_schema.py                              | 128 +++++++++++++
 tests/test_services/__init__.py                   |   0
 tests/test_services/test_music_gen.py             |  56 ++++++
 46 files changed, 2964 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-17 | 实现 - 2026-03-17 23:59

**变更文件** (46 个):
**源码变更** (28 文件):
  - `src/vn_agent/__init__.py`
  - `src/vn_agent/agents/__init__.py`
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/graph.py`
  - `src/vn_agent/agents/music_director.py`
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/agents/scene_artist.py`
  - `src/vn_agent/agents/state.py`
  - `src/vn_agent/agents/writer.py`
  - ...及其他 18 个文件

**测试变更** (8 文件):
  - `tests/__init__.py`
  - `tests/test_agents/__init__.py`
  - `tests/test_agents/test_reviewer.py`
  - `tests/test_compiler/__init__.py`
  - `tests/test_compiler/test_renpy_compiler.py`

**配置变更** (4 文件):
  - `config/music_library.yaml`
  - `config/settings.yaml`
  - `examples/sample_input.yaml`
  - `pyproject.toml`

**其他变更** (4 文件):
  - `.env.example`
  - `.githooks/pre-commit`
  - `README.md`
  - `scripts/update_docs.py`

**变更统计**:
```
.env.example                                      |   4 +
 .githooks/pre-commit                              |  24 +++
 README.md                                         |  46 ++++-
 config/music_library.yaml                         |  78 +++++++++
 config/settings.yaml                              |  24 +++
 docs/DEV_LOG.md                                   | 120 +++++++++++++
 docs/PRODUCT.md                                   | 140 ++++++++++++++++
 examples/sample_input.yaml                        |   6 +
 pyproject.toml                                    |  48 ++++++
 scripts/update_docs.py                            | 181 ++++++++++++++++++++
 src/vn_agent/__init__.py                          |   3 +
 src/vn_agent/agents/__init__.py                   |   0
 src/vn_agent/agents/character_designer.py         | 125 ++++++++++++++
 src/vn_agent/agents/director.py                   | 196 ++++++++++++++++++++++
 src/vn_agent/agents/graph.py                      |  74 ++++++++
 src/vn_agent/agents/music_director.py             |  68 ++++++++
 src/vn_agent/agents/reviewer.py                   | 180 ++++++++++++++++++++
 src/vn_agent/agents/scene_artist.py               |  83 +++++++++
 src/vn_agent/agents/state.py                      |  54 ++++++
 src/vn_agent/agents/writer.py                     | 137 +++++++++++++++
 src/vn_agent/cli.py                               | 137 +++++++++++++++
 src/vn_agent/compiler/__init__.py                 |   0
 src/vn_agent/compiler/project_builder.py          |  64 +++++++
 src/vn_agent/compiler/renpy_compiler.py           |  64 +++++++
 src/vn_agent/compiler/templates/characters.rpy.j2 |   6 +
 src/vn_agent/compiler/templates/gui.rpy.j2        |   7 +
 src/vn_agent/compiler/templates/script.rpy.j2     |  41 +++++
 src/vn_agent/config.py                            |  74 ++++++++
 src/vn_agent/schema/__init__.py                   |   0
 src/vn_agent/schema/character.py                  |  27 +++
 src/vn_agent/schema/music.py                      |  25 +++
 src/vn_agent/schema/script.py                     |  40 +++++
 src/vn_agent/services/__init__.py                 |   0
 src/vn_agent/services/image_gen.py                |  78 +++++++++
 src/vn_agent/services/llm.py                      | 106 ++++++++++++
 src/vn_agent/services/music_gen.py                |  67 ++++++++
 src/vn_agent/strategies/__init__.py               |   0
 src/vn_agent/strategies/narrative.py              | 131 +++++++++++++++
 tests/__init__.py                                 |   0
 tests/test_agents/__init__.py                     |   0
 tests/test_agents/test_reviewer.py                | 110 ++++++++++++
 tests/test_compiler/__init__.py                   |   0
 tests/test_compiler/test_renpy_compiler.py        | 123 ++++++++++++++
 tests/test_schema.py                              | 128 ++++++++++++++
 tests/test_services/__init__.py                   |   0
 tests/test_services/test_music_gen.py             |  56 +++++++
 46 files changed, 2874 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-17 | 文档 - 2026-03-17 23:26

**变更文件** (5 个):
**其他变更** (3 文件):
  - `.githooks/pre-commit`
  - `README.md`
  - `scripts/update_docs.py`

**变更统计**:
```
.githooks/pre-commit   |  24 +++++++
 README.md              |  46 ++++++++++++-
 docs/DEV_LOG.md        |  98 +++++++++++++++++++++++++++
 docs/PRODUCT.md        | 140 +++++++++++++++++++++++++++++++++++++++
 scripts/update_docs.py | 175 +++++++++++++++++++++++++++++++++++++++++++++++++
 5 files changed, 482 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-22 | Phase 8: AI 深度补全（Sprint 12-15）

**状态**: ✅ 完成

**目标**: 补全简历核心 AI 技术点 — CoT 推理、Embedding RAG、Tool Calling、流式输出

**Sprint 12: 结构化推理 Prompt**
- 新增 `src/vn_agent/prompts/templates.py` — 集中管理 prompt 模板
- Director: 4 步 chain-of-thought 推理框架（主题分析→角色动态→场景流→策略选择）
- Reviewer: 5 维度评分 rubric（叙事连贯/角色声音/情感弧/分支质量/节奏）
- `strip_thinking()`: 正则移除 `<thinking>` 推理块，防止污染 JSON 解析
- Writer: 写作前情感规划引导

**Sprint 13: Embedding RAG 检索**
- 新增 `src/vn_agent/eval/embedder.py` — `EmbeddingIndex` 类
- sentence-transformers `all-MiniLM-L6-v2` (22M) 编码 + FAISS `IndexFlatIP` 余弦相似度
- 语义查询: `"{scene.description} | strategy: {strategy}"` 兼顾语义和策略
- Graceful degradation: 无 FAISS → numpy 暴力搜索; 无 sentence-transformers → 标签检索
- `retrieve_examples_semantic()` 替代原 `retrieve_examples()` 作为 few-shot 检索

**Sprint 14: LLM Tool Calling**
- 新增 `src/vn_agent/services/tools.py` — Pydantic schema 作为 function definition
- `BackgroundPrompt` / `VisualProfileResult` 两个工具 schema
- `ainvoke_with_tools()`: LangChain `.bind_tools()` → extract `tool_calls[0]` → validate
- scene_artist + character_designer 迁移到 tool calling，失败时 fallback 到 regex

**Sprint 15: 流式 LLM 输出**
- 新增 `src/vn_agent/services/streaming.py`
- `astream_llm()`: 逐 token 流式 + callback + token usage 归因
- `astream_sse()`: SSE 格式 `data: {"token": "..."}\n\n` 事件流
- Web API: `POST /generate/stream` SSE 端点（Director outline 实时预览）
- CLI: `--stream` flag 支持

**CI 修复**:
- `ruff check` line-length 调整为 120，mock_llm.py per-file-ignore E501
- `str(Enum)` → `StrEnum` (UP042)
- 移除未使用变量 (F841)

**测试**: 122 → 140 tests（+18），全部通过

**技术决策**:
- 所有新特性通过 feature flag 控制（`use_semantic_retrieval`, `use_tool_calling`）
- RAG 依赖为可选组 `[rag]`，不影响基础安装
- Tool Calling 双路径: tool call 优先，失败回退 regex JSON 提取

---

### 2026-03-17 | 项目初始化

**状态**: 开始实施

**完成事项**:
- [ ] 确定项目架构和技术栈
- [ ] 创建开发计划

**技术决策**:
- 使用 LangGraph `StateGraph` 而非简单链式调用，支持条件边（Reviewer 循环）
- Pydantic v2 作为所有 Agent 的数据契约，保证类型安全
- BGM 支持两种策略：曲库匹配（默认）和 Suno API 生成（可选）
- Ren'Py 输出格式支持 `play music fadein` / `stop music fadeout`

**待解决问题**:
- [ ] 角色立绘一致性保证机制（跨场景同一角色风格统一）
- [ ] 长剧本的 LLM token 限制处理
- [ ] 图像生成失败的优雅降级

---

## 技术学习记录

### LangGraph 状态管理
- `TypedDict` 定义共享状态，所有节点读写同一个 state dict
- 条件边通过 `add_conditional_edges` 实现分支逻辑
- `Send` API 支持并行节点执行（Phase 4 资产并行化用到）

### Ren'Py 脚本规范
- `label` 定义场景入口
- `menu` 定义分支选择
- `jump` 实现场景跳转
- `play music "path.ogg" fadein 1.0` 播放 BGM
- `stop music fadeout 1.0` 停止 BGM

---

## 反思与改进

_（每次 commit 后更新）_

---

## 已知问题 & TODO

| 优先级 | 问题 | 状态 |
|--------|------|------|
| P0 | Phase 1-5 核心管线 | ✅ 完成 |
| P0 | Phase 6 迭代体验（5 Sprint） | ✅ 完成（56 测试） |
| P0 | Phase 7 工业化（Sprint 7-11） | ✅ 完成（122 测试） |
| P0 | Phase 8 AI深度补全（Sprint 12-15） | ✅ 完成（140 测试） |
| P1 | Web 前端（React/Vue） | 待开始 |
| P1 | 真实 BGM 文件替换占位 WAV | 待开始 |
| P2 | Ollama 本地模型验证 | 待开始 |
| P2 | Suno API 音乐生成 | 待 API 公开 |

---

_最后更新: 2026-03-28_