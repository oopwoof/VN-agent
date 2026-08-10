# VN-Agent 设计决策与 Why

> 稳定区文档。记录关键架构选择的"为什么"——避免下次重新争论同样的问题。
> 每条决策：① 一句话声明 ② 取舍背景 ③ 反驳意见为什么没采纳。
> 遇到新的值得记的决策，随手往下加。历史代码 refactor 不必追溯补齐。

---

## 1. Agent 拆成独立节点（vs 一个大 prompt）

**决策**：Director / StructureReviewer / StateOrchestrator / Writer / DialogueReviewer / CharacterDesigner / SceneArtist / MusicDirector 各自独立 LangGraph node，不合并。

**为什么**：
- 每个 Agent 输出 schema 不同（VNScript vs CharacterProfile vs BGMPlan），合并后 JSON 稳定性下降
- 模型路由粒度：Sonnet 留给 Director / Writer，Haiku 承担 StateOrchestrator / Summarizer / Reviewer（参 [决策 #5](#5-haiku-承担-summarize--review--metadatavs-全-sonnet)）
- Prompt 注意力不稀释——单 Agent 只关心一个决策域
- 并行：无依赖的 Agent（CharacterDesigner / SceneArtist / MusicDirector）可 `asyncio.gather`

**反驳没采纳**："一次 API call 成本更低" —— Sonnet pricing 按 token 不按 call，拆开每个 call 更短反而便宜

---

## 2. LangGraph StateGraph（vs SequentialChain / CrewAI）

**决策**：用 LangGraph 的 StateGraph + conditional_edges。

**为什么**：
- 修订循环（Reviewer FAIL → Writer）是 DAG 带回边的形状，SequentialChain 无法表达
- StateGraph 的共享 `AgentState` 比手写参数透传清晰
- CrewAI 是角色扮演协作范式，不适合严格流程控制

---

## 3. state_writes 声明式白名单（vs 自由字符串）

**决策**：`scene.state_writes: dict[str, Any]` 只能写 `VNScript.world_variables` 里声明过的 var，StructureReviewer 会 reject 未声明 var。

**为什么**：
- Compiler 可确定性 emit Ren'Py `$ var = value`
- StructureReviewer 可静态 lint（type + vocabulary）
- `local_regen` 可按 scene 重放 state_writes fold world_state
- 自由字符串等于给 Ren'Py compile 埋雷

**延伸**：整个系统的"声明式白名单"哲学——`transforms.rpy.j2` 特效白名单、`emotions.py` 情感词表单源、`renpy_safe` 转义白名单——都是同一条原则。新增功能（见 [ARCHITECTURE.md](./ARCHITECTURE.md) 路线三）要沿用这个。

---

## 4. Literary mode 默认（vs RAG few-shot 注入默认）

**决策**：Writer 默认走 literary mode（不注入 RAG examples），action mode 才注入 k=2-4 样本。

**为什么**：
- RAG 注入的是"别人的对话"，会压制 Writer 的 character voice 一致性（Sprint 7-5 评测：literary 4.17 > action 3.92）
- 长篇 (50+ scene) voice drift 风险更大
- 想要的是风格规范 + 节奏骨架，不是字面句子（见 [ARCHITECTURE.md](./ARCHITECTURE.md) 路线一 A 通道"防对齐诅咒"）

**为什么没换微调**：
- 1k 标注语料规模太小（SFT/DPO 需要 10k+）
- Anthropic 当前不开 Sonnet 微调
- literary-mode 已经通过 prompt + CoT 达到目标，RAG-less 不是缺陷而是设计

---

## 5. Haiku 承担 summarize / review / metadata（vs 全 Sonnet）

**决策**：Summarizer / DialogueReviewer (Python pre-gate pass) / LoreIndex metadata tagging / StateOrchestrator 全走 Haiku。

**为什么**：
- 这些任务是结构化抽取 + 判断，非创作
- Haiku 单价 $0.80/$4 vs Sonnet $3/$15，成本 ~27%
- 50 scene × 10 chapter rollup × 多轮 revision = 上百 call，Sonnet 烧不起

**反驳没采纳**："Haiku 质量差" —— 评测数据显示结构化任务 Haiku / Sonnet 差 <5%，且 Python pre-gate 兜底

---

## 6. Anthropic key pool + exp backoff（Phase 13-1 Step 1）

**决策**：多个 Anthropic API key 轮询，429 自动切换，exp backoff 重试。

**为什么**：
- 单 key Tier 1 RPM 对 50+ scene + 并行 asset gen 不够
- Key pool 让 Writer 场景级并行（[ARCHITECTURE.md](./ARCHITECTURE.md) 路线四）变可行
- Backoff 防止连锁 429 打爆所有 key

---

## 7. Monolithic prefix + 1h cache tier（Phase 13-1 Step 3）

**决策**：LLM call 的 system prompt + always_lore 合成**单块** prefix，用 Anthropic prompt caching `ephemeral` + 1h TTL tier。

**为什么**：
- 多块 prefix → 缓存命中粒度细但失效概率叠加
- 1h tier 比 5min 贵但长篇生成（Writer + Reviewer 多轮 call）命中率翻倍
- Cache 命中 90% 折扣 → 成本模型反转，"堆相关 lore 填满 context" 变可行

**前置**：Sprint 8-4 已启 ephemeral caching；Step 3 把多块合一 + 升 TTL

---

## 8. Scope tagging for lore entities (always / chapter / scene)

**决策**：`AnnotatedSession` 加 `scope` 字段，`always` 类实体（premise / 主角）直接 prepend system prompt，不进 FAISS top-k。

**为什么**：
- 观察：cosine 不利场景会把 premise card 从 top-k 踢掉，Writer 失去故事罗盘
- top-k budget 本来稀缺，留给真动态的 location / callback
- always 段配合 1h 缓存近乎零成本

**现状**：Phase 13-1 Step 3 已落；截断优先级修复详见 [AUDITS.md](./AUDITS.md) 第 1 节

---

## 9. dialogue_hash 去重 summary（Phase 13-1 Step 4）

**决策**：`Scene.summary` 带 `dialogue_hash`，next pass 对比 hash 一致则跳过 Haiku summarize。

**为什么**：
- Reviewer FAIL → run_writer 从头跑，每场重 fire Haiku summary 是浪费（6 × 3 = 18 × 正确数 6）
- 比 `if not summary` 守卫更鲁棒——不用依赖"清空"动作，`local_regen` 改了 dialogue hash 就变

---

## 10. Director 声明式 context_deps（Phase 13-1 Step 5）

**决策**：Director 在 outline 阶段为每个 scene 声明 `context_deps: list[str]`（指向前序 scene_id），Reviewer 验证 DAG 合法性，Writer 按 deps 注入对应 scene 的 summary 到 prompt。

**为什么**：
- Director 最清楚本场景的叙事依赖（callback / 承接 / 反转）
- 让 Reviewer 能静态 lint "dep 指到不存在的 scene" 这类错误
- 为 Writer 场景级并行（[ARCHITECTURE.md](./ARCHITECTURE.md) 路线四）铺 schema——并行调度器按 deps DAG 拓扑排序

---

## 11. Tool calling with Pydantic bind_tools（vs regex JSON）

**决策**：Director / Writer / Reviewer / CharacterDesigner / SceneArtist 都用 `ainvoke_with_tools` + Pydantic schema；regex fallback 只留给不支持 tool calling 的模型 / mock 模式。

**为什么**：
- Anthropic 原生 tool calling 格式稳定，比 `json.loads(re.search(...))` 可靠
- Pydantic 自动 validation 比手写 field check 简洁
- 扩字段只需改 Pydantic，不改 parser

---

## 12. neutral-first sprite + 延后批量抠图（Sprint 12-3b）

**决策**：CharacterDesigner 先生 neutral（作为 reference），再 img2img 推 happy / sad，全部生成完才批量 rembg 抠图。

**为什么**：
- Nano Banana 拿透明 PNG 当 reference 会当 silhouette 解读，情感一致性崩
- 延后抠图保证参考链里 neutral 是不透明彩图
- Prompt 里加 `soft off-white studio background` + `NOT a silhouette` 对冲同一 bug

---

## 13. rembg u2net_human_seg as optional dependency（Sprint 12-3b）

**决策**：rembg + onnxruntime 列 `[project.optional-dependencies] cutout`；未装则 sprite 保留纯色底，不崩。

**为什么**：
- 依赖 ~270MB（onnxruntime 100MB + u2net 170MB），CI 和没 GPU 的笔记本不需要
- 不装依然跑通 pipeline —— graceful degradation
- `u2net_human_seg`（不是 `u2net`）选角色专属头，边缘更干净

---

## 14. StructureReviewer 非阻塞（vs Exception raise）

**决策**：Reviewer 发现问题写 `state["structure_review_issues"]` 列表，不 raise —— Writer 在下一轮看到 issues 自己修。

**为什么**：
- LLM 生成本身不稳定，raise 会频繁杀掉整个 run
- Issues 作为 Writer prompt 输入 = 反馈闭环
- Revision 硬上限（3 轮）兜底，超了强制前进

---

## 15. FAISS IndexFlatIP（vs Pinecone / Weaviate）

**决策**：~1k 条语料用 FAISS flat 内存索引。

**为什么**：
- 1k 向量 × 384 维 ≈ 1.5MB 内存，暴力搜索 <1ms
- 向量数据库需部署 + 版本管理 + 网络 RTT，over-engineered
- 降级链：FAISS → numpy 暴力 → label filter fallback

---

## 16. BG PIL resize 1920×1080 强制（Sprint 12-3c）

**决策**：Nano Banana 输出 1344×768（"16:9" 唯一 ratio knob），生成后 PIL LANCZOS resize 到 Ren'Py 原生 1920×1080。

**为什么**：
- Ren'Py `scene bg_x` 默认 native size 居中画，不 resize 有 ~288px 黑边
- LANCZOS 对 1.4× 上采样质量足够
- 宁可后期 resize 也不用 Ren'Py 的 zoom/scale（那会耦合显示层 transform）

---

## 17. Emotion 词表单源（Sprint 12-3c sync tails）

**决策**：`src/vn_agent/schema/emotions.py` 是唯一源，reviewer 和 renpy_compiler 都 import；前端通过 `/api/constants/emotions` 端点拉同一份。

**为什么**：
- Writer / CharacterDesigner / Reviewer 三处独立硬编码 emotion list 曾经导致不对齐
- 单源 + 派发规避 drift
- 前端 TypeScript 也要对齐，不能硬编码副本

---

_遇到新的"为什么我们这样做而不那样做"的决策时，随手加一条。每条保持短、聚焦一个选择，别写成散文。_
