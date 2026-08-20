# 方法文档：Agent 能力精确调用的量化评估

> 本文档沉淀自"MiQi 自带技能精确调用"评估（数据见 [skill-eval-REPORT.md](skill-eval-REPORT.md)，实现见 [skill-invocation-eval.spec.ts](skill-invocation-eval.spec.ts)）。方法本身不限于技能：任何"agent 是否在正确场景使用了正确能力"的问题（技能、工具、工作流、MCP）都适用同一套流程。

## 一、适用场景

想回答这类问题时用本方法：

- agent 能否在用户**没有指名**的情况下用对某个能力？（"帮我做个PPT"→ 是否会走 pptx-generator 技能）
- 一次提示词/工具集/注入策略改动，是否真的改变了 agent 的行为？
- 能力清单里哪些是死代码（永远不被触发）、哪些被误触发？

**不适用**：纯逻辑正确性（用单测）、UI 回归（用 smoke）、API 契约（用集成测试）。

## 二、核心思想

```
带标签语料（无能力名的自然语言提示词 + 期望能力）
        │
        ▼
真实系统 + 真实 LLM 执行（不 mock、不简化）
        │
        ▼
观测行为事实（工具调用链，而非回复文本/产物）
        │
        ▼
对照期望答案判分（hit / wrong_skill / no_skill）
        │
        ▼
量化指标（召回率 / 精确率 / 发现率）
```

三个坚持：**真实 LLM**（mock 测不出模型行为）、**观测行为事实**（工具调用 = 做了什么，回复文本 = 说了什么，两者可能不一致）、**语料不含能力名**（含名字就测不出"能否自己想到"）。

## 三、标准流程（五步）

### 1. 建语料（带标签测试集）

每条 = `{ id, expectedCapability, prompt }`。要点：

- **prompt 是真实用户的说法**，刻意不含能力名/触发词——这是"精确调用"与"点名调用"的分界线
- 覆盖面：直接工具与能力重叠的场景（最容易绕过）、工具名强绑定的场景、纯模型能力场景、插件/扩展能力场景
- 每个期望能力至少 1 条；语料条数 10-20 条即可撑起一轮对比
- 语料文件单独抽离，便于复用与扩充

### 2. 定观测通道

找到系统里**工具调用的唯一权威出口**，把"工具名 + 完整参数"收进收集器：

- MiQi 桌面端：`chat.onProgress({ tool_hint, tool_args })`（桥接把每个 `ToolCallBeginEvent` 转发为 progress 事件）
- 通用原则：选**离模型最近**的事件层（模型发出的 tool call），不要选渲染层 DOM 或产物文件——DOM 是展示、产物是副作用，都可能与"模型实际调用了什么"脱节

同时订阅**回合终态**（final/error/aborted），否则无法判定"没等到终态"和"回合失败"。

### 3. 定判分口径（写进代码，不要事后人肉判）

判分必须是纯函数、可复现。示例口径：

```
加载了能力 X = 执行了 skill_manage(view, name=X) 或 read_file(X/SKILL.md)
发现动作     = skill_manage(list)（单独计数，不算加载）
hit          = 期望能力被加载
wrong_skill  = 加载了别的能力
no_skill     = 什么都没加载
error/timeout = 回合失败 / 没等到终态
```

指标：

- **召回率** = hit / 全部用例（能力有没有被触发）
- **精确率** = hit / 碰了能力的用例（触发了选没选对）
- **发现率** = 执行了"发现动作"的用例占比（可选，测机制如 list 是否被遵守）

口径瑕疵要**写进报告**（如"失败的 view 尝试也计入加载"、"hit ≠ 端到端成功"），否则数字会被误读。

### 4. 跑基线，逐条记录失败模式

基线跑完不要只记数字，要逐条看**工具链**分类失败模式（这次评估分出了 4 类：内置工具遮蔽、模型先验覆盖、清单不可见、工具集脱节）。失败模式才是修复的靶子。

### 5. 修复 → 同一语料复跑 → 对比

**同一语料、同一判分口径**是前提。多轮迭代（这次是基线 → v2 → v3）时逐版本保存原始数据，对比表只列可复现数字。

