# #646-v2 设计基线 v3.1：Frozen Plan + Mutable Todo（2026-08-18，ChatGPT 二轮拍板）

> v3 认可为基线方向，v3.1 补充 6 条硬约束后冻结。
> 核心：**Frozen Plan + Mutable Todo**——"用户批准什么"与"Agent 做到哪"是两个独立对象。

---

## 一、五个对象的职责（本版核心——不许混淆）

```text
PlanSnapshot = 用户批准事实（authority）
TodoState    = Agent 语义状态（execution state——不是事实！）
ToolEvent    = Runtime 事实（factual）
Timeline     = TodoState 的 projection（不拥有独立状态）
ActionGuard  = 安全事实（看真实 ToolResult，不信 Todo 的 completed）
```

**关键裁定：Todo 不是 Primary Truth！**
- Todo = semantic（模型报告的执行状态——模型可能说谎/记错）
- ToolEvent = factual（运行时真实发生了什么）
- Primary **presentation** = TodoState；Authoritative **safety** = Harness；Execution **fact** = Tool events

## 二、Todo 的权力边界（最重要）

```
Todo 可以：✓ 改状态 ✓ 加辅助步骤(kind=auxiliary) ✓ cancel ✓ block
Todo 不可以：✗ 改用户批准的目标 ✗ 偷偷扩大数据范围
            ✗ 新增外部副作用 ✗ 代替 ActionGuard ✗ 代替 ToolResult
```

**Todo 绝不能自行获得扩大任务范围的权力。**

## 三、plan / auxiliary 显式区分

```ts
TodoItem {
  id: string          // 稳定 ID（不用数组位置）
  content: string
  status: PENDING | IN_PROGRESS | BLOCKED | COMPLETED | CANCELLED
  kind: "plan" | "auxiliary"
  blockedReason?: "waiting_user" | "waiting_permission" | "waiting_external"
                 | "execution_failed" | "unknown"
}
```
- **plan item**：修改语义需要重新确认
- **auxiliary item**：可动态增加（"下载补充 PDF"是完成 plan 步骤的辅助——允许）
- 模型把 plan 步骤升级成新目标（"上传全部原始数据"）→ **scope expansion → 重新 PlanCard**

## 四、merge 限制（吸收 Grok + 加闸）

```ts
type TodoPatch =
  | { id: string; status: TodoStatus }                          // 状态翻转 OK
  | { id: string; content: string; kind: "auxiliary"; status?: TodoStatus }  // 只加辅助
```
- **已有 plan item + 修改 content → 直接拒绝**：`PLAN_MUTATION_REQUIRES_RECONFIRMATION`
- merge 只用于执行状态变化，不得通过 content 偷偷改核心任务

## 五、版本号（planVersion + todoRevision）

```text
task-123 { planVersion: 1, todoRevision: 7 }
```
- todo_write 每次 → `revision += 1`（解决并发/重复结果/stale/React 事件顺序）
- modify → `planVersion += 1` → `reconcile(planVersion=2)` → Todo 重新对齐
- 未来可回溯：Plan v2 → todo rev 9 → action confirm 3

## 六、BLOCKED 带 reason（不只是暂停）

```text
⏸ 等待用户上传样品信息（blockedReason=waiting_user）
```
（不是"⏸ 任务暂停"——用户要知道为什么）

## 七、Timeline = Todo projection（ToolEvent 保留为观察层）

```text
TodoState → Timeline（主）
ToolEvent → Execution Observation Layer（fallback——不允许空白）
```
- 模型维护 Todo：progress_source="model"
- 模型没调：harness 用工具事件产生 observed_progress（progress_source="observed"）
- 模型重新开始：立即切回 model

## 八、ActionGuard 不信 Todo

```text
ToolResult SUCCESS + TodoState COMPLETED → completed
```
- Todo 决定"Agent 认为任务状态如何"；Runtime 决定"系统事实上执行了什么"
- 上传完成 = 必须看真实 upload ToolResult（不能 todo.completed 就假设成功）

## 九、TaskResult（轻量，概念先行）

```ts
TaskResult { status: "completed" | "failed" | "cancelled",
             planVersion, todoRevision, artifacts: ArtifactRef[] }
```
Task 完整形态：PlanSnapshot + TodoState + ActionHistory + Artifacts + TaskResult
（#674 的 artifact/sha256/upload 自然接进来）

## 十、todo_write 不强制

- Prompt：复杂任务（3+ 步骤）建议使用——**是能力不是门槛**
- Harness：不要求（不用就 Tool event fallback）
- TaskPolicy 复杂度公式不变（Grok 的 3+ steps 只是 prompt guidance，不取代我们的复杂度）

## 十一、持久化定位

- P0：Task object（内存）→ TodoState（挂在 Task 下，**不是纯 UI memory**）
- P1：task-level persistence
- P2：cross-session

## 十二、Session ≠ Task

```text
Session（对话容器）
├── Task A: MOF research（plan + todo + artifacts）
└── Task B: fix React bug（plan + todo + artifacts）
```

## 十三、5 条决策记录（挡架构漂移）

1. **Todo ≠ Authority**——Agent 报告的状态，不是安全/执行事实来源
2. **Plan ≠ Todo**——PlanSnapshot 静态批准语义；TodoState 动态执行状态
3. **Todo ≠ Scope Expansion**——辅助步骤允许；目标/核心步骤/数据范围/副作用必须重新确认
4. **Tool Events ≠ Todo**——Runtime 事实 vs 语义描述，不互相替代
5. **Timeline ≠ State**——projection，不拥有独立任务状态

## 十四、最终架构图

```text
SESSION → TASK
  ├── PLAN SNAPSHOT（用户批准事实）→ PLAN CARD
  ├── TODO STATE（Agent 执行状态）→ TIMELINE
  │        ▲
  │   todo_write（semantic） / Tool Events（factual）
  └── SAFETY / ACTION（系统约束）→ GUARDS
```

## 十五、实施顺序（P0，按 ChatGPT 调整后的顺序）

| 步骤 | 内容 |
|---|---|
| P0-1 | **Task / PlanSnapshot / TodoState 数据模型**先确定（含 planVersion/todoRevision/kind/blockedReason） |
| P0-2 | **Plan confirm → 初始化 Todo**（Plan 步骤 → plan-kind Todo，稳定 ID） |
| P0-3 | **Timeline 直接读 TodoState**（projection——删"猜状态"代码） |
| P0-4 | **Tool event fallback**（observed_progress，不允许空白） |
| P0-5 | **todo_write + merge**（含 plan-item content 拒绝闸） |
| P0-6 | **summary_for_prompt**（结构化短摘要） |

> 顺序原因：先做 todo_write 容易误写成"Todo 自己是任务系统"——先确定数据模型和投影关系。

## 十六、v3 → v3.1 变更记录

| 项 | v3 | v3.1 |
|---|---|---|
| Todo 定位 | Primary + Fallback | **semantic（非事实）**；ToolEvent=factual |
| TodoItem | id/content/status | + **kind(plan/auxiliary)** + blockedReason |
| merge | 吸收 Grok | + **plan-item content 修改拒绝闸** |
| 版本 | — | + **planVersion/todoRevision** |
| 权限边界 | Plan 不可静默改 | + **Todo 不可扩大范围**（5 条决策记录） |
| TaskResult | — | + 概念先行 |
