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

### 2026-03-18 | 实现 - 2026-03-18 01:42

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/compiler/project_builder.py`

**变更统计**:
```
src/vn_agent/compiler/project_builder.py | 45 ++++++++++++++++++++++++++++++++
 1 file changed, 45 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

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
| P0 | 实现 Phase 1 基础骨架 | 进行中 |
| P1 | 实现 Phase 2 编译器 | 待开始 |
| P2 | 实现 Phase 3 多模态资产 | 待开始 |

---

_最后更新: 2026-03-18_