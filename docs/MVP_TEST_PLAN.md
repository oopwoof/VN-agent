# VN-Agent MVP 测试方案

> 每完成一个 Sprint 更新对应测试内容。最后更新：2026-03-28

---

## 测试环境

| 环境 | 命令 | 说明 |
|------|------|------|
| Mock 模式 | `docker compose up --build` | `.env.docker` 默认 `VN_AGENT_MOCK=true`，零成本 |
| Ollama 本地 | 修改 `.env.docker`，见下方 | 需要 qwen2.5:7b，零 API 成本 |
| Sonnet 云端 | 修改 `.env.docker` 填入 `ANTHROPIC_API_KEY` | 每次 ~$0.12-0.25 |

**Ollama .env.docker 配置**:
```
VN_AGENT_MOCK=false
LLM_PROVIDER=openai
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_API_KEY=ollama
OPENAI_API_KEY=ollama
LLM_DIRECTOR_MODEL=qwen2.5:7b
LLM_WRITER_MODEL=qwen2.5:7b
LLM_REVIEWER_MODEL=qwen2.5:7b
```

---

## MVP 交付指标

| # | 指标 | 目标 | 测试方法 | 状态 |
|---|------|------|---------|------|
| M1 | 端到端生成成功率 | ≥ 90% | Mock 跑 10 次统计成功率 | Mock: 100% / Ollama: 待测 |
| M2 | 单次生成成本 | ≤ $0.15 | budget preset 下 token tracker 统计 | Budget: ~$0.12 PASS / 默认: ~$0.25 |
| M3 | 输入到下载耗时 | ≤ 5 分钟 | 计时器已内置 (StatusBar) | Mock: ~5s / Ollama: ~52s / Sonnet: 预估 2-4min |
| M4 | Reviewer 评分 | ≥ 3.5/5.0 | Reviewer rubric prompt + 分数解析 | Prompt 有 rubric，代码仅 PASS/FAIL |
| M5 | Ren'Py 编译零报错 | 100% | 生成后用 Ren'Py SDK lint | PASS（Jinja2 + placeholder） |
| M6 | 首次可用（无引导） | 定性 | 找非技术人员测试 | 对话式输入 + Fast Mode |
| M7 | 首个成果 ≤30s | ≤ 30s | Director 返回时间 | Mock: 即时 / Ollama: ~12s |
| M8 | 编辑响应 ≤1s | ≤ 1s | PUT API 响应时间 | SQLite 写入 <100ms PASS |

---

## Sprint 1: 前端骨架 + 端到端联通

| # | 测试步骤 | 预期结果 | Pass? |
|---|---------|---------|-------|
| 1.1 | 打开 http://localhost:8000 | 暗色主题，左右分栏布局 | |
| 1.2 | 输入主题 → 点击 Send | 对话气泡出现，右侧进度条开始 | |
| 1.3 | 等待生成完成 | 右侧显示结果面板 | |
| 1.4 | 点击 Download ZIP | 浏览器下载 .zip 文件 | |
| 1.5 | 解压 zip → 检查文件结构 | 含 `game/script.rpy`, `characters.rpy`, `gui.rpy`, `init.rpy` | |
| 1.6 | 左侧栏 Job History | 显示刚完成的任务，可点击切换 | |
| 1.7 | 底部 StatusBar | 显示步骤状态 + 耗时 | |

---

## Sprint 2: 设定确认检查点

| # | 测试步骤 | 预期结果 | Pass? |
|---|---------|---------|-------|
| 2.1 | 输入主题 → Send | Director 开始规划 | |
| 2.2 | Director 完成 | 右侧出现世界观卡片（标题+描述） | |
| 2.3 | 检查角色卡片 | 显示角色名、性格、背景、颜色标记 | |
| 2.4 | 检查剧情大纲 | 时间线展示：场景列表 + 叙事策略标签 | |
| 2.5 | 点击 "Regenerate" | 重新生成设定，卡片内容变化 | |
| 2.6 | 点击 "Confirm & Generate Script" | 进度条推进，Writer 开始工作 | |

---

## Sprint 3: 脚本生成 + 审阅交互

