"""Tests for link capture, autostart, the native messaging host and its installer, and the local socket."""

import io
import json
import os
import plistlib
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fetchly import __version__, autostart, native_host, native_host_install as nhi  # noqa: E402
from fetchly.linkcapture import download_link  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def frame(obj) -> bytes:
    body = json.dumps(obj).encode("utf-8")
    return struct.pack("<I", len(body)) + body


def unframe(data: bytes) -> list[dict]:
    out, buf = [], io.BytesIO(data)
    while (msg := native_host.read_message(buf)) is not None:
        out.append(msg)
    return out


# linkcapture ---------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "https://example.com/files/movie.mp4",
    "  http://example.com/a/b.ZIP \n",
    "https://example.com/setup.exe?token=abc#frag",
    "https://example.com/My%20Doc.pdf",
    "https://example.com/pkg.tar.gz",
    "https://example.com/x.torrent",
])
def test_download_link_accepts(text):
    assert download_link(text) == text.strip()


@pytest.mark.parametrize("text", [
    "", "   ", "hello world", "https://example.com/", "https://example.com/page.html",
    "https://example.com/notes.txt", "ftp://example.com/a.zip", "file:///C:/a.zip", "javascript:alert(1)",
    "https://example.com/a.zip https://example.com/b.zip", "see https://example.com/a.zip",
    "https:///a.zip", "https://example.com/" + "a" * 5000 + ".zip", "example.com/a.zip",
])
def test_download_link_rejects(text):
    assert download_link(text) is None


# autostart -----------------------------------------------------------------------


class FakeRegistry:
    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


def test_launch_command_from_source():
    cmd = autostart.launch_command()
    assert cmd[-3:] == ["-m", "fetchly", "--tray"] or cmd[-1] == "--tray"
    assert cmd[-1] == "--tray"


def test_launch_command_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert autostart.launch_command() == [sys.executable, "--tray"]


def test_autostart_windows_registry(monkeypatch):
    reg = FakeRegistry()
    monkeypatch.setattr(autostart, "registry", reg)
    assert not autostart.is_enabled(platform="win32")
    autostart.set_enabled(True, platform="win32")
    assert autostart.is_enabled(platform="win32")
    assert "--tray" in reg.values["Fetchly"]
    autostart.set_enabled(True, platform="win32")  # idempotent
    autostart.set_enabled(False, platform="win32")
    assert not autostart.is_enabled(platform="win32")
    autostart.set_enabled(False, platform="win32")  # nothing to remove: no error


def test_autostart_macos_launch_agent(tmp_path):
    assert not autostart.is_enabled(tmp_path, "darwin")
    autostart.set_enabled(True, tmp_path, "darwin")
    plist = plistlib.loads(autostart.launch_agent_path(tmp_path).read_bytes())
    assert plist["Label"] == "app.fetchly.Fetchly"
    assert plist["RunAtLoad"] is True
    assert plist["ProgramArguments"][-1] == "--tray"
    assert autostart.is_enabled(tmp_path, "darwin")
    autostart.set_enabled(False, tmp_path, "darwin")
    assert not autostart.is_enabled(tmp_path, "darwin")


def test_autostart_linux_desktop_entry(tmp_path):
    autostart.set_enabled(True, tmp_path, "linux")
    entry = (tmp_path / ".config" / "autostart" / "fetchly.desktop").read_text(encoding="utf-8")
    assert "Exec=" in entry and "--tray" in entry
    assert autostart.is_enabled(tmp_path, "linux")
    autostart.set_enabled(False, tmp_path, "linux")
    assert not autostart.is_enabled(tmp_path, "linux")


# native host framing and handling -------------------------------------------------


def test_framing_round_trip_and_unicode():
    out = io.BytesIO()
    native_host.write_message(out, {"ok": True, "name": "caf\u00e9"})
    native_host.write_message(out, {"ok": False})
    assert unframe(out.getvalue()) == [{"ok": True, "name": "caf\u00e9"}, {"ok": False}]


