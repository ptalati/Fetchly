"""Formatting and path helpers shared by the CLI and the GUI."""

from __future__ import annotations

import os
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
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "Fetchly"


def default_db_path() -> Path:
    return data_dir() / "fetchly.db"


def default_download_dir() -> Path:
    return Path.home() / "Downloads"
