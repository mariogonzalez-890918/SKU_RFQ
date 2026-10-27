# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
project_root = Path(SPECPATH).resolve().parent
server_root = project_root / 'sku-servidor'


a = Analysis(
    [str(server_root / 'server.py')],
    pathex=[],
    binaries=[],
    datas=[(str(server_root / 'public'), 'public')]+[(str(server_root / name), '.') for name in ('catalogos.json','initial.json','initial-ventas.json','initial-requisiciones.json')]+([(str(server_root / 'initial-admin.json'), '.')] if (server_root / 'initial-admin.json').exists() else []),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SKU-JAD-Servidor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
