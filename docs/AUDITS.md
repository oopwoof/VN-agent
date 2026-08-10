# VN-Agent 收官审计集

> 稳定区文档。把"已知技术债 + 未完成修复"分析保留在此，供下次回到这些坑位时起点用。
> 从 [ARCHITECTURE.md](./ARCHITECTURE.md) 切出（2026-04-23）。审计项不是未来方向规划，是对当前代码库的诚实盘点——每项都有问题分析、现状清单、按 ROI 排序的修复方案。

---

## 1. Lore 截断 + 优先级缺失（2026-04-14 审计）

`src/vn_agent/eval/lore.py` 里有 4 处截断，都是 Sprint 7 时期 8K context 的历史包袱：

| 行 | 截断点 | 问题 |
|---|---|---|
| `lore.py:104` | `(first.description or 'no description')[:240]` 单 location 描述 240 字符 | 240 字符 < 一个完整句 |
| `lore.py:162` | `format_lore_block(max_chars: int = 1500)` 整块上限 | 1500 char ≈ 400 token，对 Sonnet 200K 来说毫无意义 |
| `lore.py:183` | `(getattr(ex, "text", "") or "")[:300]` 每 entity text 300 字符 | 同上，腰斩富文本人物档案 |
| `lore.py:185` | `running > max_chars` 直接 break + `"..."` 占位 | 硬截断，没优先级 |

**3 个真问题**：

1. **没优先级** — 先到先服。`extract_lore_entities` append 顺序是 premise → characters → locations → world_vars，但 retrieve top-k 后按 cosine score 重排，premise 可能不在前面，硬截断时直接被 `...` 吃掉
2. **暴力 `[:N]` 切到字符中间** — 不按句号/逗号断。`Premise: A lighthouse keeper must` ← 原文 `must save a ship or abandon her post` 被腰斩。Writer 看到半句话理解偏差
3. **历史数字** — 1500 char cap 是 Sonnet 8K context 时代设的。现在 Sonnet 200K + prompt caching 5min TTL（Sprint 8-4 已启），预算根本不紧

**配合 scope 改造一起修**（scope 设计详见 [ARCHITECTURE.md](./ARCHITECTURE.md) 路线一）：

- `scope=always` 实体（premise/世界观/主角阵容）→ **完全不截断**，全文进 system prompt prefix，靠 `cache_control: ephemeral` 摊薄成本
- `scope=chapter` 实体 → max_chars per-entity 提到 800（够装一个 ≤500-word chapter summary）
- `scope=scene` 实体（location/callback hooks）→ 保留 300 char per-entity cap（retrieved，本身 noisy，无所谓）
- `format_lore_block` 总 cap 默认提到 4000-6000 char（~1500 token），且按句号 / 段落断而非字符截
- 按 scope 优先级 fold：always 永不被裁，chapter 次之，scene 最后填空

简单实现：`format_lore_block` 改签名收 `entities: list[AnnotatedSession]` + `scope_caps: dict[str, int]`，分组按 priority 输出。

---

## 2. world_variables 状态记录的缺口（2026-04-14 审计）

下次接手前需要知道的真相：state IS recorded，但分散在多个文件里，且**没有 top-level time series、没有分支感知**。

**已记录** ✓
- `vn_script.json::world_variables` — 初始值（每个 var 的 name/type/initial_value/description）
- `vn_script.json::scenes[].state_writes` — 每场景的**增量** delta（`{var: new_value}`）
- `<output>/snapshots/<scene_id>.json` — Sprint 11-4 per-scene `world_state_after` 快照，best-effort（写失败只 log 不抛）
- `outline_checkpoint.json` — creator pause 时刻的 `world_state` 全量快照
- Ren'Py 编译产物 — `init.rpy` 的 `default var = X` + scene label 内 `$ var = X`，Ren'Py 运行时正确追踪 live state
- Phase 13-1 Step 2 新增 `state_timeline` 顶层字段（每 scene 的 state_after 都 append）—— 解决了"time series 缺失"一项

**没记录** ✗
1. ~~`vn_script.json` 本身没有 time series 字段~~（Phase 13-1 Step 2 已修复 — state_timeline 已加）
2. **分支感知完全缺失**。`local_regen.py:80-88` 线性 walk `script.scenes[:idx]` 重建 world_state，假设场景按顺序执行 — 真实玩家可能从不同分支到达同一场景，state 取决于路径。当前系统把 VNScript 当线性时间线处理，忽略 branch DAG。
3. State orchestrator 编译的 `state_constraints` 文本 ephemeral — 只在 AgentState 中存在，run 完丢失。outline_checkpoint 保留了 pause 时刻的一次，但**每场景 Writer 实际看到的 constraint 文本没存盘**，debug 时无法回溯"当时 Writer 看到了什么"。
4. 没有 Web API 暴露状态时间线 — 前端无法显示"state 演化"。
5. snapshots 目录写失败时无 fallback — Writer.py:159+ best-effort，灾难时静默丢失。

