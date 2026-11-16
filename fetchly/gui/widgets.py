"""Header bar, sidebar and the compact detail strip with one block per connection."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QSizePolicy, QStyle, QStyledItemDelegate,
    QVBoxLayout, QWidget,
)

from ..engine import DownloadSnapshot, SegmentView, Status
from ..util import human_size
from . import theme
from .icons import glyph_pixmap, paint_glyph
from .model import CATEGORIES, STATUS_FILTERS, matches, paint_bar

SEPARATOR = "·"
MAX_BLOCKS = 16
DividerRole = Qt.UserRole + 2
CountRole = Qt.UserRole + 3
GlyphRole = Qt.UserRole + 4
COUNTED = ("Active", "Queued")


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
        self.mark = QLabel()
        lay.addWidget(self.mark)
        title = QLabel("Fetchly")
        title.setObjectName("appTitle")
        lay.addWidget(title)
        lay.addStretch(1)
        self.arrow = QLabel()
        lay.addWidget(self.arrow)
        self.speed = QLabel("-")
        self.speed.setObjectName("totalSpeed")
        lay.addWidget(self.speed)
        self.set_speed(None)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        p = theme.active()
        self.mark.setPixmap(glyph_pixmap("bolt", p.highlight, 20))
        self.arrow.setPixmap(glyph_pixmap("arrow_down", p.muted, 14))

    def set_speed(self, text: str | None) -> None:
        self.arrow.setVisible(bool(text))
        self.speed.setText(text or "-")


class SidebarDelegate(QStyledItemDelegate):
    """One painter for the whole row: rounded selection pill, line icon, label and right-aligned count."""

    ICON = 16

    def paint(self, p: QPainter, option, index):
        pal = theme.active()
        r = QRectF(option.rect)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if index.data(DividerRole):
            p.setPen(QPen(QColor(pal.border), 1))
            y = int(r.center().y())
            p.drawLine(int(r.left()) + 4, y, int(r.right()) - 4, y)
            p.restore()
            return
        selected = bool(option.state & QStyle.State_Selected)
        pill = r.adjusted(0, 1, 0, -1)
        if selected or option.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal.pill if selected else pal.hover))
            p.drawRoundedRect(pill, 8, 8)
        icon_rect = QRectF(pill.left() + 10, pill.center().y() - self.ICON / 2, self.ICON, self.ICON)
        paint_glyph(p, index.data(GlyphRole), icon_rect, pal.nav_active if selected else pal.muted, 1.8)
        count = index.data(CountRole)
        right = pill.right() - 10
        if count:
            f = QFont(option.font)
            f.setPointSizeF(9)
            p.setFont(f)
            p.setPen(QColor(pal.muted))
            p.drawText(QRectF(pill.left(), pill.top(), right - pill.left(), pill.height()),
                       Qt.AlignRight | Qt.AlignVCenter, str(count))
        p.setFont(option.font)
        p.setPen(QColor(pal.text if selected else pal.muted))
        tx = icon_rect.right() + 8
        p.drawText(QRectF(tx, pill.top(), right - tx, pill.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   index.data(Qt.DisplayRole))
        p.restore()

    def sizeHint(self, option, index):
        return QSize(0, 17 if index.data(DividerRole) else 32)


class Sidebar(QListWidget):
    filterChanged = Signal(str)

    GLYPHS = {
        "All": "list", "Active": "download", "Queued": "clock", "Finished": "check",
        "Video": "film", "Archives": "archive", "Programs": "window", "Documents": "filetext",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setFixedWidth(150)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setItemDelegate(SidebarDelegate(self))
        self._items: dict[str, QListWidgetItem] = {}
        for key in STATUS_FILTERS:
            self._add(key)
        divider = QListWidgetItem(self)
        divider.setFlags(Qt.NoItemFlags)
        divider.setData(DividerRole, True)
        for key in CATEGORIES:
            self._add(key)
        self.setCurrentItem(self._items["All"])
        self.currentItemChanged.connect(self._changed)

    def _add(self, key: str) -> None:
        item = QListWidgetItem(key, self)
        item.setData(Qt.UserRole, key)
        item.setData(GlyphRole, self.GLYPHS[key])
        self._items[key] = item

    def _changed(self, cur, _prev):
        if cur is not None and cur.data(Qt.UserRole):
            self.filterChanged.emit(cur.data(Qt.UserRole))

    def update_counts(self, snaps: list[DownloadSnapshot]) -> None:
        """Counts show on Active and Queued only, and only when there is something in them."""
        for key in COUNTED:
            self._items[key].setData(CountRole, sum(1 for s in snaps if matches(s, key)) or None)


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
                      1.0 if status == Status.COMPLETED else None, status, 4, theme.active().block_track)
            p.end()
            return
        bw = (self.width() - self.GAP * (n - 1)) / n
        for i, frac in enumerate(self.fractions):
            if status == Status.COMPLETED:
                frac = 1.0
            elif frac is None and self.snap and self.snap.progress is not None:
                frac = self.snap.progress
            paint_bar(p, QRectF(i * (bw + self.GAP), 0, bw, self.BLOCK_H), frac, status, 4, theme.active().block_track)
        p.end()


class DetailPanel(QFrame):
    """One compact strip: title and connection summary, the blocks, then caption and percent."""

    CAPTION = "Each block is one thread fetching its own byte range"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detail")
        self.setFixedHeight(108)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
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
        lay.addLayout(top)

        lay.addSpacing(10)
        self.blocks = SegmentBlocks()
        lay.addWidget(self.blocks)
        lay.addSpacing(8)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        self.caption = ElidedLabel(self.CAPTION)
        self.caption.setObjectName("caption")
        self.caption.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bottom.addWidget(self.caption, 1)
        self.percent = QLabel("")
        self.percent.setObjectName("detailPercent")
        self.percent.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom.addWidget(self.percent)
        lay.addLayout(bottom)
        lay.addStretch(1)

    def show_snapshot(self, s: DownloadSnapshot | None) -> None:
        if s is None:
            self.title.setText("No download selected")
            self.title.setToolTip("")
            self.summary.setText("")
            self.percent.setText("")
            self._set_caption(self.CAPTION, False)
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
            self._set_caption(f"Error: {s.error}", True)
        else:
            self._set_caption(self.CAPTION, False)

    def _set_caption(self, text: str, error: bool) -> None:
        self.caption.setText(text)
        self.caption.setStyleSheet(f"color: {theme.active().red};" if error else "")
        self.caption.setToolTip(text if error else "")
