"""Fetchly download engine. Pure asyncio + httpx + sqlite3; no Qt imports allowed here."""

from .downloader import DEFAULT_CONNECTIONS, MAX_CONNECTIONS, Download, DownloadError, make_client
from .manager import DownloadManager
from .models import DownloadRecord, DownloadSnapshot, Segment, SegmentView, Status
from .probe import ProbeError, ProbeResult, probe
from .store import Store

__all__ = [
    "DEFAULT_CONNECTIONS", "MAX_CONNECTIONS", "Download", "DownloadError", "DownloadManager",
    "DownloadRecord", "DownloadSnapshot", "ProbeError", "ProbeResult", "Segment", "SegmentView",
    "Status", "Store", "make_client", "probe",
]
