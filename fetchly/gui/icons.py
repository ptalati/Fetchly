"""Line icons drawn with QPainter (24x24 grid, Tabler-style), so no image files are needed."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from . import theme

RESOURCES = Path(__file__).parent / "resources"


def app_icon() -> QIcon:
    return QIcon(str(RESOURCES / "fetchly.ico"))


def _poly(p: QPainter, *pts: tuple[float, float]) -> None:
    for a, b in zip(pts, pts[1:]):
        p.drawLine(QPointF(*a), QPointF(*b))


def _file_outline(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(7, 3)
    path.lineTo(14, 3)
    path.lineTo(19, 8)
    path.lineTo(19, 19)
    path.quadTo(19, 21, 17, 21)
    path.lineTo(7, 21)
    path.quadTo(5, 21, 5, 19)
    path.lineTo(5, 5)
    path.quadTo(5, 3, 7, 3)
    p.drawPath(path)
    _poly(p, (14, 3), (14, 8), (19, 8))


def _list(p):
    for y in (6, 12, 18):
        p.drawLine(QPointF(9, y), QPointF(20, y))
        p.drawPoint(QPointF(4.5, y))


def _download(p):
    _poly(p, (12, 4), (12, 15))
    _poly(p, (7, 10.5), (12, 15.5), (17, 10.5))
    _poly(p, (5, 20), (19, 20))


def _clock(p):
    p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
    _poly(p, (12, 7), (12, 12), (15, 14))


def _check(p):
    _poly(p, (5, 12.5), (10, 17.5), (19, 7))


def _film(p):
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 2.5, 2.5)
    p.drawLine(QPointF(8.5, 4), QPointF(8.5, 20))
    p.drawLine(QPointF(15.5, 4), QPointF(15.5, 20))
    for y in (8.5, 12, 15.5):
        p.drawLine(QPointF(4, y), QPointF(8.5, y))
        p.drawLine(QPointF(15.5, y), QPointF(20, y))


def _archive(p):
    _file_outline(p)
    for y in (10, 13.5, 17):
        p.drawLine(QPointF(11, y), QPointF(11, y + 1.2))
        p.drawLine(QPointF(13, y + 1.2), QPointF(13, y + 2.4))


def _window(p):
    p.drawRoundedRect(QRectF(3.5, 5, 17, 14), 2.5, 2.5)
    _poly(p, (3.5, 9.5), (20.5, 9.5))
    p.drawPoint(QPointF(6.8, 7.3))
    p.drawPoint(QPointF(9.3, 7.3))


def _filetext(p):
    _file_outline(p)
    _poly(p, (9, 13), (15, 13))
    _poly(p, (9, 17), (15, 17))


def _file(p):
    _file_outline(p)


def _plus(p):
    _poly(p, (12, 5), (12, 19))
    _poly(p, (5, 12), (19, 12))


def _play(p):
    path = QPainterPath()
    path.moveTo(7, 5)
    path.lineTo(19, 12)
    path.lineTo(7, 19)
    path.closeSubpath()
    p.drawPath(path)


def _pause(p):
    p.drawRoundedRect(QRectF(6.5, 5, 3.5, 14), 1, 1)
    p.drawRoundedRect(QRectF(14, 5, 3.5, 14), 1, 1)


def _trash(p):
    _poly(p, (4, 7), (20, 7))
    _poly(p, (10, 11), (10, 17))
    _poly(p, (14, 11), (14, 17))
    path = QPainterPath()
    path.moveTo(5.5, 7)
    path.lineTo(6.5, 19)
    path.quadTo(6.6, 21, 8.5, 21)
    path.lineTo(15.5, 21)
    path.quadTo(17.4, 21, 17.5, 19)
    path.lineTo(18.5, 7)
    p.drawPath(path)
    _poly(p, (9, 7), (9, 4), (15, 4), (15, 7))


def _settings(p):
    for y, x in ((6, 15), (12, 9), (18, 14)):
        p.drawLine(QPointF(4, y), QPointF(x - 3, y))
        p.drawLine(QPointF(x + 3, y), QPointF(20, y))
        p.drawEllipse(QPointF(x, y), 2.4, 2.4)


def _arrow_down(p):
    _poly(p, (12, 5), (12, 19))
    _poly(p, (6.5, 13.5), (12, 19), (17.5, 13.5))


def _bolt(p):
    path = QPainterPath()
    path.moveTo(13.5, 2.5)
    path.lineTo(5, 13.5)
    path.lineTo(11, 13.5)
    path.lineTo(10, 21.5)
    path.lineTo(19, 10)
    path.lineTo(13, 10)
    path.closeSubpath()
    p.setBrush(p.pen().color())
    p.drawPath(path)


GLYPHS = {
    "list": _list, "download": _download, "clock": _clock, "check": _check, "film": _film,
    "archive": _archive, "window": _window, "filetext": _filetext, "file": _file, "plus": _plus,
    "play": _play, "pause": _pause, "trash": _trash, "settings": _settings,
    "arrow_down": _arrow_down, "bolt": _bolt,
}


def paint_glyph(p: QPainter, key: str, rect: QRectF, color: str | QColor, width: float = 2.0) -> None:
    """Draw glyph `key` into `rect` with the painter's current transform."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(rect.topLeft())
    p.scale(rect.width() / 24, rect.height() / 24)
    p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    GLYPHS[key](p)
    p.restore()


def glyph_pixmap(key: str, color: str | QColor, size: int, scale: int = 2) -> QPixmap:
    pm = QPixmap(size * scale, size * scale)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_glyph(p, key, QRectF(0, 0, size, size), color)
    p.end()
    return pm


def glyph_icon(key: str, color: str, disabled: str, size: int = 20) -> QIcon:
    icon = QIcon()
    for mode, c in ((QIcon.Normal, color), (QIcon.Disabled, disabled)):
        for scale in (1, 2):
            icon.addPixmap(glyph_pixmap(key, c, size, scale), mode)
    return icon


def _themed(key: str) -> QIcon:
    p = theme.active()
    return glyph_icon(key, p.text, p.disabled)


def add_icon() -> QIcon:
    return _themed("plus")


def resume_icon() -> QIcon:
    return _themed("play")


def pause_icon() -> QIcon:
    return _themed("pause")


def remove_icon() -> QIcon:
    return _themed("trash")


def settings_icon() -> QIcon:
    return _themed("settings")
