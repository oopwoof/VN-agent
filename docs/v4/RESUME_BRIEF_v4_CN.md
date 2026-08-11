# VN-Agent — 简历简报（v4，更新于 2026-08-10，新增 P6 前端改版；取代 2026-07-19 草稿中 P2-P5 的过时状态）

> **用途**：供下游 LLM 使用的唯一事实来源简报，用于针对具体 JD 生成 **AI 产品经理（校招）**简历要点与面试话术。本文档信息完备；下游 LLM 无需打开仓库。
>
> **风格约束**：每项量化声明均标注证据路径或 commit hash。愿景性/尚未实测的声明标记为 `(愿景目标，aspirational)`。仅在技术术语、产品名、模型名、代码标识符等必要场景保留英文。

---

## 0. 核心摘要（LLM 上下文头部）

**项目定位（一句话）**：VN-Agent 是一个使用 LangGraph 多 Agent 流水线，将“一句话故事主题”转化为“可玩视觉小说”的 AI 工作台产品；项目从工程 demo 起步，在 v4 阶段升级为面向创作者的 Chat Ops 平台，全程作为 AI 产品经理校招中**产品决策 + AgentOps + 数据飞轮**的叙事载体。

**角色**：独立贡献者/负责人。**这是一个个人项目，借助 Claude Code + Gemini 作为结对编程工具进行 AI 增强开发**。产品经理决策（方向优先级、备选方案评估、成本模型）由候选人负责；代码在大量 AI 辅助下实现。坦诚这一点是优势而非负担——面试官真正想判断的是“你能否端到端推动一个 AI 产品”，而独立借助工具交付 166 个 commit + 15.8K 行代码，比假装全部手写更能说明能力。

**电梯陈述锚点（根据 JD 选择一个）**：
- **AgentOps 评测底座**——3 层 Reviewer + token/成本观测 + Pearson r 跨模型评审（r=0.643）
- **数据飞轮 M0 已跑通**——👍/👎 → BM25 injector → Reflection Agent（Haiku）；闭环已存在，但用户数据较薄
- **多源素材融合避免同质化**——上传 + 联网检索（search-agent）+ 本地开源库 + LLM 生成四通道 + 版权白名单 gate
- **成本模型经过量化**——6-scene 约 $1.7 实测 + prompt caching 复用成本 0.1× + 单元经济性测算表（Pro $29，设有用量限制）
- **六阶段路线全部闭环（P0→P5，2026-07-27，M0 级别全部交付）**——从一句话主题到"实时流式播放 + 对话式编辑 + 一键体检报告 + 一键 Autopilot 直接播放"的完整工作台，不是单点 demo
- **AI 安全自纠错的真实案例**——做 P5 时一次 CLI 冒烟测试意外触发了 5 次真实 API 调用（$0.12），当场识别根因、主动披露、修复并加回归测试锁死；这是 AgentOps 诚实文化的活案例，不是编的故事
- **P6 前端改版：把不可见的多 Agent 流水线做成产品主舞台**（2026-08-10，17 个 commit）——后端 `graph.astream()` 每个节点的事件此前被压成一个字符串、前端再用子串匹配猜回来；改成 `publish_node` → SSE `node` 事件 → `pipelineNodes` → `PipelineGraph` 的结构化链路，顺带补齐 10 个节点里缺的 6 个标签、修掉一个"进度条第 2 格永远走不到"的潜伏 bug，并做了 zh/en 全量 i18n（209 个 key 对齐）

---

## 1. 产品背景

**VN-Agent 是什么**：一款将“一句话主题”转化为可运行视觉小说（Ren'Py 项目 + Web 可玩输出）的工具。底层流程为：LangGraph 状态机 → Director（大纲）→ StructureReviewer（Sonnet，非阻塞）→ StateOrchestrator（Haiku，将符号状态转为自然语言约束）→ Thinking-fanout（按场景扇出）→ Writer（Sonnet，wave-barrier 并行）→ DialogueReviewer（3 层：结构 + 机械规则 + 5 维质量）→ Asset agents（并行，Nano Banana + rembg）→ Ren'Py 编译器。多模态输出包括：脚本、角色立绘、背景和 BGM 提示。

**为什么适合 AI 产品经理岗位**：
- 这不是另一个聊天机器人 demo，而是一条具有真实可观测性、成本追踪与质量 gate 的**多 Agent 生产流水线**；其产品形态更接近 Cursor / Perplexity / Notion AI，而非“套壳 ChatGPT”。
- AI 产品经理面试中的典型问题——如何避免输出同质化、人机协作 UX、评测/AgentOps、LLM 成本压力下的商业化、数据飞轮——在这里都有已交付代码作为答案，而不只是幻灯片。
- 长篇（50-scene）生成迫使产品直面**长上下文一致性**。这正是面试官判断候选人是否真正理解 LLM 局限，而非只会“继续堆 prompt”的关键信号。

**用户与使用场景（一段话）**：核心用户是有故事创意、但缺乏引擎技能和美术资源的**独立视觉小说创作者/学生 UP 主**。当前痛点包括：Ren'Py 学习曲线陡峭，定制美术成本高，且缺少快速反馈闭环。VN-Agent 让用户通过工作台对话运行完整的 6-Agent 流水线；用户可以上传自己的世界观笔记、检索开源素材，并导出可运行的 Ren'Py 项目或 Web 可玩分享链接。次要的“Autopilot”入口面向潜在*玩家*：输入一句话后，约 8 分钟内获得可玩内容（愿景目标，aspirational target）。

---

## 2. 实际已交付内容（经仓库验证）

### 2.1 v3（v4 之前）——技术主干（Phase 1 → Phase 13-3）

| 功能 | 产品动机 | 技术方案 | 证据 |
|---|---|---|---|
| 6-Agent LangGraph DAG（Director / StructureReviewer / StateOrch / Thinking / Writer / DialogueReviewer / Assets） | 单 prompt 生成会被截断且 JSON 易损坏 | 条件边、3 轮修订循环；素材阶段使用 `asyncio.gather` + `return_exceptions=True` 隔离故障 | `src/vn_agent/agents/graph.py` |
| 两层 Reviewer + 智能路由 | Reviewer 过去遇到每个 FAIL 都会“退回 Writer”，但图结构类失败（如场景不可达）并非 Writer 能解决 | 增加 `ReviewResult.can_writer_fix` 字段；纯函数 `decide_retry_target` 分发至 Director/Writer/Accept | `src/vn_agent/agents/reviewer.py:30`、`src/vn_agent/agents/routing.py`、commit `8a2ac88` |
| 符号化 World State + StateOrchestrator | 长篇视觉小说会发生状态漂移（“Mira 在 ch2 已读过手稿，之后却再次阅读”） | Director 声明 boolean/int 变量；Haiku 将其翻译为自然语言约束并注入 Writer prompt | `src/vn_agent/agents/state_orchestrator.py`（Sprint 9-6） |
| 面向长篇的三层记忆（**全局缓存 + 章节折叠 + 局部检索**） | Sonnet 上下文并非无限；简单注入全部历史会浪费缓存 | ① 全局缓存：Character Bible → `cache_control=ephemeral`（`enable_prompt_caching=True`，首次 1.25×，5 分钟内复用 0.1×）；② 章节折叠：`enable_chapter_rollup=True`（每 10 scenes 异步 rollup，200–800 词动态长度，<10 scenes 跳过），另有逐场景摘要 `enable_scene_summarization=False` 需 ≥15 scenes 手动开；③ 局部检索：`use_lore_retrieval=True`、`lore_k=4`（`eval/lore.py`，always/chapter/scene 三 scope）。**滑动窗口 `writer_context_window` 是第四个开关，默认 0（关）**——早期文档误记为「三层之一、默认 N=2」，以代码为准 | `config.py:166/199-223`、`src/vn_agent/agents/summarizer.py`、`eval/lore.py`、`state_orchestrator.py`、Sprint 11-1/11-2/11-3 |
| 双 Judge 交叉验证（Sonnet + GPT-4o） | Sonnet 评审 Sonnet 会形成回音室；4.17 的自评分缺乏说服力 | Sonnet 3.68 vs GPT-4o 3.66，**Pearson r=0.643，±1 分一致率=87%** | `docs/PRODUCT.md` §关键指标、commit `4f1228f` |
| 8-cell `writer_mode` 扫描实验（数据驱动切换默认值） | `writer_mode=action`（few-shot RAG）原为默认值，但缺少数据验证 | 8-cell 扫描 {literary, action, baseline_self_refine, baseline_single} × {lighthouse, dragon} → **literary 4.17 > action 3.92 > self_refine 3.45 > baseline 3.25**，默认值由此切换为 literary | Sprint 8-5、扫描结果 JSONL 日志、`config.py` 的 writer_mode 注释 |
| RAG 转向（对话 → 世界观/实体检索） | literary 模式禁用对话 few-shot 后，“RAG 成了花瓶” | 复用 FAISS + sentence-transformers 基础设施，改为检索角色/地点/世界变量实体；每次运行使用内存索引，不增加 LLM | `src/vn_agent/eval/lore.py`、Sprint 10-2 |
| BM25 + 加权 RRF 混合检索 | 纯 FAISS 会漏掉策略标签的词法匹配 | `rank_bm25` 权重 0.3 + FAISS 权重 0.7 | Sprint 6-4、`rank_bm25` 依赖 |
| 基于 `ContextVar` 的单请求 `TokenTracker` | 模块级单例会在并发任务间产生数据污染 | 使用 ContextVar 限定 tracker 作用域，并随 blackboard 持久化 | `src/vn_agent/services/token_tracker.py`、Sprint 6-5 |
| Anthropic Key Pool + 指数退避 + Sonnet/Haiku 分池 | 单个 key 遭遇 429 会导致整条流水线失败 | round-robin + 单 key 冷却 + tenacity jitter | `src/vn_agent/services/llm.py:_pool_for`、commit `95b8b97` |
| 压力测试器的健康信号 gate | 低成本层级已出现劣化后，50-scene 层级仍会消耗 $15 | 根据重试密度/key 轮换/运行时长执行 `_compute_health_signals`；支持 `--abort-on-degradation` | `scripts/smoke_longvn.py:109`、`scripts/stress_runner.sh`、commit `745e03d` |
| Anthropic Tool Use 结构化输出 + Writer 三级恢复链 | M0 运行中因 `max_tokens` 导致的截断率为 89%（16/18） | 使用 Tool Use 约束 schema；恢复顺序为 JSON array → 逐对象花括号扫描 → continuation call | `src/vn_agent/schema/script.py:418`、`writer.py:_parse_dialogue`、commits `05db6d8`、`441fbc6` |
| Ren'Py 编译器（Jinja2）+ rembg `u2net_human_seg` 人像抠图 + Nano Banana 图像 provider | 全流程输出为可直接执行 `renpy launch` 的 Ren'Py 工程 | 见 Phase 13 Sprint 10-1（Nano Banana + fallback chain）、Sprint 12-3b（rembg）、Sprint 12-3c（视觉层） | `src/vn_agent/compiler/`、`character_designer.py`、`scene_artist.py` |

**v3 汇总**：共 166 个 commit · 约 15.8K 行 src · 约 12.4K 行 tests · **659 个单元测试通过**（`docs/v3/SHOWCASE_v3.md`；随着 v4 P0/P1 新增测试，确切数字可能上下浮动约 20，但量级不变）。

### 2.2 v4 P0（多源素材融合 M0）——刚刚交付

