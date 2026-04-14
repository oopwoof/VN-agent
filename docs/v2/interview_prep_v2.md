# VN-Agent 面试准备 (v2, 2026-04-14)

> **与 v1 的差异**：v1（1111 行）覆盖了项目拷打、手撕 demo、八股知识三大块的基础。v2 **不重复** v1 的基础内容，而是聚焦 Sprint 7-12 新增的能力栈——以这些为面试重点武器，**显示从"能搭"到"能数据驱动迭代"的成长**。v1 仍然是基础知识的主参考；v2 是面试时真正要打出去的亮点。
>
> 建议通读顺序：先看 v1 §1.1-1.4（项目基础）和 v1 §3（八股），再用 v2 覆盖新能力 + 面试话术升级。

---

## 一、v2 新增能力总览

Sprint 7-12（2026-01 → 2026-04）期间加入的**新能力栈**，每一项都有具体的问题诊断、方案、数据：

| Sprint | 能力 | 核心文件 | 解决的问题 |
|--------|------|---------|------------|
| 7-5 | **StructureReviewer** | `agents/structure_reviewer.py` | Director 大纲语义错误在 Writer 后才被发现，浪费 6 次 Sonnet 调用 |
| 7-1 | **writer_mode (literary/action)** | `writer.py` + `config.py` | 不同故事类型需要不同生成策略（文学 vs 动作） |
| 7-2 | **writer_context_window** | `config.writer_context_window` | 跨场景角色声音断裂 |
| 8-1 | **双评审员（Sonnet + GPT-4o）** | `config.llm_judge_model_secondary` | Sonnet 给 Sonnet 自己打分的回音室问题 |
| 8-4 | **Prompt Caching** | `config.enable_prompt_caching` | Writer 重复调用相同 system prompt 成本高 |
| 8-5 | **Sweep 翻盘 writer_mode 默认** | 注释数据 | 假设→数据→结论的完整迭代证据 |
| 9-6 | **Symbolic World State** | `agents/state_orchestrator.py` | 长文本逻辑不一致（"已读过的东西又表现首次发现"） |
| 10-1 | **Nano Banana 图像生成** | Gemini 2.5 Flash Image + fallback | DALL-E 单点失败 |
| 10-2 | **RAG Lore Pivot** | `eval/lore.py` | literary 模式禁用 few-shot 后 FAISS 基建闲置 |
| 11-1 | **递归场景摘要** | `agents/summarizer.py` | 20+ 场景 context 爆炸 |
| 11-2 | **Character Bible 缓存** | prompt cache system suffix | 角色语言漂移 |
| 11-3 | **Persona Fingerprint 审计** | `agents/persona_audit.py` | 纯 LLM 检查声音漂移太贵 |
| 11-4 | **Per-scene snapshots** | `snapshots/*.json` | 无法回滚单场景 |
| 12-3 | **Creator mode anchor editing** | pause/continue | 人在环路编辑需求 |
| 12-4 | **Local Regen** | `agents/local_regen.py` | 只想重写一个场景，不想全部重跑 |
| 12-5 | **Unknown Chars Resolver** | `agents/unknown_chars.py` | 对话引用了 Director 未声明的角色 |

---

## 二、面试深挖问答（v2 新增）

### 2.1 StructureReviewer — 早拦截哲学

**Q: StructureReviewer 做什么？跟 DialogueReviewer 有什么区别？**

两个 Reviewer 在管线里位置不同：
- **StructureReviewer**（Sprint 7-5）：Director 之后、Writer 之前，审**大纲**
- **DialogueReviewer**（已有）：Writer 之后，审**对话**

StructureReviewer 两类审查：
1. **Narrative shape**：策略分布（不能全是 accumulate，需要有 rupture/reveal 形成弧）、角色数 vs 场景数合理性、故事弧完整性
2. **Branch intent alignment**（Sprint 6-10 第四防线）：每个分支选项的文本意图 vs 下游场景描述对齐。捕获"Director 生成了两个结构上合法但语义指向错误场景"的 bug

**Q: 为什么不等 DialogueReviewer 统一审？**

