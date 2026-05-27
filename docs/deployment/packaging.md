# 桌面打包

## 打包流程

### 1. Python 后端打包

使用 PyInstaller 将 Bridge Server 打包为独立可执行文件：

```bash
pyinstaller miqi.spec
# 输出: dist/miqi-bridge.exe (Windows) 或 dist/miqi-bridge (Linux/macOS)
```

`miqi.spec` 关键配置：

```python
a = Analysis(
    ['miqi/bridge/server.py'],
    pathex=[],
    binaries=[],
    datas=[('miqi/templates', 'miqi/templates'),
           ('miqi/skills', 'miqi/skills')],
    hiddenimports=[
        'miqi.agent', 'miqi.agent.tools', 'miqi.agent.memory',
        'miqi.providers', 'miqi.providers.openai_provider',
        'miqi.providers.anthropic_provider', 'miqi.config',
        'miqi.session', 'miqi.cron', 'miqi.channels',
        'miqi.bus', 'miqi.utils'
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure)
exe = EXE(pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='miqi-bridge',
    console=False,       # GUI 模式 (无控制台窗口)
    icon=None
)
```

### 2. 前端打包

使用 electron-builder：

```bash
cd apps/desktop
npm run build              # electron-vite 构建
npx electron-builder       # 打包安装包
```

`electron-builder.yml` 配置：

```yaml
appId: com.miqi.desktop
productName: MiQi Desktop
directories:
  output: ../../dist-new

win:
  target:
    - portable   # 便携版 .exe
    - nsis       # NSIS 安装器
  arch: [x64]

extraResources:
  - from: ../../dist/miqi-bridge.exe
    to: miqi-bridge.exe

publish:
  provider: generic
  url: https://releases.example.com
```

## 构建产物

| 文件 | 描述 | 平台 |
|------|------|------|
| `dist-new/MiQi Desktop Setup.exe` | NSIS 安装器 | Windows |
| `dist-new/MiQi Desktop.exe` | 便携版 | Windows |
| `dist/miqi-bridge.exe` | Python 后端 | Windows |
| `dist/miqi-0.1.4.tar.gz` | Python 源码包 | 通用 |
| `dist/miqi-0.1.4-py3-none-any.whl` | Python Wheel | 通用 |

## Python Wheel 打包

使用 Hatchling 构建：

```bash
uv build
# 输出:
# dist/miqi-0.1.4.tar.gz
# dist/miqi-0.1.4-py3-none-any.whl
```

Wheel 包含：

- `miqi/` 所有 Python 模块
- `miqi/templates/` 模板文件
- `miqi/skills/` 内置技能
- CLI 入口 `miqi = miqi.cli.commands:app`

## 版本管理

版本号定义在 `pyproject.toml`：

```toml
[project]
version = "0.1.4.post1"
```

构建时自动同步到 `electron-builder.yml` 的 `version` 字段。
