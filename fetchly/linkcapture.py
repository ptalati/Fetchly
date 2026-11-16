"""Decide whether copied text is a link to a downloadable file. No Qt.

    download_link(text) -> str | None
"""

from __future__ import annotations

import posixpath
import re
from urllib.parse import unquote, urlsplit

# Same buckets as the GUI categories in fetchly/gui/model.py, plus other common binaries.
VIDEO = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "mpg", "mpeg", "ts", "3gp", "ogv", "vob"}
AUDIO = {"mp3", "flac", "wav", "aac", "m4a", "ogg", "oga", "opus", "wma", "aiff", "ape", "mid", "midi"}
ARCHIVES = {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "tbz2", "txz", "iso", "zst", "lz", "lzma",
            "cab", "z", "img"}
PROGRAMS = {"exe", "msi", "msix", "appx", "dmg", "apk", "pkg", "deb", "rpm", "appimage", "jar", "bin",
            "run", "xpi", "crx", "vsix", "ipa", "whl"}
DOCUMENTS = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "rtf", "odt", "ods", "odp", "epub", "mobi",
             "azw3", "djvu", "psd", "ai"}
# "txt", "csv", "md" and "html" are left out on purpose: copied links to them are far more often
# pages or snippets people want to read than files they want to download.
TORRENT = {"torrent"}

DOWNLOAD_EXTENSIONS = VIDEO | AUDIO | ARCHIVES | PROGRAMS | DOCUMENTS | TORRENT

_WHITESPACE = re.compile(r"\s")


def extension_of(url: str) -> str:
    """Lower-case extension of the URL path ('' if none). 'x.tar.gz' gives 'gz'."""
    path = unquote(urlsplit(url).path)
    return posixpath.splitext(path)[1].lower().lstrip(".")


def download_link(text: str) -> str | None:
    """Return the URL if ``text`` is one http(s) URL whose path ends in a downloadable file type."""
    if not text:
        return None
    candidate = text.strip()
    if not candidate or len(candidate) > 4096 or _WHITESPACE.search(candidate):
        return None  # empty, huge, or more than a bare URL (a sentence, several links)
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    return candidate if extension_of(candidate) in DOWNLOAD_EXTENSIONS else None
