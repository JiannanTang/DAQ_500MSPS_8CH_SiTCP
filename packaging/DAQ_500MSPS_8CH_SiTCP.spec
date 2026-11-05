# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import re

import PySide6

spec_dir = Path(SPECPATH).resolve()
project_root = spec_dir.parent
pyside_dir = Path(PySide6.__file__).resolve().parent
runtime_binaries = [
    (str(path), ".")
    for path in pyside_dir.iterdir()
    if path.is_file()
    and re.match(r"^(MSVCP|VCRUNTIME|concrt).*\.dll$", path.name, re.IGNORECASE)
]

a = Analysis(
    [str(spec_dir / "launcher.py")],
    pathex=[str(project_root / "src")],
    binaries=runtime_binaries,
    datas=[
        (str(project_root / "config" / "registers.toml"), "config"),
        (str(spec_dir / "README_DIST.txt"), "."),
    ],
    hiddenimports=["PySide6.QtCharts"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(spec_dir / "runtime_qt_paths.py")],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DAQ_500MSPS_8CH_SiTCP",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(spec_dir / "version_info.txt"),
    contents_directory="_internal",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DAQ_500MSPS_8CH_SiTCP",
)

