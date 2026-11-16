"""Formatting and path helpers shared by the CLI and the GUI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def human_size(n: float | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def human_speed(bps: float) -> str:
    return f"{human_size(bps)}/s" if bps > 0 else "-"


def human_eta(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 1:
        return "<1s"
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s // 3600}h {(s % 3600) // 60:02d}m"


def data_dir() -> Path:
    """Where the database lives, following each platform's convention."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "Fetchly"


def default_db_path() -> Path:
    return data_dir() / "fetchly.db"


def default_download_dir() -> Path:
    return Path.home() / "Downloads"


def reveal_in_file_manager(path: Path) -> bool:
    """Open the file manager with ``path`` selected. Returns False where that isn't supported."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(path)])
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
            return True
    except OSError:
        pass
    return False  # Linux file managers have no common "select this file" command
