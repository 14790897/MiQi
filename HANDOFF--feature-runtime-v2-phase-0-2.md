# Handoff: feature/runtime-v2-phase-0-2

**From:** [lichman0405/MiQi-1](https://github.com/lichman0405/MiQi-1)  
**Branch:** `feature/runtime-v2-phase-0-2`  
**Base:** upstream `main` ([14790897/MiQi](https://github.com/14790897/MiQi))  
**Commits ahead:** 435  
**Files changed:** 389 files, +82,338 / -3,415 lines (excluding docs and plan files)  

---

## 获取方式

```bash
git remote add lichman https://github.com/lichman0405/MiQi-1.git
git fetch lichman
git log main..lichman/feature/runtime-v2-phase-0-2 --oneline
git diff main..lichman/feature/runtime-v2-phase-0-2 --stat
git merge lichman/feature/runtime-v2-phase-0-2
```

---

## 一句话概括

将 MiQi 从一个以 `AgentLoop` 为中心的聊天应用（CLI 脚本 + Node.js 桥接，零状态隔离，零类型契约），重构为以 `RuntimeSession` + `AppServer` 为核心的多租户工作台运行时平台（typed protocol contracts, persistent ledger, streaming provider, sandbox policy, hooks lifecycle, agent graph persistence, telemetry）。

---

## 一、架构重构：AgentLoop → RuntimeSession + AppServer

### 改动前（main 分支）

```
用户输入 → AgentLoop.run() → 模型 → 工具 → 回复
            ↑
            直接构造，无 session 概念
            无 client 隔离
            Node.js bridge 持有所有业务逻辑
```

### 改动后（当前分支）

```
┌──────────┐   AppServer Protocol (typed, 152 methods)   ┌──────────────┐
│ Desktop  │─── initialize / turn/start / chat.send ───→│ RuntimeSession│
│ CLI      │─── fs/readFile / command/exec ────────────→│   ├─ TaskRunner    │
│ TUI      │─── thread/resume / sessions.delete ────────→│   ├─ TurnRunner    │
│ Gateway  │─── plugin/install / model/list ────────────→│   ├─ ToolRuntime   │
│ Cron     │─── events: turn/started, agent/delta ──────→│   ├─ HistoryRuntime│
└──────────┘                                             │   ├─ ThreadRuntime │
                                                         │   ├─ LedgerRuntime │
                                                         │   ├─ AgentJobRuntime│
                                                         │   ├─ HooksRuntime  │
                                                         │   ├─ SandboxManager│
                                                         │   └─ ContextRuntime│
                                                         └──────────────┘
```

**关键变化：**
- `AgentLoop` 已完全删除（包括 `RuntimeAgentLoopCompat` shim），生产代码中零引用
- `RuntimeSession` 是唯一的运行时入口——所有前端（Desktop/CLI/TUI/Gateway/Cron）都通过它提交请求
- `TaskRunner` 将外部命令路由到 `TurnRunner`（流式模型循环）、`ThreadRuntime`、`ConfigUpdate` 或 `CompactCommand`
- `AppServer` 是传输无关的协议边界，拥有 client→session 映射、方法 dispatch、中间件链、事件扇出

---

## 二、协议契约：152 个方法的类型化

### typed vs legacy 统计

| | typed (强类型) | legacy (无类型) | 总方法数 |
|---|---|---|---|
| **改动前** | 32 | 120 | 152 |
| **改动后** | 83 | 69 | 152 |

### 已类型化的 83 个方法覆盖范围

| 方法组 | 数量 | 代表方法 |
|--------|------|---------|
| **核心能力** | 13 | `initialize`, `status`, `python.check`, `config/read`, `config/batchWrite`, `config.get`, `config.update`, `model/list`, `modelProvider/capabilities/read`, `experimentalFeature/list`, `experimentalFeature/enablement/set`, `permissionProfile/list` |
| **Turn** | 3 | `turn/start`, `turn/interrupt`, `turn/steer` |
| **进程** | 8 | `command/exec`, `command/exec/write`, `command/exec/resize`, `command/exec/terminate`, `process/spawn`, `process/writeStdin`, `process/resizePty`, `process/kill` |
| **文件系统** | 12 | `fs/readFile`, `fs/writeFile`, `fs/createDirectory`, `fs/getMetadata`, `fs/readDirectory`, `fs/remove`, `fs/copy`, `fs/watch`, `fs/unwatch`, `fuzzyFileSearch` + 3 session 子方法 |
| **插件/市场/技能** | 12 | `plugin/list`, `plugin/installed`, `plugin/read`, `plugin/skill/read`, `plugin/install`, `plugin/uninstall`, `marketplace/add`, `marketplace/remove`, `marketplace/upgrade`, `skills/list`, `skills/extraRoots/set`, `hooks/list` |
| **会话** | 9 | `sessions.list`, `sessions.get`, `sessions.delete`, `sessions.archive`, `sessions.unarchive`, `sessions.list_archived`, `sessions.get_tracked_files`, `sessions.clear_tracked_files`, `sessions.claim_legacy` |
| **线程** | 18 | `thread/start`, `thread/resume`, `thread/fork`, `thread/read`, `thread/turns/list`, `thread/turns/items/list`, `thread/list`, `thread/export`, `thread/import`, `thread/name/set`, `thread/rollback`, `thread/loaded/list` + 6 兼容方法 (`thread.create`, `thread.list`, `thread.rename`, `thread.archive`, `thread.delete`, `chat.abort`) |
| **Thread 基础设施** | 5 | `thread/compact/start`, `thread/inject_items`, `thread/shellCommand` |
| **Replay/Debug** | 3 | `replay.turns`, `replay.timeline`, `replay.messages` |

### 类型化基础设施

- **14 个 Pydantic 请求模型文件** — `core_request_models.py`, `plugin_skill_request_models.py`, `session_request_models.py`, `thread_request_models.py`, `turn_request_models.py`, `filesystem_request_models.py`, `process_request_models.py`
- **7 个 Pydantic 响应/事件模型文件** — 对应的 `*_response_models.py` 和事件模型
- **`protocol_model_schema.py`** — `model_spec()` 从 Pydantic 模型自动派生 `paramsSchema` / `resultSchema`
- **`export_app_protocol_ts.py`** — 从 Python 模型生成 TypeScript 接口（`app-protocol.ts`）
- **`protocol_snapshot.py`** — 确定性快照 + SHA-256 hash，防止意外 breaking change
- **`protocol_registry.py`** — `ProtocolMethodSpec`（stability/scope/emits/schemas）+ `ProtocolRegistry`

### 安全改进：参数校验在运行时查找之前

在所有 handler 中，校验顺序是：
1. `validate_*_params(method, params)` — Pydantic 严格类型校验
2. 然后才做 `get_bridge_state()` / `_get_session_manager()` / `_catalog()` / `_stored_reader()` 等

**效果：** 客户端传 `{"limit": "50"}`（字符串代替整数）或 `{"threadId": 123}`（整数代替字符串）时，直接返回 `INVALID_PARAMS`，不会先查数据库/沙箱再报 `INTERNAL`。

---

## 三、运行时核心能力

### 持久化
- **`HistoryRuntime`** — SQLite 持久化 turn items 和 turn records；session 重连时自动恢复
- **`ThreadRuntime`** — create/rename/archive/delete/fork/list，带 client-scoped 隔离
- **`LedgerRuntime`** — append-only SQLite 事件账本（user turns, streaming deltas, tool lifecycle）；`load_provider_messages()` 可重建完整对话
- **SessionManager** — `owner_client_id` 元数据、`OwnershipError`、client-scoped 会话操作、claim-on-first-touch 迁移

### 进程与沙箱
- **`WorkbenchProcessRuntime`** — 8 个 Codex-style 进程控制方法，client-scoped handles，streaming output + stdin + timeout/kill
- **`SandboxManager`** — `client_id:session_key` 双重命名空间隔离，避免跨 client 命名冲突
- **`ExecTool`** — 完整事件生命周期（`ExecCommandBeginEvent` / `ExecCommandEndEvent`）
- **PTY 支持** — 明确拒绝并返回 `UNSUPPORTED_FEATURE`（`command/exec/resize`, `process/resizePty`）

### Agent 任务图
- **`AgentJobRuntime`** — 持久化 sub-agent 生命周期（spawn/list/get/kill）
- **`AgentGraphStore`** — SQLite 持久化 `runtime_agent_jobs` 和 `runtime_agent_edges`（父子拓扑）
- **`CapabilityResolver`** — 按 agent role + plugin injection 过滤 tool definitions

### Hooks 生命周期
- **13 个生命周期点**全部从 runtime 触发：`SESSION_START`, `TURN_START`, `PRE_COMPACT`, `SUBAGENT_START` 等
- 支持 `continue` / `block` / `modify` 三种返回模式
- 插件可通过 manifest 注册 hooks（`command` 和 `module` 执行类型）

### 权限与审批
- **`PermissionProfile`** — 附加到 `TurnContext`；`ExecPolicy` DSL（`CommandRule`/`NetworkRule`/`FilesystemRule`，deny-wins 优先级）
- **`ApprovalPolicy`** — 五种模式（`unless-trusted`/`on-failure`/`on-request`/`granular`/`never`），对可信类别抑制 `APPROVAL_REQUIRED`

### Code Review
- **`ReviewRuntime`** — 收集 git diff → 构建 review prompt → 调用 provider → 解析结构化 `ReviewResult`/`ReviewFinding` → 流式事件
- 暴露为 `review/start` 和 `review/get` AppServer 方法

### Apply Patch
- **`ApplyPatchTool`** — unified-diff 解析器 + hunk application + context matching，与 `EditFileTool` 共享沙箱策略

---

## 四、可靠性与可观测性

### Provider 韧性
- 共享 `resilience.py`：`ErrorKind` 枚举（`RATE_LIMIT`/`SERVER_ERROR`/`AUTH`/`TIMEOUT`/`NETWORK`/`CONTENT_FILTER`）
- `with_retry` 装饰器：指数退避 + `Retry-After` header 尊重
- OpenAI `stream_chat()`：pre-connect retry + per-chunk idle timeout
- 所有 provider 调用有显式请求超时
- `LLMResponse.error_kind` 字段用于可恢复/不可恢复分类

### 错误传播
- Provider 错误不再伪装成正常回复
- `TurnRunner` 对 `finish_reason="error"` 抛出 `ProviderError`
- `TaskRunner` 将其展示为失败 turn + `ErrorEvent`（带 `error_kind` + `recoverable` 标记）
- AUTH 错误消息被 sanitized（不泄露原始 provider 异常）

### OpenTelemetry
- 可选 tracing（每 turn 一个 span，每 tool call 一个 child span）
- Metrics：turn 计数器、error 计数器、token histogram、tool 计数器
- 通过 `[observability]` 配置段控制，默认 OFF，`opentelemetry` 不存在时 no-op

---

## 五、核心文件变化

### 新增运行时模块（miqi/runtime/）
```
app_server.py              — 传输无关协议边界 + client/session registry
stored_runtime.py          — StoredRuntimeReader (SQLite 离线读取)
thread_app_handlers.py     — 12 Codex-style thread handler
thread_projection.py       — ThreadProjectionRuntime
thread_export.py           — build_export_document()
thread_protocol.py         — page_items() 分页
session_handlers.py        — 9 sessions.* handler
plugin_app_handlers.py     — 9 plugin/marketplace handler
skills_app_handlers.py     — skills/hooks handler
model_app_handlers.py      — model catalog handler
config_app_handlers.py     — config read/write handler
feature_app_handlers.py    — experimental feature handler
permission_profile_app_handlers.py
filesystem_app_handlers.py — 7 fs/* + watch handler
process_app_handlers.py    — 8 进程 handler
turn_app_handlers.py       — turn/start|interrupt|steer handler
feature_runtime.py         — FeatureRuntime
plugin_catalog.py          — PluginCatalogRuntime
permission_profile_runtime.py
protocol_model_schema.py   — model_spec() Pydantic→ProtocolMethodSpec
protocol_snapshot.py       — 兼容性快照构建器
protocol_registry.py       — ProtocolRegistry + ProtocolMethodSpec
export_app_protocol_ts.py  — Python→TypeScript 生成器
```

### 新增 Pydantic 模型（14 个文件）
```
core_request_models.py          filesystem_request_models.py
core_response_models.py         filesystem_response_models.py
plugin_skill_request_models.py  process_request_models.py
plugin_skill_response_models.py process_response_models.py
session_request_models.py       turn_request_models.py
session_response_models.py      
thread_request_models.py        turn_response_models.py
thread_response_models.py       (共计 83 个方法的 typed models)
```

### 新增 Provider / Execution 模块
```
miqi/providers/resilience.py   — ErrorKind + with_retry + 退避
miqi/execution/                 — ExecTool + ApplyPatchTool + sandbox 策略
miqi/observability/             — OpenTelemetry tracing + metrics
miqi/runtime/ledger/            — LedgerRuntime + agent graph store
```

### 删除的文件
```
miqi/agent/loop.py              — AgentLoop（已被 TaskRunner/TurnRunner 替代）
Dockerfile, docker-compose.yml  — 不再需要的容器化文件
```

---

## 六、测试体系

| 类别 | 覆盖范围 | 代表性文件 |
|------|---------|-----------|
| 请求模型 | 83 个 typed 方法 | `test_*_request_models.py` (7 个文件) |
| 响应模型 | 83 个 typed 方法 | `test_*_response_models.py` (6 个文件) |
| 验证顺序 | 证明 INVALID_PARAMS 在 state lookup 之前 | `test_phase*_validation_before_runtime.py` (5 个文件) |
| 契约审计 | live catalog 中 schema 与模型一致 | `test_phase*_contract_audit.py` (5 个文件) |
| 协议快照 | typed/legacy 计数 + hash 审计 | `test_phase68_protocol_snapshot.py` |
| 生成类型审计 | TypeScript 生成结果完整性 | `test_phase66_generated_types_audit.py` |
| AgentLoop 退役 | 零 `AgentLoop(` 零 `process_direct(` | `test_runtime_ownership_audit.py` |
| 平台分类 | subprocess/sandbox/bwrap/wsl markers | `conftest.py` pytest 标记 |
| CI | GitHub Actions 跨平台 workflow | `.github/workflows/test.yml` |

### 当前测试结果

```
Focused Plan 72 (models + validation + audit):   23 passed
Thread/turn handler tests:                        44 passed
Protocol governance (12 suites):                  45 passed
Desktop vitest (bridge + app-client):             18 passed
Desktop tsc --noEmit:                            clean
Portable non-sandbox:                           1982 passed, 6 skipped
```

---

## 七、向后兼容性

- 152 个方法全部保留在 protocol catalog 中，无删除
- 69 个 legacy 方法行为不变（仍是宽松 `{type: "object"}` schema）
- 83 个类型化方法只增加了校验严格度——正常调用路径不受影响
- `RuntimeSession` 接口完全兼容所有现有前端（Desktop/CLI/TUI/Gateway/Cron）
- `SessionManager` 向后兼容：老 session 无 `owner_client_id` 时自动 claim-on-first-touch
- `thread/turns/items/list` 保留 `UNSUPPORTED_METHOD` 行为
- 未修改 `apps/desktop/src/renderer/` 下任何 UI 组件

---

## 八、未覆盖的方法（留给后续 Plan）

69 个 legacy 方法分布在：`plugins.*`（老插件管理）、`skills.*`（老技能）、`mcp.*`（MCP 配置）、`providers.*`、`channels.*`、`permissions.*`、`cron.*`、`memory.*`、`experience:*`、`mcpServer*`、`workbench/*`、`files.*`（老文件）、`approvals.*`、`debug/*`、`agent.*`、`config/*` 等。

---

## 九、配置与工具链

- **测试运行器：** 从 `unittest` 迁移到 `pytest`（带 markers: `subprocess`, `sandbox`, `bwrap`, `wsl`）
- **包管理：** 从 pip + requirements.txt 迁移到 `uv`（`uv.lock` 提供确定性依赖）
- **CI：** 新增 `.github/workflows/test.yml`（跨平台 GitHub Actions）
- **路径：** 引入 `miqi.paths` 作为 `MIQI_HOME` / `CODEX_HOME` 的规范解析器
- **配置：** `[observability]` 和 `[approval_policy]` 配置段新增

---

*以上内容由 [Claude Code](https://claude.com/claude-code) 根据 `plan/` 目录下 54 份执行计划文档及 `git diff main..HEAD` 实际代码变更整理。*
