"""Header bar, sidebar and the compact detail strip with one block per connection."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QStyledItemDelegate, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ..engine import DownloadSnapshot, SegmentView, Status
from ..util import human_size
from . import theme
from .icons import glyph_pixmap, nav_icon
from .model import CATEGORIES, STATUS_FILTERS, matches, paint_bar

SEPARATOR = "·"
MAX_BLOCKS = 16
DividerRole = Qt.UserRole + 2


class ElidedLabel(QLabel):
    """A label that elides its text in the middle instead of forcing the layout wider."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self._apply()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt override
        self._full = text
        self._apply()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply()

    def _apply(self) -> None:
        w = max(0, self.width() - 2)
        super().setText(self.fontMetrics().elidedText(self._full, Qt.ElideMiddle, w) if w else self._full)


class HeaderBar(QFrame):
    """App mark and title on the left, total speed of all active downloads on the right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("header")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 16, 8)
        lay.setSpacing(8)
        mark = QLabel()
        mark.setPixmap(glyph_pixmap("bolt", theme.CYAN, 20))
        lay.addWidget(mark)
        title = QLabel("Fetchly")
        title.setObjectName("appTitle")
        lay.addWidget(title)
        lay.addStretch(1)
        self.arrow = QLabel()
        self.arrow.setPixmap(glyph_pixmap("arrow_down", theme.MUTED, 14))
        lay.addWidget(self.arrow)
        self.speed = QLabel("-")
        self.speed.setObjectName("totalSpeed")
        lay.addWidget(self.speed)
        self.set_speed(None)

    def set_speed(self, text: str | None) -> None:
        self.arrow.setVisible(bool(text))
        self.speed.setText(text or "-")


class SidebarDelegate(QStyledItemDelegate):
    """Draws the divider and small CATEGORIES label; everything else is stock."""

    def paint(self, p: QPainter, option, index):
        if not index.data(DividerRole):
            return super().paint(p, option, index)
        r = QRectF(option.rect)
        p.save()
        p.setPen(QPen(QColor(theme.BORDER), 1))
        left = r.left() + (4 if index.column() == 0 else 0)
        right = r.right() - (4 if index.column() == 1 else 0)
        p.drawLine(int(left), int(r.top() + 8), int(right), int(r.top() + 8))
        if index.column() == 0:
            f = QFont(option.font)
            f.setPointSizeF(8)
            f.setWeight(QFont.DemiBold)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
            p.setFont(f)
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(r.left() + 8, r.top() + 12, r.width() - 8, r.height() - 12),
                       Qt.AlignLeft | Qt.AlignVCenter, "CATEGORIES")
        p.restore()

    def sizeHint(self, option, index):
        if index.data(DividerRole):
            return QSize(0, 34)
        return super().sizeHint(option, index)


class Sidebar(QTreeWidget):
    filterChanged = Signal(str)

    GLYPHS = {
        "All": "list", "Active": "download", "Queued": "clock", "Finished": "check",
        "Video": "film", "Archives": "archive", "Programs": "window", "Documents": "filetext",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setHeaderHidden(True)
        self.setColumnCount(2)
        self.setRootIsDecorated(False)
        self.setIndentation(0)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedWidth(150)
        self.setIconSize(QSize(16, 16))
        self.setItemDelegate(SidebarDelegate(self))
        self._items: dict[str, QTreeWidgetItem] = {}
        for key in STATUS_FILTERS:
            self._add(key)
        divider = QTreeWidgetItem(self, ["", ""])
        divider.setFlags(Qt.NoItemFlags)
        divider.setData(0, DividerRole, True)
        divider.setData(1, DividerRole, True)
        for key in CATEGORIES:
            self._add(key)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hdr = self.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, hdr.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, hdr.ResizeMode.Fixed)
        self.setColumnWidth(1, 26)
        self.setCurrentItem(self._items["All"])
        self.currentItemChanged.connect(self._changed)

    def _add(self, key: str) -> None:
        item = QTreeWidgetItem(self, [key, ""])
        item.setData(0, Qt.UserRole, key)
        item.setIcon(0, nav_icon(self.GLYPHS[key], theme.MUTED, theme.CYAN))
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


def block_fractions(snap: DownloadSnapshot, limit: int = MAX_BLOCKS) -> list[float | None]:
    """Progress (0..1) of each segment, in byte order. Beyond `limit` segments, neighbours are merged."""
    segs: list[SegmentView] = sorted(snap.segments, key=lambda s: s.start)
    if not segs:
        return []
    if len(segs) > limit:
        groups = [segs[i * len(segs) // limit:(i + 1) * len(segs) // limit] for i in range(limit)]
    else:
        groups = [[s] for s in segs]
    out: list[float | None] = []
    for g in groups:
        if any(s.end is None for s in g):
            out.append(None)
            continue
        total = sum(s.end - s.start + 1 for s in g)
        got = sum(min(s.downloaded, s.end - s.start + 1) for s in g)
        out.append(got / total if total else None)
    return out


class SegmentBlocks(QWidget):
    """Equal blocks side by side, one per connection, each filling left to right."""

    BLOCK_H = 22
    GAP = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snap: DownloadSnapshot | None = None
        self.fractions: list[float | None] = []
        self.setFixedHeight(self.BLOCK_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_snapshot(self, snap: DownloadSnapshot | None) -> None:
        self.snap = snap
        self.fractions = block_fractions(snap) if snap else []
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.fractions)
        status = self.snap.status if self.snap else Status.QUEUED
        if n == 0:
            # nothing fetched yet: show an empty track so the strip keeps its shape
            paint_bar(p, QRectF(0, 0, self.width(), self.BLOCK_H),
                      1.0 if status == Status.COMPLETED else None, status, 4, "#162A4D")
            p.end()
            return
        bw = (self.width() - self.GAP * (n - 1)) / n
        for i, frac in enumerate(self.fractions):
            if status == Status.COMPLETED:
                frac = 1.0
            elif frac is None and self.snap and self.snap.progress is not None:
                frac = self.snap.progress
            paint_bar(p, QRectF(i * (bw + self.GAP), 0, bw, self.BLOCK_H), frac, status, 4, "#162A4D")
        p.end()


class DetailPanel(QFrame):
    """One compact strip: title, connection summary and percent, the blocks, a caption."""

    CAPTION = "Each block is one thread fetching its own byte range"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detail")
        self.setFixedHeight(138)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 10)
        lay.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.title = ElidedLabel("No download selected")
        self.title.setObjectName("detailTitle")
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top.addWidget(self.title, 1)
        self.summary = QLabel("")
        self.summary.setProperty("muted", True)
        top.addWidget(self.summary)
        self.percent = QLabel("")
        self.percent.setObjectName("detailPercent")
        self.percent.setMinimumWidth(40)
        self.percent.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.percent)
        lay.addLayout(top)

        lay.addSpacing(8)
        self.blocks = SegmentBlocks()
        lay.addWidget(self.blocks)
        lay.addSpacing(6)

        self.caption = QLabel(self.CAPTION)
        self.caption.setObjectName("caption")
        lay.addWidget(self.caption)
        lay.addStretch(1)

        self.meta = ElidedLabel("")
        self.meta.setObjectName("caption")
        self.meta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.meta)

    def show_snapshot(self, s: DownloadSnapshot | None) -> None:
        if s is None:
            self.title.setText("No download selected")
            self.title.setToolTip("")
            self.summary.setText("")
            self.percent.setText("")
            self.meta.setText("")
            self.meta.setToolTip("")
            self.blocks.set_snapshot(None)
            return
        self.title.setText(s.filename or s.url)
        self.title.setToolTip(s.url)
        n = s.connections
        resume = "resume supported" if s.resumable else "no resume"
        if s.status.is_running:
            conns = f"{s.active_connections} of {n} connections"
        else:
            conns = f"{n} connection" + ("" if n == 1 else "s")
        self.summary.setText(f"{conns} {SEPARATOR} {resume}")
        if s.status == Status.COMPLETED:
            pct = "100%"
        else:
            pct = f"{s.progress * 100:.0f}%" if s.progress is not None else "-"
        self.percent.setText(pct)
        self.blocks.set_snapshot(s)

        if s.status == Status.ERROR and s.error:
            self.meta.setText(f"Error: {s.error}")
            self.meta.setStyleSheet(f"color: {theme.RED};")
        else:
            self.meta.setText(f"Saved to {s.folder}")
            self.meta.setStyleSheet("")
        got = f"{human_size(s.downloaded)} of {human_size(s.size)}"
        self.meta.setToolTip(f"{got}\n{s.folder}\n{s.url}")
