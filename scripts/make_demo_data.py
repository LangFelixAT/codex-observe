from __future__ import annotations

import argparse
from pathlib import Path

from codex_observe.demo import (
    DEFAULT_DEMO_DB,
    DEFAULT_DEMO_SESSIONS,
    create_demo_database,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a synthetic Codex Observe demo database."
    )
    parser.add_argument("--out", default=DEFAULT_DEMO_DB, help="Output SQLite path.")
    parser.add_argument(
        "--sessions",
        default=DEFAULT_DEMO_SESSIONS,
        help="Directory for generated JSONL sessions.",
    )
    parser.add_argument(
        "--keep-sessions",
        action="store_true",
        help="Keep generated JSONL files after ingestion.",
    )
    args = parser.parse_args()

    result = create_demo_database(
        args.out, args.sessions, keep_sessions=args.keep_sessions
    )
    print(
        f"Created {Path(args.out)} with {result.files_imported} files, "
        f"{result.threads} threads, {result.events} events."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
