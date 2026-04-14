# VN-Agent 产品文档

> 记录产品规划、状态、思考与决策

---

## 产品愿景

**一句话描述**: 让任何人都能通过一行命令，将一个故事主题变成完整的可玩视觉小说。

**目标用户**:
1. 独立游戏开发者（无美术/音乐资源，想快速原型验证）
2. 创意写作者（想将故事转化为交互体验）
3. 教育工作者（制作教学用互动故事）

**核心价值主张**:
- 零门槛：只需提供主题描述
- 全流程：剧本+角色+背景+BGM 一键生成
- 可控：JSON 中间格式可手动编辑
- 可运行：直接输出 Ren'Py 项目

---

## 产品状态

**当前阶段**: Phase 12-3 创作者模式 + Ren'Py 视觉层全面补完。352 tests pass。

**Sprint 8-5 sweep + cross-model judge 完成**：literary 4.17 > action 3.92 > baseline_self_refine 3.45 > baseline_single 3.25。GPT-4o cross-judge 重跑后 Sonnet 3.68 / GPT-4o 3.66，**Pearson r = 0.643, ±1-pt agreement = 87%** — 直接反驳"自评自"批评。

**Sprint 12 进度**：
- 12-3 创作者模式 pause-after-outline + continue-outline ✅（CLI + 5 pytest）
- 12-3b 立绘 rembg 抠图（u2net_human_seg，3:4 portrait）✅
- 12-3c Ren'Py 视觉层：image 路径声明、情感别名（filesystem-aware）、1920×1080 BG resize（PIL LANCZOS 保存时）、sprite zoom 0.45（self-contained ATL transforms）、悬浮 branch 菜单、renpy_safe 全覆盖、emotion 词表 dedupe 到 `schema/emotions.py`、sprite/BG aspect+zoom 共享常量 ✅
- 12-4 local regen CLI（单场景重写不跑全 pipeline）✅
- 12-5 unknown-character resolver metadata（creator-mode 阻断时附带结构化 payload）✅

下一步：Sprint 12-1（streaming pipeline, JIT scene delivery）/ 13-1（API key pool, 多用户前置）

