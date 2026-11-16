import asyncio
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from server import RangeServer  # noqa: E402

from fetchly.engine import Download, DownloadManager, DownloadRecord, Status, Store  # noqa: E402

FAST = dict(backoff_base=0.01, min_split_size=64 * 1024, save_interval=0.05)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def make_server():
    servers = []

    def _make(data: bytes, **kw) -> RangeServer:
        s = RangeServer(data, **kw).start()
        servers.append(s)
        return s

    yield _make
    for s in servers:
        s.stop()


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "state.db")
    yield s
    s.close()


def new_download(store, url, folder, connections=8, **kw):
    return Download(store, DownloadRecord(url=url, folder=str(folder), connections=connections), **{**FAST, **kw})


def test_full_download_parallel(make_server, store, tmp_path):
    data = os.urandom(3 * 1024 * 1024 + 123)  # odd size on purpose
    srv = make_server(data)
    d = new_download(store, srv.url, tmp_path / "out", connections=8)
    status = asyncio.run(d.run())

    assert status == Status.COMPLETED, d.rec.error
    out = tmp_path / "out" / "file.bin"
    assert out.exists() and not (tmp_path / "out" / "file.bin.part").exists()
    assert sha(out) == srv.sha256
    assert d.rec.resumable and d.rec.size == len(data)
    assert len(set(srv.range_starts())) >= 8  # really used parallel ranges
    assert store.get(d.id).status == Status.COMPLETED


def test_resume_after_interruption(make_server, store, tmp_path):
    data = os.urandom(2 * 1024 * 1024)
    srv = make_server(data, delay=0.01)  # ~1.6 MB/s per connection
    folder = tmp_path / "out"

    async def run_then_pause():
        d = new_download(store, srv.url, folder, connections=4)
        task = d.start()
        while d.rec.downloaded < 400 * 1024:
            await asyncio.sleep(0.02)
        d.stop()
        return await task, d

    status, d1 = asyncio.run(run_then_pause())
    assert status == Status.PAUSED
    saved = store.get(d1.id)
    assert saved.status == Status.PAUSED
    assert 0 < saved.downloaded < len(data)
    assert sum(s.downloaded for s in saved.segments) == saved.downloaded
    assert (folder / "file.bin.part").stat().st_size == len(data)  # pre-allocated

    # A fresh engine instance (as after an app restart) continues from the database.
    srv.delay = 0.0
    srv.requests.clear()
    d2 = Download(store, store.get(d1.id), **FAST)
    assert asyncio.run(d2.run()) == Status.COMPLETED, d2.rec.error
    assert sha(folder / "file.bin") == srv.sha256
    # It asked only for the missing bytes: every range started past its segment's original start.
    resumed_from = [s for s in srv.range_starts() if s > 0]
    assert resumed_from and all(st not in (0, 512 * 1024, 1024 * 1024, 1536 * 1024) for st in resumed_from)


def test_resume_restarts_when_file_changed(make_server, store, tmp_path):
    data = os.urandom(1024 * 1024)
    srv = make_server(data, delay=0.01)

    async def run_then_pause():
        d = new_download(store, srv.url, tmp_path, connections=4)
        task = d.start()
        while d.rec.downloaded < 200 * 1024:
            await asyncio.sleep(0.02)
        d.stop()
        await task
        return d

    d1 = asyncio.run(run_then_pause())
    new_data = os.urandom(1024 * 1024)
    srv.data, srv.etag, srv.delay = new_data, '"v2"', 0.0
    d2 = Download(store, store.get(d1.id), **FAST)
    assert asyncio.run(d2.run()) == Status.COMPLETED
    assert sha(tmp_path / "file.bin") == hashlib.sha256(new_data).hexdigest()


def test_server_without_range_support(make_server, store, tmp_path):
    data = os.urandom(1024 * 1024 + 7)
    srv = make_server(data, ranges=False)
    d = new_download(store, srv.url, tmp_path, connections=8)
    assert asyncio.run(d.run()) == Status.COMPLETED, d.rec.error
    assert not d.rec.resumable
    assert len(d.rec.segments) == 1
    assert sha(tmp_path / "file.bin") == srv.sha256
    # probe + one real download, no parallel ranges
    assert len([r for r in srv.requests if r[1] is None]) == 1


def test_dynamic_splitting(make_server, store, tmp_path):
    data = os.urandom(2 * 1024 * 1024)
    # The first half crawls, the second half is instant: connection 2 finishes early
    # and must take over half of what connection 1 still has left.
    srv = make_server(data, delay=lambda start: 0.02 if start < 1024 * 1024 else 0.0)
    d = new_download(store, srv.url, tmp_path, connections=2)
    t0 = time.monotonic()
    assert asyncio.run(d.run()) == Status.COMPLETED, d.rec.error
    assert d.splits >= 1
    assert len(d.rec.segments) > 2
    assert sha(tmp_path / "file.bin") == srv.sha256
    # Segments still tile the file exactly.
    segs = sorted(d.rec.segments, key=lambda s: s.start)
    assert segs[0].start == 0 and segs[-1].end == len(data) - 1
    assert all(a.end + 1 == b.start for a, b in zip(segs, segs[1:]))
    # Without splitting, 1 MB at 16 KB/20 ms would take ~1.3 s; splitting must beat that.
    assert time.monotonic() - t0 < 1.3


def test_retries_transient_errors(make_server, store, tmp_path):
    data = os.urandom(512 * 1024)
    srv = make_server(data, fail_first=3)
    d = new_download(store, srv.url, tmp_path, connections=4)
    assert asyncio.run(d.run()) == Status.COMPLETED, d.rec.error
    assert sha(tmp_path / "file.bin") == srv.sha256


def test_existing_file_gets_unique_name(make_server, store, tmp_path):
    srv = make_server(os.urandom(100_000))
    (tmp_path / "file.bin").write_bytes(b"old")
    d = new_download(store, srv.url, tmp_path)
    assert asyncio.run(d.run()) == Status.COMPLETED
    assert (tmp_path / "file.bin").read_bytes() == b"old"
    assert sha(tmp_path / "file (1).bin") == srv.sha256


def test_manager_end_to_end(make_server, tmp_path):
    data = os.urandom(1024 * 1024)
    srv = make_server(data)
    m = DownloadManager(tmp_path / "m.db", max_active=2, **FAST)
    m.start()
    try:
        ids = [m.add(srv.url, str(tmp_path / f"d{i}"), connections=4) for i in range(3)]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            snaps = {s.id: s for s in m.snapshots()}
            if all(snaps[i].status == Status.COMPLETED for i in ids):
                break
            time.sleep(0.05)
        assert all(snaps[i].status == Status.COMPLETED for i in ids), [snaps[i].error for i in ids]
        for i in range(3):
            assert sha(tmp_path / f"d{i}" / "file.bin") == srv.sha256
        m.remove(ids[0])
        assert all(s.id != ids[0] for s in m.snapshots())
    finally:
        m.shutdown()


def test_engine_has_no_qt_imports():
    engine_dir = Path(__file__).parent.parent / "fetchly" / "engine"
    for f in engine_dir.glob("*.py"):
        imports = re.findall(r"^\s*(?:from|import)\s+(\S+)", f.read_text(), re.M)
        assert not [m for m in imports if m.startswith(("PySide", "PyQt", "shiboken"))], f
