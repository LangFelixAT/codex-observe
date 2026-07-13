from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path


def scalar(conn: sqlite3.Connection, query: str) -> int:
    return int(conn.execute(query).fetchone()[0])


def test_make_demo_data_creates_representative_database(tmp_path: Path) -> None:
    db = tmp_path / "demo.sqlite"
    sessions = tmp_path / "sessions"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/make_demo_data.py",
            "--out",
            str(db),
            "--sessions",
            str(sessions),
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )

    assert "Created" in result.stdout
    assert db.exists()
    assert not sessions.exists()
    with sqlite3.connect(db) as conn:
        assert scalar(conn, "SELECT COUNT(*) FROM conversations") == 2
        assert scalar(conn, "SELECT COUNT(*) FROM threads") == 6
        assert scalar(conn, "SELECT COUNT(*) FROM usage_snapshots") >= 9
        assert scalar(conn, "SELECT COUNT(*) FROM tool_calls") >= 3
        assert scalar(conn, "SELECT COUNT(*) FROM prompt_blocks") >= 3
        assert (
            scalar(conn, "SELECT COUNT(*) FROM threads WHERE agent_role='guardian'")
            == 2
        )
        assert (
            scalar(
                conn,
                "SELECT COUNT(*) FROM events WHERE payload_type='context_compacted'",
            )
            == 1
        )
