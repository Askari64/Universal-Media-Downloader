# -*- mode: python ; coding: utf-8 -*-

import sys
from PyInstaller.utils.hooks import collect_submodules

# --- Analysis ---
a = Analysis(
    ['Universal Media Downloader.py'],
    pathex=[r'C:\Users\Askari\OneDrive\Documents\Projects\media-downloader\GUI_Downloader'],
    binaries=[('ffmpeg.exe', '.'), ('ffprobe.exe', '.')],
    datas=[],
    hiddenimports=collect_submodules('yt_dlp') + collect_submodules('customtkinter'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# --- PYZ ---
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# --- EXE ---
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Universal Media Downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
