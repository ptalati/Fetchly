"""Find out what the server offers before downloading: size, range support, name, validators."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class ProbeError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class ProbeResult:
    final_url: str
    size: int | None
    resumable: bool
    filename: str
    etag: str | None
    last_modified: str | None


async def probe(client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None,
                extensions: dict | None = None) -> ProbeResult:
    """GET with ``Range: bytes=0-0``; a 206 answer means byte ranges work.

    GET is used instead of HEAD because many servers answer HEAD incorrectly.
    Only the headers are read; the body is not consumed.
    """
    async with client.stream("GET", url, headers={**(headers or {}), "Range": "bytes=0-0"},
                             extensions=extensions) as r:
        if r.status_code >= 400:
            raise ProbeError(f"HTTP {r.status_code} {r.reason_phrase}", r.status_code)
        size: int | None = None
        resumable = False
        if r.status_code == 206:
            total = _content_range_total(r.headers.get("content-range"))
            if total is not None:
                size, resumable = total, True
        else:
            cl = r.headers.get("content-length")
            if cl and cl.isdigit() and not r.headers.get("content-encoding"):
                size = int(cl)
        return ProbeResult(
            final_url=str(r.url),
            size=size,
            resumable=resumable,
            filename=filename_from(r.headers.get("content-disposition"), str(r.url)),
            etag=r.headers.get("etag"),
            last_modified=r.headers.get("last-modified"),
        )


def _content_range_total(value: str | None) -> int | None:
    # "bytes 0-0/12345"
    if not value:
        return None
    m = re.match(r"\s*bytes\s+\d+-\d+/(\d+)\s*$", value, re.I)
    return int(m.group(1)) if m else None


def filename_from(content_disposition: str | None, url: str) -> str:
    name = None
    if content_disposition:
        m = re.search(r"filename\*\s*=\s*([^']*)'[^']*'([^;]+)", content_disposition, re.I)
        if m:
            name = unquote(m.group(2).strip().strip('"'), encoding=m.group(1) or "utf-8", errors="replace")
        else:
            m = re.search(r'filename\s*=\s*"([^"]+)"', content_disposition, re.I) or re.search(
                r"filename\s*=\s*([^;]+)", content_disposition, re.I
            )
            if m:
                name = m.group(1).strip()
    if not name:
        name = unquote(os.path.basename(urlsplit(url).path))
    return sanitize_filename(name)


def sanitize_filename(name: str) -> str:
    name = os.path.basename(name.replace("\\", "/"))
    name = _INVALID_CHARS.sub("_", name).strip().rstrip(". ")
    if not name:
        name = "download"
    if Path(name).stem.upper() in _RESERVED:
        name = "_" + name
    return name[:200]


def unique_path(folder: str | Path, filename: str, also_avoid_suffix: str = ".part") -> Path:
    """Return folder/filename, or 'name (1).ext' etc. if it (or its .part) already exists."""
    folder = Path(folder)
    stem, ext = os.path.splitext(filename)
    stem2, ext2 = os.path.splitext(stem)
    if ext2.lower() == ".tar":  # keep 'name (1).tar.gz', not 'name.tar (1).gz'
        stem, ext = stem2, ext2 + ext
    candidate = folder / filename
    n = 1
    while candidate.exists() or (also_avoid_suffix and Path(str(candidate) + also_avoid_suffix).exists()):
        candidate = folder / f"{stem} ({n}){ext}"
        n += 1
    return candidate
