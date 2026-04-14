# VN-Agent 面试投屏展示指南 (v2, 2026-04-14)

> **与 v1 的差异**：v1 是 10 步 8 分钟的基础展示，聚焦 Director 两步、Writer RAG 注入、Reviewer 结构校验；v2 增补了 **StructureReviewer 早拦截**、**双轨 RAG（dialogue + lore pivot）**、**长文本一致性三层记忆**（Character Bible / Summarizer / Symbolic State）、**Persona Fingerprint 审计**、**Sprint 8-5 sweep 数据故事**、**单场景热重写**、**RAG 审计文件 `rag_retrievals.jsonl`**。节奏调整为 **12 步 10 分钟**。

---

## 展示前准备

### 提前打开的 Tab（按展示顺序）

1. **GitHub 仓库首页** — README.md（架构图）
2. `src/vn_agent/agents/graph.py` — DAG 编排
3. `src/vn_agent/agents/state.py` — 共享状态
4. `src/vn_agent/agents/director.py` — 两步规划 + 截断修复
5. `src/vn_agent/agents/structure_reviewer.py` — ★ **大纲审查（v2 新）**
6. `src/vn_agent/agents/writer.py` — RAG 注入 + literary/action 模式
7. `src/vn_agent/eval/lore.py` — ★ **Lore pivot（v2 新）**
8. `demo_output/vn_joint_20260414_120437/rag_retrievals.jsonl` — ★ **RAG 审计文件（v2 新）**
9. `src/vn_agent/agents/reviewer.py` — 结构校验 + LLM 质量审查
10. `src/vn_agent/agents/summarizer.py` — ★ **递归摘要（v2 新）**
11. `src/vn_agent/agents/persona_audit.py` — ★ **声音漂移审计（v2 新）**
12. `src/vn_agent/agents/state_orchestrator.py` — ★ **Symbolic World State（v2 新）**
13. `src/vn_agent/config.py` — 多模型路由 + writer_mode + caching
14. `tests/test_integration/test_pipeline.py` — 集成测试
15. `.github/workflows/ci.yml` — CI
16. 终端窗口

### 预验证演示命令

```bash
# 生成前预览（dry-run 不调 API）
uv run vn-agent dry-run --theme "A clockmaker's last apprentice"

# Mock 模式完整管线（零 API 成本）
uv run vn-agent generate --mock --output ./demo_output/showcase --theme "..."

# 查看 RAG 审计文件
head -3 demo_output/vn_joint_*/rag_retrievals.jsonl | python -m json.tool

# 结构校验
uv run vn-agent validate ./demo_output/showcase

# 单场景热重写
uv run vn-agent regen --output ./demo_output/showcase --scene ch1_opening
```

---

## 展示流程（10 分钟）

### Step 1 — README 架构图（1 min）

**打开 GitHub 首页 README.md**

> "输入一句话主题，输出可运行 Ren'Py 游戏。核心是**多 Agent DAG + 质量闭环 + 长文本一致性**三个层次。"

手指着架构图讲 3 个关键设计：
1. **Agent 分工**：每个 Agent 独立决策域，合并会导致 prompt 膨胀 + JSON 不稳定
2. **修订循环**：Writer↔Reviewer 条件边，3 轮硬上限
3. **并行资产**：Character/Scene/Music 无依赖，asyncio.gather

---

### Step 2 — DAG 编排（1.5 min）

**打开 `graph.py`**

**`build_graph()` 函数**：

```python
graph.add_edge("director", "writer")
graph.add_edge("writer", "reviewer")
graph.add_conditional_edges("reviewer", _after_review, {
    "proceed": "asset_generation",
    "revise": "writer",        # 修订循环
    "end": END,
})
```

> "LangGraph StateGraph 原生支持条件边 + 循环，比 chain 更声明式。"

**`_run_assets_parallel`**：

```python
results = await asyncio.gather(
    _traced("character_designer", run_character_designer),
    _traced("scene_artist", run_scene_artist),
    _traced("music_director", run_music_director),
    return_exceptions=True,  # ← 故障隔离
)
```

