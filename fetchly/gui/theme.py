"""Dark navy / blue / cyan theme, matching the icon palette."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

NAVY = "#0E1B33"
SIDEBAR = "#0A1528"
SURFACE = "#132443"
SURFACE_HI = "#1A2F55"
BORDER = "#22396A"
TEXT = "#E8EEF8"
MUTED = "#8EA3C6"
BLUE = "#3B82F6"
CYAN = "#67E8F9"
RED = "#F87171"
AMBER = "#FBBF24"
TRACK = "#0A1426"

QSS = f"""
* {{ font-family: "Segoe UI", sans-serif; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {NAVY}; }}
QToolBar {{ background: {NAVY}; border: none; border-bottom: 1px solid {BORDER}; padding: 6px 10px; spacing: 6px; }}
QToolBar QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px;
    padding: 5px 10px; color: {TEXT}; }}
QToolBar QToolButton:hover {{ background: {SURFACE_HI}; border-color: {BORDER}; }}
QToolBar QToolButton:pressed {{ background: {BORDER}; }}
QToolBar QToolButton:disabled {{ color: #4E628A; }}
QToolBar QToolButton#primary {{ background: {BLUE}; color: white; font-weight: 600; }}
QToolBar QToolButton#primary:hover {{ background: #5B95F8; }}

QTreeWidget#sidebar {{ background: {SIDEBAR}; border: none; border-right: 1px solid {BORDER}; padding: 8px 6px; outline: 0; }}
QTreeWidget#sidebar::item {{ height: 30px; padding-left: 6px; }}
QTreeWidget#sidebar::item:last {{ padding-right: 10px; }}
QTreeWidget#sidebar::item:hover {{ background: {SURFACE}; }}
QTreeWidget#sidebar::item:selected {{ background: {SURFACE_HI}; color: {CYAN}; }}
QTreeWidget#sidebar {{ show-decoration-selected: 1; }}

QTableView {{ background: {NAVY}; alternate-background-color: #10203C; border: none; gridline-color: transparent;
    selection-background-color: {SURFACE_HI}; selection-color: {TEXT}; outline: 0; }}
QTableView::item {{ padding: 0 8px; border: none; }}
QTableView::item:selected {{ background: {SURFACE_HI}; }}
QHeaderView::section {{ background: {NAVY}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px 8px; font-size: 9pt; font-weight: 600; }}

QFrame#detail {{ background: {SIDEBAR}; border-top: 1px solid {BORDER}; }}
QLabel#detailTitle {{ font-size: 12pt; font-weight: 600; }}
QLabel.muted, QLabel[muted="true"] {{ color: {MUTED}; }}
QLabel#sectionLabel {{ color: {MUTED}; font-size: 8.5pt; font-weight: 600; letter-spacing: 1px; }}

QLineEdit, QSpinBox {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 8px;
    selection-background-color: {BLUE}; }}
QLineEdit:focus, QSpinBox:focus {{ border-color: {BLUE}; }}
QPushButton {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ background: {SURFACE_HI}; }}
QPushButton:default, QPushButton#primary {{ background: {BLUE}; border-color: {BLUE}; color: white; font-weight: 600; }}
QPushButton:default:hover, QPushButton#primary:hover {{ background: #5B95F8; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {BORDER}; border-radius: 3px; background: {SURFACE}; }}
QCheckBox::indicator:checked {{ background: {BLUE}; border-color: {BLUE}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 24px; }}
QSplitter::handle {{ background: {BORDER}; }}
QStatusBar {{ background: {SIDEBAR}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ color: {MUTED}; padding: 0 8px; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {SURFACE_HI}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QMessageBox QLabel {{ color: {TEXT}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in (
        (QPalette.Window, NAVY), (QPalette.WindowText, TEXT), (QPalette.Base, SURFACE),
        (QPalette.AlternateBase, "#10203C"), (QPalette.Text, TEXT), (QPalette.Button, SURFACE),
        (QPalette.ButtonText, TEXT), (QPalette.Highlight, BLUE), (QPalette.HighlightedText, "#FFFFFF"),
        (QPalette.ToolTipBase, SURFACE), (QPalette.ToolTipText, TEXT), (QPalette.PlaceholderText, MUTED),
    ):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
