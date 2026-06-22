# Plan 60：可信测试基线设计

> 日期：2026-06-22
>
> 状态：已批准
>
> 范围：非 Desktop Python Runtime 与测试基础设施

## 1. 背景

MiQi 当前已经有较大的 Python 测试集，但测试路径解析和运行环境没有形成统一契约。本次受限 Windows 环境中的全量测试结果为 `1699 passed, 48 failed, 5 skipped`。失败主要集中于两类环境耦合：

- 部分代码和测试仍访问真实 `C:\Users\lishi\.miqi`，即使 fixture 已提供临时 workspace。
- exec/sandbox 测试依赖真实子进程、bwrap 或 WSL，却没有统一的平台能力分类。

当前 `.github/workflows/build.yml` 主要负责 Electron 构建和发布，没有独立、跨平台的非 Desktop Python 测试门禁。在此状态下直接实施协议、安全或配置改造，无法可靠区分代码回归与测试环境污染。

## 2. 目标

Plan 60 建立一个可信、隔离、跨平台的测试基线：

1. 所有 MiQi 自有数据路径通过一个统一 Interface 解析。
2. 测试默认只读写 pytest 提供的临时根目录。
3. 普通测试、真实子进程测试和平台 sandbox 测试有明确分类。
4. Windows 与 Ubuntu CI 独立验证非 Desktop Python Runtime。
5. 环境缺少可选平台能力时产生有原因的 skip，而不是权限错误或隐式降级。

## 3. 非目标

Plan 60 不实施以下工作：

- 不修改 Agent、Thread、Turn、Provider 或工具的语义；仅允许改变本设计明确规定的路径解析行为。
- 不实现 Landlock、原生 Windows sandbox 或网络代理。
- 不修复与测试环境隔离无关的既有产品缺陷。
- 不改动 `apps/desktop/` 或 Electron 构建流程。
- 不以删除测试、放宽断言或批量标记 skip 的方式取得绿色结果。
- 不要求受限的 Agent 沙箱环境能够启动本来被宿主禁止的子进程。

## 4. 方案选择

### 4.1 采用：显式 `MIQI_HOME` 契约

增加统一的路径解析 Module。`MIQI_HOME` 表示 MiQi 的数据根目录；未设置时保持现有用户行为，解析为 `~/.miqi`。

所有配置、session、memory、trace、plugin 和 runtime state 路径必须从该 Module 获取，不能各自使用 `Path.home() / ".miqi"`。需要读取旧 `~/.assistant` 或其他历史目录时，也由该 Module 暴露明确的 legacy path。

选择该方案的原因：

- 比在测试中广泛 monkeypatch `Path.home()` 更接近真实部署方式。
- 为未来分层配置、portable install 和多实例运行提供稳定 seam。
- 生产默认值不变，迁移风险较低。

### 4.2 不采用：只在测试中 monkeypatch `Path.home()`

该方案修改少，但无法防止新代码再次直接访问用户目录，也不能为真实用户提供可配置的数据根目录。它只隐藏耦合，不建立路径 Interface。

### 4.3 不采用：只通过 CI 容器隔离 HOME

容器可以减少宿主污染，但 Windows 测试仍需要路径契约；同时开发者本地运行 pytest 仍可能访问真实用户数据。

## 5. 架构设计

### 5.1 Home Path Module

新增 `miqi/paths.py`，作为 MiQi-owned path 的唯一事实源。公开 Interface 至少包括：

- `get_miqi_home() -> Path`
- `get_config_path() -> Path`
- `get_legacy_config_path() -> Path`
- `get_legacy_data_dir() -> Path`

路径规则：

