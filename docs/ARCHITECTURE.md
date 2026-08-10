# VN-Agent 架构路线（v3 长期路线，🔒 SHELVED）

> **⚠️ 本文档已归为 SHELVED（保留，不删除）**
> 自 2026-07-08 起，**当前生效的产品北极星见 [docs/v4/PRODUCT_v4.md](./v4/PRODUCT_v4.md)**。
> 本文档的四条长期架构路线（四通道 RAG / 自我进化 Agent / Ren'Py 表现力扩展 / thinking-sync 并行 Writer）**保留但不承诺 timeline**；v4 阶段以工作台形态、素材外源、对话式操作、实时互动生成为主，长期架构在 v4 稳定后视需要重启。
>
> —— 原文档正文完整保留于下：

---

> 稳定区文档（低频更新）。记录未来要走的架构方向 —— 不是已实施的工作，也不是每日 commit 流水。
>
> 从 DEV_LOG.md 切出（2026-04-23）。审计项迁到 [AUDITS.md](./AUDITS.md)，关键决策的"为什么"在 [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md)。每日 commit 流水现在记在 [CHANGELOG.md](./CHANGELOG.md)（由 `scripts/update_docs.py` 自动维护）。相关 P2 backlog 交叉引用 [PRODUCT.md](./PRODUCT.md)。

---

## 未来架构路线 (2026-04-14 收官草案 + 2026-04-23 扩充)

这一节记录下一阶段要走的架构方向。四条路线彼此正交：

1. **路线一**：把 RAG 从"单一文本检索"升级为四通道工业系统
2. **路线二**：把 Agent 从"写完就忘"升级为"自我纠错"
3. **路线三**：把 Ren'Py 表现力吃干榨净 + 多 Agent 架构分层扩容
4. **路线四**：把 Writer 从顺序改成 thinking-sync-并行

---

### 路线一：四通道 RAG 架构 — 解耦代码与文学

当前 RAG 只做对话风格示例注入（literary 模式跳过，action 模式注入 k=2-4）。下一步按业务职能拆成 4 个独立通道，每通道只喂给需要它的 Agent。

**核心思想**：Writer 需要的是"节奏骨架"而非字面句子，SceneArtist 需要的是 ATL transform 代码，Orchestrator 需要的是 `if/menu` 语法；混在一起喂全模型会触发"Lost in the Middle"。解法是 RAG Router：每次生成前做意图分类，按需分发。

#### ETL & Chunking（进入向量库之前的结构化清洗）

1. **代码清洗 + 边界提取** — 剥离引擎初始化，以 `label` / 核心 `menu` 为物理边界切"场景块"，不按 token 硬切
2. **上下文语义切片** — 按对话轮次（20-30 行）切片，头部强制注入 AI 生成的 Context Header，防止碎片化
3. **元数据打标** — 轻量模型（Haiku）给每个切片打 `characters_involved` / `has_choices` / `narrative_tension` 标签，支撑高频精准 metadata filtering

#### 四个通道

| 通道 | 目标 | 数据源 | 处理策略 |
|---|---|---|---|
| A. 叙事风格 | 顶级台词张力、铺垫参考 | 核心对话文本 + 情感高潮 | **防对齐诅咒**：提取"节奏骨架"而非原句喂 Writer |
| B. 逻辑工程 | 复杂分支 + 变量控制语法参考 | `if/elif/menu` 代码段 | 作为硬约束，指导正确 Ren'Py 语法 |
| C. 视觉演出 | 大作级镜头语言 + 特效动画 | `screens.rpy` + ATL `transform` | 给资产/排版 Agent 提供 `vpunch` 等动态演出代码 |
| D. 编译架构 | 内存安全 + 打包无 bug | `options.rpy` + `gui.rpy` + Python 类 | Pipeline 起点提供全局配置模板 + 宏函数规范 |

#### RAG Router 编排

