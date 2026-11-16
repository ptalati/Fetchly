# Fetchly

A personal multi-connection download manager for Windows (Python + PySide6).

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
```

## Use

- GUI: `.venv\Scripts\python -m fetchly`
- CLI: `.venv\Scripts\python -m fetchly <url> -c 8 -o <folder>`
- Tests: `.venv\Scripts\python -m pytest -q`

## How it works

- `fetchly/engine/` (no Qt): probes size, byte-range support, filename and ETag, then downloads up to 16 parallel range segments into a pre-allocated `.part` file. It splits the largest remaining segment when a connection frees up, retries with backoff, falls back to one connection when ranges are not supported, and renames the file when done.
- Progress per segment is saved in SQLite, so paused or interrupted downloads resume where they stopped.
- `fetchly/gui/`: toolbar, category sidebar, download list, per-connection detail panel, Add URL and Settings dialogs, tray icon with completion notifications.

Packaging (PyInstaller / Inno Setup) and the browser extension are later phases.