| 功能模块 | 计划 | 状态 |
|---------|------|------|
| 故事导演 (Director Agent) | Phase 1 | ✅ 完成 |
| 剧本编写 (Writer Agent) | Phase 1 | ✅ 完成 |
| 叙事策略体系 | Phase 1 | ✅ 完成 |
| 剧本审稿 (Reviewer Agent) | Phase 2 | ✅ 完成 |
| Ren'Py 编译器 | Phase 2 | ✅ 完成 |
| CLI 工具 (generate/validate/compile/dry-run) | Phase 2 | ✅ 完成 |
| 角色立绘生成 | Phase 3 | ✅ 完成（需 OpenAI API） |
| 场景背景生成（并行化） | Phase 3 | ✅ 完成（需 OpenAI API） |
| BGM 音乐导演（曲库策略） | Phase 3 | ✅ 完成 |
| --resume 断点续传 | Phase 4 | ✅ 完成 |
| 错误恢复（非致命错误累积） | Phase 4 | ✅ 完成 |
| 流式进度显示 | Phase 4 | ✅ 完成 |
| Reviewer PASS 判断修复 | Phase 6 | ✅ 完成 |
| Director 分支校验 | Phase 6 | ✅ 完成 |
| 选择性重试（仅瞬态错误） | Phase 6 | ✅ 完成 |
| Ren'Py 表情切换 | Phase 6 | ✅ 完成 |
| Ren'Py 场景转场（fade/dissolve） | Phase 6 | ✅ 完成 |
| Ren'Py 角色位置编排 | Phase 6 | ✅ 完成 |
| Writer 中文支持 | Phase 6 | ✅ 完成 |
| 对话行数约束 | Phase 6 | ✅ 完成 |
| Token 用量追踪 + 成本预估 | Phase 6 | ✅ 完成 |
| Reviewer 可选跳过 LLM 质检 | Phase 6 | ✅ 完成 |
| Budget preset（全 Haiku） | Phase 6 | ✅ 完成 |
| OGG 占位音频文件 | Phase 6 | ✅ 完成 |
| Web API (FastAPI) | Phase 6 | ✅ 完成 |
| 评估框架（策略分类 + 管线质量） | Phase 7 | ✅ 完成 |
| COLX_523 语料集成（1,036 条标注） | Phase 7 | ✅ 完成 |
| Few-shot 示例检索注入 Writer | Phase 7 | ✅ 完成 |
| Reviewer 策略一致性检查 | Phase 7 | ✅ 完成 |
| 可观测性 Trace（耗时 + token 追踪） | Phase 7 | ✅ 完成 |
| SQLite 持久化 Job Store | Phase 7 | ✅ 完成 |
| Web API 增强（/jobs, DELETE, 并发控制） | Phase 7 | ✅ 完成 |
| GitHub Actions CI | Phase 7 | ✅ 完成 |
| Docker 容器化 | Phase 7 | ✅ 完成 |
| Schema 验证 + LLM repair | Phase 7 | ✅ 完成 |
| Chain-of-Thought 推理 Prompt | Phase 8 | ✅ 完成 |
| 5 维度评分 Rubric (Reviewer) | Phase 8 | ✅ 完成 |
| Embedding RAG (sentence-transformers + FAISS) | Phase 8 | ✅ 完成 |
| LLM Tool Calling (Pydantic schema) | Phase 8 | ✅ 完成 |
| 流式 LLM 输出 (CLI + SSE) | Phase 8 | ✅ 完成 |
| Director 7B 本地模型适配 | Phase 9 | ✅ 完成（简化 prompt，4 场景+分支） |
| React + TypeScript 前端 (Vite) | Phase 9 Sprint 1 | ✅ 完成 |
| 对话式交互 + 左右分栏布局 | Phase 9 Sprint 1 | ✅ 完成 |
| 分步生成 API（黑板机制） | Phase 9 Sprint 2 | ✅ 完成 |
| 设定确认检查点（世界观/角色/大纲） | Phase 9 Sprint 2 | ✅ 完成 |
| 场景导航 + 场景级脚本编辑器 | Phase 9 Sprint 3 | ✅ 完成 |
| Reviewer 审核结果展示 | Phase 9 Sprint 3 | ✅ 完成 |
| 导出 JSON / 下载 ZIP | Phase 9 Sprint 3 | ✅ 完成 |
| Docker 多阶段构建（Node + Python） | Phase 9 | ✅ 完成 |
| Mock 模式 Web 支持 | Phase 9 | ✅ 完成 |
| 资产管理面板（上传/替换） | Phase 9 Sprint 4 | 🔜 下一步 |
| VN 预览播放器 | Phase 9 Sprint 4 | 🔜 下一步 |
| 双 Key Pool + Prompt Caching | Phase 9 Sprint 5 | 🔜 后续 |
| 场景过渡卡片（entry/exit/emotional arc） | Phase 10 Sprint 6-1 | ✅ 完成 |
| RAG 策略 pre-filter（硬约束+软降级） | Phase 10 Sprint 6-2 | ✅ 完成 |
| 异质语料加载器（1,036 标注 + 265k 未标注） | Phase 10 Sprint 6-3 | ✅ 完成 |
| BM25 + 加权 RRF 混合检索 | Phase 10 Sprint 6-4 | ✅ 完成 |
| Per-job Token Tracker（ContextVar 隔离） | Phase 10 Sprint 6-5 | ✅ 完成 |
| Director 分支结构校验（独占下游） | Phase 10 Sprint 6-6 | ✅ 完成 |
| Reviewer 分支语义校验（Jaccard） | Phase 10 Sprint 6-7 | ✅ 完成 |
| Writer 智能截断 fallback（重生成） | Phase 10 Sprint 6-8 | ✅ 完成 |
| Pre-flight 检查（key/成本/输出目录/探活） | Phase 10 Sprint 6-9a | ✅ 完成 |
| 立绘一致性（neutral-first 参考锚点） | Phase 10 Sprint 6-9b | ✅ 完成 |
| 真实端到端 demo 脚本 + run_meta.json | Phase 10 Sprint 6-9c | ✅ 完成 |
| 策略 taxonomy 对齐 annotation guideline | Phase 10 Sprint 6-fix | ✅ 完成 |
| Reviewer 阈值硬判（avg ≥ 3.5 覆盖 LLM） | Phase 10 Sprint 6-fix | ✅ 完成 |
| Writer 注入角色 background + Reviewer 读完整对白 | Phase 10 Sprint 6-fix | ✅ 完成 |
| RAG 检索 jsonl 持久化 + BOM bug 修复 + few-shot 截断 300→2000 | Phase 10 Sprint 6-fix | ✅ 完成 |
| writer_mode 双通道（literary / action）+ 物理 taxonomy Writer prompt | Phase 11 Sprint 7-1 | ✅ 完成 |
| 选择性长上下文（prior scenes dialogue injection） | Phase 11 Sprint 7-2 | ✅ 完成 |
| Reviewer + eval judge 升 Sonnet | Phase 11 Sprint 7-3 | ✅ 完成 |
| 两层 Reviewer 架构（Sonnet structure + Sonnet dialogue + Python gate） | Phase 11 Sprint 7-5 / 7-5b | ✅ 完成 |
| 扩展 StructureReviewer audit（7 条本地检查 + LLM intent alignment） | Phase 11 Sprint 7-5b | ✅ 完成 |
| Intent alignment 第 4 层分支防御 — 融入 StructureReviewer LLM audit | Phase 11 Sprint 7-5b | ✅ 完成 |
| 跨模型 judge（GPT-4o）+ Pearson r / ±1 agreement 报告 | Phase 11 Sprint 8-1 | ✅ 完成 |
| 规则化策略 metrics（零 LLM，6 策略）+ 三角交叉验证 | Phase 11 Sprint 8-2 | ✅ 完成 |
| 基线模式（baseline_single + baseline_self_refine）+ 8-cell sweep | Phase 11 Sprint 8-3 | ✅ 完成 |
| Anthropic prompt caching（≥1500 chars system prompts） | Phase 11 Sprint 8-4 | ✅ 完成 |
| 8-cell sweep 实际运行 | Phase 11 Sprint 8-5 | 🔜 待用户 --confirm 触发 |
| Nano Banana (Gemini) 图像 provider + fallback chain + byte validation + retry classification | Phase 13 Sprint 10-1 | ✅ 完成 |
| RAG lore pivot — entity retrieval (characters + locations + world_vars + premise) | Phase 13 Sprint 10-2 | ✅ 完成 |
| Recursive scene summarization (Haiku, ≤100 words, gated ≥15 scenes) | Phase 13 Sprint 11-1 | ✅ 完成 |
| Character Bible 作为 prompt-cached system suffix | Phase 13 Sprint 11-2 | ✅ 完成 |
| Persona 指纹 voice-drift audit (pure Python) | Phase 13 Sprint 11-3 | ✅ 完成 |
| 每场景 snapshot → Sprint 12-4 local regen 基础 | Phase 13 Sprint 11-4 | ✅ 完成 |
| Gemini code review fixes (state timeline + revision loop + type validation + image chain) | Phase 13 Sprint 9/10-fix | ✅ 完成 |
| GPT-4o cross-judge auto-routing by model name | Phase 13 Sprint 8-1-fix | ✅ 完成 |
| World state 符号化追踪（WorldVariable schema + Scene state I/O + BranchOption requires） | Phase 12 Sprint 9-1 | ✅ 完成 |
| Director 发出 world_variables + 每场景 state_reads/writes | Phase 12 Sprint 9-2 | ✅ 完成 |
| Writer 读 world_state 遵循 Director 写入 | Phase 12 Sprint 9-3 | ✅ 完成 |
| Ren'Py 编译器 `default` + `$ var = value` + `"choice" if guard:` | Phase 12 Sprint 9-4 | ✅ 完成 |
| DialogueReviewer 状态一致性 + 类型/enum 合约校验 | Phase 12 Sprint 9-5/9-7 | ✅ 完成 |
| State Orchestrator (Haiku pre-Writer 约束注入) | Phase 12 Sprint 9-6 | ✅ 完成 |
| 图像 fallback UX 升级（text-first 降级，替换 neutral-bytes copy） | Phase 11 Sprint 10-1 | 🔜 |
| RAG ROI 转向 — lore / 实体检索（而非对白风格） | Phase 11 Sprint 10-2 | 🔜 |
| 长篇记忆三层架构（递归摘要 + Character Bible + Persona fingerprinting） | Phase 12 Sprint 11 | 🔜 20+ scene 时启用 |
| 异质语料作为 generation-only 策略的 fallback | Phase 10 Sprint 6-12 | 🔜 Backlog |
| Few-shot 显式标注 pivot 位置（`>>> PIVOT <<<` 内联） | Phase 10 Sprint 6-13 | 🔜 Backlog |
| ComfyUI + LoRA + ControlNet 工业立绘流水线 | Phase 12 | 🔜 长期规划 |
| Suno API 音乐生成 | Phase 3 | ⏳ 待 Suno API 公开 |

