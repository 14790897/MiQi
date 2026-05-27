# 记忆系统

MiQi 的记忆系统采用三层架构，确保 Agent 在跨会话、跨项目中保持连续性和学习能力。

## 三层架构

| 层级 | 存储位置 | 作用域 | 写入方式 | 说明 |
|------|----------|--------|----------|------|
| Cloud Memory | 服务端数据库 | 全局 | 自动学习 | 用户长期偏好，服务端注入 |
| User Memory | `~/.workbuddy/MEMORY.md` | 跨项目 | 手动 / Agent 写入 | 用户级强制规则 |
| Workspace Memory | `.workbuddy/memory/` | 单项目 | Agent 自动写入 | 项目日志 + 关键决策 |

## Workspace Memory

### 文件结构

```
{workspace}/.workbuddy/memory/
├── YYYY-MM-DD.md      # 每日工作日志（追加模式）
└── MEMORY.md           # 项目长期记忆（覆盖+整理）
```

### 日志格式

```markdown
## 2026-05-27

- 完成 XXX 功能的开发
- 修复了 YYY bug（原因：ZZZ，方案：WWW）
- 选用了 AAA 框架处理 BBB 问题
```

### 关键规则

- 每日日志仅追加，不覆盖
- 30 天以上的日志自动归档到 MEMORY.md
- 不记录敏感信息
- 项目级偏好自动写入 MEMORY.md

## 自改进系统

### 经验教训（Legacy Lessons）

Agent 完成任务后通过 Nudge 系统自动总结经验。经验具有三状态生命周期：

```
active → stale → archived
```

- **active**：活跃经验，可能注入 Agent 上下文
- **stale**：陈旧经验，降低引用权重
- **archived**：已归档，不再注入

!!! warning "注意"
    自 2026-05-15 起，`lessons_legacy_inject_enabled` 默认设为 `false`。经验教训不再自动注入 Agent 提示词，取而代之的是基于 Task Trace 的相似历史上下文机制。

### 技能管理

- **SkillCurator**：LLM 驱动的技能生命周期管理
- **自动归档**：长期未使用的技能自动标记为 stale
- **Nudge 提醒**：定期提示 Agent 评估和更新技能

## 记忆工具

Agent 可通过以下工具操作记忆：

| 工具 | 操作 | 说明 |
|------|------|------|
| `memory_read` | 读取 | 搜索并读取相关记忆 |
| `memory_write` | 写入 | 创建新记忆条目 |
| `memory_append` | 追加 | 向已有记忆追加内容 |
| `session_search` | 搜索 | FTS5 全文搜索历史会话 |
