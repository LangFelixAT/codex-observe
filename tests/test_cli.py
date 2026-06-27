from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from codex_observe import cli


def dashboard_path() -> str:
    return str(Path(cli.__file__).with_name("dashboard.py"))


def test_serve_passes_host_and_port_to_streamlit_before_app_separator(tmp_path: Path) -> None:
    db = tmp_path / "observe.sqlite"

    with patch("codex_observe.cli.subprocess.call", return_value=0) as call:
        result = cli.main(["serve", "--host", "127.0.0.1", "--port", "9999", "--db", str(db)])

    assert result == 0
    call.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            dashboard_path(),
            "--server.address",
            "127.0.0.1",
            "--server.port",
            "9999",
            "--",
            "--db",
            str(db),
        ]
    )


def test_scan_and_serve_uses_same_streamlit_host_port_ordering(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    db = tmp_path / "observe.sqlite"

    with (
        patch("codex_observe.cli.ingest") as ingest,
        patch("codex_observe.cli.subprocess.call", return_value=0) as call,
    ):
        ingest.return_value.files_imported = 0
        ingest.return_value.duplicate_files = 0
        ingest.return_value.threads = 0
        ingest.return_value.events = 0
        result = cli.main(
            [
                "scan-and-serve",
                str(sessions),
                "--host",
                "0.0.0.0",
                "--port",
                "8502",
                "--db",
                str(db),
            ]
        )

    assert result == 0
    ingest.assert_called_once_with(str(sessions), str(db))
    call.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            dashboard_path(),
            "--server.address",
            "0.0.0.0",
            "--server.port",
            "8502",
            "--",
            "--db",
            str(db),
        ]
    )

def test_serve_passes_host_without_port_before_app_separator(tmp_path: Path) -> None:
    db = tmp_path / "observe.sqlite"

    with patch("codex_observe.cli.subprocess.call", return_value=0) as call:
        cli.main(["serve", "--host", "127.0.0.1", "--db", str(db)])

    call.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            dashboard_path(),
            "--server.address",
            "127.0.0.1",
            "--",
            "--db",
            str(db),
        ]
    )


def test_serve_passes_port_without_host_before_app_separator(tmp_path: Path) -> None:
    db = tmp_path / "observe.sqlite"

    with patch("codex_observe.cli.subprocess.call", return_value=0) as call:
        cli.main(["serve", "--port", "9999", "--db", str(db)])

    call.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            dashboard_path(),
            "--server.port",
            "9999",
            "--",
            "--db",
            str(db),
        ]
    )
