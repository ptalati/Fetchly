"""Command line front end: ``python -m fetchly <url> -c 8 -o <folder>``."""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

from . import __version__
from .engine import DEFAULT_CONNECTIONS, MAX_CONNECTIONS, Download, DownloadRecord, Status, Store
from .util import default_db_path, default_download_dir, human_eta, human_size, human_speed


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fetchly", description="Multi-connection downloader.")
    p.add_argument("url", help="URL to download")
    p.add_argument("-c", "--connections", type=int, default=DEFAULT_CONNECTIONS,
                   help=f"parallel connections, 1-{MAX_CONNECTIONS} (default {DEFAULT_CONNECTIONS})")
    p.add_argument("-o", "--output", default=str(default_download_dir()), help="folder to save into")
    p.add_argument("--db", default=str(default_db_path()), help="state database (for resume)")
    p.add_argument("--version", action="version", version=f"Fetchly {__version__}")
    return p


def progress_line(d: Download, width: int) -> str:
    s = d.snapshot()
    pct = s.progress
    bar_w = 20
    if pct is None:
        bar, pct_txt = "?" * bar_w, "  ?  "
    else:
        filled = int(pct * bar_w)
        bar, pct_txt = "#" * filled + "-" * (bar_w - filled), f"{pct * 100:5.1f}%"
    txt = (f"{pct_txt} [{bar}] {human_size(s.downloaded)} / {human_size(s.size)}  "
           f"{human_speed(s.speed)}  ETA {human_eta(s.eta)}  conn {s.active_connections}/{s.connections}")
    return txt[: width - 1].ljust(width - 1)


async def _run(d: Download) -> Status:
    width = shutil.get_terminal_size((100, 20)).columns
    task = d.start()

    async def ticker():
        while True:
            sys.stdout.write("\r" + progress_line(d, width))
            sys.stdout.flush()
            await asyncio.sleep(0.25)

    t = asyncio.create_task(ticker())
    try:
        return await task
    finally:
        t.cancel()
        sys.stdout.write("\r" + progress_line(d, width) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    folder = str(Path(args.output).expanduser().resolve())
    store = Store(args.db)
    rec = store.find_unfinished(args.url, folder)
    if rec:
        print(f"Resuming {rec.filename or args.url} ({human_size(rec.downloaded)} already saved)")
        rec.connections = args.connections
    else:
        rec = DownloadRecord(url=args.url, folder=folder, connections=args.connections)
    d = Download(store, rec)
    try:
        status = asyncio.run(_run(d))
    except KeyboardInterrupt:
        print("\nPaused. Run the same command again to resume.")
        return 130
    finally:
        store.close()
    if status == Status.COMPLETED:
        print(f"Saved {d.final_path} ({human_size(rec.size)})")
        return 0
    print(f"Failed: {rec.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
