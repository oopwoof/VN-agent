# VN-Agent — 现场 Demo 运行手册（v4）

> **用途**：面试现场演示的操作手册。假设你此刻有点紧张、网络不一定可靠、面试官只给你 5 分钟。
>
> **日期**：2026-08-11 · **配套**：`docs/v4/INTERVIEW_PREP_v4_CN.md`（话术）· `docs/v4/RESUME_BRIEF_v4_CN.md`（事实来源）
>
> **一句话**：**演示前 10 分钟按 §1 起服务，演示时照 §3 走，出事看 §5。**

---

## 1. 启动清单（演示前 10 分钟做）

需要**两个终端**。没有一键启动脚本——这是已知的粗糙点，如果被问到就直说「M0 阶段没做，两条命令的事」。

> ⚠️ **本节命令是 PowerShell 原生写法**，因为这台机器的默认终端是 PowerShell。
> **不要照抄 bash 语法**——`VN_AGENT_MOCK=1 <命令>` 这种内联环境变量前缀在 PowerShell 里是解析错误，`unset` 不存在，`curl -s -o -w` 在 PS 5.1 里是 `Invoke-WebRequest` 的别名、参数全不认。
> 用 Git Bash 的话，文末 §7 有 bash 对照版。

### 终端 1 · 后端

```powershell
# ⚠️ 必须在仓库根目录执行
cd D:\tasks\summer-intern\vn\VN-agent
$env:VN_AGENT_MOCK = "1"
.venv\Scripts\python.exe -m uvicorn vn_agent.web.app:app --port 8000
```

启动后**第一眼就看这一行**（`app.py:81` 打印，不是 log 是 print，一定会出现）：

```
[vn-agent] VN_AGENT_MOCK='1' -> mock floor ON (no billable calls)
```

看到 `OFF (real API calls possible)` 就是环境变量没设上，**停下重来**。

> `$env:VN_AGENT_MOCK` 只在**当前这个 PowerShell 窗口**里有效。换个窗口、或者关掉重开，都要重设——上次 $0.28 那次事故就是这个形状（详见 §6）。

**为什么必须在根目录**：`src/vn_agent/assets/library.py:28` 的素材库 manifest 用的是相对路径 `data/assets/opensource/manifest.json`。换个目录启动不会报错，只会**静默变成空素材库**——多源素材那一段演示会什么都不显示，而且现场很难看出原因。

### 终端 2 · 前端

```powershell
cd D:\tasks\summer-intern\vn\VN-agent\frontend
npm run dev
```

打开 **http://localhost:5173/** 。v2 工作台已是默认外壳（commit `3730936`），不需要带参数。

### 起完就验（30 秒，别跳过）

```powershell
(Invoke-WebRequest http://127.0.0.1:8000/jobs -UseBasicParsing).StatusCode   # 期望 200
(Invoke-WebRequest http://localhost:5173/ -UseBasicParsing).StatusCode        # 期望 200
```

浏览器里确认三件事：左侧历史记录能加载、右侧是「输入一个主题开始生成」空态、底部状态条显示「就绪」。

---

## 2. 零花费保证（这一节的准确性比什么都重要）

**结论：设了 `VN_AGENT_MOCK=1` 就是安全的，不需要再勾选界面上的 Mock 复选框。**

但这个结论**在 2026-08-11 之前是错的**，值得知道为什么——它本身就是个好故事（见 §6）：

- 唯一的闸门是 `mock_mode_var` 这个 ContextVar。`services/llm.py` 的 `ainvoke_llm` 和 `services/image_gen.py` 都只认它。
- 修复前，`VN_AGENT_MOCK=1` 只 patch 了 10 个 agent 里的 5 个，且**从不设置** `mock_mode_var`。前端 `mock` 默认 `false`，于是 `structure_reviewer` / `state_orchestrator` / `thinking` / `summarizer` 全部走真实网络，图片生成也完全没挡。
- 修复（`web/app.py::_resolve_mock`）把环境变量变成**下限**：能强制打开 mock，永远不能关闭。六个 `mock_mode_var.set` 调用点全部走它。

### 演示前的最后一道自检

