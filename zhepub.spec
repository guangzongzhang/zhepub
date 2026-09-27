# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：生成单个 EPUB中文编辑器.exe。

用法：python -m PyInstaller zhepub.spec --noconfirm
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve()

# 用不到的 Qt 模块，排除后可以明显减小 exe 体积
QT_EXCLUDES = [
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebChannel",
    "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuickWidgets", "PyQt6.Qt3DCore",
    "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets", "PyQt6.QtBluetooth",
    "PyQt6.QtNetwork", "PyQt6.QtNfc", "PyQt6.QtPositioning", "PyQt6.QtSensors",
    "PyQt6.QtSerialPort", "PyQt6.QtSql", "PyQt6.QtTest", "PyQt6.QtPdf",
    "PyQt6.QtPdfWidgets", "PyQt6.QtSvgWidgets", "PyQt6.QtOpenGL",
    "PyQt6.QtOpenGLWidgets", "PyQt6.QtDesigner", "PyQt6.QtHelp",
]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "assets" / "icon.ico"), "assets")],
    # 繁简转换是可选功能；若构建环境装了 opencc，一并打包
    hiddenimports=["opencc"],
    excludes=["tkinter", "unittest", "pydoc", "pytest", "PIL", "numpy"] + QT_EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EPUB中文编辑器",
    icon=str(ROOT / "assets" / "icon.ico"),
    console=False,
    upx=False,
    version=str(ROOT / "version_info.txt"),
)
