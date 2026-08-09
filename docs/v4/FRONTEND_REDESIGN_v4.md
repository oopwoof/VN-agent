# VN-Agent Studio 前端改版设计方案（v4 · P6）

> 状态：设计已定稿，待用户 review 后转实施计划
> 日期：2026-08-07
> 归档约定：遵循 `feedback_doc_versioning`，新文档进 `docs/v4/`，不覆盖旧版

---

## 1. Context：为什么要做这次改版

### 1.1 触发点

用户正在准备 AI 产品经理校招，VN-Agent 是核心作品。P0–P5 六阶段功能已全部交付并通过浏览器端到端验证，但用户对当前界面的评价是：**"随处可见的模板"**，缺少能让面试官眼前一亮的交互瞬间。

### 1.2 真正的问题不是配色

第一版提案给出了三个"视觉方向"，用户一句话否掉：**"这三个的区别感觉只是颜色而已，本质上是一样的。"** 这个判断是对的——三个方向共用同一套布局，只换了色板。

重新勘查后，问题的真实定位是**结构层面的两个缺陷**：

**缺陷 A：布局是通用 AI SaaS 模板形状。**
`App.tsx` 是「侧栏 + 左右五五分栏 + 底部状态条」，聊天流在左、面板在右。这是每个 AI 产品的默认形状，与「视觉小说生成器」这个题材没有任何关系。

**缺陷 B（更严重）：项目最值钱的东西在 UI 里完全不可见。**
这个项目的差异化叙事是「多 Agent 协作流水线」。但生成过程中，`PreviewPanel` 只渲染：

```
◌  Writing scene 3…
   Elapsed: 41s
```

一个转圈加一行字。同时后端 `graph.astream()` 正在逐节点吐出真实事件——director → structure_reviewer → state_orchestrator → thinking_fanout → cross_ref_sync → writer → reviewer → asset_generation——**这些信号全部被丢弃**。

更糟的是 `_STEP_LABELS`（`web/app.py:1335`）只映射了 10 个图节点中的 4 个，其余节点直接把内部标识符漏给用户：

```python
label = _STEP_LABELS.get(node_name, f"Running {node_name}")
#  → 用户实际看到 "Running cross_ref_sync"
```

而前端 `PreviewPanel.stepIndex()` 又反过来对这个字符串做子串匹配（`p.includes('setting')`、`p.includes('writer')`…）来猜测五步进度条应该走到第几格。**一条本来结构化的信号，被降级成字符串再被猜回来。**

### 1.3 预期结果

1. 生成过程从「占位状态」升级为**主舞台**：多 Agent 流水线实时可见，成本实时跳动。这既是视觉冲击力，也是简历叙事的直接演示。
2. 生成完成后进入**故事板**：分支结构一眼可见，单场景就地重写（把 P3 Chat Ops 从"打字描述哪一场"变成空间选取）。
3. 界面获得与题材匹配的视觉身份，而不是通用模板。
4. 中文成为一等公民（当前**界面文案 100% 硬编码英文**，见 §5）。
5. **迁移过程中现有功能零回归**——这是硬约束，见 §6。

---

## 2. 方案总览：工作台形态随阶段切换

方向 1（流水线剧场）与方向 3（故事板）不是二选一，而是**同一个工作台在不同阶段的两种形态**。它们各自最强的时刻正好互补，且恰好对应 `store.ts` 里**已经存在**的 `AppStep` 状态机——不需要硬塞两套 UI。

```
输入主题 ──▶ 流水线剧场 ──▶ 故事板 ──▶ 播放器（全幅）
            (生成中)      (可编辑)     (沉浸)

Autopilot ──────────────────────────────▶ （直达播放器，最短路径）
```

| 阶段形态 | 触发的 `AppStep` | 主体内容 |
|---|---|---|
| 流水线剧场 | `generating_setting` / `generating_script` / `compiling` | Agent 流水线实况 + 场景胶片条 + 成本计数 |
| 故事板 | `setting_review` / `script_review` / `asset_management` / `completed` | 场景卡片网格 + 分支箭头 + 就地重写 |
| 播放器 | `vnPreview === true`（任意阶段可进入） | 全幅 VN 播放 |