> "`return_exceptions=True` 让单 Agent 失败不中断其他，异常收集到 state['errors']。"

---

### Step 3 — Director 两步规划 + 截断修复（1 min）

**打开 `director.py`**

> "Director 拆两步：Step1 出场景+角色大纲，Step2 补分支+音乐。单步同时输出四维度会让 max_tokens 截断。"

**滚动到 `_salvage_truncated_json`（第 341-420 行）**

> "JSON 截断双策略修复：反向扫描找最后一个闭合括号截断 + 正向括号计数找最后一个顶层逗号截断。两者互补。"

**LLM Self-Repair**（第 423-442 行）：

> "修复后 Pydantic 还失败的话，错误信息喂回 LLM 让它修。最后一道防线。"

---

### Step 4 ★ **StructureReviewer — 大纲早拦截（1 min）**

**打开 `structure_reviewer.py`**

> "这是 Sprint 7-5 加的新层：在 Writer 启动前审核 Director 的**大纲**。"

**两类审查**：
1. **Narrative shape**：策略分布是否合理、角色数 vs 场景数是否匹配、故事弧完整性
2. **Branch intent alignment**：每个分支选项的文本意图是否对齐下游场景描述

**动机**：

> "Director 大纲可能结构上 PASS 但语义上错——比如两个分支都合法，但'大声朗读'选项指向了'安静独处'场景。如果让 Writer 继续，会浪费 6 次 Sonnet 对话生成才被 DialogueReviewer 拦截。在 outline 阶段审，不合格回 Director，省钱。"

**关键设计**：默认非阻塞（warnings 进 state['errors']），只在 `structure_review_strict=True` 时阻塞——避免 sweep 里每个 soft warning 都停。

---

### Step 5 — Writer + literary/action 双模式（1.5 min）

**打开 `writer.py`**

**逐场景生成**（第 56-61 行）：

> "Writer 对每个场景独立调用 LLM，不看其他场景对话。每次 prompt 短、JSON 截断概率低、独立重试。"

**打开 `config.py` 第 88-104 行**

> "Sprint 7 引入 writer_mode 两种：
> - `action`：注入原始对话 few-shot（galgame/动漫风格）
> - `literary`：物理框架系统 prompt，**零 few-shot 注入**，防止风格污染"

**Sprint 8-5 sweep 数据**（指着注释）：

```
literary mean 4.17 vs action 3.92 vs baseline_self_refine 3.45 vs baseline_single 3.25
literary beat action on BOTH themes including the action-leaning dragon (4.5 vs 4.17)
```

> "数据驱动的翻盘：literary 在**两个主题**上都赢，包括动作主题。4 月 14 号把默认 flip 成 literary。这启发了 Sprint 10-2 的 RAG pivot——基建不扔，找新用途。"

---

### Step 6 ★ **Lore Pivot — RAG 的第二条轨道（1.5 min）**

**打开 `eval/lore.py`**

**读模块注释（第 1-28 行）**：

```
Critique: "RAG is a flower vase — we build it and never use it in literary mode."
This module pivots the same infrastructure to a different job: retrieve
WORLD-BUILDING FACTS (character backgrounds, location descriptions,
world variables, story premise) per-scene so Writer can keep those
facts consistent across scenes without style contamination.
```

> "Sprint 7 禁了 few-shot 之后 FAISS 基建成了'花瓶'。Sprint 10-2 把同一套检索转用来召回**事实性实体**——角色背景、场景描述、世界变量——而不是对话风格。"

**关键设计**：
- Lore 从 Director 输出里 extract（不新增 LLM 调用、不改 schema）
- Per-run 内存索引（每个主题 bespoke）
- 强制 `AnnotatedSession(strategy=None)` 复用 `EmbeddingIndex.search`
- **在 literary + action 两种模式都开**（facts 不污染风格）