**修复建议（按 ROI 排）**：

- ~~快胜（30 min）：vn_script.json 顶部加 `state_timeline: list[dict]` 字段~~ **✅ 已完成（Phase 13-1 Step 2）**
- **中等（2h）**：scene-level snapshot 加 `state_constraints_seen` 字段（state_orchestrator 给本场景生成的 constraint 文本），让 debug 知道 Writer 当时的"指令书"。
- **真长（4h+）**：分支感知 state — 每条 path 一个 timeline；local_regen 时根据玩家路径重建。需要把 VNScript 看成 DAG 而非 list，state walker 改写。建议放进 Sprint 11+ 的长篇/分支章节再做，6-scene demo 暂时不刚需。

---

## 3. Recursive Summarization 重复 + chapter rollup 缺失（2026-04-14 审计）

Sprint 11-1 的 per-scene Haiku summary 有两个 bug 类问题，外加一个未实现的 deferred 项（Phase 13-1 Step 4 已修前两项，Step 3 前提下 chapter rollup 也已收）：

**问题 1：修订循环里每场重复 summarize**（**✅ Phase 13-1 Step 4 已修**）
`writer.py:140-157` 的 summary 块在 `for idx, scene in enumerate(script.scenes)` 循环内，最初没有 `if not updated_scene.summary` 守卫。Reviewer FAIL → run_writer 从头跑 → 全场重写 → summary 也跟着每场重 fire。
- 6 scenes × 3 revisions = 18 次 Haiku call（应该 6 次）
- 单价 ~$0.002，每 run 浪费 ~$0.024。规模化后累积明显（且 Haiku QPS 也被吃掉）
- 修复采用 `dialogue_hash` 对比方案（比纯 `if not summary` 守卫更鲁棒）

**问题 2：local_regen 后 summary stale**（**✅ Phase 13-1 Step 4 已修**）
`local_regen.regenerate_scene` 直接调用 `_write_scene` 单场景 helper，最初绕过 run_writer 外层 loop body 里的 summary 块。
- 重写场景的 `scene.summary` 仍是旧 dialogue 的 summary
- 下游场景 fold `older_summaries`（writer.py:104-108）时拿到错的提要
- Writer 看到的"前情提要" ≠ 实际 dialogue → 长篇生成会逐渐漂
- 修复：local_regen 后 dialogue_hash mismatch 触发 summary refire

**问题 3：chapter-level rollup 完全没实现**（**✅ Phase 13-1 已实装**）
`summarizer.py:14` 的 docstring 列了"Chapter-level rollups every N scene summaries (500-word meta-summary)"作为 Deferred，最初只有 per-scene summary，没有跨章压缩。
- 50 scenes × 100 words = 5000 words / ~6500 tokens 全部塞进 Writer prompt
- 真正长篇 (50+ scenes) 跑起来 context 必爆
- 修复：每 10 scene fire-and-forget Haiku rollup，下一章开头 gather，墙钟近乎零开销

**历史修复清单**：

| ROI | 改动 | 状态 |
|---|---|---|
| 30 sec | writer.py:140 加 `if not updated_scene.summary` 守卫 + revision 入口处清空 stale summary | 被更强方案取代 |
| 2 min | summary 字段含 `dialogue_hash`，next pass 比对，hash 同则跳过 | ✅ Phase 13-1 Step 4 |
| 5 min | local_regen.py:130 splice 后 conditional summary refire | ✅ Phase 13-1 Step 4 |
| 1.5 h | 实现 chapter rollup：每 10 个 scene summary fold 一次 | ✅ Phase 13-1 |

**本条审计剩余遗留**：
- `state_constraints_seen` 字段（和审计 2 共享） — 未修
- Web API 对 state_timeline / summary / rollup 的暴露 — 未修
- 分支感知 summary（玩家走不同路径下游场景 summary 链可能需要 fork）— 同审计 2 的"真长项"

---

_本文档只记录审计项本身。修复动作后续会合并进 CHANGELOG.md 相应 commit 条目，保持审计档案稳定可参考。_
