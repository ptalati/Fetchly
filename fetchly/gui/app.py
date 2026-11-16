"""GUI entry point: ``python -m fetchly`` (no arguments) or ``fetchly-gui``."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from ..engine import DownloadManager
    from ..util import data_dir, default_db_path
    from .icons import app_icon
    from .main_window import MainWindow
    from .theme import apply_theme

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Fetchly.Fetchly")
        except Exception:
            pass

    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("Fetchly")
    app.setOrganizationName("Fetchly")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    apply_theme(app)

    data_dir().mkdir(parents=True, exist_ok=True)
    manager = DownloadManager(default_db_path())
    try:
        manager.max_active = int(manager.store.get_setting("max_active", "3"))
    except ValueError:
        pass
    manager.start()
    try:
        window = MainWindow(manager)
        window.show()
        return app.exec()
    finally:
        manager.shutdown()


if __name__ == "__main__":
    sys.exit(main())
