# #646-v2 当前情况汇报（2026-08-17，求 GPT 评审）

## 一、背景回顾

#646 = 执行前确认。经过三轮评审（你的 8/15 拍板），方向定为：**#646 不是「工具执行前确认」，
而是「任务启动授权」**——Agent Task Planning System（任务计划决策点）。

## 二、当前实现状态（#719 分支，基于 #711 合并后的 develop）

### 已实现（Phase 1 + Phase 2 核心）

| 组件 | 状态 |
|---|---|
| `ask_user_plan_confirm` 工具（title/goal/steps/permissions schema） | ✅ 已实现（模型主动腿） |
| `TaskState` 状态机（PLANNING→WAIT_CONFIRM→RUNNING→WAIT_DANGEROUS_ACTION→COMPLETED/CANCELLED） | ✅ 已实现 |
| 前端 `PlanCard` 组件（计划+权限+[开始执行]；running 步骤进度；completed/cancelled） | ✅ 已实现（未做 Kimi 视觉评审——**Kimi API 预算超限 429，无法多模态评审**） |
| `TaskPolicy`/`ActionPolicy` 双策略（`miqi/execution/task_policy.py`） | ✅ 已实现 |
| **harness 强制计划卡**（turn_runner 插桩：模型首轮 tool_calls 后、第一个工具执行前，TaskPolicy 判定 → 强制弹卡） | ✅ 已实现 |
| 工具→用户语言映射（TOOL_DESCRIPTION：web_search→搜索公开资料 等） | ✅ 已实现 |
| 协作（允许编辑）模式：文件写入自动放行（approval_policy file_write=never），exec/上传仍确认 | ✅ 已实现 |
| 工具分工：ask_user_confirm_card 收紧为危险动作专用（上传/支付/删除/外发）；多步骤计划明确指向 ask_user_plan_confirm | ✅ 已实现 |
| 错误文案中文化（sanitizeUiMessage + 后端 ErrorEvent 3 处） | ✅ 已实现 |

### TaskPolicy 当前规则（含实测边界修正）

```python
def should_plan_confirm(tool_calls, *, mode="collaboration", uses_skill=False, expected_minutes=0.0):
    if mode == "autonomous": return False          # 自动模式不弹（非阻塞展示）
    if uses_skill: return True                      # Skill 执行弹
    return task_risk_score(tool_calls) >= TaskIntentRisk.MODIFY_LOCAL
    # 即：纯读任务（搜索/读论文，无论多少工具）不弹；
    #     含写文件/执行/上传（或读+写混合）弹
```

风险等级：READ_ONLY=0 / MODIFY_LOCAL=1（write_file/edit/apply_patch）/ EXECUTE=2（exec）/
EXTERNAL_EFFECT=3（upload/delete/payment/外发）。

## 三、实测结果（用户实机测试，3 轮）

### 第 1 轮（Phase 1 后，仅模型主动腿）
- 结果：模型调了**旧工具** ask_user_confirm_card（没用新工具）——弹的是危险动作卡样式，流程顺序错（先审批后计划）
- 根因：两个工具 description/指令重叠，模型选错

### 第 2 轮（工具分工收紧后）
- 结果：模型**完全不调用任何确认工具**，直接文本问「要不要保存成文档」——计划卡没出现
- 结论：**模型主动调用不可靠**（同一天两次行为不一致）→ 触发 Phase 2 harness 强制

### 第 3 轮（harness 强制后）
- 结果：**计划卡出现了** ✓（harness 生效，标题=用户请求摘要）
- 新问题 1：**步骤名全空白**（显示 01 02 03 04 无文字）——KUN tool_call 的 name 提取缺失 → 已修（空名防御）
- 新问题 2（用户观点）：**「强制弹窗一定要有边界」**——纯搜索任务（"搜索 MOF-5 合成方法并抓取 2 个网页详情"，4 个读工具）不该弹计划卡 → 已修（纯读不弹）
- 待验证：边界修正后纯搜索是否真的不弹、含写任务是否弹且有步骤文字

## 四、当前问题与待决策项

### 1. Kimi 视觉评审无法执行（硬阻塞）
- 用户的 Kimi key（sk-c7u...QWBV）所属项目 proj-6138fdf0 预算超限，**API 返回 429**（平台拒绝，与模型无关，kimi-latest/k2.6 都试过）
- 备选：Hermes 配置里有 siliconflow 的 GLM-5.2（支持视觉）可做参考评审——**未获用户同意使用**（用户坚持要 Kimi）
- PlanCard/ConfirmCard UI 已按 Claude Code 风格自查改了一版，但**没有经过多模态视觉评审**——用户对 UI 质量要求高（此前确认卡经 Kimi 三轮迭代）

### 2. 待实现（GPT 8/15 拍板中的剩余项）
| 项 | 状态 | 说明 |
|---|---|---|
| 自动模式非阻塞计划展示 | ❌ 未做 | GPT：auto 模式弹「AI 计划」展示不阻塞（📋 正在执行: 步骤 ✓⟳），不是确认 |
| Action Guard 强制（危险动作最后确认） | ⚠️ 半做 | ask_user_confirm_card 承担（模型主动），**harness 侧强制拦截（upload/delete/payment 执行前必弹）未接** |
| 长任务进度实时推送（TaskState → 前端 running 步骤状态） | ❌ 未做 | PlanCard running 态组件有，但后端事件推送未接 |
| TaskPolicy 复杂度阈值（complexity_score） | ⚠️ 已实现但**未启用** | 纯读不弹后复杂度对纯读无意义；Skill 时长等元数据接入后启用 |
| 审批设置 UI 重构（自主执行策略命名/普通用户只看 Mode 单选） | ❌ 未做 | GPT：隐藏高级设置，普通用户只有「AI 自主程度」 |
| 白名单 → 允许规则（工具+场景） | ❌ 未做 | GPT：科研检索（web_search/web_fetch+学术网站+本会话）替代 url 清单 |

### 3. 待决策（需要你拍板）
1. **边界细节**：纯读不弹是否够？「多个来源总结」（读 10 篇后不写文件、纯文本总结）弹不弹？
   ——现在不弹（纯读）——但用户可能希望这种"大任务"弹一次确认意图
2. **harness 弹卡的步骤来源**：目前只有工具序列（用户语言）——模型不写计划。
   要不要两阶段（先 Intent 卡「查看计划」→ 模型生成详细计划 → 确认）？——你 8/15 说演示不需要
3. **自动模式**：非阻塞展示的实现方式（后端事件 → 前端 PlanCard 展示态）——现在还没接
4. **#684 去留**：按你拍板「#684 降级为 Action Guard 不删除」——是否需要在 #719 合入前把
   #684 的 Action Guard 部分（审批跳过/危险动作拦截）先并过来？

## 五、9 月演示目标链路（确认是否仍是验收标准）

```
用户: 帮我完成 MOF 调研并上传 Qraft
→ 📋 Plan Card（搜索/分析/生成/上传 + 权限）[开始执行]
→ 执行动画（✓ 搜索论文 / ✓ 生成报告 / ○ 上传）
→ ⚠ Upload Action Card（确认上传）
→ 完成
```

## 六、测试与验证现状

- pytest：task_policy 5 + turn_runner 22 + ask_user_confirm 29 = 56 passed
- vitest：ConfirmCard 15 + PlanCard 3 = 18 passed（+ 全量 178）
- tsc web 0 错误
- 真机：第 3 轮实测计划卡出现（边界修正后待重测）
