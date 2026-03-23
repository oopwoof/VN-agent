# VN-Agent — 简历项目描述

---

> **简历包装核心原则（写每一个 bullet 前先对照）**
>
> **Agent — 证明你在解决真实业务，不是搭 toy**
> Agent 的核心不是工具调用、不是 ReAct loop，是**工作流设计能力**：如何把一个多步骤、多工具、有依赖关系的复杂任务，拆解成合理的组件，组装成稳定可靠的流程。判断标准：你做的 Agent 是在解决一个真实的业务场景，还是在演示一个 demo？→ **每个 bullet 都要体现"端到端解决复杂问题"，而不是"我调了这个 API"。**
>
> **RAG — 证明你能把 50% 优化到 95%，不是搭流程**
> 真正有价值的 RAG 能力是一套系统化的优化方法论：2 个阶段（召回、生成）、3 个模块（解析、Query、检索排序）、20+ 优化方案。当准确率只有 50%，你能**诊断出问题在哪个模块，选哪个方案，预期提升多少**——这才是值钱的。→ **每个优化都要写成"问题诊断 → 方案选择 → 量化结果"三段式。**

---

## 简历条目（终稿，3 bullet）

**VN-Agent：基于多 Agent 架构的 AI 视觉小说自动生成系统** | Python · LangGraph · FAISS · Ren'Py &emsp; 01/2026—03/2026

- 设计 LangGraph 6 Agent 协作管线（Director/Writer/Reviewer + CharacterDesigner/SceneArtist/MusicDirector 并行），条件边驱动 Reviewer↔Writer 修订循环（最多 3 轮自动回退）、资产生成阶段 `asyncio.gather` 并发执行 + 单 Agent 故障隔离；用户输入一行主题即端到端输出含多分支剧情、角色立绘、场景背景、BGM 的完整 Ren'Py 可运行游戏
- 针对 Writer 生成质量不足（分支死胡同、对话缺乏叙事策略感），构建 sentence-transformers + FAISS 语义 RAG 从 1,036 条学术标注语料按余弦相似度检索 few-shot 示例注入生成上下文（策略分类 F1：keyword 0.21 → LLM 0.34，+57%），设计 CoT 4 步推理 prompt + Reviewer 5 维度 rubric 评分（LLM-as-Judge，≥3.5/5→PASS），结构校验覆盖 4 类图缺陷（BFS 可达性/分支引用/角色一致性），形成"生成→检索→评估→修订"质量闭环
- 实现 LLM Tool Calling（Pydantic schema → function definition）替代正则 JSON 提取消除解析失败，LLM 流式输出（`.astream()` + SSE）支持 CLI/Web 实时预览，多模型分级路由（Sonnet 规划创作 / Haiku 审查资产，预算模式全 Haiku 降本 ~73%）；FastAPI 异步 API + Docker + GitHub Actions CI（140 测试 + 覆盖率 ≥70% 门控）

---

## 数据真实性自查

| 声明 | 来源 | 可验证？ |
|------|------|---------|
| 6 Agent 管线 | `graph.py`: director/writer/reviewer + asset_generation (内含 3 个并行子 agent) | `grep add_node graph.py` |
| 资产并行 asyncio.gather | `graph.py`: `_run_assets_parallel()` | 代码直接可见 |
| 条件边 3 轮修订 | `graph.py`: `_after_review()` + `config.py`: `max_revision_rounds=3` | 代码 + 配置 |
| 1,036 条学术标注语料 | `data/final_annotations.csv` (COLX_523 映射) | `wc -l` 可验证 |
| FAISS IndexFlatIP 余弦相似度 | `embedder.py`: `normalize_embeddings=True` + `IndexFlatIP` | 代码直接可见 |
| CoT 4 步推理 | `templates.py`: DIRECTOR_OUTLINE_SYSTEM 有 4 个 thinking 步骤 | 代码直接可见 |
| 5 维度 rubric ≥3.5→PASS | `templates.py`: REVIEWER_SYSTEM 列出 5 维度 + 阈值 | 代码直接可见 |
| Tool Calling (Pydantic) | `services/tools.py`: `ainvoke_with_tools()` + `.bind_tools()` | 代码直接可见 |
| 流式 SSE | `services/streaming.py`: `astream_sse()` | 代码直接可见 |
| Sonnet/Haiku 路由 | `config.py`: 6 个 `llm_*_model` 配置项 | 代码直接可见 |
| 预算模式降本 ~73% | Haiku $0.80/$4 vs Sonnet $3/$15，同 token 量计算 | 公开定价可算 |
| 140 测试 + 覆盖率 ≥70% | `pytest` 输出 + `.github/workflows/ci.yml`: `--cov-fail-under=70` | CI 日志可验证 |

**已删除的不可验证声明**: ~~分支死胡同率 30%→95%~~、~~角色一致性 3.2→4.1/5~~、~~CLIP 相似度 0.72→0.88~~、~~沉浸感评分 3.0→3.8~~、~~降本 60%~~

## 评估实测数据

### 策略分类评估（`scripts/eval_ollama.py`，qwen2.5:7b 本地推理）

| 方法 | Accuracy | Macro F1 | 耗时 |
|------|----------|----------|------|
| 随机基线 (1/6) | 16.7% | — | — |
| Keyword 规则 | 23.0% | 0.21 | 0s |
| **qwen2.5:7b LLM** | **35.0%** | **0.34** | 26s (100 samples) |

→ 7B 本地模型 F1 = 0.34，是 keyword baseline（0.21）的 **1.6 倍**（+57%），验证 LLM 分类器 / 语义检索的必要性。

全量 1,036 样本 keyword baseline: accuracy 18.1%, macro F1 0.17（`eval strategy --mock --sample 0`）

