"""Watches the clipboard for copied download links.

    watcher = ClipboardWatcher()
    watcher.linkCopied.connect(on_link)   # str: the URL
    watcher.enabled = True
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from ..linkcapture import download_link


class ClipboardWatcher(QObject):
    linkCopied = Signal(str)

    def __init__(self, parent: QObject | None = None, debounce_ms: int = 300, enabled: bool = True):
        super().__init__(parent)
        self.enabled = enabled
        self._last: str | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self._check)
        QGuiApplication.clipboard().dataChanged.connect(self._on_changed)

    def forget_last(self) -> None:
        """Let the same URL fire again (e.g. after the user dismissed it and copies it anew)."""
        self._last = None

    def _on_changed(self) -> None:
        if self.enabled:
            self._timer.start()  # restart: several dataChanged signals per copy fire once

    def _check(self) -> None:
        if not self.enabled:
            return
        clip = QGuiApplication.clipboard()
        mime = clip.mimeData()
        text = clip.text() if mime is not None and mime.hasText() else ""
        url = download_link(text)
        if url is None:
            self._last = None  # copying something else resets the "same URL twice" guard
            return
        if url == self._last:
            return
        self._last = url
        self.linkCopied.emit(url)
