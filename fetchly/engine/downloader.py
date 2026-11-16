"""One download: parallel range segments written into a pre-allocated .part file.

Lifecycle: ``await Download.run()`` probes the URL, (re)builds the segment list,
starts up to ``connections`` workers and returns when the file is complete,
paused (``stop()``) or failed. Progress is saved to SQLite every half second,
so a later ``run()`` - even in a new process - picks up where it left off.
"""

from __future__ import annotations

import asyncio
import collections
import os
import time
from pathlib import Path
from typing import Callable

import httpx

from .models import DownloadRecord, DownloadSnapshot, Segment, SegmentView, Status
from .probe import ProbeError, ProbeResult, probe, unique_path
from .store import Store
from .prealloc import preallocate

MAX_CONNECTIONS = 16
DEFAULT_CONNECTIONS = 8
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
USER_AGENT = "Fetchly/0.1"


# Headers the engine owns; a browser-supplied copy would break ranges, decoding or framing.
_RESERVED_HEADERS = {"range", "if-range", "host", "content-length", "accept-encoding", "connection",
                     "transfer-encoding", "te", "upgrade", "proxy-authorization", "proxy-connection"}
# Credentials that must never follow a redirect to another host.
_ORIGIN_ONLY_HEADERS = {"cookie", "authorization"}


def clean_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """Keep only headers worth forwarding from a browser (drops ones the engine controls itself)."""
    out: dict[str, str] = {}
    for k, v in (headers or {}).items():
        k, v = str(k).strip(), str(v).strip()
        if k and v and k.lower() not in _RESERVED_HEADERS and "\n" not in k + v and "\r" not in k + v:
            out[k] = v
    return out


async def _strip_foreign_credentials(request: httpx.Request) -> None:
    """Request hook: Cookie/Authorization only go to the host the download was started from."""
    origin = request.extensions.get("fetchly_origin")
    if origin and request.url.host != origin:
        for name in list(request.headers):
            if name.lower() in _ORIGIN_ONLY_HEADERS:
                del request.headers[name]


class DownloadError(Exception):
    pass


class _Transient(Exception):
    """An error worth retrying (dropped connection, 5xx, short read)."""


def make_client(max_connections: int = MAX_CONNECTIONS) -> httpx.AsyncClient:
    # HTTP/1.1 on purpose: the speed-up comes from separate TCP connections,
    # which HTTP/2 would collapse into one multiplexed connection.
    return httpx.AsyncClient(
        http2=False,
        follow_redirects=True,
        timeout=httpx.Timeout(30.0, connect=15.0),
        limits=httpx.Limits(max_connections=max_connections + 2, max_keepalive_connections=max_connections),
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
        event_hooks={"request": [_strip_foreign_credentials]},
    )