跑一次生成后立刻查：

```powershell
(Invoke-WebRequest "http://127.0.0.1:8000/api/projects/<job_id>/token-usage" -UseBasicParsing).Content
```

**必须是 `"calls":0`**。任何非零都说明有真实调用，立刻停下。

> 对照数据：修复前同样形状的请求是 `calls:3~5` / `$0.05~$0.11`；修复后实测 `calls:0` / `$0.0`（generate-setting 与 generate-script 两段都验过）。

### 如果面试官问「这是真生成的吗」

**必须直说是 mock。** 这个问题上含糊一次，后面所有数字都不可信了。

> 「现在这一跑是 mock，返回的是预置 fixture，所以它不花钱、也不会在你面前挂掉。我演示的是**流水线的编排和状态**——哪个 Agent 在跑、节点之间怎么流转、失败怎么回退，这部分是真的，事件都是后端 `graph.astream()` 推上来的。
> 真实生成的数据我有实测：6 幕含素材约 $1.7 / 30 分钟，双 Judge 一致性 Pearson r=0.643。要看真跑的话我可以给你看 `run_metrics.json` 和 trace。」

**为什么不现场真跑**：一次 6 幕真实生成要 30 分钟，面试给不了这个时间；而且真调外部 API 在现场网络下是额外的失败面。

### 想要绝对保险

演示用的 shell 里把 key 清掉，硬件级杜绝：

```powershell
Remove-Item Env:ANTHROPIC_API_KEY, Env:GOOGLE_API_KEY, Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
```

`_provider_has_credentials` 会跳过所有 provider。代价是真要现场跑真实生成就跑不了了——**建议演示全程用 mock**，真实成本数据用 `RESUME_BRIEF` 里已实测的数字讲。

---

## 3. 演示动线

### 3A · 90 秒版（默认选这个）

**目标：让面试官看见「多 Agent 流水线」这件事，而不是听我说。**

> ⚠️ **演示主题必须用「樱花树下的转学生」，不要临场换别的。**
> mock 的 fixture 是**按语言选的，不是按主题选的**（`services/mock_llm.py:356 _has_cjk`）：任何中文主题都会返回同一份校园恋爱 fixture——标题「樱花树下的约定」、角色「小雪（转学生）」、场景「初次相遇 / 午后对话 / 樱花下的约定」。
> 所以输入「深海灯塔的守望者」，出来的会是一个樱花校园故事。**面试官一眼就能看出对不上**，而且这是现场最难圆的一种尴尬。用一个和 fixture 对得上的主题，画面就是自洽的。
> （已入库的两张截图就带着这个错位：job `d93e856f` 主题是「黄昏的旧书店」，播放器里却是「初次相遇」。见 §3C。）

| 步骤 | 操作 | 口播 |
|---|---|---|
| 1 | 输入主题「樱花树下的转学生」 | 「输入只有一个主题，剩下的全部由流水线决定。」 |
| 2 | 点 **⚡ 一键生成** | 「这是 Autopilot——它会跳过所有确认步骤。我一次都不会再点。」 |
| 3 | **停下来，让节点依次点亮** | 「右边是真实的 LangGraph 执行状态：导演 → 结构审校 → 状态编排 → 分场推理 → 交叉引用 → 编剧 → 质量审校。**不是进度条动画**，每一格都是后端 `graph.astream()` 推上来的节点事件。」 |
| 4 | 指「素材生成 · 已跳过」 | 「纯文本模式下这一步不跑，所以它显示『已跳过』而不是一直转圈——空状态也要说实话。」 |
| 5 | 场景胶片条逐格填充 | 「场景是边生成边流过来的，不是等全部做完。」 |
| 6 | 自动进入全幅播放器 | 「零点击。工作台让位给作品本身。」 |

**耗时**：mock 下约 40–90 秒（3 场景）。刚好够讲完上面这些。

### 3B · 3 分钟版（有时间、或面试官想看细节）

不勾 Fast Mode，走完整确认流程：