---

## 核心用户流程

```
$ vn-agent generate "一个时间旅行者在二战期间寻找失散家人的故事" --output ./my_vn

[1/6] Director 规划故事结构...
[2/6] Writer 创作剧本...
[3/6] Reviewer 审核剧本...
[4/6] 生成角色立绘和场景背景...
[5/6] Music Director 分配 BGM...
[6/6] 编译 Ren'Py 项目...

Token Usage Summary (8 LLM calls)
  Total: 12,500 input + 4,200 output = 16,700 tokens
  Estimated cost: $0.1005

✅ 完成！输出目录: ./my_vn
   - 8 个场景
   - 3 个角色
   - 4 首 BGM
```

### Web API 流程

```bash
# 启动服务器
uv sync --extra web && uvicorn vn_agent.web.app:app --port 8000

# 提交生成任务
curl -X POST localhost:8000/generate \
  -d '{"theme":"校园恋爱","text_only":true}' \
  -H 'Content-Type: application/json'
# → {"job_id":"a1b2c3d4"}

# 查询状态
curl localhost:8000/status/a1b2c3d4
# → {"status":"completed","progress":"done - 3 scenes","errors":[]}

# 列出所有任务
curl localhost:8000/jobs
# → [{"job_id":"a1b2c3d4","theme":"校园恋爱","status":"completed",...}]

# 下载结果
curl -O localhost:8000/download/a1b2c3d4

# 删除任务（含输出目录）
curl -X DELETE localhost:8000/jobs/a1b2c3d4
```

