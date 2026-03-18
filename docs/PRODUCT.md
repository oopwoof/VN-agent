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

**当前阶段**: Phase 4 优化中（核心功能全部完成）

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
| Web 界面 (FastAPI) | Phase 4 | ⏳ 待开始 |
| Suno API 音乐生成 | Phase 3 | ⏳ 待 Suno API 公开 |

---

## 核心用户流程

```
$ vn-agent generate --theme "一个时间旅行者在二战期间寻找失散家人的故事" --output ./my_vn

[1/6] 📋 Director 规划故事结构...
[2/6] ✍️  Writer 创作剧本...
[3/6] 🔍 Reviewer 审核剧本...
[4/6] 🎨 生成角色立绘和场景背景...
[5/6] 🎵 Music Director 分配 BGM...
[6/6] 📦 编译 Ren'Py 项目...

✅ 完成！输出目录: ./my_vn
   - 8 个场景
   - 3 个角色
   - 4 首 BGM
   - 预计游玩时长: 20-30 分钟
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
- [x] 集成测试（46 个测试全部通过）
- [x] stop_reason 诊断日志（区分 max_tokens vs end_turn）
- [x] Director 两步走（outline → details，避免截断）
- [x] 鲁棒 JSON 解析（_salvage_truncated_json 双策略）
- [x] 调试原始响应保存（debug/director_step*.txt）
- [x] Director 完成后立即存检查点（vn_script.json）
- [ ] FastAPI 后端 + Web 界面
- [ ] Suno API 音乐生成（待 API 公开）

### Phase 5 - 成本优化与本地化 ✅ 完成
- [x] 默认模型切换到 claude-sonnet-4-6（~5× 便宜于 Opus）
- [x] 按 Agent 分配模型（Director/Writer=Sonnet，其余=Haiku）
- [x] llm_base_url + llm_api_key 字段，支持任意 OpenAI 兼容端点
- [x] config/presets/groq_free.yaml（免费，llama-3.3-70b）
- [x] config/presets/ollama_local.yaml（本地，qwen2.5:7b）
- [x] --mock CLI flag（零 API 调用，fixture 数据，~1 秒完整流程）
- [x] build_project 自动生成占位 PNG（开发期 Ren'Py 不报错）
- [x] Ollama 0.18.1 已安装（qwen2.5:7b 已下载）

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

---

## 竞品分析

| 工具 | 优势 | 劣势 |
|------|------|------|
| ChatGPT | 通用对话 | 无结构化输出，无引擎集成 |
| NovelAI | 故事生成 | 无 Ren'Py 输出，无 Agent 编排 |
| 手写 Ren'Py | 完全控制 | 需要编程知识，耗时 |
| **VN-Agent** | 全流程自动化，结构化，可扩展 | 依赖 LLM API 成本 |

---

## 关键指标（待定义）

- 生成成功率（端到端不报错）
- 剧本质量评分（人工评估）
- 生成时间（从输入到输出）
- API 成本（每次生成的花费）

---

---

## 接下来的开发任务

### 近期（下次开发时）

**P0 - 验证 Ollama 本地流程**
- [ ] 释放内存后用 qwen2.5:1.5b 跑一次完整 pipeline（`--text-only`）
- [ ] 观察 stop_reason 日志，确认 max_tokens 是否真的生效
- [ ] 验证 JSON 解析在本地模型下的鲁棒性

**P1 - 提升生成质量**
- [ ] Reviewer 在 LLM 返回 PASS 时条件放宽（当前 `len < 20` 过严）
- [ ] Writer 对中文对话的 prompt 调优（避免英文回复）
- [ ] Director step2 branch 校验：过滤掉引用了不存在 scene_id 的分支

**P2 - FastAPI 后端**
- [ ] `POST /generate` → 接收 theme，返回 job_id
- [ ] `GET /status/{job_id}` → SSE 流式推送进度
- [ ] `GET /download/{job_id}` → 下载 zip 包

### 中期

**Web UI**
- [ ] 简单的 React/Vue 前端：输入框 + 进度条 + 预览 + 下载
- [ ] vn_script.json 可视化编辑器（场景图 / 对话编辑）

**质量提升**
- [ ] 真实 BGM 文件（freesound.org CC0 素材）
- [ ] 图像生成接通（Stability AI / FLUX 本地）
- [ ] Suno API（等 API 公开）

_最后更新: 2026-03-18_