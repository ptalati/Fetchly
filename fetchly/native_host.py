"""Native messaging host: the link between the browser extension and the running Fetchly app.

Chrome and Firefox start this program and talk to it over stdin/stdout, each message being a
4-byte little-endian length followed by UTF-8 JSON. Run from source with
``python -m fetchly.native_host``; frozen builds ship it as ``fetchly-host``.

    {"type": "download", "url", "referrer", "filename", "headers"}  ->  {"ok": true} | {"ok": false, "error": ...}
    {"type": "ping"}                                                ->  {"ok": true, "version": ..., "running": bool}

Downloads are forwarded to the app over its local socket. If the app is not running it is
started (to the tray) and the host retries for about 10 seconds.

Imports are kept light on purpose: QtCore and QtNetwork only, no widgets.
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import BinaryIO, Callable

from . import __version__

MAX_MESSAGE_BYTES = 8 * 1024 * 1024  # browsers send at most 64 MiB; a download request is a few KB
LAUNCH_WAIT_SECONDS = 10.0
RETRY_INTERVAL = 0.3


# framing -----------------------------------------------------------------------


def read_message(stream: BinaryIO) -> dict | None:
    """Read one framed message. None at end of input; ValueError on a bad frame."""
    header = stream.read(4)
    if not header:
        return None
    if len(header) < 4:
        raise ValueError("truncated length prefix")
    (length,) = struct.unpack("<I", header)
    if length > MAX_MESSAGE_BYTES:
        raise ValueError(f"message too large ({length} bytes)")
    body = stream.read(length)
    if len(body) < length:
        raise ValueError("truncated message")
    msg = json.loads(body.decode("utf-8"))
    if not isinstance(msg, dict):
        raise ValueError("message must be a JSON object")
    return msg


def write_message(stream: BinaryIO, obj: dict) -> None:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    stream.write(struct.pack("<I", len(body)) + body)
    stream.flush()


# talking to the app -------------------------------------------------------------


def app_command() -> list[str]:
    """Command that starts the app minimised to the tray, detached from this host."""
    if getattr(sys, "frozen", False):
        name = "Fetchly.exe" if sys.platform == "win32" else "Fetchly"
        return [str(Path(sys.executable).with_name(name)), "--tray"]
    from .autostart import launch_command

    return launch_command()


def launch_app() -> None:
    """Start the app detached, so closing the browser (or this host) does not stop it."""
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                    "close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                                   | subprocess.CREATE_NO_WINDOW)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(app_command(), **kwargs)


def _send(msg: dict) -> bool:
    from .gui.single_instance import send_to_running

    return send_to_running(msg)


def forward(msg: dict, send: Callable[[dict], bool] | None = None, launch: Callable[[], None] | None = None,
            wait: float = LAUNCH_WAIT_SECONDS, sleep: Callable[[float], None] = time.sleep,
            clock: Callable[[], float] = time.monotonic) -> dict:
    """Hand ``msg`` to the running app, starting it first if needed."""
    send = send or _send
    launch = launch or launch_app
    if send(msg):
        return {"ok": True}
    try:
        launch()
    except OSError as e:
        return {"ok": False, "error": f"could not start Fetchly: {e}"}
    deadline = clock() + wait
    while clock() < deadline:
        sleep(RETRY_INTERVAL)
        if send(msg):
            return {"ok": True}
    return {"ok": False, "error": "Fetchly did not start in time"}


def handle(msg: dict, **hooks) -> dict:
    """Turn one browser message into a reply. ``hooks`` are forwarded to ``forward`` (for tests)."""
    kind = msg.get("type")
    if kind == "ping":
        send = hooks.get("send") or _send
        return {"ok": True, "version": __version__, "running": bool(send({"cmd": "ping"}))}
    if kind == "download":
        url = msg.get("url")
        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
            return {"ok": False, "error": "missing or unsupported url"}
        headers = msg.get("headers")
        add = {
            "cmd": "add",
            "url": url,
            "referrer": msg.get("referrer") if isinstance(msg.get("referrer"), str) else "",
            "filename": msg.get("filename") if isinstance(msg.get("filename"), str) else "",
            "headers": {str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) else {},
        }
        return forward(add, **hooks)
    return {"ok": False, "error": f"unknown message type {kind!r}"}


def serve(stdin: BinaryIO, stdout: BinaryIO, **hooks) -> None:
    """Answer messages until the browser closes the pipe."""
    while True:
        try:
            msg = read_message(stdin)
        except (ValueError, UnicodeDecodeError) as e:
            write_message(stdout, {"ok": False, "error": f"bad message: {e}"})
            return  # framing is lost; the browser will start a new host
        if msg is None:
            return
        try:
            reply = handle(msg, **hooks)
        except Exception as e:  # noqa: BLE001 - never leave the browser waiting for a reply
            reply = {"ok": False, "error": str(e) or e.__class__.__name__}
        write_message(stdout, reply)


def caller_allowed(argv: list[str]) -> bool:
    """Chrome passes the caller's origin as an argument. Refuse origins other than ours.

    (Chrome already enforces ``allowed_origins``; this is a second check. Firefox passes the
    manifest path and extension id instead, and is enforced by ``allowed_extensions``.)
    """
    from .native_host_install import CHROME_ORIGIN

    origins = [a for a in argv if a.startswith("chrome-extension://")]
    return all(o == CHROME_ORIGIN for o in origins)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if sys.platform == "win32":  # make stdio binary: no CRLF translation of the length prefix
        import msvcrt
        import os

        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    if not caller_allowed(argv):
        write_message(stdout, {"ok": False, "error": "caller not allowed"})
        return 1
    # QtNetwork's blocking socket calls want a core application object to exist.
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])  # noqa: F841
    serve(stdin, stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
