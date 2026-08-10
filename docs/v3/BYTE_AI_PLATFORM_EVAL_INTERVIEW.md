# 字节 AI Platform 评测产品实习面试：VN-Agent 项目讲法

> 岗位：产品（评测方向）实习生 - AI Platform / AgentOps  
> 目标：把 VN-Agent 从“多 Agent 生成项目”讲成“AgentOps 评测、观测、Badcase 归因、数据飞轮”的产品经历。  
> 简历锚点：Minimax Prompt Engineer + VN-Agent + CGI 智能派单，形成“真实用户对话评测经验 + 自研 AgentOps 项目 + 可解释 AI 决策系统”的组合。

---

## 1. 岗位真正看什么

这个岗位不是单纯问“你会不会做大模型应用”，而是看你能不能站在 Agent 开发者和平台产品的中间，设计一套让 Agent 持续变好的基础设施。

### JD 关键词拆解

| JD 表述 | 背后能力 | VN-Agent 对应讲法 |
|---|---|---|
| AgentOps 平台 | 面向 Agent 开发者的工程平台，而不是单点 Demo | VN-Agent 不是一次生成，而是 Director / Writer / Reviewer / Asset pipeline，有观测、评测、重试、成本记录 |
| 评测产品规划和设计 | 定义指标、评测样本、版本验收、Badcase 流转 | VN-Agent 有 LLM-as-Judge、BFS 结构校验、mechanical check、smoke metrics、baseline sweep |
| Prompt Engineering | Prompt 不是玄学，要能被评测闭环驱动 | literary vs action vs self-refine vs baseline 的 8-cell sweep，数据驱动默认策略切换 |
| Agent 观测 | Trace、token、stop_reason、cost、失败类型可见 | 记录 token usage、max_tokens hit rate、cache token、key rotation、reviewer fail type |
| 数据处理 | 评测集构造、标签体系、样本归因 | Minimax 的意图树标签 + VN-Agent 的 graph/dialogue/quality fail 分类 |
| 模型微调/数据飞轮 | 评测结果反哺数据、prompt、路由策略 | “评测 -> 归因 -> 策略修复 -> smoke 验证 -> 回写经验”闭环 |
| 商业化平台 | 要讲 PM 视角：用户是谁、场景是什么、价值怎么量化 | 用户是 Agent 开发者，痛点是效果不可控、问题不可定位、调优无闭环 |

### 面试中的一句定位

> VN-Agent 表面上是视觉小说生成器，但我准备重点讲的是它背后的 AgentOps 问题：一个多 Agent 应用上线后，怎么评测效果、怎么观测失败、怎么判断失败应该由哪个 Agent 修、怎么把 Badcase 变成下一轮 prompt / routing / 数据策略的改进。

---

## 2. 你的优势叙事

### 推荐主线

你可以把自己包装成“懂 Agent 应用，也做过评测闭环的 AI 产品候选人”：

1. **用户侧经验**：在 Minimax 做过真实用户对话 case 归因、意图树标签、Benchmark 和版本验收。
2. **平台侧项目**：VN-Agent 自己搭了一个多 Agent 应用，并且踩过评测、观测、重试、成本、结构化输出这些 AgentOps 问题。
3. **产品侧迁移**：能把这些经验抽象成平台能力，例如评测集管理、指标看板、trace 归因、Badcase workflow、prompt 版本对比。

### 不要只讲技术栈

弱讲法：

> 我用了 LangGraph、FAISS、Pydantic、Ren'Py，做了多 Agent 自动生成视觉小说。

强讲法：

> 我把 VN-Agent 当成一个小型 AgentOps 平台来做：每次 run 都记录 cost、token、stop_reason、reviewer fail type；每个失败不是只看 pass/fail，而是分类成 graph-class、dialogue-class、LLM-quality，再决定应该回到 Director、Writer，还是直接 accept。这个过程和评测平台很像，本质是把 Agent 的黑盒失败变成可观测、可归因、可迭代的产品闭环。

---

## 3. VN-Agent 最适合这个岗位的 5 个可聊点

### 3.1 评测体系：从“生成好不好”拆成多层指标

**面试官可能问**：你怎么评估一个 Agent 生成结果好不好？

**推荐回答**：

> 我不会只让 LLM 打一个总分，因为总分不可行动。VN-Agent 里我把评测拆成三层：第一层是 deterministic structural check，比如 BFS 可达性、分支引用、角色 ID 是否存在；第二层是 mechanical check，比如 dialogue line count、schema 是否完整；第三层才是 LLM quality check，用 voice、subtext、arc、pacing、strategy execution 五个维度打分。这样评测结果可以直接变成修复动作：结构问题回 Director，台词质量问题回 Writer。

