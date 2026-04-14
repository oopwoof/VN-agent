# VN-Agent 面试投屏展示指南

> 目标：用 5-8 分钟带面试官走完项目全貌，节奏紧凑，每一步都有代码可看。
> 建议提前打开所有标注的文件 tab，避免现场找文件。

---

## 展示前准备

### 提前打开的 Tab（按展示顺序）

1. **GitHub 仓库首页** — README.md（架构图）
2. `src/vn_agent/agents/graph.py` — DAG 编排
3. `src/vn_agent/agents/state.py` — 共享状态
4. `src/vn_agent/agents/director.py` — 两步规划 + 截断修复
5. `src/vn_agent/agents/writer.py` — RAG 注入 + 逐场景生成
6. `src/vn_agent/agents/reviewer.py` — 结构校验 + LLM 质量审查
7. `src/vn_agent/schema/script.py` — 核心数据模型
8. `src/vn_agent/config.py` — 多模型路由
9. `src/vn_agent/eval/strategy_eval.py` — 评测
10. `tests/test_integration/test_pipeline.py` — 集成测试
11. `.github/workflows/ci.yml` — CI
12. 终端窗口（准备跑测试/dry-run）

### 可选演示命令（提前验证能跑通）

```bash
# Mock 模式生成（零 API 成本，~3 秒完成）
uv run vn-agent generate --mock --output ./demo_output --theme "A lighthouse keeper during a storm"

# 跑测试（不含慢速 API 测试）
uv run pytest -x --tb=short -m "not slow" -q

# 结构校验
uv run vn-agent validate ./demo_output
```

---

## 展示流程

### 第一步：README 架构图（1 分钟）

**打开 GitHub 仓库首页 README.md**

> "这个项目是一个多 Agent AI 视觉小说生成器。输入一句话主题，输出一个可运行的 Ren'Py 游戏，包含分支剧情、立绘、背景、BGM。"

指着架构图讲三个核心设计：

```
Director → Writer ⇄ Reviewer → [Character | Scene | Music] → Ren'Py
```

1. **6 Agent 分工**："每个 Agent 负责独立决策域，prompt 和 output schema 不同，合并会导致 JSON 输出不稳定"
2. **修订循环**："Writer 和 Reviewer 之间有条件循环，最多 3 轮，防止无限循环"
3. **并行资产生成**："三个资产 Agent 无数据依赖，用 `asyncio.gather` 并行，耗时降为 max(T)"

---

### 第二步：DAG 编排代码（1.5 分钟）

**打开 `src/vn_agent/agents/graph.py`**

**重点展示 `build_graph()` 函数（第 123-163 行）：**

```python
graph.set_entry_point("director")
graph.add_edge("director", "writer")
graph.add_edge("writer", "reviewer")

# 条件分支：通过/修订/结束
graph.add_conditional_edges("reviewer", _after_review, {
    "proceed": "asset_generation",
    "revise": "writer",        # ← 修订循环
    "end": END,                # ← text_only 模式
})
```

> "LangGraph 的 StateGraph 原生支持条件边和循环，比手写 while 循环更声明式、可观测。"

**指一下 `_after_review` 条件函数（第 100-120 行）：**

> "三路分支：review_passed → 生成资产；未通过且未超轮次 → 回 Writer 修订；text_only → 直接结束。"

**指一下 `_run_assets_parallel`（第 45-79 行）：**

```python
results = await asyncio.gather(
    _traced("character_designer", run_character_designer),
    _traced("scene_artist", run_scene_artist),
    _traced("music_director", run_music_director),
    return_exceptions=True,  # ← 故障隔离
)
```

> "`return_exceptions=True` 让单个 Agent 失败不会中断其他两个，异常收集到 state['errors'] 里。"

---

### 第三步：共享状态（30 秒）

**打开 `src/vn_agent/agents/state.py`**

> "所有 Agent 共享一个 TypedDict 状态，每个 Agent 只读取自己需要的字段、写入自己负责的字段。"

关键字段快速过一遍：

| 字段 | 写入者 | 读取者 |
|------|--------|--------|
| `vn_script` | Director → Writer → Reviewer | 所有 |
| `characters` | Director → CharacterDesigner | Writer, Compiler |
| `review_passed` | Reviewer | 条件函数 `_after_review` |
| `revision_count` | Reviewer | 条件函数（判断是否超轮次） |
| `review_feedback` | Reviewer | Writer（修订时参考） |
| `text_only` | 用户输入 | 条件函数（跳过资产生成） |

---

### 第四步：Director 两步规划 + 截断修复（1.5 分钟）

**打开 `src/vn_agent/agents/director.py`**

**两步拆分的动机（第 64-73 行）：**