### 评估流程

```bash
# 策略分类评估（mock 模式，关键词 baseline）
vn-agent eval strategy --corpus path/to/final_annotations.csv --sample 50 --mock

# 策略分类评估（LLM 模式）
vn-agent eval strategy --corpus path/to/final_annotations.csv --sample 20

# 查看上次评估结果
vn-agent eval summary
```

---

## 产品规划

### Phase 1（第1-2周）- 文本管线 MVP ✅ 完成
- [x] 项目架构设计
- [x] 基础 Agent 框架（Director + Writer）
- [x] 叙事策略体系（8 种策略）
- [x] CLI 基础命令
- [x] 测试覆盖（schema + agent 单元测试）

### Phase 2（第3-4周）- 完整文本管线 ✅ 完成
- [x] Reviewer Agent + 修订循环（最多 3 次）
- [x] Ren'Py 编译器（含 BGM play/stop 指令）
- [x] 完整 CLI（generate / validate / compile / dry-run）
- [x] Jinja2 模板（script/characters/gui/init）

### Phase 3（第5-6周）- 多模态资产 ✅ 完成
- [x] 角色立绘生成（DALL-E 3 / Stability AI）
- [x] 场景背景生成（并行化，去重）
- [x] BGM 曲库策略（16 曲目，8 情绪）
- [x] Music Director Agent（相邻相同情绪共享曲目）

### Phase 4（第7-8周）- 优化 ✅ 核心完成
- [x] 并行化加速（asyncio.gather）
- [x] 流式进度显示（LangGraph stream_mode="updates"）
- [x] 错误恢复（非致命错误累积，不中断流程）
- [x] --resume 断点续传
- [x] stop_reason 诊断日志（区分 max_tokens vs end_turn）
- [x] Director 两步走（outline → details，避免截断）
- [x] 鲁棒 JSON 解析（_salvage_truncated_json 双策略）
- [x] 调试原始响应保存（debug/director_step*.txt）
- [x] Director 完成后立即存检查点（vn_script.json）

### Phase 5 - 成本优化与本地化 ✅ 完成
- [x] 默认模型切换到 claude-sonnet-4-6（~5× 便宜于 Opus）
- [x] 按 Agent 分配模型（Director/Writer=Sonnet，其余=Haiku）
- [x] llm_base_url + llm_api_key 字段，支持任意 OpenAI 兼容端点
- [x] config/presets/groq_free.yaml（免费，llama-3.3-70b）
- [x] config/presets/ollama_local.yaml（本地，qwen2.5:7b）
- [x] --mock CLI flag（零 API 调用，fixture 数据，~1 秒完整流程）
- [x] build_project 自动生成占位 PNG（开发期 Ren'Py 不报错）