1. `MIQI_HOME` 已设置且非空：返回展开用户变量后的绝对路径。
2. `MIQI_HOME` 未设置：返回 `Path.home() / ".miqi"`。
3. 默认配置路径为 `<miqi_home>/config.json`。
4. legacy 路径只用于显式迁移或兼容读取，不作为新数据写入位置。
5. 解析函数本身不创建目录；目录创建由实际写入 Module 负责。
6. `AgentDefaults.workspace` 的序列化默认值继续保持 `~/.miqi/workspace`，避免破坏现有配置协议；仅当该字段仍为默认值且显式设置了 `MIQI_HOME` 时，`Config.workspace_path` 将其解析为 `<miqi_home>/workspace`。用户显式配置的其他 workspace 值保持原有解析语义。
7. 为保持旧数据可访问，`get_data_path()` 在未设置 `MIQI_HOME`、且 `~/.assistant` 已存在但 `~/.miqi` 不存在时，回退到 `~/.assistant`；一旦用户开始使用 `~/.miqi` 或显式设置 `MIQI_HOME`，则优先使用当前数据根。该回退对 config、session、workspace、channel media、runtime state 等所有通过 `get_data_path()` 解析的路径生效。

`miqi/config/loader.py`、`miqi/utils/helpers.py` 和 `miqi/session/manager.py` 迁移到该 Interface。后续通过仓库扫描确认其他直接拼接 `.miqi` 的生产代码，并逐项迁移。

### 5.2 Session Legacy Path Injection

`SessionManager` 当前根据 `Path.home()` 构造 `legacy_sessions_dir`。修改为：

- 默认从统一 path Module 解析 legacy data directory。
- 构造函数允许显式传入 `legacy_sessions_dir`，供测试和迁移工具使用。
- 新 session 永远写入传入的 `workspace / "sessions"`。
- 只有读取既有 session 时才检查 legacy 路径。

这样 SessionManager 的 Interface 明确表达新存储位置与迁移来源，测试不再依赖全局 home。

### 5.3 Pytest Isolation Fixture

根级 `tests/conftest.py` 增加 autouse fixture，为每个测试建立独立临时环境：

- `MIQI_HOME=<tmp_path>/.miqi`
- `HOME=<tmp_path>/home` 和 Windows 对应 home 环境变量，仅用于第三方库或仍需兼容的标准库路径解析
- `TEMP`、`TMP`、`TMPDIR=<tmp_path>/tmp`

fixture 必须在测试结束后恢复环境变量。测试仍可显式覆盖这些变量验证默认行为或迁移行为。

注册 `self_managed_env` marker 作为严格受控的 opt-out。只有需要完整自行管理 `MIQI_HOME`、`HOME`、`USERPROFILE`、`TEMP`、`TMP` 和 `TMPDIR` 的环境契约测试可以使用；使用该 marker 的测试必须在任何路径读取或写入前通过 `monkeypatch` 设置所需环境，不允许访问真实用户目录。外部工具发现测试应优先在隔离环境内覆盖具体路径，不应仅为方便而 opt out。

增加路径泄漏回归测试：在临时 home 外放置哨兵文件，运行配置和 session 读写后证明哨兵未被访问或修改，并证明所有新文件位于临时根目录。

### 5.4 测试能力分类

在 pytest 配置中注册以下 markers：

- `self_managed_env`：测试自行隔离并管理 home/temp 环境；不允许使用真实用户目录。
- `subprocess`：需要启动普通本地子进程。
- `sandbox`：需要真实隔离 Adapter。
- `wsl`：仅 Windows 且需要可用 WSL distribution。
- `bwrap`：需要 Linux/WSL 中可用的 bubblewrap。

规则：

- 普通测试不得依赖上述能力。
- `subprocess` 测试在正常 Windows/Ubuntu CI 中必须运行，不能默认 skip。
- `sandbox` 测试根据具体 Adapter 再标记 `wsl` 或 `bwrap`。
- skip reason 必须包含缺失的 executable、平台或能力名称。
- 测试不得捕获广泛异常后自行“通过”；能力检测集中在 fixture 中。

### 5.5 CI 分层

新增 `.github/workflows/python-tests.yml`，与 Desktop build workflow 解耦。

CI matrix：

- `windows-latest` + Python 3.11
- `ubuntu-latest` + Python 3.11

两个平台都执行：

1. checkout
2. setup Python
3. install uv
4. `uv sync --all-extras`
5. 普通测试与 subprocess 测试

