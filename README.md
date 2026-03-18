# VN-Agent

> 多 Agent 协作的 AI 视觉小说生成器

输入一行主题描述，输出完整可运行的 [Ren'Py](https://www.renpy.org/) 项目（剧本 + 角色立绘 + 场景背景 + BGM）。

## 快速开始

```bash
# 安装依赖（需要 uv）
uv sync

# 配置 API Keys
cp .env.example .env
# 编辑 .env，填入 ANTHROPIC_API_KEY 等

# 启用 git hooks（首次克隆后运行）
git config core.hooksPath .githooks

# 生成视觉小说
vn-agent generate --theme "一个时间旅行者在二战期间寻找失散家人的故事" --output ./my_vn
```

## 文档

- [开发日志](docs/DEV_LOG.md) — 开发过程、技术决策、反思
- [产品文档](docs/PRODUCT.md) — 产品规划、状态、思考

## 项目结构

```
src/vn_agent/
├── agents/         # LangGraph Agent 节点
├── compiler/       # Ren'Py 项目编译器
├── schema/         # Pydantic 数据模型
├── services/       # LLM / 图像 / 音乐服务
└── strategies/     # 叙事策略
```

## 开发

```bash
uv run pytest          # 运行测试
uv run ruff check .    # 代码检查
```
