---
name: e2e-debug-electron
description: |
  Debug and fix failing Playwright E2E tests for the MiQi Electron desktop app.
  Supports three modes:
  - Plan mode (`/e2e-debug-electron plan`, 模式一)：分析失败 → 制定修复计划 → 等待用户确认 → 执行
  - Ask mode (`/e2e-debug-electron ask`, 模式二)：只读查询，不修改任何文件
  - Edit mode (`/e2e-debug-electron`, 默认)：直接分析并修复代码
  Use when the user asks to debug, investigate, or fix E2E test failures,
  Playwright test reports, Electron app test issues, or any combination
  like "debug e2e", "分析 E2E 测试失败", "fix playwright test", etc.
triggers:
  - "/e2e-debug-electron"
  - "/e2e-debug"
  - "debug e2e"
  - "debug electron test"
  - "分析E2E测试"
  - "E2E测试失败"
  - "fix playwright test"
  - "fix e2e test"
  - "playwright report"
  - "electron e2e"
---

# E2E Debug Electron — 三模式调试技能

分析、定位并修复 MiQi Electron 桌面应用的 Playwright E2E 测试失败。
根据用户传入的参数自动切换模式。

---

## 模式选择

读取用户输入的第一个参数，按以下规则切换：

| 参数 | 模式 | 行为 |
|------|------|------|
| `plan` | **Plan 模式** | 分析 → 制定修复计划 → 展示给用户 → 等待确认 → 执行修复 |
| `ask` | **Ask 模式** | 只读分析，回答疑问，**不修改任何文件、不执行命令** |
| *(无参数/其他)* | **Edit 模式（默认）** | 加载技能 → 分析失败 → 直接修改代码修复 |

模式判定逻辑：
- 如果用户输入包含 `plan` → 进入 Plan 模式
- 如果用户输入包含 `ask` → 进入 Ask 模式
- 其他情况 → 默认 Edit 模式

---

## 项目 E2E 测试概况

测试目录：`apps/desktop/tests/`

```
apps/desktop/
├── playwright.config.ts       # Playwright 配置
├── tests/
│   ├── smoke/                 # Smoke 测试（mock bridge，Chromium 浏览器）
│   │   ├── smoke.spec.ts
│   │   ├── issue-*.spec.ts
│   │   └── logs.spec.ts
│   └── e2e/                   # Electron E2E 测试（真实桌面应用）
│       ├── helpers/
│       │   └── electron-setup.ts   # 共享启动/交互工具
│       ├── full-electron.spec.ts
│       ├── approval-persistence.spec.ts
│       ├── sandbox-exec.spec.ts
│       ├── sandbox-toggle.spec.ts
│       ├── session-key-mapping.spec.ts
│       ├── session-streaming-isolation.spec.ts
│       ├── task-assets.spec.ts
│       ├── pptx-generator.spec.ts
│       └── mof-skill.spec.ts
└── test-reports/
    ├── html/                  # HTML 报告
    └── results.json           # JSON 结果
```

### 运行测试命令

```bash
# 所有 Electron E2E 测试
cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron

# 单个测试文件
cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron tests/e2e/full-electron.spec.ts

# 带 UI 模式调试
cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron --ui

# 查看 HTML 报告
cd apps/desktop && npx playwright show-report test-reports/html

# 只运行失败的测试
cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron --last-failed
```

---

## 模式一：Plan 模式（分析 → 计划 → 确认 → 执行）

### 触发方式
用户输入 `/e2e-debug-electron plan` 或包含 `plan` 关键词。

### 工作流

**Step 1 — 收集信息**
1. 读取 Playwright 测试报告：`apps/desktop/test-reports/results.json`
2. 如果用户提到了特定测试文件，读取对应的 spec 文件
3. 分析失败截图（如有）：检查 `test-results/` 目录下的截图
4. 读取相关源代码文件，理解测试覆盖的功能

**Step 2 — 分析根因**
1. 从错误消息、堆栈跟踪、超时信息中定位失败原因
2. 分类失败类型：
   - **选择器失效**：UI 元素变更导致 locator 找不到
   - **超时**：LLM 响应慢、页面加载慢、等待条件不满足
   - **断言失败**：预期行为与实际行为不一致
   - **环境问题**：Electron 启动失败、bridge 未初始化
   - **竞态条件**：异步操作顺序不确定
3. 识别受影响的源文件（非测试文件）

**Step 3 — 制定修复计划**
格式化输出修复计划：

```markdown
## E2E 修复计划

### 失败测试
- `<test-name>`: `<失败原因简述>`

### 根因分析
<1-3 句话说明根本原因>

### 受影响文件
1. `<file-path>` — `<修改说明>`
2. `<file-path>` — `<修改说明>`

### 修复步骤
1. [ ] <步骤1>
2. [ ] <步骤2>
...

### 预估影响
- 风险等级：低/中/高
- 可能影响的其他测试：<列出或说明无>
```

**Step 4 — 等待用户确认**
展示计划后，**不要自动执行任何修改**。明确询问用户：
"以上是修复计划，是否确认执行？请回复 confirm / 修改 / 取消。"

**Step 5 — 执行修复**
用户确认后：
1. 按步骤顺序修改代码
2. 每改完一个文件，检查语法正确性
3. 全部改完后，运行受影响的测试验证
4. 报告最终结果

