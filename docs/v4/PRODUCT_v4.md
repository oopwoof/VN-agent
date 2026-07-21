# VN-Agent 产品文档 v4

> **版本定位**：v4 是当前生效的产品北极星。
>
> - v1/v2/v3（产品愿景 + 工程需求）**保留但搁置**，索引见 [附录 A](#附录-a从-v3-shelved-回到-v4-的产品差异)
> - 本文档服务两个目的：(1) 指导 v4 阶段的产品开发；(2) 支撑 AI 产品经理校招沟通材料
> - **当前优先级：方案 Y（简历爆点最大化，10-14 周）** — 见第 5 节各方向优先级 P0-P5，与第 5.6 节 v3-shelved 回补方向（详细路线见 `plans/cached-wibbling-karp.md`）
>
> _起草：2026-07-08 · 优先级定稿：2026-07-13 · 语言：中文 · 归属：docs/v4/_

---

## 0. 一句话

**VN-Agent v4** 是一个让创作者用聊天完成 Visual Novel 生产的 **AI 工作台平台**：素材可外源引入，流程可对话式操作，可选一键 autopilot 给非创作者玩家生成个性化互动小说。

—— 核心变化：把 v3 的"多 Agent 流水线 CLI/API"**升级**为"以工作台为主界面、以对话为主交互、以创作者为主用户"的产品形态；同时把"能不能生产 50-scene"的工程北极星**下沉**为技术底座。

---

## 1. 为什么要 v4：v3 交付了什么，还缺什么

### 1.1 v3 已经交付的能力

| 能力 | 交付状态 | v4 的地位 |
|---|---|---|
| Director / Writer / Reviewer 多 Agent 流水线 | ✅ | 内核，不重写 |
| Ren'Py 编译输出 | ✅ | 后端可选导出格式之一 |
| 立绘 / 场景 / BGM 生成 | ✅ | 素材层的**默认降级路径**，v4 引入外源素材做优先路径 |
| CLI (`vn-agent generate`) + 简单 FastAPI + 早期 React 前端 | ✅ | v4 **重构前端 + 平台化**，CLI 保留为脚本入口 |
| 结构化 blackboard state (`vn_script.json`) | ✅ | v4 平台的**共享文档模型** |
| 可观测：TokenTracker、trace、cost、cache、run_metrics | ✅ | 直接进 v4 的运维看板 |
| 50+ scene 长篇能力（Phase 13-1/2/3） | 工程接近就绪 | 支撑 v4 "真实创作"而非 demo |

### 1.2 v3 的产品盲点（v4 要正面回答的）

| 盲点 | 用户侧表现 | v4 的回答 |
|---|---|---|
| **产品面貌太"工程"** | CLI + JSON + Ren'Py 三件套，创作者接受门槛高 | 方向 ①：**用户友好的前端工作台** |
| **同时服务玩家 + 创作者，两头都不深** | 创作者要引擎知识，玩家要装 Ren'Py SDK | 方向 ②：**聚焦创作者**，为潜在玩家提供 autopilot 快通道 |
| **生成内容同质化，缺"创作者的东西"** | 只有 theme 一个输入，输出千篇一律的 LLM 味 | 方向 ③：**多源素材引入**（上传 / 网检 / 本地开源库） |
| **工作流线性，无法回改和试错** | 一条路走到黑，中间过程不可见不可编辑 | 方向 ④：**Beyond-workflow 工作台**，对话式操作台上任意节点 |
| **成品是静态资产，无法体验"生成中"** | JSON → 编译 → 打包，用户看不到过程 | 方向 ⑤：**实时互动生成**，边玩边生成 |

---

## 2. 产品愿景与定位

### 2.1 一句话愿景

> 让每个有故事想讲的创作者，都能在一个可对话、可看见、可试错的 AI 工作台里，从主题走到可发布的 Visual Novel。

### 2.2 用户与场景

| 用户角色 | 场景 | 现有痛点 | v4 关键路径 |
|---|---|---|---|
| **主：独立创作者/写手** | 一个人从零做完一部作品 | 引擎学习门槛、美术资源短缺、没有反馈闭环 | 工作台 + 素材外源 + 分节可回改 |
| **主：轻度创作者/学生 UP** | 想验证一个故事创意 | 不想学 Ren'Py，也不想只写文字 | 对话式工作台，Autopilot 出可玩预览 |
| **次：玩家/受众** | 想玩定制化 VN | 现有 VN 库存有限，个性化生成成品少 | Autopilot 快通道，实时互动生成 |
| **次：教育/培训场景** | 教学互动、企业培训 | 手写脚本太贵 | 平台的模板 + 素材库能力 |

### 2.3 差异化

不是"又一个 AI 生成 VN 的 demo"，v4 的三条护城河：

1. **多 Agent 流水线 + 观测 + 评测** 的工程底座（v3 已有 659 单元测试 + 3 次真跑验证）
2. **多源素材融合**（上传 + 网检 + 本地开源库）做为一等公民，而非"生成不出来才降级"
3. **对话式工作台**让 PM/创作者共同编辑同一个文档，超越"一次生成一件事"的 workflow

—— 这三点其中任意一条都可以作为 AI PM 面试的差异化叙事锚点。

---

## 3. 产品北极星

### 3.1 首要指标（产品）

| 指标 | 定义 | 目标 | v3 现状 |
|---|---|---|---|
| **创作者一次完成率 (Completion Rate)** | 创作者从进入工作台到导出可玩作品的比例 | ≥ 40%（beta） | 无数据（CLI 无法追踪） |
| **单作品创作时长中位数 (Median Session)** | 从新建到导出的挂钟时间 | ≤ 45 分钟（10-scene 短篇） | 6-scene demo 约 30-60 min |
| **素材多样性 (Diversity Index)** | 输出中非-LLM-默认素材占比（上传/检索/开源库） | ≥ 30% | 0%（全生成） |
| **工作台交互满意度 (Chat Ops NPS)** | 用户对"对话式操作台"的满意度 | ≥ 40 | 无（无 chat ops） |

### 3.2 次要指标（技术底座，从 v3 沿用）

| 指标 | 目标 | 说明 |
|---|---|---|
| 50-scene 长篇端到端墙钟 | ≤ 30 min | v3 Phase 13 遗留北极星 |
| 单次生成 API 成本 | ≤ $15（50 scene） | v3 遗留 |
| Cache read ratio | ≥ 50%（scene 10+） | v3 遗留 |
| 服务 SLO | p95 首场景 TTFS ≤ 60s | v4 新增（实时互动前置） |

---

## 4. 产品架构（PM 视角）

```
┌──────────────────────────────────────────────────────────────────────┐
│                    创作者工作台 (v4 新增，方向 ①/④)                  │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐   │
│  │ 剧本视图      │ 素材面板      │ 预览播放器    │ Chat Ops 会话 │   │
│  │ (scene 树)   │ (上传/检索)   │ (实时互动)    │ (对话式操作) │   │
│  └──────────────┴──────────────┴──────────────┴──────────────┘   │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │  意图/指令/编辑事件
┌──────────────────────────────────▼───────────────────────────────────┐
│                   Autopilot 快通道 (v4 新增，方向 ②)                 │
│    玩家侧一句话主题 → 全参数自动选择 → 端到端交付可玩产物            │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────┐
│              素材层 Fusion (v4 新增，方向 ③)                         │
│  ┌────────────┬────────────┬────────────┬──────────────────┐      │
│  │ 用户上传    │ 网络检索    │ 本地开源库  │ LLM/图像生成      │      │
│  │ 文本/图片   │ (web/RAG)  │ (asset lib)│ (v3 已有降级路径) │      │
│  └────────────┴────────────┴────────────┴──────────────────┘      │
│           ↓ 素材去重 / 语义匹配 / 版权与安全 gate                    │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────┐
│           v3 多 Agent 生成内核 (Director / Writer / Reviewer ...)    │
│           + LangGraph orchestration + 观测/评测/成本追踪            │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────┐
│      实时互动生成引擎 (v4 新增，方向 ⑤)                              │
│      流式 Scene 交付 · 玩家分支影响后续生成 · 边玩边算                │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │
                                   ▼
              导出：Web 可玩 / Ren'Py 工程 / 分享链接
```

---

## 5. 五大产品方向（用户输入的 5 项）

> 每项包含：**产品意图 · 核心用户故事 · 交付形态 · 关键指标 · 依赖 · 风险**。
> **优先级**栏位留空，由产品负责人后续填入（不做默认排序，避免自作主张）。

---

### ① 用户友好、展示清晰、设计美观的前端

**产品意图**：把 v3 的 CLI/JSON 三件套换成一个可以被非工程创作者使用的工作台前端；工程审美 → 用户审美。

**核心用户故事**
- 作为轻度创作者，我不写代码，我想通过图形界面看到我的剧本骨架、逐场景对白、角色立绘、并直接在页面上试玩。
- 作为专业创作者，我需要一个"编辑器 + 预览"的双栏工作面，节奏对得上 Google Docs 那种协作感受。

**交付形态**
- 单页应用（当前 `frontend/`, React + TypeScript），至少三个主视图：**剧本 (scene 树)** / **素材 (画廊)** / **预览 (播放器)**
- 设计语言：中性偏温暖，重视信息密度但不喧宾夺主；深/浅色一等公民
- 首帧内容 ≤ 3 秒可交互（骨架 + Skeleton loading）
- 状态视觉一致：生成中 / 待评审 / 需修正 / 已锁定 四种态；全局进度可见

**关键指标**
- 首屏可交互时间 (TTI) ≤ 3 秒
- 新用户 5 分钟内启动第一次生成的比例 ≥ 60%
- 页面报错率 ≤ 0.5% 单会话

**依赖**：v3 FastAPI (`src/vn_agent/web/app.py`) 已就绪；`vn_script.json` 作为共享文档模型可直接绑定前端状态。

**风险**：设计资源自带负担；建议前期用一套设计系统（例如 shadcn/ui + Tailwind）降低组件成本，不自研 UI kit。

**优先级**：**P2**（与 ⑤ 并行；2 周；demo 门面）

---

### ② 从"玩家+创作者双端"→ 创作者中心 + Autopilot 玩家路径

**产品意图**：v3 试图同时让"玩家玩"和"创作者创作"，导致两端都做不深。v4 明确：**主用户是创作者**，玩家路径退化为 **Autopilot 一键快通道**（"最优路径"，无需 UI 参与）。

**核心用户故事**
- 作为创作者，我在工作台里主导内容；页面上没有玩家侧的"玩"入口来分散我的注意力（玩家侧独立在 Autopilot 页面）。
- 作为潜在玩家，我不进创作者工作台；我通过独立入口，输入一句话主题 → 系统全自动选参数 → 拿到可玩产物。

**交付形态**
- Autopilot 单入口（一个 URL / 一个 API）：接受主题 + （可选）个性化偏好（长度、类型、深度）
- 后台以固定"最优参数配方"运行：模型选型、并发度、chapter rollup、素材降级顺序都不暴露
- 输出直接 Web 播放（不要求玩家装 Ren'Py SDK）
- Autopilot 内部记录哪次跑成功，反哺创作者侧的"推荐配置"

**关键指标**
- Autopilot 成功率（生成即可玩） ≥ 85%
- Autopilot 端到端墙钟 ≤ 8 分钟（10 scene 默认档）
- 创作者工作台 vs Autopilot 的 DAU 比例（观察产品实际主战场）

**依赖**：v3 preset（`config/presets/*.yaml`）+ mock 模式已可用；需要新增 "player-web-runtime"（把生成产物直接用 Web VN player 渲染，见方向 ⑤）。

**风险**：Autopilot 的 "最优参数" 需要长期数据校准；beta 阶段允许运营手动调 preset。

**优先级**：**P5**（3-5 天；demo 闭环；依赖 P0 素材库 + P2 web player + P1 数据飞轮反哺）

---

### ③ 多样化生成：外源信息引入（上传 · 网检 · 本地开源库）

**产品意图**：内容同质化的根源是"只有 theme 一个输入 + 只用 LLM 生成"。v4 让创作者可以把自己的世界观笔记、参考图、开源角色资产、维基百科条目都作为一等公民接进生成流水线。

**核心用户故事**
- 作为创作者，我有一个 10 页的世界观 word 文档，我想上传后 Director 生成剧本时能引用它；出现地名/角色不该是模型编的，是我笔记里的。
- 作为创作者，我上传一张参考画风的角色图，希望立绘生成沿用它的风格，而不是每次都是 LLM 平均脸。
- 作为创作者，我在生成 fantasy 世界时希望系统能从本地开源素材库里挑合适的地图/UI 元素，而不是全靠 LLM 生成。

**交付形态**
- **上传通道**：文本 (md/pdf/docx) + 图片 (png/jpg)；上传即入向量索引（chunk + embedding），生成前作为 RAG 源
- **网检通道 = search-agent 化**（不是简单 URL fetch）：用户给关键词/主题 → Haiku 生成 3-5 个查询 query → 首选 MCP `WebSearch` + `WebFetch`（Claude Code 内置零成本），次选 `mcp__gemini-cli__ask-gemini`（Gemini 3 Flash grounding 兜底），最后 fallback 到 `httpx` + 手贴 URL → 结果聚合去重 → 抽核心段落 → embed 入 `user_upload` scope。带**成本 gate**（默认 5 query cap + 8k tokens cap）+ **引用溯源**（每个 chunk 记 `source_url` + `retrieved_at` + `search_query`）。不自建 crawler、不写 headless browser。
- **本地开源素材库**：预置 CC0/CC-BY 的立绘、背景、BGM 素材（Kenney/OpenGameArt 级别）；语义标签检索；命中优先于 LLM 生成
- **素材去重**：跨来源 embedding 去重（同一张图/同一段文本只保留一份）
- **版权/安全 gate**：网检和上传素材过内容审核 + 版权提示

**关键指标**
- **素材多样性 Diversity Index**（v4 首要指标之一）
- 平均"每部作品外源素材占比" ≥ 30%
- 生成内容相似度（跨作品）下降 ≥ 20%（相比 v3 baseline）

**依赖**：v3 已有 FAISS + sentence-transformers 骨架；lore RAG（`src/vn_agent/eval/lore.py`）可直接扩为多通道；素材库需要新的 storage 层。

**风险**：版权与合规是大坑；beta 阶段建议只做 CC0/CC-BY + 用户明确授权上传两个来源；web fetch 默认关闭。

**优先级**：**P0**（当前阶段；2-3 周；☆简历爆点 #1 — "AI 如何避免同质化"）

---

### ④ Beyond-workflow 平台：工作台 + 对话式操作

**产品意图**：v3 是"提交主题 → 等 6 步流水线跑完"的一次性 workflow。v4 是"永久打开的工作台，用户可以对着任意 scene / 任意资产 / 任意流程节点，用对话式操作发起修改、追问、试错"。

**核心用户故事**
- 作为创作者，我看到 scene 5 的对白写得不像我想的那样，我不想重跑整个 pipeline；我在聊天框里说"scene 5 的女主要更迟疑一点"，工作台就只重生 scene 5。
- 作为创作者，我想加一个新角色，不想改 JSON；我在聊天里说"加一个反派学长，出现在 scene 3-6"，系统自动改角色表 + 相关 scene 提示 + 立绘请求。
- 作为创作者，我在工作台任意点右键都能问"这里为什么这样写"，系统能引用生成时的 Reviewer trace 回答。

**交付形态**
- **Chat Ops 面板**：常驻工作台侧栏；对话可**引用**任意资产/场景/评审结果（类似 Notion / Cursor 的选中引用体验）
- **意图路由**：把对话消息路由到 Director / Writer / Reviewer / Asset agent 之一或组合；用户不需要知道谁在做
- **可撤销 / 版本对比**：工作台每次操作都留一个 checkpoint（复用 v3 local_regen 的机制）；用户可 diff 两个版本
- **任务卡片**：长任务（重跑一整章、批量重绘）在工作台顶端显示进度卡片，用户可继续别的操作

**关键指标**
- 用户平均一次会话内 chat ops 操作数 ≥ 8 次
- "对话式操作"完成任务的比例 vs "点击式表单" ≥ 50%
- 一次会话内 checkpoint 回滚使用率 ≥ 20%（说明"敢试错"）

**依赖**：v3 的 `local_regen`（单 scene 重写）+ blackboard 状态机是核心；需要新建**意图路由层**（把自然语言映射到 pipeline 节点）+ 一个 orchestrator 前端 API。

**风险**：意图路由是 LLM 系统里的常见塌房区（用户说 A、系统跑成 B）；beta 阶段可用"意图预览 + 用户确认"降低误操作成本。

**优先级**：**P3**（3-5 周；☆简历爆点 #3 — "AI 产品如何设计人机协作"；工程风险最高，用 4 级 fallback 缓解，详见 [跟进方案](#p3-intent-router--llm-塌房-4-级-fallback)）

---

### ⑤ Visual Novel 的实时互动生成

**产品意图**：把"生成 → 打包 → 玩"的三段体验，压缩成"边生成边玩"，让"故事"和"生成"的边界消失。

**核心用户故事**
- 作为玩家，我进入 Autopilot 页面 30 秒后，第一场就可玩了；后面的场景在我读前几行时后台流式生成好。
- 作为玩家，我在 scene 3 做的选择会真实改变 scene 4-10 的走向，而不是提前烘焙好的分支树。
- 作为创作者，我可以**开启"直播模式"**，观察一个真实玩家怎么走过我的作品，观察 Reviewer 实时点评。

**交付形态**
- **流式 pipeline**：Director 出 outline → Writer 边写边推 scene → 前端 SSE/WebSocket 收到就播放
- **Just-in-Time Scene Delivery**：`pipeline_lookahead=2` 保证下一场景一定备好；玩家分支后 lookahead 重定向
- **玩家分支影响生成**：玩家的选择进入 Director 的"navigation state"，重新规划后续
- **Web VN player**：自研轻量播放器（不依赖 Ren'Py SDK），支持立绘/BG/BGM/选择菜单
- **直播模式（创作者）**：把玩家实时会话映射到工作台的 scene 树上高亮

**关键指标**
- 首场景可玩时间 (TTFS) ≤ 60 秒（v3 sprint 12-1 遗留北极星）
- 分支后 scene 生成延迟 p95 ≤ 15 秒
- 玩家中途放弃率 ≤ 15%（10-scene 平均）

**依赖**：v3 `LangGraph.astream` 已支持流式；需要写新的 web VN player + WebSocket bridge；分支后重规划需要 Director 支持"从 scene N 开始 replan"。

**风险**：流式 UX 是最烧钱的方向（wall-time 敏感 + 缓存失效频繁）；建议 M1 stress test 之后再开工。

**优先级**：**P2**（与 ① 并行；2 周；demo 视觉冲击力顶级；`pipeline_lookahead=2` 预取本来就要算的 scene，成本无增加）

---

## 5.6 v3-shelved 回补方向（B 数据飞轮 + C PlaytestAgent）

> 2026-07-13 优先级定稿时，把 v3 shelved `docs/PRODUCT.md` 的两个 P2 backlog 方向**拉回**作为 v4 简历爆点（源自"自我进化 Agent"与"PlaytestAgent + Vision LLM Judge"两条路线）。
> 两方向的选择基于三维打分（简历/demo/落地），与其他 5 大方向格式一致；也是**产品盲点跟进方案**的四轮联动的其中两轮，见每方向末尾"盲点跟进"子节。

---

### B · 自我进化 Agent M0（数据飞轮）

**产品意图**：v3 已有 TokenTracker + Trace 观测底座，但缺"用户反馈 → 系统改进"的闭环。B 方向做一个 3 层 minimum viable 数据飞轮（L1 BM25 few-shot + L2 Reflection 元规则 + L3 DPO 微调延后），1-2 周就跑通闭环，直接对答 AI PM 面试高频题"AI 产品如何做 AI Ops / 数据飞轮"。

**核心用户故事**
- 作为创作者，我看到 scene 5 女主对白"废话太多"，我在预览下面点👎 + 写理由"过于唠叨"；下次生成同类主题时 Writer 收到规则约束"绝对禁止：废话太多"。
- 作为产品，我每周跑一次 Reflection Agent，把散落的反馈归纳为一批元规则（"避免过多形容词""结局分支避免非黑即白"），写入 dynamic_guidelines.json，下次系统启动时自动挂进 Writer system prompt。

**交付形态**
- 前端 chat/preview 里的 👍/👎 按钮 + 原因输入 → 落 JSONL 到 `data/feedback/`
- `src/vn_agent/feedback/injector.py`：BM25 扫 JSONL（复用 v3 Sprint 6-4 rank_bm25），Writer prompt 前追加 few-shot "禁止：..."
- 异步 Reflection Agent（batch job）从 JSONL 提炼元规则 → `data/feedback/dynamic_guidelines.json` → 启动时拼进 Writer system prompt（走 v3 Sprint 8-4 prompt-caching 基础设施）
- **不做** L3 DPO 微调（超出 M0）

**关键指标**
- 反馈条数 → BM25 命中率
- Writer 输出规则违反率下降（用 v3 Sprint 8-2 规则化策略 metrics 复核）
- alpha 用户满意度 NPS ≥ 30

**依赖**：v3 rank_bm25 + prompt-caching + TokenTracker 全在；前端 chat/preview 已有

**风险**：M0 阶段无真实用户数据。缓解方案：3-5 alpha 用户（同学 + r/RenPy + 独立创作者社群）+ 作者自用；数据源不只 alpha，还包括 P5 Autopilot 玩家 + P4 Vision Judge 隐式反馈三条自然沉淀源

**盲点跟进（M0 → M2 5 步）**：见 `plans/cached-wibbling-karp.md` "P1 数据飞轮 · 真实用户数据补齐路径"

**优先级**：**P1**（1-2 周；☆简历爆点 #2 — AI Ops 数据飞轮）

---

### C · PlaytestAgent + Vision LLM Judge

**产品意图**：v3 已有 Sonnet + GPT-4o 双评审 + Pearson r 交叉验证的评测底座；C 方向把评测从"离线跑分"升级为"作品完成后一键体检卡"，创作者可见（UI coherence / dead-end detection / interactivity pacing / player agency / coverage 五维），直接对答 AI PM "AI 产品如何做评测和运维"。

**核心用户故事**
- 作为创作者，我导出前一键"体检" — PlaytestAgent 用 Ren'Py `config.skipping` 自动走完所有分支，Sonnet vision 看截图 + 对白判"UI 是否协调""是否有死路""互动节奏是否合适"；报告写入 `run_meta.json` 作为发布前编辑复审。
- 作为产品，M1 阶段分数回流 Director prompt 做闭环（"上次 dead-end detection = 2/5，本次重点检查分支可达性"）。

**交付形态**
- `src/vn_agent/playtest/auto_walk.py`：Ren'Py 官方 `config.skipping` + `--warp` + `renpy.screenshot()` harness 遍历所有分支
- `src/vn_agent/playtest/vision_judge.py`：截图 + 对白日志喂 Sonnet vision，评 5 维
- Eval 扩维度进 v3 `eval strategy` / `run_metrics.json` 骨架
- M0 阶段仅报告不闭环（成本 gate：每次 $0.20）

**关键指标**
- Vision Judge 打分 vs 人类玩家评分 Pearson r ≥ 0.5（复用 v3 Sprint 8-1 cross-judge 模式，M1.5 验证）
- 报告覆盖率（多少 % 作品发布前跑过体检）
- Vision Judge 成本 ≤ $0.20/run

**依赖**：v3 Ren'Py 编译器 + `eval strategy` + Sprint 8-1 Pearson r 都在；Sonnet vision API 现成

**风险**：Vision Judge 有效性未验证。缓解：M0 报告 + M1.5 用 v3 Sprint 8-1 cross-judge 模式做 Pearson r 验证 → < 0.5 触发 prompt 迭代；M2 用 Vision Judge 分数蒸馏 Haiku vision（distillation）降本 $0.20 → $0.02

**盲点跟进（M0 → M2 5 步）**：见 `plans/cached-wibbling-karp.md` "P4 PlaytestAgent · 闭环 3 步走"

**优先级**：**P4**（2 周；☆简历爆点 #4 — AI 评测闭环）

---

## 6. 与 v3 shelved 需求的映射（保留但搁置）

v3 的所有已建能力都不重写，v4 只做**收编**和**新增**。以下表格说明每个 v3 需求在 v4 里的地位：

| v3 需求 | v4 处理方式 |
|---|---|
| Phase 13-1/2/3 长篇 50-scene 工程 | **保留为技术底座**，v4 方向 ⑤ 依赖它 |
| Ren'Py 编译器 + 视觉层 | **保留为可选导出**，v4 主播放是 Web player |
| CLI (`vn-agent generate`) | **保留为脚本入口**（自动化 / 批量 / CI） |
| CharacterDesigner / SceneArtist / MusicDirector | **保留为素材层降级路径**（方向 ③ 命中外源素材优先） |
| Anthropic prompt caching / RAG / 多 Agent | **保留为内核**，不动 |
| 早期 React 前端 (Phase 9 Sprint 1-3) | **淘汰**，v4 前端重构（方向 ①） |
| 双端定位（玩家 + 创作者混合 UI） | **淘汰**，v4 拆成创作者工作台 + Autopilot 两个入口（方向 ②） |
| Phase 12-1 streaming pipeline | **升级**为 v4 方向 ⑤ 的一部分 |
| Sprint 13-2/3/4 job queue / cost caps / fleet | **保留为 backlog**，v4 beta 阶段暂不启动 |
| P2 四通道 RAG / 自我进化 Agent / Ren'Py 表现力 | **保留在 ARCHITECTURE.md**（shelved），v4 不承诺时间 |

详见 [附录 A](#附录-a从-v3-shelved-回到-v4-的产品差异)。

---

## 7. 用于 AI 产品经理校招的叙事锚点

（本节是给你自己看的：把 v4 抽象为面试可讲的 3 个产品能力）

### 7.1 定位一句话

> VN-Agent 是我做的一个 AI 工作台产品：主用户是 VN 创作者，通过对话操作一个多 Agent 生成流水线，把"从主题到可玩作品"的路径从 4 小时缩到 45 分钟；玩家侧我做了 Autopilot 快通道。它让我完整走了一遍 AI 产品 PM 的三个核心问题：**流程可视化 / 素材融合 / 评测闭环**。

### 7.2 三个可讲的产品能力（面试锚点）

| 面试问 | 你的锚点 | 展开材料 |
|---|---|---|
| "AI 产品如何避免同质化" | v4 方向 ③ 多源素材融合 | 讲上传 + 网检 + 开源库 fusion，讲版权 gate，讲素材多样性指标 |
| "AI 产品如何设计人机协作" | v4 方向 ④ Chat Ops 工作台 | 讲意图路由、checkpoint、版本对比、beyond-workflow 概念 |
| "AI 产品如何做评测和运维" | v3 遗留的 TokenTracker + 3 层 Reviewer + smoke health signal | 讲 AgentOps 的概念（Bad case 归因、多 Agent trace、cache hit 观测） |

### 7.3 会被追问的三个点（提前准备）

1. **"这是个人项目还是团队项目？"** — 个人项目 (170 commit / 15.8K LoC src)，用 Claude Code + Gemini 做 AI-augmented 开发；重点讲你在 PM 决策上的判断（例如决定 pivot 到创作者中心的依据）。
2. **"竞品呢？"** — NovelAI / AI Dungeon / Charat 都不出 Ren'Py 工程，也不做多 Agent 评测闭环；v4 差异化在**平台 + 评测**而不是**生成质量**（这个模型比不过大厂）。
3. **"能商业化吗？"** — 短期不做 to C 收费；讲 SaaS + 素材市场 + 工具链授权三个可能路径；重点是"AI 生成已经不稀缺，工作台和评测底座才是壁垒"。

### 7.4 阶段交付状态（2026-07-21 更新，只列已核实事实，不列未测过的目标值）

| 阶段 | 状态 | 已核实的事实 |
|---|---|---|
| **P0** ③多源素材融合 | ✅ 已提交 | `assets/{library,dedup,license_gate,text_ingest,web_search_agent}.py` + `metrics/diversity.py` 落地；diversity index 已实现并写入 `vn_script.json.metrics`，**尚未在真实 API 跑一次拿到实测百分比**（目标 ≥30% 仍是目标，不是已验证数字，讲的时候要如实区分） |
| **P1** B数据飞轮 | ✅ 已提交 | BM25 injector + Reflection Agent（Haiku）+ 前端 👍/👎 落地；M0 阶段无真实 alpha 用户反馈数据，闭环用合成/mock 反馈验证过跑通，**不能说"已有用户数据"** |
| **P2** ①前端+⑤流式 | ✅ 已提交（浏览器烟测未做） | Tailwind v4 修复（此前 className 全部不生效，`npm run build` 现在产出 35KB CSS）；SSE scene_ready 流式播放落地；**没有实测 TTI/TTFS 数字**，这两个北极星指标目标值还是目标 |
| **P0+P1 合计测试** | — | `tests/test_assets` + `tests/test_metrics` + `tests/test_feedback` 共 173 个测试用例（2026-07-21 collect 计数） |

**面试口径提醒**：以上"已提交"只代表代码落地 + 单元测试通过，不代表北极星指标（diversity ≥30%、TTI ≤3s 等）已经用真实数据验证。讲的时候用"闭环已跑通，指标待真实流量验证"的措辞，不要把目标值说成实测值。

---

## 8. 横切约束：中文 VN 一等公民

> 面试展示优先场景是**中文 VN**（面试官母语，视觉冲击更强）。所有阶段的 mock demo + 真实 API smoke 都以中文为默认，不作为额外功能列。

### 8.1 现状事实（v3 已有基础）

- v3 已有 CJK 检测 → Writer 自动追加中文 prompt 指令（Phase 6 Sprint 3）
- v3 已有中文 mock fixture（"校园恋爱" 主题完整 Director+Writer 数据）
- v3 Ren'Py 编译已过中文（filesystem-aware emotion / 全 renpy_safe 覆盖 / 1920×1080 BG resize / sprite 3:4 portrait）
- **未验证**：真实 API 中文 6-scene 端到端质量（策略执行、Reviewer 打分、素材命名中文对齐）

### 8.2 每阶段中文交付要求

| 阶段 | 中文要求 |
|---|---|
| **P0 多源素材** | 素材库 manifest 支持中文 tag；上传中文 md/pdf 走 `langchain-text-splitters`（CJK chunk_size=300，英文默认 800）；diversity index 在中文下同样有效 |
| **P1 数据飞轮** | 👍/👎 原因输入支持中文；Reflection 元规则**用中文生成**（避免英文规则再翻译丢意思） |
| **P2 前端 + 流式** | 前端至少中英双语（默认中文）；`VNPreview` 中文 typewriter 效果按 grapheme（非 byte）切，不掉字 |
| **P3 Chat Ops** | 意图路由分类器 prompt 中文优先；意图预览卡片中文渲染 |
| **P4 PlaytestAgent** | Vision Judge 打分维度中英双语，主报告中文 |
| **P5 Autopilot** | 独立入口默认中文主题输入 |

### 8.3 质量 gate（P0 完成时验证一次，作为其他阶段的 baseline）

- 中文 6-scene 真实 API 跑通（用户 `--confirm` 触发，memory `feedback_api_approval`）
- Reviewer avg ≥ 3.5（与英文 baseline 持平；v3 现状 literary 4.17）
- 无中文字符编码 bug、无 Ren'Py 编译报错、无 emotion alias 断裂
- 命名规范：`character_id` / `scene_id` 保留英文（引擎 label 必须），显示层全中文

---

## 9. 商业化与成本模型

> 面试高频题："这个能商业化吗？成本能覆盖吗？"
> 这一节写"真会推向 alpha 收费"级别的思考，不是纸上定价——同时保持能在 30 秒讲清楚。

### 9.1 目标商业模式（3 条路径 × 优先级）

三条路径**不冲突**——同一个平台在不同用户 tier 上叠加。优先级按"能不能自然从 v4 P0-P5 长出来"排。

| 路径 | 描述 | 推进优先级 | 依赖 v4 方向 |
|---|---|---|---|
| **A · SaaS 订阅**（创作者 tier） | 免费额度（每月 3 作品 / ≤10 scene / mock 图像）→ Pro 订阅（无限作品 / 真图像 / 优先算力 / 私有素材库）→ Team tier（多人协作 / 共享 Chat Ops 会话） | **P0**（v4 自然形态） | ① 前端工作台 + ② Autopilot + ④ Chat Ops |
| **B · 素材市场**（marketplace 抽成） | 创作者上传自制立绘/BG/BGM，标价 or CC-BY 分成；平台抽 15-20%。**买家侧**：其他创作者付费下载并直接进本地素材库。 | **P1**（依赖 P0-2 库 + P0-4 版权 gate 上线后接支付） | ③ 素材融合（库是交易场） + P0-4 gate（合规前提） |
| **C · 工具链授权**（to-B 白牌） | 把 v4 的 Multi-Agent + AgentOps 底座（评测 / 观测 / diversity 指标）打包卖给游戏公司做内部内容生产工具。按 seat / 按调用计费。 | **P2**（需要 P4 PlaytestAgent 稳定后才有说服力） | v3 全套评测 + P4 PlaytestAgent + Chat Ops |

**不做**：广告变现（VN 用户量小，广告 CPM 承载不住成本）；一次性买断（LLM 后端持续成本，一次性收费会亏）。

### 9.2 成本分层（v3 实测锚点 + M0/M1 假设）

单作品**变动成本**分 7 层，每层给 v3 已有实测数字或明确假设。数字取自 `docs/PRODUCT.md` 关键指标 + `run_meta.json` 历史。

| 成本层 | 6-scene demo | 50-scene 目标 | 说明 / 来源 |
|---|---|---|---|
| **① LLM API**（Director + Writer + Reviewer） | ~$0.49 → $1.7*（含图像 prompt） | ≤ $15 | v3 Phase 10 Sprint 6-fix + Sprint 8-4 caching；Sonnet + Haiku 分级；prompt cache 5-min TTL（scene 10+ 命中率 ≥ 50%） |
| **② 图像生成 API**（Nano Banana / DALL-E 3） | 已含在 ①（~$1.2 / demo） | ~$8-12 / 50-scene | v3 Sprint 12-3b~c；**P0-2 库命中一次可省 $0.02-0.05**（避免 prompt LLM + 图像 API 两次） |
| **③ 存储**（S3 兼容 / Cloudflare R2） | ~$0.001 / demo（<5MB） | ~$0.008 / 50-scene | 每作品 ~40MB 打包（图像 + BGM），CDN 缓存后长尾成本可忽略 |
| **④ 带宽**（下载 + 在线播放器） | ~$0.001 / demo | ~$0.01 / 50-scene | Web VN player（v4 方向 ⑤）走 SSE + JIT scene delivery，带宽 << 一次性 ZIP 下载 |
| **⑤ 人工审核**（P0-4 license gate 兜底 + NSFW） | ~$0（M0 只做 whitelist gate） | $0.20-0.50 / 50-scene | Alpha 阶段作者自审；Beta 引入 Vision LLM 预筛 + 人工兜底（估 5% 需人工，$0.5/条 × 5%） |
| **⑥ Web search API**（P0-5 Serper 兜底） | ~$0（默认关闭） | ~$0.02 / 50-scene | Serper 免费 tier 2500 次/月覆盖前 500 作品；超额 $0.30 / 1k queries |
| **⑦ 客服/退款/异常**（分摊） | — | ~5% AOV | Beta 后按经验值 |

*注：$1.7 是 v3 Phase 12-3 Showcase demo（含真实 Sonnet + Nano Banana + Haiku + Character Bible）实测。

**固定成本**（不按作品分摊）：GPU/CPU（Autopilot 排队、SBERT embedding、rembg 抠图） · 域名 · Sentry 观测 · 支付通道 · 法务/合规。M0 阶段全部走 serverless（Cloudflare Workers + Render / Fly.io free tier）压到近零。

### 9.3 单位经济性与定价假设

| 场景 | 成本 | 假设定价 | 毛利 | 备注 |
|---|---|---|---|---|
| 免费用户（每月 3 作品，mock 图像） | ~$0.05 | 0 | -$0.05 | 引流；靠付费用户补贴 |
| Pro 订阅创作者（预估 10 作品/月，真图像 50-scene） | ~$15 × 10 = $150 / 月 | **$29 / 月** | 严重负毛利 ❌ | 说明纯 SaaS 单档不成立，必须做 tier + 用量限制 |
| Pro 订阅（限 3 作品/月 + 优先算力） | ~$45 / 月 | **$29 / 月** | -$16 / 月 | 仍负；LLM 侧成本主导 |
| Pro 订阅（限 3 × 10-scene 用真图 + 40 × mock 图） | ~$18 / 月 | **$29 / 月** | ~$11 / 月（38%）✅ | 需要"用量分级"设计（v3 preset 已有骨架） |
| Team tier（Chat Ops + 5 seat） | 上面 × 5 + 存储 = ~$95 / 月 | **$199 / 月** | ~$104 / 月（52%） | Chat Ops 交付人机协作，愿付 |
| 素材市场抽成 | ~$0（存储 + 带宽） | 15% of 单件（假设均值 $3） | ~$0.45 / 件 | 靠量走通；预估 P1 上线 6 个月能起飞轮 |
| To-B 工具链授权 | 底座已在（v3+v4） | $2k-10k / 月 / 客户 | > 80% | 一个客户覆盖全平台运营成本 |

**关键 insight（面试锚点）**：**LLM 成本主导 → 不能纯 SaaS 单档定价 → 必须"用量分级"**。这跟"cursor 按订阅但底层套 API 用量"、"perplexity 免费搜索 + Pro 按需求" 同构。我用 v3 preset 骨架实现了这个"分级"能力（budget preset 全 Haiku、$0.01-0.02/次；literary preset 全 Sonnet + Nano Banana、$1.5/6-scene）。

### 9.4 面试可讲的一句话

> "AI 生成本身不是护城河 —— OpenAI 明天开放同样的能力大家一起白菜价。所以我把成本模型设计在**用量分级 + 素材市场 + 工具链授权**三条腿：SaaS 是入口，Marketplace 靠交易费吃复利，to-B 工具链靠评测/观测底座（AgentOps）差异化。**先跑 SaaS 免费 + Pro 带用量限制**验证毛利，成本大头 LLM 通过 preset 分级 + prompt caching + 素材库命中降本。"

**会被追问**：
- Q: "毛利表里 Pro 档 $29 是不是拍脑袋？" → A: 对标 Cursor Pro $20 / Perplexity Pro $20 / Poe $20 是 AI SaaS 心理锚点；用量限制是让它数学上成立的关键，不是心理定价的关键
- Q: "免费用户为什么补贴？" → A: LTV 假设——mock 图像的免费用户里有 3-5% 转化为 Pro，Pro 平均订阅 4 个月 = ARPU $116。免费户 CAC ≈ 补贴总额 / 转化率 = $0.05 × 30 / 4% ≈ $37.5，远低于 LTV $116
- Q: "素材市场版权风险？" → A: P0-4 license gate + 上传强制授权声明 + 平台不做二次授权（只做撮合）三层防御；Alpha 只做 CC0/CC-BY + 用户自证素材两类白名单

---

## 附录 A：从 v3 shelved 回到 v4 的产品差异

| 维度 | v3 (shelved) | v4 (current) |
|---|---|---|
| 首要形态 | CLI + JSON + Ren'Py 工程 | Web 工作台 + Autopilot Web 页面 |
| 首要用户 | 创作者 + 玩家（模糊） | 创作者（明确） + 玩家（Autopilot） |
| 首要交互 | 命令行 / 表单 / 一次性生成 | 对话式工作台 / 可任意节点介入 |
| 素材来源 | 全部 LLM/图像生成 | 上传 + 网检 + 开源库 + LLM（降级） |
| 生成体验 | 生成完 → 打包 → 玩 | 边生成边玩（流式） |
| 首要指标 | 50-scene 工程可行性 | 创作者完成率 + 素材多样性 |
| 平台形态 | 单一 pipeline job | 常驻工作台 + 多 job 编排 |

## 附录 B：v4 之外仍生效的文档

| 文档 | 用途 | v4 关系 |
|---|---|---|
| `docs/PRODUCT.md` (v1-v3) | 历史产品记录 | **shelved，保留** |
| `docs/ARCHITECTURE.md` | v3 P2 长期架构路线（四通道 RAG / 自我进化） | **shelved，保留**（v4 不承诺 timeline） |
| `docs/DESIGN_DECISIONS.md` | 关键工程决策的"为什么" | **持续更新**（内核不变） |
| `docs/AUDITS.md` | 技术债 / 未完成修复 | **持续更新** |
| `docs/CHANGELOG.md` | 每日 commit 流水（hook 自动） | **持续更新** |
| `docs/v2/RESUME_v2.md` / `docs/v2/SHOWCASE_GUIDE_v2.md` | 简历/showcase 材料 | **另有校招用途，不影响** |
| `docs/v3/SHOWCASE_v3.md` / `docs/v3/BYTE_AI_PLATFORM_EVAL_INTERVIEW.md` | v3 面试口径 | **另有校招用途，不影响** |
| `docs/v4/README_v4.md` | v4 导航（本文档姊妹篇） | 本目录索引 |

---

_文档结束。5 大方向的优先级 / M0-M4 里程碑 / 具体 owner，由产品负责人后续填入。_