经济账：
- Writer 为 6 个场景生成对话 = 6 次 Sonnet 调用（每次 ~3K tokens input + 1K output）
- 生成完才发现大纲错 → 6 次浪费
- StructureReviewer 只用一次 Haiku 审查 outline → 几乎免费

**早拦截哲学**：问题越早发现越便宜。LLM 调用是真金白银，架构设计要把昂贵的步骤放到尽可能靠后。

**Q: 非阻塞策略怎么考虑的？**

默认 warnings 进 state['errors']，只在 `structure_review_strict=True` 时阻塞。原因：
- Sweep 场景下每个 soft warning 停，跑不完批量评测
- 真实使用时单个 soft warning 不至于让管线停 → 给用户看 warning，让 Writer 继续尝试
- 多个硬错误聚集时才阻塞 → 减少误报

---

### 2.2 RAG Lore Pivot — 工程判断力的体现

**Q: 为什么会做 Lore Pivot？**

故事线（按时间顺序讲）：

1. **Sprint 6 之前**：Writer 有 RAG few-shot 注入，FAISS 检索 1,036 条对话语料，按策略硬过滤
2. **Sprint 7-1**：引入 `writer_mode`。发现 Sonnet 做文学风格时，JRPG/galgame 原始文本 few-shot **反而污染潜在空间**（角色开始说"yare yare"、场景描写变成游戏风格舞台指示）→ literary 模式**禁用** few-shot 注入
3. **但是**：FAISS 索引、embedder、retriever 的代码还在跑，`rag_retrievals.jsonl` 还在写，**只是没人用检索结果**
4. **Gemini code review 点出**："RAG is a flower vase — we build it and never use it in literary mode"
5. **Sprint 10-2 Pivot**：同一套检索基础设施**转用来检索事实性实体**——角色背景、场景描述、世界变量、故事前提

**Q: Lore 检索跟 few-shot 的关键区别？**

| 维度 | Dialogue few-shot | Lore 检索 |
|------|-------------------|-----------|
| 检索什么 | 相似风格的对话片段 | 当前剧本的事实实体 |
| 数据来源 | 1,036 条学术标注语料（外部） | Director 当前输出（内部） |
| 索引类型 | Disk-backed、跨 run 复用 | Per-run 内存索引 |
| 适用模式 | action only（literary 禁用） | literary + action 都开 |
| 污染风险 | 可能污染风格（literary 禁因） | 事实不污染风格 |
| 目的 | 让 Writer 学"怎么说" | 让 Writer 记住"世界是什么" |

**Q: 实现细节上有什么取巧？**

```python
# eval/lore.py 关键设计
def extract_lore_entities(script, characters):
    # 不新增 LLM 调用、不改 schema
    # 直接从 Director 已有输出 extract
    # 强制 AnnotatedSession(strategy=None) 复用 EmbeddingIndex.search
```

- **不新增 LLM 调用**：lore 直接从 Director 的 VNScript 和 CharacterProfile 里 extract
- **不改 schema**：coerce 成 `AnnotatedSession(strategy=None)` 复用现有 `EmbeddingIndex.search`
- **Per-run 索引**：每个主题 bespoke，~80ms 建索引 + ~$0.008/run，噪声级别

**面试价值**：
- 展示**工程判断力**：发现"RAG 基建闲置"，没有扔掉重来，而是找到新用途
- 展示**从 code review 里读出问题**：Gemini 说"花瓶"，你真听进去了
- 展示**从 sweep 数据里诊断风格污染**：不是拍脑袋决定禁用 few-shot，是 Sprint 8-5 数据支持

---

### 2.3 Sprint 8-5 Sweep 数据故事

**Q: 你的技术决策有数据支撑吗？**

完整的**假设→实验→翻盘**故事：

**起点（Sprint 7）**：
- 假设：literary 模式（零 few-shot）更适合文学主题，action 模式（带 few-shot）更适合动作主题
- 基于直觉，默认按主题类型切换

**实验设计**：
- 4 种策略：baseline_single / baseline_self_refine / action / literary
- 2 种主题：文学向（clockmaker）+ 动作向（dragon）
- LLM-as-Judge 5 维度评分（Sonnet + GPT-4o 双评审员）