- 前置意图分类器（极低成本模型），每次生成请求做 dispatch
- Writer 只收通道 A，SceneArtist 只收通道 C，Orchestrator 只关注 B + D
- 每个 Agent 的 Context Window 保持绝对纯净，互不干扰

#### 落地顺序（ROI 阶梯）

1. **骨架（ETL + 通道 B）** — 跑通数据清洗脚本 + 逻辑代码检索，确保引擎不报编译语法错
2. **血肉（通道 A）** — 引入脱水"叙事节奏骨架"，提升对话文学质量
3. **皮相 + 底座（通道 C + D）** — 系统稳定后引入高级 ATL 镜头 + 全局架构参考，完成"全栈游戏生成引擎"进化

#### Lore-RAG 子优化：entity scope（always / chapter / scene）

当前 `src/vn_agent/eval/lore.py:60-71` 把 Premise、character、location、world_var 全部放进同一个 FAISS top-k 池。结果：cosine 不利的场景（比如 premise 是"灯塔守夜人"但当前场景写争吵），premise card 会被从 top-k 中踢掉，Writer 失去故事罗盘。

改法：给 `AnnotatedSession`（lore entity）加 `scope` 字段：

| Scope | 包含什么 | 注入方式 |
|---|---|---|
| `always` | Premise、theme、世界设定、主角阵容、`immutability_score=10` 核心属性 | 拼进 system prompt 顶部，包 `cache_control: ephemeral`（5 min TTL，~10× 便宜）。检索失败也不丢 |
| `chapter` | 章节内反复出现的次要角色、当前章节 world_state 演化 | 章节内固定 prefix，跨章重检索 |
| `scene` | 仅本场景的 location、callback hook、world_var detail | 当前 top-k 行为不变 |

**实现要点**：
- `lore.py::extract_lore_entities` 在构造 entity 时按规则打 scope
- `LoreIndex.retrieve` 只对 scope=`scene` 跑 FAISS top-k；scope=`always` 直接返回
- Writer prompt 模板分两段：`{always_lore_block}{retrieved_lore_block}`
- always 段开 prompt caching（Sprint 8-4 已启用，新逻辑只是延伸）

**收益**：
- top-k budget 释放给真正动态的 location / callback，召回质量升
- premise 永驻 context，长篇生成防跑题
- 缓存命中后 always 段近乎零成本

**和四通道 RAG 关系**：scope 字段是通道 A 内部的细分（"骨架级 always" vs "动态 scene 级"），也可以横跨通道 — 通道 D（编译架构）天然全是 always-on 类。

#### 截断逻辑（已迁出）

详见 [AUDITS.md](./AUDITS.md) §1 —— `Lore 截断 + 优先级缺失`。该审计的"scope 优先级 fold"修复方案与上面的 scope 设计共享实现。

---

### 路线二：自我进化 Agent — 经验沉淀与反向传播

当前系统"写完就忘"：失败场景被 Reviewer 打回，修改记录丢失。下一步建三层架构，按 ROI 递增：

#### 第一层：经验库 RAG（Dynamic Few-Shot）— 见招拆招

- **信号捕获**：
  - 负样本 — Reviewer 打分 < 3 且被打回；创作者手改对白；逻辑崩溃生成
  - 正样本 — 一次性通过且未改；玩家高频点赞场景
- **向量化入库** — 专用 `faiss_experience_db`，schema：`{intent, bad_generation, good_generation, reason}`
- **RAG 动态注入** — Writer 下次写"愤怒"场景时系统 Prompt 追加："注意过往错误：[Bad]，学习范例：[Good]"

#### 第二层：元规则反思（Meta-Reflection）— 举一反三

引入 **Reflection Agent**（不参与日常生成，后台异步跑批）：
1. 提取最近 100 次 Reviewer 打回日志
2. 找共性错误 — 例如"Writer 写傲娇角色总像刻薄反派"
3. 输出规则建议 — "处理傲娇属性时，每 3 句带刺话后必加掩饰性肢体动作（别过脸/低头）"
4. 写入 `dynamic_guidelines.json`，Director/Writer 启动时自动拼接到 System Prompt