def test_read_message_errors():
    assert native_host.read_message(io.BytesIO(b"")) is None
    with pytest.raises(ValueError):
        native_host.read_message(io.BytesIO(b"\x01\x00"))  # truncated prefix
    with pytest.raises(ValueError):
        native_host.read_message(io.BytesIO(struct.pack("<I", 50) + b"{}"))  # truncated body
    with pytest.raises(ValueError):
        native_host.read_message(io.BytesIO(struct.pack("<I", native_host.MAX_MESSAGE_BYTES + 1)))
    with pytest.raises(ValueError):
        native_host.read_message(io.BytesIO(frame([1, 2])))  # not an object


def test_ping_reply():
    reply = native_host.handle({"type": "ping"}, send=lambda m: m == {"cmd": "ping"})
    assert reply == {"ok": True, "version": __version__, "running": True}
    assert native_host.handle({"type": "ping"}, send=lambda m: False)["running"] is False


def test_download_forwarded():
    sent = []
    msg = {"type": "download", "url": "https://x.test/a.zip", "referrer": "https://x.test/", "filename": "a.zip",
           "headers": {"Cookie": "a=b", "N": 1}}
    reply = native_host.handle(msg, send=lambda m: sent.append(m) or True)
    assert reply == {"ok": True}
    assert sent == [{"cmd": "add", "url": "https://x.test/a.zip", "referrer": "https://x.test/",
                     "filename": "a.zip", "headers": {"Cookie": "a=b", "N": "1"}}]


def test_download_rejects_bad_input():
    assert native_host.handle({"type": "download", "url": "file:///etc/passwd"}, send=lambda m: True)["ok"] is False
    assert native_host.handle({"type": "download"}, send=lambda m: True)["ok"] is False
    assert native_host.handle({"type": "nope"})["ok"] is False


def test_download_launches_app_then_retries():
    calls = {"send": 0, "launch": 0}
    now = [0.0]

    def send(m):
        calls["send"] += 1
        return calls["send"] >= 4  # the app needs a few attempts to come up

    def launch():
        calls["launch"] += 1

    def sleep(s):
        now[0] += s

    reply = native_host.forward({"cmd": "add"}, send=send, launch=launch, sleep=sleep, clock=lambda: now[0])
    assert reply == {"ok": True}
    assert calls == {"send": 4, "launch": 1}


def test_download_gives_up_after_timeout():
    now = [0.0]

    def sleep(s):
        now[0] += s

    reply = native_host.forward({"cmd": "add"}, send=lambda m: False, launch=lambda: None, wait=2.0,
                                sleep=sleep, clock=lambda: now[0])
    assert reply["ok"] is False and "error" in reply


def test_launch_failure_reported():
    def boom():
        raise OSError("nope")

    reply = native_host.forward({"cmd": "add"}, send=lambda m: False, launch=boom)
    assert reply["ok"] is False and "nope" in reply["error"]


def test_serve_answers_each_message_and_survives_errors():
    stdin = io.BytesIO(frame({"type": "ping"}) + frame({"type": "bogus"}) + frame({"type": "ping"}))
    stdout = io.BytesIO()
    native_host.serve(stdin, stdout, send=lambda m: True)
    replies = unframe(stdout.getvalue())
    assert [r["ok"] for r in replies] == [True, False, True]


def test_serve_bad_frame_replies_and_stops():
    stdout = io.BytesIO()
    native_host.serve(io.BytesIO(b"\xff\xff\xff\xff"), stdout)
    assert unframe(stdout.getvalue())[0]["ok"] is False


def test_caller_allowed():
    assert native_host.caller_allowed([])
    assert native_host.caller_allowed([nhi.CHROME_ORIGIN])
    assert native_host.caller_allowed(["C:\\x\\app.fetchly.host.json", "fetchly@fetchly.app"])
    assert not native_host.caller_allowed(["chrome-extension://" + "a" * 32 + "/"])


# native host installer -------------------------------------------------------------


class FakeHostRegistry:
    def __init__(self):
        self.keys = {}

    def set_default(self, key, value):
        self.keys[key] = value

    def get_default(self, key):
        return self.keys.get(key)

    def delete(self, key):
        self.keys.pop(key, None)