**数据（Sprint 8-5）**：

```
baseline_single        : 3.25   (单次 Sonnet 输出，无修订)
baseline_self_refine   : 3.45   (+0.20, 自评自改边际收益)
action                 : 3.92   (+0.47, few-shot 有效)
literary               : 4.17   (+0.25, physics prompt 击败 few-shot)

按主题拆解（关键）:
  文学主题（clockmaker）: literary 4.0 vs action 3.67  → literary 赢（意料之中）
  动作主题（dragon）   : literary 4.5 vs action 4.17  → literary **还是赢**（反直觉！）
```

**结论（Sprint 8-5 翻盘）**：
- literary 在**两个主题上都赢**，包括"应该 action 赢"的动作主题
- 翻盘默认：`writer_mode` 从按主题切换改为默认 `literary`
- 这直接启发了 Sprint 10-2 RAG pivot（既然 few-shot 全场面都输，那基建要转用途）

**Q: 为什么 physics prompt 比 few-shot 好？**

猜测（也是面试时可以诚实说的）：
- Sonnet 自身文学生成能力已经很强
- Few-shot 的 JRPG/galgame 原始文本**把 Sonnet 从文学潜空间拉回 galgame 潜空间**
- Physics prompt 给一个抽象的创作指导框架，让 Sonnet 在自己的文学能力范围内发挥

**面试价值**：展示**数据驱动**（不是拍脑袋）+ **反直觉发现**（愿意让数据推翻假设）+ **串联能力**（从一个发现推出下一个方向）。

---

### 2.4 长文本一致性 — 三层记忆 + 审计

**Q: 20+ 场景的 VN 怎么保证角色不漂移？**

**三层记忆体系**：

```
┌─────────────────────────────────────────────────┐
│ Layer 1: Character Bible (Sprint 11-2)          │
│ 角色定义 → prompt-cached system suffix          │
│ Anthropic ephemeral cache 5min 窗口             │
│ 首次 1.25× → 后续 0.1×                          │
│ 6-18 次 Writer 调用共享完整角色信息              │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│ Layer 2: Sliding Window (Sprint 7-2)            │
│ 最近 N 场景完整对话注入 Writer prompt            │
│ 保持局部连贯（writer_context_window）           │
│ 默认 N=0，literary config 可调高                │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│ Layer 3: Recursive Summarization (Sprint 11-1)  │
│ 更老场景 → Haiku 低温 0.2 → ≤100 词摘要         │
│ 默认 OFF，≥15 场景才开启（短 run 不付这笔钱）    │
│ 回写到 scene.summary，Writer prompt 跳过老场景   │
└─────────────────────────────────────────────────┘
```

**审计层（Sprint 11-3）**：Persona Fingerprint
- **零 LLM 纯 Python** substring + keyword 匹配
- Director 为每个角色声明 `speech_fingerprint`（用词/句式/口头禅）
- 审计器扫描对话，统计 fingerprint 特征出现频率
- **漂移阈值**：某角色对话里 fingerprint 命中率 < 阈值 → 写入 Reviewer feedback
- 设计哲学：**false positive 优于 false negative**，只作提示不强制修订
- **短路优化**：< 10 场景直接跳过（短 run 不是问题）

**逻辑层（Sprint 9-6）**：Symbolic World State
- Director 声明布尔/整型状态变量：`manuscript_read: bool=False`, `affinity_kael_mira: int=3`
- 每个场景声明 `state_reads=["manuscript_read"]` 和 `state_writes={"affinity_kael_mira": +2}`
- `state_orchestrator` 用 Haiku 翻译：`manuscript_read=True` → "Mira has already read the manuscript. Do not have her react as if discovering it for the first time."
- 注入 Writer prompt 的显式约束块
- **创作与逻辑解耦**：Writer 专注对话工艺，逻辑由状态系统保障

**Q: 为什么不直接把所有历史对话塞 Writer prompt？**

经济账 + 工程账：
- 20 场景 × 平均 500 tokens/场景 = 10K tokens context
- Writer 每次调用都塞 10K → 每场景 10K × 20 场景 = **200K tokens/run** 只是历史
- Sonnet 200K context 能装，但成本/延迟都爆
- 递归摘要：20 场景 × ≤100 词 ≈ 2K tokens，压缩 80%

