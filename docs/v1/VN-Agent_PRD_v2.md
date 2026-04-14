# VN-Agent PRD v2.0 — 产品需求文档

> 基于已有 Phase 1-8 后端能力，聚焦 Web 前端交互层与面向小白用户的全流程体验设计。
>
> 最后更新：2026-03-28

---

## 一、产品定位

### 1.1 一句话定位

**让零基础创作者通过对话式交互，将一个故事灵感变成可玩的 Ren'Py 视觉小说。**

### 1.2 核心差异化

| 维度 | AI Dungeon / NovelAI | ChatGPT 直接写 | 手写 Ren'Py | **VN-Agent** |
|------|---------------------|---------------|------------|-------------|
| 输出物 | 实时文本流 | 纯文本 | 可玩项目 | **可玩 Ren'Py 项目** |
| 结构化 | 无 | 无 | 手动 | **自动（JSON 中间格式）** |
| 分支叙事 | 运行时生成 | 需手动组织 | 手动编写 | **LLM 规划 + 用户审批** |
| 用户门槛 | 低 | 低 | 高 | **低（对话式交互）** |
| 可编辑性 | 无 | 复制粘贴 | 完全 | **双模式（Prompt + 直接编辑）** |
| 资产整合 | 无 | 无 | 手动 | **API 链路 + 用户上传** |

### 1.3 目标用户

**主要用户：零基础创作者（P0）**
- 有故事想法但不会编程
- 期望"输入灵感→得到可玩游戏"
- 需要高度引导式交互，每步可视化反馈

**次要用户：独立开发者 / Game Jam 参与者（P1）**
- 用过 Ren'Py，希望加速原型开发
- 需要更多可控性（直接编辑 JSON、自定义模板）
- 可能跳过引导直接进入高级模式

**探索用户：教育工作者（P2）**
- 制作教学用互动故事
- 后续迭代考虑

---

## 二、系统架构

### 2.1 多 Agent 层级架构

采用**混合层级架构（Hierarchical + Blackboard）**，在现有 Agent 基础上升级：

```
┌─────────────────────────────────────────────────┐
│                  用户交互层（Web UI）              │
│          对话面板  |  流程可视化  |  编辑面板       │
└─────────────────┬───────────────────────────────┘
                  │ WebSocket / SSE
┌─────────────────▼───────────────────────────────┐
│              Web API 层（FastAPI）                │
│         任务调度 · 状态管理 · 文件服务              │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│           核心控制层 (Control Layer)              │
│                                                  │
│  ┌──────────────────────────────────────┐        │
│  │     导演 Agent (Director/Manager)     │        │
│  │  - 解析用户 Prompt                     │        │
│  │  - 制定项目计划（世界观·角色·大纲）       │        │
│  │  - 分发任务到执行层                     │        │
│  │  - 阶段性审批检查点                     │        │
│  └──────────────┬───────────────────────┘        │
│                 │                                 │
│  ┌──────────────▼───────────────────────┐        │
│  │       共享黑板 (Blackboard)            │        │
│  │  {                                    │        │
│  │    world_setting: {...},              │        │
│  │    characters: {...},                 │        │
│  │    plot_outline: {...},               │        │
│  │    scene_scripts: [...],             │        │
│  │    asset_manifest: {...},            │        │
│  │    user_feedback: [...]              │        │
│  │  }                                    │        │
│  └──────────────┬───────────────────────┘        │
│                 │                                 │
├─────────────────▼───────────────────────────────┤
│           职能执行层 (Worker Layer)               │
│                                                  │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ │
│  │ 编剧 Agent  │ │ 美术统筹    │ │ 音乐导演     │ │
│  │ (Writer)    │ │ Agent      │ │ Agent        │ │
│  │             │ │            │ │              │ │
│  │ ·大纲展开   │ │ ·提取视觉   │ │ ·情绪-曲目   │ │
│  │ ·对白撰写   │ │  提示词     │ │  匹配        │ │
│  │ ·分支编排   │ │ ·调用生图   │ │ ·曲库/API    │ │
│  │ ·情感标注   │ │  API       │ │  策略        │ │
│  │             │ │ ·角色一致性 │ │              │ │
│  │             │ │  Seed 管理  │ │              │ │
│  └────────────┘ └────────────┘ └──────────────┘ │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │          开发 Agent (Compiler)              │  │
│  │  ·JSON → Ren'Py 脚本编译                    │  │
│  │  ·资产路径映射 · 模板渲染                     │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
├──────────────────────────────────────────────────┤
│           审核层 (Critic Layer)                   │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │         审稿 Agent (Reviewer)               │  │
│  │  ·分支完整性（menu↔label 闭环）              │  │
│  │  ·角色一致性（characters_present 校验）       │  │
│  │  ·场景可达性（start 可达所有 scene）          │  │
│  │  ·叙事策略一致性                             │  │
│  │  ·5 维度评分 Rubric                         │  │
│  │  ·资产清单完整性（新增）                      │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

### 2.2 黑板协作机制

所有 Agent 通过共享黑板（Blackboard）读写状态，而非直接点对点通信。黑板本质上是一个持续更新的结构化 JSON 字典：

```json
{
  "project_id": "uuid",
  "theme": "用户输入的主题",
  "world_setting": {
    "genre": "科幻",
    "era": "近未来",
    "tone": "悬疑",
    "key_rules": ["时间旅行有代价", "..."]
  },
  "characters": {
    "char_001": {
      "name": "林夏",
      "role": "protagonist",
      "personality": "...",
      "visual_profile": {
        "hair": "黑色短发",
        "outfit": "白色实验服",
        "features": "左眼下有泪痣",
        "art_style_prompt": "anime style, ..."
      },
      "emotions": ["neutral", "happy", "sad", "angry", "surprised"]
    }
  },
  "plot_outline": {
    "act_structure": "三幕式",
    "scenes": [...],
    "branch_points": [...],
    "endings": [...]
  },
  "scene_scripts": [...],
  "asset_manifest": {
    "character_sprites": {...},
    "backgrounds": {...},
    "bgm": {...},
    "sfx": {...}
  },
  "user_feedback": [],
  "generation_config": {
    "llm_model": "claude-sonnet-4-6",
    "budget_preset": "standard"
  }
}
```

### 2.3 Agent 协作流程

```
Director 解析主题
    ↓ 写入黑板: world_setting + characters + plot_outline
    ↓ [用户确认检查点 ①]
