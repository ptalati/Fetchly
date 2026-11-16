"""Table model for the download list, its filters, and the progress-bar delegate."""

from __future__ import annotations

import os

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ..engine import DownloadSnapshot, Status
from ..util import human_eta, human_size, human_speed
from . import theme

CATEGORIES: dict[str, set[str]] = {
    "Video": {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "mpg", "mpeg", "ts"},
    "Archives": {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "iso", "zst"},
    "Programs": {"exe", "msi", "msix", "appx", "bat", "cmd", "dmg", "apk", "pkg", "deb", "rpm"},
    "Documents": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf", "odt", "ods",
                  "csv", "epub", "md"},
}

STATUS_FILTERS = {
    "All": lambda s: True,
    "Active": lambda s: s.status.is_running,
    "Queued": lambda s: s.status in (Status.QUEUED, Status.PAUSED, Status.ERROR),
    "Finished": lambda s: s.status == Status.COMPLETED,
}

STATUS_TEXT = {
    Status.QUEUED: "Queued",
    Status.CONNECTING: "Connecting",
    Status.DOWNLOADING: "Downloading",
    Status.PAUSED: "Paused",
    Status.COMPLETED: "Done",
    Status.ERROR: "Error",
}


def category_of(snap: DownloadSnapshot) -> str | None:
    name = snap.filename or snap.url.split("?")[0]
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    for cat, exts in CATEGORIES.items():
        if ext in exts:
            return cat
    return None


def matches(snap: DownloadSnapshot, key: str) -> bool:
    if key in STATUS_FILTERS:
        return STATUS_FILTERS[key](snap)
    return category_of(snap) == key


def display_name(snap: DownloadSnapshot) -> str:
    return snap.filename or snap.url


COLUMNS = ["Name", "Size", "Status", "Speed", "Time left"]
SnapRole = Qt.UserRole + 1


class DownloadModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[DownloadSnapshot] = []
        self.filter_key = "All"

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section].upper()
        if orientation == Qt.Horizontal and role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter) if section == 0 else int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        s = self._rows[index.row()]
        col = index.column()
        if role == SnapRole:
            return s
        if role == Qt.DisplayRole:
            if col == 0:
                return display_name(s)
            if col == 1:
                if s.size and s.status != Status.COMPLETED:
                    return f"{human_size(s.downloaded)} / {human_size(s.size)}"
                return human_size(s.size if s.size else s.downloaded or None)
            if col == 2:
                if s.status == Status.DOWNLOADING and s.progress is not None:
                    return f"{s.progress * 100:.0f}%"
                return STATUS_TEXT[s.status]
            if col == 3:
                return human_speed(s.speed) if s.status.is_running else ""
            if col == 4:
                return human_eta(s.eta) if s.status.is_running else ""
        if role == Qt.TextAlignmentRole and col > 0:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            if col == 2 and s.status == Status.ERROR:
                return QColor(theme.RED)
            if col == 2 and s.status == Status.COMPLETED:
                return QColor(theme.CYAN)
            if col == 3 and s.status.is_running:
                return QColor(theme.CYAN)
            if col > 0:
                return QColor(theme.MUTED) if col != 3 else None
        if role == Qt.ToolTipRole:
            return s.error if s.status == Status.ERROR else s.url
        return None

    def snapshot_at(self, row: int) -> DownloadSnapshot | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def row_of(self, download_id: int) -> int:
        for i, s in enumerate(self._rows):
            if s.id == download_id:
                return i
        return -1

    def update(self, snapshots: list[DownloadSnapshot]) -> bool:
        """Refresh rows. Returns True when the row set changed (selection must be restored)."""
        rows = sorted((s for s in snapshots if matches(s, self.filter_key)), key=lambda s: s.created_at, reverse=True)
        if [s.id for s in rows] == [s.id for s in self._rows]:
            self._rows = rows
            if rows:
                self.dataChanged.emit(self.index(0, 0), self.index(len(rows) - 1, len(COLUMNS) - 1))
            return False
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()
        return True


def _bar_gradient(rect: QRectF, status: Status) -> QLinearGradient | QColor:
    if status == Status.ERROR:
        return QColor(theme.RED)
    if status in (Status.PAUSED, Status.QUEUED):
        return QColor("#4B6491")
    g = QLinearGradient(rect.topLeft(), rect.topRight())
    g.setColorAt(0, QColor(theme.BLUE))
    g.setColorAt(1, QColor(theme.CYAN))
    return g


def paint_bar(p: QPainter, rect: QRectF, fraction: float | None, status: Status, radius: float = 2.5) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(theme.TRACK))
    p.drawRoundedRect(rect, radius, radius)
    if fraction is None:
        return
    w = rect.width() * max(0.0, min(1.0, fraction))
    if w <= 0:
        return
    fill = QRectF(rect.x(), rect.y(), max(w, radius * 2), rect.height())
    p.setBrush(_bar_gradient(rect, status))
    p.drawRoundedRect(fill, radius, radius)


class NameDelegate(QStyledItemDelegate):
    """File name on top, a slim progress bar underneath."""

    def paint(self, p: QPainter, option, index):
        s: DownloadSnapshot = index.data(SnapRole)
        self.initStyleOption(option, index)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if option.state & QStyle.State_Selected:
            p.fillRect(option.rect, QColor(theme.SURFACE_HI))
        r = QRectF(option.rect).adjusted(12, 7, -12, -8)
        f = QFont(option.font)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QPen(QColor(theme.TEXT)))
        text_rect = QRectF(r.x(), r.y(), r.width(), r.height() - 9)
        name = p.fontMetrics().elidedText(display_name(s), Qt.ElideMiddle, int(text_rect.width()))
        p.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, name)
        bar = QRectF(r.x(), r.bottom() - 4, r.width(), 4)
        paint_bar(p, bar, s.progress if s.status != Status.COMPLETED else 1.0, s.status, 2)
        p.restore()

    def sizeHint(self, option, index):
        return QSize(320, 46)
