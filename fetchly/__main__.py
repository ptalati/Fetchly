"""``python -m fetchly <url> ...`` runs the CLI; ``python -m fetchly`` with no arguments opens the window."""

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from .cli import main as cli_main

        return cli_main()
    from .gui.app import main as gui_main

    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
