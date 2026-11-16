"""Fetchly main window: toolbar, category sidebar, download list, detail panel, tray."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHeaderView, QLabel, QMainWindow, QMenu, QMessageBox,
    QSizePolicy, QSplitter, QSystemTrayIcon, QTableView, QToolBar, QWidget, QHBoxLayout,
)

from ..engine import DEFAULT_CONNECTIONS, DownloadManager, DownloadSnapshot, Status
from ..util import default_download_dir, human_speed
from . import icons
from .dialogs import AddUrlDialog, SettingsDialog
from .model import DownloadModel, NameDelegate
from .widgets import DetailPanel, Sidebar

REFRESH_MS = 500


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

        self._build_toolbar()
        self._build_body()
        self._build_tray()
        self._build_statusbar()

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

    # layout -----------------------------------------------------------------

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        self.act_add = QAction(icons.add_icon(), "Add URL", self, shortcut="Ctrl+N", triggered=self.add_url)
        self.act_resume = QAction(icons.resume_icon(), "Resume", self, triggered=self.resume_selected)
        self.act_pause = QAction(icons.pause_icon(), "Pause", self, triggered=self.pause_selected)
        self.act_remove = QAction(icons.remove_icon(), "Remove", self, shortcut="Delete", triggered=self.remove_selected)
        self.act_settings = QAction(icons.settings_icon(), "Settings", self, triggered=self.open_settings)
        tb.addAction(self.act_add)
        tb.widgetForAction(self.act_add).setObjectName("primary")
        tb.addSeparator()
        for a in (self.act_resume, self.act_pause, self.act_remove):
            tb.addAction(a)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self.act_settings)

    def _build_body(self):
        self.sidebar = Sidebar()
        self.sidebar.filterChanged.connect(self._filter_changed)

        self.model = DownloadModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setItemDelegateForColumn(0, NameDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setWordWrap(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(lambda _i: self.open_file())
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, w in ((1, 170), (2, 110), (3, 110), (4, 100)):
            h.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, w)
        h.setHighlightSections(False)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._selection_changed())

        self.detail = DetailPanel()

        right = QSplitter(Qt.Vertical)
        right.addWidget(self.table)
        right.addWidget(self.detail)
        right.setStretchFactor(0, 3)
        right.setStretchFactor(1, 2)
        right.setHandleWidth(1)
        right.setSizes([470, 260])

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.sidebar)
        lay.addWidget(right, 1)
        self.setCentralWidget(central)

    def _build_statusbar(self):
        self.status_left = QLabel()
        self.status_right = QLabel()
        self.statusBar().addWidget(self.status_left, 1)
        self.status_right.setMinimumWidth(180)
        self.status_right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.statusBar().addPermanentWidget(self.status_right)
        self.statusBar().setSizeGripEnabled(False)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        self.tray.setToolTip("Fetchly")
        menu = QMenu()
        menu.addAction("Show Fetchly", self.show_window)
        menu.addAction("Add URL...", self.add_url)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)
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
        done = sum(1 for s in snaps if s.status == Status.COMPLETED)
        self.status_left.setText(f"{len(running)} active  -  {done} finished  -  {len(snaps)} total")
        self.status_right.setText(f"Total speed {human_speed(total)}" if running else "Idle")
        self.tray.setToolTip(f"Fetchly - {len(running)} active, {human_speed(total)}" if running else "Fetchly")

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

    def add_url(self, url: str | None = None):
        self.show_window()
        if not isinstance(url, str):  # QAction.triggered passes `checked` (bool)
            clip = QGuiApplication.clipboard().text().strip()
            url = clip if clip.lower().startswith(("http://", "https://")) and "\n" not in clip else ""
        dlg = AddUrlDialog(
            self, url,
            self.setting("default_folder", str(default_download_dir())),
            self.setting("default_connections", DEFAULT_CONNECTIONS),
        )
        if dlg.exec() != AddUrlDialog.Accepted:
            return
        folder = dlg.folder.text().strip()
        Path(folder).mkdir(parents=True, exist_ok=True)
        new_id = self.manager.add(dlg.url.text().strip(), folder, dlg.connections.value(),
                                  start=dlg.start_now.isChecked())
        self.refresh()
        row = self.model.row_of(new_id)
        if row >= 0:
            self.table.selectRow(row)

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
        dlg = SettingsDialog(
            self,
            self.setting("default_folder", str(default_download_dir())),
            self.setting("default_connections", DEFAULT_CONNECTIONS),
            self.setting("max_active", 3),
        )
        if dlg.exec() != SettingsDialog.Accepted:
            return
        store = self.manager.store
        store.set_setting("default_folder", dlg.folder.text().strip())
        store.set_setting("default_connections", str(dlg.connections.value()))
        store.set_setting("max_active", str(dlg.max_active.value()))
        self.manager.set_max_active(dlg.max_active.value())

    def _final_path(self, s: DownloadSnapshot) -> Path | None:
        return Path(s.folder) / s.filename if s.filename else None

    def open_file(self):
        snaps = self.selected_snapshots()
        if not snaps:
            return
        s = snaps[0]
        p = self._final_path(s)
        if s.status == Status.COMPLETED and p and p.exists():
            os.startfile(str(p))
        else:
            self.open_folder()

    def open_folder(self):
        snaps = self.selected_snapshots()
        if not snaps:
            return
        s = snaps[0]
        p = self._final_path(s)
        if s.status == Status.COMPLETED and p and p.exists():
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
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

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self._quitting = True
        self.tray.hide()
        self.close()
        QGuiApplication.instance().quit()

    def closeEvent(self, e):
        running = any(s.status.is_running or s.status == Status.QUEUED for s in self.manager.snapshots())
        if running and not self._quitting:
            e.ignore()
            self.hide()
            self.tray.showMessage("Fetchly is still downloading",
                                  "Downloads continue in the background. Right-click the tray icon to quit.",
                                  icons.app_icon(), 4000)
            return
        self._quitting = True
        self.tray.hide()
        e.accept()
        QGuiApplication.instance().quit()