> "单步让 LLM 同时生成场景大纲 + 分支 + 音乐 + 角色，prompt 太长，max_tokens 容易截断。拆成两步：Step1 只出场景和角色大纲，Step2 在已有结构上补导航和音乐。"

**Step2 的关键约束（第 216-219 行）：**

```python
user_prompt = f"""All valid scene IDs: {json.dumps(scene_ids)}"""
```

> "把合法 ID 列表显式传给 LLM，约束它只能引用这些 ID，减少幻觉。"

**截断修复 — 滚动到 `_salvage_truncated_json`（第 341-420 行）：**

> "LLM 输出的 JSON 可能因为 max_tokens 限制被截断。我设计了双策略修复：反向扫描找最后一个闭合括号截断、正向括号计数找最后一个顶层逗号截断。两种策略互补——反向适合截断在深层嵌套里的情况，正向适合截断在顶层字段之间的情况。"

**如果面试官感兴趣，指一下 `_close_and_parse`（第 351-381 行）：**

> "核心是括号栈：扫描未闭合的 `{` 和 `[`，把缺失的闭合符号补上。"

**LLM Self-Repair（第 423-442 行）：**

> "如果截断修复后 Pydantic 校验还是失败，把错误信息喂回 LLM 让它修。这是最后一道防线。"

---

### 第五步：Writer + RAG 注入（1 分钟）

**打开 `src/vn_agent/agents/writer.py`**

**逐场景生成（第 56-61 行）：**

> "Writer 对每个场景独立调用 LLM 生成对话。每次调用只看当前场景的元数据 + 全局角色描述 + 修订反馈，不看其他场景的对话。这样每次 prompt 短、JSON 截断概率低，且可以独立重试。"

**RAG few-shot 注入（第 146-172 行）：**

```python
query = f"{scene.description} | strategy: {strategy_label}"
examples = retrieve_examples_semantic(embedding_index, query, strategy_label, k=settings.few_shot_k)
```

> "用 1,036 条标注语料建了 FAISS IndexFlatIP 索引。检索时 query 拼接场景描述和策略标签，先语义检索 over-retrieve，再按策略标签硬过滤，最终 top-K 注入 Writer prompt 作为 few-shot 示例。"

**修订反馈集成（第 119-121 行）：**

```python
if revision_feedback:
    feedback_note = f"\nIMPORTANT - Revision feedback to address:\n{revision_feedback}\n"
```

> "如果 Reviewer 打回来了，Writer 会在 prompt 里看到具体的修改建议。"

---

### 第六步：Reviewer 结构校验（1 分钟）

**打开 `src/vn_agent/agents/reviewer.py`**

**`_structural_check`（第 77-120 行）— 快速展示 4 项确定性校验：**

> "不依赖 LLM 的确定性规则，100% 检测率：
> 1. **起始场景存在性**（第 82-84 行）— 入口 ID 存在吗
> 2. **引用合法性**（第 86-97 行）— 每条分支指向的场景存在吗
> 3. **BFS 可达性**（第 99-103 行）— 从起点能走到所有场景吗
> 4. **角色一致性**（第 108-114 行）— 说话的角色在声明列表里吗"

**BFS 实现（第 123-140 行）：**

> "从 start_scene_id 出发，沿着 next_scene_id 和 branches 做 BFS，找出所有可达场景。不可达的就是孤岛。"

**核心理念：**

> "确定性校验保底，LLM 质量审查补充。结构问题不需要 LLM 判断，用确定性规则就能 100% 拦截。"

---

### 第七步：数据模型（30 秒，快速过）

**打开 `src/vn_agent/schema/script.py`**

> "整个管线流转的核心是 `VNScript`：包含场景列表 `scenes`、每个场景有 `dialogue`（对话）、`branches`（分支）、`music`（BGM）。最终编译成 Ren'Py 脚本。"

指一下三个关键类型的关系：

```
VNScript
  └── Scene[]
        ├── DialogueLine[]  ← Writer 填充
        ├── BranchOption[]  ← Director Step2 填充
        └── MusicCue        ← Director Step2 填充
```

---

### 第八步：多模型路由 + 成本优化（30 秒）

**打开 `src/vn_agent/config.py`**

> "6 个 Agent 各自可配模型。默认：Director/Writer 用 Sonnet（需要复杂推理），其他 4 个用 Haiku（简单结构化任务）。全 Haiku 模式降本 73%。"

指一下 per-agent 配置字段：

```python
llm_director_model   # Sonnet — 复杂规划
llm_writer_model     # Sonnet — 对话质量
llm_reviewer_model   # Haiku  — 结构化审查
```

> "还支持一行配置切 Ollama 本地模型，零 API 成本。"

---

### 第九步：测试 + CI（1 分钟）

**打开 `tests/test_integration/test_pipeline.py`**