### Phase 6 - 迭代体验开发 ✅ 完成（5 个 Sprint）
- [x] **Sprint 1: 管线可靠性**
  - Reviewer PASS 判断改为首行前缀匹配 + 结构化反馈检测
  - Director step2 分支目标校验（过滤不存在的 scene_id）
  - LLM 重试仅对瞬态错误（网络超时、限流、500），认证错误直接抛出
- [x] **Sprint 2: Ren'Py 视觉体验**
  - 表情切换（`show char emotion`，跟踪当前表情避免重复指令）
  - 场景转场（首场景 `with fade`，后续 `with dissolve`）
  - 角色位置编排（1人 center，2人 left/right，3+ left/center/right）
- [x] **Sprint 3: Writer 鲁棒性 + 中文支持**
  - CJK 检测自动追加中文 prompt 指令
  - 对话行数 min/max 约束（不足填充，超出截断）
  - 中文 mock fixture（"校园恋爱" 主题完整 Director+Writer 数据）
- [x] **Sprint 4: 成本监控**
  - TokenTracker 模块级单例，按模型累加 input/output tokens
  - CLI 生成后输出 token summary + 估算成本
  - `reviewer_skip_llm` 配置项，跳过 LLM 质检省一次 API 调用
  - `config/presets/budget.yaml`（全 Haiku，4 场景，~$0.01-0.02/次）
  - 真实 API 烟雾测试（`@pytest.mark.slow`，需 ANTHROPIC_API_KEY）
- [x] **Sprint 5: 打磨 + Web API**
  - OGG 占位音频（内联 WAV 格式，无需 ffmpeg）
  - FastAPI 后端（POST /generate, GET /status, GET /download）
  - pyproject.toml `[web]` 可选依赖（fastapi + uvicorn）

### Phase 11 - 双通道 Writer + 评估严谨性 ✅ 完成（Sprint 7 + 8）
**背景**：Phase 10 跑出首次真实 demo 后，外部架构评审（GPT/Gemini + 资深审查者）指出四个核心硬伤：
1. **对齐诅咒**：raw VN 语料 few-shot 让 Sonnet 吸收动作感偏置，压制文学潜空间
2. **自审 echo chamber**：Sonnet 评 Sonnet 自己作品，4.17 分水分大
3. **没 baseline**：声称 multi-agent 有用但没对比 single-shot / self-refine
4. **缺 symbolic state**：跨场景状态靠长上下文硬记，伸缩性崩

Phase 11 就是对这批批评的系统化响应（Sprint 9/10 deferred 处理 state + 图像，见 Phase 12 roadmap）。

- [x] **Sprint 7-1**: writer_mode 双通道（literary / action）+ 物理 taxonomy Writer system prompt
  - 直接回应"对齐诅咒"：literary 模式跳过 raw few-shot 注入，靠物理 taxonomy 描述驱动；action 模式保留原 RAG 行为
  - RAG 检索 **仍然运行**（审计）仅注入被 mode 控制
- [x] **Sprint 7-2**: 选择性长上下文（`writer_context_window`，默认 0，开启后 Writer 看前 N 场完整对白）
- [x] **Sprint 7-3**: Reviewer + eval judge 升 Sonnet（按用户模型选型原则：叙事分析给 Sonnet）
- [x] **Sprint 7-5 + 7-5b**: 两层 Reviewer 架构
  - StructureReviewer (Sonnet): outline 级 narrative audit，含 Sprint 6-10 intent alignment 融合
  - DialogueReviewer (Sonnet): 剧本级 craft rubric — voice / subtext / arc / pacing / strategy_execution 5 维
  - Python `_mechanical_check`: 零 LLM 前置门（行数 / ID / emotion / keyword） — Sonnet 只花在叙事判断
  - 7 条本地 structure audit：策略枚举合法性、角色效率、策略分布、弧形状、pacing 多样性
