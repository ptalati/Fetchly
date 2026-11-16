"""One running Fetchly per user, reachable over a local socket (QtNetwork only, no widgets).

The running app owns an ``InstanceServer``. Anything else - a second launch, the browser
native-messaging host - uses ``send_to_running()`` to hand it a message.

Wire format: one JSON object per line (UTF-8, newline-terminated), e.g.
    {"cmd": "show"}
    {"cmd": "ping"}              (reply only; used to see whether the app is running)
    {"cmd": "add", "url": "...", "referrer": "...", "filename": "...", "headers": {...}}
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

MAX_MESSAGE_BYTES = 1024 * 1024  # a request with a big Cookie header is still far below this


def server_name(home: str | Path | None = None) -> str:
    """Socket name, unique per user (hash of the home folder). FETCHLY_INSTANCE_NAME overrides it (tests)."""
    override = os.environ.get("FETCHLY_INSTANCE_NAME")
    if override:
        return override
    home = str(home if home is not None else Path.home())
    return "fetchly-" + hashlib.sha1(home.lower().encode("utf-8")).hexdigest()[:16]


class InstanceServer(QObject):
    """Listens for messages from other processes and turns them into signals."""

    showRequested = Signal()
    addRequested = Signal(dict)

    def __init__(self, name: str | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.name = name or server_name()
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.UserAccessOption)
        self._server.newConnection.connect(self._on_connection)
        self._buffers: dict[QLocalSocket, bytearray] = {}

    def listen(self) -> bool:
        """Start listening. Returns False if another live instance already owns the name."""
        if self._server.listen(self.name):
            return True
        # A crashed instance leaves a stale name behind; clear it and retry once.
        # (If a live instance owns the name, send_to_running() reaches it, so callers check that first.)
        QLocalServer.removeServer(self.name)
        return self._server.listen(self.name)

    def close(self) -> None:
        self._server.close()

    def is_listening(self) -> bool:
        return self._server.isListening()

    # internals -----------------------------------------------------------

    def _on_connection(self) -> None:
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            self._buffers[sock] = bytearray()
            sock.readyRead.connect(lambda s=sock: self._on_ready(s))
            sock.disconnected.connect(lambda s=sock: self._on_disconnected(s))
            if sock.bytesAvailable():
                self._on_ready(sock)

    def _on_ready(self, sock: QLocalSocket) -> None:
        buf = self._buffers.get(sock)
        if buf is None:
            return
        buf += bytes(sock.readAll())
        while True:
            nl = buf.find(b"\n")
            if nl < 0:
                break
            line = bytes(buf[:nl])
            del buf[: nl + 1]
            self._dispatch(sock, line)
        if len(buf) > MAX_MESSAGE_BYTES:
            sock.abort()

    def _on_disconnected(self, sock: QLocalSocket) -> None:
        # A sender that closes right after writing may leave a final line without "\n".
        buf = self._buffers.pop(sock, None)
        if buf and buf.strip():
            self._dispatch(None, bytes(buf))
        sock.deleteLater()

    def _dispatch(self, sock: QLocalSocket | None, line: bytes) -> None:
        if not line.strip():
            return
        try:
            msg = json.loads(line.decode("utf-8"))
        except ValueError:
            self._reply(sock, {"ok": False, "error": "invalid JSON"})
            return
        if not isinstance(msg, dict):
            self._reply(sock, {"ok": False, "error": "message must be an object"})
            return
        cmd = msg.get("cmd")
        if cmd == "add":
            url = msg.get("url")
            if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
                self._reply(sock, {"ok": False, "error": "missing or unsupported url"})
                return
        elif cmd not in ("ping", "show"):
            self._reply(sock, {"ok": False, "error": f"unknown cmd {cmd!r}"})
            return
        # Acknowledge before signalling: a slot may open a modal dialog, and a sender that waits
        # longer than its timeout would assume Fetchly is not running and send the link again.
        self._reply(sock, {"ok": True})
        if cmd == "show":
            self.showRequested.emit()
        elif cmd == "add":
            self.addRequested.emit(msg)

    @staticmethod
    def _reply(sock: QLocalSocket | None, obj: dict) -> None:
        if sock is not None and sock.state() == QLocalSocket.ConnectedState:
            sock.write(json.dumps(obj).encode("utf-8") + b"\n")
            sock.flush()


def send_to_running(msg: dict, timeout_ms: int = 1500, name: str | None = None) -> bool:
    """Deliver ``msg`` to the running instance. True once it has acknowledged the message.

    Needs a QCoreApplication (or QApplication) to exist only for the event loop of the
    receiver; this function itself blocks on the socket and works without one.
    """
    sock = QLocalSocket()
    sock.connectToServer(name or server_name())
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(json.dumps(msg).encode("utf-8") + b"\n")
    if not sock.waitForBytesWritten(timeout_ms):
        sock.abort()
        return False
    ok = False
    if sock.waitForReadyRead(timeout_ms):
        try:
            ok = bool(json.loads(bytes(sock.readAll()).split(b"\n", 1)[0].decode("utf-8")).get("ok"))
        except ValueError:
            ok = False
    sock.disconnectFromServer()
    return ok