#### 第三层：自动化 Prompt 优化 + 模型蒸馏 — 基因重组

- **DSPy 式自动优化** — 给 50 个满分场景作 Target，强优化器（GPT-4o/Sonnet）反复改 `physics_diagram` Prompt 逼近 Target，优胜替换旧 Prompt
- **SFT/DPO 微调** — 积累 10K 个极高质量 [Context → Dialogue] 对后，用 DPO（Chosen = 好信号，Rejected = 坏信号）微调 Llama 3 8B / Haiku，廉价模型内生免疫常见错误

#### 周末快速原型（先做 L1 的极简版）

1. 创作者 UI 加 👍 / 👎 按钮
2. 👎 时要求填一句原因（"废话太多"）
3. 脚本存 `[前置上下文, 失败生成, 评语]` 为 JSONL
4. Writer 下次调用前 BM25 扫此 JSONL，相似上下文就把评语强塞 Prompt：**"绝对禁止：废话太多"**

打补丁式进化，小规模能让创作者觉得 AI **"教得会"**。

---

### 收官审计（已迁出）

以下审计已迁到 [AUDITS.md](./AUDITS.md)（2026-04-23 切分）：

- **§2 world_variables 状态记录的缺口**（time-series / branch awareness / constraint persistence）—— Phase 13-1 Step 2 已收 `state_timeline` 一项，其他待修
- **§3 Recursive Summarization 重复 + chapter rollup 缺失** —— Phase 13-1 Step 4 已收 hash-dedup 和 local_regen refire；chapter rollup 已实装

---

### 其他未收的尾巴（之前的 roadmap）

- **Sprint 12-1 流式 pipeline**（player mode JIT delivery）— 重写 `graph.astream` 为 segmented streaming，`pipeline_lookahead=2`，首场景 TTFS 从 5 min 降到 ~60s
- ~~**Sprint 13-1 API key pool**~~ — ✅ Phase 13-1 Step 1 已实装
- **Sprint 13-2/3/4** — job queue + cost caps + fleet dashboard（多用户 ops）
- **真实 BGM 文件** — freesound.org CC0 素材替换占位 OGG
- **CharacterDesigner 额外 emotion**（thoughtful/angry 等独立 PNG）— 已 filesystem-aware，只要生成就自动生效
- **Suno API 音乐生成** — 待 API 公开

---

### 前端 / Web API 同步缺口（Phase 9 之后全部没跟进）

后端 Sprint 9-12 大量 feature 没有在 FastAPI (`src/vn_agent/web/app.py`) 和 React 前端 (`frontend/src/`) 暴露。目前两端停留在 Phase 9 的"生成 + 分步编辑 + 资产管理"三件套。

需要补的 **Web 端点**（~6 个）：

| 端点 | 对应后端能力 | 备注 |
|---|---|---|
| `POST /api/projects/{id}/pause-outline` | Sprint 12-3 `--pause-after outline` | 运行到 state_orchestrator 后中断，dump sidecar |
| `POST /api/projects/{id}/continue-outline` | Sprint 12-3 continue-outline CLI | 读 edited vn_script + sidecar，跑 writer-only graph |
| `POST /api/projects/{id}/regen-scene` | Sprint 12-4 local regen CLI | body: `{scene_id, feedback}`，重写单场景 |
| `GET /api/projects/{id}/unknown-characters` | Sprint 12-5 resolver payload | 读 state 的 `unknown_characters` 列表 |
| `POST /api/projects/{id}/resolve-unknown-character` | creator consent gate | body: `{character_id, action: "auto-fill"\|"open-editor", profile_stub?}` |
| `GET /api/projects/{id}/eval-metrics` | Sprint 8-1/8-2 judge + rule metrics | 读 `scored.json` 返回 per-scene Sonnet/GPT-4o/rule 三元数据 |
| `GET /api/projects/{id}/diagnostics` | Sprint 12-6 | 聚合 trace.json + 各种 warnings 返回单页诊断 |

