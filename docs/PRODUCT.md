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

**当前阶段**: Phase 10 工业级升级（Sprint 6-1 ~ 6-9c）完成 — 端到端真实 API 跑通

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
| Intent alignment 分支意图校验（第 4 层防御） | Phase 10 Sprint 6-10 | 🔜 下一步 |
| Nano Banana (Gemini) 图像 provider 集成 | Phase 10 Sprint 6-11 | 🔜 下一步 |
| 异质语料作为 generation-only 策略的 fallback | Phase 10 Sprint 6-12 | 🔜 Backlog |
| Few-shot 显式标注 pivot 位置（`>>> PIVOT <<<` 内联） | Phase 10 Sprint 6-13 | 🔜 Backlog |
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
- 剧本质量评分（人工评估 + `eval strategy` 自动评估）
- 生成时间（从输入到输出）— **现可通过 trace.json 追踪每步耗时**
- API 成本（每次生成的花费）— **现可通过 TokenTracker 精确追踪**
- 策略分类准确率 — **`vn-agent eval strategy` 量化**
- 管线质量指标 — **结构完整性 / 对话质量 / 策略覆盖 / 成本效率**
- 测试通过率 — **当前 122 passed, 1 deselected**

---

## 接下来的开发任务

### 近期

**P0 - Web 前端**
- [ ] 简单的 React/Vue 前端：输入框 + 进度条 + 预览 + 下载
- [ ] vn_script.json 可视化编辑器（场景图 / 对话编辑）

**P1 - 质量提升**
- [ ] 真实 BGM 文件（freesound.org CC0 素材替换占位 WAV）
- [ ] 图像生成端到端验证（Stability AI / FLUX 本地）
- [ ] 多语言扩展（日文、韩文 prompt 适配）
- [ ] Writer 输出更丰富的情感状态（目前以 neutral/happy/sad 为主）
- [ ] 评估框架扩展：对真实语料跑 LLM 策略分类 baseline

### 中期

**质量与稳定性**
- [ ] 验证 Ollama 本地模型完整流程（释放内存后 qwen2.5:1.5b）
- [ ] Suno API 音乐生成（待 API 公开）
- [ ] 评估框架：Writer 输出自动与 gold label 对比（strategy consistency 精细化）
- [ ] Trace 分析工具（从 trace.json 提取瓶颈、优化建议）

_最后更新: 2026-04-13_