# 开发指南

## 开发环境搭建

### 必备工具

- Python 3.11+ 和 uv
- Node.js 20+ 和 npm
- Git (含子模块支持)
- WSL2 (Windows 用户推荐)

### 克隆并初始化

```bash
git clone --recurse-submodules <repo-url>
cd miqi-desktop
uv sync
cd apps/desktop && npm install
```

### 启动开发模式

```bash
cd apps/desktop
npm run dev
```

## 开发工作流

### Python 后端开发

```
miqi/
├── agent/      修改 Agent 逻辑 → 写测试 → uv run pytest
├── bridge/     添加 IPC handler → 更新 shared/ipc.ts → 前端适配
├── providers/  新增 LLM 适配 → 更新 ProviderRegistry
└── tools/      新增工具 → 注册到 ToolRegistry
```

### 前端开发

```
apps/desktop/src/
├── main/       修改主进程逻辑 → 重启应用
├── preload/    修改暴露 API → 重启应用
├── renderer/   修改 UI → HMR 热更新
└── shared/     修改类型定义 → 前后端同步更新
```

### 添加新的 IPC 通道

1. **shared/ipc.ts**：定义 IPC 常量 + Zod Schema
2. **main/ipc/**：实现 Main 进程 handler
3. **bridge/server.py**：实现 Bridge handler
4. **preload/index.ts**：暴露 preload API
5. **renderer**：调用 `window.miqi.*` API

## 代码规范

### Python

```bash
# 代码检查
uv run ruff check .

# 代码格式化
uv run ruff format .

# 行长度限制: 100
```

### TypeScript

```bash
# ESLint 检查
cd apps/desktop && npm run lint
```

### 提交规范

遵循 Conventional Commits：

```
feat: 添加 SkillHub 页面
fix: 修复快照回滚时的文件创建问题
refactor: 重构 SessionManager 存储层
docs: 更新 README 安装说明
test: 添加 TaskTrace 数据模型测试
```

## 测试

### Python 测试

```bash
# 运行所有测试
uv run pytest

# 运行特定模块
uv run pytest tests/test_trace.py

# 带覆盖率
uv run pytest --cov=miqi --cov-report=html
```

### 前端测试

```bash
cd apps/desktop

# 运行测试
npm run test

# 监视模式
npm run test:watch
```

## 调试

### Python 调试

开发模式下，Bridge Server 的日志输出到 Electron DevTools Console：

```python
from loguru import logger
logger.info("Debug message")  # → DevTools Console
```

### 前端调试

- 打开 Electron DevTools：`Ctrl+Shift+I`
- React DevTools 可用
- Network 面板可查看 IPC 通信

## 目录约定

| 目录 | 约定 |
|------|------|
| `miqi/` | 纯 Python，不包含 Node.js 依赖 |
| `apps/desktop/` | 纯 Node.js/TypeScript，通过 Bridge 通信 |
| `tests/` | 镜像 `miqi/` 结构，`test_module.py` 对应 `module.py` |
| `docs/` | MkDocs Material 格式，每个页面一个 `.md` 文件 |
