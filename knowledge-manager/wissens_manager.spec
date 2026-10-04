# -*- mode: python ; coding: utf-8 -*-
# Baut Wissens-Manager als Ordner (Single Directory): dist/Wissens-Manager/Wissens-Manager.exe
# Aufruf im Ordner knowledge-manager:  .venv\Scripts\pyinstaller --noconfirm wissens_manager.spec

EXCLUDES = [
    "tkinter", "unittest", "pytest", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtQml", "PyQt6.QtQuick",
    "PyQt6.QtMultimedia", "PyQt6.QtSql", "PyQt6.QtTest", "PyQt6.Qt3DCore", "PyQt6.QtBluetooth", "PyQt6.QtNfc", "PyQt6.QtSensors",
]

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=[],
    datas=[("wissens_manager/fonts", "wissens_manager/fonts")],
    hiddenimports=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Wissens-Manager",
    console=False,  # Fenster-Programm ohne Konsole
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Wissens-Manager")