需要补的 **前端组件**（~5 个）：

| 组件 | 职责 |
|---|---|
| `CreatorPausePanel` | 触发 `--pause-after outline`，显示 Director 的 outline + StructureReviewer issues，允许内联编辑后点击"继续" |
| `RegenSceneButton` | 每个 scene 旁边加重写按钮，弹窗收 `feedback` 字段，触发 regen-scene |
| `UnknownCharacterResolverModal` | 当 reviewer 返回 unknown_characters ≠ []，弹出 modal 展示 profile_stub + 样本对话，让 creator 选 auto-fill / open editor |
| `WorldStatePanel` | 显示并允许编辑 `VNScript.world_variables`（name / type / initial_value / description），pause-after-outline 时尤其重要 |
| `DiagnosticsSidebar` | creator-mode only，聚合显示：per-scene 判分、rule-based signals、persona drift warnings、StructureReviewer issues。可手动触发 eval（花钱） |

前端 `types.ts` **数据模型同步**：
- `CharacterProfile` 补 `immutability_score`、`speech_fingerprint` 字段（Sprint 9/11 schema 增强）
- `Scene` 补 `summary`、`state_reads`、`state_writes`、`narrative_strategy`、`emotional_arc`、`entry_context`、`exit_hook` 字段（Sprint 6/9/11 累加）
- `VNScript` 补 `world_variables` 数组
- 情感词表改为从 `/api/constants/emotions` 拉，不要前端硬编码（对齐 `src/vn_agent/schema/emotions.py` 单源）
- `BranchOption` 补 `requires: Record<string, any>` 字段（Sprint 9 symbolic guard）

前端 **视觉呈现** 需同步：
- `VNPreview.tsx` 预览时 sprite 3:4 + zoom 0.45、BG 1920×1080 的新尺寸；此前可能按旧 1:1 假设布局
- `AssetPanel.tsx` 显示每个 sprite 的 3 个生成版 + 6 个 alias 来源（让 creator 看到 `thoughtful` 当前别名到 `sad`，点"生成真实表情"可触发补图）

实施建议顺序：
1. `types.ts` 先同步（前端其他组件都依赖它）— 纯增量，不破坏现有 UI
2. `unknown-characters` + resolver modal — 小闭环，阻塞最少
3. `regen-scene` 按钮 — 复用已存在的 script panel
4. `pause-outline` + `continue-outline` 成对做 — 是 creator mode 的门面
5. `WorldStatePanel` + `DiagnosticsSidebar` — 大块 UI，最后做

---

### 路线三：Ren'Py 表现力扩展 + Multi-Agent 架构演进 (2026-04-20)

当前管线只处理"剧本 + 立绘 + 背景 + BGM + 分支"这 5 个维度。要把 Ren'Py 支持的能力吃干榨净（Live2D / 多音轨 / minigame / stat 面板 / 时间循环 / 多结局 / i18n / runtime LLM），管线本身需要分层扩容。这一路线和路线一、二正交——它动的是 **schema + graph topology + compiler 模板**，不是检索机制或自我进化机制。

#### 摸底：Ren'Py 到底支持哪些（诚实版）

面试级别的诚实审计：Ren'Py 能力分三档。