Writer 读取黑板 → 生成 scene_scripts
    ↓ 写入黑板: scene_scripts
Reviewer 读取黑板 → 审核
    ↓ PASS → 继续 / FAIL → 携带反馈打回 Writer（最多 3 次）
    ↓ [用户确认检查点 ②]
美术统筹 从黑板提取 visual_profile + background_requirement → 生成/映射资产
音乐导演 从黑板提取 scene mood → 匹配/生成 BGM
    ↓ 写入黑板: asset_manifest
    ↓ [用户确认检查点 ③]
Compiler 读取完整黑板 → 编译 Ren'Py 项目
    ↓ [最终预览 + 下载]
```

### 2.4 技术栈

| 层 | 技术选型 | 理由 |
|---|---------|------|
| 前端 | React + TypeScript + Tailwind | 组件生态丰富，适合复杂交互面板（编辑器、流程可视化） |
| 状态管理 | Zustand | 轻量，适合中等复杂度应用 |
| 实时通信 | SSE（已有） + WebSocket（后续） | SSE 已在 Phase 8 实现，MVP 复用 |
| 后端 API | FastAPI（已有） | 复用现有 Web API 层 |
| Agent 编排 | LangGraph（已有） | 复用现有 Agent 框架 |
| 持久化 | SQLite（已有） | JobStore 已实现 |
| LLM | Claude Sonnet 4.6（主力）/ Haiku（辅助）/ 本地 Qwen 2.5 7B（Fallback） | 成本分级策略 |
| 部署 | 本地优先 → Docker → 云端 | 渐进式 |

---

## 三、核心用户流程（Web UI）

### 3.1 全流程概览

```
[输入主题] → [设定确认] → [脚本生成] → [脚本审阅] → [资产生成/上传] → [预览编译] → [下载]
                ↑              ↑              ↑              ↑              ↑
           可编辑/重生成     可编辑/重生成    可编辑/重生成    可上传替换     可全局修改
```

### 3.2 界面布局

采用**左右分栏**布局：

```
┌─────────────────────────────────────────────────────────┐
│  VN-Agent                               [设置] [帮助]    │
├──────────────────────┬──────────────────────────────────┤
│                      │                                   │
│    对话交互面板        │         成果展示/编辑面板           │
│    (Chat Panel)      │         (Preview Panel)           │
│                      │                                   │
│  ┌────────────────┐  │  ┌─────────────────────────────┐  │
│  │ 系统: 欢迎！     │  │  │  📋 流程进度条                │  │
│  │ 请输入你的VN    │  │  │  ● 设定 → ○ 脚本 → ○ 资产   │  │
│  │ 故事灵感...     │  │  │    → ○ 编译                  │  │
│  │                │  │  ├─────────────────────────────┤  │
│  │ 用户: 一个在    │  │  │                              │  │
│  │ 赛博朋克世界里  │  │  │  [当前阶段的可编辑内容]        │  │
│  │ 寻找记忆的故事  │  │  │                              │  │
│  │                │  │  │  世界观设定 ✏️                │  │
│  │ 系统: 已生成    │  │  │  角色卡片 ✏️                 │  │
│  │ 世界观设定...   │  │  │  剧情大纲树 ✏️               │  │
│  │                │  │  │  ...                         │  │
│  ├────────────────┤  │  │                              │  │
│  │ [输入框]  [发送]│  │  │  [✅ 确认并继续] [🔄 重新生成]│  │
│  └────────────────┘  │  └─────────────────────────────┘  │
│                      │                                   │
├──────────────────────┴──────────────────────────────────┤
│  💰 预估成本: $0.05  |  📊 Token: 3,200  |  ⏱ 耗时: 12s  │
└─────────────────────────────────────────────────────────┘
```

### 3.3 分步交互设计

#### Step 0：项目初始化

**用户操作**：输入故事主题（一句话或一段描述）

**可选配置**（折叠面板，有合理默认值）：
- 语言：中文（默认） / English
- 脚本规模：短篇 ~5min / 标准 ~10min（默认） / 长篇 ~20min
- 成本预设：经济（全 Haiku，~¥0.1）/ 标准（Sonnet+Haiku，~¥0.7）/ 高质量（全 Sonnet，~¥2）
- 确认模式：逐步确认（默认） / 快速生成（跳过中间确认，一键到底）

**系统行为**：Director Agent 开始解析主题

#### Step 1：设定确认（用户检查点 ①）

**展示内容**（右侧面板）：

**A. 世界观设定卡片**
```
🌍 世界观
━━━━━━━━━━━━━━━━━
类型：赛博朋克 / 悬疑          [✏️ 编辑]
时代：2087年，新东京
基调：忧郁但温暖
核心设定：
  · 记忆可以被数字化交易
  · 主角失去了过去3年的记忆
  · 地下记忆黑市正在扩张
```

**B. 角色卡片（可展开/折叠）**
```
👤 林夏（主角）                 [✏️ 编辑] [🗑️ 删除]
━━━━━━━━━━━━━━━━━
性格：沉默寡言，内心细腻
背景：前记忆工程师，因事故失忆
外貌：黑色短发，左眼下有泪痣，白色旧外套
关系：与"零"是前同事

👤 零（关键角色）               [✏️ 编辑] [🗑️ 删除]
━━━━━━━━━━━━━━━━━
...

[+ 添加角色]
```

**C. 剧情大纲（树状可视化）**
```
📖 剧情结构
━━━━━━━━━━━━━━━━━

开幕 → 发现线索 → 潜入黑市 → [选择分支]
                                 ├→ 信任零 → 真相结局
                                 └→ 独自行动 → 遗忘结局

预计场景数：8        分支点：1        结局数：2
```

**用户操作选项**：
- ✏️ 直接点击编辑任何字段
- 💬 在左侧对话框用自然语言修改："把主角改成女性"、"增加一个反派角色"
- 📎 上传参考文件（角色设定文档、世界观文档等）
- ✅ **确认并进入脚本生成**
- 🔄 **重新生成设定**（可附加修改意见）

#### Step 2：脚本生成 + 审阅（用户检查点 ②）

**生成过程展示**：
- 左侧对话面板实时流式输出 Writer 的创作过程
- 右侧面板实时更新场景列表，显示进度

**生成完成后右侧面板**：

```
📝 剧本预览
━━━━━━━━━━━━━━━━━