def test_manifest_contents():
    c = nhi.manifest("chrome", "C:/x/fetchly-host.exe")
    assert c["name"] == "app.fetchly.host" and c["type"] == "stdio" and c["path"] == "C:/x/fetchly-host.exe"
    assert c["allowed_origins"] == [nhi.CHROME_ORIGIN] and "allowed_extensions" not in c
    f = nhi.manifest("firefox", "/x/fetchly-host")
    assert f["allowed_extensions"] == ["fetchly@fetchly.app"] and "allowed_origins" not in f


def test_extension_id_matches_manifest_key():
    import base64
    import hashlib

    key = json.loads((ROOT / "browser-extension" / "manifest.chrome.json").read_text(encoding="utf-8"))["key"]
    digest = hashlib.sha256(base64.b64decode(key)).hexdigest()[:32]
    assert "".join(chr(ord("a") + int(c, 16)) for c in digest) == nhi.CHROME_EXTENSION_ID


def test_register_windows(tmp_path):
    reg = FakeHostRegistry()
    data = tmp_path / "data"
    exe = tmp_path / "fetchly-host.exe"
    files = nhi.register(platform="win32", reg=reg, data=data, executable=exe)
    assert files and all(f.exists() for f in files)
    for sub in (r"Software\Google\Chrome", r"Software\Microsoft\Edge", r"Software\BraveSoftware\Brave-Browser",
                r"Software\Mozilla"):
        assert reg.keys[sub + r"\NativeMessagingHosts\app.fetchly.host"].endswith(".json")
    firefox = json.loads(Path(reg.keys[r"Software\Mozilla\NativeMessagingHosts\app.fetchly.host"]).read_text("utf-8"))
    assert firefox["allowed_extensions"] == ["fetchly@fetchly.app"] and firefox["path"] == str(exe)
    assert nhi.is_registered(platform="win32", reg=reg, data=data, executable=exe)
    before = dict(reg.keys)
    nhi.register(platform="win32", reg=reg, data=data, executable=exe)  # idempotent
    assert reg.keys == before
    nhi.unregister(platform="win32", reg=reg, data=data)
    assert reg.keys == {} and not nhi.is_registered(platform="win32", reg=reg, data=data, executable=exe)


def test_is_registered_detects_moved_executable(tmp_path):
    reg = FakeHostRegistry()
    nhi.register(platform="win32", reg=reg, data=tmp_path, executable=tmp_path / "a.exe")
    assert not nhi.is_registered(platform="win32", reg=reg, data=tmp_path, executable=tmp_path / "b.exe")


def test_register_linux_only_for_installed_browsers(tmp_path):
    (tmp_path / ".config" / "google-chrome").mkdir(parents=True)
    (tmp_path / ".mozilla").mkdir()
    files = nhi.register(home=tmp_path, platform="linux", executable="/opt/fetchly/fetchly-host")
    assert {f.parent.parent.name for f in files} == {"google-chrome", ".mozilla"}
    chrome = json.loads((tmp_path / ".config/google-chrome/NativeMessagingHosts/app.fetchly.host.json").read_text("utf-8"))
    assert chrome["allowed_origins"] == [nhi.CHROME_ORIGIN]
    assert not (tmp_path / ".config" / "chromium").exists()
    assert nhi.is_registered(home=tmp_path, platform="linux", executable="/opt/fetchly/fetchly-host")
    nhi.unregister(home=tmp_path, platform="linux")
    assert not list(tmp_path.rglob("app.fetchly.host.json"))


def test_register_macos(tmp_path):
    support = tmp_path / "Library" / "Application Support"
    (support / "Google" / "Chrome").mkdir(parents=True)
    (support / "Mozilla").mkdir()
    nhi.register(home=tmp_path, platform="darwin", executable="/Applications/Fetchly.app/x/fetchly-host")
    assert (support / "Google/Chrome/NativeMessagingHosts/app.fetchly.host.json").exists()
    assert (support / "Mozilla/NativeMessagingHosts/app.fetchly.host.json").exists()


def test_host_executable_from_source_writes_launcher(tmp_path):
    p = nhi.host_executable(platform="win32", data=tmp_path)
    assert p.name == "fetchly-host.bat" and "fetchly.native_host" in p.read_text()
    q = nhi.host_executable(platform="linux", data=tmp_path)
    assert q.name == "fetchly-host.sh" and q.read_text().startswith("#!/bin/sh")