### Plan 模式权限
- ✅ 读取文件、搜索代码、分析日志
- ✅ 运行测试（仅用于诊断，如 `npx playwright test --last-failed`）
- ❌ 修改文件（仅用户确认后才允许）
- ❌ Git 操作（仅用户确认后才允许）

---

## 模式二：Ask 模式（只读查询）

### 触发方式
用户输入 `/e2e-debug-electron ask` 或包含 `ask` 关键词。

### 工作流

**Step 1 — 理解问题**
解析用户的具体问题，确定需要查看哪些文件/报告。

**Step 2 — 读取与分析**
1. 读取测试报告、日志文件、spec 文件、源代码
2. 分析失败原因或回答用户的具体问题
3. 可以搜索代码库、查看 git 历史

**Step 3 — 回答**
以清晰的结构化格式回答用户问题：
- 直接回答用户的问题
- 提供相关代码片段和文件路径（带行号）
- 如果用户没问但相关，可以补充上下文

### Ask 模式限制（运行时强制执行）
- ✅ 读取文件 (`read_file`)
- ✅ 搜索代码 (`grep`, `list_dir`)
- ✅ 分析日志
- ✅ 网页搜索/获取 (`web_search`, `web_fetch`)
- ❌ **禁止** 修改文件 (`write_file`, `edit_file`, `apply_patch`)
- ❌ **禁止** 执行命令 (`exec`, `bash`)
- ❌ **禁止** Git 操作
- ❌ **禁止** 创建文档 (`create_docx`, `create_pptx`, `create_xlsx`)
- ❌ **禁止** 生成子代理 (`spawn`)
- ❌ **禁止** 计划任务 (`cron`)
- ❌ **禁止** 技能管理 (`skill_manage`)
- ❌ **禁止** 内存写入 (`memory`)

如果用户请求超出只读范围的操作，回复：
"当前处于 Ask 模式（只读），无法执行写操作。如需修复，请使用 `/e2e-debug-electron`（Edit 模式）或 `/e2e-debug-electron plan`（Plan 模式）。"

---

## 模式三：Edit 模式（默认，直接修复）

### 触发方式
用户输入 `/e2e-debug-electron`（无参数），或描述测试失败要求修复。

### 工作流

1. **快速诊断**：读取测试报告 → 定位失败测试 → 读取相关源文件
2. **直接修复**：修改源代码或测试代码来修复问题
3. **验证**：运行受影响的测试确认修复有效
4. **报告**：总结做了什么修改、为什么这样修改

### Edit 模式权限
- ✅ 所有读操作
- ✅ 修改文件
- ✅ 运行测试
- ✅ Git 操作
- ✅ 所有工具可用（受正常审批策略约束）

---

## 常见 E2E 失败模式与修复策略

### 1. 选择器/定位器失效
**症状**：`locator.click: Timeout 10000ms exceeded`、`Error: locator.fill: Target closed`
**常见原因**：UI 文案变更、DOM 结构调整、组件替换
**修复策略**：
- 检查对应前端代码中的实际元素
- 更新 spec 中的 `getByText()`, `getByPlaceholder()`, `getByRole()` 等选择器
- 考虑使用 `data-testid` 提高稳定性

### 2. LLM 响应超时
**症状**：测试在等待 AI 回复时超时
**常见原因**：LLM 调用慢、模型不可用、网络问题
**修复策略**：
- 检查 `LLM_TIMEOUT` 常量是否合理（当前 180s）
- 检查 provider 配置和 API key
- 确认模型是否支持请求的功能

### 3. Electron 启动失败
**症状**：`electron.launch: Timeout`、`Browser window not found`
**常见原因**：Electron 版本兼容性、构建产物缺失、端口冲突
**修复策略**：
- 确认 `apps/desktop/` 构建成功
- 检查 `electron-setup.ts` 中的启动参数
- 验证 Playwright 与 Electron 版本兼容性

### 4. Bridge 通信失败
**症状**：`bridge not initialized`、IPC 调用无响应
**常见原因**：preload 脚本错误、bridge 超时、序列化问题
**修复策略**：
- 检查 `apps/desktop/src/main/bridge*.ts` 相关代码
- 查看 `waitForBridgeInitialized` 的超时设置
- 检查主进程日志

### 5. 截图/视频断言失败
**症状**：`expect(locator).toHaveScreenshot()` 失败
**常见原因**：UI 视觉变更、分辨率差异、平台渲染差异
**修复策略**：
- 更新基准截图：`npx playwright test --update-snapshots`
- 确认变更是否预期内的 UI 更新
- 检查 CI 与本地的渲染差异

---

## 快速参考：关键文件路径

| 文件 | 用途 |
|------|------|
| `apps/desktop/playwright.config.ts` | Playwright 配置、项目定义、超时设置 |
| `apps/desktop/tests/e2e/helpers/electron-setup.ts` | Electron 启动、页面交互工具函数 |
| `apps/desktop/tests/smoke/mocks.ts` | Smoke 测试的 mock bridge |
| `apps/desktop/test-reports/results.json` | 最新测试运行结果 |
| `apps/desktop/test-reports/html/` | HTML 测试报告 |
| `apps/desktop/src/main/` | Electron 主进程源码 |
| `apps/desktop/src/renderer/` | Electron 渲染进程源码 |
| `miqi/agent/` | Agent 核心逻辑（可能影响 E2E 行为） |
| `miqi/kun_runtime/` | KUN 运行时（Agent 循环、工具调度） |