- [x] **Sprint 8-1**: 跨模型 judge — GPT-4o 独立评估，Pearson r + ±1 agreement 输出，< 0.3 触发 WARN
- [x] **Sprint 8-2**: 规则化策略 metrics — 6 个策略各自的纯 Python 信号（rupture=最大情感跳、accumulate=能量 Pearson r、erode=句长下降+sentiment 衰减+省略号、uncover=专名揭示率、contest=speaker×emotion alternation、drift=decisive 信号的反面）。15 新测试。
- [x] **Sprint 8-3**: 基线模式 — `baseline_single` 一次 Sonnet 产完整 script，`baseline_self_refine` 一次 draft + 一次 self-critique + revise；8-cell sweep ({literary, action, baseline_single, baseline_self_refine} × {lighthouse, dragon})
- [x] **Sprint 8-4**: Anthropic prompt caching — system prompt ≥1500 chars 标 `cache_control=ephemeral`，Writer 6-18 次调用共享缓存 5 分钟 TTL，预估 $0.07-0.25/run 节省

**成果**：264 → 279 tests pass。架构对抗外部批评的点位化响应（plan 有明细）。**下一步 Sprint 8-5**：用户 `--confirm` 触发 8-cell sweep，实测 ~$2.80 + judge ~$0.10。数据出来后决定 Sprint 9（world state）启停。

### Phase 10 - 工业级升级 ✅ 完成（Sprint 6-1 ~ 6-9c + fix）
**背景**：一面后对照米哈游 game-agent 的三个面经问题（角色一致性 / 跨场景连贯 / RAG 策略），把 toy demo 提到工业级信号。

- [x] **6-1 场景过渡卡片**：Director step2 为每对相连场景输出 `entry_context/exit_hook/emotional_arc`；Writer 独立生成每场景时天然锚定前后文，token 成本每场景只 +2-3 句，比传完整前文便宜
- [x] **6-2 RAG 策略 pre-filter**：从 post-filter 改为硬约束 pre-filter + soft degradation（标注不够时 FAISS 补足，未标注作为 backfill 只在降级时用）
- [x] **6-3 异质语料加载器**：1,036 标注 + 265k 未标注双层融合，id/指纹去重（标注覆盖未标注），标注永远排前
- [x] **6-4 BM25 + weighted RRF**：FAISS=0.7 + BM25=0.3 加权融合，诚实标注"在 VN 对话语料上 BM25 边际收益有限"——方法论完整就够
- [x] **6-5 Per-job Token Tracker**：`ContextVar` 替代模块级 singleton，多 job 并发成本隔离，数据随 blackboard 持久化
- [x] **6-6 Director 分支结构校验**：两分支 `next_scene_id` 互斥 + 3-hop 下游独占可达集；失败自动 repair，二次失败降级为线性
- [x] **6-7 Reviewer 分支语义校验**：Jaccard 相似度 + 角色集合 + 情绪分布三维比较，> 0.8 打 cosmetic warning（纯代码零 LLM 调用）
- [x] **6-8 Writer 智能截断**：对话行数 < `min_dialogue_lines` 时用已有对白尾部作上下文重生成一次，失败才退化为占位符
- [x] **6-9a Pre-flight 检查**：key 校验 + 输出目录可写性 + 成本估算（LLM+图像）+ 可选 `--ping` 探活；`vn-agent dry-run` 命令
- [x] **6-9b 立绘一致性（neutral-first）**：先生成 neutral 作为视觉锚，happy/sad 用 neutral 图作参考（openai_gpt_image / stability 支持）；不支持 ref 的 provider 用同一 base descriptor 保证 prompt 一致；任一情绪失败拷贝 neutral bytes 作 fallback
- [x] **6-9c 真实端到端 demo**：`scripts/run_real_demo.py` 执行 preflight → 交互确认 → 跑全链路 → 输出 `run_meta.json`（预估 vs 实际成本 + wall time + 错误列表）
- [x] **Sprint 6-fix：策略 taxonomy 对齐**（跑 demo 时发现）
  - `STRATEGY_MAP` 原来把 `Uncover→reveal` / `Contest→contrast` / `Drift→weave` 映射错了（语义相反），Writer 学到相反的文风
  - 改为 identity 映射 6 个对齐标签 `accumulate/erode/rupture/uncover/contest/drift`，保留 `escalate/resolve` 作为 generation-only 额外维度
- [x] **Sprint 6-fix：Reviewer 阈值硬判**：之前 PASS/FAIL 只看 LLM 输出首行，解析出来的 rubric 分数未参与判决。改为 `settings.reviewer_pass_threshold`（默认 3.5）作为权威，LLM 字符串作为备份
- [x] **Sprint 6-fix：Writer 注入角色 background + Reviewer 读完整对白**：之前 Writer 只拿 personality（对白扁平）、Reviewer 只看 3 行 preview（voice 评分基本靠猜），都是可修的成本权衡
- [x] **Sprint 6-fix：Pre-flight token 估算重新校准**：首次真实 Sonnet 跑完后发现预估低估 179%（$0.18 → $0.49）。用真实 median 重新建表，再跑估算误差 < 0.1%

