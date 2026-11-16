"""Light and dark themes. The active palette follows the system colour scheme."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

RES = (Path(__file__).parent / "resources").as_posix()


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str            # window and list background
    header: str        # header bar and toolbar
    sidebar: str
    detail: str        # detail strip
    surface: str       # inputs, menus
    surface_hi: str
    border: str        # panel dividers
    divider: str       # thin row dividers
    text: str
    muted: str
    disabled: str
    accent: str        # primary buttons, focus, selection
    accent_hi: str
    bar_start: str     # progress bar gradient (equal for a flat fill)
    bar_end: str
    highlight: str     # percent label, header bolt
    nav_active: str    # icon of the selected sidebar item
    red: str
    green: str
    amber: str
    track: str         # empty progress bar
    block_track: str   # empty segment block
    paused: str        # bar of a paused or queued download
    row_sel: str
    pill: str          # selected sidebar item
    hover: str         # sidebar hover
    btn_bg: str
    btn_border: str
    btn_hover: str
    btn_hover_border: str
    check_border: str
    chevron: str       # suffix of the chevron svg files
    categories: dict = field(default_factory=dict)


DARK = Palette(
    name="dark", bg="#0E1B33", header="#0E1B33", sidebar="#0A1528", detail="#0A1528",
    surface="#132443", surface_hi="#1A2F55", border="#22396A", divider="#162A4D",
    text="#E8EEF8", muted="#8EA3C6", disabled="#4E628A",
    accent="#3B82F6", accent_hi="#5B95F8", bar_start="#3B82F6", bar_end="#67E8F9", highlight="#67E8F9", nav_active="#67E8F9",
    red="#F87171", green="#34D399", amber="#FBBF24",
    track="#0A1426", block_track="#162A4D", paused="#4B6491",
    row_sel="#1A2F55", pill="#1A2F55", hover="#132443",
    btn_bg="#132443", btn_border="#22396A", btn_hover="#1A2F55", btn_hover_border="#34508A",
    check_border="#3A5590", chevron="",
    categories={"Video": "#A78BFA", "Archives": "#FBBF24", "Programs": "#34D399", "Documents": "#60A5FA"},
)

LIGHT = Palette(
    name="light", bg="#FFFFFF", header="#F7F7F8", sidebar="#FFFFFF", detail="#FFFFFF",
    surface="#FFFFFF", surface_hi="#F1F1F4", border="#E3E3E6", divider="#EDEDF0",
    text="#1F1F22", muted="#6B6B73", disabled="#B4B4BC",
    accent="#2F6FDB", accent_hi="#4A84E8", bar_start="#2F6FDB", bar_end="#2F6FDB", highlight="#2F6FDB", nav_active="#1F1F22",
    red="#C62828", green="#1A8F2E", amber="#B7791F",
    track="#EFEFF2", block_track="#EFEFF2", paused="#B4B4BC",
    row_sel="#E8F0FC", pill="#E9E9EC", hover="#F3F3F5",
    btn_bg="#FFFFFF", btn_border="#D4D4D8", btn_hover="#F1F1F4", btn_hover_border="#C4C4CA",
    check_border="#B4B4BC", chevron="-light",
    categories={"Video": "#7C3AED", "Archives": "#B7791F", "Programs": "#1A8F2E", "Documents": "#2F6FDB"},
)

_active: Palette = DARK
_listeners: list[Callable[[Palette], None]] = []


def active() -> Palette:
    """The palette currently applied; paint code reads colours from here at paint time."""
    return _active


def on_change(callback: Callable[[Palette], None]) -> None:
    """Call `callback(palette)` after a new palette has been applied."""
    _listeners.append(callback)


def build_qss(p: Palette) -> str:
    return f"""
* {{ font-family: "Segoe UI", sans-serif; font-size: 10pt; color: {p.text}; }}
QMainWindow, QDialog {{ background: {p.bg}; }}
QFrame#header {{ background: {p.header}; border: none; border-bottom: 1px solid {p.border}; }}
QLabel#appTitle {{ font-weight: 600; font-size: 11pt; }}
QLabel#totalSpeed {{ color: {p.muted}; }}
QToolBar {{ background: {p.header}; border: none; border-bottom: 1px solid {p.border}; padding: 6px 10px; spacing: 6px; }}
QToolBar QToolButton {{ background: {p.btn_bg}; border: 1px solid {p.btn_border}; border-radius: 8px;
    padding: 5px 12px 5px 8px; color: {p.text}; }}
