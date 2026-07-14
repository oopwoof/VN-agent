# docs/v4/ — 当前生效的产品文档

> v4 = 2026-07-08 起 VN-Agent 的**当前产品北极星**。
>
> v1/v2/v3 的产品与工程需求**保留但搁置**（不删除，只标记 SHELVED），优先级由产品负责人后续决定。

---

## 文件说明

| 文件 | 内容 | 何时读 |
|---|---|---|
| [PRODUCT_v4.md](./PRODUCT_v4.md) | 主产品文档：愿景、用户、五大方向、指标、v3 映射、AI PM 校招叙事 | **产品决策、面试准备时必读** |
| README_v4.md（本文件） | v4 目录导航 + 与 v3 的关系 | 需要快速定位时 |

**姊妹目录**：
- `docs/v3/` — v3 时代的 SHOWCASE 与面试口径，**仍可用于校招**（不因 v4 而废）
- `docs/v2/` — v2 简历与 showcase 指南，**仍可用于校招**
- `docs/archive/` — 历史 DEV_LOG（更早期的开发流水）

**根目录文档的 v4 关系**：

| 根目录文档 | v4 状态 |
|---|---|
| `docs/PRODUCT.md` | 🔒 SHELVED — 顶部已加指向 v4 的标记 |
| `docs/ARCHITECTURE.md` | 🔒 SHELVED — 长期架构路线保留但不承诺 timeline |
| `docs/DESIGN_DECISIONS.md` | ✅ 持续更新 — 工程决策记录，内核不变 |
| `docs/AUDITS.md` | ✅ 持续更新 — 技术债追踪 |
| `docs/CHANGELOG.md` | ✅ 自动更新 — 每日 commit 流水 |
| `README.md` | ✅ 已更新导航指向 v4 |

---

## 五大方向 + v3 回补速览（详见 PRODUCT_v4.md 第 5 节 / 5.6 节）

| # | 方向 | 优先级 | 一句话 |
|---|---|---|---|
| ① | 用户友好前端 | **P2** | 从 CLI/JSON 换成 Web 工作台 (剧本 / 素材 / 预览 / Chat Ops 四视图) |
| ② | 创作者中心 + Autopilot | **P5** | 主用户明确为创作者；玩家走 Autopilot 快通道 |
| ③ | 多源素材融合 | **P0** ★ | 上传 + 网检（search-agent）+ 本地开源库作为一等公民 |
| ④ | 对话式工作台 | **P3** ★ | 常驻工作台 + 意图路由 + 可任意节点介入，超越"一次性 workflow" |
| ⑤ | 实时互动生成 | **P2** | 流式 pipeline + Web VN player，边玩边生成 |
| **B** | 自我进化 Agent（数据飞轮） | **P1** ★ | 👍/👎 → BM25 few-shot → Reflection 元规则，v3 shelved 回补 |
| **C** | PlaytestAgent + Vision Judge | **P4** ★ | 作品发布前"一键体检卡"，v3 shelved 回补 |

★ = 简历爆点方向。**优先级已由用户于 2026-07-13 定稿：方案 Y**（10-14 周，简历爆点最大化）。详细排序与盲点跟进方案见 `plans/cached-wibbling-karp.md`。

**横切约束（贯穿所有阶段）**：**中文 VN 一等公民支持** — 面试展示默认走中文，P0 完成时验证质量 gate 作为其他阶段的 baseline。详见 PRODUCT_v4.md 第 8 节。

---

## AI 产品经理校招锚点（详见 PRODUCT_v4.md 第 7 节）

三个可讲的产品能力：
1. **多源素材融合 → 回答"AI 产品如何避免同质化"**
2. **Chat Ops 工作台 → 回答"AI 产品如何设计人机协作"**
3. **AgentOps 评测底座（v3 遗留）→ 回答"AI 产品如何做评测和运维"**

---

_最后更新：2026-07-08_
