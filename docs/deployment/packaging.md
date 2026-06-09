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
    - msi        # MSI 安装器
  arch: [x64]
  icon: src/renderer/assets/icon.ico  # ICO 文件需包含多种尺寸

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

## 常见问题与解决方案

### 1. MSI 构建失败：图标找不到

错误信息：
```
error LGHT0094 : The identifier 'Icon:MiQiDesktopIcon.exe' could not be found.
```

问题原因：
WiX Toolset（用于构建 MSI）需要应用程序图标包含多种尺寸（16x16、32x32、48x48、64x64、128x128、256x256）。单一尺寸的图标会导致构建失败。

解决方案：
创建包含多种尺寸的 ICO 文件。项目中提供了生成脚本：

```bash
cd apps/desktop
node scripts/generate-icon.js
```

脚本会生成 `src/renderer/assets/icon.ico`，包含所有必需的尺寸。

### 2. 图标尺寸不足

错误信息：
```
image C:\...\icon.ico must be at least 256x256
```

问题原因：
electron-builder 要求主图标至少为 256x256 像素。

解决方案：
确保 ICO 文件包含 256x256 尺寸，同时包含其他常用尺寸以兼容不同系统和显示环境。
