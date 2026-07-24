## 类型

- [x] 🐛 Bug 修复
- [x] 🧪 测试
- [x] 🔧 其他

## 变更概述

修复 WSL E2E CI 频繁失败：添加超时保护、修复配置持久化顺序、消除测试假阳性、提高沙箱冷启动等待时间。

## 背景/问题

CI 中 `wsl-e2e` job 经常失败，根因是沙箱冷启动初始化（wsl export → import → apt-get install bwrap）需要 3-5 分钟，但代码中存在多个缺陷：

1. WSL 子进程调用无超时保护 — 假死时永久阻塞
2. 配置 `enabled=True` 在初始化成功前就持久化 — 初始化失败后沙箱永远无法自愈
3. `waitForResponseComplete` stream stabilization 假阳性 — AI 静默失败时 ~400ms 就返回 true
4. regression-284 测试只等 90s — 远小于冷启动需要的 3-5 分钟
5. 测试在沙箱就绪前就发送 LLM 请求 — 工具静默回退到本地执行
6. 无 retry 机制 — 瞬态失败直接挂掉 CI

## 变更内容

### Tier 1 — 关键缺陷修复

1. **`miqi/sandbox/bwrap.py`** — `_detect_wsl_distro()` 和 `_find_any_wsl_distro()` 中 3 处裸 `proc.communicate()` 添加 `asyncio.wait_for()` 超时 guard（15-30s）。假死 WSL 进程不再永久阻塞。

2. **`miqi/bridge/loop.py`** — `save_config(enabled=True)` 从 `initialize()` 之前移到之后。初始化失败时重置 `enabled=False` 以便下次重启重试。

3. **`apps/desktop/tests/e2e/helpers/electron-setup.ts`** — `waitForResponseComplete` Phase 3 添加 `grown` 标志，要求 textContent 确实增长过才判定完成。

4. **`apps/desktop/tests/e2e/regression-284-sandbox.spec.ts`** — 超时 90s→300s，polling 5s→10s。每次轮询打印 label 文本到 CI 日志。

### Tier 2 — 测试韧性

5. **`electron-setup.ts`** — 新增 `waitForSandboxReady()` 辅助函数，轮询 `runtime.status().sandbox_available`。`sandbox-exec.spec.ts` 在 `beforeAll` 中调用。

6. **`apps/desktop/playwright.config.ts`** — Electron 项目 CI 环境 `retries: 2`。

7. **`.github/workflows/python-tests.yml`** — `wsl-e2e` job 添加 concurrency group。

### Tier 3 — 诊断

8. **`miqi/bridge/loop.py` + `miqi/sandbox/bwrap.py`** — 沙箱初始化、export、import、apt-get 各步骤添加 `time.monotonic()` 计时代码。

### Tier 4 — 一致性

9. **`miqi/config/schema.py`** — `share_net` 默认 `True`→`False`，与 `SandboxManager`/`BwrapSandbox` 构造器默认值一致。`docs/developer-guide.md` 同步更新。

## 日志/验证证据

```
$ uv run python -c "from miqi.config.schema import SandboxConfig; c = SandboxConfig(); print(f'share_net={c.share_net}, enabled={c.enabled}')"
share_net=False, enabled=True

$ git diff --stat
 9 files changed, 102 insertions(+), 23 deletions(-)
```

## 测试情况

- Python 单元测试：`uv run pytest tests/sandbox/` — 通过（本地无 WSL 环境，sandbox marker 自动跳过）
- Schema 导入验证：通过
- Playwright E2E：需在 CI `wsl-e2e` job 中验证
- 本 PR 仅修改沙箱初始化流程和测试辅助逻辑，不影响现有前端功能

## 截图

无需截图（后端逻辑修复 + 测试基础设施变更）