Autopilot 保留现有的"首场景到达即自动进播放器"行为（`store.ts` 的 `onScene` 分支），确保「一句话 → 可玩」这条最短路径的冲击力不被新 UI 稀释。

---

## 3. 视觉系统

### 3.1 核心思路：用**字体**承载反差，而不是只用颜色

工作台与作品的反差，如果只靠色板区分，就会退化成第一版被否掉的那种「换皮」。真正的做法是让**排版系统本身**编码这个反差：

- **仪器面（工作台）**：紧凑无衬线 + 等宽数字。标签、指标、节点名、成本、耗时——全部走 `font-variant-numeric: tabular-nums`，字号小、字距略开、信息密度高。读起来像仪表盘。
- **叙事面（作品）**：衬线 + 宽松行高。场景标题、角色名、对白——中文用思源宋体/宋体族，英文用衬线族。读起来像出版物。

这两套排版共存于同一屏时，反差自然成立，不依赖配色。

### 3.2 色彩

暗色为底。理由不是审美偏好，而是功能性：**这是一个视觉媒介的创作工具**，生成的插画/背景需要在中性暗背景上才能被正确判断色彩——与 Figma / Premiere / Lightroom 选择暗色底同理。

| Token | 值 | 用途 |
|---|---|---|
| `--ground` | `#0e1012` | 应用底色（近黑，微冷偏移） |
| `--surface` | `#16191c` | 面板 |
| `--surface-raised` | `#1d2125` | 卡片 / 浮层 |
| `--rule` | `#282d32` | 分隔线 |
| `--ink` / `--ink-soft` / `--ink-faint` | `#e6e9ec` / `#9aa3ab` / `#69727a` | 文字三级 |
| `--instrument` | `#c8944a` | **强调色：黄铜/琥珀**——仪表盘联想，明确区别于现有 indigo 与"AI 紫" |
| `--instrument-wash` | `#2a2116` | 强调色底 |

语义色独立于强调色，不参与品牌表达：`--ok #4a9d6e` / `--warn #c9873f` / `--crit #c15550`。

**饱和色只出现在播放器里**——那是生成内容自己的颜色。工作台保持中性 + 单一黄铜强调，把视觉预算集中花在作品上。

### 3.3 动效

只做三处，每一处都编码真实信息，不做装饰性动画：

1. **节点点亮**：流水线节点从暗转亮，边线走一道流光。对应真实的 `node` 事件。
2. **场景卡填充**：骨架屏 → 内容，对应真实的 `scene_ready` 事件。
3. **舞台交接**：流水线剧场 → 播放器的交叉溶解（约 400ms）。

全部尊重 `prefers-reduced-motion`。

---

## 4. 组件设计

### 4.1 后端改动（两处，均为加法）

**（a）新增 `node` 事件类型** — `services/job_events.py`：

```python
def publish_node(node: str, label: str) -> None:
    """Publish a graph-node transition to whichever job is active in this
    async context. Mirrors publish_scene_ready's ContextVar pattern."""
    job_id = current_job_id.get()
    if not job_id:
        return
    publish(job_id, {"event": "node", "node": node, "label": label})
```

在 `web/app.py` 两处 `store.update_status(job_id, "running", progress=label)` 旁各加一行调用（`:1158` 与 `:1397`）。

复用理由：SSE 端点 `stream_scenes` 已经是通用转发器（`yield f"data: {json.dumps(event)}"`），前端 `streamScenes` 对未知 `event` 类型静默忽略——**新事件类型对现有客户端完全无害**，不需要版本协商。

**（b）补全 `_STEP_LABELS`** — 当前只覆盖 4/10 个节点，导致 `Running cross_ref_sync` 这类内部标识符漏给用户。补齐全部 10 个节点的中英文标签。这本身就是一个真实的 UX bug 修复，与改版独立成立。

### 4.2 前端新增组件

| 文件 | 职责 |
|---|---|
| `src/design/tokens.css` | §3.2 的 CSS 自定义属性；Tailwind 类通过 `var()` 引用 |
| `src/i18n/dict.ts` + `useT.ts` | 轻量 i18n（见 §5），不引第三方库 |
| `src/components/PipelineStage.tsx` | 流水线剧场：节点图 + 胶片条 + 成本计数 |
| `src/components/PipelineGraph.tsx` | 手写 SVG 节点图（约 200 行），消费 store 的 `pipelineNodes` |
| `src/components/StoryboardBoard.tsx` | 场景卡片网格 + 分支连线 |
| `src/components/SceneCard.tsx` | 单张场景卡：缩略图 / 标题 / 行数 / 评分徽章 / 重写入口 |
| `src/shell/WorkbenchShell.tsx` | 新外壳，按 `AppStep` 决定渲染哪种形态 |