**Q: Character Bible prompt caching 省多少？**

假设 Character Bible ≈ 2K tokens（所有角色背景 + fingerprint）：
- 不 cache：6-18 次 Writer 调用 × 2K × $3/MTok = **$0.036-0.108/run**（仅 Bible 部分）
- Cache：首次 $3 × 1.25 = $3.75/MTok input，后续 $3 × 0.1 = $0.3/MTok
- 18 次调用：$3.75 + 17 × $0.3 = $8.85 per MTok 等效（对比裸 $54）→ **省 84%**（仅 Bible 部分）

（真实节省取决于全 prompt 多长，这里只估算 Bible 部分）

---

### 2.5 双评审员交叉验证

**Q: 为什么要 Sonnet + GPT-4o 双评审员？**

核心问题：**"Sonnet 给 Sonnet 自己的输出打分"** 的回音室问题：
- Writer 是 Sonnet
- Reviewer 用 Sonnet 评 Sonnet 的输出 → 可能对 Sonnet 风格有系统性高估
- 评估结果不可信（sweep 数据没法说"literary 4.17 真的比 action 3.92 好"，可能只是 Sonnet 更认可 Sonnet）

**设计**：
- Primary judge: `llm_judge_model = "claude-sonnet-4-6"`（一致性监督）
- Secondary judge: `llm_judge_model_secondary = "gpt-4o"`（独立锚点）
- 两个评分分别记录，可做 inter-rater agreement 检查
- 若 OpenAI key 缺失 → 退回 Sonnet-only 模式（degraded but not broken）

**Q: inter-rater agreement 怎么算？**

配对 t-test：Sprint 8-5 sweep 里每个 (theme, strategy) 都有 Sonnet 分数和 GPT-4o 分数，看两个 judge 的排序是否一致。如果一致 → 结论可信；如果不一致 → 报 disagreement 不做结论。

---

### 2.6 可操作性设计 — Local Regen + Snapshots

**Q: 用户跑完一次想改一个场景怎么办？**

全管线重跑：
- 时间：30-60s（取决于场景数和 API 延迟）
- 金钱：全套 Sonnet + Haiku 调用
- 破坏性：其他场景的对话也会重生成，原本满意的也没了

**Sprint 11-4 + 12-4 方案**：

1. **Per-scene snapshots**：Writer 为每个场景生成完对话后立即 snapshot 到 `snapshots/{scene_id}.json`
2. **Local regen CLI**：`vn-agent regen --output ./out --scene ch1_opening`
   - 加载其他场景的 snapshot
   - 只对目标场景调 Writer + DialogueReviewer
   - 保留所有其他场景不变
3. **Creator mode anchor editing**（Sprint 12-3）：用户可以在 React 前端 pause 管线，编辑中间产物（大纲、对话、角色定义），然后 continue

**面试价值**：展示**人机协作思维**（不假设全自动是终极目标，承认人工干预的价值）+ **生产级可操作性**（考虑真实用户会怎么用）。

---

### 2.7 RAG 审计 — rag_retrievals.jsonl

**Q: RAG 黑盒怎么调试？**

每次检索落盘 JSONL 一行：

```json
{
  "scene_id": "ch1_opening",
  "strategy": "__lore__",               // 或具体策略名
  "query": "Aldric calls Sable...",     // 完整 query
  "retrieved": [                         // top-K 检索结果
    {
      "id": "location:bg_workshop_midnight",
      "title": "bg_workshop_midnight",
      "strategy": null,                  // lore 检索无策略
      "text_preview": "..."              // 前 200 字
    },
    ...
  ]
}
```

**审计价值**：
- **命中率分析**：哪些 query 召回了无关结果？query 构造需要优化吗？
- **策略分布**：lore 检索 vs strategy 检索各占多少？是否平衡？
- **回放调试**：用户投诉某场景对话不对，可以翻 JSONL 看当时给 Writer 塞了什么
- **Sweep 分析**：跨主题比较 RAG 命中模式，看哪些主题 RAG 帮助最大

