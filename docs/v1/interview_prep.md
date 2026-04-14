# 游戏AI研发实习生（Agent方向）面试准备

> 岗位：崩坏IP项目组 · AI研发实习生（Agent方向）
> 核心匹配：VN-Agent 本身就是一个 AI 驱动的游戏内容生产管线，与 JD 要求的"AI Agent 在游戏研发管线中的应用"高度吻合

---

## 零、米哈游 AI 进展速查（面试前必读）

### 两条主线

| 方向 | 口号 | 具体落地 |
|------|------|---------|
| **AI驱动提效** | AI 应用到游戏开发全流程 | Echo 平台、杯中逸事测试工具、策划配置自动生成（2h→5min）、2D→3D 预览、材质生成 |
| **AI驱动创新** | AI 带来新游戏体验 | 帕姆AI助手（代做日常/打关卡）、三月七 6.1 万条不重复对话（380ms 延迟）、智能NPC |

### Echo 平台 —— 你面试的组在做的东西

- 米哈游内部 **AI Agent 平台**，承载游戏研发各环节的 AI 工具链
- 已落地工具：
  - **策划配置自动生成**：输入文字描述 → LLM 生成角色配置 → 落地游戏环境，**配置时长 2 小时→5 分钟**
  - **"杯中逸事" 自动测试**：AI Agent 自主控制游戏角色，自动寻找最优解，替代人工 QA
  - **美术辅助**：正视图→3D 预览、AI 快速生成场景/物体材质

### 蔡浩宇 LinkedIn 暴论（2024.8）

> "AIGC 已经完全改变了游戏开发。未来只有两类人做游戏有意义：(1) 顶尖 0.0001% 的天才精英团队创造前所未有的东西，(2) 99% 的业余爱好者为个人满足而创作。普通专业游戏开发者可能要考虑转行。"

→ 面试时可以提到这个观点，表达你对"AI 辅助而非替代"的理解，展示你关注公司动态

### Anuttacon（蔡浩宇离开米哈游后的 AI 创业公司）

- 首款产品 *Whispers from the Star*：100% 实时渲染 + LLM 驱动角色 + 多模态交互
- 核心技术：动态叙事分支（玩家对话实时改写后续剧情节点）、记忆向量更新
- 延迟掩盖：模拟"通信延迟"隐藏 AI 响应时间
- → 与你的 VN-Agent 方向高度相似，可以作为讨论话题

### 米哈游 AI 生态布局

| 维度 | 具体 |
|------|------|
| 自研大模型 | **Glossa**（2024.9 备案，定位：智能NPC/个性化对话/内容生产自动化） |
| 投资 | MiniMax（天使轮，持股~7%，2026.1 港股 IPO 市值 900亿+） |
| 合作 | Nvidia ACE（NPC 语音交互）、复旦 NLP 实验室（Agent Survey 论文） |
| 语音 AI | 逆熵AI：零样本声音克隆（15min原始音频→情感标注→批量TTS），MOS 4.5/5，92% 玩家分不出AI/真人 |
| 子公司 | 无定谷科技（注册资本 **5亿**，2025.7），秘法科技/原初海科技等 |

### 关键数据（面试引用）

| 指标 | 数值 | 来源 |
|------|------|------|
| 策划配置生成 | 2h → 5min（降 96%） | Echo 平台 |
| NPC 对话量 | 三月七 6.1 万条不重复对话 | 星穹铁道 |
| 对话延迟 | 380ms | 星穹铁道 NPC |
| 策划人力 | 5人月 → 2人周（降 80%） | 星穹铁道 NPC 剧情 |
| 留存提升 | +4.7% | AI NPC 功能 |
| 语音质量 | MOS 4.5/5，92% 无法分辨 | 逆熵AI / 未定事件簿 |
| 3D 建模 | 10 工作日 → 0.5-1 天（NeRF） | 美术管线 |

---

## 一、项目拷打（预计 30-40 min）

### 1.1 架构设计类（必问）

**Q: 为什么拆成 6 个 Agent 而不是一个大 prompt？**

- 每个 Agent 对应独立决策域（规划/创作/审核/视觉/音乐），prompt + output schema 不同
- 合并后 prompt 过长导致：① JSON 输出不稳定（格式错误率上升）② 注意力稀释，后面的指令被忽略
- Agent 解耦后可以独立选模型（Sonnet 做规划 vs Haiku 做审查），独立重试，独立测试
- **类比游戏管线**：跟游戏引擎的 pipeline 思路一样——场景管理、渲染、物理是独立子系统，不是一个巨型函数
- **类比米哈游 Echo 平台**：Echo 也是把不同工具（配置生成、测试、美术）拆成独立 Agent 挂载

**Q: 为什么选 LangGraph 而不是 LangChain 的 SequentialChain 或 CrewAI？**

- 需要**条件分支**（Reviewer 通过/不通过走不同路径）和**循环**（修订 loop），这是 DAG 拓扑，chain 无法表达
- LangGraph 的 StateGraph 原生支持 conditional_edges + 共享 state，比手写 while 循环更声明式、可观测
- CrewAI 更适合角色扮演式协作，不适合严格流程控制的生产管线

**Q: 资产阶段为什么并行？怎么做的故障隔离？**

- CharacterDesigner、SceneArtist、MusicDirector 无数据依赖（立绘不需要背景，BGM 不需要图片）
- `asyncio.gather(*tasks, return_exceptions=True)`：单个 Agent 抛异常不会中断其他两个
- 异常累积到 `state["errors"]`，最终报告给用户但不中断管线
- 串行 3T → 并行 max(T)，资产阶段耗时降为原来的 ~1/3

**Q: Director 为什么要拆成两步？**

- 单步生成：场景大纲 + 分支导航 + 角色 + BGM 四个维度同时输出，prompt 长、max_tokens 容易截断
- 两步：Step1 只生成场景大纲和角色（结构确定），Step2 在已有结构基础上补充分支关系和 BGM mood
- 还设计了截断修复：双策略 JSON salvage（反向扫描闭合 + 正向括号计数截断）→ LLM self-repair

**Q: 修订循环怎么防止无限循环？效果怎么样？**

- 硬上限 `max_revision_rounds=3`，超过后强制 proceed
- 条件函数 `_after_review()`：PASS → 资产/END，FAIL + rounds < 3 → Writer，rounds ≥ 3 → 强制前进
- 实测 7B 模型触发了完整 3 轮修订循环，结构校验最终 PASS，验证了循环机制的鲁棒性

### 1.2 RAG 优化类（核心亮点，面试官最可能深挖）

**Q: 怎么定位到生成瓶颈在上下文不足？**

排除法 + 数据驱动定位：

1. **观察 Reviewer 的 FAIL 分布**：结构问题（分支死胡同）由 4 类 BFS 校验 100% 拦截；剩余 FAIL 来自 LLM 质量审核
2. **排除 prompt 问题**：迭代多版 prompt，收益递减——说明不是指令不清
3. **排除模型能力问题**：换更强模型有改善但成本不可接受
4. **验证实验**：手动在 prompt 里塞一段真实对话示例 → 生成质量明显提升 → **确认是上下文不足**（Writer 没有"好的对话长什么样"的参考）
5. → 引入 RAG 自动化 few-shot 注入

> **注意**：这里的定性判断（"策略感低"）没有持久化的 Reviewer 评分日志佐证——`eval_ollama_results.json` 只记录了 `review_passed: false` 和 `revision_count: 3`，Reviewer 具体反馈文本未落盘。面试时应基于可验证数据（revision_count、review_passed、F1 对比）回答，不编造观测。

**Q: RAG 链路具体优化了哪些模块？**

三个阶段分别优化：

- **Query 构造**：纯场景描述检索 → 拼接 `"{description} | strategy: {label}"`（`writer.py:157`），让 embedding 向量同时编码语义内容和策略意图
- **检索排序**（`embedder.py:95-119`）：
  1. Over-retrieve：需要 k 条结果先取 5k 条候选（`fetch_k = min(k*5, len(sessions))`）
  2. FAISS IndexFlatIP 语义搜索：`normalize_embeddings=True` 后内积 = 余弦相似度
  3. 策略感知重排：`matched = [s for s in candidates if s.strategy == strategy]` 放前面，再截取 top-k
