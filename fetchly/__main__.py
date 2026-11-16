"""``python -m fetchly <url> ...`` runs the CLI; ``python -m fetchly`` with no arguments opens the window.

``python -m fetchly --tray`` opens the GUI too; the GUI checks ``"--tray" in sys.argv`` to start
minimised to the system tray (used by start-at-sign-in and by the browser host).
"""

import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1:] != ["--tray"]:
        from .cli import main as cli_main

        return cli_main()
    from .gui.app import main as gui_main

    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
