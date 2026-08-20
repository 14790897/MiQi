# #646-v2 设计基线 v3：Frozen Plan + Mutable Todo（2026-08-18，ChatGPT 拍板）

> 上一轮：GPT 冻结版（TaskPolicy 复杂度/风险分离 + mutation gate + Auto Timeline）。
> 本轮（Grok todo 研究后）：ChatGPT 拍板 **A+ 方案**——Task Lifecycle 基础。
> 本文档是 #646-v2 的**设计基线**（实施依据）。

---

## 一、核心定义（一句话）

> **#646 不是"一个计划卡组件"，而是 MiQi 的 Task Lifecycle 基础：
> PlanSnapshot 定义用户批准的目标，TodoState 定义 Agent 当前执行状态，
> Timeline 只是 TodoState 的可视化投影，ActionGuard 负责不可逆操作的最后一道控制。**

## 二、三个东西的分工（不可混）

| 组件 | 回答的问题 | 性质 |
|---|---|---|
| **PlanCard** | "你打算做这件事，我同意不？" | **用户授权点**——一旦 confirm 不可静默修改 |
| **Todo** | "既然同意了，任务做到哪里了？" | **执行状态资源**——Agent 动态维护 |
| **Harness** | 安全边界 + 兜底观察 | 只保证边界，不猜语义进度 |

## 三、Frozen Plan + Mutable Todo（本次最核心）

```text
PlanCard created → PlanSnapshot（用户批准的事实）
        ↓ confirm
TodoState initialized（Plan 步骤 → Todo 初始值）
        ↓
模型 todo_write（增量更新：状态翻转/新增辅助步骤/合并/取消）
        ↓
Timeline（Todo 的 projection——UI 只读 TodoState）
```

**关键规则**：
- **PlanSnapshot 一旦 confirm 不可静默修改**（Approved Plan ≠ Executed Plan 不允许）
- **Todo 可以动态**（pending→in_progress→completed、新增辅助步骤、cancelled）
- **如果改变已批准的核心计划（目标/核心步骤/外部副作用/数据范围）→ Plan mutation
  → 重新进入 PlanCard → 用户重新确认**（Todo 更新检测 high-impact change → PlanCard）
- **merge 只用于执行状态变化**，不用于改目标

## 四、model-preferred, harness-backed（两级数据源）

```text
Primary: TodoState（模型 todo_write）
Fallback: Harness Execution Observations（ToolCallBegin/End）
```
- 模型调 todo_write → progress_source="model"（Timeline 读 Todo）
- 模型没调 → harness 用工具事件维护 observed_progress（**Timeline 不允许空白**）
- 模型重新开始 todo_write → 立即切回 model

## 五、merge 增量更新（直接吸收 Grok）

```json
{"merge": true, "todos": [{"id": "b", "status": "completed"}, {"id": "c", "status": "in_progress"}]}
```
- 只发变化项（翻转状态不用重发内容）
- 自动升级：模型忘写 merge 但意图明显（全是指向已有 id 的状态翻转）→ 自动 merge
- **稳定 ID**（不用数组位置）：`{"id": "research-literature", "content": "...", "status": "pending"}`

## 六、Todo 状态（5 态，比 Grok 多 Blocked）

```text
PENDING / IN_PROGRESS / BLOCKED / COMPLETED / CANCELLED
```
- BLOCKED：等用户输入/等权限/等外部资源（⏸ 等待用户上传样品信息）

## 七、summary_for_prompt（结构化短摘要）

```json
{"total": 6, "completed": 3, "in_progress": ["生成实验报告"], "pending": 2, "blocked": 0}
```
Prompt 展示："3/6 完成；当前：生成实验报告；待执行 2 项。"（token 少、模型看得懂、UI 不受影响）

## 八、modify 循环（Plan v2 → reconcile，不直接 merge）

```text
Plan v1 → 用户 MODIFY → Plan v2 → 用户确认 → replace PlanSnapshot → reconcile TodoState
```

## 九、9 月实施范围（P0/P1/P2）

### P0（必须）
1. **TodoState**：`TodoItem{id, content, status(5态)}`（内存/任务级，9 月可先不持久化跨 session）
2. **todo_write 工具**（merge + summary + is_read_only）
3. **PlanCard confirm → TodoState 初始化**（Plan 步骤 → Todo 初始值，稳定 ID）
4. **Timeline 改读 TodoState**（projection——删掉"猜状态"代码）
5. **Tool events 作为 fallback**（observed_progress，不允许空白）
6. **summary_for_prompt**

### P1
7. **Plan mutation detection**（模型改核心步骤 → PlanCard）
8. **modify → PlanSnapshot v2 → Todo reconcile**
9. **task-level persistence**

### P2（不做）
- 跨 session / global Todo registry / priority scheduler / 复杂 reconcile engine / todo search

## 十、Todo 归属（Task scoped，非 global）

```text
Session ≠ Task
Session（对话容器）→ Task #123（有目标生命周期的 Agent 工作）
  ├─ PlanSnapshot
  ├─ TodoState
  ├─ Action confirmations
  └─ artifacts
```

## 十一、最终架构

```text
User → Mode → Task
  ├── PlanSnapshot → PlanCard → User Confirm（Frozen）
  ├── TodoState（model: todo_write / harness: event fallback）→ Timeline（projection）
  ├── Permission/Safety
  └── ActionGuard → Execute
```

---

## 决策记录（vs 之前基线）

| 决策 | v2 基线 | v3（本轮） |
|---|---|---|
| 步骤所有者 | harness 从工具序列生成 | **模型 todo_write**（harness fallback） |
| Plan 与 Todo | 一体 | **分离**（Frozen Plan + Mutable Todo） |
| 进度数据源 | ToolCall 事件猜 | **TodoState 为主**（projection） |
| 更新方式 | 全量 | **merge 增量** |
| 状态 | 4 态 | **5 态（+BLOCKED）** |
| 持久化 | 会话内 | **Task scoped**（9 月内存级） |
| 优先级 | — | 9 月不做 |
