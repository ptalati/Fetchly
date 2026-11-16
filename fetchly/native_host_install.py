"""Registers Fetchly's native messaging host with the browsers on this machine. No Qt.

    register(...)       write host manifests (and, on Windows, the HKCU registry keys); idempotent
    unregister(...)     remove them again
    is_registered(...)  True when every manifest exists and points at the current host executable

The host manifest is named ``app.fetchly.host``. Chrome-family browsers get ``allowed_origins``
for the extension id below, Firefox gets ``allowed_extensions``. Everything that touches the
machine takes an optional override (``home``, ``platform``, ``registry``, ``data``,
``executable``), so tests never touch the real registry or home folder.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

HOST_NAME = "app.fetchly.host"
HOST_DESCRIPTION = "Fetchly download manager"

# Derived from the public "key" in browser-extension/chrome/manifest.json, so unpacked installs get this id.
CHROME_EXTENSION_ID = "ibkpdihldgloenialblmglncdlpbjdko"
FIREFOX_EXTENSION_ID = "fetchly@fetchly.app"
CHROME_ORIGIN = f"chrome-extension://{CHROME_EXTENSION_ID}/"


@dataclass(frozen=True)
class Target:
    """One browser family's registration point."""

    browser: str
    kind: str  # "chrome" (allowed_origins) or "firefox" (allowed_extensions)
    registry_key: str  # HKCU subkey (Windows)
    mac_dir: str  # relative to ~/Library/Application Support
    linux_dir: str  # relative to ~


TARGETS = (
    Target("chrome", "chrome", r"Software\Google\Chrome\NativeMessagingHosts",
           "Google/Chrome/NativeMessagingHosts", ".config/google-chrome/NativeMessagingHosts"),
    Target("chromium", "chrome", r"Software\Chromium\NativeMessagingHosts",
           "Chromium/NativeMessagingHosts", ".config/chromium/NativeMessagingHosts"),
    Target("edge", "chrome", r"Software\Microsoft\Edge\NativeMessagingHosts",
           "Microsoft Edge/NativeMessagingHosts", ".config/microsoft-edge/NativeMessagingHosts"),
    Target("brave", "chrome", r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
           "BraveSoftware/Brave-Browser/NativeMessagingHosts", ".config/BraveSoftware/Brave-Browser/NativeMessagingHosts"),
    Target("firefox", "firefox", r"Software\Mozilla\NativeMessagingHosts",
           "Mozilla/NativeMessagingHosts", ".mozilla/native-messaging-hosts"),
)


class _WinRegistry:
    """HKCU access for the default value of a key; replaced by a fake in tests."""

    def set_default(self, subkey: str, value: str) -> None:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, value)

    def get_default(self, subkey: str) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as k:
                return winreg.QueryValueEx(k, "")[0]
        except FileNotFoundError:
            return None

    def delete(self, subkey: str) -> None:
        import winreg

        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)
        except FileNotFoundError:
            pass


registry = _WinRegistry()  # monkeypatch with an object that has set_default/get_default/delete


# helpers -----------------------------------------------------------------------


def _platform(platform: str | None) -> str:
    return platform or sys.platform


def _data_dir(data: Path | None) -> Path:
    if data is not None:
        return Path(data)
    from .util import data_dir

    return data_dir()


def manifest(kind: str, executable: Path | str) -> dict:
    m = {"name": HOST_NAME, "description": HOST_DESCRIPTION, "path": str(executable), "type": "stdio"}
    if kind == "firefox":
        m["allowed_extensions"] = [FIREFOX_EXTENSION_ID]
    else:
        m["allowed_origins"] = [CHROME_ORIGIN]
    return m


def host_executable(platform: str | None = None, data: Path | None = None) -> Path:
    """The program browsers should launch.

    Frozen builds ship ``fetchly-host`` next to the app executable. From source a small
    launcher script is generated in the data folder.
    """
    platform = _platform(platform)
    win = platform == "win32"
    if getattr(sys, "frozen", False):
        return Path(sys.executable).with_name("fetchly-host.exe" if win else "fetchly-host")
    folder = _data_dir(data) / "native-host"
    folder.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable)
    if win:
        console = python.with_name("python.exe")  # the host needs stdin/stdout; pythonw has none
        if console.exists():
            python = console
    root = Path(__file__).resolve().parent.parent
    if win:
        path = folder / "fetchly-host.bat"
        body = f'@echo off\r\nset "PYTHONPATH={root};%PYTHONPATH%"\r\n"{python}" -m fetchly.native_host %*\r\n'
    else:
        path = folder / "fetchly-host.sh"
        body = f'#!/bin/sh\nPYTHONPATH="{root}${{PYTHONPATH:+:$PYTHONPATH}}" exec "{python}" -m fetchly.native_host "$@"\n'
    _write_if_changed(path, body)
    if not win:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _write_if_changed(path: Path, text: str) -> None:
    data = text.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _manifest_text(kind: str, executable: Path | str) -> str:
    return json.dumps(manifest(kind, executable), indent=2) + "\n"


def _manifest_files(platform: str, home: Path, data: Path | None) -> list[tuple[Target, Path]]:
    """Where each browser's manifest file lives (and whether to bother with that browser)."""
    out: list[tuple[Target, Path]] = []
    if platform == "win32":
        folder = _data_dir(data) / "native-host"
        for t in TARGETS:
            out.append((t, folder / f"{HOST_NAME}.{t.kind}.json"))  # chrome-family share one file
        return out
    for t in TARGETS:
        rel = t.mac_dir if platform == "darwin" else t.linux_dir
        base = home / "Library" / "Application Support" if platform == "darwin" else home
        folder = base / rel
        if folder.parent.exists():  # skip browsers that were never installed
            out.append((t, folder / f"{HOST_NAME}.json"))
    return out


# public API --------------------------------------------------------------------


def register(home: Path | None = None, platform: str | None = None, reg=None,
             data: Path | None = None, executable: Path | str | None = None) -> list[Path]:
    """Write the manifests (and registry keys on Windows). Safe to call on every start.

    Returns the manifest files that exist afterwards.
    """
    platform = _platform(platform)
    home = Path(home) if home else Path.home()
    reg = reg or registry
    exe = executable or host_executable(platform, data)
    written: list[Path] = []
    for target, path in _manifest_files(platform, home, data):
        _write_if_changed(path, _manifest_text(target.kind, exe))
        if platform == "win32" and reg.get_default(target.registry_key + "\\" + HOST_NAME) != str(path):
            reg.set_default(target.registry_key + "\\" + HOST_NAME, str(path))
        if path not in written:
            written.append(path)
    return written


def unregister(home: Path | None = None, platform: str | None = None, reg=None,
               data: Path | None = None) -> None:
    platform = _platform(platform)
    home = Path(home) if home else Path.home()
    reg = reg or registry
    for target, path in _manifest_files(platform, home, data):
        if platform == "win32":
            reg.delete(target.registry_key + "\\" + HOST_NAME)
        path.unlink(missing_ok=True)


def is_registered(home: Path | None = None, platform: str | None = None, reg=None,
                  data: Path | None = None, executable: Path | str | None = None) -> bool:
    """True when every manifest (and Windows registry key) exists and points at the current host."""
    platform = _platform(platform)
    home = Path(home) if home else Path.home()
    reg = reg or registry
    exe = str(executable or host_executable(platform, data))
    files = _manifest_files(platform, home, data)
    if not files:
        return False
    for target, path in files:
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("path") != exe:
                return False
        except (OSError, ValueError):
            return False
        if platform == "win32" and reg.get_default(target.registry_key + "\\" + HOST_NAME) != str(path):
            return False
    return True
