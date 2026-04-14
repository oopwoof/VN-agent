# VN-Agent — 简历项目描述 (v2, 2026-04-14)

> **与 v1 的差异**：v1 聚焦 6-Agent DAG + 单轨 RAG + 多模型路由的基础架构；v2 增补了 Sprint 7–12 的新能力——**双轨 RAG（dialogue + lore pivot）**、**长文本一致性三层记忆**（Character Bible / 递归摘要 / Symbolic World State）、**StructureReviewer 早拦截**、**Persona fingerprint 审计**、**Sprint 8-5 sweep 数据驱动的 writer_mode 决策**、**单场景热重写**、**双评审员交叉验证**。Bullet 从"能搭"升级到"能用数据迭代"。

---

## 写作原则

- **Agent**：证明你在解决真实业务，不是搭 toy。核心是**工作流设计能力**——如何把多步骤、多工具、有依赖的复杂任务拆成合理组件。每个 bullet 体现"端到端解决复杂问题"。
- **RAG**：证明你能把 50% 优化到 95%。价值是系统化优化方法论：**诊断 → 方案选择 → 量化结果**。
- **长文本生成**（v2 新增）：证明你理解 LLM 的上下文与一致性问题。长篇 VN（20+ 场景）不是把 Writer 调 20 次，而是要解决**角色语言漂移、世界状态一致性、跨场景逻辑连贯**的结构性挑战。

---

## 简历条目（终稿，3 bullet）

**VN-Agent：基于多 Agent 架构的 AI 视觉小说自动生成系统** | Python · LangGraph · FAISS · Ren'Py &emsp; 11/2025—04/2026

- **架构**：单次 LLM 调用难以稳定生成完整游戏（prompt 膨胀致输出截断/格式崩坏），拆解为 LangGraph 多 Agent DAG + 黑板共享状态——Director 两步规划（大纲 → 导航）、**StructureReviewer 在 Writer 启动前审核大纲**（检查策略分布 + 分支意图对齐，不合格直接回 Director 修改，避免浪费 6 次 Sonnet 对话生成）、Writer↔DialogueReviewer 条件边驱动的 3 轮修订循环、资产阶段 3 Agent 并发 + `return_exceptions` 故障隔离；实现从一行主题到含多分支剧情、立绘、BGM 的完整可运行 Ren'Py 项目的端到端生成，配套 React 分步交互前端 + **单场景热重写（local regen + per-scene snapshots）**
- **算法**：分析 Reviewer FAIL 反馈定位瓶颈为 Writer 上下文不足，建立**双轨 RAG 体系**——(1) 对话 few-shot 检索（1,036 条 COLX_523 语料 + FAISS IndexFlatIP + 策略硬过滤），策略分类 F1 提升 **57%**（0.21→0.34）；(2) **Lore 实体检索（Sprint 10-2 pivot）**——Sprint 7 literary 模式禁用对话 few-shot（风格污染 Sonnet 文学潜空间）后同一套检索基础设施**转用于召回角色/场景/世界变量等事实性实体**，`rag_retrievals.jsonl` 全链路审计；**Sprint 8-5 sweep 数据驱动**：literary (4.17) > action (3.92) > self-refine (3.45) > baseline (3.25)，数据翻盘 writer_mode 默认值；质量闭环由 LLM-as-Judge 5 维度 rubric + BFS 可达性 + 分支意图对齐 + Persona fingerprint 声音漂移审计四层构成，**Sonnet 自评 + GPT-4o 独立交叉验证**规避"同模型自评"偏差
- **工程**：长文本生成一致性工程——**Character Bible 作为 prompt-cached system suffix**（Anthropic ephemeral cache，首次 1.25× 后续 0.1×，6-18 次 Writer 调用共享）、**递归逐场景摘要**（Haiku 低温度翻译工作，超过 15 场景时启用）压缩历史、**Symbolic World State + state_orchestrator**（布尔/整型状态变量翻译为自然语言约束注入 Writer，防止"已读过手稿却又表现得第一次发现"）；Tool Calling（Pydantic schema）消除 JSON 解析失败 + 双策略 salvage（反向闭合 + 正向括号计数）+ LLM self-repair；多模型分级路由（Sonnet 创造 / Haiku 翻译类廉价工作）预算模式降本 **~73%**；FastAPI 异步 Web API + Docker 多阶段 + GitHub Actions CI（165 测试 + 覆盖率 60% 门控）