每个 run 生成一个独立文件，不跨 run 污染。按 scene_id + strategy 分组方便 grep。

---

## 三、面试话术升级（v2 扩展 v1）

### 3.1 开场自我介绍（30 秒版）

> "我主要做了 VN-Agent，一个 **AI 视觉小说自动生成系统**。核心是 **LangGraph 多 Agent DAG + 双轨 RAG + 长文本一致性工程**。
>
> **技术亮点**有三个：
> 1. **从 Sprint 数据里读出方向**：Sprint 8-5 sweep 发现 physics prompt 全场面打败 few-shot，直接导致 Sprint 10-2 把 RAG 基建从风格 few-shot pivot 成事实实体检索
> 2. **长文本一致性工程**：Character Bible prompt caching + 递归场景摘要 + 符号世界状态 + 零 LLM persona fingerprint 审计，解决 20+ 场景 VN 的角色漂移问题
> 3. **早拦截架构**：StructureReviewer 在 Writer 启动前审大纲，省掉 6 次 Sonnet 调用"

### 3.2 "你遇到过最难的技术问题"

**推荐答案**：Sprint 7 literary 模式上线后的**隐性基建空转**问题。

> "Sprint 7 我加了 writer_mode。literary 模式禁用了对话 few-shot 注入，因为发现 JRPG 风格原始文本会污染 Sonnet 的文学潜空间。但 FAISS 索引、embedder、retriever 的代码还在跑，每个 run 都在生成 `rag_retrievals.jsonl`，只是没人用检索结果。
>
> Gemini code review 的时候有一句话点醒我：'RAG is a flower vase — we build it and never use it in literary mode'。
>
> 这让我意识到一个更大的问题：**literary 模式下 RAG 基建是死代码**。两种选择：
> 1. 扔掉：清理代码，literary 模式不跑 RAG
> 2. 重用：找新用途
>
> 我选了 (2)——Sprint 10-2 的 Lore Pivot。把同一套检索基础设施转用来检索**事实性实体**（角色背景、场景描述、世界变量），让 Writer 跨场景保持世界观一致。这个解法的几个关键决策：
>
> - Lore 从 Director 已有输出 extract，**不新增 LLM 调用、不改 schema**
> - Per-run 内存索引，**不污染主 disk 索引**
> - Coerce 成 `AnnotatedSession(strategy=None)` **复用 `EmbeddingIndex.search`**
> - 在 literary + action **两种模式都开**（facts 不污染风格）
>
> 这个案例我觉得能说明几个点：
> 1. **愿意听 code review**：没有把 Gemini 的批评当噪音，真的让它推动决策
> 2. **工程判断力**：死代码不是直接删，看能不能重用基建
> 3. **系统思维**：一个发现（Sprint 8-5 sweep 数据）能推出另一个方向（Sprint 10-2 pivot）"

### 3.3 "你这个项目在真实场景有什么用？"（游戏/AI 应用方向延伸）

> "VN-Agent 本身是视觉小说，但架构可以迁移到几个游戏研发场景：
>
> 1. **关卡/任务自动生成**：Director 的两步规划 + StructureReviewer 的大纲审查 → 可用于关卡设计工具（大纲审查检查可达性、平衡性、任务依赖）
> 2. **NPC 对话系统**：双轨 RAG（lore 检索 + dialogue few-shot）→ 在线对话生成，lore 检索保证世界观一致，few-shot 保证风格一致
> 3. **长对话历史管理**：递归摘要 + Character Bible prompt caching → 长时间玩家 NPC 互动不掉角色一致性
> 4. **生成内容审查**：Reviewer 架构（结构 + 质量 + persona + 符号状态）→ UGC 内容审查管线
> 5. **生成流程可操作性**：local regen + snapshots + creator mode → 策划/写手的人在环路编辑工具"

### 3.4 反问面试官（v2 补充游戏场景）

- "团队在长文本生成（对话历史、剧情记忆）上遇到过角色一致性问题吗？怎么解决的？"
- "Agent 系统的审计/可观测性是怎么做的？有类似 `rag_retrievals.jsonl` 的审计文件吗？"
- "评估 LLM 输出质量是用 LLM-as-Judge 还是别的方式？有做双评审员避免回音室问题吗？"
- "本地推理 vs 云端 API 的取舍？有没有做过 sweep 对比不同模型/策略？"