- **生成注入**（`writer.py:166-169`）：top-K 示例格式化为 few-shot block 注入 Writer prompt，配合 CoT 4 步推理（情感状态→策略引导→潜台词→角色声音）

> **重要细节**：FAISS 索引编码的是 `s.text`（完整 12 行对话），但 query 是 `scene.description`（短描述）。这存在语义空间 mismatch（短文本 vs 长文本），FAISS 的语义排序精度打折扣。**真正保证策略相关性的是后处理的硬性标签过滤，不是 FAISS 的语义分数。** 改进方案：对语料生成 description-level 摘要做索引，或引入 BM25+向量混合检索。

**Q: FAISS IndexFlatIP 是什么？为什么选它？**

FAISS（Facebook AI Similarity Search）的索引类型拆解：

| 部分 | 含义 |
|------|------|
| Flat | 不压缩不聚类，存原始向量，暴力遍历 |
| IP | Inner Product（内积），归一化后等价余弦相似度 |

选 Flat 的理由：1,036 条语料 × 384 维 ≈ 1.5MB 内存，暴力搜索 < 1ms。其他方案对比：

| 索引类型 | 原理 | 速度 | 精度 | 适用规模 |
|----------|------|------|------|----------|
| IndexFlatIP | 暴力内积 | O(N×d) | **100%** | < 10 万（本项目） |
| IndexIVFFlat | 先 K-Means 聚类，只搜最近几个簇 | 快 10-50× | ~95-99% | 10 万-1000 万 |
| IndexIVFPQ | 聚类 + 乘积量化压缩 | 快 100× | ~90-95% | 千万-亿 |
| IndexHNSWFlat | 层级图导航（跳表式） | 快 10-100× | ~99% | 10 万-5000 万 |

> **面试追问"如果语料到 100 万怎么办"**：→ IndexIVFFlat(nlist=1000, nprobe=50)，精度损失 < 3%；→ 超 1 亿换 Milvus/Pinecone 分布式向量数据库。

**Q: 为什么不用向量数据库（Pinecone/Weaviate）？**

- 1,036 条语料，FAISS 内存 < 10MB，精确搜索延迟 < 1ms
- 大型向量数据库在这个规模是 over-engineering，增加部署复杂度和成本
- 三级降级设计：FAISS → numpy 暴力搜索 → 标签过滤 fallback
- 如果语料规模到百万级才需要考虑分布式向量数据库

**Q: F1 只有 0.34，不高啊？**

- 这是 6 分类任务（随机基线 16.7%），且是 7B 本地模型（qwen2.5:7b），不是 GPT-4
- 重点不在绝对值，而在**方法论**：keyword baseline 0.21 → LLM zero-shot 0.34，提升 57%
- 单类数据：rupture 从 0.17→0.56（3 倍+），contrast 从 0.20→0.43（2 倍+），有明显文本特征的策略提升显著
- 如果换 Claude Sonnet 预计会有更大提升（但 100 条 API 调用 ≈ $2-5，评测预算需要控制）

> **澄清**：这个评测对比的是 keyword vs **LLM zero-shot**（不是 RAG）。`eval_ollama.py:37` 显式关闭了 RAG（`USE_SEMANTIC_RETRIEVAL=false`）。和 RAG 的关系是**间接的**：证明 LLM 能区分 6 种策略 → RAG 按策略标签过滤是有意义的。**没有直接评测"加 RAG vs 不加 RAG"的生成质量差异**，这是一个缺失的 A/B 实验。

**Q: 策略分类评测具体怎么做的？**

评测脚本 `scripts/eval_ollama.py`，用 qwen2.5:7b 本地模型跑：

1. 从 `data/final_annotations.csv` 加载 1,036 条人工标注语料（每条有 `predominant_strategy` gold label）
2. 随机采样 100 条（`random.sample(valid, sample_size)`）
3. 两个分类器分别跑：
   - **Keyword baseline**（`strategy_eval.py:17-36`）：每种策略 5-6 个关键词，数匹配数量取最多的
   - **LLM zero-shot**（`eval_ollama.py:77-87`）：system prompt = "你是策略分类器，只回答策略名"，把对话喂给 LLM
4. 对比 gold label 计算每类 Precision/Recall/F1，macro F1 = 6 类平均

用 macro F1 而非 accuracy 的原因：6 类样本分布不均（reveal 30 条 vs contrast 10 条），macro F1 对每个类别一视同仁。

**Q: RAG 效果怎么评估？**

当前做了**可行性验证**（策略分类 F1），缺少**直接效果对比**。完整评测方案：

```
控制变量: 同一 theme、同一模型、同一 prompt 模板
实验组:   Writer prompt 注入 RAG 检索的 2 条 few-shot 示例
对照组:   Writer prompt 不注入任何示例

评估方式（由弱到强）:
① LLM-as-Judge: 用 Reviewer 5 维评分，30+ theme，paired t-test 检验显著性
② 策略一致性: 对生成对话跑策略分类器，检查是否和 Director 指定策略一致
③ 人工盲评: 3 个评估者打分，Cohen's Kappa 确认一致性
```

没做的原因：30 theme × 2 组 × ~6 次 API ≈ 360 次调用，Claude Sonnet ≈ $15-20，且 LLM 生成有随机性需多次重复。

> **面试话术**："策略分类 F1 验证了 RAG 链路的可行性前提（LLM 理解策略差异），但缺少'加 RAG vs 不加'的 A/B 对比。如果有更多预算，第一个要补的就是这个实验。"

### 1.3 工程实践类

**Q: Tool Calling 和正则提取 JSON 有什么区别？为什么要换？**

1. 类型安全：Pydantic schema 自动校验字段类型和约束
2. 鲁棒性：LLM 原生 function calling 协议，不需要手写正则去匹配 ````json` 块
3. 可扩展：新工具只需定义 Pydantic model，不需改解析逻辑
4. 保留了 regex fallback 降级路径（不支持 tool calling 的模型 / mock 模式）

**Q: 多模型路由怎么设计的？降本 73% 怎么算的？**

- 6 个 Agent 各自可配模型：Director/Writer 用 Sonnet（需要复杂推理），Reviewer/Asset Agents 用 Haiku（简单结构化任务）
- Sonnet: $3/$15 per MTok，Haiku: $0.80/$4 per MTok
- 全 Haiku 模式成本约为全 Sonnet 的 27%（降本 73%）
- 默认路由（2 Sonnet + 4 Haiku）降本约 20%，保留关键节点质量
- **类比米哈游场景**：Echo 平台的不同工具也需要匹配不同复杂度的模型，不可能全用最贵的

**Q: 测试和 CI 怎么做的？**

174 个 test 函数，21 个测试文件，三层测试策略：

**Mock LLM 零成本测试**（`test_pipeline.py:100-132`）：
- `mock_ainvoke` fixture 通过 `mocker.patch` 替换所有 Agent 的 `ainvoke_llm`
- 根据 system prompt 关键词和 caller 标签分发预定义 JSON 响应
- 效果：全部测试零 API 调用，毫秒级完成

**`@pytest.mark.slow` 隔离真实 API 测试**（`test_real_api.py`）：
- 标记 `@pytest.mark.slow` + `skipif(not ANTHROPIC_API_KEY)`
- CI 用 `-m "not slow"` 跳过；开发者手动 `pytest -m slow` 执行

**GitHub Actions CI 流水线**（`.github/workflows/ci.yml`）：
```
Push/PR to main → Lint (ruff check) → Type check (mypy) → Test + Coverage (--cov-fail-under=60)
```

**Docker 两阶段构建**：Stage1 node:20 编译 React 前端 → Stage2 python:3.11 + 前端静态文件，最终镜像无 node_modules

**Semaphore 并发控制**（`app.py:81-95`）：
- `asyncio.Semaphore(3)` 限制同时最多 3 条 pipeline 并行
- 每个 pipeline ~6-10 次 API 调用 + Assets 阶段内部 gather 并行，不限制会触发 rate limit
- `async with sem:` 协程级阻塞，不占线程，等待时让出事件循环

### 1.4 游戏场景延伸（JD 核心关注点，主动往这里引）

**Q: 这个项目跟游戏开发有什么关系？**

- VN-Agent 本质上就是一个**游戏内容生产管线**：从故事主题到可运行的 Ren'Py 游戏，覆盖了剧情、美术、音乐的全流程
- 核心思路可迁移到游戏研发：
  - AI 生成策划配置（类似 Director）→ 米哈游 Echo 的配置生成工具
  - AI 审查代码/资源一致性（类似 Reviewer）→ 米哈游的代码审查需求
  - AI 批量生成美术资产（类似 Asset Agents）→ 米哈游的材质/立绘生成
- 修订循环机制可用于任何"生成→检查→修复"的自动化流程

**Q: 如果让你设计 Echo 平台上的一个新 Agent 工具，你会怎么做？**

以"策划数值配置自动生成"为例（米哈游已有类似工具，从 2h 降到 5min）：

```
架构：
1. Planner Agent：解析策划自然语言描述，识别配置类型（技能/装备/关卡）
2. Generator Agent：根据规划 + 历史配置 RAG 检索，生成配置 JSON
3. Validator Agent：
   - 结构校验：字段完整性、类型合法性（确定性规则）
   - 平衡性校验：数值范围、与现有配置的兼容性（LLM 判断 + 规则兜底）
