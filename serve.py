#!/usr/bin/env python3
"""Serve the built site locally from ./public. Does not deploy."""

from __future__ import annotations

import argparse
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the built site on localhost.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--directory",
        default=str(PUBLIC),
        help="Folder to serve (default: public/).",
    )
    args = parser.parse_args()
    directory = Path(args.directory)
    if not directory.exists():
        print(f"{directory} is missing. Run python build.py first.", file=sys.stderr)
        return 1
    # Binding to 127.0.0.1 keeps this local. Use --host 0.0.0.0 only if you
    # intentionally want other devices on your network to preview the draft.
    httpd = ThreadingHTTPServer((args.host, args.port), partial(Handler, directory=str(directory)))
    print(f"Serving {directory} at http://{args.host}:{args.port}/  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