| 功能 | 产品动机 | 技术方案 | 证据（commit） |
|---|---|---|---|
| 文本上传通道（md/pdf/docx → 分块 + 向量化 → lore RAG 中的 `user_upload` scope） | 创作者拥有自己的世界观笔记；v3 无处承载 | `assets/text_ingest.py` + 复用 `eval/embedder.py` + 在 `eval/lore.py` 中新增 scope；前端已接入上传 | commits `d1746d4`、`eed2c2d` |
| 本地开源素材库（manifest 驱动，11 个 CC0 种子素材） | 内容同质化的根因是“只有主题输入，也只有 LLM 输出” | `assets/library.py`——以 manifest JSON 作为唯一事实来源（**不**扫描文件系统，否则会静默纳入未授权文件）；标签交集 + 可选 sentence-transformer 余弦相似度；3 个背景 + 5 个立绘 + 3 个 BGM CC0 种子素材 | commit `1957158`、`data/assets/opensource/manifest.json` |
| 联网检索 Agent（主题 → 查询规划 → 搜索 → 分块 → RAG） | 简单 URL 抓取是死路；目标是实现“跨多来源的 AI 规划器” | Provider 协议：`SerperProvider`（生产）、`StaticFixtureProvider`（测试）、`GeminiGroundingProvider`（M1 stub）；使用 Haiku 规划查询；硬成本 gate：**最多 5 个查询、最多 8k tokens**；每个 chunk 均携带 `source_url` + `retrieved_at` + `search_query` | commit `eed2c2d`、`src/vn_agent/assets/web_search_agent.py` |
| 跨来源去重（图像 pHash + 文本向量余弦相似度） | Web 结果高度重叠（Wiki + Fandom + Reddit 镜像） | `assets/dedup.py`——复用 `imagehash` 库；文本使用余弦相似度 | commit `d1746d4`、`src/vn_agent/assets/dedup.py` |
| 许可证 gate（白名单：**CC0 / CC-BY / CC-BY-SA / user_owned / derived**） | 素材市场方向需要默认合法安全 | `assets/license_gate.py::audit()`（报告模式）+ `enforce()`（抛出 `LicenseGateError`）；采用白名单而非黑名单，其他许可证均需显式审核 | `src/vn_agent/assets/license_gate.py` |
| 多样性指数指标 | v4 首要产品指标 #3（非 LLM 素材占比 ≥ 30%） | `metrics/diversity.py` 统计非 LLM 素材占比，写入 `vn_script.json.metrics` | `src/vn_agent/metrics/diversity.py` |
| 恢复机制（Writer 局部落盘 + Web 恢复 endpoint） | 真实运行 3cbbf260 在 Reviewer 处卡住 52 分钟，且无任何产物 | `salvage.py`：在 `vn_script.json` 与 `snapshots/*.json` 之间选取完成度最高的结果；Web 侧提供 `POST /api/projects/{id}/resume` | commit `d52261c`、`src/vn_agent/salvage.py` |
| Reviewer 调试状态预落盘 + 硬超时 | 同一次 52 分钟卡死事件中，无法检索究竟哪个 prompt 卡住 | `services/pending_debug.py`：每次封装后的 LLM 调用前写入 `debug/{name}.pending.txt`，结束后重命名为 `.done.txt` / `.error.txt`；使用 `asyncio.wait_for` 和 `settings.reviewer_timeout_seconds`（默认 300s） | commit `47d50fa`、`src/vn_agent/services/pending_debug.py` |
| 单请求 mock 开关 + `run-analyzer` subagent + 文档 §9 商业化 | v3 mock 仅能通过环境变量控制，在多任务中会泄漏；同时缺少商业化章节 | 单请求 `mock=true` 标记 + 文档 §9（3 条商业路径 + 7 层成本表 + Pro/Team 单元经济性） | commit `383a982` |
| 上传删除 + 取消选择 UX | 文件上传错误后无法撤回 | 前端删除与取消按钮；服务端 unlink | commit `1602ddd` |

### 2.3 v4 P1（数据飞轮 M0）——刚刚交付

| 功能 | 产品动机 | 技术方案 | 证据 |
|---|---|---|---|
| `feedback/store.py`——仅追加 JSONL（`data/feedback/all.jsonl`） | 数据飞轮需要跨任务的唯一事实来源，而非各任务的数据孤岛 | M0 冻结记录 schema：`{id, job_id, scene_id, verdict, reason, tags, context, created_at}`；不可变，编辑意味着新建记录并添加 `supersedes: id` | commit `49baaf2`、`src/vn_agent/feedback/store.py` |
| `feedback/injector.py`——向 Writer prompt 注入 BM25 few-shot | 点踩反馈需要切实影响下一次生成 | `rank_bm25`（复用 Sprint 6-4 依赖），top_k=3，min_score=-1.0（针对 IDF 会变为负值的小型 M0 语料调优）；query 以场景为中心（`description + strategy + characters_present`），而非以主题为中心；**只使用点踩**（点赞不含可供 prompt 注入的“AVOID”信号，它在 Reflection 中作为锚点发挥作用）；注入格式为 Writer “写 N 行对话”指令上方的 `"AVOID: ..."` 自然语言行 | `src/vn_agent/feedback/injector.py` |
| `feedback/reflection.py`——Reflection Agent（批处理任务 → `dynamic_guidelines.json`） | L2 层将局部规则提升为结构性规则 | 使用 Haiku 而非 Sonnet——任务偏分类，在 1k 条记录下约 $0.01/run；`--min-samples` 默认 20（用 3 条记录运行没有意义）；原子写入（tmp + rename）；每条规则输出 polarity + confidence；Writer 下次启动时将其作为经过 prompt cache 的 suffix 载入 | `src/vn_agent/feedback/reflection.py` |
| **M0 未交付**：DPO fine-tuning（L3） | 需要 ≥1k 条标注记录与训练算力；M0 两者均不具备 | 明确排除——“数据到位后在 M1.5 实施” | plan 文件 §“P1 数据飞轮 · 真实用户数据补齐路径” |

**v4 P0/P1 测试概况**：`tests/test_assets/`（7 个文件：dedup、library、license_gate、text_ingest、upload_delete、web_search_agent）+ `tests/test_feedback/`（3 个文件：store、injector、reflection）。每个模块均有隔离单元测试；已存在 upload → generate → diversity 流程的集成测试（`test_upload_flow.py`）。

### 2.4 v4 P2（前端打磨 + JIT 流式播放）——已交付

| 功能 | 产品动机 | 技术方案 | 证据（commit） |
|---|---|---|---|
| Tailwind v4 + 设计系统修复 | `className` 里引用了 Tailwind class，但依赖链从未真正装上——截图全是无样式状态 | `tailwindcss` + `@tailwindcss/vite` 接入 `frontend/vite.config.ts`；用真实 `npm run build` 验证过 | commit `a309058` |
| SSE 即时场景流式推送 | 玩家过去要等完整脚本生成完才能看到任何内容，没有"看着它被写出来"的时刻 | `services/job_events.py` 实现每任务 pub/sub（与 `TokenTracker` 同款 ContextVar 作用域）；`/api/projects/{id}/stream/scenes` SSE 端点；`VNPreview.tsx` 场景一到就消费 | commit `a309058`、`src/vn_agent/services/job_events.py` |

**未完成**：流式体验的浏览器手工点击验证（单元/集成测试覆盖了 SSE 管线和 store 状态机，但没覆盖真实渲染出的"Watch Live"体验）——2026-07-21 用户明确要求延后，截至 2026-07-29 仍未做。

### 2.5 v4 P3（Chat Ops M0）——已交付

| 功能 | 产品动机 | 技术方案 | 证据（commit） |
|---|---|---|---|
| 4 意图分类器（local_regen / add_character / edit_asset / explain） | 生成后的编辑过去只能走 CLI + 表单，无法对话式操作 | `chat_ops/intent_router.py`，Haiku 分类器，双语 mock 模式关键词 fixture 支持零成本 demo | commit `47d59e4` |
| L1 执行前预览确认卡片 | 意图分类错了却静默改动场景，比体验慢一点更糟 | 每个 mutating 意图都先返回 `requires_confirmation` 预览；`POST /chat/{preview,execute}`；只有前端明确 confirm 后才真正执行 | commit `47d59e4`、`ChatPanel.tsx` |
| `local_regen` 真执行器（唯一完整接线的意图） | M0 范围内的诚实取舍——与其 4 个都做假执行器，不如先做实 1 个 | 复用 `agents/local_regen.py::regenerate_scene`（未重造轮子）；`regenerate_scene` 直接写 `vn_script.json`（绕过 web 层 JobStore），所以 `chat_execute` 要重新从磁盘读取、同步回 SQLite blackboard——真实存在的一致性坑，由 `test_execute_local_regen_syncs_blackboard_from_disk` 专门盯着 | commit `47d59e4` |
| 每个已解决 turn 的审计轨迹 | 需要项目状态可审计，而非全量 UI 埋点 | 每个"已解决"turn 落一行 JSONL 到 `<output_dir>/chat_ops/turns.jsonl`（mutating 意图只在 confirm 后落盘，被取消的 turn 不落盘），与已有的 `rag_retrievals.jsonl` 同一套约定 | commit `47d59e4` |

**M0 范围内的诚实取舍**：4 个意图全部能正确分类，但只有 `local_regen` 接了真执行器；`add_character`/`edit_asset` 返回诚实的"M0 未实现"提示，不是静默失败。L2 置信度阈值 / L3 top-K 选项 / L4 反馈飞轮回 P1 仍是路线图，未开始。浏览器点击验证未做。

### 2.6 v4 P4（PlaytestAgent + Vision LLM Judge M0）——已交付

| 功能 | 产品动机 | 技术方案 | 证据（commit） |
|---|---|---|---|
| Branch walker | 需要自动遍历所有可达路径，不只是主线 | `playtest/branch_walker.py` 尊重 `BranchOption.requires` 状态门——比 `reviewer.py` 现有的 BFS 可达性检查更严格 | commit `c4793a5` |
| Pillow 帧合成器（从真实 Ren'Py headless 执行范围收缩而来） | 原计划假设用真实引擎截图（`--warp` + `renpy.screenshot()`） | 勘查发现仓库**完全没有 headless 执行基础设施**——没有 subprocess 封装、没有 `--test` flag、没有任何截图自动化。用户确认将 M0 范围收缩为基于管线自身真实/占位 PNG 的 Pillow 合成代表帧；真实引擎截图推迟到 M1 | commit `c4793a5`，范围调整已写入文档 |
| Vision LLM Judge，5 维度打分 | 需要判断"这好不好玩/连贯"，不只是"能不能编译" | `playtest/vision_judge.py` 把合成帧 + 对白日志喂给 Claude vision；`services/llm.py` 新增 `images` 参数——**仓库首次支持 vision LLM 调用** | commit `c4793a5` |
| 顺手修的 CJK 渲染 bug | Pillow 默认字体没有 CJK 字形——中文渲染成方块 | 换成系统 CJK 字体 + 按字符（而非按单词）换行；中英文均用真实 mock 生成的项目截图做过视觉验证 | commit `c4793a5` |

**未完成**：真实引擎 headless 截图（M1，需要目前不存在的 Ren'Py `--warp` harness）；Vision Judge 的成本/评分尚未在真实 API 运行上实测（目前只做过 mock 验证）；Playtest 报告 UI 的浏览器点击验证。

### 2.7 v4 P5（Autopilot M0）——已交付，顺手修了两个真实 bug

| 功能 | 产品动机 | 技术方案 | 证据（commit） |
|---|---|---|---|
| 一键"⚡ Autopilot"按钮 | 此前每个阶段都交付了能力，但从未组装成"输入主题、直接可玩"的单一入口 | 复用已有的 `fast_mode` 自动跳过 review 链路；新增 preset 解析 + 首个 scene 到达时自动切入 SSE 流式播放器 | commit `5e8d621` |
| 基于 `ContextVar` 的逐任务 settings 覆盖 | `get_settings()` 是 `@lru_cache` 的进程级单例，被约 20 处 agent/graph 代码直接调用——Autopilot 需要逐任务 preset，又不能碰这 20 处调用点 | `config.py::get_settings()` 拆分为 `_load_default_settings()`（缓存）+ 优先检查的 `_settings_override: ContextVar[Settings\|None]`；所有现有调用点零改动自动获得逐任务覆盖能力 | commit `5e8d621`、`src/vn_agent/config.py` |
| **发现并修复（已获用户确认）**：`/generate` 双重执行 + 状态写入竞态 | 在设计 Autopilot 成功率 KPI 时发现——如果不修，这个指标测的其实是一个竞态条件 | `POST /generate` 过去会对每次真实生成独立触发一个后台 `_run_job` 任务，而 SPA 自己的 `generate-setting → generate-script` 链路又会跑同一个 job——`_run_job` 拿了并发信号量，另一条路径没拿。修复：新增 `interactive` 请求字段（SPA 传 `true` 跳过 `_run_job`；无头 API 调用方默认 `false`，契约不变） | commit `5e8d621` |
| **发现、披露并修复（完整披露后获用户确认）**：`--mock` CLI 冒烟测试期间的真实 API 花费 | 一次例行 sanity check（`vn-agent generate --mock`）意外产生了**5 次真实 Anthropic 调用，约 $0.12** | 根因：`agents/reviewer.py` / `structure_reviewer.py` 的真实 LLM 调用走 `services/pending_debug.py::ainvoke_with_pending_debug()`，该函数内部做了一次全新的 `ainvoke_llm` import——完全绕过了 CLI 按模块打的静态 mock patch。修复：`_patch_mock_llm()` 现在同时设置 `ainvoke_llm` 内部实际检查的 `mock_mode_var` ContextVar，堵住所有调用路径的口子，不只是被抓到的那几个。已安全验证（响应亚秒级，无网络往返）+ 加了永久回归测试（`tests/test_cli/test_mock_patch.py`） | 同一 commit `5e8d621`；修复前已向用户完整披露 |
| `autopilot/outcomes.py`——M0 只记录，尚不排序 | 路线图需要 M1"按历史成功率排序 preset"的数据源 | Append-only JSONL（`data/autopilot/runs.jsonl`），与 `feedback/store.py` 同形状；M0 只追加，尚无消费/排序逻辑 | commit `5e8d621` |

