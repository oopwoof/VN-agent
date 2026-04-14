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

### 2026-04-14 | 实现 - 2026-04-14 09:38

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/cli.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_character_designer.py`

**变更统计**:
```
src/vn_agent/cli.py                          | 220 ++++++++++++++++++++++++++-
 tests/test_agents/test_character_designer.py |  11 ++
 2 files changed, 230 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 09:27

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/character_designer.py`

**变更统计**:
```
src/vn_agent/agents/character_designer.py | 23 +++++++++++++----------
 1 file changed, 13 insertions(+), 10 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 09:24

**变更文件** (6 个):
**源码变更** (4 文件):
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/graph.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/services/bg_remove.py`

**配置变更** (1 文件):
  - `pyproject.toml`

**其他变更** (1 文件):
  - `uv.lock`

**变更统计**:
```
pyproject.toml                            |   5 +
 src/vn_agent/agents/character_designer.py |  56 +++-
 src/vn_agent/agents/graph.py              |  31 ++
 src/vn_agent/config.py                    |   9 +
 src/vn_agent/services/bg_remove.py        |  97 +++++++
 uv.lock                                   | 466 +++++++++++++++++++++++++++++-
 6 files changed, 659 insertions(+), 5 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 09:01

**变更文件** (2 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/local_regen.py`
  - `src/vn_agent/cli.py`

**变更统计**:
```
src/vn_agent/agents/local_regen.py | 172 +++++++++++++++++++++++++++++++++++++
 src/vn_agent/cli.py                |  48 +++++++++++
 2 files changed, 220 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 06:09

**变更文件** (3 个):
**源码变更** (1 文件):
  - `src/vn_agent/services/image_gen.py`

**配置变更** (1 文件):
  - `config/settings.yaml`

**其他变更** (1 文件):
  - `scripts/check_gemini_access.py`

**变更统计**:
```
config/settings.yaml               | 16 +++++++++++-----
 scripts/check_gemini_access.py     |  6 ++++--
 src/vn_agent/services/image_gen.py | 24 +++++++++++++++++++++---
 3 files changed, 36 insertions(+), 10 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 06:00

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/config.py`

**变更统计**:
```
src/vn_agent/config.py | 13 +++++++++----
 1 file changed, 9 insertions(+), 4 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | Phase 13: 长篇记忆 + Nano Banana + Gemini-review fixes + 首次 sweep 数据

用户睡觉我自动推了一轮。核心产出：

**Gemini 3 Pro 二审意见（核心工程改善）** — commit `b40de7e`
- [BLOCKER] `state_orchestrator` time-travel: 修为**按场景时间线模拟** state，每个 reading scene 收到它开始时刻的有效状态（不再是全局 initial 快照）
- [BLOCKER] Writer revision loop state corruption: 每次 `run_writer` 入口**从 `script.world_variables.initial_value` 重新 seed**，revision 不继承上次 end-of-story state
- [MAJOR] `enum_values=[]` silent-accept: 现在 enum 变量必须有非空 `enum_values`
- [MAJOR] 图像 fallback 区分 retryable：400/401/403/404 直接 raise（同 prompt 在其他 provider 也会失败，烧钱），429/5xx/timeout 才降链
- [MAJOR] 图像 byte validation：PNG/JPEG/GIF/WebP magic 检测，写盘前 `_write_validated` 校验，防 0-byte 文件上 Ren'Py
- [MAJOR] Director step1 prompt 示例补齐 `enum_values`，避免 LLM 漏发导致下游空 enum
- 8 类错误-分类 + 6 类 byte-validation 测试（13 新）

**Sprint 10-1 Nano Banana 图像 provider** — commit `b8d80be`
- `google_gemini` image_provider 分支：REST 调用 `gemini-2.5-flash-image-preview` `:generateContent`
- Fallback chain: `google_gemini → openai_gpt_image → openai → stability`（text）/ `google_gemini → openai_gpt_image → stability`（ref）
- `scripts/check_gemini_access.py`：免费文本探活 + 付费图像探活，告诉用户是 key 问题还是 billing 问题
- 10 新 tests 覆盖 provider capabilities + dispatcher + Gemini response shape（camelCase/snake_case）

**Sprint 10-2 RAG lore pivot** — commit `5593bf1`
- 外部批评"literary 模式 RAG 是花架子"的响应：同套 FAISS + BM25 基础设施，从**检索对话 few-shot**转为**检索世界观实体**（character backgrounds, unique locations, world_variables, premise）
- 两种 writer_mode 都注入 lore（事实不污染风格）
- 15 新 tests。每 run +~250 input tokens（~$0.008，噪声级）

**Sprint 11 长篇记忆四件套** — commits `d6facbd`, `992bd49`, `9cb9477`, `40c5f0e`
- **11-1 Recursive summarization**（Haiku ≤100 词/场景，gated ≥15 场景）
- **11-2 Character Bible**：per-run 结构化角色参考，放 system prompt → Sprint 8-4 prompt caching 自动 amortize（~70% cache win on Bible tokens at 6 scenes）
- **11-3 Persona fingerprint audit**（纯 Python）：Director 声明 `speech_fingerprint`，Reviewer 长文本跑 token-freq 匹配，flag voice drift 非阻塞警告。13 新 tests
- **11-4 Per-scene snapshots**：`{scene_id, dialogue, world_state_after, summary}` 写到 `snapshots/<id>.json`，Sprint 12-4 local regen 基础

**GPT-4o cross-judge 自动路由** — commit `2bc02d7`
- 8-5 sweep 数据暴露：secondary judge 其实全部 404（`model="gpt-4o"` 被路由到 Anthropic API）
- `get_llm` 加 `_infer_provider_from_model`：`claude-*` → anthropic，`gpt-*/o1-*/o3-*` → openai，auto override pipeline default
- **意味着本次 sweep 的 "cross-model" 数据实际是 Sonnet-self-judged**，下次 sweep 才会有真正的 Pearson r

**Sprint 8-5 实际 sweep 数据** — `demo_output/sweep/sweep_results.md`
- 8 cells × 2 themes = $5.33 actual（预估 ~$2.80，多轮 revision loop 在 literary_lighthouse 吃了 $1.78）
- **Aggregate mean**:
  - literary: **4.17** (n=12)
  - action: 3.92 (n=12)
  - baseline_self_refine: 3.45 (n=11)
  - baseline_single: 3.25 (n=12)
- **Multi-agent 证明值钱**：literary vs baseline_single +28%
- literary **两个主题都赢**（dragon 4.5, lighthouse 3.83）— 物理 prompt 胜过动作 RAG 即使在动作主题

**Tests 303 → 329**（13 新 Gemini fixes + 10 Gemini provider + 15 lore + 13 persona audit + 其他测试更新）

**遗留给早上的**：
- 可以考虑把 `writer_mode` 默认切到 `literary`（sweep 数据支持），但这是默认行为变更，保留给用户决策
- Sprint 12（流式 + 双模式）和 Sprint 13（多用户并发）是下一批大改动
- GPT-4o cross-judge 实际数据还没有 — 下次 sweep 会填补

---

### 2026-04-14 | 实现 - 2026-04-14 05:41

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py | 53 +++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 53 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 05:27

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/services/llm.py`

**变更统计**:
```
src/vn_agent/services/llm.py | 41 +++++++++++++++++++++++++++++++++++++----
 1 file changed, 37 insertions(+), 4 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 02:26

**变更文件** (5 个):
**源码变更** (4 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/persona_audit.py`
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/schema/character.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_persona_audit.py`

**变更统计**:
```
src/vn_agent/agents/director.py         |   7 +-
 src/vn_agent/agents/persona_audit.py    | 147 ++++++++++++++++++++++++++++++++
 src/vn_agent/agents/reviewer.py         |  10 +++
 src/vn_agent/schema/character.py        |  11 +++
 tests/test_agents/test_persona_audit.py | 124 +++++++++++++++++++++++++++
 5 files changed, 298 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 02:23

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py | 48 ++++++++++++++++++++++++++++++++++++++++++-
 1 file changed, 47 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 02:21

**变更文件** (6 个):
**源码变更** (6 文件):
  - `src/vn_agent/agents/summarizer.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/cli.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/schema/script.py`
  - `src/vn_agent/services/mock_llm.py`

**变更统计**:
```
src/vn_agent/agents/summarizer.py | 96 +++++++++++++++++++++++++++++++++++++++
 src/vn_agent/agents/writer.py     | 52 ++++++++++++++++++++-
 src/vn_agent/cli.py               |  1 +
 src/vn_agent/config.py            | 10 ++++
 src/vn_agent/schema/script.py     | 11 +++++
 src/vn_agent/services/mock_llm.py | 11 +++++
 6 files changed, 180 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 02:17

**变更文件** (6 个):
**源码变更** (5 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/agents/state_orchestrator.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/services/image_gen.py`

**测试变更** (1 文件):
  - `tests/test_services/test_image_gen.py`

**变更统计**:
```
src/vn_agent/agents/director.py           |   7 ++
 src/vn_agent/agents/reviewer.py           |  42 +++++-----
 src/vn_agent/agents/state_orchestrator.py |  59 ++++++++++----
 src/vn_agent/agents/writer.py             |  24 ++++--
 src/vn_agent/services/image_gen.py        |  96 +++++++++++++++++++----
 tests/test_services/test_image_gen.py     | 125 +++++++++++++++++++++++++++++-
 6 files changed, 289 insertions(+), 64 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 01:57

**变更文件** (4 个):
**源码变更** (3 文件):
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/eval/lore.py`

**测试变更** (1 文件):
  - `tests/test_eval/test_lore.py`

**变更统计**:
```
src/vn_agent/agents/writer.py |  55 +++++++++++-
 src/vn_agent/config.py        |   6 ++
 src/vn_agent/eval/lore.py     | 191 ++++++++++++++++++++++++++++++++++++++++++
 tests/test_eval/test_lore.py  | 151 +++++++++++++++++++++++++++++++++
 4 files changed, 402 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 00:56

**变更文件** (4 个):
**源码变更** (2 文件):
  - `src/vn_agent/config.py`
  - `src/vn_agent/services/image_gen.py`

**测试变更** (1 文件):
  - `tests/test_services/test_image_gen.py`

**其他变更** (1 文件):
  - `scripts/check_gemini_access.py`

**变更统计**:
```
scripts/check_gemini_access.py        | 120 +++++++++++++++++
 src/vn_agent/config.py                |   5 +
 src/vn_agent/services/image_gen.py    | 242 ++++++++++++++++++++++++++++++----
 tests/test_services/test_image_gen.py |  87 +++++++++++-
 4 files changed, 422 insertions(+), 32 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 测试 - 2026-04-14 00:31

**变更文件** (1 个):
**测试变更** (1 文件):
  - `tests/test_prompts/test_templates.py`

**变更统计**:
```
tests/test_prompts/test_templates.py | 8 +++++---
 1 file changed, 5 insertions(+), 3 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 00:24

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/reviewer.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_reviewer.py`

**变更统计**:
```
src/vn_agent/agents/reviewer.py    |  67 +++++++++++++++++++--
 tests/test_agents/test_reviewer.py | 115 +++++++++++++++++++++++++++++++++++++
 2 files changed, 177 insertions(+), 5 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 00:17

**变更文件** (5 个):
**源码变更** (5 文件):
  - `src/vn_agent/agents/graph.py`
  - `src/vn_agent/agents/state_orchestrator.py`
  - `src/vn_agent/cli.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/services/mock_llm.py`

**变更统计**:
```
src/vn_agent/agents/graph.py              |  16 ++--
 src/vn_agent/agents/state_orchestrator.py | 130 ++++++++++++++++++++++++++++++
 src/vn_agent/cli.py                       |   1 +
 src/vn_agent/config.py                    |   4 +
 src/vn_agent/services/mock_llm.py         |   9 +++
 5 files changed, 155 insertions(+), 5 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 00:11

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/reviewer.py`

**变更统计**:
```
src/vn_agent/agents/reviewer.py | 49 +++++++++++++++++++++++++++++++++++++++++
 1 file changed, 49 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 00:10

**变更文件** (2 个):
**源码变更** (2 文件):
  - `src/vn_agent/compiler/templates/init.rpy.j2`
  - `src/vn_agent/compiler/templates/script.rpy.j2`

**变更统计**:
```
src/vn_agent/compiler/templates/init.rpy.j2   | 15 ++++++++++++++
 src/vn_agent/compiler/templates/script.rpy.j2 | 28 +++++++++++++++++++++++++++
 2 files changed, 43 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 00:03

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py | 54 +++++++++++++++++++++++++++++++++++++++++--
 1 file changed, 52 insertions(+), 2 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | 实现 - 2026-04-14 00:01

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/director.py`

**变更统计**:
```
src/vn_agent/agents/director.py | 101 ++++++++++++++++++++++++++++++++++++----
 1 file changed, 93 insertions(+), 8 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 23:58

**变更文件** (3 个):
**源码变更** (3 文件):
  - `src/vn_agent/agents/state.py`
  - `src/vn_agent/schema/character.py`
  - `src/vn_agent/schema/script.py`

**变更统计**:
```
src/vn_agent/agents/state.py     | 12 +++++++-
 src/vn_agent/schema/character.py | 11 ++++++++
 src/vn_agent/schema/script.py    | 60 ++++++++++++++++++++++++++++++++++++++++
 3 files changed, 82 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-14 | Phase 12: Symbolic World State（Sprint 9 完整 7 子项）

**触发点**：外部批评的第 4 硬伤 — 无 symbolic state，跨场景靠长上下文硬记，伸缩性崩。Phase 12 给 VN-Agent 补上"游戏引擎"那一半。

**9-1 schema 基础**：新 `WorldVariable`（name / type {bool,int,string,enum} / initial / enum_values）+ `Scene.state_reads/writes` + `BranchOption.requires` + `VNScript.world_variables` + `CharacterProfile.immutability_score`。AgentState 加 `world_state + state_constraints`。

**9-2 Director 产出**：step1 prompt 要求声明 world_variables（明示"只列真要用的"），step2 prompt 每场景填 state_reads/writes/branch.requires。`run_director` 返 `world_state` seed。

**9-3 Writer 消费**：prompt 新增按需可选的 state 块。设计决策：**Writer 不产出 state_writes** — Director 在大纲时声明，Writer 只写符合的对白。权责干净。

**9-4 Ren'Py 编译**：`default var = initial` + `$ var = value` + menu 生成 Ren'Py 原生 `"choice" if has_key and not cursed:` 守护。

**9-5+9-7 Reviewer 强制**：`_mechanical_check` 扩 state I/O 有效性 + 类型/enum 合约。bool 拒 int、int 拒 bool（抓误声明）、enum 必须在 enum_values 里。这层"加法式"回滚策略含义：Writer 能自由演化值（3→7），但不能破坏类型契约。

**9-6 State Orchestrator (Haiku)**：插在 structure_reviewer 和 writer 之间，读 world_state → 产叙事约束文本。Writer 不用脑内算 "affinity=6/10 意味着什么说话方式"，Haiku 提前翻译。~$0.002/run，**Sonnet 不花在该 Haiku 干的活上**。

**架构收益**：
- VN-Agent 从"扩写器"变"引擎"：跨场景符号状态，不靠长上下文记忆
- 长篇伸缩性解决：state 是固定大小 dict，100 场景的状态仍 < 10KB
- 创作者可手编 world_variables.initial_value 做"平行世界"（Sprint 12-4 local regen 准备好）
- Sprint 8-5 sweep 触发后跑的数据带完整 state 机制

**真实指标**：Tests 279 → 287（8 新 9-7 + 1 旧维度 test 更新）

---

### 2026-04-13 | Phase 11: 双通道 Writer + 评估严谨性（Sprint 7 + 8）

**触发点**：Phase 10 首次真实 demo 跑通后，外部架构评审（GPT/Gemini + 资深审查者）指四个硬伤：对齐诅咒 / 自审 echo chamber / 无 baseline / 无 symbolic state。Phase 11 是对前三个的系统化响应，state 推 Phase 12。

**按批评拆解**：

**1. 对齐诅咒 → Sprint 7-1**
- `writer_mode: Literal["literary", "action"]`。literary 默认跳过 raw few-shot 注入，靠物理 taxonomy 描述驱动。RAG 检索仍跑（审计），仅注入被 mode 控制
- 物理化 Writer system prompt：每种策略加 vector/threshold/energy 描述

**2. 自审 echo chamber → Sprint 8-1 + 8-2**
- 8-1：GPT-4o secondary judge，Pearson r 汇报，优雅降级
- 8-2：零 LLM 规则化 metrics 6 个策略各自信号（rupture=最大情感 jump × position weighting，accumulate=能量 Pearson r，erode=句长下降+sentiment+省略号，uncover=专名揭示率，contest=speaker×emotion alternation，drift=decisive 信号反面）。三方裁判对齐才可信

**3. 无 baseline → Sprint 8-3**
- `baseline_single` 一次 Sonnet call 产完整 script，`baseline_self_refine` draft+self-critique+revise。sweep 4×2=8 cells 含 baseline
- 预算 ~$2.80 + judge ~$0.10

**4. 成本优化 → Sprint 8-4**
- Anthropic prompt caching：system prompt ≥1500 chars 标 `cache_control=ephemeral`，5-min TTL。Writer 6-18 次同 prompt 共享缓存，预估 `-$0.07-0.25/run`

**Sprint 7 架构演进子项**：
- 7-2 选择性长上下文 `writer_context_window`
- 7-3 Reviewer + judge 升 Sonnet
- 7-5 两层 Reviewer（Sonnet structure + Haiku dialogue 初版）
- 7-5b Dialogue 回 Sonnet + Python `_mechanical_check` 前置门 + Reviewer prompt 专注 craft + StructureReviewer audit 4→7 条（捕获 LLM 策略枚举幻觉）

**真实运行里程碑**：
- Sprint 7-4 单 cell 跑（literary × lighthouse）531s $1.17 actual vs $0.52 estimate
  **暴露 Director LLM repair 破坏性 bug**（改 narrative_strategy, 吞 characters）
  修为纯 Python `_degrade_invalid_branches`（`c5b76bd`）
- Sprint 8 完成，264 → 279 tests pass（rule metrics 15 新）

**下一步**：Sprint 8-5 用户 --confirm 触发 8-cell sweep 实测。数据出来后决定 Sprint 9（world state）启停优先级。

---

### 2026-04-13 | 实现 - 2026-04-13 23:33

**变更文件** (2 个):
**源码变更** (2 文件):
  - `src/vn_agent/config.py`
  - `src/vn_agent/services/llm.py`

**变更统计**:
```
src/vn_agent/config.py       |  8 ++++++
 src/vn_agent/services/llm.py | 65 ++++++++++++++++++++++++++++++++++++--------
 2 files changed, 61 insertions(+), 12 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 23:31

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/baseline_runners.py`

**其他变更** (1 文件):
  - `scripts/run_sweep.py`

**变更统计**:
```
scripts/run_sweep.py                    | 186 +++++++++++++++++-----
 src/vn_agent/agents/baseline_runners.py | 269 ++++++++++++++++++++++++++++++++
 2 files changed, 412 insertions(+), 43 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 23:26

**变更文件** (3 个):
**源码变更** (1 文件):
  - `src/vn_agent/eval/strategy_metrics.py`

**测试变更** (1 文件):
  - `tests/test_eval/test_strategy_metrics.py`

**其他变更** (1 文件):
  - `scripts/eval_strategy_adherence.py`

**变更统计**:
```
scripts/eval_strategy_adherence.py       |  11 +-
 src/vn_agent/eval/strategy_metrics.py    | 311 +++++++++++++++++++++++++++++++
 tests/test_eval/test_strategy_metrics.py | 179 ++++++++++++++++++
 3 files changed, 500 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 23:21

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/config.py`

**其他变更** (1 文件):
  - `scripts/eval_strategy_adherence.py`

**变更统计**:
```
scripts/eval_strategy_adherence.py | 143 +++++++++++++++++++++++++++++++------
 src/vn_agent/config.py             |   5 ++
 2 files changed, 126 insertions(+), 22 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 22:45

**变更文件** (5 个):
**源码变更** (4 文件):
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/agents/structure_reviewer.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/prompts/templates.py`

**配置变更** (1 文件):
  - `config/settings.yaml`

**变更统计**:
```
config/settings.yaml                      |  10 ++-
 src/vn_agent/agents/reviewer.py           | 104 ++++++++++++++++++++++++++++--
 src/vn_agent/agents/structure_reviewer.py |  26 ++++++++
 src/vn_agent/config.py                    |  14 ++--
 src/vn_agent/prompts/templates.py         | 102 ++++++++++++++++++-----------
 5 files changed, 207 insertions(+), 49 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 22:17

**变更文件** (8 个):
**源码变更** (7 文件):
  - `src/vn_agent/agents/graph.py`
  - `src/vn_agent/agents/state.py`
  - `src/vn_agent/agents/structure_reviewer.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/cli.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/services/mock_llm.py`

**配置变更** (1 文件):
  - `config/settings.yaml`

**变更统计**:
```
config/settings.yaml                      |   9 +-
 src/vn_agent/agents/graph.py              |  24 ++-
 src/vn_agent/agents/state.py              |   8 +
 src/vn_agent/agents/structure_reviewer.py | 320 ++++++++++++++++++++++++++++++
 src/vn_agent/agents/writer.py             |  26 ++-
 src/vn_agent/cli.py                       |   1 +
 src/vn_agent/config.py                    |   5 +
 src/vn_agent/services/mock_llm.py         |  13 ++
 8 files changed, 398 insertions(+), 8 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 20:44

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/director.py`

**变更统计**:
```
src/vn_agent/agents/director.py | 34 +++++++++++-----------------------
 1 file changed, 11 insertions(+), 23 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 杂项 - 2026-04-13 18:46

**变更文件** (1 个):
**其他变更** (1 文件):
  - `scripts/run_sweep.py`

**变更统计**:
```
scripts/run_sweep.py | 262 +++++++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 262 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 18:44

**变更文件** (3 个):
**源码变更** (1 文件):
  - `src/vn_agent/services/preflight.py`

**配置变更** (1 文件):
  - `config/settings.yaml`

**其他变更** (1 文件):
  - `scripts/eval_strategy_adherence.py`

**变更统计**:
```
config/settings.yaml               | 16 ++++++++++------
 scripts/eval_strategy_adherence.py |  5 ++++-
 src/vn_agent/services/preflight.py |  4 +++-
 3 files changed, 17 insertions(+), 8 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 18:42

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py | 36 ++++++++++++++++++++++++++++++++++--
 1 file changed, 34 insertions(+), 2 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 18:41

**变更文件** (3 个):
**源码变更** (3 文件):
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/prompts/templates.py`

**变更统计**:
```
src/vn_agent/agents/writer.py     | 36 ++++++++++-----
 src/vn_agent/config.py            | 23 ++++++++++
 src/vn_agent/prompts/templates.py | 95 ++++++++++++++++++++++++++++++++-------
 3 files changed, 127 insertions(+), 27 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 杂项 - 2026-04-13 18:15

**变更文件** (1 个):
**其他变更** (1 文件):
  - `scripts/eval_strategy_adherence.py`

**变更统计**:
```
scripts/eval_strategy_adherence.py | 162 +++++++++++++++++++++++++++++++++++++
 1 file changed, 162 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 18:05

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/eval/retriever.py`

**变更统计**:
```
docs/PRODUCT.md                |  3 +++
 src/vn_agent/eval/retriever.py | 28 +++++++++++++++++++++++-----
 2 files changed, 26 insertions(+), 5 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 18:00

**变更文件** (2 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/eval/corpus.py`

**变更统计**:
```
src/vn_agent/agents/writer.py | 56 +++++++++++++++++++++++++++++++++++++++----
 src/vn_agent/eval/corpus.py   |  5 +++-
 2 files changed, 56 insertions(+), 5 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 17:45

**变更文件** (1 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py | 8 ++++++++
 1 file changed, 8 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | Phase 10: 工业级升级（Sprint 6-1 ~ 6-9c + fix）

**背景**：一面后对照面经三问（角色一致性 / 跨场景连贯 / RAG 策略），把 toy demo 提到工业级。11 个独立 commit，264 测试全绿，端到端真实 API 首次跑通。

**按问题拆解**：

1. **Q1（角色一致性）**：
   - Sprint 6-2 在 Director step1 加 `art_direction` 字段，下游所有 sprite/bg 共用风格前缀
   - Sprint 6-9b **neutral-first 策略**：先生成 neutral 立绘作视觉锚，happy/sad 用 neutral 图作 reference（openai_gpt_image `/v1/images/edits` / stability `image-to-image`）。不支持 ref 的 provider 用同一 base descriptor，保证 prompt 一致。任一情绪失败自动拷贝 neutral bytes，Ren'Py 永不断链
   - 遗留：Sprint 6-11 准备接入 Nano Banana（Gemini 2.5 Flash Image，多图 ref，$0.039/图）

2. **Q2（跨场景连贯）**：
   - Sprint 6-1 **场景过渡卡片**：Director step2 为每对相连场景输出 `entry_context`（前场结尾）+ `exit_hook`（本场铺垫）+ `emotional_arc`。Writer 独立生成每场景时天然锚定前后文。token 成本每场景 +2-3 句，远比传完整前文便宜。

3. **Q3（RAG 策略）**：
   - Sprint 6-2 **策略 pre-filter**：从 post-filter 改硬约束 + soft degradation（标注不够 k 个时 FAISS 补足，未标注作 backfill 只在降级时用）
   - Sprint 6-3 **异质语料加载器**：1,036 标注 + 265k 未标注双层融合，id/指纹去重
   - Sprint 6-4 **BM25 + weighted RRF**：FAISS=0.7 + BM25=0.3 加权，诚实标注"在 VN 对话语料上 BM25 边际收益有限"——方法论完整就够
   - **Sprint 6-fix**：跑 demo 时发现 `STRATEGY_MAP` 把 `Uncover→reveal / Contest→contrast / Drift→weave` 映射错了（语义相反，对齐 annotation guideline 后改为 identity 映射 6 个对齐标签 `accumulate/erode/rupture/uncover/contest/drift`，保留 `escalate/resolve` 作为 generation-only 额外维度）

**工程质量补丁**：
- Sprint 6-5 **Per-job Token Tracker**：`ContextVar` 替代模块级 singleton，多 job 成本隔离不污染
- Sprint 6-6 **Director 分支结构校验**：两分支 target 互斥 + 3-hop 下游独占
- Sprint 6-7 **Reviewer 分支语义校验**：Jaccard + 角色集合 + 情绪分布三维比较，> 0.8 打 cosmetic warning
- Sprint 6-8 **Writer 智能截断**：对话行数不够时用已有对白尾部作上下文重生成一次，失败才退化占位符
- Sprint 6-9a **Pre-flight**：key + 输出目录 + 成本估算 + `--ping` 探活，避免浪费 API
- **Sprint 6-fix Reviewer 阈值硬判**：之前只看 LLM 首行 PASS/FAIL 字符串，解析出来的 rubric 分数未参与判决。改为 `settings.reviewer_pass_threshold`（默认 3.5）权威，LLM 字符串做备份
- **Sprint 6-fix Writer 注入 background + Reviewer 读完整对白**：之前两个都是"成本权衡"挡箭牌——实算每场景多 ~80 tokens input、Reviewer 多 ~3500 input tokens Haiku，加起来 < 1 美分

**真实跑通里程碑**：
- 2026-04-13 16:38：首次 Anthropic Sonnet 端到端，6 场景 text-only，531s，reviewer avg 5.0/5.0，0 errors
- 产物 `The Last Ballad of Kael Ironveil` — 对白有潜台词/情绪切换/有意义分支
- Sprint 6-9a 成本估算首次校准：预估 $0.18 → 实际 $0.49（+179% 偏差）。用真实 median 重建 preflight 表，再跑误差 < 0.1%
- **发现 RAG 静默失效**：`config/settings.yaml` 里 `corpus_path: "data\final_annotations.csv"` 是双引号 YAML，`\f` 被解成 form feed，`load_corpus` 报 OSError 被 except 吞掉，Writer 全程无 few-shot。改为正斜杠后 1,036 条语料正常加载，重跑验证

**遗留 / 下一步**：
- Sprint 6-10 intent alignment（第 4 层防御）：选项文本 vs 下游场景的语义耦合，需 Haiku LLM 打分
- Sprint 6-11 Nano Banana provider 集成
- 长上下文场景时开启 265k 未标注语料做 stylistic diversity

**测试基线**：从 245 → 264 pass（Sprint 6-9b 13 新，Sprint 6-fix Reviewer 阈值 6 新）

---

### 2026-04-13 | 实现 - 2026-04-13 17:03

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/services/preflight.py`

**配置变更** (1 文件):
  - `config/settings.yaml`

**变更统计**:
```
config/settings.yaml               |  3 ++-
 src/vn_agent/services/preflight.py | 20 +++++++++++++-------
 2 files changed, 15 insertions(+), 8 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 杂项 - 2026-04-13 16:37

**变更文件** (1 个):
**其他变更** (1 文件):
  - `scripts/run_real_demo.py`

**变更统计**:
```
scripts/run_real_demo.py | 13 ++++++++++++-
 1 file changed, 12 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 16:32

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/cli.py`

**其他变更** (1 文件):
  - `scripts/run_real_demo.py`

**变更统计**:
```
scripts/run_real_demo.py | 32 ++++++++++++++++----------------
 src/vn_agent/cli.py      | 22 +++++++++++-----------
 2 files changed, 27 insertions(+), 27 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 12:20

**变更文件** (3 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/config.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_reviewer.py`

**变更统计**:
```
src/vn_agent/agents/reviewer.py    | 21 ++++++++++++++--
 src/vn_agent/config.py             |  3 +++
 tests/test_agents/test_reviewer.py | 50 ++++++++++++++++++++++++++++++++++++++
 3 files changed, 72 insertions(+), 2 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 12:09

**变更文件** (9 个):
**源码变更** (5 文件):
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/eval/corpus.py`
  - `src/vn_agent/eval/strategy_eval.py`
  - `src/vn_agent/strategies/narrative.py`

**测试变更** (4 文件):
  - `tests/test_eval/test_corpus.py`
  - `tests/test_eval/test_embedder.py`
  - `tests/test_eval/test_retriever.py`
  - `tests/test_eval/test_strategy_eval.py`

**变更统计**:
```
src/vn_agent/agents/reviewer.py       |  59 ++++++------
 src/vn_agent/agents/writer.py         |  11 ++-
 src/vn_agent/eval/corpus.py           |  14 ++-
 src/vn_agent/eval/strategy_eval.py    |  18 ++--
 src/vn_agent/strategies/narrative.py  | 163 +++++++++++++++++++++++-----------
 tests/test_eval/test_corpus.py        |   6 +-
 tests/test_eval/test_embedder.py      |   6 +-
 tests/test_eval/test_retriever.py     |   2 +-
 tests/test_eval/test_strategy_eval.py |  10 +--
 9 files changed, 188 insertions(+), 101 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 杂项 - 2026-04-13 11:12

**变更文件** (1 个):
**其他变更** (1 文件):
  - `scripts/run_real_demo.py`

**变更统计**:
```
scripts/run_real_demo.py | 241 +++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 241 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 测试 - 2026-04-13 11:04

**变更文件** (1 个):
**测试变更** (1 文件):
  - `tests/test_services/test_preflight.py`

**变更统计**:
```
tests/test_services/test_preflight.py | 6 ++++++
 1 file changed, 6 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 10:48

**变更文件** (4 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/services/image_gen.py`

**测试变更** (2 文件):
  - `tests/test_agents/test_character_designer.py`
  - `tests/test_services/test_image_gen.py`

**变更统计**:
```
src/vn_agent/agents/character_designer.py    | 125 ++++++++++++++-----
 src/vn_agent/services/image_gen.py           | 178 ++++++++++++++++++++++++---
 tests/test_agents/test_character_designer.py | 161 ++++++++++++++++++++++++
 tests/test_services/test_image_gen.py        |  90 ++++++++++++++
 4 files changed, 511 insertions(+), 43 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 10:40

**变更文件** (3 个):
**源码变更** (2 文件):
  - `src/vn_agent/cli.py`
  - `src/vn_agent/services/preflight.py`

**测试变更** (1 文件):
  - `tests/test_services/test_preflight.py`

**变更统计**:
```
src/vn_agent/cli.py                   |  99 ++++++------
 src/vn_agent/services/preflight.py    | 277 ++++++++++++++++++++++++++++++++++
 tests/test_services/test_preflight.py | 143 ++++++++++++++++++
 3 files changed, 469 insertions(+), 50 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 10:31

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/writer.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_writer.py`

**变更统计**:
```
src/vn_agent/agents/writer.py    |  76 +++++++++++++++++++++++++--
 tests/test_agents/test_writer.py | 109 +++++++++++++++++++++++++++++++++++++++
 2 files changed, 180 insertions(+), 5 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 10:28

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/reviewer.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_reviewer.py`

**变更统计**:
```
src/vn_agent/agents/reviewer.py    | 112 +++++++++++++++++++++++++++++++-
 tests/test_agents/test_reviewer.py | 128 +++++++++++++++++++++++++++++++++++++
 2 files changed, 239 insertions(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 10:23

**变更文件** (2 个):
**源码变更** (1 文件):
  - `src/vn_agent/agents/director.py`

**测试变更** (1 文件):
  - `tests/test_agents/test_director.py`

**变更统计**:
```
src/vn_agent/agents/director.py    | 130 ++++++++++++++++++++++++++
 tests/test_agents/test_director.py | 186 +++++++++++++++++++++++++++++++++++++
 2 files changed, 316 insertions(+)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 09:13

**变更文件** (5 个):
**源码变更** (4 文件):
  - `src/vn_agent/services/llm.py`
  - `src/vn_agent/services/streaming.py`
  - `src/vn_agent/services/token_tracker.py`
  - `src/vn_agent/web/app.py`

**测试变更** (1 文件):
  - `tests/test_services/test_token_tracker.py`

**变更统计**:
```
src/vn_agent/services/llm.py              |  4 +-
 src/vn_agent/services/streaming.py        |  4 +-
 src/vn_agent/services/token_tracker.py    | 54 +++++++++++++++++--
 src/vn_agent/web/app.py                   | 88 ++++++++++++++++++++++++++++---
 tests/test_services/test_token_tracker.py | 65 ++++++++++++++++++++++-
 5 files changed, 201 insertions(+), 14 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 08:23

**变更文件** (5 个):
**源码变更** (2 文件):
  - `src/vn_agent/eval/embedder.py`
  - `src/vn_agent/eval/fusion.py`

**测试变更** (1 文件):
  - `tests/test_eval/test_fusion.py`

**配置变更** (1 文件):
  - `pyproject.toml`

**其他变更** (1 文件):
  - `uv.lock`

**变更统计**:
```
pyproject.toml                 |   1 +
 src/vn_agent/eval/embedder.py  | 151 +++++++++++++++++++++++++++++------------
 src/vn_agent/eval/fusion.py    |  70 +++++++++++++++++++
 tests/test_eval/test_fusion.py |  60 ++++++++++++++++
 uv.lock                        |  14 ++++
 5 files changed, 252 insertions(+), 44 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 08:12

**变更文件** (4 个):
**源码变更** (3 文件):
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/eval/corpus_loader.py`

**测试变更** (1 文件):
  - `tests/test_eval/test_corpus_loader.py`

**变更统计**:
```
src/vn_agent/agents/writer.py         |   5 +-
 src/vn_agent/config.py                |   1 +
 src/vn_agent/eval/corpus_loader.py    | 146 ++++++++++++++++++++++++++++++++++
 tests/test_eval/test_corpus_loader.py | 126 +++++++++++++++++++++++++++++
 4 files changed, 276 insertions(+), 2 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 00:40

**变更文件** (5 个):
**源码变更** (4 文件):
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/config.py`
  - `src/vn_agent/eval/embedder.py`
  - `src/vn_agent/eval/retriever.py`

**测试变更** (1 文件):
  - `tests/test_eval/test_embedder.py`

**变更统计**:
```
src/vn_agent/agents/writer.py    |  1 +
 src/vn_agent/config.py           |  1 +
 src/vn_agent/eval/embedder.py    | 66 +++++++++++++++++++++++++++++++++++++---
 src/vn_agent/eval/retriever.py   | 12 ++++++--
 tests/test_eval/test_embedder.py | 52 +++++++++++++++++++++++++++++++
 5 files changed, 125 insertions(+), 7 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-13 | 实现 - 2026-04-13 00:27

**变更文件** (4 个):
**源码变更** (4 文件):
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/writer.py`
  - `src/vn_agent/schema/script.py`
  - `src/vn_agent/services/mock_llm.py`

**变更统计**:
```
src/vn_agent/agents/director.py   | 29 +++++++++++++++++++++++------
 src/vn_agent/agents/writer.py     | 14 +++++++++++++-
 src/vn_agent/schema/script.py     | 13 +++++++++++++
 src/vn_agent/services/mock_llm.py | 35 ++++++++++++++++++++++++++++-------
 4 files changed, 77 insertions(+), 14 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-04-01 | 实现 - 2026-04-01 21:32

**变更文件** (4 个):
**源码变更** (4 文件):
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/scene_artist.py`
  - `src/vn_agent/agents/state.py`

**变更统计**:
```
src/vn_agent/agents/character_designer.py | 14 +++++++++-----
 src/vn_agent/agents/director.py           |  7 +++++++
 src/vn_agent/agents/scene_artist.py       | 12 ++++++++----
 src/vn_agent/agents/state.py              |  4 ++++
 4 files changed, 28 insertions(+), 9 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-28 | 实现 - 2026-03-28 23:12

**变更文件** (6 个):
**源码变更** (2 文件):
  - `src/vn_agent/agents/reviewer.py`
  - `src/vn_agent/web/app.py`

**其他变更** (3 文件):
  - `frontend/src/components/ScriptPanel.tsx`
  - `frontend/src/components/SettingPanel.tsx`
  - `frontend/src/components/StatusBar.tsx`

**变更统计**:
```
docs/MVP_TEST_PLAN.md                    |   2 +-
 frontend/src/components/ScriptPanel.tsx  |  28 +++++-
 frontend/src/components/SettingPanel.tsx | 142 ++++++++++++++++++++-----------
 frontend/src/components/StatusBar.tsx    |  20 +++++
 src/vn_agent/agents/reviewer.py          |  43 +++++++++-
 src/vn_agent/web/app.py                  |  14 +++
 6 files changed, 192 insertions(+), 57 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-28 | 实现 - 2026-03-28 22:49

**变更文件** (8 个):
**源码变更** (5 文件):
  - `src/vn_agent/agents/character_designer.py`
  - `src/vn_agent/agents/director.py`
  - `src/vn_agent/agents/scene_artist.py`
  - `src/vn_agent/prompts/templates.py`
  - `src/vn_agent/services/mock_llm.py`

**测试变更** (2 文件):
  - `tests/test_integration/test_pipeline.py`
  - `tests/test_prompts/test_templates.py`

**变更统计**:
```
docs/MVP_TEST_PLAN.md                     | 147 +++++++++++++++++++++++++
 src/vn_agent/agents/character_designer.py |   6 +-
 src/vn_agent/agents/director.py           |  15 ++-
 src/vn_agent/agents/scene_artist.py       |   6 +-
 src/vn_agent/prompts/templates.py         | 172 ++++++++++++++++++++++--------
 src/vn_agent/services/mock_llm.py         |   9 +-
 tests/test_integration/test_pipeline.py   |   5 +-
 tests/test_prompts/test_templates.py      |   2 +-
 8 files changed, 300 insertions(+), 62 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-28 | 杂项 - 2026-03-28 22:08

**变更文件** (7 个):
**其他变更** (7 文件):
  - `frontend/src/App.tsx`
  - `frontend/src/app.css`
  - `frontend/src/components/ChatPanel.tsx`
  - `frontend/src/components/ProgressBar.tsx`
  - `frontend/src/components/StatusBar.tsx`

**变更统计**:
```
frontend/src/App.tsx                    | 29 +++++++++++++++++++----
 frontend/src/app.css                    |  7 ++++++
 frontend/src/components/ChatPanel.tsx   | 41 ++++++++++++++++++++++++++++++---
 frontend/src/components/ProgressBar.tsx | 20 ++++++++++------
 frontend/src/components/StatusBar.tsx   | 26 ++++++++++++++++-----
 frontend/src/store.ts                   | 24 +++++++++++++++++--
 frontend/src/types.ts                   |  1 +
 7 files changed, 126 insertions(+), 22 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-28 | 实现 - 2026-03-28 22:01

**变更文件** (10 个):
**源码变更** (1 文件):
  - `src/vn_agent/web/app.py`

**配置变更** (1 文件):
  - `pyproject.toml`

**其他变更** (8 文件):
  - `frontend/src/api.ts`
  - `frontend/src/components/AssetPanel.tsx`
  - `frontend/src/components/PreviewPanel.tsx`
  - `frontend/src/components/ScriptPanel.tsx`
  - `frontend/src/components/VNPreview.tsx`

**变更统计**:
```
frontend/src/api.ts                      |  28 +++++-
 frontend/src/components/AssetPanel.tsx   | 142 ++++++++++++++++++++++++++++
 frontend/src/components/PreviewPanel.tsx |  40 ++++----
 frontend/src/components/ScriptPanel.tsx  |  16 +++-
 frontend/src/components/VNPreview.tsx    | 136 +++++++++++++++++++++++++++
 frontend/src/store.ts                    | 101 +++++++++++++++-----
 frontend/src/types.ts                    |  16 ++++
 pyproject.toml                           |   1 +
 src/vn_agent/web/app.py                  | 156 ++++++++++++++++++++++++++++++-
 uv.lock                                  |  11 +++
 10 files changed, 598 insertions(+), 49 deletions(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-28 | 杂项 - 2026-03-28 21:38

**变更文件** (1 个):
**其他变更** (1 文件):
  - `.github/workflows/ci.yml`

**变更统计**:
```
.github/workflows/ci.yml | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
```

**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---

### 2026-03-28 | Phase 9: Web 前端交互层（PRD v2 Sprint 1-3）

**状态**: ✅ Sprint 1-3 完成

**目标**: 基于 PRD v2，构建 React + TypeScript Web 前端，实现分步生成 + 用户检查点 + 场景编辑

---

#### Sprint 1: React 前端骨架 + 端到端联通

**技术决策**:
- 选择 React + TypeScript + Vite 替代原 vanilla HTML/JS：后续 Sprint 需要复杂组件交互（编辑器、树状可视化），vanilla 无法支撑
- Tailwind CSS 使用 CDN 而非 `@tailwindcss/vite` 插件：v4 原生插件在 Windows 上有 `@tailwindcss/oxide` 二进制文件加载问题
- 状态管理选择 Zustand（不用 Redux）：中等复杂度应用，Zustand 更轻量
- Vite proxy 配置：开发模式前端 :5173 → 后端 :8000 API 透传，避免 CORS 问题

**架构**: 左右分栏（ChatPanel + PreviewPanel），侧栏 JobHistory

**交付**: 6 个组件 + API 客户端 + Zustand store + 多阶段 Dockerfile

---

#### Sprint 2: 设定确认检查点

**技术决策**:
- 后端引入"黑板"（Blackboard）机制：Director 输出写入 `jobs.blackboard` JSON 列，前端通过 API 读取/编辑
- SQLite schema 迁移：`ALTER TABLE jobs ADD COLUMN blackboard`，带向后兼容检测
- 分步 API 设计：`generate-setting` 仅跑 Director 并返回，不启动 Writer，用户确认后才触发 `generate-script`
- 前端状态机：`idle → generating_setting → setting_review → generating_script → completed`

**问题与反思**:
- Windows 上 `VN_AGENT_MOCK=true docker compose up` 的 shell 变量不传入容器 → 改用 `.env.docker` 文件方案
- Pydantic 对象无法 JSON 序列化存入 SQLite → Sprint 3 改为 `model_dump()` 序列化

**交付**: 5 个新 API + SettingPanel 组件（世界观/角色/大纲卡片 + 确认/重新生成按钮）

---

#### Sprint 3: 脚本生成 + 审阅交互

**技术决策**:
- 黑板存储完整对话（不仅是摘要）：`scene_scripts[].dialogue[]` 含 character_id/text/emotion
- Reviewer 反馈写入黑板：`reviewer.passed` / `reviewer.feedback` / `reviewer.revision_count`
- 场景编辑 API：`PUT /api/projects/{id}/script/{scene_id}` 同时更新 `scene_scripts` 和 `_script_json`（保持双份数据一致）
- 前端 ScriptPanel：标签页导航切换场景，inline 编辑模式（character_id 输入 + emotion 下拉 + text 文本框）

**交付**: ScriptPanel 组件 + 场景编辑 API + 导出 JSON API + Reviewer banner

---

#### Director 7B 本地模型适配

**问题**: qwen2.5:7b 只生成 1 个场景（应 3-5 个），原因是 Director prompt 过于复杂（CoT `<thinking>` 标签 + 策略列表 + 复杂 JSON schema）超出 7B 模型能力

**方案**: 自动检测小模型（模型名含 qwen/llama/phi/mistral/gemma），启用简化 prompt 路径
- 去掉 `<thinking>` 指令和策略列表
- 用紧凑 JSON 示例（含 3 个场景）代替 schema 说明
- 明确指示 `Include exactly N scenes`

**效果**: qwen2.5:7b 稳定输出 4 场景 + 2 个分支选择，生成完整可玩 Ren'Py 脚本

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
| P0 | Phase 8 AI 深度补全（Sprint 12-15） | ✅ 完成（140 测试） |
| P0 | Phase 9 Web 前端 Sprint 1-3 | ✅ 完成（React + 分步生成 + 场景编辑） |
| P0 | Ollama 7B 本地模型适配 | ✅ 完成（4 场景+分支） |
| P1 | Phase 9 Sprint 4：资产管理面板 | 🔜 下一步 |
| P1 | Phase 9 Sprint 5：体验打磨 + 双 Key Pool | 🔜 后续 |
| P1 | 真实 BGM 文件替换占位 WAV | 待开始 |
| P2 | 自然语言编辑（对话式修改设定/脚本） | 待开始 |
| P2 | Suno API 音乐生成 | 待 API 公开 |

---

_最后更新: 2026-04-14_