| 档位 | 能力 | 依据 |
|---|---|---|
| ✅ 官方 API 直接支持 | Live2D (`renpy.Live2D`)、ATL 动画、多音轨 (`renpy.music.register_channel`)、CDD minigame（DDLC 同款）、`screen` lang 自定义 UI、`translate` 块 i18n、Shift+R live reload、GLSL shader (7.4+)、`python:` 块跑任意 Python | 全部有官方 doc / 经典游戏示例 |
| ⚠️ 技术上能做但要自己搭 harness | auto-playthrough（`config.skipping` + `--warp` + `renpy.screenshot()`，但**没有** `--test` flag）、mod/DLC 热加载（`config.archives.append()` 可行但官方没承诺热插拔）、runtime LLM 调 API（`httpx` 不在自带包里，要打包到 `game/python-packages/`） | 需要自己写胶水，不是开箱即用 |
| ❌ 不建议吹 | 粒子特效（只有 `SnowBlossom` 和 deprecated `Particles`，真要做得嵌 pygame）、真正的"热加载 DLC"（通常要重启）、"Agent-driven 自由叙事沙盒"（超出 VN 范式） |

**设计红线**：不要把"Ren'Py 理论上能跑 Python"等价于"Ren'Py 原生支持 X"。面试官懂 Ren'Py 会追问具体 API。

#### 六个管线改造点（按优先级）

**① Schema 大扩容（最基础，纯 Pydantic 变更）**

现有 `Scene` 字段：`state_reads/state_writes/branches/bgm_mood/description/dialogue`。新增以承载扩展能力：

```python
class Scene(BaseModel):
    # 现有字段...
    cg_moment: bool = False                       # 触发 CG 高保真生成管线
    ambient: AmbientSpec | None = None            # {time, weather, tension_level}
    minigame: MinigameRef | None = None           # 插入 CDD minigame
    scene_effects: SceneEffectPlan | None = None  # on_enter/emphasis_lines/on_exit
    loop_reset_vars: list[str] = []               # 时间循环回滚清单
    locale_hints: dict[str, str] = {}             # i18n TM hint

class VNScript(BaseModel):
    # 现有：scenes, characters, world_variables
    style_bible: StyleBible | None = None         # 项目级皮肤（gui.rpy 参数）
    audio_plan: AudioPlan | None = None           # 多音轨声场
    stat_system: StatSystemSpec | None = None     # 好感度 / 属性系统
    ending_classifiers: list[EndingRule] = []     # true/good/normal/bad 自动分类
    minigame_library: list[MinigameSpec] = []     # 可被 scene 引用的 CDD 定义
```

**关键原则**：新字段全部 `Optional`，旧 pipeline 看不懂就忽略 — 零破坏性升级。

**② 管线图拆成"规划层 / 内容层 / 集成层"三段**

现在是扁平线性（Director → Structure → State → Writer → Reviewer → Assets）。扩展后：
想下要不要抽离一个总设计师出来。主agent决定是否激活可选agent。

```
[规划层] 全串行（schema 层层填充）
  Director
    → StructureReviewer
    → StateOrchestrator
    → StyleDirector          （新）查 StyleBible RAG 产 project_skin + scene_effects
    → InteractivityPlanner   （新）决策 minigame / stat_panel 插入点
    → AudioDirector          （扩）替代 MusicDirector，产多轨 AudioPlan

[内容层] 尽量并行（asyncio.gather return_exceptions=True）
  Writer ⇄ Reviewer（revise 循环保留）
  CharacterDesigner（加 Live2D segment 输出）
  SceneArtist（加 ambient 变体：白天/黄昏/雨）
  MinigameSpecWriter       （新）为每个 slot 生成 Python snippet
  EffectComposer           （新）per-scene transform 编排

[集成层]
  RenpyCompiler（模板参数化）
  LocalizationAgent        （新）translate 块生成
  PlaytestAgent            （新）auto-walk + 截图 + Vision 审查
```

**③ StructureReviewer 升级为"全 schema 完整性守门人"**

现有只 check BFS 可达 + `state_writes` 变量声明。扩展后新增规则：

| 规则 | 检查什么 |
|---|---|
| `loop_reset_vars ⊆ world_variables` | 时间循环只能回滚声明过的变量 |
| `scene.scene_effects.on_enter ∈ transforms 白名单` | 特效名必须在 `transforms.rpy.j2` 已定义 |
| `minigame.id ∈ minigame_library` | 场景引用的 minigame 必须有对应 spec |
| `ending_classifiers 覆盖所有 terminal state` | 所有 branch 终点都能被分类（无 orphan） |
| `stat_system.thresholds` 单调 | 好感度阈值不能乱序 |
| Live2D motion ∈ 角色 motion 库 | 引用的动画必须存在 |