**范围调整（已获用户确认）**：`docs/v4/PRODUCT_v4.md` 原描述 Autopilot 是独立入口（自己的 URL/API）。`App.tsx` 目前没有客户端路由，M0 改为在现有工作台 SPA 里加一个按钮——与 P3/P4 的范围调整是同一模式，写进文档而非隐藏。

**v4 P0-P5 汇总**：939 个测试用例（2026-07-29 `pytest --collect-only`），最近一次全量回归 937 passed / 1 skipped / 1 deselected，exit 0。**P2-P5 四个阶段共同未完成项**：浏览器手工点击验证——2026-07-21 用户明确要求延后以继续开发，截至 2026-07-29 仍未做（本日期曾尝试过一次浏览器烟测，但因 Claude-in-Chrome 插件未连接而中断；服务已保持运行，等下次重试）。**P6 期间部分补上**：改版的 Task 5/6/7/8 各跑了一次真实 mock 模式浏览器验证，这是 P2-P5 的 UX 第一次被浏览器验证；具体验了什么、没验什么见 §2.8。

### 2.8 v4 P6（前端改版——改的是结构，不是配色）——已是默认外壳，分支尚未合并

分支 `feat/frontend-redesign-v4`，**19 个 commit**（`fa68464`..`1ac8ebf`，经 `git rev-list --count main..feat/frontend-redesign-v4` 核实；其中 17 个是改版本身，`fa68464`..`3730936`）。设计稿 `docs/v4/FRONTEND_REDESIGN_v4.md`（`a25e1e2`），实施计划 `docs/v4/FRONTEND_REDESIGN_PLAN_v4.md`（`5a8a0b8`），工程台账 `.superpowers/sdd/FRONTEND_REDESIGN_PLAN_v4/progress.md`。

| 功能 | 产品动机 | 技术方案 | 证据（commit） |
|---|---|---|---|
| 把问题从"选配色"重新定义为**两个结构性缺陷** | 第一版提案给了三个"视觉方向"，被用户一句话否掉——*"这三个的区别感觉只是颜色而已，本质上是一样的。"* 这个判断是对的：三个方向共用同一套布局 | 重新勘查后指出真实缺陷。**A**：恒定的左右五五分栏——每个 AI SaaS 的默认形状，与"视觉小说生成器"这个题材毫无关系。**B（更严重）**：项目最值钱的多 Agent 流水线在 UI 里完全不可见——`PreviewPanel` 只渲染一个转圈加一行字，而后端正在逐节点吐真实事件，这些信号全部被丢弃 | `docs/v4/FRONTEND_REDESIGN_v4.md` §1.2-1.3、设计稿 commit `a25e1e2` |
| **结构化流水线信号端到端打通**（核心修复） | `graph.astream()` 每个节点吐一次更新，web 层把它压成一个 progress **字符串**，前端再对这个字符串做子串匹配、猜五步进度条走到第几格。一条本来结构化的信号，被降级成散文再被猜回来 | `services/job_events.py::publish_node()`（复用 `publish_scene_ready` 的 ContextVar 模式）→ SSE `node` 事件 → store 的 `pipelineNodes` / `pipelineOrder` → `PipelineGraph.tsx` 手写 SVG 节点脊。SSE 端点本就是通用转发器、前端对未知 event 类型静默忽略，所以**不需要版本协商，对现有客户端零破坏** | `fa68464`、`7c8a339`、`5fe971d`、`0315aad`；`src/vn_agent/services/job_events.py:56` |
| 顺带修的真实 UX bug：**10 个节点里 6 个没有标签** | 用户看到的是裸露的内部标识符——字面意义上的 `Running cross_ref_sync` | `_STEP_LABELS` 从 4 条补到 10 条（核实：`git show 6f7a285:src/vn_agent/web/app.py` 是 4 条，当前是 10 条）。用 `tests/test_web/test_pipeline_labels.py` 锁死——该测试遍历**编译后的图**，任何节点缺标签即失败，未来新增节点无法静默回归 | `7c8a339` |
| 谁都没注意到的潜伏 bug：**进度条第 2 格不可达** | 旧的 `stepIndex()` 里 `p.includes('script')` 排在 `p.includes('review')` 前面，于是所有含 "script" 的 step 名都被前者抢先命中，审校/Review 那一格被静默跳过 | 用 `Record<AppStep, number>` 表 + `pipelineActive === 'reviewer'` 实时判断，取代散文匹配。这个 bug 是**因为 i18n 才被发现的**：progress 字符串一翻译进度条就会坏，翻译的阻塞点暴露了逻辑错误 | `782b5de`；`frontend/src/components/PreviewPanel.tsx:10-37`（注释里写清了缺陷本身） |
| 界面文案此前 **100% 硬编码英文**，补齐 zh/en | demo 的观众是中文面试官，而聊天列是全屏最常被读的区域 | 不引第三方库。`i18n/dict.ts` + `useT.ts`；**zh 209 个 key、en 209 个 key，集合完全一致**（解析文件核实）。对齐由 `tsc` 结构性保证——`dict[lang][key]` 意味着 en 缺 key 就构建失败。聊天记录存 **key + vars**、在渲染时解析，所以切语言会**重译整段历史**，而不只是新消息。节点标签放在前端翻译，因为 SSE 事件本就携带结构化 node id，后端保持稳定英文 | `bfdf963`、`b046835`、`da5659a`、`5b1ebeb`；`frontend/src/i18n/dict.ts` |
| **六层迁移，每层独立可回滚** | 前端**没有测试框架**（`package.json` 无 vitest/jest），稳定性买不到测试，只能来自架构 | L0 后端事件 → L1 tokens → L2 i18n → L3 外壳切换 → L4 流水线 + 故事板 → L5 切默认。契约冻结：`api.ts` 签名与 store 的 **action** 签名不变，只做加法。新旧外壳并存，`?shell=v1` / `?shell=v2` 优先且写入 localStorage 持久化 | `8113a7f`；`frontend/src/shell/useShellVariant.ts` |
| 形态随 `AppStep` 走，五五分栏被干掉 | 缺陷 A | `WorkbenchShell.resolveForm()` 把 `AppStep` 映射到 6 种形态之一；聊天列宽度随形态变化——`player: 0`（作品全幅）、`pipeline: 20rem`（舞台才是主角）、其余 `24rem` | `4f26c00`；`frontend/src/shell/WorkbenchShell.tsx:13-39` |
| 做故事板但**不让动作栏成为孤儿** | 如果改版直接替换 `ScriptPanel`，会让唯一的 5 个 script_review 确认按钮和逐场景对白编辑器失去入口 | `StoryboardBoard` + `SceneCard`；`ScriptPanel` 保留为**卡片详情态**，不是被替换。卡内就地重写把 prompt 喂给 P3 Chat Ops 意图路由，把"打字描述是哪一场"变成空间选取 | `7319a3a`、`0470352`；`frontend/src/components/StoryboardBoard.tsx:12` |
| 包体积回归：先记账，再消除 | L4 把 framer-motion 拉进模块图，只为两个效果 | `4f26c00` 在 commit message 里**如实记账**（270→406 kB raw，**81→125 kB gzipped**），并对照计划的 TTI ≤ 3s 目标标记为"切换前必须做的决定"，而不是静默带过；`717c203` 随后用 CSS `@keyframes` 换掉 framer-motion（405→280 kB raw，**125→84 kB gzipped**，仅比 L4 之前基线高约 3 kB）。附带收益：`prefers-reduced-motion` 现在自动生效，而 JS 库改内联样式会完全绕过它 | `4f26c00`、`717c203` |
| `director` 从不在节点流里上报——**靠浏览器验证发现，不是靠读代码** | 只按 `pipelineNodes` 渲染 10 个节点的话，`director` 会整场卡在 `pending`——图里的第一个节点，出错最显眼的位置 | `publish_node` 只接在 `_run_script_generation` 上，而该函数进图时大纲已经建好；`director` 更早在 `generate_setting()` 里执行，那里没有 `publish_node` 调用。修法：在 `confirmSetting()` 里把 `director` 直接种成 `'done'`（能走到这一步，按定义大纲就已存在）。同一次修改里：`text_only` 打开时 `asset_generation` 渲染为合法的**已跳过**，而不是永远 pending | 台账 §"INPUT REQUIRED BY TASK 9"；在 `0315aad` 中解决 |

**P6 哪些浏览器验过、哪些没验**（这个区分很重要，见 §9.2）：
- ✅ 真实 mock 模式浏览器会话验证过：语言开关切换整个界面文案且**无需刷新**（Task 6）；`?shell=v1`/`?shell=v2` 切换与 localStorage 双向粘性，以及在 v2 外壳里跑完整 Autopilot 直到编译产出（Task 7）；实时 `node` 事件序列 `structure_reviewer → director_step2_redo → structure_reviewer → state_orchestrator → thinking_fanout → cross_ref_sync → writer → reviewer`，这同时证明了修订回环是真实且可观测的（Task 8）。
- ✅ **同样验证过（2026-08-11）**：**最终** v2 外壳的 10 点完整走查在 mock 模式浏览器会话里 **10/10 通过**——空态、流水线剧场节点按序点亮、不勾 Fast Mode 时 `setting_review` 正确路由到 SettingPanel 且两个确认按钮都在、故事板网格、卡片详情五个剧本操作齐全且 `focusScene` 打开的是点中那一场（而非第一场）、从卡片播放进入指定场次且对话栏完全收起、铅笔图标经 Chat Ops 意图卡完成就地改写、Autopilot 零点击进入全幅播放器、`?shell=v1` 行为未变、无应用级 console 报错。走查还**抓出两个类型检查抓不到的缺陷**：无活跃节点的两个阶段活动行显示英文，以及 20rem 流水线宽度下聊天按钮换行/被裁切——均已在 `4e7c370` 修复。
- ✅ **Task 14 已完成**（`3730936`）：`frontend/src/shell/useShellVariant.ts` 的 `DEFAULT_VARIANT` 现为 `'v2'`，且是在走查通过之后才翻的；验证时先清空 localStorage，测的是真实首次访问者看到的东西。**演示现在直接开裸 `/` 即可。** `?shell=v1` 保留为逃生口。
- ❌ **刻意未做**：Task 15（删除旧外壳）。押后到面试季之后——失去 `?shell=v1` 等于失去现场演示的退路，而保留它的成本只是三个文件的死代码。
- ❌ **仍未验证**：形态切换那 ~250ms 的淡入（需要逐帧计时，静态截图看不出来）；以及 P2-P5 在**旧界面**上的 UX 走查（2026-07-21 就存在的老账，与本次改版无关）。

---

## 3. 经得住面试追问的指标

**分类**：(M) = 真实 API 运行实测，(K) = mock/计算所得，(T) = 尚未达成的目标。