### 4.3 store 改动（纯加法）

```ts
// 新增 state（不改任何现有字段或 action 签名）
pipelineNodes: Record<string, 'pending' | 'active' | 'done'>
pipelineOrder: string[]
lang: 'zh' | 'en'
```

在 `confirmSetting()` 现有的 `api.streamScenes(...)` handlers 里新增 `onNode` 回调即可——`api.ts` 的 `streamScenes` 增加一个可选 handler，其余调用点零改动。

**关键约束：`api.ts` 的方法签名与返回类型不变**（仅新增可选参数）。这是 §6 稳定性保证的基础。

### 4.4 现有组件的处置

| 组件 | 处置 |
|---|---|
| `VNPreview.tsx` | 保留逻辑，重做排版（叙事面字体）+ 分支选项样式 |
| `ChatPanel.tsx` | 拆分：消息流 / 意图确认卡 / 输入栏三部分，输入栏在流水线形态下变底部命令栏 |
| `ScriptPanel` / `SettingPanel` | 被 `StoryboardBoard` 吸收为卡片详情态 |
| `AssetPanel` / `PlaytestPane` | 保留，接入新 token 与 i18n |
| `PreviewPanel.tsx` | **被 `WorkbenchShell` 取代**——它当前承担的「按 step 决定渲染哪个面板」职责上移到外壳，且改由形态而非 step 直接分支 |
| `ProgressBar` | **删除**——其 `stepIndex()` 字符串猜测逻辑被真实 `node` 事件取代 |
| `StatusBar` / `JobHistory` / `FeedbackWidget` | 保留，接入新 token 与 i18n |

---

## 5. 中文支持（当前完全缺失）

**勘查结论：生成内容（对白、场景标题）走 LLM，中文没问题；但界面文案 100% 硬编码英文**，10 个组件无一例外——`Settings`、`Send`、`Click to continue`、`Fin`、`Back to Editor`、`Retry generation`、`Watch Live`、`Confirm`/`Cancel`、`No jobs yet`、`Enter a theme to start generating` 等。

所以「中文环境的场景和交互」目前**并没有**被覆盖。

方案：**轻量 i18n，不引第三方库**。

```ts
// src/i18n/dict.ts
export const dict = {
  zh: { 'chat.send': '发送', 'vn.continue': '点击继续', 'vn.fin': '完', ... },
  en: { 'chat.send': 'Send',  'vn.continue': 'Click to continue', 'vn.fin': 'Fin', ... },
} as const

// src/i18n/useT.ts — 从 store 读 lang，返回 t(key)
```

- **默认中文**（面试主场景），侧栏提供中/EN 切换。
- 切换即时生效（store 状态驱动，无需刷新），本身就是一个可演示的产品点。
- 中文排版细节：`text-wrap: balance` 对 CJK 标题、行高放宽到 1.7、避免 `letter-spacing` 作用于 CJK 正文。

---

## 6. 稳定性保证：分层迁移，任何一层都可独立回滚

用户明确要求「保证稳定的情况下转移过去」。前端**没有测试框架**（`package.json` 无 vitest/jest），所以稳定性不能靠测试兜底，必须靠**架构隔离 + 可回退开关**。

### 6.1 契约冻结

`api.ts` 的方法签名、返回类型、以及 store 的 **action 签名**全部不变，只做加法（新增可选参数 / 新增 state 字段）。改版是**纯表现层**的。这条守住，回归风险就被限制在渲染层。

### 6.2 六层顺序，每层独立可验证

