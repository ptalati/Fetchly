"""Entry point PyInstaller freezes into the console fetchly-host (browser native messaging host)."""

import sys

from fetchly.native_host import main

if __name__ == "__main__":
    sys.exit(main())
