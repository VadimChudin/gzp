# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-спецификация десктопного приложения GZP.

Собирает один каталог с GZP.exe. Индикаторы MQL кладутся внутрь как ресурсы —
после установки приложение само раскладывает их по терминалам.
"""

import os
from pathlib import Path

ROOT = Path(os.environ.get("GZP_ROOT", Path.cwd()))

datas = [
    (str(ROOT / "mql" / "MT4" / "Indicators"), "mql/MT4/Indicators"),
    (str(ROOT / "mql" / "MT5" / "Indicators"), "mql/MT5/Indicators"),
]

assets = ROOT / "assets"
if assets.exists():
    datas.append((str(assets), "assets"))

a = Analysis(
    [str(ROOT / "gzp.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PIL._tkinter_finder",
        "MetaTrader5",
        "gzp_core",
        "gzp_core.app",
        "gzp_core.auth",
        "gzp_core.branding",
        "gzp_core.config",
        "gzp_core.data_feed",
        "gzp_core.engine",
        "gzp_core.exporter",
        "gzp_core.indicators",
        "gzp_core.lifecycle",
        "gzp_core.mt_patcher",
        "gzp_core.splash",
        "gzp_core.version",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "matplotlib", "scipy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GZP",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # без чёрного консольного окна
    icon=str(ROOT / "assets" / "gzp.ico") if (ROOT / "assets" / "gzp.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="GZP",
)