**延续非阻塞哲学**：新 Agent 输出经过这一关，错了写 `structure_feedback`，不直接崩 Ren'Py 编译。

**④ Compiler 从"写死模板"变"参数化皮肤 + 特效白名单"**

现有只俩模板（`script.rpy.j2` + `init.rpy.j2`）。扩展后：

```
compiler/templates/
├── script.rpy.j2        # 扩展：scene_effects / minigame / loop 支持
├── init.rpy.j2          # 扩展：world_vars 注册、stat_system 声明
├── gui.rpy.j2           # 新：StyleBible → 项目皮肤
├── screens.rpy.j2       # 新：say screen + stats panel + gallery
├── transforms.rpy.j2    # 新：特效白名单（shake/fade/vignette/...）
├── audio.rpy.j2         # 新：register_channel + 音景 cue
├── live2d.rpy.j2        # 新：角色 Live2D 声明
└── tl/{locale}/...      # 新：translate 块（LocalizationAgent 产）
```

**关键防线**：`transforms.rpy.j2` 作为白名单——StyleDirector / EffectComposer 只能**组合**不能**发明** transform 名字，避免生成不能编译的 .rpy。等价于 `state_writes` 变量必须在 `world_variables` 声明过的哲学。

**⑤ 加"运行时 Agent 通道"（为 NPC 闲聊 / 自适应分支）**

VN-Agent 当前只是编译期工具。要支持 runtime LLM 需要常驻服务：

```
src/vn_agent/runtime/
├── runtime_api.py       # FastAPI: POST /npc_chat, /suggest_branch
├── game_bridge.py       # Ren'Py 侧 httpx 封装 + 降级逻辑
└── session_cache.py     # 玩家 persona / 对话历史
```

Ren'Py 侧（打包 httpx 到 `game/python-packages/`）：

```python
# init python:
def npc_chat(character_id, player_input):
    try:
        return httpx.post(f"{API}/npc_chat", timeout=3.0).json()["reply"]
    except Exception:
        return fallback_lines[character_id]  # 离线降级
```

**设计原则**：runtime LLM 是**增强**不是核心——服务挂了游戏仍可玩（走预生成 fallback）。这是生产级必须的。

**⑥ Eval 框架扩维度（闭环）**

现有 Reviewer 5 维只评文本。扩展后新增：

| 新维度 | 审核方式 |
|---|---|
| UI coherence | Vision LLM 看 Playtest 截图打分 |
| Interactivity pacing | 确定性规则 + LLM（minigame 频次合理性） |
| Player agency | 跑 state diff 分析（branch 是否有实质影响） |
| Coverage | 确定性：所有 scene/branch ≥1 条 playtest 通路 |

**闭环**：Eval 分数回流 Director 下次 prompt——"上次 interactivity pacing 低，这次少塞 minigame"。

#### 实施顺序（严格按依赖）

| 步 | 工作 | 工期估计 |
|---|---|---|
| 1 | Schema 扩容（Pydantic 字段 + 向后兼容） | 1 周 |
| 2 | StructureReviewer 规则扩展（与 schema 同步） | 几天 |
| 3 | Compiler 模板参数化（拆 gui/screens/transforms） | 1-2 周 |
| 4 | StyleDirector + EffectComposer | 1 周 |
| 5 | PlaytestAgent（Ren'Py warp + screenshot harness） | 2 周 |
| 6 | InteractivityPlanner + MinigameSpecWriter | 1-2 周 |
| 7 | LocalizationAgent | 1 周 |
| 8 | Runtime API 通道（打包 + 降级） | 2 周 |