**亮点**：

- 不是“LLM-as-Judge 一把梭”，而是 deterministic rules + LLM judge 分层。
- 每个指标要能 action，否则只是 vanity metric。
- 这非常贴合评测产品：指标体系设计、自动评测、失败归因、版本验收。

**可用数据**：

- Writer 策略 sweep：`literary 4.17 > action 3.92 > self_refine 3.45 > baseline_single 3.25`。
- 结构校验覆盖：start_scene / branch_refs / BFS 可达 / character 一致性。
- 真 API smoke：M0、mini #1、mini #2 三轮，不是 mock 数据。

### 3.2 Badcase 归因：FAIL 不是布尔值，而是分类问题

**面试官可能问**：Agent 失败了，你怎么定位原因？

**推荐回答**：

> 我在 VN-Agent 里踩过一个典型坑：最早 Reviewer 只告诉我 fail，于是所有 fail 都回 Writer 修。但 M0 smoke 发现有些 fail 是 graph topology，比如 unreachable scene，Writer 根本不负责改 `next_scene_id`，重试三轮只是在烧 token。后面我把 ReviewResult 加了 `can_writer_fix`，把失败分类成 graph-class、dialogue-class、LLM-quality，路由器根据类型决定回 Director、回 Writer，还是跳过无效 revision。

**产品化抽象**：

如果做 AgentOps 评测平台，这对应的是：

- Fail taxonomy：失败类型体系。
- Root cause attribution：失败归因到 prompt、tool、retrieval、model、planner、executor。
- Suggested action：给开发者下一步建议，而不是只显示红灯。

**可用数据**：

- M0 6-scene smoke：38.1 min，3 轮 Writer rev，暴露 graph-class fail。
- C1 修复：`can_writer_fix=False` 时跳过 Writer 无效重试。
- 估算避免浪费：约 `$1.10 / 6-scene run` 的 wasted Writer cycles，50 scene 约 `$9` 量级。

### 3.3 数据飞轮：评测结果如何反哺 Prompt / RAG / Routing

**面试官可能问**：你怎么理解 Agent 调优的数据飞轮？

**推荐回答**：

> 我理解的数据飞轮不是“收集更多数据”这么简单，而是评测结果必须能驱动下一轮产品或工程策略。VN-Agent 里有两个例子。第一，writer_mode sweep 发现 literary prompt 比 action few-shot 更好，说明原本的对话 few-shot RAG 在文学生成里有风格污染，于是我把 RAG 从风格示例转向 lore 实体检索。第二，M0 smoke 发现 graph-class fail 不该回 Writer，于是把 routing 从字符串判断升级成 typed review result。两者都是从 eval signal 到 product decision。

**产品化抽象**：

AgentOps 评测平台可以把数据飞轮设计成：

1. 收集 run trace、prompt version、model version、retrieval evidence、judge score。
2. 聚合 Badcase，按失败类型和影响面排序。
3. 支持开发者做 prompt / model / retrieval / tool 参数 A/B。
4. 用固定 eval set 做回归测试。
5. 把胜出策略沉淀为模板或默认配置。

### 3.4 观测与成本：评测平台不能只看效果，还要看代价

**面试官可能问**：AgentOps 为什么需要观测？

**推荐回答**：

> 因为 Agent 的质量问题和成本问题通常是同一个问题的两面。比如 VN-Agent 里我一开始以为把 max_tokens 从 5000 提到 8000 能减少截断，但 mini #1 反向证明 Sonnet 会把 cap 当 target，3/3 都吃满 8K，单 scene 成本上涨约 51%。如果没有 token、stop_reason、cost 的观测，只看最终 pass/fail，就会做错优化方向。

**可用数据**：

- M0 max_tokens hit rate：`89% (16/18)`。
- mini #1 cap 8000：`100% (3/3)`，out tokens `7999 / 8000 / 8000`。
- 单 scene 主调成本：`$0.084 -> $0.129`，约 `+54%`。
- 结论：cap 不是质量杠杆，真正杠杆在 prompt-side line budget 和 clean JSON 终止指令。

### 3.5 长文本一致性：Agent 评测不只是单轮问答

**面试官可能问**：你项目里最像复杂 Agent 应用的地方是什么？

**推荐回答**：

