# Bridge 通信

`miqi/bridge/server.py`（约 2300 行，57 个 handler）是连接 Electron 前端和 Python 后端的核心通信层。

> **AppServer 层**: Bridge Server 内部运行 AppServer（`miqi/runtime/app_server.py`），提供传输无关的类型化协议层。详见 [架构文档](../architecture.md)。

## 通信协议

Bridge 通过 **stdin/stdout** 使用 **JSON-line** 格式进行双向通信：

### 消息格式

```json
// Request — 前端 → 后端
{"id": "uuid-abc123", "method": "chat:send", "params": {"message": "Hello", "sessionId": "desktop:1747..."}}

// Response — 后端 → 前端
{"id": "uuid-abc123", "result": {"ok": true}}

// Event — 后端 → 前端 (流式推送)
{"id": "uuid-abc123", "type": "progress", "data": {"text": "我正在思考..."}}
```

### 协议规则

- 一行一个 JSON 对象（`\n` 分隔）
- `id` 关联请求与对应的流式事件
- 同步响应在请求处理完成后立即返回
- 流式事件在长时操作中持续推送

## Handler 完整列表

### Chat（聊天）

| Method | Handler | 说明 |
|--------|---------|------|
| `chat:send` | `handle_chat_send` | 发送消息，启动 Agent 处理 |
| `chat:abort` | `handle_chat_abort` | 中断当前 Agent 执行 |

### Sessions（会话）

| Method | Handler | 说明 |
|--------|---------|------|
| `sessions:list` | `handle_sessions_list` | 列出所有会话 |
| `sessions:get` | `handle_sessions_get` | 获取会话详情 |
| `sessions:delete` | `handle_sessions_delete` | 删除会话 |
| `sessions:archive` | `handle_sessions_archive` | 归档会话 |
| `sessions:unarchive` | `handle_sessions_unarchive` | 取消归档 |
| `sessions:get_tracked_files` | `handle_sessions_get_tracked_files` | 获取会话追踪文件 |
| `sessions:clear_tracked_files` | `handle_sessions_clear_tracked_files` | 清除追踪 |

### Config（配置）

| Method | Handler | 说明 |
|--------|---------|------|
| `config:get` | `handle_config_get` | 获取全局配置 |
| `config:set` | `handle_config_set` | 更新全局配置 |

### Providers（提供商）

| Method | Handler | 说明 |
|--------|---------|------|
| `providers:list` | `handle_providers_list` | 列出提供商 |
| `providers:test` | `handle_providers_test` | 测试连接 |
| `providers:update` | `handle_providers_update` | 更新配置 |

### Memory（记忆）

| Method | Handler | 说明 |
|--------|---------|------|
| `memory:facts` | `handle_memory_facts` | 获取记忆快照 |
| `memory:lessons` | `handle_memory_lessons` | 获取经验教训 |
| `memory:delete_lesson` | `handle_memory_delete_lesson` | 删除经验 |
| `memory:toggle_lesson` | `handle_memory_toggle_lesson` | 切换经验状态 |

### Skills（技能）

| Method | Handler | 说明 |
|--------|---------|------|
| `skills:list` | `handle_skills_list` | 列出本地技能 |
| `skills:create` | `handle_skills_create` | 创建技能 |
| `skills:upload` | `handle_skills_upload` | 上传/安装技能 |
| `skills:delete` | `handle_skills_delete` | 删除技能 |

### Files（文件操作 + 版本控制）

| Method | Handler | 说明 |
|--------|---------|------|
| `files:diff` | `handle_files_diff` | 对比修改 |
| `files:revert` | `handle_files_revert` | 恢复快照 |
| `files:accept` | `handle_files_accept` | 接受修改 |

### MCPs（MCP 管理）

| Method | Handler | 说明 |
|--------|---------|------|
| `mcps:list` | `handle_mcps_list` | 列出 MCP 服务 |
| `mcps:upsert` | `handle_mcps_upsert` | 添加/更新 MCP |
| `mcps:delete` | `handle_mcps_delete` | 删除 MCP |

### 其他

| Method | Handler | 说明 |
|--------|---------|------|
| `python:check` | `handle_python_check` | Python 环境检测 |
| `wsl:check` | `handle_wsl_check` | WSL2 状态检测 |
| `wsl:install` | `handle_wsl_install` | 安装 WSL2 |
| `experience:list` | `handle_experience_list` | 经验面板数据 |
| `cron:*` | `handle_cron_*` | 定时任务管理 |
| `channels:*` | `handle_channels_*` | 消息通道管理 |
| `approvals:*` | `handle_approvals_*` | 命令审批管理 |

## BridgeManager 生命周期

前端 `BridgeManager`（`apps/desktop/src/main/bridge.ts`）管理 Python 子进程：

1. **启动时**按优先级查找 Python 后端：

| 优先级 | 来源 |
|--------|------|
| 1 | `MIQI_PYTHON_PATH` 环境变量 |
| 2 | 打包的 `miqi-bridge.exe` |
| 3 | `uv run python miqi/bridge/server.py` |
| 4 | `.venv/Scripts/python.exe miqi/bridge/server.py` |
| 5 | 系统 `python3` |

2. **运行时**：
   - 监听 stdout 解析 JSON-line 消息
   - 将响应路由到对应的 IPC renderer
   - 检测子进程崩溃并自动重启

3. **退出时**：
   - 发送 SIGTERM 优雅关闭
   - 清理子进程资源

## PyInstaller 打包

Bridge Server 可打包为独立 `miqi-bridge.exe`：

```ini
# miqi.spec
a = Analysis(
    ['miqi/bridge/server.py'],
    hiddenimports=[
        'miqi.agent', 'miqi.agent.tools', 'miqi.agent.memory',
        'miqi.providers', 'miqi.config', 'miqi.session',
        'miqi.cron', 'miqi.channels', 'miqi.bus'
    ],
    ...
)
pyz = PYZ(a.pure)
exe = EXE(pyz, console=False, ...)  # GUI 模式 (无控制台窗口)
```

### --check 自检模式

`miqi-bridge.exe` 支持 `--check` 参数，用于环境验证。该逻辑在 `server.py` 文件顶部处理（标准库 import 之后、项目 import 之前），确保即使项目模块加载失败也能正确报告环境状态。

```bash
miqi-bridge.exe --check
# 输出: {"ok": true, "python_version": "3.12.10", "issues": []}
```

**为什么不支持 `-c` 参数**：PyInstaller 打包的 exe 不是 Python 解释器，传给 exe 的参数会变成 `sys.argv`，而非 Python 解释器选项。因此 `miqi-bridge.exe -c "code"` 不会执行代码。

**`console=False` 行为**：虽然不弹出控制台窗口，但 `spawnSync` 仍可通过 stdout 管道捕获输出，`--check` 的 JSON 输出能被 Electron 正常读取。
