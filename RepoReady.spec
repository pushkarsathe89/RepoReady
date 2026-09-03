# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for RepoReady.

Build a single-file, windowed desktop app:

    pyinstaller RepoReady.spec

The output ``dist/RepoReady.exe`` has no console window and needs no
Python installation on the target machine.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# tkcalendar loads some of its submodules dynamically; pull them all in.
hiddenimports = collect_submodules("tkcalendar")
datas = collect_data_files("tkcalendar")

a = Analysis(
    ["repoready.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="RepoReady",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)