> VN-Agent 的难点不是生成一段文本，而是 20 到 50 个 scene 的长线一致性。这里评测也不能只看单轮回答，要看跨场景角色、世界状态、伏笔回收和分支可达性。我做了三层记忆和评测：全局角色设定作为 cached prefix，章节 rollup 压缩历史，局部 RAG 注入当场景相关 lore；评测侧则看 graph reachability、角色一致性、context_deps 是否被正确承接。

**适合对齐 JD 的点**：

- Agent 全生命周期：规划、生成、审查、重试、资产生成、编译。
- 复杂 Agent 不是单 prompt，而是状态机 + 记忆 + 工具 + 评测。
- 平台产品需要服务这类复杂开发者，而不是只服务 Chatbot。

---

## 4. 3 分钟项目介绍模板

### 版本 A：偏评测产品

> VN-Agent 是我做的一个多 Agent 视觉小说生成系统，用户输入一个故事主题，系统会通过 Director、Writer、Reviewer 和 Asset agents 生成可运行的 Ren'Py 项目。  
>
> 我面试这个岗位会重点讲它的 AgentOps 部分。因为这个项目最大的挑战不是“能不能生成”，而是生成失败后如何评测、归因和迭代。我把评测拆成三层：第一层是 Python deterministic checks，例如 BFS 可达性、分支引用、角色 ID；第二层是 mechanical checks，例如行数和 schema 完整性；第三层是 LLM-as-Judge，从 voice、subtext、arc、pacing、strategy execution 五个维度评价文本质量。  
>
> 这个分层评测直接驱动 routing。比如 M0 smoke 时 Reviewer 发现 unreachable scenes，但当时所有 fail 都回 Writer，结果 Writer 连续三轮重试都修不好，因为拓扑是 Director 负责的。后面我把 ReviewResult 设计成 typed result，加了 `can_writer_fix`，让 graph-class fail 不再浪费 Writer budget。这个经历让我很明确地意识到，评测产品不能只告诉用户 pass/fail，而要告诉开发者失败类型、根因和建议动作。  
>
> 同时，我也做了策略评测和成本观测。比如比较 single-shot、self-refine、action few-shot、literary prompt 四种方案，发现 literary 评分最高，推动我把 RAG 从风格 few-shot 转向 lore 实体检索。另一个例子是 token cap 实验，8K cap 反而让模型吃满更多 token、成本上涨，说明优化方向应该回到 prompt-side budget，而不是盲目加 max_tokens。  
>
> 所以我觉得 VN-Agent 和 AgentOps 评测产品很相关：它让我完整经历了“构建 Agent -> 观测运行 -> 评测结果 -> Badcase 归因 -> 策略迭代”的闭环。

### 版本 B：偏产品经理

> 如果把 VN-Agent 抽象成产品问题，它服务的是“想快速创作长篇互动故事的创作者”。但从平台角度看，它也是一个 Agent 开发者工具：我需要知道每次生成为什么好、为什么坏、哪里花了钱、失败应该回到哪个模块修。  
>
> 我做的核心不是单次生成效果，而是把调优过程产品化。首先定义评测指标，把结构正确性、机械完整性和文学质量分开；然后把每次 run 的 token、cost、stop_reason、review fail type 记录下来；最后把评测结果用于调优，比如 prompt 策略 sweep、RAG pivot、routing 修复。  
>
> 这和 AI Platform 的 AgentOps 很像：平台要帮助业务开发者把 Agent 从“能跑”变成“可观测、可评测、可持续优化”。我在 Minimax 做过真实用户对话 case 归因和 Benchmark，在 VN-Agent 里又把这种评测闭环落到了一个完整 Agent 系统里，所以我对这个岗位的评测产品方向很感兴趣。

---

## 5. 面试问答库

### Q1：你为什么觉得 VN-Agent 和 AgentOps 评测产品相关？

**短答**：

> 因为 VN-Agent 的核心问题就是 AgentOps 的问题：多 Agent 链路长、失败原因复杂、效果和成本都需要观测，调优必须靠评测闭环。它不是一个单 prompt demo，而是一个包含 planning、writing、reviewing、retry、asset generation、compile 的完整 Agent pipeline。

**加分点**：

- AgentOps 平台要服务的是开发者，所以输出不能只是分数，而是 failure taxonomy + trace + suggested action。
- VN-Agent 的 `can_writer_fix` 就是一个小型 suggested action：这个问题 Writer 能不能修，不能修就不要让它重试。

### Q2：如果让你设计 Agent 评测产品，你会怎么做？

**推荐框架**：

