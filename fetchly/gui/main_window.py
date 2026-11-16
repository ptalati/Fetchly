"""Fetchly main window: toolbar, category sidebar, download list, detail panel, tray."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHeaderView, QMainWindow, QMenu, QMessageBox,
    QSizePolicy, QSystemTrayIcon, QTableView, QToolBar, QVBoxLayout, QWidget, QHBoxLayout,
)

from .. import autostart, native_host_install
from ..engine import DEFAULT_CONNECTIONS, DownloadManager, DownloadSnapshot, Status
from ..util import default_download_dir, human_speed, reveal_in_file_manager
from . import icons, theme
from .clipboard_watch import ClipboardWatcher
from .dialogs import AddUrlDialog, SettingsDialog
from .model import DownloadModel, NameDelegate, TextDelegate
from .taskbar import TaskbarProgress, overall
from .widgets import DetailPanel, HeaderBar, Sidebar

REFRESH_MS = 500
BROWSER_DEDUPE_SECONDS = 15  # the same link from the browser again within this window is ignored


class MainWindow(QMainWindow):
    def __init__(self, manager: DownloadManager):
        super().__init__()
        self.manager = manager
        self.setWindowTitle("Fetchly")
        self.setWindowIcon(icons.app_icon())
        self.resize(1180, 760)
        self._quitting = False
        self._last_status: dict[int, Status] = {}
        self._notify_folder: str | None = None
        self._add_dialog_open = False
        self._pending_adds: list[dict] = []
        self._recent_browser_urls: dict[str, float] = {}  # url -> time.monotonic() when received
        self.add_dialog: AddUrlDialog | None = None

        self.header = HeaderBar()
        self.setMenuWidget(self.header)
        self._build_toolbar()
        self._build_body()
        self._build_tray()

        self.act_quit = QAction("Quit Fetchly", self, shortcut="Ctrl+Q", triggered=self.quit_app)
        self.addAction(self.act_quit)
        self.clipboard_watcher = ClipboardWatcher(self, enabled=self.flag("watch_clipboard", True))
        self.clipboard_watcher.linkCopied.connect(self._on_clipboard_link)
        self.act_watch.setChecked(self.clipboard_watcher.enabled)

        self.taskbar = TaskbarProgress()
        theme.on_change(self._theme_changed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)
        self.refresh()

    # settings -------------------------------------------------------------

    def setting(self, key: str, default):
        v = self.manager.store.get_setting(key)
        if v is None:
            return default
        return type(default)(v)

    def flag(self, key: str, default: bool) -> bool:
        v = self.manager.store.get_setting(key)
        return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")

    def set_flag(self, key: str, value: bool) -> None:
        self.manager.store.set_setting(key, "1" if value else "0")

    def attach_server(self, server) -> None:
        """Handle "show" and "add" requests from second launches and the browser extension."""
        server.showRequested.connect(self.show_window)
        server.addRequested.connect(self.on_browser_add)

    # layout -----------------------------------------------------------------

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        self.act_add = QAction("Add URL", self, shortcut="Ctrl+N", triggered=self.add_url)
        self.act_resume = QAction("Resume", self, triggered=self.resume_selected)
        self.act_pause = QAction("Pause", self, triggered=self.pause_selected)
        self.act_remove = QAction("Remove", self, shortcut="Delete", triggered=self.remove_selected)
        self.act_settings = QAction("Settings", self, triggered=self.open_settings)
        self._apply_icons()
        tb.addAction(self.act_add)
        for a in (self.act_resume, self.act_pause, self.act_remove):
            tb.addAction(a)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self.act_settings)
        sb = tb.widgetForAction(self.act_settings)
        sb.setObjectName("iconOnly")
        sb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        sb.setToolTip("Settings")

    def _apply_icons(self) -> None:
        """(Re)create the toolbar icons in the active theme's colours."""
        for act, make in ((self.act_add, icons.add_icon), (self.act_resume, icons.resume_icon),
                          (self.act_pause, icons.pause_icon), (self.act_remove, icons.remove_icon),
                          (self.act_settings, icons.settings_icon)):
            act.setIcon(make())

    def _theme_changed(self, _palette) -> None:
        self._apply_icons()
        self.header.refresh_theme()
        self.sidebar.viewport().update()
        self.table.viewport().update()
        self._update_detail()

    def _build_body(self):
        self.sidebar = Sidebar()
        self.sidebar.filterChanged.connect(self._filter_changed)

        self.model = DownloadModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setItemDelegate(TextDelegate(self.table))
        self.table.setItemDelegateForColumn(0, NameDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(50)
        self.table.setWordWrap(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(lambda _i: self.open_file())
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, w in ((1, 90), (2, 100), (3, 80)):
            h.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, w)
        h.setHighlightSections(False)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._selection_changed())

        self.detail = DetailPanel()

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.table, 1)
        rl.addWidget(self.detail)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.sidebar)
        lay.addWidget(right, 1)
        self.setCentralWidget(central)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        self.tray.setToolTip("Fetchly")
        menu = QMenu()
        menu.addAction("Open Fetchly", self.show_window)
        menu.addAction("Add URL...", lambda: self.add_url(show_main=False))
        menu.addAction("Pause all", self.pause_all)
        self.act_watch = menu.addAction("Watch clipboard")
        self.act_watch.setCheckable(True)
        self.act_watch.toggled.connect(self._watch_toggled)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self._open_notified_folder)
        self.tray.show()

    # refresh ------------------------------------------------------------------

    def refresh(self):
        snaps = self.manager.snapshots()
        self._notify_completions(snaps)
        selected = self.selected_ids()
        if self.model.update(snaps):
            self._restore_selection(selected)
        self.sidebar.update_counts(snaps)
        self._update_detail()
        self._update_actions()
        running = [s for s in snaps if s.status.is_running]
        total = sum(s.speed for s in running)
        self.header.set_speed(human_speed(total) if running and total > 0 else None)
        self.tray.setToolTip(f"Fetchly - {len(running)} active, {human_speed(total)}" if running else "Fetchly")
        self.taskbar.update(int(self.winId()), *overall(snaps))

    def _notify_completions(self, snaps: list[DownloadSnapshot]):
        for s in snaps:
            prev = self._last_status.get(s.id)
            if prev is not None and prev != Status.COMPLETED and s.status == Status.COMPLETED:
                self._notify_folder = s.folder
                self.tray.showMessage("Download complete", s.filename or s.url, icons.app_icon(), 6000)
            elif prev is not None and prev != Status.ERROR and s.status == Status.ERROR:
                self.tray.showMessage("Download failed", f"{s.filename or s.url}\n{s.error or ''}",
                                      QSystemTrayIcon.Warning, 6000)
            self._last_status[s.id] = s.status

    def _restore_selection(self, ids: list[int]):
        sm = self.table.selectionModel()
        sm.blockSignals(True)
        sm.clearSelection()
        for i in ids:
            row = self.model.row_of(i)
            if row >= 0:
                sm.select(self.model.index(row, 0),
                          QItemSelectionModel.Select | QItemSelectionModel.Rows)
        sm.blockSignals(False)
        self.table.viewport().update()

    def _selection_changed(self):
        self._update_detail()
        self._update_actions()

    def _update_detail(self):
        snaps = self.selected_snapshots()
        self.detail.show_snapshot(snaps[0] if snaps else None)

    def _update_actions(self):
        snaps = self.selected_snapshots()
        self.act_resume.setEnabled(any(s.status in (Status.PAUSED, Status.ERROR) for s in snaps))
        self.act_pause.setEnabled(any(s.status.is_running or s.status == Status.QUEUED for s in snaps))
        self.act_remove.setEnabled(bool(snaps))

    def _filter_changed(self, key: str):
        self.model.filter_key = key
        self.refresh()

    # selection helpers ------------------------------------------------------------

    def selected_snapshots(self) -> list[DownloadSnapshot]:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [s for s in (self.model.snapshot_at(r) for r in rows) if s]

    def selected_ids(self) -> list[int]:
        return [s.id for s in self.selected_snapshots()]

    # commands ------------------------------------------------------------------

    def add_url(self, url: str | None = None, headers: dict[str, str] | None = None, show_main: bool = True):
        if self._add_dialog_open:
            return
        if show_main:
            self.show_window()
        if not isinstance(url, str):  # QAction.triggered passes `checked` (bool)
            clip = QGuiApplication.clipboard().text().strip()
            url = clip if clip.lower().startswith(("http://", "https://")) and "\n" not in clip else ""
        dlg = AddUrlDialog(
            self, url,
            self.setting("default_folder", str(default_download_dir())),
            self.setting("default_connections", DEFAULT_CONNECTIONS),
            headers=headers,
        )
        self.add_dialog = dlg
        self._add_dialog_open = True
        try:
            dlg.show()
            self._bring_to_front(dlg)
            accepted = dlg.exec() == AddUrlDialog.Accepted
        finally:
            self._add_dialog_open = False
            self.add_dialog = None
            self.clipboard_watcher.forget_last()
        if accepted:
            folder = dlg.folder.text().strip()
            Path(folder).mkdir(parents=True, exist_ok=True)
            new_id = self.manager.add(dlg.url.text().strip(), folder, dlg.connections.value(),
                                      start=dlg.start_now.isChecked(), headers=dlg.headers or None)
            self.refresh()
            row = self.model.row_of(new_id)
            if row >= 0:
                self.table.selectRow(row)
        if self._pending_adds:  # browser downloads that arrived while the dialog was open
            QTimer.singleShot(0, self._run_pending_add)

    def _run_pending_add(self):
        if self._pending_adds and not self._add_dialog_open:
            self.on_browser_add(self._pending_adds.pop(0))

    def on_browser_add(self, msg: dict):
        """A download handed over by the browser extension (via the native host)."""
        url = msg.get("url")
        if not isinstance(url, str) or not url:
            return
        if not msg.get("_queued"):
            # One click can reach us twice (browser retries, a resent hand-off): drop repeats.
            now = time.monotonic()
            self._recent_browser_urls = {u: t for u, t in self._recent_browser_urls.items()
                                         if now - t < BROWSER_DEDUPE_SECONDS}
            if url in self._recent_browser_urls:
                return
            self._recent_browser_urls[url] = now
        headers = msg.get("headers")
        headers = {str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) and headers else {}
        referrer = msg.get("referrer")
        if not headers and isinstance(referrer, str) and referrer:
            headers = {"Referer": referrer}
        if self.flag("browser_confirm", True):
            if self._add_dialog_open:
                self._pending_adds.append({**msg, "_queued": True})
                return
            self.add_url(url, headers=headers, show_main=False)
            return
        folder = self.setting("default_folder", str(default_download_dir()))
        Path(folder).mkdir(parents=True, exist_ok=True)
        self.manager.add(url, folder, self.setting("default_connections", DEFAULT_CONNECTIONS),
                         start=True, headers=headers or None)
        self.refresh()
        self.tray.showMessage("Download added", url, icons.app_icon(), 4000)

    def _on_clipboard_link(self, url: str):
        if self._add_dialog_open or any(s.url == url for s in self.manager.snapshots()):
            return
        self.add_url(url, show_main=False)

    def _watch_toggled(self, on: bool):
        self.clipboard_watcher.enabled = on
        self.set_flag("watch_clipboard", on)

    def pause_all(self):
        for s in self.manager.snapshots():
            if s.status.is_running or s.status == Status.QUEUED:
                self.manager.pause(s.id)
        QTimer.singleShot(100, self.refresh)

    @staticmethod
    def _bring_to_front(w: QWidget) -> None:
        """Raise a window above other apps. Windows refuses plain activateWindow() from a background process."""
        w.setWindowState((w.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        w.show()
        w.raise_()
        w.activateWindow()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(int(w.winId()))
            except Exception:
                pass

    def resume_selected(self):
        for s in self.selected_snapshots():
            if s.status in (Status.PAUSED, Status.ERROR):
                self.manager.resume(s.id)
        QTimer.singleShot(100, self.refresh)

    def pause_selected(self):
        for s in self.selected_snapshots():
            if s.status.is_running or s.status == Status.QUEUED:
                self.manager.pause(s.id)
        QTimer.singleShot(100, self.refresh)

    def remove_selected(self):
        snaps = self.selected_snapshots()
        if not snaps:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Remove")
        box.setIcon(QMessageBox.Question)
        name = snaps[0].filename or snaps[0].url if len(snaps) == 1 else f"{len(snaps)} downloads"
        box.setText(f"Remove {name} from the list?")
        box.setInformativeText("Unfinished partial files are always deleted.")
        also = QCheckBox("Also delete the downloaded file from disk")
        box.setCheckBox(also)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.button(QMessageBox.Yes).setText("Remove")
        if box.exec() != QMessageBox.Yes:
            return
        for s in snaps:
            self.manager.remove(s.id, delete_file=also.isChecked())
            self._last_status.pop(s.id, None)
        self.refresh()

    def open_settings(self):
        try:
            start_at_login = autostart.is_enabled()
        except Exception:
            start_at_login = False
        try:
            host_ok = native_host_install.is_registered()
        except Exception:
            host_ok = False
        dlg = SettingsDialog(
            self,
            self.setting("default_folder", str(default_download_dir())),
            self.setting("default_connections", DEFAULT_CONNECTIONS),
            self.setting("max_active", 3),
            autostart=start_at_login,
            watch_clipboard=self.clipboard_watcher.enabled,
            browser_confirm=self.flag("browser_confirm", True),
            host_registered=host_ok,
        )
        if dlg.exec() != SettingsDialog.Accepted:
            return
        store = self.manager.store
        store.set_setting("default_folder", dlg.folder.text().strip())
        store.set_setting("default_connections", str(dlg.connections.value()))
        store.set_setting("max_active", str(dlg.max_active.value()))
        self.manager.set_max_active(dlg.max_active.value())
        self.set_flag("browser_confirm", dlg.browser_confirm.isChecked())
        self.act_watch.setChecked(dlg.watch_clipboard.isChecked())  # toggled -> watcher + setting
        if dlg.autostart.isChecked() != start_at_login:
            try:
                autostart.set_enabled(dlg.autostart.isChecked())
            except Exception as exc:
                QMessageBox.warning(self, "Start at sign-in", f"Could not change the setting: {exc}")

    def _final_path(self, s: DownloadSnapshot) -> Path | None:
        return Path(s.folder) / s.filename if s.filename else None

    def open_file(self):
        snaps = self.selected_snapshots()
        if not snaps:
            return
        s = snaps[0]
        p = self._final_path(s)
        if s.status == Status.COMPLETED and p and p.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
        else:
            self.open_folder()

    def open_folder(self):
        snaps = self.selected_snapshots()
        if not snaps:
            return
        s = snaps[0]
        p = self._final_path(s)
        if s.status == Status.COMPLETED and p and p.exists() and reveal_in_file_manager(p):
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(s.folder))

    def copy_link(self):
        snaps = self.selected_snapshots()
        if snaps:
            QGuiApplication.clipboard().setText("\n".join(s.url for s in snaps))

    def _context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        if index.row() not in {i.row() for i in self.table.selectionModel().selectedRows()}:
            self.table.selectRow(index.row())
        menu = QMenu(self)
        menu.addAction("Open", self.open_file)
        menu.addAction("Open folder", self.open_folder)
        menu.addAction("Copy link", self.copy_link)
        menu.addSeparator()
        menu.addAction(self.act_resume)
        menu.addAction(self.act_pause)
        menu.addAction(self.act_remove)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # tray / window ------------------------------------------------------------------

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()

    def _open_notified_folder(self):
        if self._notify_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._notify_folder))

    def tray_available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show_window(self):
        self._bring_to_front(self)

    def quit_app(self):
        self._quitting = True
        self.tray.hide()
        self.close()
        QGuiApplication.instance().quit()

    def closeEvent(self, e):
        if self._quitting:
            self.tray.hide()
            e.accept()
            QGuiApplication.instance().quit()
            return
        e.ignore()
        if not self.tray_available():  # nowhere to hide: minimise instead of losing the window
            self.showMinimized()
            return
        self.hide()
        if not self.flag("tray_hint_shown", False):
            self.set_flag("tray_hint_shown", True)
            self.tray.showMessage("Fetchly", "Fetchly is still running in the tray. Right-click the icon to quit.",
                                  icons.app_icon(), 5000)