QToolBar QToolButton:hover {{ background: {p.btn_hover}; border-color: {p.btn_hover_border}; }}
QToolBar QToolButton:pressed {{ background: {p.border}; }}
QToolBar QToolButton:focus {{ border-color: {p.accent}; }}
QToolBar QToolButton:disabled {{ color: {p.disabled}; background: transparent; border-color: {p.divider}; }}
QToolBar QToolButton#iconOnly {{ padding: 5px 7px; }}

QListWidget#sidebar {{ background: {p.sidebar}; border: none; border-right: 1px solid {p.border}; padding: 8px 6px; outline: 0; }}

QTableView {{ background: {p.bg}; border: none; gridline-color: transparent;
    selection-background-color: {p.row_sel}; selection-color: {p.text}; outline: 0; }}
QTableView::item {{ padding: 0 4px; border: none; }}
QTableView::item:selected {{ background: {p.row_sel}; }}
QHeaderView::section {{ background: {p.bg}; color: {p.muted}; border: none; border-bottom: 1px solid {p.border};
    padding: 6px 4px; font-size: 9pt; }}

QFrame#detail {{ background: {p.detail}; border-top: 1px solid {p.border}; }}
QLabel#detailTitle {{ font-size: 10.5pt; font-weight: 600; }}
QLabel#detailPercent {{ color: {p.highlight}; font-weight: 600; }}
QLabel#caption {{ color: {p.muted}; font-size: 9pt; }}
QLabel.muted, QLabel[muted="true"] {{ color: {p.muted}; }}

QLineEdit, QSpinBox {{ background: {p.surface}; border: 1px solid {p.btn_border}; border-radius: 6px; padding: 6px 8px;
    selection-background-color: {p.accent}; selection-color: white; }}
QSpinBox {{ padding-right: 26px; }}
QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 22px; background: {p.surface_hi};
    border-left: 1px solid {p.btn_border}; }}
QSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 6px; border-bottom: 1px solid {p.btn_border}; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 6px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {p.border}; }}
QSpinBox::up-arrow {{ image: url("{RES}/chevron-up{p.chevron}.svg"); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url("{RES}/chevron-down{p.chevron}.svg"); width: 10px; height: 10px; }}
QSpinBox::up-arrow:disabled, QSpinBox::down-arrow:disabled {{ image: none; }}
QLineEdit:focus, QSpinBox:focus {{ border-color: {p.accent}; }}
QPushButton {{ background: {p.btn_bg}; border: 1px solid {p.btn_border}; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ background: {p.btn_hover}; }}
QPushButton#primary {{ background: {p.accent}; border-color: {p.accent}; color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: {p.accent_hi}; border-color: {p.accent_hi}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {p.check_border}; border-radius: 4px; background: {p.surface}; }}
QCheckBox::indicator:hover {{ border-color: {p.accent}; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; image: url("{RES}/check.svg"); }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.btn_border}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.btn_border}; border-radius: 4px; min-width: 24px; }}
QSplitter::handle {{ background: {p.border}; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.btn_border}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p.surface_hi}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 6px; }}
QToolTip {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.btn_border}; padding: 4px; }}
QMessageBox QLabel {{ color: {p.text}; }}
"""


def _qpalette(p: Palette) -> QPalette:
    pal = QPalette()
    for role, color in (
        (QPalette.Window, p.bg), (QPalette.WindowText, p.text), (QPalette.Base, p.surface),
        (QPalette.AlternateBase, p.surface_hi), (QPalette.Text, p.text), (QPalette.Button, p.btn_bg),
        (QPalette.ButtonText, p.text), (QPalette.Highlight, p.accent), (QPalette.HighlightedText, "#FFFFFF"),
        (QPalette.ToolTipBase, p.surface), (QPalette.ToolTipText, p.text), (QPalette.PlaceholderText, p.muted),
    ):
        pal.setColor(role, QColor(color))
    return pal


def apply_palette(app: QApplication, p: Palette) -> None:
    """Make `p` the active palette, restyle the application and notify listeners."""
    global _active
    _active = p
    app.setStyle("Fusion")
    app.setPalette(_qpalette(p))
    app.setStyleSheet(build_qss(p))
    for callback in list(_listeners):
        callback(p)


def system_palette() -> Palette:
    """Dark when the system is set to dark; light for Light or Unknown."""
    scheme = QGuiApplication.styleHints().colorScheme()
    return DARK if scheme == Qt.ColorScheme.Dark else LIGHT


def apply_theme(app: QApplication) -> None:
    """Apply the system scheme now and again whenever it changes."""
    apply_palette(app, system_palette())
    app.styleHints().colorSchemeChanged.connect(lambda _scheme: apply_palette(app, system_palette()))