---

## 四、手撕/现场 demo（v2 补充 v1）

v1 已有：Agent 修订循环、语义检索、BFS 可达性、Tool Calling schema。v2 补充：

### 4.1 Persona Fingerprint 简化实现（零 LLM）

```python
import re
from collections import Counter
from dataclasses import dataclass

@dataclass
class PersonaFingerprint:
    keywords: list[str]        # 常用词（"quite", "rather"）
    phrases: list[str]         # 口头禅（"as you know", "I reckon"）
    min_hit_rate: float = 0.3  # 30% 对话行至少命中一次

def audit_persona(
    character_id: str,
    dialogue_lines: list[str],
    fingerprint: PersonaFingerprint,
) -> tuple[bool, str]:
    """
    返回 (passed, feedback)。False positive 优于 False negative。
    """
    hits = 0
    all_keywords = fingerprint.keywords + fingerprint.phrases
    for line in dialogue_lines:
        line_lower = line.lower()
        if any(kw.lower() in line_lower for kw in all_keywords):
            hits += 1

    hit_rate = hits / max(len(dialogue_lines), 1)
    if hit_rate < fingerprint.min_hit_rate:
        return False, (
            f"{character_id}: fingerprint hit rate {hit_rate:.1%} "
            f"below {fingerprint.min_hit_rate:.0%}. "
            f"Expected traits: {all_keywords[:3]}..."
        )
    return True, ""
```

**面试点评时说**：
- 故意选简单的 substring 匹配，不是 false positive 友好
- 真实生产里可能用 TF-IDF 或编辑距离，但那是优化，不是起点
- 零 LLM 成本，作为 Reviewer 的前置 cheap check

### 4.2 递归摘要设计题

"给你一个 20 场景 VN，如何为 Writer 维护场景 10 的完整上下文（记住前 9 个场景的关键事实）？"

**回答框架**：

```python
async def build_writer_context(
    current_scene_idx: int,
    all_scenes: list[Scene],
    window: int = 2,           # 滑窗大小
) -> str:
    """三层上下文合并。"""
    ctx = []

    # Layer 1: Character Bible（通过 system prompt 注入，不在这里）
    # 但注意这一层靠 prompt caching 省钱

    # Layer 2: 滑窗 — 最近 window 场景完整对话
    window_start = max(0, current_scene_idx - window)
    for scene in all_scenes[window_start:current_scene_idx]:
        ctx.append(f"## Scene {scene.id} (full)\n")
        for line in scene.dialogue:
            speaker = line.character_id or "narrator"
            ctx.append(f"[{speaker}] {line.text}")

    # Layer 3: 更老场景用摘要
    for scene in all_scenes[:window_start]:
        if scene.summary:  # summarizer 已经写过
            ctx.append(f"## Scene {scene.id} (summary)\n{scene.summary}")
        # 没 summary 的跳过，非阻塞

    return "\n\n".join(ctx)
```

**讨论点**：
- 滑窗 window 怎么选？经验值 1-2，再大 context 爆炸
- 摘要什么时候生成？**场景写完 + Reviewer 通过之后**（不是生成前），这样摘要描述的是 actually landed 的内容
- 摘要 retry 怎么办？Haiku 低 temp=0.2 近确定性，一般不用 retry；失败就 `scene.summary=None`，Writer prompt 跳过那一层

### 4.3 RAG 审计文件的解析

"给你一个 `rag_retrievals.jsonl`，写个脚本分析 RAG 命中模式"