[场景导航栏]
 S1:开幕 | S2:线索 | S3:黑市 | S4a:信任 | S4b:独行 | ...

━━━━━━━━━━━━━━━━━
场景 1：记忆的碎片                    [✏️ 编辑场景]
背景：赛博朋克街道·夜晚
出场角色：林夏

  旁白：霓虹灯在潮湿的路面上投下破碎的倒影。
  林夏：（独白）又是这个梦...三年前的事，我什么都想不起来。
  林夏：（看向手中的芯片）只有这个，是唯一的线索。

  [→ 进入场景 2]
━━━━━━━━━━━━━━━━━
场景 2：旧友重逢                      [✏️ 编辑场景]
...

━━━━━━━━━━━━━━━━━
Reviewer 评审结果：
  ✅ 分支完整性：通过
  ✅ 角色一致性：通过
  ✅ 场景可达性：通过
  ⚠️ 叙事策略：场景3→4 转折略突兀（建议）
  评分：4.2 / 5.0

[✅ 确认脚本] [✏️ 整体修改意见] [🔄 重新生成] [📥 导出 JSON]
```

**编辑模式**：点击 ✏️ 后进入该场景的文本编辑器，支持：
- 直接修改对白文本
- 修改角色情绪标签
- 调整场景顺序（拖拽）
- 在对话框中提 Prompt 级修改意见（如："让场景3的对话更紧张一些"）

#### Step 3：资产生成/上传（用户检查点 ③）

**右侧面板：资产管理面板**

```
🎨 艺术资产
━━━━━━━━━━━━━━━━━

角色立绘
  林夏                            [上传替换] [🔄 重新生成]
    [placeholder_linxia.png]
    neutral | happy | sad | angry | surprised

  零                              [上传替换] [🔄 重新生成]
    [placeholder_zero.png]
    neutral | happy | sad

场景背景
  S1: 赛博朋克街道·夜晚           [上传替换] [🔄 重新生成]
    [placeholder_bg_street.png]
  S2: 旧公寓·室内                 [上传替换] [🔄 重新生成]
    [placeholder_bg_apartment.png]
  ...

🎵 音乐 & 音效
  BGM-1: 忧郁氛围 (S1, S2)       [上传替换] [🔄]
    [placeholder.ogg] ▶️ 试听
  BGM-2: 紧张悬疑 (S3)           [上传替换] [🔄]
    [placeholder.ogg] ▶️ 试听
  ...

[✅ 确认资产] [📎 批量上传]
```

**MVP 资产策略**：
- **立绘**：预置一组通用 anime 风格 placeholder PNG（按角色性别/发色分类）
- **背景**：预置 10-15 张通用场景图（街道/室内/学校/森林等）
- **BGM**：复用现有 16 曲目曲库（已按 8 种情绪分类）
- **API 链路**：代码中完整保留 DALL-E 3 / Stability AI 调用逻辑，通过配置开关控制是否实际调用

**用户上传规范**：
- 立绘：PNG，建议 600×900px，透明背景
- 背景：PNG/JPG，建议 1920×1080px
- BGM/音效：OGG 格式（Ren'Py 原生支持）

#### Step 4：最终预览 + 编译下载

**右侧面板：全局预览**

```
🎮 项目预览
━━━━━━━━━━━━━━━━━

[简易 VN 播放器预览窗口]
  ┌─────────────────────────────┐
  │  [背景图]                    │
  │                              │
  │      [角色立绘]              │
  │                              │
  │  ┌──────────────────────┐   │
  │  │ 林夏：又是这个梦...    │   │
  │  └──────────────────────┘   │
  │           [▶ 下一句]        │
  └─────────────────────────────┘

项目统计：
  场景数：8    角色数：3    分支点：1    结局数：2
  对话总量：约 6,500 字    预计游玩时长：~10 分钟
  消耗 Token：16,700    估算成本：$0.10

