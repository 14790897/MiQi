# 会话管理

`SessionManager`（`miqi/session/manager.py`）负责对话会话的完整生命周期管理。

## 存储结构

```
sessions/
├── desktop:1747123456789/       # 按 channel:timestamp 命名
│   ├── conversation.jsonl       # 对话历史 (JSON Lines)
│   ├── tracked_files.json       # 修改文件追踪
│   └── .archived                # 归档标记 (空文件)
├── desktop:1747123999999/
│   └── ...
└── feishu:oc_xxx/              # 飞书等外部通道会话
    └── ...
```

## 核心功能

### 会话生命周期

1. **创建**：首次发送消息时自动创建会话
2. **活跃**：持续对话，追加 `conversation.jsonl`
3. **归档**：通过 `.archived` 标记隐藏，零开销
4. **恢复**：删除 `.archived` 即可恢复
5. **删除**：永久删除会话目录

### 会话隔离

- **工作目录隔离**：每个会话的文件操作限定在自身目录
- **上下文独立**：不同会话不共享对话历史
- **工具作用域**：文件工具默认限制在当前会话目录

### 文件追踪

`tracked_files.json` 记录会话中 Agent 修改的文件列表：

```json
{
  "files": [
    {
      "path": "/abs/path/to/file.py",
      "snapshot": ".miqi_snapshots/hash123.snap",
      "modified_at": 1747123456.789
    }
  ]
}
```

前端通过 `sessions:get_tracked_files` IPC 获取列表，提供 diff/revert/accept 操作。

## 会话搜索

通过 FTS5 全文索引实现跨会话搜索：

- SQLite FTS5 引擎
- 实时增量索引
- 支持中文分词
- `session_search` 工具在 Agent 上下文中可用

## 会话压缩

长时间对话可通过以下方式压缩：

- **窗口截断**：`memory_window` 参数控制保留的最近 N 轮对话
- **摘要生成**：LLM 生成对话摘要替代完整历史
- **上下文注入**：将摘要注入到新对话的系统提示词中

## CLI 命令

```bash
miqi session list              # 列出所有会话
miqi session show <id>         # 查看会话详情
miqi session delete <id>       # 删除会话
miqi session archive <id>      # 归档会话
miqi session search <query>    # 搜索会话内容
```