# local socket and real host round trip ----------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication  # a QCoreApplication too; GUI wiring tests share it

    return QApplication.instance() or QApplication([])


def run_blocking(qapp, fn, timeout_ms=15000):
    """Run ``fn`` in a thread while pumping the Qt event loop, so an InstanceServer can answer it."""
    from PySide6.QtCore import QEventLoop, QTimer

    result = {}

    def work():
        result["value"] = fn()

    t = threading.Thread(target=work)
    t.start()
    loop = QEventLoop()
    poll = QTimer()
    poll.timeout.connect(lambda: loop.quit() if not t.is_alive() else None)
    poll.start(20)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    t.join(1)
    # Deliver signals the server queued for the event loop (it acknowledges first, then signals).
    for _ in range(20):
        qapp.processEvents()
        time.sleep(0.005)
    return result.get("value")


SEND_SNIPPET = (
    "import json, sys; from fetchly.gui.single_instance import send_to_running; "
    "print(send_to_running(json.loads(sys.argv[1]), timeout_ms=3000, name=sys.argv[2]))"
)


def send_from_other_process(msg: dict, name: str) -> bool:
    """send_to_running blocks, and Qt sockets do not cross threads, so a client is a separate process."""
    env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen")
    out = subprocess.run([sys.executable, "-c", SEND_SNIPPET, json.dumps(msg), name], env=env,
                         capture_output=True, text=True, timeout=30)
    return out.stdout.strip() == "True"


def test_instance_server_signals(qapp):
    from fetchly.gui.single_instance import InstanceServer, send_to_running

    name = f"fetchly-test-{os.getpid()}"
    server = InstanceServer(name)
    assert server.listen()
    added, shown = [], []
    server.addRequested.connect(added.append)
    server.showRequested.connect(lambda: shown.append(1))
    try:
        assert run_blocking(qapp, lambda: send_from_other_process({"cmd": "show"}, name)) is True
        msg = {"cmd": "add", "url": "https://x.test/a.zip", "headers": {"Cookie": "a=b"}}
        assert run_blocking(qapp, lambda: send_from_other_process(msg, name)) is True
        assert run_blocking(qapp, lambda: send_from_other_process({"cmd": "ping"}, name)) is True
        assert run_blocking(qapp, lambda: send_from_other_process({"cmd": "add", "url": "ftp://x"}, name)) is False
        assert run_blocking(qapp, lambda: send_from_other_process({"cmd": "bogus"}, name)) is False
    finally:
        server.close()
    assert shown == [1]
    assert added == [msg]
    assert send_to_running({"cmd": "ping"}, timeout_ms=300, name=name) is False  # closed: nobody home


def test_real_host_process_round_trip(qapp, monkeypatch):
    """Frame a message into `python -m fetchly.native_host` and see the app side receive it."""
    from fetchly.gui import single_instance
    from fetchly.gui.single_instance import InstanceServer

    monkeypatch.setenv("FETCHLY_INSTANCE_NAME", f"fetchly-test-host-{os.getpid()}")  # never the real app's socket
    server = InstanceServer()
    assert server.listen()
    added = []
    server.addRequested.connect(added.append)
    env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen")
    payload = frame({"type": "ping"}) + frame({
        "type": "download", "url": "https://x.test/f.iso", "referrer": "https://x.test/",
        "filename": "f.iso", "headers": {"Cookie": "s=1", "User-Agent": "UA"},
    })

    def run_host():
        return subprocess.run([sys.executable, "-m", "fetchly.native_host"], input=payload, env=env,
                              capture_output=True, timeout=30)

    try:
        proc = run_blocking(qapp, run_host, timeout_ms=40000)
    finally:
        server.close()
    assert proc is not None and proc.returncode == 0, getattr(proc, "stderr", b"")
    ping, download = unframe(proc.stdout)
    assert ping == {"ok": True, "version": __version__, "running": True}
    assert download == {"ok": True}
    assert added == [{"cmd": "add", "url": "https://x.test/f.iso", "referrer": "https://x.test/",
                      "filename": "f.iso", "headers": {"Cookie": "s=1", "User-Agent": "UA"}}]
    assert single_instance.server_name()  # name is stable for the user