```python
import json
from collections import defaultdict, Counter

def analyze_rag_audit(jsonl_path: str) -> dict:
    """
    分析 RAG 审计文件:
      - 每场景 query 数
      - lore vs strategy 检索比例
      - 策略检索命中率（retrieved 里至少一个 strategy 匹配 query strategy）
    """
    per_scene = defaultdict(list)
    strategy_vs_lore = Counter()
    strategy_hit = {"hit": 0, "miss": 0}

    with open(jsonl_path) as f:
        for line in f:
            r = json.loads(line)
            per_scene[r["scene_id"]].append(r)

            if r["strategy"] == "__lore__":
                strategy_vs_lore["lore"] += 1
            else:
                strategy_vs_lore["strategy"] += 1
                # 检查 top-K 里是否有至少一个 strategy 匹配
                hits = [
                    rt for rt in r["retrieved"]
                    if rt.get("strategy") == r["strategy"]
                ]
                if hits:
                    strategy_hit["hit"] += 1
                else:
                    strategy_hit["miss"] += 1

    return {
        "scenes": len(per_scene),
        "queries_per_scene": {k: len(v) for k, v in per_scene.items()},
        "strategy_vs_lore": dict(strategy_vs_lore),
        "strategy_hit_rate": (
            strategy_hit["hit"] / max(sum(strategy_hit.values()), 1)
        ),
    }
```

**面试点评**：
- `defaultdict(list)` + `Counter` 是 Python 数据处理的习惯用法
- 计算 hit rate 要防除零（`max(sum, 1)`）
- 真实场景会加 argparse、CSV/JSON 输出、可视化等，但核心是数据聚合逻辑

---

## 五、核心话术速查表（v2 最终版）

| 追问主题 | 30 秒核心回答 |
|---------|--------------|
| 项目是什么 | 多 Agent 生成 VN，亮点是**双轨 RAG + 长文本一致性 + 数据驱动迭代** |
| 为什么拆 Agent | JSON 稳定性 + 注意力分散 + 独立选模型/重试 + **早拦截省钱** |
| RAG 怎么优化 | 双轨：**dialogue few-shot**（1036 语料+策略硬过滤）+ **lore 实体**（director 输出 extract，不污染风格） |
| 长文本一致性 | 三层记忆：**Character Bible 缓存 + 滑窗 + 递归摘要** + **Persona 审计** + **Symbolic State** |
| 数据驱动 | Sprint 8-5 sweep：**literary 4.17 > action 3.92**，两个主题都赢，驱动 RAG pivot |
| 双评审员 | Sonnet 自评 + **GPT-4o 独立锚点**，避免回音室，可做 inter-rater agreement |
| 早拦截 | **StructureReviewer** 在 Writer 之前审大纲，**省 6 次 Sonnet 调用** |
| 截断修复 | **双策略 JSON salvage**（反向闭合 + 正向括号计数）+ **LLM self-repair** |
| 降本 73% | Haiku $0.80/$4 vs Sonnet $3/$15；把 Haiku 用在**翻译类廉价工作** |
| Prompt caching | Anthropic ephemeral 5min 窗口，**首次 1.25×，后续 0.1×** |
| Local regen | Per-scene snapshot + CLI，**只重写一个场景不破坏其他** |
| RAG 审计 | **rag_retrievals.jsonl** 每行 query/retrieved 落盘，离线分析 |

---

## 六、v1 → v2 信息迁移指南

v1 关于**以下内容**保留有效，面试时可参考 v1 §对应章节：
- §1.1 架构基础（6 Agent 拆分、LangGraph 选型）
- §1.2 RAG 基础优化（query 拼接、FAISS 选型、F1 0.34 解读）
- §1.3 工程基础（Tool Calling、测试、CI）
- §1.4 游戏场景延伸
- §2 手撕代码（修订循环、语义检索、BFS、Tool Calling schema）
- §3 八股知识（Transformer、Agent 框架、Prompt Engineering）
- §4 STAR 框架回答

v2 **新增/升级**（本文档重点）：
- StructureReviewer + 早拦截哲学
- Sprint 8-5 sweep 数据驱动故事
- RAG Lore Pivot 工程判断力案例
- 长文本一致性三层记忆 + Persona 审计 + Symbolic State
- 双评审员交叉验证
- Local Regen + snapshots + creator mode
- RAG 审计文件 rag_retrievals.jsonl
- Prompt caching 成本模型

**面试时推荐策略**：v1 基础内容铺底（让面试官看到管线完整），v2 新能力作为深挖点武器（证明迭代能力）。如果时间短，直接用 v2 的 §三.1 30 秒介绍开头，等面试官挑具体方向再深入。
