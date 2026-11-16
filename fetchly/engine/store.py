"""SQLite persistence for downloads, their segments and app settings."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from .models import DownloadRecord, Segment, Status

SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    folder TEXT NOT NULL,
    filename TEXT,
    size INTEGER,
    resumable INTEGER NOT NULL DEFAULT 0,
    etag TEXT,
    last_modified TEXT,
    connections INTEGER NOT NULL DEFAULT 8,
    status TEXT NOT NULL,
    downloaded INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at REAL NOT NULL,
    finished_at REAL
);
CREATE TABLE IF NOT EXISTS segments (
    download_id INTEGER NOT NULL REFERENCES downloads(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start INTEGER NOT NULL,
    "end" INTEGER,
    downloaded INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (download_id, idx)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

_FIELDS = (
    "url", "folder", "filename", "size", "resumable", "etag", "last_modified",
    "connections", "status", "downloaded", "error", "created_at", "finished_at",
)


class Store:
    """Thread-safe wrapper around one SQLite connection."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # downloads -----------------------------------------------------------

    def add(self, rec: DownloadRecord) -> int:
        if not rec.created_at:
            rec.created_at = time.time()
        values = self._values(rec)
        with self._lock:
            cur = self._db.execute(
                f"INSERT INTO downloads ({', '.join(_FIELDS)}) VALUES ({', '.join('?' * len(_FIELDS))})",
                values,
            )
            rec.id = cur.lastrowid
        if rec.segments:
            self.save_segments(rec.id, rec.segments)
        return rec.id

    def update(self, rec: DownloadRecord) -> None:
        with self._lock:
            self._db.execute(
                f"UPDATE downloads SET {', '.join(f'{f}=?' for f in _FIELDS)} WHERE id=?",
                (*self._values(rec), rec.id),
            )

    def save(self, rec: DownloadRecord) -> None:
        """Update the download row and replace its segments in one transaction."""
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._db.execute(
                    f"UPDATE downloads SET {', '.join(f'{f}=?' for f in _FIELDS)} WHERE id=?",
                    (*self._values(rec), rec.id),
                )
                self._write_segments(rec.id, rec.segments)
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def save_segments(self, download_id: int, segments: list[Segment]) -> None:
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._write_segments(download_id, segments)
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def _write_segments(self, download_id: int, segments: list[Segment]) -> None:
        self._db.execute("DELETE FROM segments WHERE download_id=?", (download_id,))
        self._db.executemany(
            'INSERT INTO segments (download_id, idx, start, "end", downloaded) VALUES (?, ?, ?, ?, ?)',
            [(download_id, i, s.start, s.end, s.downloaded) for i, s in enumerate(segments)],
        )

    def get(self, download_id: int) -> DownloadRecord | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM downloads WHERE id=?", (download_id,)).fetchone()
            if row is None:
                return None
            return self._record(row)

    def all(self) -> list[DownloadRecord]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM downloads ORDER BY id").fetchall()
            return [self._record(r) for r in rows]

    def find_unfinished(self, url: str, folder: str) -> DownloadRecord | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM downloads WHERE url=? AND folder=? AND status!=? ORDER BY id DESC LIMIT 1",
                (url, folder, Status.COMPLETED.value),
            ).fetchone()
            return self._record(row) if row else None

    def delete(self, download_id: int) -> None:
        with self._lock:
            self._db.execute("DELETE FROM downloads WHERE id=?", (download_id,))

    # settings ------------------------------------------------------------

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    # helpers -------------------------------------------------------------

    @staticmethod
    def _values(rec: DownloadRecord) -> tuple:
        return (
            rec.url, rec.folder, rec.filename, rec.size, int(rec.resumable), rec.etag,
            rec.last_modified, rec.connections, rec.status.value, rec.downloaded, rec.error,
            rec.created_at, rec.finished_at,
        )

    def _record(self, row: sqlite3.Row) -> DownloadRecord:
        segs = self._db.execute(
            'SELECT start, "end", downloaded FROM segments WHERE download_id=? ORDER BY idx',
            (row["id"],),
        ).fetchall()
        return DownloadRecord(
            id=row["id"],
            url=row["url"],
            folder=row["folder"],
            filename=row["filename"],
            size=row["size"],
            resumable=bool(row["resumable"]),
            etag=row["etag"],
            last_modified=row["last_modified"],
            connections=row["connections"],
            status=Status(row["status"]),
            downloaded=row["downloaded"],
            error=row["error"],
            created_at=row["created_at"],
            finished_at=row["finished_at"],
            segments=[Segment(s["start"], s["end"], s["downloaded"]) for s in segs],
        )