**前四步 = "把静态 VN 做到生产级"的最小增量**；后四步 = "走向 AI-native VN"的研究性扩展。面试被问"从哪开始"答前四步。

#### 面试口径（什么能吹、什么要保守）

**能吹**：
- Live2D / 多音轨 / minigame CDD / screen lang / i18n / live reload — 全都有官方 API
- StyleDirector + transforms 白名单这套设计哲学（延续 state_writes 声明式约束）
- 运行时 LLM + 降级 fallback 的生产级考量
- PlaytestAgent + Vision Judge 闭环（miHoYo 质量保障口味）
- 策划编辑器 + 局部重跑（Sprint 12-4 已有 foundation，扩到图形化）

**要保守**：
- Runtime LLM 需要打包 httpx 到 `game/python-packages/`，有部署摩擦
- Auto-playthrough 没有 `--test` flag，要自己搭 harness
- Mod/DLC 热加载 Ren'Py 官方没承诺，通常要重启
- 粒子特效 Ren'Py 支持弱，不要和 Unity ParticleSystem 比

**别碰**：
- "Agent-driven 自由互动 VN"（超出 VN 范式，面试被追问会露馅）
- "跨作品 IP 共享 world_lore"（是后端 RAG 工程问题，不是 Ren'Py 问题）

---

### 路线四：Writer 场景级并行 with thinking-sync (2026-04-23 草案)

**现状**：`src/vn_agent/agents/writer.py:147` 是严格顺序 `for idx, scene in enumerate(script.scenes)`。6 场景 × 单场景 ~8s Sonnet ≈ 50s 纯 Writer 时间；50 场景 ≈ 7 分钟。Writer 是单次生成里最慢的节点。

#### 为什么不选"朴素拓扑并行"

直接按 `context_deps` 拓扑排序分 batch、然后 `asyncio.gather` 并写能省墙钟，但并行 worker 之间彼此"瞎写"：
- 两个场景各自埋同一个 callback
- 角色语气微漂移，跨场景 voice 不一致
- 交叉伏笔没有协调，读起来割裂

**朴素并行只解决了"速度"，不解决"协调"**。

#### 采用设计：四阶段 fanout–sync–fanout

```
阶段 0  Director 双层 brief
        → 每场景 scene_brief（细节：人物动线、beats、情绪曲线）
        → 全局 macro_reference（主题、节奏、伏笔布置点）

阶段 1  Writer thinking fanout（并行，Haiku 级）
        每场景 worker 产 scene_thinking（写作意图 + 关键 beats + callback 计划，不是 dialogue）
        墙钟 ~5-10s 收齐全部

阶段 2  依赖图交叉修改
        按 context_deps（Phase 13-1 Step 5）查看所依赖场景的 scene_thinking
        各自更新自己的 thinking（1 轮固定 + 冲突检测，不追不动点）

阶段 3  Writer writing fanout（并行，Sonnet 级）
        thinking 冻结后，每场景并行写 dialogue
        墙钟 ~15-20s（并行度取决于 RPM）

阶段 4  Review（成本驱动选择）
        低成本模式：per-scene Reviewer（快、可 per-scene 回炉，复用 Sprint 12-4 local_regen）
        高质量模式：whole-script Sonnet pass（统一 voice/节奏，50 场 ~30s、~$0.5）
        长篇推荐：两者叠加（per-scene 兜底 + 整本 pass 只在收官跑一次）
```

#### 为什么 thinking 阶段是关键

- **便宜**：Haiku 级，thinking 不是创作
- **互相可见**：让 Writer 们"知道彼此要写什么"——消除"两个 worker 各埋同一 callback"
- **柔化边**：`context_deps` 从硬前置（A 写完 B 才能写）变成柔性协商（A/B 同时 plan，互相修正，最后同时写）

#### 为什么 macro_reference 必须共享

