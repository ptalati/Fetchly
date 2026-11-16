"""Builds the browser extension zips into browser-extension/dist/.

    python browser-extension/build.py

Writes Fetchly-Browser-Extension.zip (Chrome, Edge, Brave) and Fetchly-Firefox-Extension.zip.
Icons are generated from fetchly/gui/resources/fetchly-256.png with Pillow.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = HERE / "src"
DIST = HERE / "dist"
SIZES = (16, 32, 48, 128)
SOURCE_ICON = ROOT / "fetchly" / "gui" / "resources" / "fetchly-256.png"
SOURCE_FILES = ("background.js", "popup.html", "popup.js")
TARGETS = {"chrome": "Fetchly-Browser-Extension.zip", "firefox": "Fetchly-Firefox-Extension.zip"}


def make_icons() -> None:
    from PIL import Image

    icons = SRC / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE_ICON) as img:
        img = img.convert("RGBA")
        for s in SIZES:
            img.resize((s, s), Image.LANCZOS).save(icons / f"icon-{s}.png")


def build(target: str) -> Path:
    manifest = json.loads((HERE / f"manifest.{target}.json").read_text(encoding="utf-8"))
    DIST.mkdir(exist_ok=True)
    out = DIST / TARGETS[target]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        for name in SOURCE_FILES:
            z.write(SRC / name, name)
        for s in SIZES:
            z.write(SRC / "icons" / f"icon-{s}.png", f"icons/icon-{s}.png")
    return out


def main() -> int:
    make_icons()
    for target in TARGETS:
        print(build(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
