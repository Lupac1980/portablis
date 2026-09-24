# -*- mode: python ; coding: utf-8 -*-
# Spec do PyInstaller para gerar Portabilis.exe (portable, sem instalacao).
# Build no Windows:  pyinstaller Portabilis.spec --noconfirm
block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('scan.py', '.'), ('clone.py', '.'), ('ui.py', '.'), ('cli.py', '.')],
    hiddenimports=['winreg'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Portabilis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,               # se tiver UPX instalado, melhora a compressao
    upx_exclude=[],
    runtime_tmpdir=None,    # None = one-file portavel (extrai em temp controlado)
    console=False,          # app de GUI; use True para depurar
    disable_windowed_traceback=False,
    icon='assets/portabilis.ico' if __import__('os').path.exists('assets/portabilis.ico') else None,
)
