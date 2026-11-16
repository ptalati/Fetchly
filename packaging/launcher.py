"""Entry point PyInstaller freezes into the Fetchly app."""

import sys

from fetchly.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