[🔄 返回修改] [📦 编译并下载 Ren'Py 项目] [📥 导出 JSON]
```

**编译产物**：
- 完整的 Ren'Py 项目目录（.zip）
- 包含：script.rpy, characters.rpy, gui.rpy, init.rpy, images/, audio/
- 用户解压后可直接用 Ren'Py SDK 运行

---

## 四、脚本生成规格

### 4.1 规模定义

| 模式 | 场景数 | 对话行数 | 字数范围 | 游玩时长 | 分支 | 结局 |
|------|--------|---------|---------|---------|------|------|
| 短篇 | 4-6 | 40-60 | ~3,000字 | ~5min | 1 | 2 |
| **标准（默认）** | **8-12** | **80-120** | **5,000-8,000字** | **~10min** | **1-2** | **2** |
| 长篇 | 15-20 | 150-200 | ~12,000字 | ~20min | 2-3 | 3 |

> MVP 阶段仅实现**标准**模式。

### 4.2 分支结构规范

**MVP 必须满足**：
- 至少 1 个分支选择点
- 分支导向 2 个不同结局
- 每个结局有独立的终幕场景

**分支点设计原则**（由 Director Agent 规划，用户可修改）：
- 分支点默认位于剧情 60-70% 处（三幕结构的第二幕末尾）
- 选项数量：2-3 个（MVP 固定 2 个）
- 分支后的路线独立发展，不汇合（MVP 简化设计）
- 每条分支路线至少包含 2 个场景

**分支结构 JSON 示例**：
```json
{
  "branch_point": {
    "scene_id": "scene_05",
    "position": "end",
    "choices": [
      {
        "text": "选择信任零",
        "leads_to": "scene_06a",
        "ending_type": "true_ending"
      },
      {
        "text": "决定独自行动",
        "leads_to": "scene_06b",
        "ending_type": "bad_ending"
      }
    ]
  }
}
```

### 4.3 脚本质量保障

**Reviewer 5 维度评分 Rubric**（已实现）：

| 维度 | 权重 | 评分标准 |
|------|------|---------|
| 叙事连贯性 | 25% | 场景之间逻辑通顺，无跳跃 |
| 角色一致性 | 25% | 性格/语气前后统一 |
| 分支合理性 | 20% | 选项有意义，结局与选择因果相关 |
| 对话质量 | 15% | 自然、有个性、推动情节 |
| 策略一致性 | 15% | 与选定叙事策略匹配 |

**质量兜底机制**：
1. Writer 输出 → Schema 验证（结构合法性）
2. Schema 不通过 → LLM Repair（自动修复一次）
3. Reviewer 结构检查（分支闭环、角色声明、场景可达）
4. Reviewer LLM 质检（5 维度评分，< 3.0 打回修订）
5. 最多 3 轮修订，超过强制接受 + 标记警告

### 4.4 长文本策略

标准模式（8-12 场景，5000-8000 字）的完整项目数据在多个环节面临 LLM 上下文长度压力。以下按截断风险从高到低列出各环节的问题与对策。

#### 4.4.1 风险全景

```
环节               输入规模（估算）         截断风险   现有防御
─────────────────────────────────────────────────────────────
Director step1     主题 prompt (~500 tok)   低        —
Director step2     outline → details        中        两步走已实现
Writer (per scene) 黑板摘要 + 单场景指令     低        按场景逐个生成 ✅
Reviewer           完整脚本 (8-12 场景)     ⚠️ 高     结构检查已实现
用户 Prompt 编辑   对话历史 + 黑板 + 指令    ⚠️ 高     无
前端展示           完整黑板 JSON             中        无
```

核心矛盾：**Writer 已经按场景拆分，不会截断；但 Reviewer 和用户 Prompt 编辑需要读全局状态，随场景数增长会触顶。**

#### 4.4.2 各环节对策

**A. Writer（已解决 ✅）**

按场景逐个调用 LLM，每次 prompt 包含：
- 系统 prompt + 叙事策略指令（固定，~800 tokens）
- 黑板摘要：世界观 + 角色卡片 + 大纲（压缩版，~1,000 tokens）
- 前序场景摘要而非全文（~200 tokens/场景，递增但可控）
- 当前场景指令（~300 tokens）

单次调用上限估算：~3,000-4,000 input tokens，远低于 Sonnet 200K 窗口。

**关键设计**：Writer 生成第 N 个场景时，不传入前 N-1 个场景的完整对白，而是传入每个前序场景的**摘要**（由 Director 预生成或从黑板提取），格式如：

```json
{
  "previous_scenes_summary": [
    {"scene_id": "s01", "summary": "林夏在街头发现记忆芯片，决定追查真相", "ending_emotion": "determined"},
    {"scene_id": "s02", "summary": "在旧公寓遇见零，得知记忆黑市的存在", "ending_emotion": "shocked"}
  ],
  "current_scene": {
    "scene_id": "s03",
    "outline": "潜入记忆黑市，发现自己的记忆正在被拍卖",
    "characters_present": ["林夏", "黑市商人"],
    "target_emotion": "tense",
    "narrative_strategy": "Uncover"
  }
}
```

**B. Reviewer（需要升级 ⚠️）**

问题：Reviewer 需要读完整脚本做全局检查（分支闭环、场景可达性、角色一致性）。8-12 个场景的完整 JSON 可能达到 8,000-15,000 tokens input。

**分层审核策略**：

```
第一层：结构检查（纯代码，零 LLM 调用，零截断风险）
  ├── 分支闭环：遍历 JSON 校验 menu choice → label 映射
  ├── 场景可达性：从 start BFS/DFS 遍历 scene graph
  ├── 角色声明完整性：对比 characters_present vs 实际对话
  └── 资产清单完整性：对比 scene background/character 引用 vs asset_manifest

第二层：局部质检（LLM，按场景分段，不截断）
  ├── 逐场景评估对话质量和角色一致性
  ├── 每次调用只传入：角色卡片 + 当前场景 + 相邻场景摘要
  └── 输出：每场景独立评分

第三层：全局连贯性评估（LLM，压缩输入）
  ├── 输入：全场景摘要列表（非全文）+ 分支结构图 + 各场景评分
  ├── 仅评估叙事连贯性和分支合理性
  └── 预估 input: ~2,000-3,000 tokens（可控）
```

**配置化控制**：
```yaml
reviewer:
  structural_check: true          # 第一层，始终开启（零成本）
  per_scene_quality: true         # 第二层，standard 以上开启
  global_coherence: true          # 第三层，quality 预设开启
  skip_llm: false                 # 全部跳过 LLM（仅第一层），budget 预设用
```

**C. 用户 Prompt 编辑（需要设计 ⚠️）**

问题：用户在 Step 2 说"让场景 3 的对话更紧张"，后端需要理解上下文才能执行。多轮编辑后，对话历史 + 黑板状态会膨胀。

**滑动窗口 + 摘要策略**：

```
Prompt 编辑的 LLM 上下文构成：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[固定] 系统 prompt                              ~500 tokens
[固定] 黑板核心摘要（世界观 + 角色卡片）           ~800 tokens
[动态] 编辑目标上下文（目标场景全文 + 相邻摘要）   ~1,500 tokens
[滑动] 最近 5 轮对话历史                         ~1,000 tokens
[新增] 用户当前指令                              ~100 tokens
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总计                                            ~4,000 tokens ✅
```

**实现要点**：
- 对话历史超过 5 轮时，早期对话压缩为摘要（"用户修改了角色名从A到B，调整了场景2情绪"）
- 黑板不传全量 JSON，而是根据用户指令动态提取相关子集
- 如果用户指令涉及全局修改（如"整体语气改轻松"），则传入全场景摘要列表而非全文

**D. Director 大纲生成（已解决 ✅）**

两步走策略已实现：
- Step 1：主题 → 粗粒度大纲（世界观 + 角色 + 场景列表）
- Step 2：大纲 → 每个场景的详细指令（分支目标、情绪弧线等）

每步 input 控制在 ~2,000-3,000 tokens。

**E. 前端黑板传输（工程问题）**

问题：完整黑板 JSON（含所有场景全文）可能达到 50-100KB，前端渲染和 API 传输需要优化。

对策：
- API 支持字段过滤：`GET /api/projects/{id}?fields=setting,outline`（不返回全量 scene_scripts）
- 场景内容按需加载：`GET /api/projects/{id}/script/{scene_id}`
- 前端按 Tab 懒加载（设定 Tab 不预加载脚本内容）

#### 4.4.3 Token 预算估算（标准模式 10 场景）

```
环节                         调用次数    avg input    avg output    总 tokens
──────────────────────────────────────────────────────────────────────────────
Director step1               1          800          1,500         2,300
Director step2               1          2,000        2,000         4,000
Writer (per scene × 10)      10         3,000        800           38,000
Reviewer 结构检查             0 (代码)   —            —             0
Reviewer 逐场景质检           10         2,000        300           23,000
Reviewer 全局连贯性           1          2,500        500           3,000
──────────────────────────────────────────────────────────────────────────────
合计                         23 calls                              ~70,000 tokens
Sonnet 预估成本              ~$0.07-0.12
```

> 注：用户 Prompt 编辑的 token 消耗取决于编辑次数，不计入基础预算。每次 Prompt 编辑约 ~4,000 tokens。

#### 4.4.4 降级策略

当检测到上下文接近模型限制时（如使用本地 Qwen 2.5 7B，上下文仅 32K）：

| 触发条件 | 降级措施 |
|---------|---------|
| 场景数 > 8 且使用本地模型 | 自动切换到短篇模式（6 场景） |
| 单次 prompt > 模型上下文 80% | 进一步压缩前序摘要（仅保留最近 3 场景） |
| Reviewer input 超限 | 跳过第三层全局连贯性评估，仅做结构+逐场景 |
| 对话历史 > 10 轮 | 强制摘要化早期历史 |
| 黑板 JSON > 200KB | 告警 + 建议用户拆分为多个短篇项目 |

### 4.5 API 限速策略

#### 4.5.1 当前限额（Anthropic Tier 1 × 2 账号）

单账号限额：

```
模型              RPM     Input TPM (不含缓存)    Output TPM
─────────────────────────────────────────────────────────────
Claude Sonnet     50      30,000                  8,000
Claude Haiku      50      50,000                  10,000
```

**双账号 Key Pool 后等效限额**：

```
模型              RPM     Input TPM               Output TPM
─────────────────────────────────────────────────────────────
Claude Sonnet     100     60,000                  16,000
Claude Haiku      100     100,000                 20,000
```

#### 4.5.2 瓶颈分析

以标准模式（10 场景）为例，将 §4.4.3 的 Token 预算按模型拆分：

```
Sonnet 调用（Director + Writer）
──────────────────────────────────────────────────
  Director step1     1 call    800 input     1,500 output
  Director step2     1 call    2,000 input   2,000 output
  Writer × 10        10 calls  3,000 input   800 output (each)
──────────────────────────────────────────────────
  合计               12 calls  32,800 input  11,500 output

  vs 单账号限额:     RPM ✅     TPM ⚠️ 超限!   TPM ⚠️ 超限!
  vs 双账号限额:     RPM ✅     TPM ✅ 54%用量   TPM ✅ 72%用量

Haiku 调用（Reviewer 逐场景 + 全局）
──────────────────────────────────────────────────
  逐场景质检 × 10    10 calls  2,000 input   300 output (each)
  全局连贯性         1 call    2,500 input   500 output
──────────────────────────────────────────────────
  合计               11 calls  22,500 input  3,500 output

  vs 单账号限额:     RPM ✅    TPM ✅         TPM ✅
  vs 双账号限额:     RPM ✅    TPM ✅ 22%     TPM ✅ 18%
```

**结论**：双账号 Key Pool 将 Sonnet input TPM 从超限（32.8K/30K = 109%）降至安全区间（32.8K/60K = 54%）。即使不做任何额外限速措施，全部 Sonnet 调用也可以在 1 分钟内自然完成。

#### 4.5.3 核心方案：双 Key 轮询池（KeyPool）

**方案概述**：后端维护 2 个 Anthropic API Key，每次 LLM 调用按 round-robin 分配 Key，使两个账号的限额均匀消耗。

**实现设计**：

```python
class KeyPool:
    """
    管理多个 API Key，按轮询分配调用，均摊限额。
    """

    def __init__(self, keys: list[str]):
        self.keys = keys
        self._index = 0
        self._lock = asyncio.Lock()
        # 每个 key 独立的用量追踪
        self.usage = {key: {"calls": 0, "input_tokens": 0, "output_tokens": 0} for key in keys}

    async def acquire(self) -> str:
        """获取下一个可用 Key（round-robin）。"""
        async with self._lock:
            key = self.keys[self._index % len(self.keys)]
            self._index += 1
            return key

    async def acquire_smart(self, model: str, estimated_input: int) -> str:
        """智能分配：优先选择近 1 分钟内 TPM 消耗更低的 Key。"""
        async with self._lock:
            # 选择滑动窗口内 input_tpm 用量最低的 key
            best_key = min(self.keys, key=lambda k: self._recent_input_tpm(k, model))
            return best_key

    def record(self, key: str, input_tokens: int, output_tokens: int):
        """记录实际消耗。"""
        self.usage[key]["calls"] += 1
        self.usage[key]["input_tokens"] += input_tokens
        self.usage[key]["output_tokens"] += output_tokens
```

**与现有代码的集成**：

后端已有 `llm_api_key` 配置字段。改造路径：

```
现有:  config.llm_api_key → 单个 key → 直接传给 LLM client
改造:  config.llm_api_keys → list[str] → KeyPool → 每次调用分配一个 key

# 向后兼容：如果配置中只有一个 key，KeyPool 退化为直通
```

**分配策略选择**：

| 策略 | 实现复杂度 | 适用场景 |
|------|-----------|---------|
| **Round-Robin（推荐 MVP）** | 低 | 2 个 Key，均匀分配即可 |
| Smart（最低用量优先） | 中 | 3+ Key，或 Key 层级不同 |
| Sticky（按模型绑定） | 低 | Key A 专跑 Sonnet，Key B 专跑 Haiku |

**MVP 推荐 Round-Robin**：12 次 Sonnet 调用，Key A 拿 6 次（~16.4K input），Key B 拿 6 次（~16.4K input），各自远低于单账号 30K 限额。

#### 4.5.4 实际生成节奏模拟（双 Key）

```
时间线 (秒)    调用                        Key    累计 Input TPM
                                                  Key-A    Key-B
────────────────────────────────────────────────────────────────
0s    ├─ Director step1 (Sonnet)          A      800      0
3s    ├─ Director step2 (Sonnet)          B      800      2,000
8s    ├─ Writer scene 1 (Sonnet)          A      3,800    2,000
14s   ├─ Writer scene 2 (Sonnet)          B      3,800    5,000
20s   ├─ Writer scene 3 (Sonnet)          A      6,800    5,000
26s   ├─ Writer scene 4 (Sonnet)          B      6,800    8,000
32s   ├─ Writer scene 5 (Sonnet)          A      9,800    8,000
38s   ├─ Writer scene 6 (Sonnet)          B      9,800    11,000
44s   ├─ Writer scene 7 (Sonnet)          A      12,800   11,000
50s   ├─ Writer scene 8 (Sonnet)          B      12,800   14,000
56s   ├─ Writer scene 9 (Sonnet)          A      15,800   14,000
62s   ├─ Writer scene 10 (Sonnet)         B      15,800   17,000
      │                                          53%用量  57%用量
      │                                          ✅ 无等待 ✅ 无等待
      │
      │  ── 切换到 Haiku（限额更宽松，可并行）──
65s   ├─ Reviewer scene 1-5 (Haiku)       A/B 交替，并行 5 calls
70s   ├─ Reviewer scene 6-10 (Haiku)      A/B 交替，并行 5 calls
74s   ├─ Reviewer 全局 (Haiku)            A      1 call
      │
77s   └─ ✅ 全部完成

预估总耗时: ~77 秒（无任何限速等待）
```

**对比单账号方案**：
- 单账号：~85 秒（场景 9→10 需等待 ~9 秒窗口滑过）
- **双账号：~77 秒（零等待）** ← 节省 ~10%，且完全消除 429 风险

#### 4.5.5 辅助策略：Prompt Caching（锦上添花）

双 Key 已经解决了限额问题，Prompt Caching 进一步降低成本和提升速度：

Anthropic Prompt Caching 允许缓存重复的 prompt 前缀，缓存命中的 tokens 不计入 input TPM 限额，且读取缓存的费用仅为正常 input 的 10%。

**可缓存的内容**（Writer 10 次调用间重复的部分）：

```
  ├── 系统 prompt (~800 tokens)         → 缓存 ✅
  ├── 世界观设定 (~300 tokens)           → 缓存 ✅
  ├── 角色卡片 (~400 tokens)             → 缓存 ✅
  ├── 叙事策略指令 (~300 tokens)         → 缓存 ✅
  └── 合计可缓存: ~1,800 tokens/call

效果：
  有效 input TPM: 32,800 → ~16,600（节省 ~50%）
  有效 Key 用量:  每 Key ~8,300 input TPM（仅 28%）
  成本节省:       缓存部分按 10% 计费，单次生成省 ~30%
```

**实现方式**：在系统 prompt 和世界观/角色卡片部分标记 `cache_control: {"type": "ephemeral"}`。

**注意**：Prompt Caching 是 per-key 的，同一个 Key 的连续调用才能命中缓存。因此 Writer 的 10 次调用如果严格 round-robin（A-B-A-B），每次都换 Key，缓存命中率会下降。

**优化**：Writer 阶段改为 Sticky 分配（连续用同一个 Key），Reviewer 阶段再切换。

```
Writer 阶段: Key A → scene 1,2,3,4,5 | Key B → scene 6,7,8,9,10
  Key A: 5 × 3,000 = 15,000 input（50% 限额）✅
  Key B: 5 × 3,000 = 15,000 input（50% 限额）✅
  缓存命中: 每 Key 连续调用 5 次，后 4 次均命中，节省 4 × 1,800 × 2 = 14,400 tokens
```

#### 4.5.6 429 重试策略（兜底）

在 KeyPool + Prompt Caching 的预防措施下，429 极少出现。但仍需兜底：

```
收到 429 Too Many Requests
  ├── 读取 retry-after header（如有）
  │     └── sleep(retry_after_seconds)
  ├── 无 header → 指数退避
  │     └── sleep(2^attempt * 1.0 + jitter)，最大 60s
  ├── 尝试切换到 KeyPool 中另一个 Key 重试（限额独立）
  ├── 最多重试 3 次
  └── 3 次后 → 标记为 rate_limit_exhausted
              ├── 非关键调用（Reviewer LLM 质检）→ 跳过，仅保留结构检查
              └── 关键调用（Writer）→ 报错，提示用户等待后重试
```

**Key 切换重试**是双账号方案独有的优势：一个 Key 被限流时，立即切到另一个 Key，大概率可以继续，无需等待。

#### 4.5.7 前端用户体验

限速等待不应该是无声的——前端需要感知并告知用户：

```
后端 SSE 推送限速事件：
  {"event": "rate_limit_wait", "data": {"wait_seconds": 9, "reason": "API rate limit, switching key..."}}

前端展示（仅在确实需要等待时显示）：
  ┌──────────────────────────────────┐
  │  ⏳ API 限额调整中，稍候... (9s)   │
  │  ████████░░░░░░░░                │
  │  提示：可在设置中添加更多 API Key   │
  └──────────────────────────────────┘
```

#### 4.5.8 多用户场景（云端部署，后续迭代）

MVP 单用户 + 双 Key 已充分满足需求。云端部署后的扩展方案：

| 策略 | 实现方式 | 适用场景 |
|------|---------|---------|
| 用户自带 API Key | 前端设置页输入 key，后端透传，限额完全隔离 | 高级用户 |
| 平台 Key Pool 扩展 | 从 2 Key 扩展到 N Key，round-robin | 平台运营 |
| 任务队列 | Redis/SQLite 队列 + worker pool | 高并发削峰 |
| Batch API | Anthropic Batch endpoint（独立限额） | 后台预生成 |

**用户自带 Key 的实现**（后续迭代）：
```
前端设置页：
  ┌─────────────────────────────────────┐
  │  ⚙️ API 设置                        │
  │                                     │
  │  模式：○ 使用平台额度（有限）        │
  │        ● 使用自己的 API Key          │
  │                                     │
  │  Anthropic API Key: [sk-ant-•••••]  │
  │  ✅ 已验证 (Tier 1)                 │
  └─────────────────────────────────────┘
```

后端已有 `llm_api_key` 配置字段，可直接透传用户自定义 Key。

#### 4.5.9 限速配置

```yaml
# config/rate_limits.yaml
rate_limits:
  tier: 1
  keys:
    - ${ANTHROPIC_API_KEY_1}         # 双 Key 池
    - ${ANTHROPIC_API_KEY_2}
  key_strategy: "sticky_per_phase"   # round_robin | sticky_per_phase | smart
  # sticky_per_phase: Writer 阶段连续用同一 Key（利于 Prompt Caching）
  #                   切换到 Reviewer 阶段时轮换 Key
  retry:
    max_attempts: 3
    base_delay: 1.0
    max_delay: 60
    jitter: true
    switch_key_on_429: true          # 429 时自动切换到另一个 Key
  prompt_caching:
    enabled: true
    cache_prefix_fields:
      - system_prompt
      - world_setting
      - character_cards
      - narrative_strategy

# 单 Key 向后兼容：
# keys:
#   - ${ANTHROPIC_API_KEY}
# 自动退化为直通模式，RatePacer 兜底
```

#### 4.5.10 策略优先级总结

```
层级    策略                  效果                    开发成本    优先级
─────────────────────────────────────────────────────────────────────
L1     双 Key Pool           限额翻倍，消除瓶颈       低         P0 (MVP)
L2     Prompt Caching        有效 TPM 再降 50%，省钱   低         P0 (MVP)
L3     Sticky 分配           最大化缓存命中率          低         P1
L4     429 Key 切换重试      兜底，几乎零额外等待      低         P0 (MVP)
L5     RatePacer 主动限流    预防性限流（单 Key 降级用）中         P2
L6     用户自带 Key          云端多用户限额隔离        低         后续迭代
```

**MVP 实现路径**：L1 + L2 + L4 即可覆盖所有场景，开发量约 1-2 天。

---

## 五、预算与成本策略

### 5.1 总预算

**100 CAD ≈ 72 USD**（按汇率 0.72）

### 5.2 成本分配

| 项目 | 预算（USD） | 说明 |
|------|-----------|------|
| Claude API（开发调试） | ~30 | 开发期间的 API 调用 |
| Claude API（演示用） | ~15 | 最终演示的高质量生成 |
| 域名 / 部署（可选） | ~10 | 如需云端演示 |
| 预留 Buffer | ~17 | 意外开销 |
| **总计** | **~72** | |

### 5.3 单次生成成本估算

| 预设 | 模型配置 | 预估成本/次 | 适用场景 |
|------|---------|-----------|---------|
| budget | 全 Haiku + 跳过 LLM 质检 | $0.01-0.02 | 开发调试 |
| standard | Sonnet(Director/Writer) + Haiku(其余) | $0.08-0.15 | 日常使用 |
| quality | 全 Sonnet | $0.30-0.50 | 演示/高质量 |
| local | Qwen 2.5 7B (RTX 3070) | $0 | 离线开发 |

### 5.4 本地模型 Fallback

RTX 3070 8GB 可运行：
- **Qwen 2.5 7B**（Q4 量化，~5GB VRAM）：基本可用，中文能力尚可
- **Qwen 2.5 3B**（更流畅）：质量略低但速度快
- 通过 Ollama 部署，已有 `ollama_local.yaml` 预设

**建议**：开发期用 local/budget 预设，演示期切换 standard/quality。

---

## 六、敏捷开发计划

### 6.0 原则

- **每个 Sprint 交付可运行增量**
- **先跑通再优化**：功能 > 体验 > 性能
- **资产生成用 placeholder**：核心投资在脚本生成质量和交互体验
- **API 链路完整但可 mock**：所有外部 API 调用有开关

### Sprint 1（Week 1-2）：前端骨架 + 端到端联通

**目标**：React 前端能调通现有 FastAPI 后端，完成一次完整的生成流程（无交互确认，一键到底）。

**交付物**：
- [ ] React + TypeScript + Tailwind 项目初始化（Vite）
- [ ] 左右分栏基础布局
- [ ] 左侧：输入框 + 对话气泡组件
- [ ] 右侧：纯文本结果展示
- [ ] 调通 POST /generate → SSE 进度 → GET /download 完整流程
- [ ] 底部状态栏（Token、耗时、成本）

**验收标准**：在浏览器输入主题，能看到生成进度，最终能下载 Ren'Py 项目 zip。

### Sprint 2（Week 3-4）：设定确认检查点

**目标**：实现 Step 1 的完整交互——用户可查看、编辑、确认世界观/角色/大纲。

**交付物**：
- [ ] 后端新增 `POST /generate/step` 分步生成接口（仅执行 Director）
- [ ] 后端新增 `PUT /project/{id}/setting` 接口（接受用户编辑）
- [ ] 右侧面板：世界观设定卡片（可编辑）
- [ ] 右侧面板：角色卡片列表（可编辑、增删）
- [ ] 右侧面板：剧情大纲树状可视化（可编辑节点）
- [ ] 左侧对话：支持自然语言修改指令（调用 Director 局部更新黑板）
- [ ] [确认并继续] / [重新生成] 按钮

**验收标准**：用户能看到设定，手动修改角色名字后确认，进入脚本生成。

### Sprint 3（Week 5-6）：脚本生成 + 审阅交互

**目标**：实现 Step 2 的完整交互——脚本流式生成、场景级预览编辑、Reviewer 反馈展示。

**交付物**：
- [ ] 后端新增 `POST /project/{id}/generate-script` 接口
- [ ] 右侧面板：场景导航栏 + 场景内容展示
- [ ] 场景级文本编辑器（点击进入编辑模式，修改对白/情绪标签）
- [ ] Reviewer 审核结果展示（通过/警告/评分）
- [ ] 左侧对话支持脚本级 Prompt 修改（"让场景3更紧张"）
- [ ] [确认脚本] / [整体修改意见] / [重新生成] / [导出 JSON]

**验收标准**：能看到分场景脚本，编辑某个场景的对白后确认，Reviewer 结果可见。

### Sprint 4（Week 7-8）：资产管理 + 编译下载

**目标**：实现 Step 3 和 Step 4——资产展示/上传替换 + 最终编译下载。

**交付物**：
- [ ] 右侧面板：资产管理面板（立绘/背景/BGM 网格展示）
- [ ] 文件上传组件（支持拖拽，校验格式和尺寸）
- [ ] Placeholder 资产自动分配逻辑（按角色性别/场景类型匹配）
- [ ] BGM 试听播放器
- [ ] 简易 VN 预览播放器（HTML 模拟 Ren'Py 效果）
- [ ] 编译并下载按钮 → 调用 /download 接口
- [ ] 后端：用户上传资产存储 + 编译时替换 placeholder

**验收标准**：能上传自定义立绘替换 placeholder，编译下载后 Ren'Py 运行正常。

### Sprint 5（Week 9-10）：体验打磨 + 快速模式

**目标**：优化整体体验，支持"快速生成"模式（跳过中间确认）。

**交付物**：
- [ ] 快速生成模式（一键到底，生成完再统一预览编辑）
- [ ] 流程进度条组件（动画，当前步骤高亮）
- [ ] 对话面板优化（打字机效果、Markdown 渲染）
- [ ] 全局修改模式（最终预览阶段可返回任意步骤修改）
- [ ] 错误处理 UI（网络错误、API 限流提示、重试按钮）
- [ ] 响应式布局适配（移动端基础支持）
- [ ] 性能优化（懒加载、防抖）

**验收标准**：完整流程流畅无明显卡顿，快速模式可用，错误有友好提示。

### 后续迭代方向（Phase 10+）

| 优先级 | 功能 | 说明 |
|--------|------|------|
| P0 | 角色驱动生成模式 | 用户先捏角色（外貌/性格/关系），再生成剧情 |
| P0 | 真实图像生成接入 | Stability AI / FLUX 本地（RTX 3070 可跑 FLUX-dev） |
| P1 | 多语言支持 | 日文、英文 Prompt 适配 + UI 国际化 |
| P1 | Suno API BGM 生成 | 待 API 公开后接入 |
| P1 | 项目保存/加载 | 用户可保存项目，后续继续编辑 |
| P2 | 协作模式 | 多人共同编辑同一项目 |
| P2 | 模板市场 | 预设世界观/角色模板库 |
| P2 | 在线 VN 播放器 | 不依赖 Ren'Py SDK，Web 端直接玩 |

---

## 七、API 接口设计（增量）

在现有 FastAPI 基础上新增以下接口，支持分步交互：

### 7.1 项目生命周期

```
POST   /api/projects                     # 创建项目（传入 theme + config）
GET    /api/projects/{id}                # 获取项目完整状态（黑板快照）
DELETE /api/projects/{id}                # 删除项目
```

### 7.2 分步生成

```
POST   /api/projects/{id}/generate-setting   # 触发 Director 生成设定
PUT    /api/projects/{id}/setting            # 用户编辑设定（世界观/角色/大纲）
POST   /api/projects/{id}/prompt-edit        # 自然语言修改指令
POST   /api/projects/{id}/generate-script    # 触发 Writer + Reviewer 生成脚本
PUT    /api/projects/{id}/script/{scene_id}  # 用户编辑单个场景脚本
POST   /api/projects/{id}/generate-assets    # 触发资产生成（或分配 placeholder）
POST   /api/projects/{id}/upload-asset       # 用户上传替换资产
POST   /api/projects/{id}/compile            # 编译 Ren'Py 项目
GET    /api/projects/{id}/download           # 下载编译产物
```

### 7.3 实时状态

```
GET    /api/projects/{id}/stream             # SSE 端点，推送生成进度
```

### 7.4 兼容旧接口

```
POST   /generate          # 保留一键生成（内部创建项目 + 全流程）
GET    /status/{job_id}   # 保留（映射到 /api/projects/{id}）
GET    /download/{job_id} # 保留
```

---

## 八、数据模型

### 8.1 Project 状态机

```
CREATED → SETTING_GENERATED → SETTING_CONFIRMED
        → SCRIPT_GENERATING → SCRIPT_GENERATED → SCRIPT_CONFIRMED
        → ASSETS_GENERATING → ASSETS_READY → ASSETS_CONFIRMED
        → COMPILING → COMPLETED
        
任意阶段 → FAILED（可恢复）
SCRIPT_CONFIRMED / ASSETS_CONFIRMED → 可返回上一步修改
```

### 8.2 SQLite Schema 扩展

```sql
-- 在现有 jobs 表基础上扩展
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    theme TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'CREATED',
    config JSON NOT NULL,           -- 生成配置
    blackboard JSON,                -- 黑板完整快照
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE project_assets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    asset_type TEXT NOT NULL,       -- character_sprite / background / bgm / sfx
    asset_key TEXT NOT NULL,        -- e.g., "char_001_happy", "bg_street_night"
    source TEXT NOT NULL,           -- placeholder / generated / uploaded
    file_path TEXT NOT NULL,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE edit_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id),
    edit_type TEXT NOT NULL,        -- manual / prompt / regenerate
    target TEXT NOT NULL,           -- setting / character / scene / asset
    before_snapshot JSON,
    after_snapshot JSON,
    prompt TEXT,                    -- 用户的自然语言修改指令（如有）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 九、风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| 脚本分支连贯性差 | 用户体验核心 | Reviewer 3轮修订 + 用户人工审阅兜底 |
