# -*- mode: python ; coding: utf-8 -*-
# Replace 'C:\\path\\to\\your\\venv\\Lib\\site-packages\\pyzbar' with the actual path you found in Step 2.
# Use double backslashes `\\` or a raw string r'...' for Windows paths.

pyzbar_path = 'C:\\Users\\Administrator\\PycharmProjects\\dev-fg-final\\venv\\Lib\\site-packages\\pyzbar'

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
     (pyzbar_path + '\\libiconv.dll', 'pyzbar'),
        (pyzbar_path + '\\libzbar-64.dll', 'pyzbar')
    ],
    datas=[],
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
    [],
    exclude_binaries=True,
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='main',
)
