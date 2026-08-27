# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).parent
APP_NAME = "JPT Sales Toolkit"
BUILD_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
BUNDLE_VERSION = BUILD_VERSION.split("-", 1)[0]
TARGET_ARCH = os.environ.get("JPT_PYINSTALLER_TARGET_ARCH") or None
if TARGET_ARCH not in {None, "x86_64", "arm64", "universal2"}:
    raise ValueError(f"Unsupported JPT_PYINSTALLER_TARGET_ARCH: {TARGET_ARCH}")


def collect_runtime_assets():
    """Package only production assets; never ship legacy users or test pages."""
    assets = [
        (str(ROOT / "frontend" / "index.html"), "frontend"),
        (str(ROOT / "frontend" / "diagnostics.html"), "frontend"),
        (str(ROOT / "backend" / "schema.sql"), "backend"),
        (str(ROOT / "VERSION"), "."),
    ]
    for relative_dir in ("frontend/css", "frontend/js", "frontend/vendor"):
        source_dir = ROOT / relative_dir
        for source in source_dir.rglob("*"):
            if source.is_file() and source.name != "README.md":
                assets.append((str(source), str(source.parent.relative_to(ROOT))))
    for name in ("fields.json", "products.json", "regions.json"):
        assets.append((str(ROOT / "config" / name), "config"))
    # urllib's platform OpenSSL path may not exist inside a frozen desktop app.
    # Ship the certifi trust store used explicitly by geocoding transport.
    assets.extend(collect_data_files("certifi"))
    return assets

analysis = Analysis(
    [str(ROOT / "desktop_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=collect_runtime_assets(),
    hiddenimports=collect_submodules("backend") + collect_submodules("uvicorn"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=TARGET_ARCH,
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        bundle,
        name=f"{APP_NAME}.app",
        bundle_identifier="com.jpt.salestoolkit",
        info_plist={
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": BUNDLE_VERSION,
            "CFBundleVersion": BUNDLE_VERSION,
            "NSHighResolutionCapable": True,
        },
    )