class Download:
    def __init__(
        self,
        store: Store,
        record: DownloadRecord,
        *,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        chunk_size: int = 64 * 1024,
        min_split_size: int = 512 * 1024,
        max_retries: int = 6,
        backoff_base: float = 0.5,
        save_interval: float = 0.5,
    ):
        if record.id is None:
            store.add(record)
        record.connections = max(1, min(MAX_CONNECTIONS, record.connections))
        self.store = store
        self.rec = record
        self.client_factory = client_factory or (lambda: make_client(MAX_CONNECTIONS))
        self.chunk_size = chunk_size
        self.min_split_size = min_split_size
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.save_interval = save_interval

        self.splits = 0  # dynamic splits performed in the current run (for tests/diagnostics)
        self._fh = None
        self._url = record.url
        self._samples: collections.deque[tuple[float, int]] = collections.deque()
        self._stop_requested = False
        self._task: asyncio.Task | None = None

    # public --------------------------------------------------------------

    @property
    def id(self) -> int:
        return self.rec.id

    @property
    def status(self) -> Status:
        return self.rec.status

    @property
    def part_path(self) -> Path | None:
        return Path(self.rec.folder) / (self.rec.filename + ".part") if self.rec.filename else None

    @property
    def final_path(self) -> Path | None:
        return Path(self.rec.folder) / self.rec.filename if self.rec.filename else None

    def start(self) -> asyncio.Task:
        """Schedule ``run()`` on the running loop and remember the task so ``stop()`` can cancel it."""
        self._task = asyncio.get_running_loop().create_task(self.run())
        return self._task

    def stop(self) -> None:
        """Pause: cancel the running task; progress is saved on the way out."""
        self._stop_requested = True
        if self._task and not self._task.done():
            self._task.cancel()

    async def run(self) -> Status:
        if self._task is None:
            self._task = asyncio.current_task()
        self._stop_requested = False
        self.rec.error = None
        try:
            await self._run()
        except asyncio.CancelledError:
            self._set_status(Status.PAUSED)
            if not self._stop_requested:
                raise  # cancelled from outside (e.g. loop shutdown): still saved by `finally`
        except Exception as e:  # noqa: BLE001 - every failure ends up on the record
            self.rec.error = str(e) or e.__class__.__name__
            self._set_status(Status.ERROR)
        finally:
            for s in self.rec.segments:
                s.active = False
            self._close_file()
            self._samples.clear()
            self._task = None
            self._save()
        return self.rec.status

    def snapshot(self) -> DownloadSnapshot:
        rec = self.rec
        segs = tuple(SegmentView(s.start, s.end, s.downloaded, s.active) for s in list(rec.segments))
        speed = self.speed if rec.status.is_running else 0.0
        eta = None
        if speed > 0 and rec.size:
            eta = max(0.0, (rec.size - rec.downloaded) / speed)
        return DownloadSnapshot(
            id=rec.id, url=rec.url, folder=rec.folder, filename=rec.filename, size=rec.size,
            downloaded=rec.downloaded, status=rec.status, resumable=rec.resumable,
            connections=rec.connections, active_connections=sum(1 for s in segs if s.active),
            speed=speed, eta=eta, error=rec.error, created_at=rec.created_at,
            finished_at=rec.finished_at, segments=segs,
        )

    @property
    def speed(self) -> float:
        now = time.monotonic()
        while self._samples and now - self._samples[0][0] > 3.0:
            self._samples.popleft()
        if not self._samples:
            return 0.0
        span = max(now - self._samples[0][0], 0.5)
        return sum(b for _, b in self._samples) / span

    # core ----------------------------------------------------------------

    async def _run(self) -> None:
        rec = self.rec
        self._set_status(Status.CONNECTING)
        async with self.client_factory() as client:
            info = await self._with_retry(
                lambda: probe(client, rec.url, rec.headers, self._extensions()))
            self._url = info.final_url
            self._prepare(info)
            await asyncio.to_thread(self._open_file)  # allocation can be slow off NTFS
            self._set_status(Status.DOWNLOADING)

            n_workers = rec.connections if rec.resumable else 1
            workers = [asyncio.create_task(self._worker(client)) for _ in range(n_workers)]
            saver = asyncio.create_task(self._autosave())
            try:
                await asyncio.gather(*workers)
            finally:
                saver.cancel()
                for w in workers:
                    w.cancel()
                await asyncio.gather(*workers, saver, return_exceptions=True)
                if self._fh:
                    self._fh.flush()
                self._save()

        if not all(s.done for s in rec.segments):
            raise DownloadError("download ended with missing data")
        self._finish()

    def _extensions(self) -> dict:
        return {"fetchly_origin": httpx.URL(self.rec.url).host}

    def _prepare(self, info: ProbeResult) -> None:
        """Decide whether the saved segments can be reused, else lay out fresh ones."""
        rec = self.rec
        if rec.segments:
            same = (
                info.resumable
                and rec.resumable
                and info.size == rec.size
                and (not (rec.etag and info.etag) or rec.etag == info.etag)
                and (rec.etag or not (rec.last_modified and info.last_modified) or rec.last_modified == info.last_modified)
                and self.part_path is not None
                and self.part_path.exists()
            )
            if not same:
                rec.segments = []
                rec.downloaded = 0
                if self.part_path and self.part_path.exists():
                    self.part_path.unlink()
        if not rec.filename:
            Path(rec.folder).mkdir(parents=True, exist_ok=True)
            rec.filename = unique_path(rec.folder, info.filename).name
        rec.size, rec.resumable = info.size, info.resumable
        rec.etag, rec.last_modified = info.etag, info.last_modified
        if not rec.segments:
            rec.segments = self._layout()
        rec.downloaded = sum(s.downloaded for s in rec.segments)
        self._save()

    def _layout(self) -> list[Segment]:
        size = self.rec.size
        if not self.rec.resumable or not size:
            return [Segment(0, None if size is None else size - 1)]
        n = max(1, min(self.rec.connections, size // self.min_split_size or 1))
        step = size // n
        segs = []
        for i in range(n):
            start = i * step
            end = size - 1 if i == n - 1 else start + step - 1
            segs.append(Segment(start, end))
        return segs

    async def _worker(self, client: httpx.AsyncClient) -> None:
        while True:
            seg = self._next_segment()
            if seg is None:
                return
            seg.active = True
            try:
                await self._fetch(client, seg)
            finally:
                seg.active = False

    def _next_segment(self) -> Segment | None:
        """An idle unfinished segment, or else half of the largest active one."""
        for s in self.rec.segments:
            if not s.active and not s.done:
                return s
        if not self.rec.resumable:
            return None
        candidates = [s for s in self.rec.segments if s.active and (s.remaining or 0) >= 2 * self.min_split_size]
        if not candidates:
            return None
        big = max(candidates, key=lambda s: s.remaining)
        mid = big.pos + big.remaining // 2
        new = Segment(mid, big.end)
        big.end = mid - 1  # the worker on `big` notices the new end and stops there
        self.rec.segments.insert(self.rec.segments.index(big) + 1, new)
        self.splits += 1
        return new

    async def _fetch(self, client: httpx.AsyncClient, seg: Segment) -> None:
        attempt = 0
        while not seg.done:
            try:
                headers = dict(self.rec.headers)
                if self.rec.resumable:
                    headers["Range"] = f"bytes={seg.pos}-{seg.end}"
                elif seg.downloaded:
                    # No ranges: a retry has to start over.
                    self.rec.downloaded -= seg.downloaded
                    seg.downloaded = 0
                async with client.stream("GET", self._url, headers=headers, extensions=self._extensions()) as r:
                    if r.status_code in RETRYABLE_STATUS:
                        raise _Transient(f"HTTP {r.status_code}")
                    if r.status_code >= 400:
                        raise DownloadError(f"HTTP {r.status_code} {r.reason_phrase}")
                    if self.rec.resumable:
                        if r.status_code != 206:
                            raise DownloadError("server stopped honouring byte ranges")
                        cr = r.headers.get("content-range", "")
                        if not cr.replace(" ", "").lower().startswith(f"bytes{seg.pos}-"):
                            raise _Transient(f"unexpected Content-Range: {cr!r}")
                    async for chunk in r.aiter_raw(self.chunk_size):
                        if seg.end is not None:
                            room = seg.end - seg.pos + 1
                            if room <= 0:
                                break
                            if len(chunk) > room:
                                chunk = chunk[:room]
                        self._write(seg.pos, chunk)
                        seg.downloaded += len(chunk)
                        self.rec.downloaded += len(chunk)
                        self._samples.append((time.monotonic(), len(chunk)))
                        attempt = 0
                        if seg.done:
                            break
                if seg.end is None:
                    # Unknown size: EOF marks the end.
                    seg.end = seg.pos - 1
                    self.rec.size = seg.pos
                elif not seg.done:
                    raise _Transient("connection closed early")
            except (httpx.TransportError, _Transient) as e:
                attempt += 1
                if attempt > self.max_retries:
                    raise DownloadError(f"gave up after {self.max_retries} retries: {e}") from e
                await asyncio.sleep(min(self.backoff_base * 2 ** (attempt - 1), 15.0))

    async def _with_retry(self, fn):
        attempt = 0
        while True:
            try:
                return await fn()
            except (httpx.TransportError, ProbeError) as e:
                if isinstance(e, ProbeError) and e.status not in RETRYABLE_STATUS:
                    raise
                attempt += 1
                if attempt > self.max_retries:
                    raise DownloadError(f"could not connect: {e}") from e
                await asyncio.sleep(min(self.backoff_base * 2 ** (attempt - 1), 15.0))

    async def _autosave(self) -> None:
        while True:
            await asyncio.sleep(self.save_interval)
            if self._fh:
                self._fh.flush()  # data must reach the OS before progress claims it
            self._save()

    # files ---------------------------------------------------------------

    def _open_file(self) -> None:
        path = self.part_path
        self._fh = open(path, "r+b" if path.exists() else "w+b")
        if self.rec.size is not None and self.rec.resumable:
            self._fh.seek(0, os.SEEK_END)
            if self._fh.tell() != self.rec.size:
                preallocate(self._fh, self.rec.size)

    def _write(self, offset: int, data: bytes) -> None:
        self._fh.seek(offset)
        self._fh.write(data)

    def _close_file(self) -> None:
        if self._fh:
            try:
                self._fh.flush()
                self._fh.close()
            finally:
                self._fh = None

    def _finish(self) -> None:
        self._close_file()
        final = self.final_path
        if final.exists():
            final = unique_path(self.rec.folder, self.rec.filename, also_avoid_suffix="")
        os.replace(self.part_path, final)
        self.rec.filename = final.name
        self.rec.size = self.rec.downloaded
        self.rec.finished_at = time.time()
        self._set_status(Status.COMPLETED)

    # state ---------------------------------------------------------------

    def _set_status(self, status: Status) -> None:
        self.rec.status = status

    def _save(self) -> None:
        self.store.save(self.rec)