**切到 `demo_output/vn_joint_*/rag_retrievals.jsonl`**

> "这是审计文件，每行记录一次检索。第一条 `strategy: __lore__` 是 lore 检索（召回了 bg_workshop_midnight、Aldric 角色背景等）。第二条同场景是传统 strategy 检索（召回 The Survival of Sarah Rose 等对话片段）。**同场景两次检索，两个用途**。"

---

### Step 7 — Reviewer 四层校验（1 min）

**打开 `reviewer.py`**

**`_structural_check`** 四项确定性规则：
1. 起始场景存在性
2. 引用合法性（分支指向的场景存在）
3. BFS 可达性（无孤岛场景）
4. 角色一致性（说话的角色已声明）

> "不用 LLM，100% 检测率。结构问题用确定性规则保底。"

**LLM 质量审查**：5 维度 rubric（Narrative / Character voice / Subtext / Strategy adherence / Pacing），≥3.5 PASS。

**双评审员（Sprint 8-1）**：

> "Sonnet 自评 + GPT-4o 独立评分交叉验证。避免'Sonnet 给 Sonnet 的产出打分'的回音室问题。"

---

### Step 8 ★ **长文本一致性三层（1 min）**

**打开 `summarizer.py`**（30 秒）

> "Sprint 11-1：20+ 场景时 Writer 塞不下完整历史。**Haiku 低温度 0.2 做翻译类工作**，每个场景写完后生成 ≤100 词摘要。默认 OFF，≥15 场景才开启。"

**打开 `state_orchestrator.py`**（30 秒）

> "Sprint 9-6：Director 声明布尔/整型状态变量（`manuscript_read=True`），state_orchestrator 把它翻译成英文约束'Mira has already read the manuscript. Do not have her react as if discovering it for the first time.'，注入 Writer prompt。**创作与逻辑解耦**。"

---

### Step 9 ★ **Persona Fingerprint — 零 LLM 声音审计（30 s）**

**打开 `persona_audit.py`**

> "Sprint 11-3：零 LLM 纯 Python 检查。Director 为每个角色声明 speech_fingerprint（用词/句式/口头禅），substring + keyword 匹配检查对话里是否出现。漂移时写入 Reviewer feedback。
> - 只在 ≥10 场景触发（短 run 没必要）
> - **False positive 优于 false negative**，只作提示不强制修订"

---

### Step 10 — 多模型路由 + Prompt Caching（30 s）

**打开 `config.py` 第 121-127 行**

```python
enable_prompt_caching: bool = True
```

> "Anthropic ephemeral cache：system prompt ≥1500 字符时打 `cache_control={"type": "ephemeral"}`。首次 1.25× 成本，5min 内复用 **0.1×**。Writer 6-18 次调用 system prompt 都一样，caching 大赚。"

**多模型路由 6 个 `llm_*_model`**：

> "Sonnet 只给 Director/Writer（需要创造），Haiku 给翻译类廉价工作（reviewer / summarizer / state_orchestrator / asset agents）。预算模式全 Haiku 降本 73%。"

---

### Step 11 — 测试 + CI（30 s）

**打开 `tests/test_integration/test_pipeline.py` 第 100-132 行**

> "Mock LLM fixture 在每个 Agent 模块的 import namespace 里 patch，零 API 成本毫秒级完成。140+ 测试覆盖率 60% CI 门控。"

**打开 `.github/workflows/ci.yml`**

> "lint (ruff) → typecheck (mypy) → test + coverage。慢速 API 测试用 `@pytest.mark.slow` 隔离。"

---

### Step 12 ★ **现场演示（1 min，可选）**

```bash
# 打开已经跑好的 rag_retrievals.jsonl，指出两种 retrieval 并存
cat demo_output/vn_joint_*/rag_retrievals.jsonl | head -3 | python -m json.tool

# 跑 mock 管线（3 秒完成）
uv run vn-agent generate --mock --output ./demo_live

# 查看生成的 VN 脚本
head -40 demo_live/vn_script.json

# 展示 per-scene snapshot（Sprint 11-4）
ls demo_output/vn_joint_*/snapshots/

# 单场景热重写（Sprint 12-4）
uv run vn-agent regen --output ./demo_live --scene ch1_opening --help
```

