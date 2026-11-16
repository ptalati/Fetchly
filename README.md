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

## Browser integration

Fetchly can take over downloads from Chrome, Edge, Brave and Firefox, and catches copied download links too.

1. Install and start Fetchly once. It registers itself with your browsers when it starts.
2. Download the extension from the [Releases](https://github.com/ptalati/Fetchly/releases) page: [Fetchly-Browser-Extension.zip](https://github.com/ptalati/Fetchly/releases/latest/download/Fetchly-Browser-Extension.zip) for Chrome, Edge and Brave, [Fetchly-Firefox-Extension.zip](https://github.com/ptalati/Fetchly/releases/latest/download/Fetchly-Firefox-Extension.zip) for Firefox. Unzip it somewhere permanent (the browser loads it from that folder).
3. Load it:
   - **Chrome:** open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick the unzipped folder.
   - **Edge:** the same at `edge://extensions`.
   - **Brave:** the same at `brave://extensions`.
   - **Firefox:** Firefox only keeps unsigned add-ons until it closes. Open `about:debugging#/runtime/this-firefox`, click **Load Temporary Add-on** and pick `manifest.json` from the unzipped folder. This is needed again after each restart until the add-on is signed.

The extension cancels the browser's own download and sends the link (with the cookies and referrer the browser used) to Fetchly, so logged-in and expiring links keep working. If Fetchly can't be reached, the browser downloads the file itself. Right-click a link and choose **Download with Fetchly** to send one by hand. The toolbar button turns capturing on or off, sets a minimum file size, and shows whether Fetchly is connected.

- **Start at sign-in:** Fetchly can start with your computer and sit in the system tray, so downloads from the browser are always caught.
- **Clipboard capture:** copy a link to a file (video, archive, installer, document and so on) and Fetchly offers to download it.

To build the extension zips yourself: `pip install pillow`, then `python browser-extension/build.py` (the zips land in `browser-extension/dist/`).

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
