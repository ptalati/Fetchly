"""Start Fetchly at sign-in (to the tray). No Qt.

    is_enabled() -> bool
    set_enabled(enabled: bool) -> None
    launch_command() -> list[str]

Windows uses the HKCU Run key, macOS a LaunchAgent plist, Linux an XDG autostart entry.
Everything that touches the system goes through the module-level ``paths`` / ``registry``
hooks (or the ``home`` argument), so tests can swap them without touching the real machine.
"""

from __future__ import annotations

import os
import plistlib
import shlex
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Fetchly"
LAUNCH_AGENT_LABEL = "app.fetchly.Fetchly"


class _WinRegistry:
    """Thin wrapper over winreg's HKCU Run key; replaced by a fake in tests."""

    def get(self, name: str) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                return winreg.QueryValueEx(k, name)[0]
        except FileNotFoundError:
            return None

    def set(self, name: str, value: str) -> None:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)

    def delete(self, name: str) -> None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except FileNotFoundError:
            pass


registry = _WinRegistry()  # monkeypatch with an object that has get/set/delete


def launch_command() -> list[str]:
    """The command that starts Fetchly minimised to the tray."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--tray"]
    exe = sys.executable
    if sys.platform == "win32":
        pythonw = Path(exe).with_name("pythonw.exe")
        if pythonw.exists():
            exe = str(pythonw)  # no console window at sign-in
    return [exe, "-m", "fetchly", "--tray"]


def _windows_command_line(cmd: list[str]) -> str:
    import subprocess

    return subprocess.list2cmdline(cmd)


def launch_agent_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def desktop_entry_path(home: Path | None = None) -> Path:
    config = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config) if config and home is None else (home or Path.home()) / ".config"
    return base / "autostart" / "fetchly.desktop"


def _desktop_entry(cmd: list[str]) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Fetchly\n"
        "Comment=Download manager\n"
        f"Exec={' '.join(shlex.quote(c) for c in cmd)}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def is_enabled(home: Path | None = None, platform: str | None = None) -> bool:
    platform = platform or sys.platform
    if platform == "win32":
        return bool(registry.get(VALUE_NAME))
    if platform == "darwin":
        return launch_agent_path(home).exists()
    return desktop_entry_path(home).exists()


def set_enabled(enabled: bool, home: Path | None = None, platform: str | None = None) -> None:
    platform = platform or sys.platform
    cmd = launch_command()
    if platform == "win32":
        if enabled:
            registry.set(VALUE_NAME, _windows_command_line(cmd))
        else:
            registry.delete(VALUE_NAME)
    elif platform == "darwin":
        path = launch_agent_path(home)
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(plistlib.dumps({"Label": LAUNCH_AGENT_LABEL, "ProgramArguments": cmd, "RunAtLoad": True}))
        else:
            path.unlink(missing_ok=True)
    else:
        path = desktop_entry_path(home)
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_desktop_entry(cmd), encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
