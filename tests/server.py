"""A small threaded HTTP file server with optional byte-range support and throttling.

Used by the tests; can also be run by hand for trying the GUI:
    python tests/server.py --size 50 --port 8765      (serves http://127.0.0.1:8765/file.bin)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


class RangeServer:
    def __init__(
        self,
        data: bytes,
        *,
        ranges: bool = True,
        chunk: int = 16 * 1024,
        delay: Callable[[int], float] | float = 0.0,
        filename: str = "file.bin",
        etag: str | None = '"v1"',
        fail_first: int = 0,
    ):
        self.data = data
        self.ranges = ranges
        self.chunk = chunk
        self.delay = delay
        self.filename = filename
        self.etag = etag
        self.fail_first = fail_first  # answer this many GETs with 503 first
        self.requests: list[tuple[str, str | None]] = []  # (method, Range header)
        self._lock = threading.Lock()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}/{self.filename}"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def start(self) -> "RangeServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def range_starts(self) -> list[int]:
        out = []
        for _, rng in self.requests:
            m = re.match(r"bytes=(\d+)-", rng or "")
            if m:
                out.append(int(m.group(1)))
        return out

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                rng = self.headers.get("Range")
                with server._lock:
                    server.requests.append(("GET", rng))
                    if server.fail_first > 0:
                        server.fail_first -= 1
                        self.send_response(503)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                data = server.data
                start, end = 0, len(data) - 1
                status = 200
                m = re.match(r"bytes=(\d+)-(\d*)$", rng or "")
                if server.ranges and m:
                    start = int(m.group(1))
                    end = min(int(m.group(2)) if m.group(2) else len(data) - 1, len(data) - 1)
                    if start >= len(data):
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{len(data)}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    status = 206
                self.send_response(status)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Content-Disposition", f'attachment; filename="{server.filename}"')
                if server.etag:
                    self.send_header("ETag", server.etag)
                if server.ranges:
                    self.send_header("Accept-Ranges", "bytes")
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.end_headers()
                delay = server.delay(start) if callable(server.delay) else server.delay
                pos = start
                try:
                    while pos <= end:
                        n = min(server.chunk, end - pos + 1)
                        self.wfile.write(data[pos: pos + n])
                        pos += n
                        if delay:
                            time.sleep(delay)
                except (ConnectionError, OSError):
                    pass

        return Handler


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=50, help="file size in MB")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--delay", type=float, default=0.002, help="seconds per 16 KB chunk, per connection")
    ap.add_argument("--no-ranges", action="store_true")
    a = ap.parse_args()
    srv = RangeServer(os.urandom(a.size * 1024 * 1024), ranges=not a.no_ranges, delay=a.delay)
    srv._httpd.server_close()
    srv._httpd = ThreadingHTTPServer(("127.0.0.1", a.port), srv._handler())
    srv._httpd.daemon_threads = True
    print(f"Serving {a.size} MB at http://127.0.0.1:{a.port}/file.bin  sha256={srv.sha256}", flush=True)
    srv._httpd.serve_forever()