4. 修订循环：Validator FAIL → Generator 带反馈重试（max 3 rounds）

关键设计：
- Tool Calling 保证输出严格匹配配置 schema
- RAG 检索历史同类配置作为 few-shot（避免生成偏离游戏平衡）
- 多模型路由：Generator 用强模型（质量），Validator 用轻量模型（速度/成本）
```

**Q: 如果让你用 Agent 做游戏自动化测试（类似"杯中逸事"），怎么设计？**

```
1. Test Planner Agent：分析游戏玩法规则 + 历史 bug 数据库（RAG），生成测试策略
2. Test Executor：通过游戏 API/脚本控制角色执行测试用例
3. Result Analyzer Agent：分析执行结果，分类 bug 严重等级
4. Feedback Loop：Analyzer 发现的问题反馈给 Planner 补充用例

核心挑战：
- 游戏状态空间大 → 需要智能剪枝（用 LLM 判断高风险路径）
- 确定性校验优先（碰撞检测、边界越界），LLM 判断兜底（视觉效果、UX）
- 实时性要求 → 小模型本地推理 + 预计算
```

---

## 二、手撕 / AI 受搓 Demo（预计 20-30 min）

### 2.1 代码题

**题目 1：实现 Agent 修订循环（最高概率考点）**

```python
import asyncio
from pydantic import BaseModel

class ReviewResult(BaseModel):
    passed: bool
    feedback: str

async def generate(prompt: str, feedback: str = "") -> str:
    """调用 LLM 生成内容"""
    full_prompt = prompt
    if feedback:
        full_prompt += f"\n\n修订要求：{feedback}"
    # response = await llm.ainvoke(full_prompt)
    # return response.content
    ...

async def review(content: str) -> ReviewResult:
    """调用 LLM 审查内容"""
    # response = await llm.ainvoke(f"审查以下内容：{content}")
    # return ReviewResult.model_validate_json(response.content)
    ...

async def generate_with_revision(prompt: str, max_rounds: int = 3) -> str:
    """生成→审查→修订循环"""
    content = await generate(prompt)
    for round_num in range(max_rounds):
        result = await review(content)
        if result.passed:
            return content
        content = await generate(prompt, feedback=result.feedback)
    return content  # 超过轮次强制返回
```

**题目 2：实现语义检索 top-k**

```python
import numpy as np

def semantic_search(
    query_embedding: np.ndarray,     # (d,)
    corpus_embeddings: np.ndarray,   # (n, d)
    k: int = 3
) -> list[int]:
    """返回 top-k 最相似的文档索引"""
    # 归一化（内积 = 余弦相似度）
    query_norm = query_embedding / np.linalg.norm(query_embedding)
    corpus_norm = corpus_embeddings / np.linalg.norm(
        corpus_embeddings, axis=1, keepdims=True
    )
    scores = corpus_norm @ query_norm  # (n,)
    return np.argsort(scores)[-k:][::-1].tolist()
```

**题目 3：BFS 检查图可达性（Reviewer 的核心逻辑）**

```python
from collections import deque

def check_reachability(
    scenes: dict[str, list[str]],  # scene_id → [branch_target_ids]
    start: str
) -> list[str]:
    """返回从 start 不可达的场景 ID 列表"""
    visited = set()
    queue = deque([start])
    visited.add(start)
    while queue:
        node = queue.popleft()
        for neighbor in scenes.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return [s for s in scenes if s not in visited]
```

**题目 4：实现 Tool Calling schema 绑定（Agent 方向核心）**

```python
from pydantic import BaseModel, Field

class SearchTool(BaseModel):
    """搜索信息"""
    query: str = Field(description="搜索关键词")

class CalculatorTool(BaseModel):
    """数学计算"""
    expression: str = Field(description="数学表达式")

def build_tools_schema(tools: list[type[BaseModel]]) -> list[dict]:
    """将 Pydantic 模型转为 OpenAI function calling 格式"""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.__name__,
                "description": tool.__doc__,
                "parameters": tool.model_json_schema(),
            },
        }
        for tool in tools
    ]

def parse_tool_call(
    response: dict, tools: list[type[BaseModel]]
) -> BaseModel:
    """解析 LLM 返回的 tool call，实例化为 Pydantic 对象"""
    tool_map = {t.__name__: t for t in tools}
    call = response["tool_calls"][0]
    schema_cls = tool_map[call["function"]["name"]]
    return schema_cls.model_validate_json(call["function"]["arguments"])
```

**题目 5：asyncio 并行执行 + 故障隔离**

```python
import asyncio

async def run_parallel_with_isolation(
    tasks: list[tuple[str, callable]]  # [(name, coroutine_fn), ...]
) -> dict[str, any]:
    """并行执行多个任务，单个失败不影响其他"""
    results = {}
    errors = []

    coros = [fn() for name, fn in tasks]
    outcomes = await asyncio.gather(*coros, return_exceptions=True)

    for (name, _), outcome in zip(tasks, outcomes):
        if isinstance(outcome, Exception):
            errors.append(f"{name}: {outcome}")
        else:
            results[name] = outcome

    return {"results": results, "errors": errors}
```

### 2.2 现场 Demo / AI 编程能力展示

JD 明确要求："借助 AI 编程工具提升开发效率，完成原型开发"

**准备展示的能力**：
- 用 Claude Code / Cursor 快速搭建 Agent 原型
- 展示如何用 AI 辅助调试、写测试、重构代码
- 关键：不是展示"你会用 AI"，而是展示你能**指导 AI 做正确的事**（prompt engineering + 工程判断力）

**可能的 Demo 场景**：
1. "现场写一个 Agent 帮策划自动生成怪物配置表"
2. "写一个 LLM 代码审查 Agent，输入 diff 输出审查意见"
3. "实现一个简单的 RAG pipeline，从文档中检索回答问题"

### 2.3 系统设计题

**"设计一个 AI 驱动的游戏配置生成系统"（贴近米哈游 Echo 平台）**

```
输入：策划自然语言描述（"给主角加一个随机触发的回复效果"）
输出：符合游戏引擎 schema 的 JSON 配置

架构：
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Parser     │ →   │  Generator  │ ←→  │  Validator   │  (修订循环)
│  理解意图     │     │  生成配置    │     │  校验合法性   │
└─────────────┘     └─────────────┘     └─────────────┘
                          ↑
                    ┌─────────────┐
                    │  RAG 检索    │  (历史同类配置作为 few-shot)
                    │  FAISS 索引  │
                    └─────────────┘

