# 更新日志

完整版本更新日志请参见项目根目录的 [CHANGELOG.md](https://github.com/14790897/MiQi/blob/electronUI/CHANGELOG.md)。

## 最新更新 (2026-05)

### 2026-05-25
- **过滤 `think` 推理块**：ChatConsole 新增 `stripThinkBlocks()`，自动去除 DeepSeek-R1 等推理模型的思考块

### 2026-05-22
- **文件快照修复**：修复快照失败静默吞异常、合并错误删除新建文件、切换会话文件重新出现等问题
- **SkillHub**：CSP 修复 + 技能文件扩展名修复（`.yml` → `.md`）

### 2026-05-22
- **SkillHub 注册中心集成**：新增 SkillHub 标签页，支持浏览/搜索/一键安装公开技能
- **会话归档**：新增存档按钮 + Settings 中的 Archived 标签页

### 2026-05-20
- **WSL2 安装引导**：设置向导新增 WSL2 自动检测和一键安装步骤
- **重新运行配置向导**：Settings 页面新增 Reconfigure 按钮

### 2026-05-18
- **经验面板**：Facts / Rules / History 三标签页
- **MCP 管理页面**：MCP 服务增删改查
- **技能 CRUD**：本地技能创建/上传/删除操作
- **会话管理改进**：目录隔离、文件追踪、标题支持

### 2026-05-15
- **任务追踪系统**：Git 风格的 Task Trace 系统上线（SQLite + FTS5 + 向量嵌入）
- **self_improvement 配置**：新增 `trace_enabled`、`lessons_legacy_inject_enabled` 等配置项
- **CLI 命令**：`miqi trace log/show/search/export/import`

### 2026-05-14
- **记忆系统重构**：新增 memory/session_search/skill_manage 工具
- **Nudge 系统**：轮次级别的记忆和技能持久化提醒
- **SkillCurator**：LLM 驱动的技能生命周期管理
- **经验教训状态机**：active → stale → archived 自动转换

## 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|----------|
| v0.1.4 | 2026-05 | 任务追踪、SkillHub、WSL2 集成、记忆系统重构 |
| v0.1.3 | 2026-04 | 前端 15 页面完整、MCP 集成、Bridge 协议稳定 |
| v0.1.0 | 2026-03 | 初始 Alpha 版本：聊天、提供商、会话管理 |
