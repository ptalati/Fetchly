# PyInstaller spec for Fetchly. Build with:  pyinstaller packaging/fetchly.spec
# Produces dist/Fetchly/ (Windows, Linux) or dist/Fetchly.app (macOS).
# Two executables share one folder: Fetchly (the app) and fetchly-host (console program the
# browser extension talks to through native messaging).
import sys
from pathlib import Path

HERE = Path(SPECPATH)
ROOT = HERE.parent
ICON = str(HERE / ("fetchly.ico" if sys.platform == "win32" else "fetchly-1024.png"))
EXCLUDES = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
            "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtMultimedia"]

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "fetchly" / "gui" / "resources"), "fetchly/gui/resources")],
    hiddenimports=["h2"],
    excludes=EXCLUDES,
)
host = Analysis(
    [str(HERE / "host_launcher.py")],
    pathex=[str(ROOT)],
    hiddenimports=["fetchly.gui.single_instance", "fetchly.native_host_install", "fetchly.autostart"],
    excludes=EXCLUDES + ["PySide6.QtWidgets", "PySide6.QtGui", "httpx", "h2"],
)
pyz = PYZ(a.pure)
host_pyz = PYZ(host.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Fetchly",
    console=False,
    icon=ICON,
)
host_exe = EXE(
    host_pyz, host.scripts, [],
    exclude_binaries=True,
    name="fetchly-host",
    console=True,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    host_exe, host.binaries, host.datas,
    name="Fetchly",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Fetchly.app",
        icon=ICON,
        bundle_identifier="app.fetchly.Fetchly",
        info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": "0.1.2"},
    )