| 层 | 内容 | 回滚方式 | 风险 |
|---|---|---|---|
| L0 | 后端 `node` 事件 + `_STEP_LABELS` 补全 | 事件无消费者时是 no-op | 极低 |
| L1 | `tokens.css` 引入 | 不删任何现有 Tailwind 类，纯新增变量 | 极低 |
| L2 | i18n 层（默认中文） | `lang` 切回 `en` 即恢复原文案 | 低 |
| L3 | `WorkbenchShell` 新外壳，**旧布局完整保留** | URL 加 `?shell=v1` 走旧壳 | 中 |
| L4 | `PipelineStage` / `StoryboardBoard` 接入 | 组件级降级到旧面板 | 中 |
| L5 | 默认切到新壳；观察期后删旧代码 | 改回默认值 | 低 |

**L3 是关键**：新旧两套外壳并存。切换机制明确为——**URL 参数 `?shell=v1` / `?shell=v2` 优先，读到后写入 localStorage 持久化**，之后刷新无需重复带参数；两者都没有时用代码里的默认值（L3/L4 期间默认 `v1` 旧壳，L5 才翻成 `v2`）。旧壳代码在 L5 之前一行不动，任何时候出问题都能一个 URL 参数退回可用状态——包括面试演示当天。

### 6.3 每层的验证方式

- **L0**：`pytest tests/test_web/ -k "stream or events"` + 新增 `node` 事件的单元测试（沿用现有 `job_events` 测试模式）。
- **L1–L5**：`cd frontend && npm run build`（`tsc -b` 类型检查是当前唯一的自动化护栏，必须每层通过）。
- **端到端**：每层结束后按既有烟测流程走一遍——`VN_AGENT_MOCK=1` 起后端 + `npm run dev`，浏览器点完 P2/P3/P4/P5 四条链路，**零 API 花费**（`feedback_api_approval` 硬约束）。
- **对照**：同一浏览器开两个标签页（`?shell=v1` 与 `?shell=v2`）做并排比对，确认行为一致。

---

## 7. 不做的事（YAGNI）

- **不引入 shadcn/ui 等整套预制组件库**——那正是"模板感"的来源。只引 `lucide-react`（图标）与 `framer-motion`（动效）两个原子库。
- **不做客户端路由**——形态切换由 `AppStep` 驱动，不需要 URL 路由基建（沿用 P5 已确认的取舍）。
- **不做真实 Ren'Py 引擎内嵌播放**——`VNPreview` 的 DOM 播放器足够，且已验证可用。
- **不重构 store 的业务逻辑**——包括已知的 `/compile` 竞态 bug，那是独立议题（已定位根因，见 plan 文件），不与改版耦合。

---

## 8. 遗留：两个已定位未修的 bug

改版**不**捎带修这两个，避免把无关风险卷进 diff：

1. `/compile` 竞态重复调用（`store.ts` 轮询重叠）——已在本 session 写好 `pollInFlight` 互斥修复，**待浏览器实测后单独提交**。
2. 种子背景图 CJK 乱码（`scripts/seed_opensource_library.py`）——已修复并重新生成 8 张图，**待与上一条一起提交**。

---

## 9. 面试可辩护性

| 追问 | 预答 |
|---|---|
| 「改 UI 算产品工作吗？」 | 改的不是皮肤，是**信息架构**——把系统里已经存在但不可见的多 Agent 协作过程暴露给用户。这是"让 AI 的工作过程可解释"这个 AI PM 核心命题的具体落地。 |
| 「流水线可视化是不是花架子？」 | 它消费的是**真实的 LangGraph 节点事件**，不是假动画。而且顺带修掉了一个真实缺陷：原先 10 个节点里 6 个的内部标识符会直接漏给用户看。 |
| 「为什么不直接用组件库？」 | 图标和动效用成熟库（lucide / framer-motion），但拒绝整套预制组件——差异化在信息架构，不在按钮圆角。 |
| 「怎么保证不把能跑的东西改坏？」 | 契约冻结 + 六层迁移 + 新旧外壳并存可一键回退。前端无测试框架是事实，所以用架构隔离而非测试来兜底，并在每层做 mock 模式端到端烟测。 |

---

## 10. 交付顺序

```
L0 后端事件 ──▶ L1 tokens ──▶ L2 i18n ──▶ L3 新外壳（旧壳并存）
                                              │
                                              ▼
                              L4 PipelineStage + StoryboardBoard
                                              │
                                              ▼
                                    L5 默认切换 + 观察期 + 清理
```

每层结束后 `npm run build` 通过 + mock 端到端烟测通过，才进入下一层。
