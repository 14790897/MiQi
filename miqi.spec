
a = Analysis(
    ['miqi/bridge/server.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('miqi/templates', 'miqi/templates'),
        ('miqi/skills', 'miqi/skills'),
    ],
    hiddenimports=[
        # MiQi internal modules
        'miqi.agent',
        'miqi.agent.tools',
        'miqi.agent.memory',
        'miqi.providers',
        'miqi.channels',
        'miqi.config',
        'miqi.session',
        'miqi.cron',
        'miqi.bus',
        'miqi.utils',
        # Third-party deps checked dynamically via importlib.import_module()
        # (PyInstaller can't detect these — server.py handle_python_check, line 1957)
        'pydantic',
        'pydantic.deprecated.decorator',
        'pydantic._internal._config',
        'httpx',
        'httpcore',
        'loguru',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='miqi-bridge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 改为 True 调试时可以看到输出
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