### 真实运行测量值（M）
- **6-scene demo 端到端**：真实 API 约 $1.7，墙钟时间约 30 分钟（`docs/PRODUCT.md` 关键指标 line 429；使用 Sonnet + Nano Banana + Haiku 的 Phase 12-3 Showcase demo）
- **Continue-outline（创作者模式后半段）**：约 $0.46，约 9 分钟（同上来源）
- **M0 baseline（6-scene，真实 API，含素材）**：38.1 分钟，$2.04（`docs/v3/SHOWCASE_v3.md` §6，2026-04-26）
  > ⚠️ **$1.7 与 $2.04 的口径**（面试官容易当场发现「两个 6-scene 成本不一样」）：两次都是**含素材**的真实运行，不是文本 vs 素材的差别。$2.04 是 2026-04-26 的 M0 baseline，`SHOWCASE_v3.md` §6 明写它的目的就是「**揭示路由优化空间**」；$1.7 是路由优化之后 Phase 12-3 的 Showcase demo。
  > **标准答法**：「两次真实运行，中间落了 `can_writer_fix` 路由优化，顺序是对得上的。但它们不是受控 A/B——主题和配置都不同，所以我不会把 $0.34 的差额说成路由省下来的钱；路由那条单独的测量是 §4.1 的约 $1.10/run。」
  > **绝不要说**：$2.04 − $1.10 = $1.7。数字对不上，而且那是两件事。
  > 另注：早期文档把这次运行标为「纯文本」，实为误记——`SHOWCASE_v3.md:45` 的产出是 6 scenes / 3 characters / **4 BGM cues**。
- **mini smoke #1（3-scene）**：10.4 分钟，$0.57——验证路由优化（相较修复前成本下降约 70%）
- **mini smoke #2（3-scene）**：20.5 分钟，$1.13——验证上限/schema 长度行为（Sonnet 将 `max_tokens=8000` 当作目标：3/3 均触及上限，输出 tokens 为 7999/8000/8000 → **单场景成本 +54%**；负向结论：提高上限**不是**质量杠杆）
- **跨 Judge Pearson r = 0.643，±1 分一致率 = 87%**（8-cell 扫描中 Sonnet 3.68 / GPT-4o 3.66，commit `4f1228f`）
- **8-cell `writer_mode` 扫描**：literary 4.17 > action 3.92 > baseline_self_refine 3.45 > baseline_single 3.25（5 维 rubric，Sprint 8-5，`docs/v2/RESUME_v2.md` §评估实测数据）
- **策略 F1 提升**：keyword 0.21 → LLM（qwen2.5:7b）0.34，**相对提升约 62%**（`docs/v2/RESUME_v2.md` §评估实测数据）。注意：`RESUME_v2.md` 原文记为「+57%」；按展示的（四舍五入后）数值算 0.21→0.34 是 +62%，推测原始百分比来自未四舍五入的底层值，而原始 eval JSON 已不在仓库。**口径：引用 0.21 → 0.34；若被追问百分比，说「约 +60%，按展示值计算」——不要把 +57% 和 0.21/0.34 并列，面试官当场就能算出对不上。**
- **Reviewer 平均通过阈值**：3.5/5.0（`settings.reviewer_pass_threshold` = 3.5，`docs/PRODUCT.md` Sprint 6-fix）

### 计算/结构指标（K）
- **共 166 个 commit**（真实 `git log | wc -l`），**约 15.8K 行 src / 约 12.4K 行 tests**（`docs/v3/SHOWCASE_v3.md` §6 引用 15,851 / 12,382）
- **659 个单元测试通过**（v3 快照；随着 v4 P0/P1 新增测试，数量已有增长）
- **测试/src 比约 78%**（`docs/v3/SHOWCASE_v3.md`）
- **budget preset（全 Haiku）的成本降幅**：相较 baseline 路由约 73%（`docs/v2/RESUME_v2.md`；根据 Sonnet $3/$15 与 Haiku $0.80/$4 计算）
- **Prompt caching 系数**：首次 1.25×，5 分钟内复用 0.1×（Anthropic ephemeral cache 规范 + Sprint 8-4 验证）
- **`can_writer_fix` 路由节省**：每次 6-scene 运行约减少 $1.10 的无效 Writer 循环（`docs/v3/SHOWCASE_v3.md` §4.1）
- **真实 API smoke 总支出**：3 次已验证运行合计约 $3.74（M0 + mini #1 + mini #2）
- **957 passed / 959 collected**（2026-08-12 `main` 上实跑，按目录分批；1 个已知 flaky `test_graph_routing.py::TestWarningsDedup`，1 个 skipped）。历史：939（2026-07-29）→ 947（2026-08-10）→ 959。
  > ⚠️ **口径**：939/947 都是 `--collect-only` 的**收集数**，不是通过数，早期文档写成「947 passed」是错的。959 是收集数，957 是实测通过数。**面试时说「约 950 个测试，实跑 957 通过」，别把两个口径混用。**
  > 另注：整套 suite 在单进程里跑到中途会触发 torch/transformers 的 Windows access violation（`eval/embedder.py` 建索引时）；**按目录分批跑则全部通过**，说明是单进程累积状态的问题，不是测试本身坏了。这是本机环境问题，已用 stash 对照验证与代码改动无关。
- **P6 分支 195 个 commit / `main` 176 个**（2026-08-11 `git rev-list --count`）。⚠️ 本文件旧的"166 个 commit"与 `docs/v3/SHOWCASE_v3.md` §6、`docs/v4/PRODUCT_v4.md` §7.3 的"170 个 commit"彼此矛盾且都已过期；请引用当前计数，或笼统说"约 190 个 commit"
- **P6 流水线标签**：10 个图节点中有标签的从 4 个补到 10 个（`git show 6f7a285:src/vn_agent/web/app.py` 对比当前 `src/vn_agent/web/app.py:1342`），完备性由 `tests/test_web/test_pipeline_labels.py` 强制
- **P6 i18n 覆盖**：zh 209 个 key / en 209 个 key，集合完全一致，其中 10 个是 `nodeLabel.*`（解析 `frontend/src/i18n/dict.ts` 得到）；对齐靠 `tsc` 保证，不靠人的纪律
- **P6 包体积**：L4 之前 81 kB gzipped → framer-motion 进入模块图后 125 kB（`4f26c00`）→ **换成 CSS 后 84 kB**（`717c203`），即整个改版净增约 3 kB
- **P6 分支规模**：19 个 commit（`git rev-list --count main..feat/frontend-redesign-v4`，2026-08-11）

### 目标——必须标记为愿景目标（T）
- **50-scene 端到端**：墙钟时间 ≤ 30 分钟，成本 ≤ $15（T，Phase 13-1 目标；6-scene baseline 为 38 分钟，因此按比例推算为 $13-19 区间）
- 场景 10 之后 **`cache_read_ratio ≥ 0.5`**（T，基础设施已具备，仍需长篇运行验证）
- **首场景 TTFS ≤ 60s**（T，Sprint 12-1 流式流水线北极星指标，尚未构建）
- **Autopilot 成功率 ≥ 85%，端到端 ≤ 8 分钟**（T，P5 M0）
- **多样性指数 ≥ 30%**（T，v4 P0 指标——导出时已计算，但尚无运行达到 30%，因为种子库仅有 11 个 CC0 素材）
- **每个会话的 Chat Ops 对话操作 ≥ 8 次**（T，P3 未交付）
- **Vision Judge 成本 ≤ $0.20/run**（T，P4 未交付；按 6 scene × 3 screenshots × Sonnet vision 定价估算）
- **创作者完成率 ≥ 40%（beta）**（T，暂无数据——CLI 无法测量）

**面试事实校验原则**：面试官追问任何指标时，都要能说明“来自 N=1 真实运行、mock，还是基于 baseline 的推算”。将 mock 数字伪装成生产数据，是 AI 产品经理面试中最快的出局方式。

---

## 4. 我做出的产品决策及其原因

格式：**决策** · **考虑过的备选方案** · **权衡逻辑** · **复盘判断**。

### 4.1 优先级方案 Y（10-14 周，最大化直接亮点）
- **决策**：按 P0（多源融合）→ P1（数据飞轮）→ P2（前端 + 流式输出，并行）→ P3（Chat Ops）→ P4（PlaytestAgent）→ P5（Autopilot）的顺序推进。
- **备选方案**：方案 X（前置 P2 前端以提升 demo 观感）；方案 Z（前置 Autopilot 以提高玩家侧黏性）；“仅打磨 v3”（不做 v4）。
- **权衡逻辑**：按三个维度评分（**简历亮点 · demo 展示力 · 产品落地性**），结果为 P0-③（14）> P0-②（13）> ①/⑤/④（12）> B（11）> C（9）。首先推进多源能力（③），能优先回答 AI 产品经理最高频的问题——“如何避免内容同质化”，同时解锁 P5 Autopilot 的 fallback 排序。前置前端虽更美观，却无法形成差异化叙事。
- **复盘判断**：P0 按计划在约 2 周内交付，证明决策正确。展示视觉小说生成器时，面试官首先会问“这与给 Claude 一个更大的上下文窗口有什么区别？”“文本上传 + 联网检索 + 开源库 + LLM 四通道融合，并配有许可证 gate”确实构成差异化答案。

### 4.2 将 v3 暂缓的 B（自进化 Agent）+ C（PlaytestAgent）重新纳入 v4
- **决策**：v3 的两个 `P2 backlog` 项目是“AI Ops / 评测飞轮”和“PlaytestAgent + Vision LLM Judge”，当时因时间原因暂缓；v4 分别将其重新纳入为 **P1** 和 **P4**。
- **备选方案**：继续作为 v3 长期架构而暂缓；只恢复一个；两者都不做，专注完成前端。
- **权衡逻辑**：两者都直接对应 AI 产品经理面试前三高频问题（数据飞轮 + 评测/AgentOps）。不重新纳入，就等于放弃代码库已经具备基础的高价值简历机会。它们并非零成本——B 需要 alpha 用户，C 需要验证 vision judge——但都能大量复用 v3 基础设施（BM25、prompt caching、Pearson r 跨 Judge 验证），边际工程成本各为 1-2 周。
- **复盘判断**：B M0 已交付（49baaf2）。数据较薄（作者自用 + 计划 3-5 名 alpha 用户），但**闭环可证明已运行**，这正是“M0”应当证明的内容。校招表述为：“M0 数据是薄的，但闭环已跑通”——将真实缺口重新界定为有意识的范围控制。

### 4.3 从“玩家 + 创作者双 UI”转向“创作者优先 + Autopilot”
- **决策**：v3 混合了玩家和创作者 UI；v4 明确拆分：创作者使用工作台（P2/P3），玩家使用 Autopilot（P5）。
- **备选方案**：保留双 UI；按 preset 区分（玩家使用默认 preset，创作者使用自定义 preset）。
- **权衡逻辑**：双 UI 导致两端体验都浅。创作流程所需的引擎知识渗透到玩家流程（需要安装 Ren'Py SDK），反之亦然。将 Autopilot 作为**完全独立的 URL/API** 可以解除耦合，让两端各自做深。该方案也符合市场数据（Cursor 区分“用户”与“开发者”定价，Perplexity 区分“普通”与“Pro”；承受 LLM 成本压力的单层产品难以生存）。
- **复盘判断**：决策正确——见 §9 单元经济性表：双模式 SaaS 无法成立，拆分用量层级并单独核算 Autopilot 后可以成立。

### 4.4 许可证 gate 采用白名单，而非黑名单
- **决策**：`ACCEPTED_LICENSES = {CC0, CC-BY, CC-BY-SA, user_owned, derived}`，其他许可证全部拒绝。
- **备选方案**：将 NSFW/限制商业使用列入黑名单；所有来源均要求 Reviewer 审批；M0 阶段跳过 gate。
- **权衡逻辑**：素材市场方向（§9 路径 B）需要默认合法安全。白名单迫使策展者为纳入素材提供依据；黑名单则会静默发布任何“尚未被禁止”的内容。每种新许可证需额外花费 1-2 小时审核——这是避免“付费产品意外发布受版权保护素材”所值得支付的保险成本。
- **复盘判断**：决策正确。面试中，这类决策体现的是**产品经理直觉，而非工程师直觉**：以吞吐量（通过素材更少）换取下游可能性（素材市场/商业化路径）。

### 4.5 单请求 `mock` 开关（而非仅支持环境变量）
- **决策**：v3 的 mock 使用进程级环境变量 `VN_AGENT_MOCK=1`；v4 在 API payload 中新增单请求 `mock=true`。
- **备选方案**：仅保留环境变量；增加 workspace 级开关。
- **权衡逻辑**：仅依赖环境变量时，无法在同一服务进程中进行多租户测试（部分任务调用真实 API，部分任务使用 mock）。单请求开关也支持 Autopilot 成本 gate（“免费层使用 mock 图片”）。
- **复盘判断**：已交付（383a982），支持 §9 的分层设计：“免费用户每月 3 部作品使用 mock 图片 → Pro 使用真实图片”。

