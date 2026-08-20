# #646-v2 设计基线 v3.2：收敛修正（2026-08-18，ChatGPT 三轮拍板）

> v3.1 方向冻结 + 本轮 7 项收敛修正。
> **核心原则（本轮）**：P0 做"计划冻结 + 状态投影 + 模型进度协议"，
> **不做"任务管理系统"**。保持克制。

---

## 一、v3.2 修正总览

| # | v3.1 | v3.2 |
|---|---|---|
| 1 | Task 一级对象 | ⬇️ **ExecutionContext**（plan_snapshot + todo_state + action_history）——P0 不要 Task 生命周期 |
| 2 | PlanSnapshot: goal/steps | + **approved_scope**（sources/artifacts/external_actions——mutation detection 依据） |
| 3 | TodoItem.kind: plan/auxiliary | + **observed**（fallback 也是 Todo——source: model/harness） |
| 4 | Primary/Fallback 双源 | **单写入模型**：所有条目进 TodoState（source 标记），Timeline 只读 TodoState.items |
| 5 | todo_write 拒绝返回 error | **error-as-output**（`{status:"rejected", reason:"PLAN_MUTATION_REQUIRES_CONFIRMATION", suggestion:"ask_user_plan_confirm"}`） |
| 6 | 完成状态 | completed = **model declared**（P0）；verification(declared/observed/verified) **P1** |
| 7 | P0 顺序 | 重排（见下） |

## 二、P0 数据模型（无 Task）

```python
@dataclass
class PlanSnapshot:
    plan_id: str
    goal: str
    steps: list[PlanStep]        # {id, content}
    approved_scope: Scope        # 新增——mutation detection 依据
    plan_version: int = 1
    approved_at: str
    approved_by: str = "user"

@dataclass
class Scope:
    sources: list[str]           # ["academic papers"]
    artifacts: list[str]         # ["report.docx"]
    external_actions: list[str]  # ["qraft upload"]

@dataclass
class TodoItem:
    id: str
    content: str
    status: str                  # pending/in_progress/blocked/completed/cancelled
    kind: str                    # plan | auxiliary | observed
    source: str                  # model | harness
    blocked_reason: str | None = None

@dataclass
class TodoState:
    task_id: str                 # 内部标识（execution context 的 id）
    revision: int = 0
    items: list[TodoItem]

@dataclass
class ExecutionContext:          # 替代 Task（P0）
    ctx_id: str
    session_key: str
    plan_snapshot: PlanSnapshot | None
    todo_state: TodoState
    action_history: list          # ActionGuard 确认记录
```

## 三、单写入模型（Timeline 只有一个源）

```text
模型 todo_write → TodoState.items[i].source="model"
harness ToolEvent → TodoState.items[i].source="harness"（kind="observed"）
Timeline → 只读 TodoState.items（不区分来源——UI 不需要知道）
```

- 模型没调 todo_write：harness 用工具事件**写入** TodoState（kind=observed, source=harness）
- 模型重新开始 todo_write：对应条目 source=model（覆盖 observed 状态）
- **Timeline 永远只有一个数据源**（不再有两个列表/两个 projection）

## 四、approved_scope（mutation detection 的判据）

```text
模型："我顺便把数据上传 GitHub"
→ 不是 Todo change——是 approved_scope violation（external_actions 只有 qraft upload）
→ 必须重新 PlanCard
```

## 五、todo_write 契约

```python
todo_write(todos: [TodoPatch], merge: bool = True) -> TodoWriteResult
# TodoPatch = {id, status?} | {id, content, kind:"auxiliary"|"observed", status?}
# 规则：
#  - merge=True 默认；自动升级（全指向已有 id 的状态翻转）
#  - plan item 改 content → 返回 rejected（error-as-output，不抛异常）：
#      {"status":"rejected","reason":"PLAN_MUTATION_REQUIRES_CONFIRMATION",
#       "suggestion":"ask_user_plan_confirm"}
#  - revision += 1
#  - 回传 summary（total/completed/in_progress/pending/blocked）
```

## 六、PlanCard 确认后的固定协议（防 Timeline 乱）

```text
用户点「开始执行」
  ↓
system inject（固定提示词）：
  "Your approved plan has been initialized.
   Maintain progress using todo_write."
  ↓
模型第一轮必须先：
  todo_write([{id:"step-1", status:"in_progress"}])
  ↓
然后才执行工具
```

（否则模型可能最后才补 todo——Timeline 又乱）

## 七、P0 实施顺序（重排）

| 步骤 | 内容 | 可运行状态 |
|---|---|---|
| Step 1 | PlanSnapshot + TodoState + ExecutionContext 数据模型（无 Task） | 单元测试 |
| Step 2 | PlanCard confirm → PlanSnapshot 冻结 + TodoState 初始化（plan-kind） | 集成：确认后 Todo 出现 |
| Step 3 | Timeline 只读 TodoState（todo_state_changed 事件 + revision） | UI 显示真实 Todo |
| Step 4 | ToolEvent → TodoState（kind=observed, source=harness）——fallback 单源化 | 模型不用 todo_write 也有进度 |
| Step 5 | todo_write + merge + error-as-output + summary | 模型驱动进度 |
| Step 6 | 确认后提示词注入（第六节协议） | 完整闭环 |

## 八、9 月演示闭环（最终形态）

```text
用户：帮我完成 MOF 调研并上传 Qraft
  ↓ PlanCard（目标/步骤 1-4/权限 网络+文件+上传）
  ↓ 用户确认
  ↓ system inject: "Maintain progress using todo_write"
  ↓ 模型 todo_write([1:in_progress]) → Timeline ⟳ 搜集论文资料
  ↓ 执行 → todo_write([1:completed, 2:in_progress]) → Timeline ✓⟳
  ↓ ActionGuard：即将上传 Qraft → 确认
  ↓ 完成
```

## 九、P1（冻结）

- verification（declared/observed/verified——completed 需 ToolResult 证据）
- plan mutation detection 自动化（approved_scope 比对）
- modify → PlanSnapshot v2 → Todo reconcile
- Task 一级对象 + task-level persistence

## 十、P2（不做）

- 跨 session / global Todo registry / priority / scheduler / todo search / 复杂 reconcile engine

---

## 决策记录（累计）

1. Todo ≠ Authority（Agent 报告的状态，不是安全/执行事实）
2. Plan ≠ Todo（静态批准语义 vs 动态执行状态）
3. Todo ≠ Scope Expansion（辅助步骤允许；目标/范围/副作用必须重新确认）
4. Tool Events ≠ Todo（事实 vs 语义——但**同入 TodoState**，source 区分）
5. Timeline ≠ State（projection）
6. **P0 ≠ 任务管理系统**（ExecutionContext 够用；Task/Persistence P1）
