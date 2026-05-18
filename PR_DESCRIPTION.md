# feat/new-func-development → master PR

## 概述

本分支包含 MiQi Desktop 自 master 以来的全部开发成果，涵盖 Desktop UI 重构、经验/Trace 系统、会话工作区、记忆系统增强、以及一系列 Bug 修复。

---

## 一、Desktop UI

### Provider 设置页面改进
- 页面标题从 "Provider" 改为"模型提供商"
- Provider 名称全面中文化（含硅基流动、通义千问、月之暗面等）
- 编辑弹窗打开时 API Base URL 自动预填默认值
- 编辑弹窗新增每个 Provider 的推荐模型标签（可点击填入）
- Provider 列表行显示脱敏 API Key 提示（前4…后4）和当前生效模型

### 会话历史加载修复
- 修复启动竞争条件：bridge 就绪前加载历史返回空且不重试（B1）
- 修复点"New Chat"调用 `/new` 命令销毁旧会话磁盘数据（B2）
- 修复侧边栏 sessions.list() 在 bridge 就绪前执行导致始终显示"No sessions"（B3）

### 经验页面
- 新增 Experience 页面，含 Facts / Rules / History 三个 Tab
- ExperienceStore 统一 facade，聚合 facts / rules / traces 三个维度
- 经验条目支持 IPC list / delete / toggle / search

### 技能页面
- 新增 Skills CRUD：创建、上传、删除；内置技能路径校验

### MCP 页面
- 新增 MCPs 页面，支持 list / upsert / delete IPC 和 bridge handler

### 设置页面重构
- Providers / Channels / Approvals / Cron 合并进 Settings 多 Tab 布局
- 侧边栏精简至 6 个导航项

### 命令审批中心
- 完整的 Command Approval Center：历史记录、白名单管理、倒计时确认

### 其他 UI 改进
- TopBar 组件 + 会话状态过滤器
- Chat Console 新增文件追踪解析和预览面板
- 侧边栏集成会话列表，支持 refreshKey 自动刷新
- 全局右键 Context Menu（聊天、会话、工作区、记忆页）
- 内存/工作区/技能页面支持 create / delete / rename / copy

---

## 二、后端 / Agent

### Trace 生命周期修复
- 每轮用户消息自动开启 trace，task_name 从消息内容生成（不再硬编码 "session"）
- `_run_agent_loop` 捕获 tools_used，在 finally 块自动关闭 trace 并写入 outcome
- 更新 TaskBeginTool 描述为"覆盖自动生成的 task_name"语义

### 会话工作区
- 新增 session-scoped 工作目录：文件默认写入 `sessions/{key}/files/`
- 快照存储于 `sessions/{key}/snapshots/`
- Git workspace 自动追加 `sessions/` 到 `.gitignore`
- 系统提示中告知 Agent 当前会话工作目录

### 记忆系统增强（Phases 1–12）
- 新增 MemoryTool、session_search 工具、skill_manage 工具
- Lesson 生命周期管理：stale / archive 自动转换、unlearn 操作
- Rule 注入默认启用（confidence threshold = 3）
- Skill curator 自动管理工作区技能生命周期
- Nudge 系统：定期记忆/技能保存提醒（已完成后清理）
- 修复 JSON 错误检测、显式记忆提取、disabled-lesson 保留、compact 排序等

### Trace 系统（Phases 1–6）
- Phase 1：TraceStore 存储层（SQLite + OPEN_TASKS.json）
- Phase 2：Agent 工具（task_begin / task_end / trace_search）
- Phase 3：Context 注入（历史 trace 注入系统提示）
- Phase 4：nudge 自动关闭
- Phase 5：lesson 迁移
- Phase 6：CLI（`miqi trace log/show/search/export/import`）
- 新增 record_step()、parent_hash 索引、get_lineage 遍历

---

## 三、Bug 修复 & 工程

- 修复 command_approval 模块缺少 `init_history_file` 调用
- 修复 ExperienceStore singleton 缓存 + 跳过 open-task recovery 副作用
- 修复 ContextMenu 命名导入和 render-props 模式
- 修复 bridge stderr 日志流和 app quit 崩溃
- 修复 HTML 嵌套错误、null 属性检查
- 支持 bundled bridge 可执行文件打包
- Session directory 重构：snapshot 去重、目录结构规范化
- 文档全面对齐代码实现（CLI 命令、配置字段、架构描述）

---

## 文件变更统计（相对 origin/master）

| 模块 | 变更类型 |
|------|---------|
| `apps/desktop/src/renderer/` | 大量新增/修改（UI 页面、组件） |
| `apps/desktop/src/main/` | 修改（IPC handlers、bridge） |
| `apps/desktop/src/shared/ipc.ts` | 修改（类型定义扩展） |
| `miqi/agent/` | 修改（loop、tools、memory、trace） |
| `miqi/bridge/server.py` | 修改（新增大量 handler） |
| `miqi/session/` | 修改（工作区、快照） |
| `miqi/providers/` | 无改动 |
| `miqi/config/schema.py` | 修改（新增配置字段） |
| `docs/` | 全面重写（与代码对齐） |
| `tests/` | 新增多个测试文件 |