Ubuntu 额外安装或检测 bwrap，并运行 bwrap-marked tests。Windows 不自动安装 WSL；WSL tests 在标准 GitHub-hosted runner 上以明确原因 skip。原生 Windows sandbox 将在后续安全计划中设计，不在本计划伪造。

CI 对所有 pull request 触发，并对 `main` push 触发；使用 path filter，仅在修改 `miqi/**`、`tests/**`、`pyproject.toml`、`uv.lock` 或该 workflow 本身时运行。

## 6. 数据流

```text
Process environment
    |
    | MIQI_HOME (optional)
    v
miqi.paths
    |-- config path --------> config loader
    |-- data root ----------> runtime stores
    `-- legacy paths -------> explicit migration reads

pytest tmp_path
    |
    `-- autouse fixture sets MIQI_HOME/HOME/TEMP
            |
            `-- every MiQi-owned write remains below tmp_path
```

## 7. 错误处理

- 空白 `MIQI_HOME` 按“未设置”处理。
- 相对 `MIQI_HOME` 在解析时转换为绝对路径，避免工作目录变化导致数据根漂移。
- 路径解析不吞掉权限错误；创建或写入失败由调用 Module 返回原始、可诊断的错误。
- capability fixture 只对“能力确实不存在”执行 skip；可执行文件存在但运行失败应判定测试失败。
- 真实产品错误不能通过新增 marker 转换为 skip。

## 8. 测试策略

### 8.1 Path contract tests

- 未设置 `MIQI_HOME` 时保持 `~/.miqi` 默认值。
- 设置绝对和相对 `MIQI_HOME` 时得到确定的绝对路径。
- config、data 和 legacy path 投影正确。
- path getter 不产生文件系统副作用。

### 8.2 Storage isolation tests

- config save/load 只访问临时 MiQi home。
- SessionManager 新数据只写入 workspace。
- legacy session 只从显式 legacy directory 迁移。
- memory、trace、plugin 等扫描到的直接 home 访问全部覆盖或迁移。
- 默认 workspace 字符串仍序列化为 `~/.miqi/workspace`；设置 `MIQI_HOME` 时，仅该默认值的运行时投影切换到隔离根目录。

### 8.3 Capability tests

- `self_managed_env` 测试在任何路径访问前设置全部六个环境变量，并仍位于 `tmp_path` 下。
- marker 和 fixture 在有能力时运行测试。
- 缺能力时 skip reason 稳定且具体。
- 普通测试不能意外请求 subprocess/sandbox fixture。

### 8.4 Full regression

- Windows 和 Ubuntu 普通套件无失败。
- 正常宿主上的 subprocess 套件无失败。
- bwrap 套件在安装 bwrap 的 Ubuntu runner 上无失败。
- 测试前后真实 MiQi home 没有新增或变更文件。

## 9. 验收标准

Plan 60 只有在以下条件全部满足时完成：

1. 生产默认数据位置仍为 `~/.miqi`。
2. `MIQI_HOME` 可覆盖配置与 MiQi-owned runtime data 根目录。
3. 生产代码不再直接拼接新的 `Path.home() / ".miqi"` 路径。
4. SessionManager 的 legacy migration path 可显式注入。
5. pytest 默认运行不会读写真实 MiQi home。
6. `self_managed_env` opt-out 已注册、使用受审计，且 opt-out 测试自行隔离所有路径环境变量。
7. 平台能力 markers 已注册，skip reason 可诊断。
8. Windows 和 Ubuntu 非 Desktop CI 已建立。
9. 在具备正常子进程权限的环境中，普通与 subprocess 测试全绿。
10. bwrap 测试在配置了 bwrap 的 Ubuntu CI 中全绿。
11. 没有通过删除测试、弱化断言或无条件 skip 达成验收。

## 10. 后续计划接口

Plan 60 完成后，Plan 61“类型化 App Server 协议”可以依赖：

- 可复现的 Windows/Ubuntu 测试环境。
- 隔离的 config、session 和 schema 输出目录。
- 明确的普通测试与平台测试门禁。
- 不会污染开发者真实 MiQi 数据的 schema/compatibility 测试。