## 四、关键设计决策（为什么这么做）

| 决策 | 理由 | 反模式 |
|---|---|---|
| 真开 Electron + 真实 LLM | 用户真实路径；mock LLM 测不出行为 | 用假 LLM 断言工具调用序列（恒真测试） |
| 每用例独立新会话 | 上下文隔离，防前一个用例污染 | 一个会话连发 14 条（互相影响） |
| 确认卡自动点"确认" | agent 主动发起人机握手时任务才继续 | 无人应答 → 回合超时被取消，测了个寂寞 |
| 交互走桥接 API（chat.send）而非 UI 输入框 | 与 UI 发送同一链路但更稳定 | DOM 选择器驱动（LLM 输出随机性下频繁失效） |
| 收集器放渲染进程 window 上 | Node 侧收不到桥接回调，page.evaluate 取回 | — |
| 增量落盘报告 | Electron 崩溃/worker 被杀不丢已跑数据 | 只在结束写一次 |
| 评估结论不 fail 测试 | 数据收集器不是回归门禁，报告是产出物 | 把指标阈值写进断言 |
| 判定只看工具调用事实 | "做了什么"比"说了什么"可靠 | 解析回复文本/验证产物 |

## 五、坑清单（实测踩过，按损失排序）

1. **worktree 里不要 junction `out/` 构建产物**：Electron 用 `__dirname` 推 repoRoot，junction 会把路径解析回主仓库 → 桥接跑的是**主仓库旧代码**，改动对 E2E 静默无效。worktree 里必须本地 `npm run build`（node_modules 可以 junction，out 不行）。
2. **改完代码先验证进程跑的是新代码**：`powershell Get-CimInstance Win32_Process | Where CommandLine -match "miqi.bridge"` 看 server.py 路径，不要假设。
3. **TaskStop 杀不掉进程树**：停掉后台任务后 playwright/electron 子进程变孤儿继续跑（还会用旧 spec 继续写报告）。清场用 PowerShell `Stop-Process`，且**按命令行匹配**甄别，别误杀用户自己开的实例。
4. **Electron dev userData 缓存损坏会连环崩溃**：崩溃一次后，`%APPDATA%/miqi-desktop-dev/ws-<repoRoot hash>` 的 Chromium 缓存坏了，后续启动即崩。删对应 ws-* 目录恢复（只含 dev 实例缓存，安全）。
5. **`PLAYWRIGHT_SKIP_WEB_SERVER=1`**：electron 项目不需要 http.server，webServer 等 3 分钟超时纯属浪费。
6. **Windows git-bash 的 taskkill 转义坏**：`taskkill /F /PID` 在 bash 里 `/F` 被当路径。用 PowerShell。
7. **git-bash 里 `> NUL` 会真建一个 `nul` 文件**：写死文件之前先确认；残留后 `rm nul`。

## 六、快速迭代模式

完整 14 用例跑一轮约 15-40 分钟，快速迭代用子集：

```bash
MIQI_SKILL_EVAL_CASES=pptx,weather MIQI_SKILL_EVAL_CASE_TIMEOUT_MIN=10 \
PLAYWRIGHT_SKIP_WEB_SERVER=1 npx playwright test \
  --config=playwright.config.ts --project=electron \
  skill-invocation-eval.spec.ts --workers=1
```

更快的验证（不要界面）：写 Python 驱动直接 `RuntimeSession.create()` + `submit()` + `next_event()`，同一套 runtime 代码、同样能收 `ToolCallBeginEvent`。启动秒级、没有 Electron 那类崩溃。代价是少测桌面桥接/事件转发一层——**迭代提示词用它，出权威数字用带壳版**。

## 七、落地清单

- [ ] 语料：10-20 条带标签提示词，刻意不含能力名
- [ ] 观测：工具调用 + 终态订阅进收集器
- [ ] 判分：纯函数口径 + 指标定义，瑕疵写进报告
- [ ] 基线：跑一轮，逐条分类失败模式
- [ ] 迭代：同一语料复跑，逐版本存原始数据
- [ ] 报告：前后对比表 + 失败模式 + 后续建议（模板见 [skill-eval-REPORT.md](skill-eval-REPORT.md)）