### 4.6 联网检索采用 search-agent，而非 crawler
- **决策**：Provider 协议（Serper 生产环境 / StaticFixture 测试 / Gemini grounding M1 stub）；Haiku 规划 3-5 个查询；每次生成硬性限制 5 个查询 + 8k tokens；每个 chunk 保留 `source_url` + `retrieved_at` + `search_query`。
- **备选方案**：httpx + 用户粘贴 URL（v3 粗糙版本）；构建无头浏览器 crawler；使用完整 Playwright。
- **权衡逻辑**：crawler 会带来合规难题、脆弱的 DOM 解析与触发限流封禁的风险。search-agent 借助 Google/Serper 已完成的合规工作，并将 DOM 解析委托给 API。使用 Haiku 规划查询（每百万输入 tokens 成本比 Sonnet 低 6×），使每次生成成本低于 $0.01；硬成本 gate 防止失控主题静默突破预算。
- **复盘判断**：已交付（eed2c2d）。Provider 协议提升了可测试性，`StaticFixtureProvider` 能让 CI 在不访问网络时保持通过。

### 4.7 Reviewer 调试状态预落盘 + 硬超时（52 分钟卡死后的防御性措施）
- **决策**：为每次 Reviewer LLM 调用封装 `pending-debug`（调用前写入 `debug/{name}.pending.txt`，调用后重命名为 `.done.txt` / `.error.txt`）+ 默认 300s 超时的 `asyncio.wait_for`。
- **备选方案**：依赖现有 trace 日志（在本次卡死中未写入）；只增加全局请求超时；不处理并寄希望于不再发生。
- **权衡逻辑**：真实事故（job 3cbbf260）中，Reviewer 卡死 52 分钟且**磁盘上零产物**。复盘发现：LLM SDK 内部等待卡死的 stream，导致现有 trace 什么也没写。解决措施必须发生在 LLM 调用**之前**而非之后。pending 文件让运维人员可以检索卡住的 prompt；硬超时限定单个 Agent 最长占用时间，300s 大于健康 Reviewer 调用的最坏情况（约 120s），但小于不合理时长。
- **复盘判断**：已与 salvage（d52261c）一同交付（47d50fa）。这是典型的“发现一个 bug，修复方案为整类卡死问题补齐可观测性”；salvage 工具本身就是可验证的结果。

### 4.8 P1 数据飞轮的 M0 范围控制：做 L1+L2，不做 L3（DPO）
- **决策**：交付 👍/👎 → BM25 injector（L1）+ Reflection Agent（L2）；明确将 DPO fine-tuning（L3）推迟到 M1.5。
- **备选方案**：交付 L3 stub；只交付 L1；完全不做飞轮。
- **权衡逻辑**：DPO 需要 ≥1k 条标注记录与训练算力。M0 两者均不具备（计划仅有 3-5 名 alpha 用户）。强行做 L3 要么使用伪造数据（不诚实），要么产出永远不会运行的 stub agent（面试中需要辩护的死代码）。L1+L2 只依靠作者自己的反馈就能证明已运行——飞轮*已经存在*，只是转速还不快。
- **复盘判断**：已交付（49baaf2）。校招表述为：“M0 数据是薄的，但闭环已跑通；数据来源不只 alpha，还包括 P5 Autopilot 玩家 + P4 Vision Judge 三条自然沉淀源——我把这三个方向做在一起，就是为了让数据飞轮不靠单一入口”（见 plan §“产品盲点后续跟进方案”）。

### 4.9 Autopilot M0 用工作台按钮，而非独立入口
- **决策**：`docs/v4/PRODUCT_v4.md` 原本把 Autopilot 定义为独立入口（自己的 URL/API）。M0 改为在现有工作台 SPA 里加一个"⚡ Autopilot"按钮。
- **备选方案**：搭建真正独立页面所需的客户端路由基建；只做一个没有 UI 的裸 API 端点，就算 M0 完成。
- **权衡逻辑**：`App.tsx` 目前没有路由。为单一新入口专门搭路由基建，会把 3-5 天的 M0 预算全部烧在基础设施上而非功能本身。一个设置 `autopilot: true` 并复用已建好的流式播放器的按钮，用小得多的成本换到了同样的用户体验（一次输入、一次点击、立刻可玩）。
- **复盘判断**：同一 session 内交付。这是 v4 六阶段里第三次（与 P3、P4 同类）原计划范围因开发中途发现的真实基础设施缺口而收缩——不是质量妥协，而是"计划先说明范围调整原因，而不是被追问后才补"这个模式本身，值得在面试里当作过程信号来讲。

### 4.10 自己 dogfooding 抓到真实成本安全 bug——先披露再修
- **决策**：一次例行 `--mock` CLI 回归检查意外触发了 5 次真实付费 API 调用后，立刻停止，不再尝试任何"我再查一下"式的调用（那会花更多钱），只用安全/离线证据（耗时、ContextVar 状态）做根因定位，在动手写任何修复代码之前先向用户完整披露事故。
- **备选方案**：悄悄修完顺带一提；先修后解释；当成不值得单独披露的小事。
- **权衡逻辑**：本项目自己的工作约定（`feedback_api_approval`）要求任何真实 API 花费都要事先明确获得确认——一次本该零成本的 sanity check 却*意外*产生花费，正是这条规则本要拦住的失败模式，即便这次不是故意违规。悄悄修复虽然更快，但会把安全机制里的真实缺口，瞒着真正承担花费的人。
- **复盘判断**：用户在收到完整披露后明确选择"现在就修"。修复方案本身（通过 LLM 客户端内部本就会检查的同一个 ContextVar，堵住*所有*调用路径的口子，而不只是打补丁堵住被抓到的那两处）之所以是更站得住脚的工程结果，正是因为有时间想清楚而不是在救火。这是"讲一个你犯过的错误"这类面试问题的好素材——事故 → 披露 → 根因定位 → 系统性（而非点状）修复 → 回归测试，闭环很干净。

### 4.11 否掉自己的第一版改版提案：问题在结构，不在配色

- **决策**：前端改版的第一版提案给了三个"视觉方向"，被用户一句话否掉——*"这三个的区别感觉只是颜色而已，本质上是一样的。"* 我没有去做第四套配色，而是重新勘查整个应用，把问题重新表述为**两个结构性缺陷**：（A）恒定的左右五五分栏，那是每个 AI SaaS 的默认形状，与视觉小说这个题材没有关系；（B）项目最值钱的多 Agent 流水线在 UI 里完全不可见，而后端正在实时吐出真实的逐节点事件，这些事件被全部丢弃。
- **备选方案**：从三个配色里挑一个交付了事；引入 shadcn/ui 之类的成套组件库，至少看起来专业；把"看起来像模板"当成审美意见，先延后。
- **权衡逻辑**：改配色是不可证伪的——你没法在面试里论证靛蓝比黄铜好。改结构是可辩护的：**信息架构现在把系统里真实存在、却在产品里没有任何表征的过程暴露了出来**。这也正是明确拒绝成套组件库的原因（设计稿 §7）——预制组件库本身就是"模板感"的来源；差异化在信息架构，不在按钮圆角。
- **复盘判断**：判断正确，而且证据是具体的而非审美的——同一批工作顺带修掉了 6 个缺失的节点标签、一个不可达的进度格、以及一条信号降级路径。面试表述：**"改的不是皮肤，是信息架构"**——让 AI 的工作过程可解释，是 AI 产品经理的核心命题，不是装修活。来源：`docs/v4/FRONTEND_REDESIGN_v4.md` §1.2、§7、§9。

### 4.12 靠架构而非测试保证稳定，因为前端根本没有测试框架

- **决策**：分**六层迁移，每层独立可回滚**，旧外壳原样保留在 `?shell=v1` 这个 URL 逃生口后面（并写入 localStorage 持久化），同时执行硬性契约冻结：`api.ts` 的方法签名、返回类型与 store 的 **action** 签名只允许新增可选参数 / 新增字段。
- **备选方案**：先引入 vitest、用测试买安全（在任何可见进展之前先花掉几周）；就地重写外壳、靠手工点击兜底；在现有组件内部打 feature flag，而不是并存两套外壳。
- **权衡逻辑**：`frontend/package.json` 里没有 vitest/jest——这是事实而不是偏好，假装有才是不诚实的选项。所以安全必须来自结构：契约层不变，回归风险就被限制在渲染层；两套外壳并存，任何故障都只有一个 URL 参数的距离就能退回可用状态——**包括面试当天**。
- **复盘判断**：这个逃生口的价值体现为一条**策略**而不只是一个机制：`DEFAULT_VARIANT` 一直保持 `'v1'` 直到走查通过才切到 `'v2'`（`3730936`），因为 L5 切换被刻意卡在"浏览器走查完成"这个前置条件上。走查后来 10/10 通过，并且抓出了两个类型检查抓不到的缺陷——这恰好说明这道闸门是有价值的。所以"我们交付了一次改版"的诚实版本是：改版已是默认外壳、逃生口保留，而且我没有只凭类型检查就去翻默认值。

### 4.13 在造成回归的那个 commit 里记账，然后把它消除

- **决策**：L4 把 `framer-motion` 拉进模块图时，commit message（`4f26c00`）当场公开记账——270→406 kB raw、81→125 kB gzipped——并对照计划的 TTI ≤ 3s 目标，标记为"切换前必须做的决定"。随后 `717c203` 用 CSS `@keyframes` 换掉该库，落到 84 kB gzipped，仅比改版前基线高约 3 kB。
- **备选方案**：保留 framer-motion（反正已经装好且能用）；默默接受 +44 kB；干脆不要动效。
- **权衡逻辑**：这个库买到的只有两个效果——运行中节点的呼吸脉冲、形态切换的交叉淡入。两者都是几行 CSS。为两个 keyframe 动画付出 44 kB gzipped，成本收益上不成立。另外还有一个只有在细看时才浮现的正确性论据：`tokens.css` 里本来就有 `prefers-reduced-motion` 块，但**JS 库改内联样式会完全绕过它**，而 `@keyframes` 自动尊重它——所以更便宜的方案同时也是更无障碍的方案。
- **复盘判断**：有一处刻意的行为损失被写下来而不是藏起来——`AnimatePresence mode="wait"` 是先退场再入场，CSS 版只做入场淡入；要复现退场那一半就得让旧树继续挂载，而 `wait` 本身还在两个形态之间引入了空档。可迁移的面试要点是**过程**：在产生回归的当下就把它写进 commit，这样"留还是删"是基于数据做的决定，而不是事后被用户发现。

---

## 5. 数据飞轮 + AgentOps 证据（校招亮点）

本项目最有力的 AI 产品经理叙事是**四盲点联动网络**：四个缺口并非相互独立，而是被设计成一个网络，每个盲点的后续解决方案都会成为其他盲点的输入。

### 5.1 四盲点联动网络（来自 plan 文件 §“产品盲点后续跟进方案”）

```
        P5 Autopilot                          P1 数据飞轮
      （成功率 / 成本）                      （创作者 👍/👎）
              │                                      │
              │            ┌───────────┐              │
              └─── 参数 ──▶│           │◀─── 反馈 ───┘
                            │  联动池   │
              ┌── 评分 ───▶│           │◀── 意图纠错 ─┐
              │            └───────────┘              │
       P4 PlaytestAgent                         P3 Chat Ops
     （Vision Judge 评分）                   （intent-router 采样）
```

联动关系：
- **P3 intent-router L4 fallback**（误分类转化为训练数据）→ **P1 `dynamic_guidelines.json`**
- **P4 Vision Judge 评分**（M0.5）→ **P5 Autopilot** preset 选择（M1）
- **P5 Autopilot 完成率**（M0.5）→ 作为隐式反馈进入 **P1 飞轮**（M1）
- **P1 dynamic_guidelines**（M1）→ **P3 intent-router prompt** + **P4 Vision Judge 评分 baseline**

**校招一句话表述**：“四个盲点不是并列，而是一张网——每个盲点的解决方案都是别的方向的输入。这是数据飞轮的产品设计思维，不是模块化实现思维。”

### 5.2 P1 M0 具体飞轮（当前实际运行内容）

