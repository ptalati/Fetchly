"""App wiring: single-instance hand-off, first-run autostart, tray/window behaviour (offscreen Qt)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.test_integration import ROOT, qapp, run_blocking  # noqa: E402,F401  (shared fixtures/helpers)

HANDOFF_SNIPPET = (
    "import json, sys; from fetchly.gui.app import hand_off_to_running; "
    "print(hand_off_to_running(json.loads(sys.argv[1]), name=sys.argv[2]))"
)


def hand_off_from_other_process(args: list, name: str) -> bool:
    import json
    import subprocess
    import sys

    env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen")
    out = subprocess.run([sys.executable, "-c", HANDOFF_SNIPPET, json.dumps(args), name], env=env,
                         capture_output=True, text=True, timeout=30)
    return out.stdout.strip() == "True"


def test_handoff_message():
    from fetchly.gui.app import handoff_message

    assert handoff_message([]) == {"cmd": "show"}
    assert handoff_message(["--tray"]) == {"cmd": "ping"}
    assert handoff_message(["http://x.test/a.zip"]) == {"cmd": "add", "url": "http://x.test/a.zip"}
    assert handoff_message(["--tray", "https://x.test/b.iso"]) == {"cmd": "add", "url": "https://x.test/b.iso"}


def test_hand_off_reaches_running_instance(qapp):
    from fetchly.gui.app import hand_off_to_running
    from fetchly.gui.single_instance import InstanceServer

    name = f"fetchly-test-handoff-{os.getpid()}"
    assert hand_off_to_running(["http://x.test/a.zip"], name=name) is False  # nobody home yet
    server = InstanceServer(name)
    assert server.listen()
    added, shown = [], []
    server.addRequested.connect(added.append)
    server.showRequested.connect(lambda: shown.append(1))
    try:
        assert run_blocking(qapp, lambda: hand_off_from_other_process(["http://x.test/a.zip"], name)) is True
        assert run_blocking(qapp, lambda: hand_off_from_other_process([], name)) is True
        assert run_blocking(qapp, lambda: hand_off_from_other_process(["--tray"], name)) is True
    finally:
        server.close()
    assert added == [{"cmd": "add", "url": "http://x.test/a.zip"}]
    assert shown == [1]  # --tray only pings


class FakeStore:
    def __init__(self):
        self.d = {}

    def get_setting(self, key, default=None):
        return self.d.get(key, default)

    def set_setting(self, key, value):
        self.d[key] = value


def test_first_run_autostart(monkeypatch):
    from fetchly import autostart
    from fetchly.gui.app import init_first_run_autostart

    calls = []
    monkeypatch.setattr(autostart, "set_enabled", lambda on: calls.append(on))
    store = FakeStore()
    assert init_first_run_autostart(store, frozen=False) is False  # dev runs never add Run keys
    assert calls == [] and "autostart_initialized" not in store.d
    assert init_first_run_autostart(store, frozen=True) is True
    assert calls == [True] and store.d["autostart_initialized"] == "1"
    assert init_first_run_autostart(store, frozen=True) is False  # a user who turned it off stays off
    assert calls == [True]


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from fetchly.engine import DownloadManager

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    from fetchly.gui import theme
    from fetchly.gui.main_window import MainWindow

    theme.apply_palette(app, theme.LIGHT)
    mgr = DownloadManager(tmp_path / "t.db")
    mgr.start()
    w = MainWindow(mgr)
    yield w
    w._quitting = True
    w.tray.hide()
    w.clipboard_watcher.enabled = False
    w.close()
    mgr.shutdown()


def test_close_hides_to_tray_and_hints_once(window, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    shown = []
    monkeypatch.setattr(window.tray, "showMessage", lambda *a, **k: shown.append(a[1]))
    window.show()
    window.close()
    assert not window.isVisible() and not window._quitting
    window.show()
    window.close()
    assert len(shown) == 1 and "still running in the tray" in shown[0]


def test_browser_add_confirm_and_direct(window, monkeypatch):
    opened = []
    monkeypatch.setattr(window, "add_url", lambda url=None, headers=None, show_main=True: opened.append((url, headers)))
    window.on_browser_add({"url": "http://x.test/a.zip", "referrer": "http://x.test/", "headers": {"Cookie": "a=b"}})
    window.on_browser_add({"url": "http://x.test/b.zip", "referrer": "http://x.test/"})
    assert opened == [("http://x.test/a.zip", {"Cookie": "a=b"}), ("http://x.test/b.zip", {"Referer": "http://x.test/"})]

    window.set_flag("browser_confirm", False)
    added = []
    monkeypatch.setattr(window.manager, "add", lambda *a, **k: added.append((a, k)) or 1)
    monkeypatch.setattr(window.tray, "showMessage", lambda *a, **k: None)
    window.on_browser_add({"url": "http://x.test/c.zip", "referrer": "http://x.test/"})
    assert len(opened) == 2 and added[0][0][0] == "http://x.test/c.zip"
    assert added[0][1]["headers"] == {"Referer": "http://x.test/"}


def test_clipboard_link_ignores_known_and_open_dialog(window, monkeypatch):
    opened = []
    monkeypatch.setattr(window, "add_url", lambda url=None, **k: opened.append(url))
    window._on_clipboard_link("http://x.test/a.zip")
    assert opened == ["http://x.test/a.zip"]
    window._add_dialog_open = True
    window._on_clipboard_link("http://x.test/b.zip")
    window._add_dialog_open = False
    assert opened == ["http://x.test/a.zip"]
    window.manager.add("http://x.test/known.zip", ".", start=False)
    window._on_clipboard_link("http://x.test/known.zip")
    assert opened == ["http://x.test/a.zip"]


def test_flags_and_watch_toggle(window):
    assert window.flag("watch_clipboard", True) is True
    window.act_watch.setChecked(False)
    assert window.clipboard_watcher.enabled is False and window.flag("watch_clipboard", True) is False
    window.set_flag("browser_confirm", False)
    assert window.flag("browser_confirm", True) is False


def test_browser_add_ignores_repeats(window, monkeypatch):
    opened = []
    monkeypatch.setattr(window, "add_url", lambda url=None, headers=None, show_main=True: opened.append(url))
    msg = {"url": "http://x.test/dup.zip", "referrer": "http://x.test/"}
    window.on_browser_add(msg)
    window.on_browser_add(dict(msg))  # the same click delivered twice
    assert opened == ["http://x.test/dup.zip"]

    import fetchly.gui.main_window as mw

    real = mw.time.monotonic
    monkeypatch.setattr(mw.time, "monotonic", lambda: real() + mw.BROWSER_DEDUPE_SECONDS + 1)
    window.on_browser_add(dict(msg))  # deliberately downloaded again later
    assert opened == ["http://x.test/dup.zip"] * 2


def test_browser_add_queued_while_dialog_open(window, monkeypatch):
    opened = []
    monkeypatch.setattr(window, "add_url", lambda url=None, headers=None, show_main=True: opened.append(url))
    window._add_dialog_open = True
    window.on_browser_add({"url": "http://x.test/q.zip"})
    window.on_browser_add({"url": "http://x.test/q.zip"})
    assert len(window._pending_adds) == 1 and opened == []
    window._add_dialog_open = False
    window._run_pending_add()
    assert opened == ["http://x.test/q.zip"]


def test_add_is_acknowledged_before_the_slot_runs(qapp):
    """A slot that blocks (the modal Add dialog) must not delay the reply past the sender's timeout."""
    import time

    from fetchly.gui.single_instance import InstanceServer

    name = f"fetchly-test-ackfirst-{os.getpid()}"
    server = InstanceServer(name)
    assert server.listen()
    seen = []

    def slow_slot(msg):  # like the modal Add dialog: a nested event loop that outlives the sender's timeout
        seen.append(msg["url"])
        end = time.monotonic() + 4
        while time.monotonic() < end:
            qapp.processEvents()
            time.sleep(0.01)

    server.addRequested.connect(slow_slot)
    try:
        assert run_blocking(qapp, lambda: hand_off_from_other_process(["http://x.test/slow.zip"], name)) is True
        end = time.monotonic() + 10
        while not seen and time.monotonic() < end:
            qapp.processEvents()
            time.sleep(0.01)
    finally:
        server.close()
    assert seen == ["http://x.test/slow.zip"]


def test_detail_blocks_merge_into_one_bar_when_complete(qapp):
    from dataclasses import replace

    from fetchly.engine.models import DownloadSnapshot, SegmentView, Status
    from fetchly.gui.widgets import DetailPanel

    segs = tuple(SegmentView(i * 100, i * 100 + 99, 50, True) for i in range(4))
    snap = DownloadSnapshot(1, "http://x.test/a.zip", ".", "a.zip", 400, 200, Status.DOWNLOADING, True,
                            4, 4, 0.0, None, None, 0.0, None, segs)
    panel = DetailPanel()
    panel.show_snapshot(snap)
    assert len(panel.blocks.fractions) == 4 and panel.caption.text() == DetailPanel.CAPTION
    done = replace(snap, status=Status.COMPLETED, downloaded=400,
                   segments=tuple(replace(s, downloaded=100, active=False) for s in segs))
    panel.show_snapshot(done)
    assert panel.blocks.fractions == [] and panel.caption.text() == DetailPanel.DONE_CAPTION
    assert panel.percent.text() == "100%"
