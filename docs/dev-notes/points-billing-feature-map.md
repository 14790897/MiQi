---
name: points-billing-feature-map
description: 平台积分计费功能的架构地图——计费闸门挂载点、每会话去重、fail-closed 语义、config.billing、前端事件流
type: project
---

平台积分计费（已合并 develop，PR #915 / merge acad0656，2026-09-03）：登录后会话首次执行工具/技能前扣 30 分，普通对话不扣，余额不足阻止任务。产品规则由用户确认：触发点=会话首次执行工具/技能；时机=开始前扣、不足则阻止；展示=设置页 + 聊天区提示。

**核心组件**：
- `miqi/kun_runtime/billing.py`：PointsBilling（读 workspace/.qraft/token.json，POST /oauth2/points/deduct；40003→阻止、401→重读 token 文件重试、网络→重试后 fail-closed）；去重键=scope（live 传 session_id，子代理同会话不重复扣；KUN 退化 thread_id）；内存 + `.qraft/billing.json` 持久化；未扣成不落标记（充值后可重试）
- live 路径挂 `miqi/execution/orchestrator.py`（审批通过后、执行前，`OrchestrationResult.BILLING_BLOCKED`），装配在 `miqi/runtime/services.py`（`config.billing.enabled/cost_per_task/source`，默认开 30 分）；KUN 路径挂 `miqi/kun_runtime/tool_host.py`
- 事件：`PointsBillingEvent`（protocol/events.py）→ bridge/loop.py drain 转发 `progress`（stream=points）→ ChatConsole 展示
- 桌面主进程：QraftClient.getPointsBalance/deductPoints；QraftService.fetchPointsBalance 缓存；`qraft:pointsBalance` IPC；token 文件新增 baseUrl 字段（billing.py 用，auth.py 忽略）

**关键点**：未登录（无 token 文件）不拦不扣——登录收口是 #835 的活；KUN AgentLoop 仍未实例化（见 [confirm-card-two-runtime-map](confirm-card-two-runtime-map.md)），闸门必须在 live orchestrator 上才能生效；测试 60 个用例在 tests/kun_runtime/test_billing.py + test_tool_host.py + tests/execution/test_orchestrator.py。

**2026-09-03 实测记录**：真实环境全链路验证通过——测试账号 18500000000（MiQi测试）经完整 OAuth2 登录 → PointsBilling.ensure_billed → 平台扣 30 → 余额 1000→970 → 本地 billing.json 落标记。注意平台 quirks：balance 接口在发放积分后才会反映真实值；发放不计入 totalEarned（一直显示 0）；测试账号密码 1q2w3e4R、测试 client_secret 默认 miqi123456（types.ts 硬编码，转正式前移除）。

**2026-09-04 状态栏积分余额**（未提交 PR，worktree claude/silly-bardeen-e0ff7f）：`StatusBar.tsx` 用 `useQraftStatus`（hooks/useQraftStatus.ts，status + onStatusChanged）读 `status.points`（QraftService.fetchPointsBalance 缓存后 emitStatus 推送）；登录后 points 为 undefined 时自动 `qraft.pointsBalance()` 拉取，失败每 30s 重试直到成功/退出；显示「积分 N」硬币图标（data-testid=statusbar-points），点击经 App.tsx 传的 onOpenPoints 跳设置→qraft tab；未登录不渲染。smoke mock（tests/smoke/mocks.ts）的 pointsBalance 已改为镜像主进程行为（成功后缓存进 _qraftStatus 并 fire qraftStatus 事件），smoke 套件新增登录/未登录两用例。⚠️ 该 worktree 的 develop（ddfe0591）尚未合 #936，Slurm 扣费后主进程不推 statusChanged，等 #936 落地后其 charge 路径需更新 pointsBalance 缓存 + emitStatus 才能让状态栏随扣费实时刷新。