---

## 核心能力矩阵（v2 扩展）

| 能力维度 | 具体技术点（★ = v2 新增） | 对应面试问题 |
|---------|-----------|-------------|
| **多 Agent 编排** | LangGraph StateGraph、条件边、循环、并行节点、Span 追踪、★ StructureReviewer 早拦截 | "为什么拆成这么多 Agent？" |
| **结构化输出** | Tool Calling（Pydantic）、双策略 JSON salvage、LLM self-repair | "LLM 输出不稳定怎么保障？" |
| **RAG 方法论** | Query 拼策略标签、FAISS、硬过滤、★ 双轨检索（few-shot + lore pivot） | "RAG 怎么优化？不是只搭了流程吧？" |
| ★ **长文本一致性** | Character Bible（prompt caching）、递归场景摘要、Symbolic World State、Persona fingerprint | "20 场景的 VN 怎么保证角色不漂移？" |
| **质量闭环** | 5 维度 LLM-as-Judge、BFS 可达性、★ 分支意图对齐、★ 双评审员（Sonnet + GPT-4o） | "怎么评估生成质量？" |
| **数据驱动迭代** | ★ Sprint 8-5 sweep（writer_mode 翻盘决策）、★ rag_retrievals.jsonl 审计 | "你的技术决策有数据支撑吗？" |
| **成本优化** | 多模型路由、prompt caching、Haiku 做翻译类廉价工作 | "73% 降本怎么算的？" |
| **工程成熟度** | FastAPI + SSE、SQLite、Docker、CI 门控、165 测试、mock LLM、★ local regen | "测试和 CI 怎么做的？" |

---

## 数据真实性自查（v2 新条目）

### v1 已有（仍有效）
6 Agent DAG · 资产并行 · 条件边 3 轮修订 · 1,036 标注语料 · FAISS IndexFlatIP · Tool Calling · SSE 流式 · 多模型路由 · 73% 降本计算 · 165 测试 · 17 API 端点 · React 9 组件 · Reviewer 5 维度 rubric。

### v2 新增可验证声明

| 声明 | 来源 | 可验证？ |
|------|------|---------|
| StructureReviewer 大纲审查 | `src/vn_agent/agents/structure_reviewer.py`（Sprint 7-5） | 代码 |
| Lore 实体检索（RAG pivot） | `src/vn_agent/eval/lore.py`（Sprint 10-2） | 代码 |
| RAG 审计轨迹 | `demo_output/*/rag_retrievals.jsonl`（每条 query/retrieved 落盘） | 文件 |
| Character Bible prompt caching | `config.enable_prompt_caching=True`（Sprint 11-2） | config |
| 递归场景摘要 | `src/vn_agent/agents/summarizer.py`（Sprint 11-1），temp=0.2 | 代码 |
| Symbolic World State | `src/vn_agent/agents/state_orchestrator.py`（Sprint 9-6） | 代码 |
| Persona fingerprint 审计 | `src/vn_agent/agents/persona_audit.py`（Sprint 11-3），零 LLM | 代码 |
| 双评审员（Sonnet + GPT-4o） | `config.llm_judge_model_secondary="gpt-4o"`（Sprint 8-1） | config |
| writer_mode literary/action | `config.writer_mode` + Sprint 8-5 sweep 注释 | config |
| 单场景热重写 | `src/vn_agent/agents/local_regen.py`（Sprint 12-4）+ `snapshots/*.json` | 代码 + 文件 |
| Unknown characters resolver | `src/vn_agent/agents/unknown_chars.py`（Sprint 12-5） | 代码 |
| Nano Banana（Gemini 2.5 Flash Image） | `config.image_provider` + fallback chain（Sprint 10-1） | config |
| rembg 立绘透明抠图 | `u2net_human_seg` 模型 | 代码 |

---

## 评估实测数据（v2 新增 sweep 数据）

### 策略分类评估（v1 已有，保留）