1. **对象层**：支持 prompt、agent、workflow、tool call、retrieval、model version 的评测对象。
2. **数据层**：支持人工样本、线上 Badcase、合成样本、回归集。
3. **指标层**：分 deterministic metrics、LLM judge metrics、human review metrics、business metrics。
4. **诊断层**：把 fail 归因到 prompt、planner、retriever、tool、memory、model、schema。
5. **工作流层**：支持 A/B、版本对比、回归测试、发布门禁、报告生成。

**用 VN-Agent 举例**：

- deterministic：BFS reachability、schema validation、line count。
- LLM judge：五维 rubric。
- observability：token、cost、stop_reason、key rotation。
- diagnosis：graph-class / dialogue-class / LLM-quality。
- iteration：literary prompt 胜出后修改默认 writer_mode，graph-class fail 后修改 routing。

### Q3：LLM-as-Judge 有什么问题？你怎么规避？

**短答**：

> LLM-as-Judge 最大问题是稳定性、偏见和不可行动。如果只给总分，很难定位怎么修。我会把它放在 deterministic checks 后面，只让它判断规则无法覆盖的质量维度，并且把 rubric 拆细。

**VN-Agent 例子**：

- 结构问题不用 LLM 判断，BFS / set 差集更稳定。
- 文学质量才交给 LLM judge，拆成 voice、subtext、arc、pacing、strategy_execution。
- 评测结论要绑定 action：低 voice 分可能回 Writer prompt，graph unreachable 回 Director。

### Q4：你如何构造评测集？

**短答**：

> 我会分三类：golden set、adversarial set 和 regression set。Golden set 看核心场景，adversarial set 专门卡边界条件，regression set 来自线上 Badcase，保证新版本不把旧问题放回来。

**结合经历**：

- Minimax：真实用户 case 归因、聚类，形成意图树标签和 Benchmark。
- VN-Agent：结构校验的 adversarial cases，例如 branch_refs、unreachable、character mismatch。
- CGI：无 Ground Truth 时用留一法 + 专家盲评，说明你知道真实业务里评测集不一定天然存在。

### Q5：你怎么判断一个评测指标是好指标？

**短答**：

> 好指标要满足三点：和用户体验相关、可稳定复现、能驱动动作。不能驱动动作的指标只能做观察，不能做发布门禁。

**例子**：

- `review_passed` 太粗，不能指导修复。
- `graph-class fail` 好，因为知道要回 Director 或跳过 Writer。
- `max_tokens hit rate` 是观察指标，可以提示截断风险，但不直接代表质量。
- `LLM quality avg score` 可用于版本比较，但需要配合维度分和 Badcase 样本。

### Q6：你做过哪些数据驱动决策？

**推荐回答**：

> VN-Agent 里我有两个典型决策。第一是 writer_mode sweep，原本以为 action few-shot 会更适合视觉小说，但数据上 literary prompt 4.17，高于 action 3.92、自评自改 3.45 和 single 3.25，所以我把默认方向转向 literary，并把 RAG 从风格示例改成事实实体检索。第二是 max_tokens cap 实验，我以为 5K 太紧，提到 8K 会缓解截断，但 mini smoke 显示模型 100% 吃满 8K，成本上涨，所以我 revert 了这个方向，转向 prompt 端约束输出长度。

### Q7：这个项目和你 Minimax 实习有什么连续性？

**短答**：

> Minimax 是真实用户对话场景，我做的是 case 归因、意图标签、Benchmark 和版本验收；VN-Agent 是我把这套思路迁移到自研 Agent pipeline 里。两者共同点都是：先定义失败类型，再用评测结果驱动策略和数据调整。

**具体连接**：

- Minimax：用户对话 Badcase -> 意图树标签 -> prompt / CoT 策略 -> A/B 验证。
- VN-Agent：生成 Badcase -> reviewer fail taxonomy -> routing / RAG / prompt strategy -> smoke 验证。

### Q8：如果加入这个团队，你最想做哪类评测产品能力？

**推荐回答**：

> 我最感兴趣的是 Agent eval 的“归因层”和“数据飞轮层”。很多平台已经能跑 eval 和展示分数，但开发者真正痛的是不知道为什么掉分，也不知道下一步该改 prompt、retrieval、tool 还是 model。我希望做的是把 trace、judge result、Badcase cluster 和版本对比结合起来，让平台不仅给分，还能给出 failure taxonomy 和 next action。

**可以提出一个产品想法**：

- Eval report 自动生成“失败类型 Top N”。
- 每类失败关联 representative traces。
- 支持一键拉取到 prompt A/B experiment。
- 回归集自动纳入历史 Badcase。
- 发布前显示新旧版本在核心场景、长尾场景、成本指标上的差异。

