# Fetchly

A fast multi-connection download manager for Windows, macOS and Linux. Fetchly splits a download into up to 16 parallel connections, and paused or interrupted downloads resume where they stopped.

## Download

| Platform | File | |
|---|---|---|
| Windows 10/11 (64-bit) | [Fetchly-Windows-Setup.exe](https://github.com/ptalati/Fetchly/releases/latest/download/Fetchly-Windows-Setup.exe) | Installer, adds Start menu and optional desktop shortcut |
| macOS (Apple Silicon) | [Fetchly-macOS.dmg](https://github.com/ptalati/Fetchly/releases/latest/download/Fetchly-macOS.dmg) | Open it and drag Fetchly to Applications |
| Linux (x86_64) | [Fetchly-Linux-x86_64.tar.gz](https://github.com/ptalati/Fetchly/releases/latest/download/Fetchly-Linux-x86_64.tar.gz) | Extract and run `Fetchly/Fetchly` |

All versions are on the [Releases](https://github.com/ptalati/Fetchly/releases) page. No Python is needed.

**First launch:** the builds are not code-signed yet, so the system will warn you once.
- **Windows:** if SmartScreen says "Windows protected your PC", click **More info**, then **Run anyway**.
- **macOS:** if it says Fetchly "cannot be opened", go to **System Settings > Privacy & Security** and click **Open Anyway**. Or run `xattr -dr com.apple.quarantine /Applications/Fetchly.app` once.
- **Linux:** needs a desktop with the usual Qt/X11 libraries (any recent Ubuntu, Fedora or Mint has them).

## Features

- Up to 16 parallel connections per download. When one finishes early, it splits the largest remaining piece so every connection stays busy.
- Pause and resume, including after closing the app or a crash.
- Falls back to a single connection on servers that don't support byte ranges.
- Retries dropped connections with backoff.
- Sidebar filters by status and file type, a detail panel with one bar per connection, and tray notifications when a download finishes.
- A command-line mode for scripts and servers.

## Run from source

Needs Python 3.11 or newer.

```
python -m venv .venv
.venv\Scripts\pip install -e .[dev]        # macOS/Linux: .venv/bin/pip
```

- GUI: `python -m fetchly`
- CLI: `python -m fetchly <url> -c 8 -o <folder>`
- Tests: `python -m pytest -q`

## Build the installers

`.github/workflows/release.yml` builds all three files on GitHub Actions. Push a version tag and the files are attached to a new release:

```
git tag v0.1.0
git push origin v0.1.0
```

To build locally: `pip install pyinstaller pillow`, then `pyinstaller packaging/fetchly.spec`. That gives `dist/Fetchly/` (or `dist/Fetchly.app` on macOS). The Windows installer additionally needs [Inno Setup](https://jrsoftware.org/isinfo.php): `iscc packaging\fetchly.iss`. Each platform's build has to be made on that platform.

## How it works

- `fetchly/engine/` (no Qt): probes size, byte-range support, filename and ETag, then downloads parallel range segments into a pre-allocated `.part` file and renames it when done.
- Progress per segment is saved in SQLite, so downloads resume where they stopped. The database lives in `%LOCALAPPDATA%\Fetchly` on Windows, `~/Library/Application Support/Fetchly` on macOS and `~/.local/share/Fetchly` on Linux.
- `fetchly/gui/`: PySide6 window, list model and dialogs.
