---
name: ignore-legacy-runtime-path
description: 用户明确要求：legacy 运行时路径以后不用管——新功能只做 KUN runtime，不再维护 legacy task_runner/resolver 路径
type: feedback
---

用户明确指示（2026-08-15，PR #711 上下文）：**legacy（非 KUN）路径以后不用管**。

背景：项目存在两套运行时——KUN runtime（miqi/kun_runtime/，AgentLoop + gate）和 legacy 路径（miqi/runtime/task_runner.py + TurnRunner + ToolRegistry + miqi/agent/user_input_resolver.py 的桌面 resolver 桥）。桌面 chat.send 目前实际走 legacy 路径，但用户在确认卡功能（#646）相关的大量 legacy 修复工作之后明确表态 legacy 不再维护。

**Why:** 用户在确认卡功能上投入了大量 legacy 路径修复（resolver 会话隔离、remember 复用、工具白名单、提示词注入等），认为 legacy 是历史包袱，未来重心在 KUN runtime。

**How to apply:**
- 新功能/新修复默认只做 KUN runtime 路径（miqi/kun_runtime/），不做 legacy（miqi/runtime/task_runner.py、turn_runner.py、agent/user_input_resolver.py、agent/tools 的 resolver 注入）
- legacy 路径的 bug 报告可以忽略或只做最小修复，不主动加固
- 涉及"桌面路径 vs KUN 路径"的讨论时，以 KUN 为准；相关遗留背景见 [confirm-card-two-runtime-map](confirm-card-two-runtime-map.md)