> "140+ pytest 测试。集成测试用 Mock LLM fixture 实现零成本测试——不调真实 API，毫秒级完成。"

指一下 mock 机制（第 100-132 行）：

```python
mocker.patch("vn_agent.agents.director.ainvoke_llm", side_effect=side_effect)
mocker.patch("vn_agent.agents.writer.ainvoke_llm", side_effect=side_effect)
mocker.patch("vn_agent.agents.reviewer.ainvoke_llm", side_effect=side_effect)
```

> "在每个 Agent 模块的 import namespace 里 patch，确保 mock 生效。"

**打开 `.github/workflows/ci.yml`**

> "CI 流程：lint（ruff）→ 类型检查（mypy）→ 测试 + 覆盖率（≥60% 门控）。慢速 API 测试用 `@pytest.mark.slow` 隔离，CI 里跳过。"

---

### 第十步：现场演示（可选，1 分钟）

**在终端运行：**

```bash
uv run vn-agent generate --mock --output ./demo_output --theme "A lighthouse keeper during a storm"
```

> "这是 mock 模式，用预置响应代替真实 API，演示完整管线流程。"

生成完成后：

```bash
# 查看生成的剧本结构
cat demo_output/vn_script.json | python -m json.tool | head -40

# 跑结构校验
uv run vn-agent validate ./demo_output

# 跑测试
uv run pytest tests/test_integration/test_pipeline.py -v --tb=short
```

---

## 面试官可能追问 & 应对

### 架构类

| 追问 | 回答要点 | 指向代码 |
|------|----------|----------|
| "为什么不用一个大 prompt？" | JSON 输出不稳定 + 注意力稀释 + 无法独立选模型/重试 | `graph.py` 6 个 node |
| "为什么选 LangGraph？" | 需要条件分支 + 循环，DAG 拓扑，chain 无法表达 | `build_graph()` conditional_edges |
| "修订循环会不会无限循环？" | 硬上限 3 轮 + `_after_review` 条件函数 | `graph.py:100-120` |
| "资产并行怎么做故障隔离？" | `return_exceptions=True` + errors 累积 | `graph.py:62-78` |

### RAG 类

| 追问 | 回答要点 | 指向代码 |
|------|----------|----------|
| "RAG 怎么做的？" | FAISS IndexFlatIP + 语义检索 + 策略标签过滤 + few-shot 注入 | `writer.py:146-172` |
| "为什么不用 Pinecone？" | 1036 条语料，FAISS 内存 < 10MB，延迟 < 1ms，向量数据库过度工程 | `eval/embedder.py` |
| "F1 只有 0.34？" | 6 分类任务随机基线 16.7%，7B 本地模型，关键是方法论：keyword 0.21 → LLM 0.34（+57%） | `eval/strategy_eval.py` |

### 工程类

| 追问 | 回答要点 | 指向代码 |
|------|----------|----------|
| "截断怎么处理？" | 双策略 JSON salvage + LLM self-repair | `director.py:341-442` |
| "测试怎么做？" | Mock LLM fixture + 零 API 成本 + `@pytest.mark.slow` 隔离 | `test_pipeline.py:100-132` |
| "怎么降本？" | 多模型路由 Sonnet+Haiku，全 Haiku 模式 −73% | `config.py` per-agent models |

### 游戏场景延伸

| 追问 | 回答要点 |
|------|----------|
| "跟游戏开发什么关系？" | 本质就是游戏内容生产管线：剧情+美术+音乐全流程自动化 |
| "怎么迁移到关卡配置生成？" | Planner → Generator → Validator + 修订循环，Validator 用确定性规则保底 |
| "Agent 在游戏中的挑战？" | 延迟（预生成+缓存）、一致性（结构化输出+确定性校验）、成本（多模型路由） |

---

## 展示节奏控制

| 步骤 | 时间 | 核心信息 |
|------|------|----------|
| README 架构图 | 1 min | 项目是什么、为什么这么拆 |
| graph.py DAG | 1.5 min | 条件边、修订循环、并行资产 |
| state.py 状态 | 0.5 min | 共享状态设计 |
| director.py 规划 | 1.5 min | 两步生成、截断修复（工程深度） |
| writer.py RAG | 1 min | RAG 注入、逐场景生成 |
| reviewer.py 校验 | 1 min | BFS 可达性、确定性规则 |
| schema 数据模型 | 0.5 min | VNScript 结构 |
| config.py 路由 | 0.5 min | 降本 73% |
| 测试 + CI | 1 min | Mock LLM、覆盖率门控 |
| 现场演示 | 1 min | mock 模式跑通全管线 |
| **合计** | **~8 min** | |

> **核心原则**：每一步都指着代码讲，不空谈概念。面试官看到的是真实的工程实现，不是 PPT。