**首次真实 API 跑通**（2026-04-13 16:38）：
- Theme: "Dragon slays the warrior"，6 场景，3 角色，text-only
- Reviewer avg = 5.0/5.0，0 errors，wall 531s
- 成本：估算 $0.492 vs 实际 $0.492（修正后）
- 产物：`The Last Ballad of Kael Ironveil` — 6 场景叙事连贯，有潜台词、情绪切换、有意义分支
- 已知遗留：分支 intent alignment（选项文本 vs 下游场景语义）未覆盖（待 Sprint 6-10）

### Phase 7 - 工业化迭代 ✅ 完成（Sprint 7-11）
- [x] **Sprint 7: 评估框架 + 策略分类基准**
  - COLX_523 语料导入（1,036 条标注 VN 会话，7 策略映射到 6 个 VN-Agent 策略）
  - 策略分类评估器（accuracy/F1/confusion matrix），支持 mock 关键词 baseline
  - 端到端管线质量指标（结构/对话/策略/成本 四维度）
  - CLI `eval strategy` / `eval summary` 子命令
- [x] **Sprint 8: Few-shot 检索 + Reviewer 策略一致性**
  - 按策略从语料检索示例注入 Writer prompt（`corpus_path` + `few_shot_k` 配置）
  - Reviewer 策略一致性检查（关键词匹配，非阻塞 warning）
- [x] **Sprint 9: 可观测性 + 结构化日志**
  - TraceContext/Span 模块单例，agent 节点自动追踪耗时 + token
  - 生成后输出 trace summary + 持久化 `trace.json`
- [x] **Sprint 10: 服务基础设施增强**
  - SQLite JobStore 替换内存 dict（进程重启不丢数据）
  - 新增 GET /jobs、DELETE /jobs/{id} 端点
  - asyncio.Semaphore 并发控制 + 环境变量配置
- [x] **Sprint 11: CI/CD + 可靠性约束**
  - GitHub Actions CI（lint + typecheck + test + 70% 覆盖率门禁）
  - Dockerfile（python:3.11-slim + uvicorn）
  - Director/Writer schema 验证 + LLM repair（一次自动修复机会）

---

## 产品思考

### BGM 策略选择
**问题**: 如何提供 BGM 支持？
**决策**: 三层策略
1. **曲库匹配**（默认，无需 API）：预置 10-15 首免费 .ogg 按情绪分类
2. **Suno API**（可选，需 key）：AI 生成定制音乐
3. **混合**（推荐）：先尝试 AI 生成，失败回退曲库

**理由**: 降低使用门槛（默认不需要额外 API），同时支持高质量定制

### 角色一致性机制
**问题**: 多场景中同一角色的立绘风格如何保持一致？
**方案**: `VisualProfile` 锚定 + 统一 `art_style_prompt` 前缀
- 每个角色生成时记录详细视觉描述（发色、服装、特征）
- 后续场景复用这些描述作为 prompt 前缀

### Reviewer 修订循环
**设计**: 最多 3 次修订，超过则强制接受当前版本
**检查项**:
- 分支完整性（所有 menu 选项都有对应 label）
- 角色一致性（出现角色在 characters_present 中声明）
- 场景可达性（所有 scene 都能从 start 到达）
- 叙事连贯性（narrative_strategy 与内容匹配）

### 成本控制策略
**问题**: 如何控制 API 调用成本？
**方案**: 多层成本控制
1. **模型分级**: Director/Writer 用 Sonnet，其余用 Haiku
2. **Budget preset**: 全 Haiku + 跳过 LLM 质检，~$0.01-0.02/次
3. **Token 追踪**: 每次生成后显示实际 token 用量和估算成本
4. **选择性重试**: 仅对瞬态错误重试，避免认证错误浪费 3 次调用
5. **reviewer_skip_llm**: 结构检查通过即 PASS，省一次 LLM 调用

---

## 竞品分析