---

## 6. 可以反问面试官的问题

### 关于岗位

1. 评测产品目前更偏离线 Benchmark，还是线上 Agent trace 的持续评估？
2. 平台服务的主要用户是内部业务研发、算法同学，还是外部商业化客户？
3. 目前 Agent 评测里最大的痛点是指标定义、数据集构建、LLM judge 稳定性，还是 Badcase 归因？

### 关于产品

1. 现在平台是否支持 prompt / model / retrieval / tool 参数的版本对比？
2. 评测报告会不会和 Agent trace 打通，比如从低分样本直接跳到执行链路？
3. 对于没有标准答案的 Agent 任务，团队更常用人工标注、LLM judge、用户反馈，还是多信号融合？

### 关于团队

1. 这个实习生会更偏 PRD 和竞品研究，还是会深度参与评测指标和平台功能设计？
2. 产品侧和研发侧协作节奏是按业务需求推进，还是会有平台能力 roadmap？

---

## 7. 简历表述可微调方向

当前简历里的 VN-Agent 已经贴近岗位，但可以在面试口头表达里更突出“评测平台”。

### 原简历重点

> 产品设计与记忆架构、并发机制与策略调优、RAG 用途错配、评测与迭代闭环。

### 面试时建议强化为

> 设计多 Agent 生成系统的评测与观测闭环：将生成质量拆解为结构可达性、机械完整性、LLM 文学质量和成本指标；通过 Reviewer fail taxonomy 定位 graph-class / dialogue-class / quality fail，并驱动 prompt、RAG 和 routing 策略迭代。

### 可补充的一句

> 这个项目让我从产品角度理解 AgentOps：开发者不只需要“跑起来”的 Agent，更需要能解释每次失败、比较每个版本、沉淀 Badcase 数据飞轮的平台。

---

## 8. 数据边界：哪些能说，哪些别夸大

### 可以直接说

- 做过 single / self-refine / action / literary 的策略对比，literary 得分最高。
- 做过三次真 API smoke，不是纯 mock。
- 记录 token、cost、stop_reason、max_tokens hit rate、key rotation。
- 引入 `can_writer_fix` 后，避免 graph-class fail 被错误送回 Writer。
- 评测包含 deterministic checks + LLM judge，不是全靠主观感觉。

### 谨慎说

- `50 scene wall ≤ 30 min` 是北极星目标，不是已达成。
- `cache_read_ratio ≥ 0.5` 是目标，字段已通，但 mini smoke 上还没验证长篇命中。
- `73% 降本` 是模型分级路由的预算模式估算，不要说成线上实测降本。
- `50 scene ~$15` 是 stress runner 目标/估算，不是最终稳定生产结果。

### 不建议说

- “我的系统已经达到生产级长篇生成。”
- “缓存已经稳定省 50% 成本。”
- “评测完全自动化替代人工。”
- “LLM-as-Judge 结果绝对可靠。”

---

## 9. 最适合背的 6 句话

1. **我理解 AgentOps 评测产品的核心不是打分，而是把 Agent 的黑盒失败变成可观测、可归因、可行动的调优闭环。**
2. **VN-Agent 里我把评测拆成 deterministic structural checks、mechanical checks 和 LLM quality judge 三层，避免所有问题都丢给 LLM 判断。**
3. **M0 smoke 让我意识到 fail 不是布尔值，而是分类问题；graph-class fail 回 Writer 只会浪费 token，所以我加了 `can_writer_fix` 做 typed routing。**
4. **writer_mode sweep 证明了 prompt / RAG 策略不能靠直觉，literary 4.17 高于 action 3.92 后，我把 RAG 从风格 few-shot 转向事实实体检索。**
5. **token cap 实验是一个反例：8K cap 没解决质量，反而让 Sonnet 吃满更多输出，所以评测平台必须同时观测效果和成本。**
6. **我在 Minimax 做过真实用户对话 Badcase 和 Benchmark，在 VN-Agent 里把这套评测闭环迁移到了完整 Agent pipeline，这和 AI Platform 的评测产品方向高度相关。**

---

## 10. 一句话结论

这场面试不要把 VN-Agent 讲成“我做了一个视觉小说生成器”，而要讲成：

> 我用 VN-Agent 亲手做了一遍 AgentOps 评测产品要解决的问题：如何定义指标、采集 trace、评估版本、归因 Badcase、控制成本，并把评测信号变成下一轮 prompt、RAG 和 routing 的产品决策。