关键设计点：
1. Tool Calling 保证输出严格匹配配置 schema（不用正则解析）
2. RAG 检索历史配置避免数值偏离平衡
3. Validator 双层校验：确定性规则（字段/类型/范围）+ LLM 语义判断（合理性）
4. 多模型路由：Generator 用强模型，Validator 用轻量模型
5. 人在回路：Validator PASS 后仍需策划确认（最终决策权在人）
```

---

## 三、八股知识（预计 20-30 min）

### 3.1 LLM 基础

**Q: Transformer 的核心机制？**
- Self-Attention：Q·K^T/√d_k → softmax → V，每个 token 关注所有其他 token
- Multi-Head Attention：多组 QKV 投影，捕获不同子空间的关系
- Position Encoding：attention 本身无序，需要位置编码引入顺序信息（正弦/RoPE/ALiBi）
- FFN + LayerNorm + Residual Connection

**Q: Q·K^T/√d_k 除的是啥？**
- √d_k = Key 向量维度的平方根。Q 和 K 做点积，d_k 项求和后方差 = d_k
- 如果 d_k=512，点积值域约 [-50, +50]，Softmax 饱和（几乎全部概率集中在最大值），梯度趋近 0
- 除以 √512 ≈ 22.6 后值域缩到 [-2, +2]，Softmax 分布平滑，梯度正常流动
- **一句话：防止点积随维度增大而膨胀，导致 Softmax 饱和和梯度消失**

**Q: KV Cache 是什么？**
- 自回归生成每步要和所有历史 token 算 attention。不缓存则每步重算所有历史 K、V → O(N²)
- KV Cache 把每步算过的 K 和 V 存下来，下一步只算新 token 的 Q/K/V → O(N)
- 只缓存 K 和 V 不缓存 Q：当前 token 的 Q 用完就不需要了，历史的 K/V 每步都被用到
- 内存开销：LLaMA-7B 序列 2048 时 ≈ 1GB（32 层 × 2(K+V) × 4096 × 2048 × 2B）
- **一句话：空间换时间，自回归从 O(N²) 降到 O(N)，代价是显存随序列长度线性增长**

**Q: LLM 推理过程（自回归生成）？**
- **Prefill 阶段**：并行处理所有 prompt tokens，生成 KV Cache
- **Decode 阶段**：逐 token 生成，每步只计算新 token 的 attention（复用 KV Cache）
- 采样策略：Temperature（平滑分布）、Top-p（nucleus sampling）、Top-k
- KV Cache 是推理加速的关键，也是显存瓶颈

**Q: Top-P 和 Top-K 分别是什么？**
- **Top-K**：只保留概率最高的 K 个候选词，其余砍掉。问题：K 固定，模型很确定时仍保留 K 个噪声词
- **Top-P（Nucleus Sampling）**：按概率从高到低累加，到达阈值 P 就截断。自适应：模型确定时候选少，犹豫时候选多
- 和 Temperature 的关系：Temperature 在前（调分布尖锐度），Top-K/P 在后（截断采样），三者正交可组合
- 本项目 `LLM_TEMPERATURE=0.3`（低随机性）+ 默认 top-p
- **一句话：Top-K 固定数量截断，Top-P 按累积概率自适应截断，Top-P 更好因为根据分布形状动态调整**

**Q: Token 和 Tokenization？**
- BPE（Byte Pair Encoding）：从字符级开始，迭代合并最频繁的 pair
- 中文通常 1-2 个 token/字，英文约 0.75 token/word
- Context window = 最大 token 数（Claude: 200K，GPT-4o: 128K）

**Q: 什么是 Hallucination？怎么缓解？**
- LLM 生成看起来合理但事实错误的内容
- 缓解：① RAG 提供事实基础 ② Tool Calling 获取实时信息 ③ CoT 增加推理步骤 ④ Reviewer/Verifier 后验检查
- VN-Agent 做法：Reviewer 结构校验（确定性）+ LLM-as-Judge（语义）双层保障

### 3.2 Agent 技术（JD 核心，必考）

**Q: 什么是 AI Agent？和普通 LLM 调用有什么区别？**
- Agent = LLM + 规划能力 + 工具使用 + 记忆
- 普通调用：输入→输出，单轮无状态
- Agent：感知→规划→行动→观察→规划...的循环，能自主完成多步任务
- 核心价值：**工作流设计能力**——把复杂任务拆解成合理组件，组装成稳定流程

**Q: 主流 Agent 框架和范式？**

| 范式 | 特点 | 适用场景 |
|------|------|---------|
| **ReAct** | Reasoning + Acting 交替循环 | 通用问答、工具使用 |
| **Plan-and-Execute** | 先规划全局，再逐步执行 | 复杂多步任务（VN-Agent Director） |
| **Multi-Agent** | 多个专业 Agent 协作 | 生产管线（VN-Agent 整体架构） |
| **Reflection** | 生成→自我反思→改进 | 代码生成、写作（VN-Agent Writer↔Reviewer） |

| 框架 | 协作模式 | 可控性 | 适用场景 |
|------|---------|--------|---------|
| **LangGraph** | 显式有向图编排，conditional edges + 共享状态 | 最高 | 流程确定的生产管线（VN-Agent 用的） |
| **CrewAI** | 角色扮演（role+goal+backstory），sequential 或 hierarchical | 中等 | 创意协作、内容生产 |
| **AutoGen（微软）** | 多轮对话式群聊，LLM 选下一个发言者（auto 模式） | 低 | 研究探索、需要人介入的场景 |
| **OpenAI Swarm** | 极简 handoff 函数传递控制权，无图无状态机 | 中等 | 客服路由、快速原型（实验性质） |
| **AutoGPT** | 单 Agent ReAct 循环（Think→Act→Observe），完全自主 | 最低 | Demo 展示（生产中几乎没人用，容易跑偏/死循环） |
| **MetaGPT** | 模拟软件公司 SOP（PM→Architect→Engineer→QA），传递结构化文档 | 高 | 软件开发自动化 |

> **AutoGen 发言选择**：GroupChat 里用额外一次 LLM 调用决定"谁下一个说话"。这是不可控的根源——可能选错人、死循环、跳过关键角色。自定义 `speaker_selection_method` 可以硬编码路由，但本质上退化成了 LangGraph 的 conditional edges。
>
> **MetaGPT 核心洞察**：Agent 间传递结构化文档比自然语言对话更可靠。VN-Agent 借鉴了这个思想——Agent 间传的是 VNScript JSON，不是聊天消息。
>
> **选 LangGraph 的理由**：VN 生成是流程确定、需要条件分支和循环重试的任务（Director→Writer→Reviewer→可能打回），需要显式图编排和共享状态，不是对话式协作（AutoGen）或角色扮演（CrewAI）能很好控制的。

**Q: Tool Calling / Function Calling 原理？**
- LLM 训练时学习了何时调用工具、如何构造参数
- 流程：用户请求 → LLM 判断需要工具 → 输出结构化 tool call（JSON）→ 框架执行 → 结果返回 LLM → 继续生成
- 优势：比正则解析更可靠，有 schema 约束，类型安全

**Q: Agent 的 Memory 机制？**
- **Short-term**：对话上下文（context window 内）
- **Long-term**：向量数据库存储历史交互，检索相关记忆
- **Working memory**：当前任务状态（LangGraph 的 AgentState）
- **Episodic**：特定事件记忆（帕姆AI助手记住玩家偏好就是这个）

**Q: 多 Agent 系统的协调模式？**
- **管道式**（Pipeline）：A→B→C 顺序执行（VN-Agent 主流程）
- **并行式**：多个 Agent 同时工作（VN-Agent 资产阶段）
- **对抗式**：Generator + Critic 互相博弈（VN-Agent Writer↔Reviewer）
- **层级式**：Manager 分配任务给 Workers

### 3.3 RAG 技术

**Q: RAG 完整链路？**

```
离线：文档 → 分块(Chunking) → 嵌入(Embedding) → 索引(FAISS/向量DB)
在线：查询 → Query改写 → 嵌入 → 检索(Retrieval) → 重排(Reranking) → 生成(Generation)
```

**Q: 检索质量差怎么排查？（展示诊断方法论）**

```
Step 1: 看 Recall@K — 如果相关文档不在 top-K 里，是召回问题
  → Query 改写（HyDE/Multi-Query）/ 混合检索（BM25+向量）/ 调 chunk 大小