| 工具 | 优势 | 劣势 |
|------|------|------|
| ChatGPT | 通用对话 | 无结构化输出，无引擎集成 |
| NovelAI | 故事生成 | 无 Ren'Py 输出，无 Agent 编排 |
| 手写 Ren'Py | 完全控制 | 需要编程知识，耗时 |
| **VN-Agent** | 全流程自动化，结构化，可扩展 | 依赖 LLM API 成本 |

---

## 关键指标

- 生成成功率（端到端不报错）
- 剧本质量评分 — **Sonnet 3.68 / GPT-4o 3.66 双判分均值**, Pearson r=0.643, ±1-pt agreement=87%（Sprint 8-5 重跑数据，commit 4f1228f）
- 生成时间（从输入到输出）— 现通过 trace.json 追踪每步耗时，showcase demo 6 scenes 约 9 min（creator-pause continue 路径）
- API 成本（每次生成的花费）— 现通过 TokenTracker 精确追踪。Showcase demo Writer+Reviewer+Assets ≈ $1.7 / 30 min 全流程；continue-outline ≈ $0.46 / 9 min（仅后半程）
- 策略分类准确率 — `vn-agent eval strategy` 量化
- 管线质量指标 — literary 4.17 > action 3.92 > baseline_self_refine 3.45 > baseline_single 3.25（8-cell sweep，multi-agent 效果验证）
- 测试通过率 — **当前 352 passed, 1 deselected**

---

## 接下来的开发任务

### 近期

**P0 - Sprint 12-1 流式 pipeline（player mode JIT delivery）**
- [ ] 重写 graph.astream 为 segmented streaming，`pipeline_lookahead=2`
- [ ] 首场景 TTFS 从 5min 降到 ~60s（Director+structure+writer1+mechanical）
- [ ] FastAPI SSE/WebSocket 推 `scene_ready` 事件

**P0 - Sprint 13-1 API key pool**
- [ ] `anthropic_api_keys: list[str]` 轮询 + 429 自动切换
- [ ] 为 100 并发用户打基础

**P1 - Visual/audio polish**
- [ ] 真实 BGM 文件（freesound.org CC0 素材替换占位 OGG）
- [ ] 角色立绘更丰富 emotion（目前 CharacterDesigner 只生成 neutral/happy/sad，其他 6 种 alias 到 neutral，filesystem-aware 已支持真实 PNG 替换）
- [ ] 多语言扩展（日文、韩文 prompt 适配）

### 中期

**质量与稳定性**
- [ ] 评估框架：Writer 输出自动与 gold label 对比（strategy consistency 精细化）
- [ ] Trace 分析工具（从 trace.json 提取瓶颈、优化建议）
- [ ] Sprint 13-2/3/4: job queue + cost caps + fleet dashboard (multi-user ops)

### 长期架构（2026-04-14 收官草案，详见 DEV_LOG.md 未来架构路线）

**P2 - 四通道 RAG 架构**（解耦代码与文学）
- [ ] ETL + chunking：以 `label`/`menu` 为物理边界的场景切片 + AI 生成的 Context Header + Haiku 元数据打标
- [ ] 通道 B（逻辑工程）：`if/elif/menu` 代码段 → 硬约束 Writer 的 Ren'Py 语法（优先跑通，确保引擎不报编译语法错）
- [ ] 通道 A（叙事风格）：提取"节奏骨架"而非字面句，提升文学质量
- [ ] 通道 C（视觉演出）：`screens.rpy` + ATL transform → 给 SceneArtist 提供 `vpunch` 等动态演出
- [ ] 通道 D（编译架构）：`options.rpy` + `gui.rpy` 全局配置模板
- [ ] RAG Router：意图分类器 dispatch，Writer 只收 A，SceneArtist 只收 C，Orchestrator 只看 B+D

**P2 - 自我进化 Agent**（经验沉淀 + 反向传播）
- [ ] L1 经验库 RAG：失败/成功生成向量化入 `faiss_experience_db`，Writer 下次调用前动态 few-shot 注入 System Prompt
- [ ] 周末快速原型：创作者 UI 加 👍/👎 按钮 + 原因字段 → JSONL → BM25 扫入 Writer prompt（"**绝对禁止：废话太多**"）
- [ ] L2 Reflection Agent：异步跑批提炼元规则 → `dynamic_guidelines.json` → 启动时拼接 System Prompt
- [ ] L3 DSPy 式自动 Prompt 优化 + DPO 微调廉价模型（Llama 3 8B / Haiku）

_最后更新: 2026-04-14_