1. **输入主题 → 发送** → 流水线剧场（同 3A 步骤 3–5）
2. **设定确认页** → 「世界观、角色、剧情大纲都可以在这里改。这是人机协作的第一个介入点。」
3. **确认并生成剧本** → 再次流水线
4. **故事板** → 「剧本出来后主区变成卡片网格——分支结构一眼可见。这是整个重构的核心判断：**界面形态应该跟着工作阶段走**，而不是从头到尾一个五五分栏。」
5. **点卡片标题 → 详情** → 「逐场对白可编辑，底部五个操作都在。」
6. **返回 → 点某张卡的「从这里播放」** → 「从这一场直接进播放器，对话栏完全收起。」
7. **点铅笔图标** → 「这是 Chat Ops：它没有走新链路，而是把请求丢进和手打字一样的意图分类器，出确认卡片再执行——降低误操作。」
8. **点右上角 EN** → 「整段历史会重译，包括已经生成的消息；但我输入的主题和 LLM 生成的正文保持原样——只有界面文案跟着切。」

### 3C · 兜底：直接放截图

`docs/v4/assets/` 下有两张来自真实 mock 运行（`calls: 0`）的截图：

| 文件 | 内容 | 配合 §3A 的哪一步 |
|---|---|---|
| `workbench-pipeline-theatre.jpg` | 流水线剧场，`交叉引用` 节点点亮、`素材生成 已跳过`、场景胶片条 | 步骤 3–5 |
| `workbench-player.jpg` | Autopilot 零点击后的全幅播放器 | 步骤 6 |

断网或时间不够时，按 §3A 的口播词讲这两张图即可——**信息量和现场跑基本相同，只是少了「它真的在动」这一层说服力**。

> ⚠️ **这两张截图带着 §3A 顶部说的那个主题错位**：job `d93e856f` 的主题是「黄昏的旧书店」，但播放器里显示的是「初次相遇」（樱花 fixture）。左侧历史栏也能看到 `mock gate check`、`节点事件验证` 这类调试用 job。
> **要么**演示时不把截图放大到能看清这些细节，**要么**按 §3A 的主题重拍一次（重拍步骤见下方「待办」）。当前两张仍可用于讲流水线形态与播放器形态，那部分是准确的。

### 已验证 / 未验证（2026-08-11 收尾）

| 项 | 状态 | 证据 |
|---|---|---|
| PowerShell 启动命令（§1 全部） | ✅ 实跑通过 | 后端 200 / 前端 200 |
| 启动 banner 显示 mock 状态 | ✅ 实跑通过 | `[vn-agent] VN_AGENT_MOCK='1' -> mock floor ON` |
| 端到端 mock 生成（3 幕，主题「樱花树下的转学生」） | ✅ `completed` | job `6cec410d` |
| **零花费** | ✅ | `{"calls":0,"estimated_cost_usd":0.0}`（生成中与完成后各查一次） |
| 主题 / 标题 / 角色 / 场景自洽 | ✅ | 樱花树下的转学生 → 樱花树下的约定 · 小雪/小明 · 初次相遇/午后对话/樱花下的约定 |
| **§3A 六步、§3B 八步的逐屏走查** | ❌ **未做** | Chrome 扩展本次全程未连上（`/compact` 同时报 403，是同一个登录过期）。上一次完整走查是 2026-08-11 早些时候的 10/10 通过 |
| **录屏 GIF** | ❌ **仍未产出** | 同上，被扩展阻塞。这是第二次尝试失败 |

**待办（需要人在场，几分钟）**：重新登录后，按 §3A 用主题「樱花树下的转学生」跑一遍，顺手重拍两张截图（换掉带主题错位的旧图）并录 GIF。
**没做也能演**——上面那张表里所有「服务能起、跑得通、不花钱」的部分都已实跑验证过。

---

## 4. 演示后可以顺手展开的三样东西

- **LangGraph 拓扑图**：`README.md` 顶部（`scripts/dump_langgraph_diagram.py` 生成，10 节点）
- **测试**：**957 passed / 959 collected**（2026-08-12 实跑；1 个已知 flaky，1 个 skipped）
- **工程台账**：`.superpowers/sdd/FRONTEND_REDESIGN_PLAN_v4/progress.md` —— 六层迁移计划、每个任务的验证记录、以及**主动记录的偏差和未完成项**。被问「你怎么保证重构不出事」时直接翻这个。

