from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .parser import ingest


def default_db() -> str:
    return str(Path.home() / ".codex-observe" / "codex_observe.sqlite")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codex-observe", description="Offline observability for Codex JSONL session logs")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest Codex JSONL files into SQLite")
    p_ingest.add_argument("sessions_path", nargs="?", default=str(Path.home() / ".codex" / "sessions"))
    p_ingest.add_argument("--db", default=default_db())

    p_serve = sub.add_parser("serve", help="Launch the Streamlit dashboard")
    p_serve.add_argument("--db", default=default_db())
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", default=None)

    p_scan = sub.add_parser("scan-and-serve", help="Ingest then launch the dashboard")
    p_scan.add_argument("sessions_path", nargs="?", default=str(Path.home() / ".codex" / "sessions"))
    p_scan.add_argument("--db", default=default_db())
    p_scan.add_argument("--host", default=None)
    p_scan.add_argument("--port", default=None)

    args = parser.parse_args(argv)
    if args.cmd in {"ingest", "scan-and-serve"}:
        Path(args.db).expanduser().parent.mkdir(parents=True, exist_ok=True)
        result = ingest(args.sessions_path, args.db)
        print(
            f"Imported {result.files_imported} JSONL files "
            f"({result.duplicate_files} duplicates skipped), "
            f"{result.threads} threads, {result.events} events into {args.db}"
        )
        if args.cmd == "ingest":
            return 0

    app_path = Path(__file__).with_name("dashboard.py")
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path), "--", "--db", args.db]
    if args.host:
        cmd.extend(["--server.address", args.host])
    if args.port:
        cmd.extend(["--server.port", str(args.port)])
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
