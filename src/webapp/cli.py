"""`minorh serve` — start the local workbench and open the browser.

Usage:
    minorh serve [--host H] [--port P] [--config PATH] [--no-browser]
    python -m src.webapp serve ...        (equivalent, no install needed)
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser

from src.flow.config import load_config


def _open_when_up(url: str) -> None:
    time.sleep(1.2)   # give uvicorn a moment to bind
    try:
        webbrowser.open(url)
    except Exception:
        pass


def serve(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="minorh serve")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--config", default=None)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    import uvicorn
    from src.webapp.server import create_app

    config = load_config(args.config)
    app = create_app(config)
    url = f"http://{args.host}:{args.port}/"

    print(f"minorh. title workbench -> {url}")
    print(f"  units:     {config.units_dir}")
    print(f"  manifests: {config.manifests_dir}")
    print(f"  project:   {config.project_root or '(unset — set project_root to enable SHIP)'}")
    print(f"  tesseract: {config.tesseract_status()}")
    if not args.no_browser:
        threading.Thread(target=_open_when_up, args=(url,), daemon=True).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "serve":
        return serve(rest)
    print(f"unknown command {cmd!r}; try: minorh serve")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