Step 2: 看 Precision@K — 如果 top-K 里噪声多，是排序问题
  → Cross-encoder 重排 / 策略过滤（VN-Agent 的做法）
Step 3: 看最终生成质量 — 如果检索对了但生成差，是注入问题
  → 调 few-shot 格式 / 加 CoT / 限制 context 长度避免干扰
```

**Q: FAISS 索引类型选择？**

| 索引 | 原理 | 速度 | 精度 | 适用规模 |
|------|------|------|------|----------|
| `IndexFlatIP` | 暴力内积（归一化后=余弦） | O(N×d) | **100%** | < 10 万（VN-Agent 用这个） |
| `IndexFlatL2` | 暴力欧氏距离 | O(N×d) | 100% | < 10 万 |
| `IndexIVFFlat` | K-Means 聚类，只搜最近 nprobe 个簇 | 快 10-50× | ~95-99% | 10 万-1000 万 |
| `IndexIVFPQ` | 聚类 + 乘积量化（384维→48字节） | 快 100× | ~90-95% | 千万-亿 |
| `IndexHNSWFlat` | 层级图导航（多层跳表式逼近） | 快 10-100× | ~99% | 10 万-5000 万 |

"精确"= Flat = 暴力遍历，和库里每个向量都算一遍距离。"近似"= IVF/HNSW，跳过大部分向量，可能漏掉真正最近的。

L2 vs IP vs 余弦：归一化后三者等价（`L2² = 2 - 2·IP`），选哪个都一样。

**Q: Embedding 模型怎么选？**
- 通用英文：`all-MiniLM-L6-v2`（384维，快速）← VN-Agent 用的
- 通用高精度：`BGE-large`（1024维，MTEB 高分）
- 中文：`bge-large-zh`、`text2vec-base-chinese`
- 选择因素：维度（存储/速度）、语言覆盖、任务匹配度、推理成本

### 3.4 Prompt Engineering

**Q: 常用 prompt 技巧？**
- **Few-shot**：给示例，让 LLM 模仿格式和风格
- **Chain-of-Thought**：分步推理（"Let's think step by step"）
- **System prompt**：设定角色和约束
- **Structured output**：要求输出 JSON/YAML + schema 约束
- **Self-consistency**：多次采样取多数投票

**Q: 怎么评估 LLM 输出质量？**
- **自动评估**：BLEU/ROUGE（参考匹配）、BERTScore（语义相似度）
- **LLM-as-Judge**：用强模型打分（VN-Agent 的 5 维度 rubric）
- **人工评估**：金标准但成本高
- **任务特定**：分类用 F1、生成用困惑度、结构用确定性校验

### 3.5 游戏 + AI 结合（加分项，展示 JD 理解）

**Q: AI Agent 在游戏开发中的应用场景？**

| 场景 | 具体应用 | 米哈游实例 | VN-Agent 类比 |
|------|---------|-----------|--------------|
| 策划配置 | 自然语言→游戏配置 JSON | Echo 配置生成（2h→5min） | Director 规划 |
| 代码审查 | 分析 diff→检查规范/bug | JD 明确要求 | Reviewer 审查 |
| 自动化测试 | AI 控制角色测试玩法 | 杯中逸事 | Reviewer BFS |
| 美术资产 | 批量生成立绘/材质/场景 | Echo 材质生成、2D→3D | Asset Agents |
| NPC 对话 | 动态生成不重复对话 | 三月七 6.1万条 | Writer + RAG |
| 语音合成 | 零样本声音克隆 | 逆熵AI（MOS 4.5） | MusicDirector |

**Q: AI 在游戏中的挑战？**
- **延迟**：游戏实时性要求高 → 预生成+缓存+小模型（米哈游 NPC 380ms）
- **一致性**：多次生成不一致 → 结构化输出+seed+确定性校验
- **成本**：大量 API 调用 → 多模型路由、本地部署、缓存
- **安全**：玩家 prompt injection → 输入过滤+输出审核
- **可控性**：纯 LLM 不可预测 → 规则兜底+人在回路

### 3.6 工程基础

**Q: asyncio 核心概念？**
- Event loop：单线程事件循环，调度协程
- `async/await`：定义和挂起协程
- `asyncio.gather()`：并发执行，`return_exceptions=True` 做故障隔离
- `asyncio.Semaphore`：控制并发数量（VN-Agent Web API 用了）

**Q: asyncio.Semaphore 在项目里怎么用的？**

```python
# app.py — 限制同时最多 3 条 pipeline 并行
_semaphore = asyncio.Semaphore(3)

async def _run_job(job_id, req, output_dir):
    async with _get_semaphore():  # 进入：计数-1，计数=0则等待
        # ... 跑整个 pipeline
    # 退出：计数+1，唤醒等待中的任务