| 角色跨场景性格漂移 | 沉浸感下降 | 黑板中维护角色卡片，Writer prompt 强制引用 |
| LLM 输出格式不稳定 | 管线中断 | Schema 验证 + LLM Repair + 鲁棒 JSON 解析（已实现） |
| 100 CAD 预算紧张 | 开发调试受限 | budget preset + 本地模型开发 + mock 模式 |
| 前端开发工作量大 | 延期 | Sprint 1 先跑通最简版，逐步增强 |
| Placeholder 资产影响演示效果 | 展示不佳 | 精选高质量 CC0 素材作为默认资产 |
| Tier 1 API 限速（30K input TPM） | 生成耗时长 / 429 中断 | 详见 §4.5：双 Key Pool 限额翻倍（54%用量）+ Prompt Caching 再降 50% + 429 自动切 Key 重试 |
| 10min 脚本 LLM 上下文长度瓶颈 | 后半段质量下降 / Reviewer 截断 | 详见 §4.4 长文本策略：Writer 按场景生成、Reviewer 分层审核、Prompt 编辑滑动窗口、本地模型降级 |

---

## 十、成功指标

### MVP 交付指标

| 指标 | 目标 |
|------|------|
| 端到端生成成功率 | ≥ 90%（含 Reviewer 修订） |
| 标准模式单次生成成本 | ≤ $0.15 |
| 输入到下载完整耗时 | ≤ 5 分钟（不含用户编辑时间） |
| 生成脚本 Reviewer 评分 | ≥ 3.5 / 5.0 |
| Ren'Py 编译零报错率 | 100% |

### 体验指标（定性）

- 小白用户能在无引导情况下完成首次生成
- 从输入到看见第一个可编辑成果 ≤ 30 秒
- 编辑操作（修改角色名/对白）响应 ≤ 1 秒

---

_文档版本: v2.0 | 基于 Phase 8 后端能力 + Web 前端规划_
_最后更新: 2026-03-28_