```
创作者 👍/👎（前端对话/预览）
    │
    ▼
feedback/store.py —— 追加至 data/feedback/all.jsonl（不可变）
    │
    ├──────────────────┐
    │                  │
    ▼                  ▼
Injector             Reflection Agent（批处理，Haiku）
（BM25 top_k=3，      （--min-samples 20，约 $0.01/run）
 仅点踩，                 │
 场景型 query）           ▼
    │              dynamic_guidelines.json（原子写入）
    │                    │
    ▼                    ▼
Writer prompt          Writer system prompt suffix
“AVOID: X. AVOID: Y.” （经过 prompt cache，复用时 0.1×）
```

体现产品经理严谨性的设计选择：
- **Injector 只使用点踩**：点赞不携带可用于 prompt 注入的“AVOID”行动信号。它们在 Reflection 中作为正向规则提取的锚点，但向场景生成 prompt 注入“PREFER”类自然语言会干扰模型。面试官听到这里会认同，因为这是产品经理所需的判断力信号，而不是追逐概念。
- **使用 BM25 而非 embeddings**：反馈原因较短（≤200 chars）、关键词密集、语言各异；BM25 在这种分布上投入产出比更高，且无需下载模型。复用 Sprint 6-4 依赖——这是**不重复造轮子**的证据。
- **`min_score = -1.0`**：BM25 IDF 在极小语料上会变为负值（M0 语料有意保持较小）。严格的正阈值会过滤掉前约 30 条记录的所有命中；语料超过约 30 条后，IDF 才会趋于正常。这个实现细节证明对算法具有实际理解。

### 5.3 AgentOps 可观测层（v3 → v4 持续演进）

- 每个任务的 **`run_metrics.json`**：`wall_seconds`、`total_cost_usd`、`cache_read_ratio`、`key_rotation_count`、`health_status`、`degradation_signals`（v3 Phase 13）
- 每个场景的 **`rag_retrievals.jsonl`**：query、retrieved_ids、similarity——将“为什么 ch3 提到了 Aldric”从黑盒问题转化为可检索问题
- 每个场景的 **`snapshots/{scene}.json`**——v3 Sprint 11-4 单场景重新生成及 v4 salvage 的基础
- **`debug/{name}.pending.txt`**——v4 P0 用于指出哪个 prompt 卡住的预落盘层
- **`trace.json`**——v3 Sprint 9 的节点级耗时 + token
- **Reviewer 3 层分类**（structural / mechanical / LLM quality）→ `can_writer_fix` bit → `decide_retry_target` 路由决策
- `--abort-on-degradation` 的**健康信号中止机制**：`retry > 5`、`key_rotation_density > 1.0` 或 `wall_minutes > 2× expected` 时标红，使压力测试器在消耗 50-scene 层级的 $15 前中止

这套 AgentOps 栈符合 Anthropic Claude / OpenAI Assistants / ByteDance Coze 等产品应具备的水平，而且每个模块都有仓库路径作为证据。

---

## 6. 商业化 + 成本模型（`PRODUCT_v4` §9 精要）

### 6.1 三路径商业模式（相互叠加，而非相互竞争）

| 路径 | 说明 | 优先级 | v4 依赖 |
|---|---|---|---|
| **A · SaaS 订阅**（创作者层级） | 免费层（3 部作品/月、≤10 scene、mock 图片）→ Pro（无限量/真实图片/优先处理/私有素材库）→ Team（多席位 + 共享 Chat Ops 会话） | **P0**（v4 的自然形态） | ① 前端 + ② Autopilot + ④ Chat Ops |
| **B · 素材市场**（marketplace 抽成） | 创作者上传自定义立绘/BG/BGM；平台抽成 15-20%。购买者为其他创作者，可直接载入本地素材库 | **P1**（收款前需要 P0-2 素材库 + P0-4 gate） | ③ + P0-4 |
| **C · 面向企业的工具链授权**（whitelabel） | 向游戏工作室销售 Multi-Agent + AgentOps 栈（评测/可观测性/多样性指标），用于内部内容生产；按席位/调用定价 | **P2**（需要 P4 PlaytestAgent 稳定后才有说服力） | v3 eval + P4 + Chat Ops |

**不采用的方案**：广告变现（视觉小说受众过小，CPM 无法覆盖 LLM 成本）；一次性永久许可证（LLM 后端持续产生费用，一次性收费会持续侵蚀利润）。

### 6.2 七层成本拆解（每部作品的可变成本）

| 层级 | 6-scene demo | 50-scene 目标 | 来源 |
|---|---|---|---|
| ① LLM API（Director + Writer + Reviewer） | 约 $0.49 → $1.7* | ≤ $15 | v3 Phase 10 Sprint 6-fix + Sprint 8-4 caching；Sonnet + Haiku 分工；prompt cache 5 分钟 TTL（场景 10 之后 cache hit ≥ 50%） |
| ② 图像生成（Nano Banana / DALL-E 3） | 已包含在 ①（每次 demo 约 $1.2） | 50-scene 约 $8-12 | Sprint 12-3b~c；**P0-2 素材库命中可通过同时避免 prompt LLM + 图像 API，节省 $0.02-0.05** |
| ③ 存储（S3-compatible / R2） | 约 $0.001 | 约 $0.008 | 每部作品打包后约 40MB（图像 + BGM），CDN 长尾成本可忽略 |
| ④ 带宽 | 约 $0.001 | 约 $0.01 | Web VN player（v4 ⑤）使用 SSE + JIT 场景传输，远低于一次性 ZIP |
| ⑤ 人工审核（P0-4 gate 兜底 + NSFW） | 约 $0（M0 仅使用白名单 gate） | $0.20-0.50 | Alpha 阶段由创作者自行审核；Beta 引入 Vision LLM 预筛 + 人工兜底（约 5% 需要人工，$0.5/次 × 5%） |
| ⑥ 联网检索（Serper fallback） | 约 $0（默认关闭） | 约 $0.02 | Serper 免费层 2500 次/月可覆盖前 500 部作品；超额价格为 $0.30 / 1k queries |
| ⑦ 支持/退款/异常处理 | — | 约 5% AOV | Beta 经验值 |

*$1.7 来自 v3 Phase 12-3 Showcase demo 实测（真实 Sonnet + Nano Banana + Haiku + Character Bible）。

### 6.3 单元经济性（Pro 层级生存测算）

| 场景 | 成本 | 假设价格 | 利润 | 备注 |
|---|---|---|---|---|
| 免费用户（3 部作品/月，mock 图片） | 约 $0.05 | 0 | -$0.05 | 引流产品；由付费转化补贴 |
| **简单粗暴的 Pro（10 部作品/月，50-scene 真实图片）** | 约 $150/月 | **$29/月** | **-$121/月 ❌** | 简单的单层 SaaS 模型**无法成立** |
| 仅限制为 3 部作品/月的 Pro | 约 $45/月 | $29/月 | -$16/月 | 仍为负数；LLM 成本占主导 |
| **按用量分层的 Pro**（3 × 10-scene 真实图片 + 40 × mock） | 约 $18/月 | $29/月 | **约 $11/月（38%）✅** | 用量分层使模型成立 |
| Team 层级（Chat Ops + 5 席位） | 约 $95/月 | $199/月 | 约 $104/月（52%） | Chat Ops 提供人机协作价值，用户有付费意愿 |
| 素材市场佣金 | 约 $0 | $3 平均价格的 15% | 约 $0.45/件 | 依赖交易规模；飞轮需要 6 个月 |
| 面向企业的 whitelabel | v3+v4 栈 | $2k-10k/月/客户 | > 80% | 单个客户即可覆盖平台运营成本 |

### 6.4 核心洞察（面试锚点）

> **“LLM 成本占主导 → 简单的单层 SaaS 模型无法成立 → 用量分层不是可选项，而是必选项。”**

其形态与 Cursor（订阅 + 后端 API 计量）、Perplexity（免费搜索 + 按需 Pro）、Poe（积分包）相同。VN-Agent 的差异在于，**preset 骨架在 v3 中已经存在**——`config/presets/budget.yaml`（全 Haiku，$0.01-0.02/run）与 `literary.yaml`（全 Sonnet + Nano Banana，$1.5/6-scene）已经实现用量分层的基础能力。因此商业化路径不是一页幻灯片，而只需调整接线。

**预判追问**：
- **“Pro 定价 $29 是拍脑袋吗？”** → 锚点：Cursor Pro $20 / Perplexity Pro $20 / Poe $20 构成 AI SaaS 的心理价格上限。让模型成立的是用量限制，而非价格本身。
- **“为什么补贴免费用户？”** → LTV 假设：使用 mock 图片的免费用户转化 Pro 的比例为 3-5%，Pro ARPU $116（平均 4 个月）。CAC ≈ $0.05 × 30 / 4% ≈ $37.5，显著低于 LTV $116。
- **“素材市场的版权风险？”** → 三重防御：P0-4 许可证 gate + 上传时 TOS 声明 + 平台不作为再授权方（marketplace 仅负责撮合）。Alpha 阶段仅支持 CC0/CC-BY + 用户确认拥有的作品。

---

## 7. 用户应准备的面试问题

### 7.1 “个人项目还是团队项目？”（最高频）
- **回答**：**个人项目，采用 AI 增强开发。**166 个 commit，约 15.8K 行源代码。开发工具链为 Claude Code（Anthropic 编程 CLI）+ Gemini CLI（通过 MCP 提供第二意见评审）。**AI 产品决策**（方向优先级评分、备选方案评估、成本模型、许可证白名单）由我负责；代码在大量 AI 辅助下实现。
- **重新定义问题**：面试官不是在考察你能否手写 15K 行代码，而是在判断你能否端到端推动 AI 产品。明确说明 AI 增强工作流本身就是能力信号——Claude Code / Cursor / Continue 正是现代 AI 产品经理的构建方式。隐瞒反而比坦诚更糟。

### 7.2 “竞品差异化？”
- **回答**：NovelAI / AI Dungeon / Charat 都是“用 LLM 生成故事”，但都无法导出 Ren'Py 项目，均不运行多 Agent 评测循环，也不提供单次运行的成本/可观测性。VN-Agent 的差异化是**平台 + 评测**，而非**生成质量**（Claude/GPT-4 的生成能力始终会超过个人 prompt engineering 的上限）。护城河是 AgentOps 底座 + 多源融合 + Chat Ops 工作流——这些能力不会因 OpenAI 发布下一代模型而商品化。

### 7.3 “能商业化吗？”
- **回答**：见 §6。不是一条路径，而是三条（SaaS + marketplace + 面向企业的 whitelabel）。LLM 成本占主导时，单层 SaaS 模型无法成立（后端成本 $150 vs $29 心理价格上限）。用量分层（按作品配额 + mock/真实图像拆分）使 Pro 层级利润率约为 38%；$199 的 Team 层级利润率约为 52%；面向企业的 whitelabel 可达 80%+，但需要 P4 稳定。**v3 preset 骨架已经实现用量分层的基础能力**，因此这不是停留在幻灯片上的设想。

### 7.4 “为什么不用 Cursor / OpenAI 直接生成完整视觉小说？”
- **回答**：实际尝试后会立刻撞上两堵墙。（1）**Prompt 膨胀**：单次要求生成场景 + 角色 + 分支 + Ren'Py 代码，会触发 `max_tokens` 截断（v3 M0 真实运行中，Writer 截断率达到 89%）。（2）**一致性**：20-scene 视觉小说需要跨场景的角色语言风格一致性 + 符号化世界状态（章节间保持 `manuscript_read=True`）；单次调用的 LLM 没有明确状态锚点。Multi-Agent DAG + Character Bible + Symbolic World State + StructureReviewer 是针对这些问题设计的工程方案，而非为了炫技堆架构。

### 7.5 “如何衡量 AI 产品成功？”
- **回答**：北极星指标 = **创作者完成率 ≥ 40%（beta）** + **会话中位时长 ≤ 45 分钟（10-scene）**。不是“生成质量”（不可证伪），也不是“使用 token 数”（虚荣指标）。辅助指标包括：**多样性指数 ≥ 30%**（非 LLM 素材占比，即反同质化指标）、**Chat Ops NPS ≥ 40**（人机协作的真实体验是否良好），以及技术底座指标（cache read ratio ≥ 50%，50-scene 端到端墙钟时间 ≤ 30 分钟/成本 ≤ $15）。