| 方法 | Accuracy | Macro F1 |
|------|----------|----------|
| 随机基线 (1/6) | 16.7% | — |
| Keyword 规则 | 23.0% | 0.21 |
| **qwen2.5:7b LLM** | **35.0%** | **0.34 (+57%)** |

### ★ Sprint 8-5 Writer 模式 sweep（v2 新增，LLM-as-Judge 5 维度平均分）

| Writer 策略 | 平均分 (1-5) | 备注 |
|------------|---------|------|
| `baseline_single`（单次全生成） | 3.25 | Sonnet 无修订原生输出 |
| `baseline_self_refine`（单模型自评自改） | 3.45 | +0.20 |
| `action`（strategy + few-shot）| 3.92 | Sprint 7 默认 |
| **`literary`（physics prompt，零 few-shot）** | **4.17** | **Sprint 8-5 翻盘为新默认** |

→ **关键发现**：literary 在**两个主题**（含动作主题）上都击败 action（动作主题 4.5 vs 4.17），证明 few-shot 反而污染 Sonnet 的文学潜在空间——这是 Sprint 10-2 RAG pivot（保留基建、转向 lore 检索）的直接动机。

### 结构校验（v1 已有，保留）

4 类缺陷（start_scene / branch_refs / BFS 可达 / character 一致性）→ **100% 检出率**（6/6 对抗用例）。

### 成本分析（v1 已有 + v2 新增 caching）

| 方案 | 相对全 Sonnet |
|------|---------------|
| 全 Sonnet | 100%（基线） |
| 默认路由（Director/Writer Sonnet + 其他 Haiku） | ~80% |
| 预算模式（全 Haiku） | **~27%（−73%）** |
| ★ Prompt caching 启用后 Writer 重复调用 | 首次 1.25×，5min 内复用 **0.1×** |

---

## Bullet 拆解 & 面试引导（v2 扩展）

### Bullet 1 — Agent 工作流设计（新增 StructureReviewer 洞察）

**追问**: "StructureReviewer 为什么要加？"
- 动机：Director 大纲可能有结构问题（如两个分支都"工作"但语义指向错误场景），Writer 生成完 6 个场景对话后才被 DialogueReviewer 拦截 → 浪费 6 次 Sonnet 调用
- **早拦截哲学**：问题越早发现越便宜。Outline 阶段就审，不合格回 Director，省钱
- 两类审查：narrative shape（策略分布 / 角色数合理性 / 故事弧完整性）+ branch intent alignment（选项文本意图 vs 下游场景描述）

### Bullet 2 — RAG 方法论（新增 Lore Pivot 杀手锏）

**追问（杀手锏）**: "Lore 检索是什么？跟 few-shot 有区别吗？"
- **问题发现**：Sprint 7 上线 literary 模式后禁用了原始对话 few-shot 注入（JRPG/galgame 风格污染 Sonnet 文学潜空间），但 FAISS 基建还在跑 → "RAG 变成花瓶"
- **Pivot**：同一套检索基础设施转用于检索**事实性实体**（角色背景、场景描述、世界变量、故事前提），而非风格模仿
- **关键设计**：
  - Lore 从 Director 输出里 extract（不新增 LLM 调用，不改 schema）
  - Per-run 内存索引（不污染主 disk 索引，每个主题 bespoke）
  - 强制 `AnnotatedSession(strategy=None)` 复用 `EmbeddingIndex.search`
  - 在 literary + action **两种模式都开**（facts 不污染风格）
- **成本**：~80ms 建索引 + ~$0.008/run，噪声级别
- **面试价值**：展示"不扔掉基建，反而找到新用途"的工程判断力 + 从 sweep 数据中读出风格污染问题的诊断能力

### Bullet 3 — 长文本一致性（v2 全新方向）

**追问**: "20 场景的 VN 怎么保证角色不漂移？"

