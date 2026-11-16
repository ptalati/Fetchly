"""Small line icons drawn with QPainter, so the toolbar needs no image files."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

RESOURCES = Path(__file__).parent / "resources"


def app_icon() -> QIcon:
    return QIcon(str(RESOURCES / "fetchly.ico"))


def _icon(draw, color: str = "#E8EEF8", disabled: str = "#4E628A", size: int = 20) -> QIcon:
    icon = QIcon()
    for mode, c in ((QIcon.Normal, color), (QIcon.Disabled, disabled)):
        for scale in (1, 2):
            pm = QPixmap(size * scale, size * scale)
            pm.setDevicePixelRatio(scale)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor(c), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            draw(p, size, QColor(c))
            p.end()
            icon.addPixmap(pm, mode)
    return icon


def add_icon(color="#FFFFFF") -> QIcon:
    def d(p, s, c):
        p.drawLine(QPointF(s / 2, 4), QPointF(s / 2, s - 4))
        p.drawLine(QPointF(4, s / 2), QPointF(s - 4, s / 2))
    return _icon(d, color)


def resume_icon() -> QIcon:
    def d(p, s, c):
        path = QPainterPath()
        path.moveTo(6, 4)
        path.lineTo(s - 4, s / 2)
        path.lineTo(6, s - 4)
        path.closeSubpath()
        p.drawPath(path)
    return _icon(d)


def pause_icon() -> QIcon:
    def d(p, s, c):
        p.drawLine(QPointF(7, 4.5), QPointF(7, s - 4.5))
        p.drawLine(QPointF(s - 7, 4.5), QPointF(s - 7, s - 4.5))
    return _icon(d)


def remove_icon() -> QIcon:
    def d(p, s, c):
        p.drawLine(QPointF(4, 6), QPointF(s - 4, 6))
        p.drawLine(QPointF(8, 6), QPointF(8.5, 3.5))
        p.drawLine(QPointF(8.5, 3.5), QPointF(s - 8.5, 3.5))
        p.drawLine(QPointF(s - 8.5, 3.5), QPointF(s - 8, 6))
        path = QPainterPath()
        path.moveTo(5.5, 6)
        path.lineTo(6.5, s - 3)
        path.lineTo(s - 6.5, s - 3)
        path.lineTo(s - 5.5, 6)
        p.drawPath(path)
    return _icon(d)


def settings_icon() -> QIcon:
    def d(p, s, c):
        for y, x in ((5, 12), (10, 7), (15, 11)):
            p.drawLine(QPointF(3, y), QPointF(s - 3, y))
            p.setBrush(QColor("#0E1B33"))
            p.drawEllipse(QPointF(x, y), 2.2, 2.2)
            p.setBrush(Qt.NoBrush)
    return _icon(d)


def dot_icon(color: str, size: int = 12) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), 2.5, 2.5)
    p.end()
    return QIcon(pm)
