"""Runs many downloads on a background asyncio thread. Thread-safe, Qt-free.

The GUI (or any other front end) calls add/pause/resume/remove from its own
thread and polls ``snapshots()`` to draw progress.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from .downloader import DEFAULT_CONNECTIONS, Download, clean_headers
from .models import DownloadRecord, DownloadSnapshot, Status
from .store import Store


class DownloadManager:
    def __init__(self, db_path: str | Path, *, max_active: int = 3, **download_kwargs):
        self.store = Store(db_path)
        self.max_active = max_active
        self._kwargs = download_kwargs
        self._downloads: dict[int, Download] = {}
        self._lock = threading.RLock()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="fetchly-engine", daemon=True)

        for rec in self.store.all():
            if rec.status.is_running or rec.status == Status.QUEUED:
                # Interrupted by a crash or quit: keep progress, wait for the user.
                rec.status = Status.PAUSED
                self.store.update(rec)
            self._downloads[rec.id] = Download(self.store, rec, **self._kwargs)

    # lifecycle -----------------------------------------------------------

    def start(self) -> None:
        self._thread.start()

    def shutdown(self, timeout: float = 5.0) -> None:
        """Pause everything that is running (progress is saved) and stop the thread."""
        if not self._thread.is_alive():
            return

        async def _stop_all():
            tasks = []
            for d in list(self._downloads.values()):
                if d._task and not d._task.done():
                    tasks.append(d._task)
                    d.stop()
            if tasks:
                await asyncio.wait(tasks, timeout=timeout)

        try:
            asyncio.run_coroutine_threadsafe(_stop_all(), self._loop).result(timeout + 1)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout)
            self.store.close()

    # commands (any thread) ------------------------------------------------

    def add(self, url: str, folder: str, connections: int = DEFAULT_CONNECTIONS, start: bool = True,
            headers: dict[str, str] | None = None) -> int:
        rec = DownloadRecord(url=url, folder=str(folder), connections=connections,
                             status=Status.QUEUED if start else Status.PAUSED,
                             headers=clean_headers(headers))
        self.store.add(rec)
        with self._lock:
            self._downloads[rec.id] = Download(self.store, rec, **self._kwargs)
        self._call(self._schedule)
        return rec.id

    def pause(self, download_id: int) -> None:
        self._call(self._pause, download_id)

    def resume(self, download_id: int) -> None:
        self._call(self._resume, download_id)

    def remove(self, download_id: int, delete_file: bool = False) -> None:
        fut = asyncio.run_coroutine_threadsafe(self._remove(download_id, delete_file), self._loop)
        fut.result(10)

    def snapshots(self) -> list[DownloadSnapshot]:
        with self._lock:
            downloads = list(self._downloads.values())
        return [d.snapshot() for d in downloads]

    def snapshot(self, download_id: int) -> DownloadSnapshot | None:
        d = self._downloads.get(download_id)
        return d.snapshot() if d else None

    def set_max_active(self, n: int) -> None:
        self.max_active = max(1, n)
        self._call(self._schedule)

    # engine thread --------------------------------------------------------

    def _call(self, fn, *args) -> None:
        self._loop.call_soon_threadsafe(fn, *args)

    def _schedule(self) -> None:
        running = sum(1 for d in self._downloads.values() if d._task and not d._task.done())
        for d in sorted(self._downloads.values(), key=lambda d: d.rec.created_at):
            if running >= self.max_active:
                break
            if d.status == Status.QUEUED and not (d._task and not d._task.done()):
                d.start().add_done_callback(lambda _t: self._schedule())
                running += 1

    def _pause(self, download_id: int) -> None:
        d = self._downloads.get(download_id)
        if not d:
            return
        if d._task and not d._task.done():
            d.stop()
        elif d.status == Status.QUEUED:
            d.rec.status = Status.PAUSED
            self.store.update(d.rec)

    def _resume(self, download_id: int) -> None:
        d = self._downloads.get(download_id)
        if d and d.status in (Status.PAUSED, Status.ERROR) and not (d._task and not d._task.done()):
            d.rec.status = Status.QUEUED
            d.rec.error = None
            self.store.update(d.rec)
            self._schedule()

    async def _remove(self, download_id: int, delete_file: bool) -> None:
        d = self._downloads.get(download_id)
        if not d:
            return
        task = d._task
        if task and not task.done():
            d.stop()
            await asyncio.wait([task], timeout=5)
        with self._lock:
            self._downloads.pop(download_id, None)
        self.store.delete(download_id)
        if d.status != Status.COMPLETED and d.part_path and d.part_path.exists():
            d.part_path.unlink(missing_ok=True)
        if delete_file and d.status == Status.COMPLETED and d.final_path and d.final_path.exists():
            d.final_path.unlink(missing_ok=True)
        self._schedule()