- 50 场景 × 独立 worker 最大风险是 character voice drift 和节奏失衡
- macro_reference 作为所有 worker 共享的 prompt prefix，配合 Phase 13-1 Step 3 的 monolithic 1h cache tier，既统一风格又不增成本（缓存命中率 > 90%）

#### 前置依赖

| 依赖 | 状态 |
|---|---|
| `context_deps` schema | ✅ Phase 13-1 Step 5 |
| `state_timeline` 全量 fold | ✅ Phase 13-1 Step 2 |
| Monolithic prefix + 1h caching | ✅ Phase 13-1 Step 3 |
| Anthropic key pool（RPM 突破）| ✅ Phase 13-1 Step 1 |
| Director schema 扩容：`scene_brief` + `macro_reference` | ⚠️ 新增字段（非破坏） |
| Scene schema 扩容：`scene_thinking` | ⚠️ 新增字段（临时，write 阶段后可留作 debug） |
| Graph topology 三个新 node：`thinking_fanout` / `cross_ref_sync` / `writing_fanout` | ⚠️ 新编排层 |
| per-scene Reviewer pass/fail | ⚠️ 当前全局 pass/fail，需分片 |

#### 成本模型（50 scene 估算）

| 模式 | Director | Thinking | Sync | Writing | Review | 墙钟 | API 成本 |
|---|---|---|---|---|---|---|---|
| 当前顺序 | ~15s | — | — | ~400s | ~60s | **~475s** | ~$0.6 |
| 朴素并行（仅拓扑）| ~15s | — | — | ~30s | ~60s | **~105s** | ~$0.6 |
| 本方案（无整本 review）| ~20s | ~10s | ~15s | ~25s | ~40s | **~110s** | ~$0.8 |
| 本方案（+ 整本 review）| ~20s | ~10s | ~15s | ~25s | ~70s | **~140s** | ~$1.3 |

thinking + sync 比朴素并行贵 ~$0.2 / run，但换来 voice 一致性和交叉协调。长篇（50+ scene）收益最大；短篇（6 scene）可以关闭整本 review。

#### 风险

- **`cross_ref_sync` 不收敛**（A 改了 B 要再改 C，C 改了又影响 A）—— 用 1 轮固定 + 冲突检测，不迭代到不动点
- **thinking ≠ writing 的脱节**（thinking 定了但 writing 实际跑偏）—— Reviewer 兜底
- **Sonnet RPM 成新瓶颈** —— Phase 13-1 Step 1 key pool 已经铺好，实际靠 key 数量扩
- **长篇 literary mode 的 voice 漂移** —— macro_reference 共享 prefix 是主要缓解；Reviewer 整本 pass 是兜底

#### 落地顺序

1. (2 周) Director schema 扩：`scene_brief` + `macro_reference`，产出就绪
2. (1 周) `scene_thinking` schema + `thinking_fanout` node（非并行先跑通，验证 Haiku 写 thinking 质量）
3. (1 周) `cross_ref_sync` 单轮实现 + 冲突日志
4. (1 周) `writing_fanout` 并行 + RPM 监测 + benchmark（6/20/50 scene 墙钟）
5. (几天) whole-script review 可选开关（成本预算开关）+ per-scene reviewer pass/fail 改造
6. (1 周) 修订循环适配：per-failed-scene regen（复用 Sprint 12-4 `local_regen`），不再全局从头跑

#### 面试口径

- 这不是朴素的 "for 循环换 asyncio.gather"——是**多阶段编排 + 交叉协商**，对应 multi-agent 系统里 fanout-sync-fanout 的经典模式（类似 MapReduce shuffle 阶段）
- 前置全部是 Phase 13-1 已收完的能力（`context_deps` / `state_timeline` / prefix caching / key pool），不是研究问题，是编排工程
- 成本折衷 review 策略（per-scene 便宜兜底 + whole-script 贵但统一）体现 "production-grade 成本意识"
- 和路线三的 Multi-Agent 架构演进正交：路线三动的是"规划层加新 Agent"，路线四动的是"Writer 本身怎么并行"