### 7.6 盲点追问（来自 plan §“面试可辩护性自审”的演练回答）

- **“P0 多样性指数怎么算才不作弊？”** → 非 LLM 素材具有字节级来源标签。多样性在导出时根据来源标签计算，而非自行申报。
- **“P1 没有真实用户怎么形成飞轮？”** → M0 = alpha + 作者自用；核心信号是**闭环已存在**，而非语料规模。数据来自三条自然渠道（alpha + Autopilot 玩家 + Vision Judge 隐式反馈），而非单一入口。
- **“P1 L3 DPO 不做是不是缩水？”** → 这是 M0 的明确范围；L3 需要 ≥1k 条记录 + 训练算力——M0 两者均不具备。**这是范围管理能力，不是缩水**。
- **“P3 Chat Ops 与 Cursor 如何差异化？”** → Cursor / Continue / Cody 是**面向代码的通用 chat ops**。VN-Agent 是**面向视觉小说流水线的垂直 chat ops**——每种意图（修改对话/添加角色/调整分支）都会分发到具体 Agent（Writer/Character/Director）。垂直深度不会被通用工具取代。
- **“P3 intent router 的 LLM 失效怎么办？”** → 四级 fallback：L1 预览卡片（M0 默认）→ L2 置信度阈值 → L3 Top-K 选项 → L4 将误分类纠错反馈给 P1 飞轮。**L4 回流 P1——这就是数据飞轮**。
- **“P4 M0 只报告、不闭环有什么用？”** → 报告本身就是产品价值（发布前“一键体检卡”）。M0.5 = 将结果作为软约束反馈给 Director prompt；M1 = 作为第 3 层 Reviewer 加入修订循环（受成本 gate 限制）；M1.5 = 以 Pearson r 对比人工结果验证 Vision Judge（复用 v3 Sprint 8-1 跨 Judge 模式）。
- **“P5 Autopilot 最优参数从哪里来？”** → M0 = 人工策划 preset；M0.5 = 每次运行写入 `data/autopilot_runs.jsonl`；M1 = 按 P4 Vision 评分 + 完成率排序；M2 = 主题 embedding → 最近邻运行 preset（接近推荐系统形态）。

### 7.7 P6 改版追问（来自 `FRONTEND_REDESIGN_v4.md` §9，并补上真正交付后才浮现的几问）

- **“改 UI 算产品工作吗？”** → 改的不是皮肤，是**信息架构**——把系统里已经存在但不可见的多 Agent 协作过程暴露给用户。“让 AI 的工作过程可解释”是 AI 产品经理的核心命题，这是它的一次具体落地。
- **“流水线可视化是不是花架子？”** → 它消费的是**真实的 LangGraph 节点事件**，不是假动画。证据：浏览器里观察到的事件序列包含 `structure_reviewer → director_step2_redo → structure_reviewer` 这段**真实的修订回环**——假动画编不出回环。而且顺带修掉了两个真实缺陷：10 个节点里 6 个的内部标识符会直接漏给用户（`Running cross_ref_sync`），以及进度条第 2 格永远走不到。
- **“为什么不直接用组件库？”** → 图标用 lucide，但拒绝整套预制组件——差异化在信息架构，不在按钮圆角；预制组件库正是“模板感”的来源。动效连库都没用，改用 CSS：framer-motion 为两个效果收 44 kB gzipped，不值。
- **“怎么保证不把能跑的东西改坏？”** → 前端**没有测试框架**，这是事实，所以不能靠测试兜底：契约冻结（`api.ts` 与 store action 签名只加不改）+ 六层迁移 + 新旧外壳并存，`?shell=v1` 一个 URL 参数即可退回可用状态。
- **“那你怎么知道新界面真的能跑？”**（最该主动答的一问）→ 分开讲：语言切换、v1/v2 切换、完整 Autopilot 跑通、节点事件序列——**这四项在真实 mock 浏览器会话里验证过**；Task 10-13 之后的最终 v2 外壳走查**没做**，因为浏览器插件中途掉线，之后只有构建 + 类型检查 + 静态检查。所以默认外壳至今没翻到 v2——翻默认值这种改动，不能只靠类型检查交付。
- **“i18n 不就是查字典替换吗？”** → 难点不在字典，在**状态**：聊天记录如果只存渲染后的文本，切语言就只能翻译新消息、历史还留在旧语言。所以消息存 key + vars、在渲染时解析，切换会重译整段历史。另外节点标签放在**前端**翻译而不是后端，因为 SSE 事件本来就带结构化 node id，后端保持稳定英文标识——这又回到同一个原则：结构化信号别降级成散文。
- **“209 个 key 怎么保证中英不漏？”** → 不靠人盯：`dict[lang][key]` 的类型定义让 `tsc` 在 en 缺 key 时直接构建失败。纪律做不到的事，交给类型系统。

---

## 8. 简历 bullet 种子（结构化供 LLM 重新生成）

格式：**声明** · **量化结果** · **证据路径/commit**。按强度由高到低排序。

1. **设计并交付用于端到端视觉小说生成的 6-Agent LangGraph DAG**（Director / StructureReviewer / StateOrchestrator / Thinking / Writer / DialogueReviewer / Assets），使用 `can_writer_fix` 类型化路由跳过无效重写，每次 6-scene 运行节省约 $1.10——`src/vn_agent/agents/graph.py`、`src/vn_agent/agents/routing.py`、commit `8a2ac88`。

2. **构建跨模型评测框架**（Sonnet 自评 + GPT-4o 独立评审），实现 **Pearson r = 0.643、±1 分一致率 = 87%**，化解“同模型自评”回音室质疑——Sprint 8-1、commit `4f1228f`、`docs/PRODUCT.md` §关键指标。

3. **开展数据驱动的 `writer_mode` 8-cell 扫描实验**，发现 **literary 4.17 > action 3.92，且在偏动作的 dragon 主题上仍然如此（4.5 vs 4.17）**，因此将默认模式从 `action`（few-shot RAG）切换为 `literary`（physics prompt）——Sprint 8-5、`docs/v2/RESUME_v2.md` §评估实测数据。

4. **交付 v4 P1 M0 数据飞轮**（创作者 👍/👎 → JSONL 仅追加存储 → BM25 injector `top_k=3, down-votes-only` → Haiku Reflection Agent 生成 `dynamic_guidelines.json`），跑通 v3 所缺少的“用户反馈 → 系统改进”闭环——commit `49baaf2`、`src/vn_agent/feedback/{store,injector,reflection}.py`。

5. **交付 v4 P0 M0 多源素材融合**（文本上传 + Serper 联网检索 Agent + 11 个素材的 CC0 种子库 + 跨来源 pHash/embedding 去重 + CC0/CC-BY/CC-BY-SA/user_owned/derived 许可证白名单 gate），目标为**多样性指数 ≥ 30%**——commits `d1746d4`、`eed2c2d`、`1957158`、`src/vn_agent/assets/`。

6. **将 RAG 从对话 few-shot（存在风格污染）转向世界观实体检索**，保留原有 FAISS + sentence-transformers 基础设施，仅改变被查询的实体类型——Sprint 10-2、`src/vn_agent/eval/lore.py`。

7. **构建三层长篇记忆**：Character Bible 作为 `cache_control=ephemeral` 的 prompt-cached suffix（首次 1.25×，复用 0.1×）+ 在 ≥15 scenes 时启用的 Haiku 递归场景摘要 + 滑动窗口 `writer_context_window`——Sprint 11-1/11-2/11-3。

8. **将成本与可观测性设为一等能力**：通过 ContextVar 实现单请求 `TokenTracker`（多任务安全）+ `run_metrics.json`（wall / cost / cache_read_ratio / health_status / degradation_signals）+ 每场景 `rag_retrievals.jsonl` 审计 + 压力测试器的 `--abort-on-degradation`——Sprint 6-5、Phase 13 M0-4。

9. **定位并修复 Reviewer 静默卡死 52 分钟的问题**：增加 `pending-debug` 预落盘（在 LLM 调用**之前**写入 `debug/{name}.pending.txt`，调用后重命名）+ `asyncio.wait_for` 硬超时 + `salvage` 工具，从卡死运行的 `vn_script.json` / `snapshots/*.json` 中恢复已完成场景——commits `d52261c`、`47d50fa`、`src/vn_agent/salvage.py`、`src/vn_agent/services/pending_debug.py`。

10. **设计四盲点联动网络**：让每个 M0 缺口（用户数据薄/LLM 误分类/缺少闭环/参数依赖人工）成为另一个盲点后续方案的输入，将真实缺口重新界定为“数据飞轮的产品设计思维”——`plans/cached-wibbling-karp.md` §“产品盲点后续跟进方案”。

11. **使用三维评分（简历亮点 · demo 展示力 · 产品落地性），从 3 种备选顺序中确定方案 Y（10-14 周）优先级**；P0 多源能力按预测在约 2 周内交付——plan 文件 §“Context”、评分矩阵。

12. **构建三路径商业化模型**（SaaS + marketplace + 面向企业的 whitelabel），完成七层可变成本拆解与单元经济性测算；结果显示单层 Pro 定价 $29 时每月亏损 $121，而按用量分层的 Pro（3 次真实图像 + 40 次 mock）每月利润约 $11（38%）——`docs/v4/PRODUCT_v4.md` §9。

13. **通过 Anthropic Tool Use 实现结构化输出，并构建 Writer 三级恢复链**（JSON array parse → 逐对象花括号扫描 → continuation call）；尽管 M0 真实运行中 `max_tokens` 触顶率为 89%，仍将 100% 场景恢复至 ≥5 行对话——`src/vn_agent/schema/script.py:418`、commits `05db6d8`、`441fbc6`。

14. **通过 Anthropic Key Pool + 指数退避 + Sonnet/Haiku 分池提升 API 韧性**，并在压力测试器中增加健康 gate（`retry > 5` / `key_rotation_density > 1.0` / `wall_minutes > 2× expected` → 标红 → 在消耗 50-scene 层级的 $15 前中止）——commits `95b8b97`、`745e03d`。

15. **通过模型分层实施成本工程**（Sonnet 负责创意型 Director/Writer，Haiku 负责偏转换任务的 Reviewer/summarizer/asset agents）+ prompt caching，使 budget preset 成本降低约 73%（每 MTok $3/$15 vs $0.80/$4）——Phase 6、Sprint 8-4。

16. **将中文视觉小说设为一等横切约束**（CJK 检测 + 面向 CJK 的 langchain-text-splitters `chunk_size=300` + `character_id/scene_id` 使用英文但展示层使用中文 + P0 质量 gate：中文 6-scene 端到端 Reviewer 平均分 ≥ 3.5）——`docs/v4/PRODUCT_v4.md` §8。

17. **交付 Chat Ops M0 及四级 intent-router fallback 规划，L1 已建成**（默认执行前预览确认卡片；L2 置信度阈值 / L3 top-K / L4 反馈回流飞轮是明确路线图，尚未构建）——commit `47d59e4`、`src/vn_agent/chat_ops/`、plan 文件 §“P3 intent router · LLM 塌房 4 级 fallback”。

18. **166 个 commit（v3 baseline）· 约 15.8K 行 src · 约 12.4K 行 tests · 659 个单元测试通过（v3）· 截至 v4 P0-P5（2026-07-29）共 939 个测试用例 · v4 之前 3 次已验证真实 API smoke 运行（总支出约 $3.74）**——使用 Claude Code + Gemini 进行 AI 增强开发的个人项目，采用适合校招的诚实表述。

19. **交付 SSE 即时场景流式推送**（`services/job_events.py` 每任务 pub/sub，与 `TokenTracker` 同款 ContextVar 作用域），让播放器随管线写出实时显示场景，而不是等完整脚本生成完——把"提交后等待"变成一个可见的生成过程——commit `a309058`。

20. **交付 PlaytestAgent + Vision LLM Judge M0**，其中包含一次开发中途诚实记录的范围调整：勘查发现仓库完全没有 Ren'Py headless 执行基础设施，M0 因此从"真实引擎截图"转向"基于管线自身生成美术的 Pillow 帧合成器"，真实引擎截图推迟到 M1——`services/llm.py` 由此获得仓库首个 vision LLM 调用点——commit `c4793a5`。

