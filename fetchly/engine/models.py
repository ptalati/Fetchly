"""Plain data types shared by the engine, the CLI and the GUI. No Qt here."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    QUEUED = "queued"
    CONNECTING = "connecting"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"

    @property
    def is_running(self) -> bool:
        return self in (Status.CONNECTING, Status.DOWNLOADING)


@dataclass
class Segment:
    """A byte range [start, end] (inclusive) of the file.

    ``end`` is None when the total size is unknown (single connection, read to EOF).
    ``downloaded`` counts bytes written from ``start``.
    """

    start: int
    end: int | None
    downloaded: int = 0
    active: bool = False  # runtime only, not persisted

    @property
    def pos(self) -> int:
        return self.start + self.downloaded

    @property
    def length(self) -> int | None:
        return None if self.end is None else self.end - self.start + 1

    @property
    def remaining(self) -> int | None:
        return None if self.end is None else max(0, self.end - self.pos + 1)

    @property
    def done(self) -> bool:
        return self.end is not None and self.pos > self.end


@dataclass
class DownloadRecord:
    """Everything persisted about one download."""

    url: str
    folder: str
    connections: int = 8
    id: int | None = None
    filename: str | None = None
    size: int | None = None
    resumable: bool = False
    etag: str | None = None
    last_modified: str | None = None
    status: Status = Status.QUEUED
    downloaded: int = 0
    error: str | None = None
    created_at: float = 0.0
    finished_at: float | None = None
    segments: list[Segment] = field(default_factory=list)
    # Extra request headers (Cookie, Referer, User-Agent...) sent on the probe and every segment request.
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SegmentView:
    start: int
    end: int | None
    downloaded: int
    active: bool


@dataclass(frozen=True)
class DownloadSnapshot:
    """An immutable copy of a download's state, safe to hand to another thread."""

    id: int
    url: str
    folder: str
    filename: str | None
    size: int | None
    downloaded: int
    status: Status
    resumable: bool
    connections: int
    active_connections: int
    speed: float  # bytes/s
    eta: float | None  # seconds
    error: str | None
    created_at: float
    finished_at: float | None
    segments: tuple[SegmentView, ...]

    @property
    def progress(self) -> float | None:
        if not self.size:
            return 1.0 if self.status == Status.COMPLETED else None
        return min(1.0, self.downloaded / self.size)