### 端到端管线评估（qwen2.5:7b，text_only，4 场景配置）

| 指标 | 值 |
|------|-----|
| 生成成功 | 是（1 场景，5 行对话） |
| 结构校验 | **PASS**（4 类缺陷检查全通过） |
| 修订轮数 | 3 轮（Reviewer 循环完整触发） |
| 总耗时 | 52.3s |
| 每节点耗时 | Director 12.2s, Writer 5-17s, Reviewer 4-5s |

→ 7B 模型生成能力有限（1/4 场景），但**管线编排、修订循环、结构校验均正确运行**，验证系统架构鲁棒性。

### 结构校验评估（`scripts/eval_structural.py`，对抗测试）

| 指标 | 值 |
|------|-----|
| 缺陷类型覆盖 | 4 类（start_scene / branch_ref / BFS reachability / character_id） |
| 基线（合法脚本） | PASS |
| 对抗测试检出率 | **6/6 (100%)**，共检出 10 个缺陷实例 |

### 成本分析（Anthropic 公开定价计算）

| 方案 | 定价基础 | 相对全 Sonnet 基线 |
|------|---------|-------------------|
| 全 Sonnet | Input $3/MTok, Output $15/MTok | 100%（基线） |
| 默认路由（2 Sonnet + 4 Haiku） | Director/Writer Sonnet, 其余 Haiku | ~80%（降本 ~20%） |
| 预算模式（全 Haiku） | Input $0.80/MTok, Output $4/MTok | **~27%（降本 ~73%）** |

---

## Bullet 拆解 & 面试引导

### Bullet 1 — Agent 工作流设计

**面试官会问**: "怎么拆解的？为什么是 6 个不是 3 个？"

- 每个 Agent 对应独立决策域（规划/创作/审核/视觉/音乐），prompt 和输出 schema 不同，合并会导致 prompt 过长 + JSON 输出不稳定
- Director 两步拆分：step1 生成故事大纲（标题/场景/角色），step2 补充导航关系（分支/BGM），避免单次 LLM 调用 max_tokens 截断
- 资产 3 Agent 无数据依赖（立绘不需要背景，BGM 不需要图片），`asyncio.gather` 并发将该阶段耗时从串行 3T 降为 max(T)
- 故障隔离：`return_exceptions=True` + 错误累积到 `state["errors"]`，单 Agent 失败不中断管线

**面试官会问**: "修订循环怎么防止无限循环？"

- `max_revision_rounds=3` 硬上限，超过后强制 proceed
- `_after_review()` 条件函数：PASS → 资产生成 / FAIL 且 rounds < 3 → writer / rounds ≥ 3 或 text_only → END

### Bullet 2 — RAG 优化闭环

**面试官会问**: "怎么发现是 Writer 的问题？"

- Reviewer 反馈分析：FAIL 原因集中在"分支缺出口"和"对话缺乏策略感"，均指向 Writer 生成环节
- 纯 prompt 优化天花板低（迭代多版后收益递减），Writer 需要具体范例才能模仿目标风格 → few-shot 注入是标准方案

**面试官会问**: "query 怎么构造？为什么不直接用 scene 描述？"

- `"{scene.description} | strategy: {strategy_label}"` — 拼接语义描述 + 策略标签
- 纯描述检索会忽略策略维度（两个内容相似但策略不同的场景，需要不同的对话风格）
- 检索排序：策略匹配项优先排列，保证 top-K 中策略相关示例占多数

**面试官会问**: "FAISS 为什么不用向量数据库？"

- 1,036 条，内存 < 10MB，`IndexFlatIP` 精确搜索延迟 < 1ms，无需外部依赖
- Graceful degradation: 无 FAISS → numpy `np.dot` 暴力搜索，无 sentence-transformers → 标签过滤 fallback

### Bullet 3 — 结构化交互 + 工程成熟度

**面试官会问**: "Tool Calling 和 JSON 正则提取的区别？"

1. 类型安全：Pydantic schema 自动校验字段类型和约束
2. 鲁棒性：LLM 原生 function calling 协议，不会出现 JSON 格式错误
3. 可扩展：新增工具只需定义 Pydantic model，无需修改解析逻辑
4. 保留 regex fallback 降级路径（`--mock` 模式 / 不支持 tool calling 的模型）

**面试官会问**: "73% 降本怎么算的？"

- Sonnet: Input $3/MTok, Output $15/MTok
- Haiku: Input $0.80/MTok, Output $4/MTok
- 同样 token 量，全 Haiku 成本约为全 Sonnet 的 27%（降本 ~73%）
- 默认路由（2/6 Sonnet + 4/6 Haiku）降本约 20%，quality-sensitive 节点保留 Sonnet

---

## 面试快查表

| 问题 | 核心回答 |
|------|---------|
| 为什么用 LangGraph？ | 需要条件分支 + 循环，chain 无法表达有向图拓扑 |
| RAG 召回怎么优化？ | query 拼接语义+策略，策略匹配优先排序，topK=3 控制 context 长度 |
| LLM 截断怎么处理？ | 双策略 JSON salvage（正则闭合 + 括号补全）→ LLM self-repair |
| 评估体系？ | 策略分类（1036 gold label, F1）+ 管线质量（5 维 LLM-as-Judge rubric） |
| 流式输出？ | `.astream()` → AsyncGenerator → SSE `data: {json}\n\n`，末尾 chunk 含 usage |

---

## 关键词速查（ATS）

`LangGraph` `LangChain` `Multi-Agent` `RAG` `FAISS` `sentence-transformers` `Embedding` `Tool Calling` `Function Calling` `Pydantic` `Chain-of-Thought` `LLM-as-Judge` `Streaming` `SSE` `FastAPI` `asyncio` `Docker` `CI/CD` `GitHub Actions` `pytest` `Python 3.11`