| # | 测试步骤 | 预期结果 | Pass? |
|---|---------|---------|-------|
| 3.1 | Writer + Reviewer 完成 | 右侧出现场景标签页导航 | |
| 3.2 | 点击各场景标签 | 切换显示对应场景的对话内容 | |
| 3.3 | Reviewer banner | 顶部显示 PASS/FAIL + 修订次数 | |
| 3.4 | 点击某场景 "Edit" | 出现输入框（角色ID、对话文本、情绪下拉） | |
| 3.5 | 修改一行对话 → Save | 保存成功，显示更新后的内容 | |
| 3.6 | 点击 "Export JSON" | 下载 JSON 文件，内容正确 | |
| 3.7 | 点击 "Preview VN" | 进入 VN 预览模式（Sprint 4 测试） | |
| 3.8 | 点击 "Confirm Script & Continue" | 编译 → 进入资产管理 | |

---

## Sprint 4: 资产管理 + VN 预览

| # | 测试步骤 | 预期结果 | Pass? |
|---|---------|---------|-------|
| 4.1 | 资产面板出现 | 三个标签页：Backgrounds / Characters / BGM | |
| 4.2 | Backgrounds 标签 | 网格展示，每个卡片标记 "placeholder" | |
| 4.3 | Characters 标签 | 按角色分组，每个情绪一个卡片 | |
| 4.4 | BGM 标签 | 每个曲目有 play/pause 按钮 | |
| 4.5 | 点击 BGM 播放 | 播放音频（placeholder 为静音） | |
| 4.6 | 准备一张 PNG → 拖拽到 Background 卡片 | "placeholder" 消失，显示上传的图片 | |
| 4.7 | 准备一张 PNG → 拖拽到 Character 卡片 | 同上 | |
| 4.8 | 点击 "Re-compile & Download" | 下载 ZIP 包含上传的资产 | |
| 4.9 | VN 预览：点击屏幕 | 背景 + 角色 + 对话逐行显示 | |
| 4.10 | VN 预览：到达分支 | 显示选项按钮，点击跳转对应场景 | |
| 4.11 | VN 预览：到达结局 | 显示 "Fin" + "Back to Editor" | |

---

## Sprint 5: 体验打磨 + 快速模式

| # | 测试步骤 | 预期结果 | Pass? |
|---|---------|---------|-------|
| 5.1 | Settings → 勾选 Fast Mode | 复选框选中 | |
| 5.2 | 输入主题 → Send | 自动跳过设定确认+脚本确认 | |
| 5.3 | 最终到达资产面板 | 一键从输入到资产管理，无手动确认 | |
| 5.4 | 观察最新系统消息 | 打字机效果（逐字出现） | |
| 5.5 | 进度条活跃段 | 闪烁/脉冲动画 + 当前步骤高亮 | |
| 5.6 | 生成失败时 | 红色错误面板 + "Retry generation" 链接 | |
| 5.7 | 手机浏览器打开 | 侧栏隐藏，汉堡按钮，面板上下堆叠 | |
| 5.8 | StatusBar | 显示步骤名称 + Fast 标记 + 耗时 | |

---

## Ren'Py 运行验证

| # | 步骤 | 预期 | Pass? |
|---|------|------|-------|
| R1 | 下载 [Ren'Py SDK](https://www.renpy.org/latest.html) | 获取 renpy-8.x 目录 | |
| R2 | 解压生成的 ZIP 到 Ren'Py projects 目录 | 项目出现在 Launcher 中 | |
| R3 | Launch Project | 游戏启动，显示标题 | |
| R4 | 点击开始 | 第一场景：背景 + 角色 + 对话 | |
| R5 | 推进对话 | 对话逐行显示，表情切换 | |
| R6 | 到达分支选择 | menu 显示 2+ 选项 | |
| R7 | 选择不同分支 | 跳转到不同场景 | |
| R8 | 到达结局 | 游戏结束，无崩溃 | |

---

## 回归测试命令

```bash
# 后端
uv run ruff check src/ tests/               # lint
uv run mypy src/vn_agent/ --ignore-missing-imports  # type check
uv run pytest -x --tb=short -m "not slow"    # unit tests

# 前端
cd frontend && npm run build                 # TypeScript 编译 + Vite 构建

# Docker
docker compose up --build                    # 端到端验证
```