**三层记忆体系**：
1. **Character Bible（Sprint 11-2）**: 角色定义作为 **prompt-cached system suffix**，Anthropic ephemeral cache（首次 1.25×，5min 内 0.1×），6-18 次 Writer 调用共享 → 每次 Writer 都带完整角色背景，不用担心随机漂移
2. **Sliding window（Sprint 7-2）**: 最近 N 场景完整对话注入 Writer prompt，保持局部连贯（`writer_context_window`）
3. **Recursive summarization（Sprint 11-1）**: 更老的场景用 Haiku（temp=0.2 近确定性）压到 ≤100 词摘要，避免 context 爆炸；**默认 OFF**，≥15 场景时开启（短 run 不付这笔钱）

**零成本声音审计（Sprint 11-3）**：
- Persona fingerprint：Director 为每个角色声明 `speech_fingerprint` 特征（用词/句式/口头禅）
- 纯 Python substring + keyword 匹配检查对话里是否出现 → 漂移时写入 Reviewer feedback
- 只在 ≥10 场景时触发，短 run 短路；**false positive 优于 false negative**，只作提示不触发强制修订

**符号状态注入（Sprint 9-6）**：
- Director 定义布尔/整型状态变量（`manuscript_read: True`、`affinity_kael_mira: 6`）
- 每个场景声明 `state_reads`（读哪些变量）
- `state_orchestrator` 用 Haiku 把"manuscript_read=True" 翻译成 "Mira has already read the manuscript. Do not have her react as if discovering it for the first time."
- 注入 Writer prompt → 创作与逻辑解耦

**追问**: "Tool Calling 和 JSON 正则的区别？"
1. 类型安全（Pydantic 自动校验）
2. 鲁棒性（LLM 原生协议）
3. 可扩展（新工具只需 Pydantic model）
4. 保留 regex fallback（mock / 不支持的模型）

**追问**: "73% 降本怎么算的？"
- Sonnet $3/$15 per MTok vs Haiku $0.80/$4
- 全 Haiku ≈ 全 Sonnet 的 27%
- **关键洞察（v2 强化）**：把 Haiku 用在"翻译类廉价工作"——summarizer、state_orchestrator、scene_artist prompt、character_designer、reviewer 结构审查；Sonnet 只留给 Director/Writer 真正需要创造力的节点

---

## 面试快查表（v2 扩展）

| 问题 | 核心回答 |
|------|---------|
| 为什么用 LangGraph？ | 需要条件边 + 循环，DAG 拓扑，chain 无法表达 |
| RAG 怎么优化？ | Query 拼策略标签 + FAISS 召回 + 硬过滤 + 双轨（dialogue few-shot / lore 实体） |
| LLM 截断怎么处理？ | 双策略 JSON salvage（反向闭合 + 正向括号计数）→ LLM self-repair |
| ★ 长文本一致性？ | Character Bible 缓存 + 滑窗对话 + 递归摘要 + persona audit + 符号状态 |
| 怎么评估生成质量？ | 策略分类 F1 + 5 维 LLM-as-Judge + Sonnet/GPT-4o 交叉验证 |
| 流式输出？ | `.astream()` → AsyncGenerator → SSE `data: {json}\n\n` |
| ★ Sprint 8-5 sweep 发现？ | literary 4.17 > action 3.92，physics prompt 击败 few-shot，驱动 RAG pivot |
| ★ StructureReviewer 为什么？ | 大纲阶段拦截结构问题，省下 6 次 Sonnet 对话生成的钱 |
| ★ Lore pivot 是什么？ | 同一套 FAISS 基建从"风格 few-shot"转向"事实实体检索"，不污染 Sonnet 文学空间 |

---

## 关键词速查（ATS 友好，v2 扩展）

`LangGraph` · `StateGraph` · `Conditional Edges` · `Multi-Agent` · `RAG` · `FAISS` · `IndexFlatIP` · `Sentence-Transformers` · `LLM-as-Judge` · `Tool Calling` · `Pydantic` · **★`Prompt Caching`** · **★`Character Bible`** · **★`Symbolic World State`** · **★`Persona Fingerprint`** · `Anthropic Claude` · `Sonnet` · `Haiku` · `GPT-4o` · **★`Gemini 2.5 Flash Image`** · `FastAPI` · `SSE` · `asyncio.gather` · `Docker` · `GitHub Actions` · `pytest` · `mypy` · `ruff` · `Ren'Py` · `BFS` · `React` · `TypeScript` · `Zustand` · `SQLite`
