# PyInstaller spec for Fetchly. Build with:  pyinstaller packaging/fetchly.spec
# Produces dist/Fetchly/ (Windows, Linux) or dist/Fetchly.app (macOS).
import sys
from pathlib import Path

HERE = Path(SPECPATH)
ROOT = HERE.parent
ICON = str(HERE / ("fetchly.ico" if sys.platform == "win32" else "fetchly-1024.png"))

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "fetchly" / "gui" / "resources"), "fetchly/gui/resources")],
    hiddenimports=["h2"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtMultimedia"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Fetchly",
    console=False,
    icon=ICON,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Fetchly")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Fetchly.app",
        icon=ICON,
        bundle_identifier="app.fetchly.Fetchly",
        info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": "0.1.0"},
    )