21. **在设计 Autopilot 成功率 KPI 时发现并修复了一个真实正确性 bug**：`POST /generate` 过去会对每次真实（非 mock）生成静默触发两条独立竞态的代码路径，其中一条持有并发信号量、另一条没有——在这个 KPI 建立在竞态条件之上之前，用一个请求级 `interactive` 标志修复——commit `5e8d621`。

22. **在一次例行 `--mock` CLI 冒烟测试中发现、披露并修复了一个真实成本安全缺口**：该 flag 让 8 个 agent 模块中的 2 个悄悄绕过了 mock patch，通过一个内部重新 import LLM 客户端的 helper 函数产生了 5 次真实 Anthropic API 调用（约 $0.12）。立即停止、用安全（非网络）证据定位根因、在动手修复前完整披露，随后通过设置 LLM 客户端内部本就会检查的同一个 ContextVar，堵住*所有*调用路径的口子（而不只是被抓到的那些），并加了永久回归测试——commit `5e8d621`、`tests/test_cli/test_mock_patch.py`。

23. **设计了基于 `ContextVar` 的逐任务 settings 覆盖机制**（`config.py::get_settings()`），让 Autopilot 能给每个生成任务分配独立调优的 preset，而无需触碰 agent graph 里约 20 处现有调用点——沿用（而非重造）代码库里 mock 模式和 token tracker 已有的同款作用域模式——commit `5e8d621`。

24. **在 M0 范围内完整交付了 v4 六阶段路线（P0→P5）**——多源融合、数据飞轮、流式 UI、Chat Ops、PlaytestAgent、Autopilot——每个阶段均带测试交付，每个阶段的诚实缺口（数据薄/LLM 误分类风险/仅报告不闭环/参数靠人工/UX 未做浏览器验证）均记录在案而非隐藏，六个阶段中有三个（P3/P4/P5）在开发中途做过明确的、经用户确认的范围调整——plan 文件 `cached-wibbling-karp.md`。

25. **端到端修复了一处"结构化信号被降级"的缺陷（v4 P6）**：LangGraph 流水线每个节点吐一次事件，web 层却把它压成一个 progress **字符串**，前端再对该字符串做子串匹配、猜回五步进度条。改为 `publish_node` → SSE `node` 事件 → store `pipelineNodes` → `PipelineGraph`，让多 Agent 流水线——这个产品的核心差异化——第一次在产品里可见。同一次改动还修掉两个潜伏缺陷：**10 个图节点里 6 个没有标签**（用户看到 `Running cross_ref_sync`）以及**显示步骤 2（审校）不可达**，因为 `'script'` 子串判断抢先命中——commits `fa68464`、`7c8a339`、`5fe971d`、`0315aad`、`782b5de`、`tests/test_web/test_pipeline_labels.py`。

26. **否掉自己的第一版设计提案，并把它从配色重新定义为信息架构**：三个"视觉方向"被用户一句话否掉（"这三个的区别感觉只是颜色而已"），于是重新勘查并指名两个结构性缺陷——恒定五五分栏导致的通用 AI SaaS 模板感，以及在 UI 里完全不可见的多 Agent 流水线。交付 `WorkbenchShell`，布局形态随 `AppStep` 走，聊天列宽度是"当前阶段在讲什么"的函数（player 0、pipeline 20rem、其余 24rem）——commit `4f26c00`、`docs/v4/FRONTEND_REDESIGN_v4.md` §1.2。

27. **在完全没有测试框架可依靠的前提下，用六层独立可回滚的迁移改造一个在跑的 UI**：`api.ts` 与 store action 签名契约冻结（只做加法），新旧外壳并存在 `?shell=v1` URL 逃生口之后并持久化到 localStorage，且默认值刻意留在旧外壳、把切换卡在浏览器走查这个前置条件上——commit `8113a7f`、`frontend/src/shell/useShellVariant.ts`。

28. **为一个 100% 硬编码英文的界面补齐中英双语，并让类型系统保证对齐**：每种语言 209 个 key、集合完全一致，缺 key 时 `tsc` 直接构建失败；聊天记录存 key + vars、渲染时解析，因此切语言会重译**整段历史**而不只是新消息；节点标签在前端本地化，因为 SSE 事件本就携带结构化 node id——commits `bfdf963`、`b046835`、`da5659a`、`5b1ebeb`、`frontend/src/i18n/dict.ts`。

29. **在造成包体积回归的那个 commit 里如实记账，随后把它消除**：L4 为两个动画引入 framer-motion（81 → 125 kB gzipped，在 `4f26c00` 中对照计划的 TTI ≤ 3s 目标公开写明），随后改用 CSS `@keyframes`，落到 84 kB——整个改版净增约 3 kB，且严格更无障碍，因为 JS 库改内联样式会绕过 `prefers-reduced-motion`，而 `@keyframes` 自动尊重它——commit `717c203`。

---

## 9. 给下游 LLM 的警示说明

### 9.1 强声明（可以增强语气，但不能夸大数字）
- 评测基础设施（跨 Judge Pearson r、8-cell 扫描、5 维 rubric、确定性结构检查）真实存在；每个数字均有仓库证据。
- v3 已交付功能（多 Agent DAG、RAG 转向、三层记忆、符号状态、prompt caching）均经代码验证。
- v4 P0/P1 M0 功能（多源融合 + 数据飞轮 L1+L2）是刚刚落地且配有测试的 commit。
- 商业化思考（三路径、七层成本、单元经济性）有计算依据。

### 9.2 以下声明**不得**夸大
- **用户规模**：除作者外，本项目没有真实用户。**不得**写“服务 100+ 创作者”；应写“为创作者设计，计划招募 3-5 名 alpha 用户”。
- **数据飞轮规模**：L1 + L2 正在运行，但语料规模较小。**不得**写“基于 10k+ 反馈记录训练”；应写“闭环已交付，数据仍在持续收集”。
- **P0-P5 六阶段截至 2026-07-27 均已交付 M0 级别代码 + 测试**（详见 §2.4-2.7）。这与本文档 2026-07-19 草稿版本（当时写"P2-P5 均未交付"）不同——那句话现已过时，不要再使用。但这里的"已交付"指的是 **M0 级别、单元/集成测试覆盖、mock 模式验证过**——**不等于**"在真实生产流量上验证过"。这两类声明要分开：
  - ✅ 可以用现在时声称："Chat Ops M0 已实现且测试覆盖" / "流式播放器、PlaytestAgent、Autopilot 均已构建并通过测试套件"。
  - ❌ 尚不成立，不要声称：P2-P5 的任何一项 UX 都做过**浏览器手工点击验证**（2026-07-21 起明确延后，截至 2026-07-29 仍未做）——应说"代码完成、测试覆盖，UI 走查待补"，不要说"已现场演示过"。
  - ❌ 尚不成立：Autopilot 自身的 KPI（成功率 ≥ 85%、墙钟 ≤ 8 分钟）**尚未在真实运行上测量过**——只有 mock 模式 + 单元测试。应说"已埋好测量点，首次真实运行验证待做"。
  - ❌ 尚不成立：Chat Ops"每会话 ≥ 8 次操作"和 Vision Judge"≤ $0.20/run"仍是未测量的目标（无真实用户，Vision Judge 也无真实 API 实测）——和下面已有的 50-scene / diversity index 目标同等对待。
- **50-scene 长篇**：基础设施已具备，但完整 50-scene 的时长/成本声明是**根据 6-scene baseline 推算**，并非实测。应写“正朝 50-scene 成本低于 $15 的目标推进”，不能写“已实现 50-scene 成本 $15”。
- **多样性指数 ≥ 30%**：这是**目标**，不是实测结果。应写“目标达到 30%+”，不能写“已达到 30%+”。
- **Vision Judge 有效性**：已构建（P4 M0），但只做过 mock 验证（英文+中文 mock 生成截图的人工视觉检查）。**不得**声称已获得 Vision Judge 的 Pearson r 或真实每次运行成本；只能陈述实测的 Sonnet vs GPT-4o 跨 Judge r=0.643（这是另一组 v3 时代的评审对比，不是同一件事）。
- **P6 前端改版（2026-08-10）**：同样适用"M0 交付 ≠ 生产验证"的纪律，并且多一条轴——这项工作在一个**尚未合并的分支**上（`feat/frontend-redesign-v4`），而且**默认外壳仍然是旧的**。
  - ✅ 可以声称：改版在 L4 层面代码完成、构建通过、可在 `?shell=v2` 访问；后端 `node` 事件链路、10/10 节点标签、步骤 2 修复、209 个 key 的中英词典都已在代码树中，且 key 对齐由类型系统强制。
  - ✅ 可以声称，并且值得精确声称：**有四项在真实 mock 模式浏览器会话里验证过**——实时语言切换、`?shell=v1`/`v2` 切换与 localStorage 双向粘性、在 v2 外壳中跑完整 Autopilot 直到编译产出、以及包含真实修订回环 `structure_reviewer → director_step2_redo → structure_reviewer` 的实时节点事件序列。
  - ✅ 可以声称：**最终** v2 外壳（Task 10-13，故事板、卡片详情、形态驱动布局）已于 2026-08-11 完成浏览器走查并 **10/10 通过**，而且走查本身抓出了两个类型检查抓不到的缺陷（英文活动行、聊天按钮换行），均已修复。应说"mock 模式下端到端走查过，10/10"。
  - ✅ 可以声称：改版**已是默认**（`DEFAULT_VARIANT = 'v2'`，`3730936`），且是走查通过之后才切的。❌ 不成立：说它已合并——分支 `feat/frontend-redesign-v4` 仍未合并，Task 15（删旧外壳）刻意押后。应说"已是默认外壳，逃生口保留，分支待合并"。
  - ❌ **不要**给出 TTI 数字。TTI ≤ 3s 仍是目标；包体积是实测的（`717c203` 之后 84 kB gzipped），TTI 不是。
- **P5 mock 安全事故（2026-07-27）可以完整讲**——这对 AI 产品经理面试是真正的正面信号（自己 dogfooding 发现、修复前先披露、精准根因定位、加永久回归测试锁死），不需要淡化或隐瞒。不要夸大金额（实际是 $0.12 / 5 次调用），也不要暗示它发生在生产/用户可见的场景——它发生在候选人自己的 CLI 冒烟测试里。

### 9.3 AI 增强开发表述（应这样说，而非那样说）
- ✅“使用 Claude Code + Gemini 作为结对编程工具构建；产品经理决策（方向优先级、成本模型、许可证 gate 白名单）由我负责，代码通过 AI 增强方式实现。”
- ❌“8 个月独立手写 15K 行生产级 Python”（不诚实，面试官也不会相信）
- ✅“产品的独立负责人；166 个 commit 体现从规格定义到交付的端到端所有权。”
- ❌“一人团队”——无法传达有效信息。

### 9.4 中文简历中值得原样保留的表述
- “简历爆点”——对应英文 “resume standout”，但直译会失去语境
- “AI PM 高频题”——评测语境词汇
- “数据飞轮”（data flywheel）——与自行翻译的英文表达语义略有差异
- “面试可辩护性自审”——整句话能体现主人翁意识
- “闭环已跑通”——M0 规模交付的关键表述
- “北极星指标”（North Star metric）——标准产品经理术语，在中文中更自然

### 9.5 给下游 LLM 的重新生成优先级提示
若必须压缩为 3-5 条 bullet：选择种子 1 + 2 + 3 + 4 + 12。若压缩为一行：选择种子 4 + 5（v4 P0/P1 刚刚交付 + AgentOps 评测底座），因为这些证据最新，且对 AI 产品经理面试问题的覆盖度最高。

若 JD 强调**评测 / AgentOps**：优先使用 2 + 8 + 9 + 3。
若 JD 强调**产品 / 用户**：优先使用 4 + 5 + 10 + 11 + 12。
若 JD 强调 **AI 原生基础设施**：优先使用 1 + 6 + 7 + 13 + 14。
若 JD 强调**人机交互 / 可解释性 / 偏前端的产品岗**：优先使用 25 + 26 + 28 + 17——种子 25 是整个项目里最强的"我把 AI 的过程做可读了"的故事，因为它是一个**缺陷叙事**（结构化信号 → 散文 → 再猜回来），而不是一串功能清单。
若 JD 强调**交付纪律 / 约束下的质量**：优先使用 27 + 29 + 22 + 9。

---

_简报结束。下游 LLM 应将本文档视为权威事实来源；简历 bullet 若需纳入本文档之外的信息，必须先在仓库中核验。_