---

## 面试官可能追问 & 应对

### v2 新增追问

| 追问 | 回答要点 | 指向代码 |
|------|----------|----------|
| ★ "StructureReviewer 为什么要加？" | 大纲阶段拦截语义错分支，省 6 次 Sonnet 调用 | `structure_reviewer.py` |
| ★ "writer_mode 怎么选的？" | Sprint 8-5 sweep 数据驱动：literary 4.17 > action 3.92，两个主题都赢 | `config.py:88-104` 注释 |
| ★ "Lore pivot 具体做了什么？" | 同一套 FAISS 基建，从风格 few-shot 转向事实实体检索 | `eval/lore.py` |
| ★ "长文本怎么保证角色不漂移？" | Character Bible 缓存 + 滑窗 + Haiku 递归摘要 + persona audit + 符号状态 | summarizer + persona_audit + state_orchestrator |
| ★ "rag_retrievals.jsonl 做什么？" | 每条 query/retrieved 落盘，离线分析 RAG 命中率与策略分布 | 审计文件直接展示 |
| ★ "双评审员为什么？" | 规避 Sonnet 评 Sonnet 自己的回音室，GPT-4o 做独立锚点 | `config.llm_judge_model_secondary` |
| ★ "local regen 是什么？" | 单场景热重写，per-scene snapshot 回滚点，人在环路编辑 | `local_regen.py` + `snapshots/` |

### v1 已有（仍有效）

| 追问 | 回答要点 |
|------|----------|
| "为什么拆这么多 Agent？" | JSON 稳定性 + 注意力 + 独立选模型/重试 |
| "为什么选 LangGraph？" | 条件边 + 循环 DAG，chain 无法表达 |
| "资产并行怎么故障隔离？" | `return_exceptions=True` + errors 累积 |
| "RAG 为什么不用 Pinecone？" | 1036 条语料 FAISS 足够，over-engineering |
| "F1 只有 0.34？" | 6 分类随机基线 16.7%，关键是方法论 keyword 0.21 → LLM 0.34 |
| "73% 降本怎么算的？" | Haiku/Sonnet 定价比算 + Haiku 做翻译类廉价工作 |

---

## 展示节奏控制

| Step | 时间 | 核心信息 | 新/留 |
|------|------|----------|-------|
| 1. README 架构图 | 1 min | 项目是什么 | 留 |
| 2. graph.py DAG | 1.5 min | 条件边 + 并行 | 留 |
| 3. director.py 规划 | 1 min | 两步 + JSON salvage | 留 |
| 4. ★ structure_reviewer | 1 min | **大纲早拦截** | **新** |
| 5. writer.py 模式 | 1.5 min | **literary/action + Sprint 8-5 数据** | 扩展 |
| 6. ★ lore.py + rag_retrievals | 1.5 min | **RAG pivot + 审计** | **新** |
| 7. reviewer.py 四层 | 1 min | 结构 + 质量 + **双评审员** | 扩展 |
| 8. ★ summarizer + state_orch | 1 min | **长文本三层记忆** | **新** |
| 9. ★ persona_audit | 0.5 min | **零 LLM 声音审计** | **新** |
| 10. config.py 路由 + caching | 0.5 min | **prompt caching** | 扩展 |
| 11. 测试 + CI | 0.5 min | mock fixture | 留 |
| 12. 现场演示 | 1 min | mock 跑 + rag_retrievals 展示 | 扩展 |
| **合计** | **~12 min** | | |

> **v2 核心叙事线**：从"多 Agent 能跑"（v1）升级到"数据驱动迭代 + 长文本一致性工程"（v2）。展示重点不是功能多少，而是**每个特性都有具体问题、诊断路径、数据支持**。