```

为什么限制 3：每个 pipeline ~6-10 次 API 调用 + Assets 阶段 gather 并行，10 个用户同时提交可能瞬间 100+ 并发请求打 API → 触发 rate limit → 全部 429 失败。Semaphore 是协程级阻塞（不占线程），比 threading.Lock 更轻量。Lock 是 Semaphore(1) 的特例。

**Q: Pydantic v2 vs v1？**
- Rust 核心（pydantic-core），验证速度快 5-50x
- `model_validate()` 替代 `parse_obj()`，`model_dump()` 替代 `dict()`
- `model_json_schema()` 生成 JSON Schema（Tool Calling 需要）

**Q: FastAPI 异步机制？**
- ASGI（Starlette），原生支持 `async def` 路由
- 后台任务：`asyncio.create_task()` fire-and-forget
- 中间件、依赖注入、自动 OpenAPI 文档

---

## 四、面试策略

### 4.1 STAR 框架回答项目问题

- **Situation**：AI 视觉小说生成系统，要求端到端自动化
- **Task**：设计多 Agent 工作流，解决 LLM 输出不稳定、生成质量差的问题
- **Action**：拆解为 6 Agent DAG + RAG 优化 + 结构校验闭环
- **Result**：端到端生成可运行游戏，F1 提升 57%，降本 73%，140+ 测试覆盖

### 4.2 主动往游戏场景引导

开场就说：
> "我注意到岗位要求改进 AI Agent 在游戏研发管线中的应用。我的项目做的就是这件事——把一个多步骤的游戏内容生产流程（剧情→美术→音乐→可运行游戏），用 Agent 架构端到端自动化。"

每个技术点都往游戏场景类比：
- 修订循环 → "类似你们杯中逸事的测试→反馈→重测循环"
- RAG few-shot → "类似你们用历史配置作为参考来生成新配置"
- 多模型路由 → "不同任务用不同复杂度的模型，和 Echo 平台的思路一样"

### 4.3 展示你了解米哈游

在合适的时机自然地提到：
- "我看到你们 Echo 平台已经实现了策划配置从 2 小时降到 5 分钟，我的项目也做了类似的——用 RAG 和结构化输出保证生成质量..."
- "蔡浩宇说 AIGC 已经完全改变了游戏开发，我认同 AI 会极大提效，但关键是怎么保证生成质量和可控性，这也是我项目重点解决的问题..."
- "帕姆AI助手的方向很有意思——从工具辅助到玩家体验创新，这也是 AI 在游戏中两条不同的路线..."

### 4.4 准备的反问

- "Echo 平台目前在游戏研发管线中覆盖了哪些环节？团队接下来最想突破的是哪个方向？"
- "你们在 Agent 输出可靠性上是怎么做保障的？有没有类似我项目里 Reviewer 结构校验的机制？"
- "Glossa 大模型目前在内部的使用情况怎么样？是否有计划在更多场景落地？"
- "团队对本地小模型推理 vs 云端 API 的取舍是什么考虑？"

---

## 五、关键文件索引（复习代码用）

| 文件 | 内容 | 面试关联 |
|------|------|---------|
| `src/vn_agent/agents/graph.py` | DAG 编排、条件边、并行资产 | 架构设计 |
| `src/vn_agent/agents/director.py` | 两步规划、截断修复 | LLM 工程 |
| `src/vn_agent/agents/writer.py` | RAG 注入、few-shot、对话生成 | RAG 优化 |
| `src/vn_agent/agents/reviewer.py` | BFS 校验、5 维度 rubric | 质量保障 |
| `src/vn_agent/services/tools.py` | Tool Calling + Pydantic bind_tools | 结构化输出 |
| `src/vn_agent/eval/strategy_eval.py` | F1 评测、keyword baseline | 评估方法论 |
| `src/vn_agent/eval/embedder.py` | FAISS 索引、语义检索 | RAG 技术 |
| `src/vn_agent/config.py` | 多模型路由配置 | 成本优化 |
| `src/vn_agent/web/app.py` | FastAPI + Semaphore + Job Store | 工程实践 |
| `docs/RESUME.md` | 简历描述 + 数据真实性自查 | 面试前通读 |

---

## 六、深挖问答实录（对话中积累的细节）

### 6.1 DAG 是什么意思？

DAG = **Directed Acyclic Graph（有向无环图）**。

- **有向**：边有方向，A→B 表示 A 完成后才能执行 B
- **无环**：不能绕回起点

在 VN-Agent 里描述 Agent 之间的执行顺序和依赖关系。Reviewer↔Writer 的修订循环严格来说是有环的，但通过 `max_revision_rounds=3` 硬上限保证终止性，等价于展开成最多 3 层的 DAG。LangGraph 内部也是这么处理的——conditional edge 不是图回边，而是状态机的条件转移。

**为什么不直接说"顺序执行"**：因为它有条件分支（Reviewer PASS/FAIL 走不同路径）、并行扇出（3 个资产 Agent 同时跑）、受控循环（修订 loop），这些是 DAG 拓扑而非简单链。

### 6.2 并行 + 故障隔离具体含义

**并行**：CharacterDesigner、SceneArtist、MusicDirector 无数据依赖，用 `asyncio.gather` 同时启动，总耗时从串行 3T 降为 max(T)。

**故障隔离**：核心是 `return_exceptions=True` 这一个参数。

- **没有它**：SceneArtist 调图片 API 超时 → gather 直接崩 → 另外两个的结果也丢了 → 整个管线失败
- **有了它**：异常作为返回值放进 results 列表 → 代码逐个检查 `isinstance(r, Exception)` → 成功的合并结果，失败的记到 errors → 管线继续

用户拿到的游戏：立绘有、BGM有、背景缺失用占位图 → **局部降级优于全局失败**。

### 6.3 六个 Agent 详细分工、协作与不足

#### 各 Agent 详细工作流

**Director（规划大脑）** — 从用户主题生成故事骨架

- **两步法**：Step1 生成场景大纲+角色（不含分支/音乐）→ Step2 在已有结构上补充 next_scene_id、branches、music_mood → `_merge_outline_details()` 合并并过滤无效引用
- **截断修复**：双策略 JSON salvage（反向扫描闭合 + 正向括号计数截断）→ 失败则 LLM self-repair（把报错喂回 LLM）
- **Checkpoint**：完成后立即存 `vn_script.json` + `characters.json`，Director 最贵，后面崩了可以 `--resume` 跳过
- **小模型适配**：检测模型名含 qwen/llama 等 → 用简化 prompt

**Writer（创作引擎）** — 为每个场景填写对话

- 加载 RAG 语料（可选）→ 构建/加载 FAISS 嵌入索引
- 遍历每个 scene，构建 prompt：场景描述 + 角色信息 + 叙事策略 + 修订反馈 + RAG few-shot 示例
- Query 构造：`"{scene.description} | strategy: {label}"` 同时覆盖语义和策略维度
- 中文检测：主题含中文字符 → 追加"请用中文写对话"
- 三级对话解析：①匹配 ````json [...]```` 代码块 ②raw_decode 从第一个 `[` ③全文 json.loads ④占位符兜底
- 约束执行：< min_lines → 补占位行，> max_lines → 截断

**Reviewer（质量守门人）** — 双层检查决定通过或打回

- **Layer 1 结构校验（零 LLM 调用）**：start_scene 存在、branch 引用合法、BFS 可达性、角色一致性 → 任一不通过直接 FAIL
- **Layer 2 LLM 质量评分（可跳过）**：叙事连贯性、角色一致性、节奏感、分支有意义性 → 首行 PASS 则通过
- **策略一致性检查（非阻塞警告）**：关键词匹配，只记警告不影响 PASS/FAIL

**CharacterDesigner（角色视觉）** — 所有角色并行 `asyncio.gather`

- 优先 Tool Calling（`bind_tools([VisualProfileResult])`）→ 失败降级为自由文本 JSON 提取
- 生成 neutral/happy/sad 三个表情立绘
- 每个角色独立故障隔离

**SceneArtist（场景美术）** — 按 background_id 去重后并行

- 多个场景共享同一个背景 → 只生成一次
- 优先 Tool Calling（`bind_tools([BackgroundPrompt])`）→ 失败降级
- 生成的 prompt 写回所有共享该 bg_id 的 scene

**MusicDirector（音乐编排）** — 最简单的 Agent（68 行，无 LLM 调用）

- 遍历场景，读 music.mood → 相邻场景 mood 相同则复用同一首曲子 → 不同则 `resolve_music_cue()` 从音乐库匹配

#### 协作机制

所有 Agent 通过 **AgentState 共享字典**协作——每个 Agent 读它需要的字段，写它负责的字段，LangGraph 自动 merge：

```
theme          ← 用户输入，全程不变
vn_script      ← Director 创建 → Writer 填对话 → SceneArtist 填背景 → MusicDir 填音乐
characters     ← Director 创建 → CharDesigner 填视觉
review_feedback ← Reviewer 写反馈 → Writer 读反馈修改
revision_count  ← Reviewer 每轮 +1 → graph 判断是否继续循环
errors         ← 所有 Agent 累积非致命错误
```

#### 已知不足

1. **Writer 串行写场景**：`for scene in scenes: await _write_scene()` 逐场景串行，但代码里其实没有传递前面场景的对话结果，理论上可以分组并行
2. **Reviewer 反馈太粗**：全场景统一反馈，问题可能只在某个场景，其他场景被迫看无关反馈 → 应做 per-scene 反馈
3. **质量评分过于粗粒度**：LLM 质量检查只看首行是否 PASS，没有按 5 维度拆分结构化评分 → 应用 Tool Calling 返回每个维度分数
4. **策略一致性检查太弱**：只是关键词匹配，不是语义判断 → 应用 embedding 相似度或 LLM 判断
5. **没有跨场景一致性检查**：不检查角色状态跨场景的矛盾（如角色在场景 3 死了又在场景 5 出现）→ 应维护"世界状态"追踪

> 面试时主动提这些不足，展示反思能力。话术："如果再做一版，我会优先改 Writer 并行和 Reviewer per-scene 反馈这两个。"

### 6.4 Build vs Buy 选型决策全览

#### 用了现成的，为什么选它

| 组件 | 选了 | 不选什么 | 核心理由 |
|------|------|---------|---------|
| 图编排 | **LangGraph** | CrewAI / SequentialChain / AutoGen | 需要条件分支+循环的 DAG 拓扑，chain 无法表达 |
| 向量索引 | **FAISS IndexFlatIP** | Pinecone / Weaviate / Milvus / Chroma | 1K 语料不需要分布式，精确搜索 <1ms，pip install 即用 |
| Embedding | **all-MiniLM-L6-v2** | BGE-large / ada-002 / bge-large-zh | 384 维够用、80MB 模型、本地编码快、语料是英文 |
| LLM 调用 | **LangChain** | 直接用 Anthropic/OpenAI SDK | 一个 `ainvoke()` 统一 4 个 provider，`bind_tools()` 抹平 tool calling 协议差异 |
| 持久化 | **SQLite** | PostgreSQL / Redis / 内存 dict | 零部署（Python 标准库自带），单文件，进程重启不丢数据 |
| 重试 | **tenacity** | 手写 for 循环 | 指数退避 + 选择性重试（只重试暂态错误）手写容易出 bug |

#### 自己造的，为什么不用现成的

| 组件 | 为什么自己写 |
|------|-------------|
| **JSON 截断修复** | 场景太特殊：max_tokens 截断 + Unicode，标准 json_repair 库假设输入是完整但格式错误的 JSON |
| **Tracing（117 行）** | OpenTelemetry 需要 collector 服务 + 后端，LangSmith 要注册云服务。单机 CLI 工具只需要输出 trace.json |
| **Token Tracker（77 行）** | LangChain callback 绑在 chain 上，不适合跨多 Agent 全局统计。单例模式任何地方一行 `tracker.add()` |
| **BFS 结构校验** | 确定性问题用代码：100% 准确、0 延迟、0 成本。LLM 做图可达性判断不可靠 |
| **对话解析三级降级** | 需要"从混合文本中定位 JSON"，不是修复格式错误。不同 LLM 输出格式差异大 |
| **策略关键词检查** | 快速粗筛（zero-cost），非阻塞警告。用 LLM 更准但要多一次调用，当前选择成本优先 |

**面试话术**：
> "我的选型原则是匹配规模和场景。千条语料用 FAISS 不用 Pinecone，单机工具用 SQLite 不用 PG，能用确定性代码解决的不用 LLM。自己写的要么是场景太特殊没有现成库，要么是现成方案太重，要么是确定性逻辑不该交给概率模型。"

### 6.5 Tool Calling 深入解析

#### 本质区别

- **传统方式**：prompt 里写"请返回 JSON" → LLM 返回自由文本（可能夹废话）→ 正则提取 → json.loads → 祈祷格式没问题
- **Tool Calling**：告诉 LLM "你有一个工具，参数 schema 如下" → LLM 返回结构化的 `tool_call` 对象（不是文本）→ 直接取 args → Pydantic 校验

#### 项目实现三层

**第一层：定义工具 Schema**（`services/tools.py`）

```python
class VisualProfileResult(BaseModel):
    """Design a character's visual appearance for consistent rendering."""
    # ↑ docstring 变成工具 description，LLM 能看到

    art_style: str = Field(description="Art style descriptor...")
    appearance: str = Field(description="Detailed physical appearance...")
    default_outfit: str = Field(description="Default clothing...")
```

Pydantic 模型同时是给 LLM 看的工具定义和给代码用的校验器。`model_json_schema()` 自动转为 JSON Schema 发给 API。

**第二层：绑定工具并调用**（`services/tools.py: ainvoke_with_tools()`）

```python
llm = get_llm(model)
llm_with_tools = llm.bind_tools(tools)       # Pydantic → JSON Schema → 注入 API 请求
result = await llm_with_tools.ainvoke(messages)

tool_calls = result.tool_calls                # 结构化的 tool call，不是文本
tc = tool_calls[0]
schema = tool_map[tc["name"]]                 # 找到 VisualProfileResult 类
return schema.model_validate(tc["args"])      # Pydantic 校验，类型安全
```

`bind_tools` 底层做了什么：把 Pydantic 类转为 JSON Schema，注入到 API 请求（Claude: `tools=[{name, description, input_schema}]`，OpenAI: `tools=[{type:"function", function:{...}}]`）。LangChain 抹平了协议差异。

**第三层：调用方 + Fallback**（`character_designer.py`）

```python
if settings.use_tool_calling:
    try:
        result = await ainvoke_with_tools(..., [VisualProfileResult], ...)
        visual_data = result.model_dump()   # Pydantic 实例 → dict
    except Exception:
        pass  # Tool calling 失败，不崩

if not visual_data:  # Fallback：传统自由文本 JSON 提取
    response = await ainvoke_llm(...)
    visual_data = _parse_visual_profile(content)  # 正则提取
```

#### 保留 Fallback 的原因

1. Ollama 本地模型不一定支持 tool calling
2. Mock 模式测试时返回纯文本
3. LLM 可能返回文本而非 tool call（`tool_calls` 为空）

#### 哪些 Agent 用 / 不用 Tool Calling

| Agent | 用？ | 原因 |
|-------|------|------|
| CharacterDesigner | 用 | 输出 3 个短字段，结构固定 |
| SceneArtist | 用 | 输出 1 个 prompt 字段，结构固定 |
| Director | 不用 | 输出大型嵌套 JSON（scenes+characters+branches），太复杂 |
| Writer | 不用 | 对话数组长度不固定，不适合 tool schema |
| Reviewer | 不用 | 输出是判断+反馈文本，不是结构化数据 |

**判断标准**：输出结构固定、字段少、不需要变长数组 → 用 Tool Calling。输出复杂或灵活 → 用自由文本 + 解析。

#### 对比总结

```
                 传统正则解析              Tool Calling
LLM 输出     自由文本（可能夹废话）      结构化 tool_call 对象
格式保证     靠 prompt 祈祷             API 协议约束
类型校验     手动逐字段检查             Pydantic model_validate 一步到位
漏字段       运行时 KeyError            ValidationError（提前暴露）
新增字段     改 prompt + 改正则         只加 Pydantic Field
多工具       不同模板 + 不同解析         bind_tools([Tool1, Tool2])，LLM 自己选
```

### 6.6 模型选择的逻辑

按**任务复杂度和不可逆性**分级，把贵的模型花在刀刃上：

| Agent | 模型 | 理由 |
|-------|------|------|
| Director | Sonnet（贵） | 整个管线的"大脑"，规划错了后面全废，最需要创造力和全局推理 |
| Writer | Sonnet（贵） | 要写有策略感、角色区分度的对话，语言质量要求高 |
| Reviewer | Haiku（便宜） | 核心是零 LLM 调用的结构校验，LLM 只做辅助打分，Haiku 够用 |
| CharacterDesigner | Haiku | 输出一段视觉描述，填充型任务不需要复杂推理 |
| SceneArtist | Haiku | 同上，"文字翻译成图像 prompt" |
| MusicDirector | Haiku | 最简单——读 mood 标签匹配音轨，几乎是查表 |

成本算账：Sonnet $3/$15 per MTok，Haiku $0.80/$4 per MTok。默认路由（2S+4H）降本 ~20%，全 Haiku 预算模式降本 ~73%。

### 6.7 LangGraph 并行代码详解

`graph.py` 核心结构拆解：

**图的构建**（声明式拓扑）：
```python
graph = StateGraph(AgentState)            # 共享状态字典
graph.add_node("director", ...)           # 添加节点
graph.add_node("writer", ...)
graph.add_node("reviewer", ...)
graph.add_node("asset_generation", _run_assets_parallel)  # 3 Agent 藏在一个节点

graph.set_entry_point("director")         # 起点
graph.add_edge("director", "writer")      # 线性连接
graph.add_edge("writer", "reviewer")

graph.add_conditional_edges("reviewer", _after_review, {  # 条件分支
    "proceed": "asset_generation",
    "revise": "writer",
    "end": END,
})
graph.add_edge("asset_generation", END)
return graph.compile()
```

**条件判断**（三路分发器）：
```python
def _after_review(state):
    if not review_passed and revision_count < max_rounds:
        return "revise"       # → Writer 重写
    if text_only:
        return "end"          # → 直接结束
    return "proceed"          # → 资产生成
```

**并行 + 故障隔离**（一个节点内藏 3 个 Agent）：
```python
async def _run_assets_parallel(state):
    results = await asyncio.gather(
        _traced("character_designer", run_character_designer),
        _traced("scene_artist", run_scene_artist),
        _traced("music_director", run_music_director),
        return_exceptions=True,
    )
    merged = {}
    errors = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            errors.append(f"{agent_name}: {r}")    # 记录，不中断
        elif isinstance(r, dict):
            merged.update(r)                        # 合并成功结果
    merged["errors"] = errors
    return merged
```

**可观测性包装**（装饰器模式）：
```python
def _make_traced_node(name, func):
    async def traced(state):
        with trace.span(name) as span:        # 记录耗时
            result = await func(state)
            span.set_attribute("input_tokens", ...)  # 记录 token
            return result
    return traced
```

LangGraph 的价值：**把"执行什么"和"怎么编排"分离**。每个 Agent 只管自己的逻辑，graph.py 只管拓扑和路由。加新 Agent = `add_node` + `add_edge`，不改任何已有 Agent。

### 6.8 RAG 链路深挖：FAISS 搜的是什么？策略参与了吗？

**索引编码的内容**：`embedder.py:61` 编码的是 `s.text`（12 行完整对话原文），不含策略标签。策略标签（`s.strategy`）只存在 metadata 里。

**FAISS 只管语义相似度，策略靠后处理过滤**：
1. FAISS `IndexFlatIP` 按向量内积排序（纯语义）
2. 检索完后 Python 代码硬性重排：`matched = [s for s in candidates if s.strategy == strategy]` 排前面

**Query 里拼的 `"strategy: rupture"` 有用吗？** 有一点但有限——embedding 模型看到这几个英文词会轻微影响向量方向，但语料文本里没有这些词，信号很弱。

**description vs text 的语义 mismatch**：
- Query = `scene.description`（短描述，~10 词，如"雨中的告别"）
- Database = `s.text`（12 行完整对话，~200 词）
- 短文本和长文本的向量天然不太靠近，即使讲同一件事，embedding 模型把它们编到不同的语义空间区域
- **当前之所以"勉强能用"**：语料只有 1,036 条 + 5 倍 over-retrieve + 策略硬过滤兜底 + few-shot 只需"还行"的例子

**改进方案**：
1. 改索引文本：编码 `s.title` 或让 LLM 生成 summary，让 query 和 index 在同一语义粒度
2. 双塔模型：用非对称检索模型（如 `ms-marco-MiniLM`），query 和 doc 走不同 encoder
3. 混合检索：BM25 关键词匹配 + 语义搜索，RRF 融合排序
4. 索引扩充：对每条语料额外生成 description-like 摘要存入索引

### 6.9 策略分类评测与 RAG 的真实关系

**澄清**：策略分类评测里**没有 RAG**。`eval_ollama.py:37` 显式关闭了 RAG：`USE_SEMANTIC_RETRIEVAL=false`

对比的是：
| 方法 | 做法 | F1 |
|------|------|-----|
| Keyword | 每个策略 5-6 个关键词，数命中数 | 0.21 |
| LLM zero-shot | qwen2.5:7b 直接读对话文本分类 | 0.34 |

**和 RAG 的关系是间接的**：
1. 评测证明 LLM 能区分 6 种策略（F1 > random 0.167）
2. → RAG 按策略标签过滤检索结果是有意义的（模型理解策略差异）
3. → 给 Writer 注入同策略的 few-shot 示例能提供针对性引导

**缺失的评测**：没有"加 RAG vs 不加 RAG"的直接 A/B 对比实验。

### 6.10 测试和 CI 详解

**174 个测试函数**，21 个测试文件，分布：
- `test_agents/` — Reviewer、Callbacks
- `test_services/` — LLM、Mock LLM、Tools、Token Tracker、Streaming
- `test_compiler/` — Ren'Py 编译器
- `test_eval/` — 策略分类、Corpus、Embedder、Retriever
- `test_web/` — Store（SQLite）、App（FastAPI）
- `test_integration/` — 全流水线集成测试

**Mock LLM 机制**（`test_pipeline.py:100-132`）：

```python
@pytest.fixture
def mock_ainvoke(mocker):
    async def side_effect(system, user, schema=None, model=None, caller="llm"):
        if "reviewer" in system_lower:    return MockMessage("PASS")
        elif "director" in system_lower:  return MockMessage(DIRECTOR_JSON)
        elif "writer" in system_lower:    return MockMessage(WRITER_JSON)

    mocker.patch("vn_agent.agents.director.ainvoke_llm", side_effect=side_effect)
    mocker.patch("vn_agent.agents.writer.ainvoke_llm", side_effect=side_effect)
    mocker.patch("vn_agent.agents.reviewer.ainvoke_llm", side_effect=side_effect)
```

关键：patch 的是每个 Agent 模块里的 `ainvoke_llm`（因为 `from ... import` 创建了模块本地引用），不是只 patch 源模块。

**CI 门控**：`pytest -x --tb=short -m "not slow" --cov=src/vn_agent --cov-fail-under=60`
- `-x`：第一个失败就停
- `-m "not slow"`：跳过真实 API 测试
- `--cov-fail-under=60`：覆盖率低于 60% → CI 失败

**Semaphore 并发控制**：
```python
_MAX_CONCURRENT = int(os.environ.get("VN_AGENT_MAX_CONCURRENT", "3"))
_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

async def _run_job(job_id, req, output_dir):
    async with _get_semaphore():  # 最多 3 个 job 同时跑
        # ...跑 pipeline
```

Semaphore(N) 是计数器信号量：每个任务进入计数-1，完成计数+1，计数=0 时新任务阻塞。和 Lock 的关系：Lock = Semaphore(1)。用 `asyncio.Semaphore`（协程级）而非 `threading.Semaphore`（线程级），等待时不阻塞线程。

### 6.11 多 Agent 框架深度对比

**LangGraph**：显式有向图。节点是函数，边是状态转移。`add_conditional_edges` 实现 if/else 和 retry loop。所有 Agent 共享 TypedDict，确定性流程。

**CrewAI**：角色扮演。每个 Agent 定义 role + goal + backstory，LLM 通过人设理解职责。两种模式：sequential（流水线）或 hierarchical（Manager 分配）。比 LangGraph 更灵活但更不可控。

**AutoGen**：多轮对话群聊。发言选择有 5 种策略：
- `round_robin`（轮流）、`random`（随机）、`manual`（人工选）
- `auto`（**LLM 选**）：每轮额外一次 LLM 调用决定谁说话 → 不可控的根源（选错人、死循环、跳过关键角色）
- 自定义函数：手写路由逻辑，但本质退化成 LangGraph 的 conditional edges

**Swarm**：极简 handoff。Agent 调用一个函数就把控制权交给另一个 Agent。没有图、没有状态机。OpenAI 明确说是教学/原型工具。

**AutoGPT**：单 Agent ReAct 循环（Think→Act→Observe），给一个目标让它完全自主运行。极度不可控，经常跑偏/死循环/token 黑洞。生产中几乎没人用。

**MetaGPT**：模拟软件公司组织架构（PM→Architect→Engineer→QA），用 SOP 约束协作。核心洞察：**Agent 间传递结构化文档比自然语言对话更可靠**。VN-Agent 借鉴了这个思想——Agent 间传的是 VNScript JSON，不是聊天消息。

| 维度 | LangGraph | CrewAI | AutoGen | Swarm | AutoGPT | MetaGPT |
|------|-----------|--------|---------|-------|---------|---------|
| 协作模式 | 显式图 | 角色团队 | 群聊对话 | handoff | 单 Agent 循环 | SOP 流水线 |
| Agent 自主性 | 低 | 中 | 高 | 中 | 最高 | 低 |
| 可控性 | 最高 | 中 | 低 | 中 | 最低 | 高 |
| 生产就绪 | 是 | 基本 | 偏研究 | 实验 | 否 | 基本 |
