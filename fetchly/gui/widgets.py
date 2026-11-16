"""Sidebar and the detail panel with one bar per connection."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QScrollArea, QSizePolicy, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..engine import DownloadSnapshot, SegmentView, Status
from ..util import human_size, human_speed
from . import theme
from .icons import dot_icon
from .model import CATEGORIES, STATUS_FILTERS, STATUS_TEXT, matches, paint_bar


class Sidebar(QTreeWidget):
    filterChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setHeaderHidden(True)
        self.setColumnCount(2)
        self.setRootIsDecorated(False)
        self.setIndentation(0)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedWidth(200)
        self.setIconSize(QSize(12, 12))
        self._items: dict[str, QTreeWidgetItem] = {}
        dots = {"All": theme.TEXT, "Active": theme.CYAN, "Queued": theme.MUTED, "Finished": theme.BLUE}
        for key in STATUS_FILTERS:
            self._add(key, dots[key])
        header = QTreeWidgetItem(self, ["CATEGORIES", ""])
        header.setFlags(Qt.NoItemFlags)
        f = QFont()
        f.setPointSizeF(8.5)
        f.setWeight(QFont.DemiBold)
        header.setFont(0, f)
        header.setForeground(0, QColor(theme.MUTED))
        header.setSizeHint(0, QSize(0, 36))
        cat_colors = {"Video": "#A78BFA", "Archives": theme.AMBER, "Programs": "#34D399", "Documents": "#60A5FA"}
        for key in CATEGORIES:
            self._add(key, cat_colors[key])
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hdr = self.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        self.setColumnWidth(1, 34)
        self.setCurrentItem(self._items["All"])
        self.currentItemChanged.connect(self._changed)

    def _add(self, key: str, color: str) -> None:
        item = QTreeWidgetItem(self, [key, ""])
        item.setData(0, Qt.UserRole, key)
        item.setIcon(0, dot_icon(color))
        item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
        item.setForeground(1, QColor(theme.MUTED))
        self._items[key] = item

    def _changed(self, cur, _prev):
        if cur is not None and cur.data(0, Qt.UserRole):
            self.filterChanged.emit(cur.data(0, Qt.UserRole))

    def update_counts(self, snaps: list[DownloadSnapshot]) -> None:
        for key, item in self._items.items():
            n = sum(1 for s in snaps if matches(s, key))
            item.setText(1, str(n) if n else "")


class SegmentRows(QWidget):
    """Paints a whole-file map plus one row per connection/segment."""

    ROW_H = 20
    MAP_H = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snap: DownloadSnapshot | None = None
        self.rows: list[SegmentView] = []
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_snapshot(self, snap: DownloadSnapshot | None) -> None:
        self.snap = snap
        self.rows = self._pick_rows(snap) if snap else []
        self.setFixedHeight(self.MAP_H + 14 + len(self.rows) * self.ROW_H)
        self.update()

    @staticmethod
    def _pick_rows(snap: DownloadSnapshot) -> list[SegmentView]:
        segs = sorted(snap.segments, key=lambda s: s.start)
        live = [s for s in segs if s.active or s.end is None or s.start + s.downloaded <= s.end]
        return live or segs

    def paintEvent(self, _e):
        if not self.snap:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        snap = self.snap
        w = self.width()
        # whole-file map: where every segment has written its bytes
        map_rect = QRectF(0, 0, w, self.MAP_H)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.TRACK))
        p.drawRoundedRect(map_rect, 3, 3)
        if snap.size:
            for s in snap.segments:
                x = w * s.start / snap.size
                dw = w * s.downloaded / snap.size
                if dw > 0:
                    color = theme.CYAN if s.active else (theme.BLUE if snap.status != Status.PAUSED else "#4B6491")
                    p.setBrush(QColor(color))
                    p.drawRect(QRectF(x, 1, max(dw, 1), self.MAP_H - 2))
        elif snap.status == Status.COMPLETED:
            p.setBrush(QColor(theme.BLUE))
            p.drawRoundedRect(map_rect, 3, 3)

        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        y = self.MAP_H + 14
        label_w, right_w = 34, 150
        for i, s in enumerate(self.rows):
            length = None if s.end is None else s.end - s.start + 1
            frac = None if not length else s.downloaded / length
            p.setPen(QColor(theme.CYAN if s.active else theme.MUTED))
            p.drawText(QRectF(0, y, label_w, self.ROW_H - 6), Qt.AlignLeft | Qt.AlignVCenter, f"#{i + 1}")
            status = snap.status if not (s.end is not None and s.start + s.downloaded > s.end) else Status.COMPLETED
            paint_bar(p, QRectF(label_w, y + 4, w - label_w - right_w - 10, 6), frac, status, 3)
            p.setPen(QColor(theme.MUTED))
            txt = f"{human_size(s.downloaded)} / {human_size(length)}"
            p.drawText(QRectF(w - right_w, y, right_w, self.ROW_H - 6), Qt.AlignRight | Qt.AlignVCenter, txt)
            y += self.ROW_H
        p.end()


class DetailPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detail")
        self.setMinimumHeight(170)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(28)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.title = QLabel("No download selected")
        self.title.setObjectName("detailTitle")
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        left.addWidget(self.title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)
        self.fields: dict[str, QLabel] = {}
        for r, key in enumerate(["Status", "Size", "Speed", "Connections", "Resume", "Saved to", "URL"]):
            k = QLabel(key)
            k.setProperty("muted", True)
            v = QLabel("-")
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.setMaximumWidth(420)
            grid.addWidget(k, r, 0, Qt.AlignTop)
            grid.addWidget(v, r, 1)
            self.fields[key] = v
        left.addLayout(grid)
        left.addStretch(1)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(470)
        outer.addWidget(lw)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.conn_label = QLabel("CONNECTIONS")
        self.conn_label.setObjectName("sectionLabel")
        right.addWidget(self.conn_label)
        self.rows = SegmentRows()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 6, 0)
        hl.addWidget(self.rows)
        hl.addStretch(1)
        scroll.setWidget(holder)
        right.addWidget(scroll, 1)
        outer.addLayout(right, 1)

    def show_snapshot(self, s: DownloadSnapshot | None) -> None:
        if s is None:
            self.title.setText("No download selected")
            for v in self.fields.values():
                v.setText("-")
            self.conn_label.setText("CONNECTIONS")
            self.rows.set_snapshot(None)
            return
        fm = self.title.fontMetrics()
        self.title.setText(fm.elidedText(s.filename or s.url, Qt.ElideMiddle, 450))
        status = STATUS_TEXT[s.status]
        if s.status == Status.ERROR and s.error:
            status += f" - {s.error}"
        self.fields["Status"].setText(status)
        pct = f" ({s.progress * 100:.1f}%)" if s.progress is not None and s.status != Status.COMPLETED else ""
        self.fields["Size"].setText(f"{human_size(s.downloaded)} of {human_size(s.size)}{pct}")
        self.fields["Speed"].setText(human_speed(s.speed) if s.status.is_running else "-")
        self.fields["Connections"].setText(
            f"{s.active_connections} active of {s.connections}" if s.status.is_running else f"{s.connections} max"
        )
        self.fields["Resume"].setText(
            "Supported (byte ranges)" if s.resumable else ("Not supported, single connection" if s.segments else "-")
        )
        saved = self.fields["Saved to"]
        saved.setText(saved.fontMetrics().elidedText(s.folder, Qt.ElideMiddle, 360))
        saved.setToolTip(s.folder)
        url = self.fields["URL"]
        url.setText(url.fontMetrics().elidedText(s.url, Qt.ElideMiddle, 360))
        url.setToolTip(s.url)
        n_active = s.active_connections
        self.conn_label.setText(f"CONNECTIONS  -  {n_active} ACTIVE" if s.status.is_running else "CONNECTIONS")
        self.rows.set_snapshot(s)
