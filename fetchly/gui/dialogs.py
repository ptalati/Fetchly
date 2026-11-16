"""Add URL and Settings dialogs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..engine import MAX_CONNECTIONS


def _folder_row(parent: QWidget, edit: QLineEdit) -> QWidget:
    row = QWidget(parent)
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    h.addWidget(edit, 1)
    browse = QPushButton("Browse...")
    browse.setAutoDefault(False)

    def pick():
        folder = QFileDialog.getExistingDirectory(parent, "Save to folder", edit.text())
        if folder:
            edit.setText(folder)

    browse.clicked.connect(pick)
    h.addWidget(browse)
    return row


class AddUrlDialog(QDialog):
    def __init__(self, parent, url: str, folder: str, connections: int, headers: dict[str, str] | None = None):
        super().__init__(parent)
        self.headers = dict(headers or {})  # request headers from the browser (cookies, referer)
        self.setWindowTitle("Add download")
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(14)
        title = QLabel("Add a download")
        title.setObjectName("detailTitle")
        v.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.url = QLineEdit(url)
        self.url.setPlaceholderText("https://example.com/file.zip")
        form.addRow("URL", self.url)
        self.folder = QLineEdit(folder)
        form.addRow("Save to", _folder_row(self, self.folder))
        self.connections = QSpinBox()
        self.connections.setRange(1, MAX_CONNECTIONS)
        self.connections.setValue(connections)
        self.connections.setFixedWidth(90)
        form.addRow("Connections", self.connections)
        self.start_now = QCheckBox("Start now")
        self.start_now.setChecked(True)
        form.addRow("", self.start_now)
        v.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = buttons.button(QDialogButtonBox.Ok)
        ok.setText("Download")
        ok.setObjectName("primary")
        ok.setDefault(True)
        buttons.button(QDialogButtonBox.Cancel).setAutoDefault(False)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)
        self.url.selectAll()

    def _accept(self):
        url = self.url.text().strip()
        if not url.lower().startswith(("http://", "https://")):
            self.url.setFocus()
            self.url.setStyleSheet("border-color: #F87171;")
            return
        if not self.folder.text().strip():
            self.folder.setFocus()
            return
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, parent, folder: str, connections: int, max_active: int, *, autostart: bool = False,
                 watch_clipboard: bool = True, browser_confirm: bool = True, host_registered: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(14)
        title = QLabel("Settings")
        title.setObjectName("detailTitle")
        v.addWidget(title)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.folder = QLineEdit(folder)
        form.addRow("Default folder", _folder_row(self, self.folder))
        self.connections = QSpinBox()
        self.connections.setRange(1, MAX_CONNECTIONS)
        self.connections.setValue(connections)
        self.connections.setFixedWidth(90)
        form.addRow("Connections per download", self.connections)
        self.max_active = QSpinBox()
        self.max_active.setRange(1, 10)
        self.max_active.setValue(max_active)
        self.max_active.setFixedWidth(90)
        form.addRow("Simultaneous downloads", self.max_active)
        self.autostart = QCheckBox("Start Fetchly when I sign in")
        self.autostart.setChecked(autostart)
        form.addRow("", self.autostart)
        self.watch_clipboard = QCheckBox("Watch clipboard for download links")
        self.watch_clipboard.setChecked(watch_clipboard)
        form.addRow("", self.watch_clipboard)
        self.browser_confirm = QCheckBox("Ask before downloading links from the browser")
        self.browser_confirm.setChecked(browser_confirm)
        form.addRow("", self.browser_confirm)
        v.addLayout(form)
        self.host_status = QLabel("Browser extension host: " + ("registered" if host_registered else "not registered"))
        self.host_status.setObjectName("caption")
        v.addWidget(self.host_status)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save = buttons.button(QDialogButtonBox.Save)
        save.setObjectName("primary")
        save.setDefault(True)
        buttons.button(QDialogButtonBox.Cancel).setAutoDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)