---

## 5. 故障预案

| 症状 | 原因 | 现场怎么办 |
|---|---|---|
| 前端白屏 / 请求 502 | 8000 端口没起来或被别的进程占了 | `netstat -ano \| Select-String ":8000"`，最后一列是 PID；占用就 `Stop-Process -Id <PID>`，或换端口起后端并**临时**改 `frontend/vite.config.ts` 的 proxy target（改完记得别提交） |
| Vite 起在 5174 | 5173 被占 | 直接用 5174，proxy 不受影响 |
| 素材面板空的 | uvicorn 不是在仓库根目录起的 | 停掉，`cd` 到根目录重起（见 §1） |
| 第一次生成卡很久 | 换了台机器，sentence-transformers / u2net 在冷下载（~90MB + ~170MB） | **不要在没预热过的机器上演示**。当前这台已缓存 |
| 界面出问题 | v2 有 bug | 地址栏加 `?shell=v1` 立刻退回旧外壳（`useShellVariant.ts`）。旧壳完整保留，功能不缺，只是没有流水线剧场 |
| `token-usage` 非零 | mock 闸门没生效 | **立刻停止演示**，回看后端启动那一行 banner 是不是 `mock floor ON`。是 `OFF` 就说明 `$env:VN_AGENT_MOCK` 没设在**这个**窗口里 |
| 断网 / 投屏挂了 / 只剩 1 分钟 | — | 放录屏（`docs/v4/assets/`），照 §3A 的口播词讲。**准备这个的意义就在这里** |

---

## 6. 如果被问到「你演示的时候花钱了吗」

这是个好问题，而且有个诚实且加分的答案：

> 「花过。我在做前端重构的浏览器验证时，以为 `VN_AGENT_MOCK=1` 是全局保险，结果它只覆盖了 10 个 agent 里的 5 个，也完全没挡图片生成——14 次真实调用，大约 0.28 美元。
>
> 值得说的是根因：这不是忘了加开关，而是『mock』在这个系统里长成了**好几套互相有缝的机制**——环境变量 patch 一批、请求体的 ContextVar 管另一批、图片生成只认 ContextVar。八月三号我修过其中一个缝，当时没意识到还有第二个。
>
> 修法是把环境变量变成 ContextVar 的**下限**而不是并列的第二套机制，六个调用点收敛到一个 helper。并且加了一条测试：**任何 `mock_mode_var.set` 调用点绕过这个 helper 就直接失败**，agent 清单从磁盘反推，将来新增 agent 也堵得住——不是修一个 bug，是让这一类 bug 不能再出现。」

这段的价值在于它同时展示了：AI 应用的成本安全意识、根因分析而非补丁思维、以及「用测试固化边界」的工程习惯。**主动讲比被问出来强得多。**

---

## 7. Git Bash 对照版（只在你确实用 bash 时看这里）

正文用 PowerShell，因为那是这台机器的默认终端。如果开的是 Git Bash：

```bash
cd /d/tasks/summer-intern/vn/VN-agent
VN_AGENT_MOCK=1 .venv/Scripts/python.exe -m uvicorn vn_agent.web.app:app --port 8000

cd /d/tasks/summer-intern/vn/VN-agent/frontend && npm run dev

curl -s -o /dev/null -w "backend:%{http_code}\n" http://127.0.0.1:8000/jobs
curl -s -o /dev/null -w "frontend:%{http_code}\n" http://localhost:5173/
curl -s "http://127.0.0.1:8000/api/projects/<job_id>/token-usage"
unset ANTHROPIC_API_KEY GOOGLE_API_KEY OPENAI_API_KEY
```

启动 banner 与 §1 相同，两种 shell 都会打印。

---

_运行手册结束。话术见 `docs/v4/INTERVIEW_PACK_v4_CN.md`（面试主用）与 `docs/v4/INTERVIEW_PREP_v4_CN.md`（STAR 详版），事实核对见 `docs/v4/RESUME_BRIEF_v4_CN.md`。_
