"""GUI entry point: ``python -m fetchly`` (no arguments) or ``fetchly-gui``."""

from __future__ import annotations

import logging
import sys

log = logging.getLogger("fetchly")

URL_PREFIXES = ("http://", "https://")


def handoff_message(args: list[str]) -> dict:
    """What a second launch tells the running instance: add a URL, stay quiet (--tray), or show the window."""
    url = next((a for a in args if a.lower().startswith(URL_PREFIXES)), None)
    if url:
        return {"cmd": "add", "url": url}
    if "--tray" in args:
        return {"cmd": "ping"}  # started at sign-in while already running: do not pop the window up
    return {"cmd": "show"}


def hand_off_to_running(args: list[str], name: str | None = None) -> bool:
    """Pass this launch to an already-running Fetchly. True when it answered, so we should exit."""
    from .single_instance import send_to_running

    return send_to_running(handoff_message(args), name=name)


def init_first_run_autostart(store, frozen: bool | None = None) -> bool:
    """Turn start-at-sign-in on once, for installed builds only. Returns True when it was enabled now.

    "autostart_initialized" is stored so a user who later switches it off is not overridden.
    """
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if not frozen or store.get_setting("autostart_initialized") is not None:
        return False
    from .. import autostart

    try:
        autostart.set_enabled(True)
    except Exception:
        log.exception("could not enable start at sign-in")
        return False
    store.set_setting("autostart_initialized", "1")
    return True


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from ..engine import DownloadManager
    from ..util import data_dir, default_db_path
    from .icons import app_icon
    from .main_window import MainWindow
    from .single_instance import InstanceServer
    from .theme import apply_theme

    full_argv = list(sys.argv if argv is None else argv)
    args = full_argv[1:]

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Fetchly.Fetchly")
        except Exception:
            pass

    app = QApplication(full_argv)
    app.setApplicationName("Fetchly")
    app.setOrganizationName("Fetchly")
    app.setQuitOnLastWindowClosed(False)

    # One Fetchly per user: if it is already running, hand this launch over and leave.
    if hand_off_to_running(args):
        return 0
    server = InstanceServer(parent=app)
    if not server.listen():
        log.warning("could not listen for other Fetchly launches")

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
        init_first_run_autostart(manager.store)
        try:
            from .. import native_host_install
            native_host_install.register()
        except Exception:
            log.exception("could not register the browser extension host")
        window = MainWindow(manager)
        window.attach_server(server)
        if "--tray" in args and window.tray_available():
            pass  # tray only
        else:
            window.show_window()
        return app.exec()
    finally:
        server.close()
        manager.shutdown()


if __name__ == "__main__":
    sys.exit(main())
