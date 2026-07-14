from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from codex_observe.parser import CodexIngestor, ingest


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def rows_for_session(
    *,
    thread_id: str = "thread-root",
    session_id: str = "session-1",
    parent_thread_id: str | None = None,
    agent_role: str | None = None,
    agent_nickname: str = "",
    user_text: str = "Please inspect the repo.",
    assistant_text: str = "I will inspect it.",
    input_tokens: int = 120,
    cached_input_tokens: int = 40,
    output_tokens: int = 30,
    reasoning_tokens: int = 10,
    total_tokens: int = 160,
    tool_call_id: str = "call-1",
) -> list[dict[str, Any]]:
    source: dict[str, Any] | str = "root"
    if parent_thread_id:
        source = {
            "subagent": {
                "thread_spawn": {
                    "agent_role": agent_role or "worker",
                    "agent_nickname": agent_nickname,
                }
            }
        }
    return [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": thread_id,
                "session_id": session_id,
                "parent_thread_id": parent_thread_id,
                "source": source,
                "thread_source": "subagent" if parent_thread_id else "root",
                "cwd": "D:/repo",
                "cli_version": "0.1.0",
                "model_provider": "openai",
                "timestamp": "2026-01-01T00:00:00Z",
            },
        },
        {
            "timestamp": "2026-01-01T00:01:00Z",
            "type": "event",
            "payload": {
                "type": "message",
                "role": "user",
                "content": user_text,
                "turn_id": "turn-1",
            },
        },
        {
            "timestamp": "2026-01-01T00:02:00Z",
            "type": "event",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": assistant_text,
                "turn_id": "turn-1",
            },
        },
        {
            "timestamp": "2026-01-01T00:03:00Z",
            "type": "event",
            "payload": {
                "type": "token_count",
                "turn_id": "turn-1",
                "info": {
                    "total_token_usage": {
                        "input_tokens": input_tokens,
                        "cached_input_tokens": cached_input_tokens,
                        "output_tokens": output_tokens,
                        "reasoning_output_tokens": reasoning_tokens,
                        "total_tokens": total_tokens,
                    },
                    "last_token_usage": {
                        "input_tokens": 20,
                        "cached_input_tokens": 5,
                        "output_tokens": 7,
                        "reasoning_output_tokens": 3,
                        "total_tokens": 30,
                    },
                    "model_context_window": 200000,
                },
            },
        },
        {
            "timestamp": "2026-01-01T00:04:00Z",
            "type": "event",
            "payload": {
                "type": "function_call",
                "call_id": tool_call_id,
                "name": "shell_command",
                "arguments": json.dumps(
                    {
                        "command": "Get-ChildItem",
                        "workdir": "D:/repo",
                        "timeout_ms": 1000,
                    }
                ),
                "turn_id": "turn-1",
            },
        },
        {
            "timestamp": "2026-01-01T00:05:00Z",
            "type": "event",
            "payload": {
                "type": "function_call_output",
                "call_id": tool_call_id,
                "output": "listed files",
                "turn_id": "turn-1",
            },
        },
    ]


def scalar(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> Any:
    return conn.execute(query, params).fetchone()[0]


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_ingests_minimal_root_session_and_reingests_without_duplicates(
    tmp_path: Path,
) -> None:
    session = tmp_path / "root.jsonl"
    db = tmp_path / "observe.sqlite"
    write_jsonl(session, rows_for_session())

    result = ingest(str(session), str(db))
    again = ingest(str(session), str(db))

    assert result.files_imported == 1
    assert result.threads == 1
    assert result.events == 6
    assert again.files_imported == 1

    with open_db(db) as conn:
        assert scalar(conn, "SELECT COUNT(*) FROM files") == 1
        assert scalar(conn, "SELECT COUNT(*) FROM conversations") == 1
        assert scalar(conn, "SELECT COUNT(*) FROM threads") == 1
        assert scalar(conn, "SELECT COUNT(*) FROM events") == 6
        assert scalar(conn, "SELECT COUNT(*) FROM usage_snapshots") == 1
        assert scalar(conn, "SELECT COUNT(*) FROM tool_calls") == 1
        assert scalar(conn, "SELECT COUNT(*) FROM messages") == 2
        thread = conn.execute(
            "SELECT * FROM threads WHERE thread_id='thread-root'"
        ).fetchone()
        conv = conn.execute(
            "SELECT * FROM conversations WHERE session_id='session-1'"
        ).fetchone()
        assert thread["final_input_tokens"] == 120
        assert thread["final_cached_input_tokens"] == 40
        assert thread["final_uncached_input_tokens"] == 80
        assert thread["final_output_tokens"] == 30
        assert thread["final_reasoning_tokens"] == 10
        assert thread["final_total_tokens"] == 160
        assert conv["total_input_tokens"] == 120
        assert conv["total_cached_input_tokens"] == 40
        assert conv["total_uncached_input_tokens"] == 80
        assert conv["total_output_tokens"] == 30
        assert conv["total_reasoning_tokens"] == 10
        assert conv["total_tokens"] == 160
        tool = conn.execute("SELECT * FROM tool_calls").fetchone()
        assert tool["tool_name"] == "shell_command"
        assert tool["command"] == "Get-ChildItem"
        assert tool["workdir"] == "D:/repo"
        assert tool["timeout_ms"] == 1000
        assert tool["output"] == "listed files"
        assert tool["output_chars"] == len("listed files")


def test_duplicate_paths_and_same_path_reimport_are_deterministic(
    tmp_path: Path,
) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    canonical = sessions / "a.jsonl"
    duplicate = sessions / "b.jsonl"
    db = tmp_path / "observe.sqlite"
    original = rows_for_session(
        input_tokens=100,
        cached_input_tokens=25,
        output_tokens=10,
        reasoning_tokens=5,
        total_tokens=115,
    )
    write_jsonl(canonical, original)
    write_jsonl(duplicate, original)

    result = ingest(str(sessions), str(db))

    assert result.files_imported == 1
    assert result.duplicate_files == 1
    with open_db(db) as conn:
        assert scalar(conn, "SELECT COUNT(*) FROM files") == 2
        dup = conn.execute("SELECT * FROM files WHERE is_duplicate=1").fetchone()
        assert dup["path"] == str(duplicate.resolve())
        assert dup["duplicate_of"] == str(canonical.resolve())
        assert scalar(conn, "SELECT COUNT(*) FROM events") == 6
        assert (
            scalar(
                conn,
                "SELECT total_tokens FROM conversations WHERE session_id='session-1'",
            )
            == 115
        )

    duplicate.unlink()
    updated = rows_for_session(
        user_text="A changed prompt",
        assistant_text="A changed answer",
        input_tokens=220,
        cached_input_tokens=20,
        output_tokens=50,
        reasoning_tokens=30,
        total_tokens=300,
    )
    write_jsonl(canonical, updated)
    result = ingest(str(canonical), str(db))

    assert result.files_imported == 1
    with open_db(db) as conn:
        assert (
            scalar(
                conn,
                "SELECT COUNT(*) FROM files WHERE path=?",
                (str(canonical.resolve()),),
            )
            == 1
        )
        assert (
            scalar(conn, "SELECT COUNT(*) FROM threads WHERE thread_id='thread-root'")
            == 1
        )
        assert (
            scalar(conn, "SELECT COUNT(*) FROM messages WHERE thread_id='thread-root'")
            == 2
        )
        assert (
            scalar(conn, "SELECT text FROM messages WHERE role='user'")
            == "A changed prompt"
        )
        assert (
            scalar(
                conn,
                "SELECT total_tokens FROM conversations WHERE session_id='session-1'",
            )
            == 300
        )
        assert (
            scalar(
                conn,
                "SELECT final_uncached_input_tokens FROM threads WHERE thread_id='thread-root'",
            )
            == 200
        )


def test_empty_and_missing_session_meta_files_do_not_create_partial_rows(
    tmp_path: Path,
) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "empty.jsonl").write_text("", encoding="utf-8")
    write_jsonl(
        sessions / "events-only.jsonl",
        [
            {
                "type": "event",
                "payload": {"type": "message", "role": "user", "content": "hello"},
            }
        ],
    )
    db = tmp_path / "observe.sqlite"

    result = ingest(str(sessions), str(db))

    assert result.files_seen == 2
    assert result.files_imported == 0
    assert result.empty_files == 1
    assert result.missing_meta_files == 1
    with open_db(db) as conn:
        for table in [
            "files",
            "conversations",
            "threads",
            "events",
            "messages",
            "usage_snapshots",
            "tool_calls",
        ]:
            assert scalar(conn, f"SELECT COUNT(*) FROM {table}") == 0


def test_supported_tool_call_and_output_shapes_are_normalized(tmp_path: Path) -> None:
    session = tmp_path / "tools.jsonl"
    db = tmp_path / "observe.sqlite"
    rows = rows_for_session(tool_call_id="fn-1")[:1] + [
        {
            "timestamp": "2026-01-01T00:01:00Z",
            "type": "event",
            "payload": {
                "type": "function_call",
                "call_id": "fn-1",
                "name": "shell_command",
                "arguments": "{not-json",
                "turn_id": "turn-tools",
            },
        },
        {
            "timestamp": "2026-01-01T00:02:00Z",
            "type": "event",
            "payload": {
                "type": "function_call_output",
                "call_id": "fn-1",
                "output": {"ok": True},
                "turn_id": "turn-tools",
            },
        },
        {
            "timestamp": "2026-01-01T00:03:00Z",
            "type": "event",
            "payload": {
                "type": "custom_tool_call",
                "call_id": "custom-1",
                "name": "apply_patch",
                "input": "*** Begin Patch",
                "turn_id": "turn-tools",
            },
        },
        {
            "timestamp": "2026-01-01T00:04:00Z",
            "type": "event",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "custom-1",
                "content": "patched",
                "turn_id": "turn-tools",
            },
        },
        {
            "timestamp": "2026-01-01T00:05:00Z",
            "type": "event",
            "payload": {
                "type": "tool_search_call",
                "call_id": "search-1",
                "query": "needle",
                "turn_id": "turn-tools",
            },
        },
        {
            "timestamp": "2026-01-01T00:06:00Z",
            "type": "event",
            "payload": {
                "type": "tool_search_output",
                "call_id": "search-1",
                "output": ["hit"],
                "turn_id": "turn-tools",
            },
        },
        {
            "timestamp": "2026-01-01T00:07:00Z",
            "type": "event",
            "payload": {
                "type": "custom_tool_call",
                "call_id": "patch-1",
                "name": "apply_patch",
                "arguments": ["not", "a", "string"],
                "turn_id": "turn-tools",
            },
        },
        {
            "timestamp": "2026-01-01T00:08:00Z",
            "type": "event",
            "payload": {
                "type": "patch_apply_end",
                "call_id": "patch-1",
                "stdout": "done",
                "stderr": "",
                "success": True,
                "turn_id": "turn-tools",
            },
        },
    ]
    write_jsonl(session, rows)

    result = ingest(str(session), str(db))

    assert result.files_imported == 1
    with open_db(db) as conn:
        calls = {
            row["call_id"]: row
            for row in conn.execute("SELECT * FROM tool_calls ORDER BY call_id")
        }
        assert set(calls) == {"fn-1", "custom-1", "search-1", "patch-1"}
        assert json.loads(calls["fn-1"]["arguments_json"]) == {"_raw": "{not-json"}
        assert calls["fn-1"]["output"] == '{"ok":true}'
        assert calls["fn-1"]["output_chars"] == len('{"ok":true}')
        assert calls["custom-1"]["tool_name"] == "apply_patch"
        assert calls["custom-1"]["command"] == "*** Begin Patch"
        assert calls["custom-1"]["output"] == "patched"
        assert calls["search-1"]["tool_name"] == "tool_search"
        assert calls["search-1"]["command"] == "needle"
        assert calls["search-1"]["output"] == '["hit"]'
        assert json.loads(calls["patch-1"]["arguments_json"]) == {
            "input": ["not", "a", "string"]
        }
        assert calls["patch-1"]["output"] == "done"
        assert calls["patch-1"]["success"] == 1


def test_previously_unique_path_becoming_duplicate_removes_stale_thread_rows(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical.jsonl"
    changing = tmp_path / "changing.jsonl"
    db = tmp_path / "observe.sqlite"
    canonical_rows = rows_for_session(
        thread_id="canonical-thread", session_id="canonical-session", total_tokens=100
    )
    old_unique_rows = rows_for_session(
        thread_id="old-thread", session_id="old-session", total_tokens=900
    )
    write_jsonl(canonical, canonical_rows)
    write_jsonl(changing, old_unique_rows)
    ingest(str(canonical), str(db))
    ingest(str(changing), str(db))

    write_jsonl(changing, canonical_rows)
    result = ingest(str(changing), str(db))

    assert result.files_imported == 0
    assert result.duplicate_files == 1
    with open_db(db) as conn:
        assert scalar(conn, "SELECT COUNT(*) FROM files") == 2
        assert (
            scalar(
                conn,
                "SELECT is_duplicate FROM files WHERE path=?",
                (str(changing.resolve()),),
            )
            == 1
        )
        assert scalar(
            conn,
            "SELECT duplicate_of FROM files WHERE path=?",
            (str(changing.resolve()),),
        ) == str(canonical.resolve())
        assert (
            scalar(conn, "SELECT COUNT(*) FROM threads WHERE thread_id='old-thread'")
            == 0
        )
        assert (
            scalar(conn, "SELECT COUNT(*) FROM events WHERE thread_id='old-thread'")
            == 0
        )
        assert (
            scalar(
                conn,
                "SELECT COUNT(*) FROM conversations WHERE session_id='old-session'",
            )
            == 0
        )
        assert (
            scalar(
                conn,
                "SELECT total_tokens FROM conversations WHERE session_id='canonical-session'",
            )
            == 100
        )


def test_directory_reimport_does_not_let_stale_duplicate_overwrite_changed_canonical(
    tmp_path: Path,
) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    canonical = sessions / "a.jsonl"
    duplicate = sessions / "b.jsonl"
    db = tmp_path / "observe.sqlite"
    original = rows_for_session(
        thread_id="thread-root", session_id="session-1", total_tokens=100
    )
    write_jsonl(canonical, original)
    write_jsonl(duplicate, original)
    ingest(str(sessions), str(db))

    updated = rows_for_session(
        thread_id="thread-root",
        session_id="session-1",
        user_text="updated canonical prompt",
        input_tokens=300,
        cached_input_tokens=50,
        output_tokens=60,
        reasoning_tokens=40,
        total_tokens=400,
    )
    write_jsonl(canonical, updated)
    result = ingest(str(sessions), str(db))

    assert result.files_imported == 1
    assert result.duplicate_files == 1
    with open_db(db) as conn:
        assert (
            scalar(
                conn,
                "SELECT total_tokens FROM conversations WHERE session_id='session-1'",
            )
            == 400
        )
        assert (
            scalar(
                conn,
                "SELECT final_total_tokens FROM threads WHERE thread_id='thread-root'",
            )
            == 400
        )
        assert (
            scalar(conn, "SELECT text FROM messages WHERE role='user'")
            == "updated canonical prompt"
        )
        assert (
            scalar(
                conn,
                "SELECT is_duplicate FROM files WHERE path=?",
                (str(duplicate.resolve()),),
            )
            == 1
        )


def test_falsey_tool_outputs_are_preserved(tmp_path: Path) -> None:
    session = tmp_path / "falsey-tools.jsonl"
    db = tmp_path / "observe.sqlite"
    rows = rows_for_session(tool_call_id="zero-call")[:1] + [
        {
            "timestamp": "2026-01-01T00:01:00Z",
            "type": "event",
            "payload": {
                "type": "function_call",
                "call_id": "zero-call",
                "name": "zero",
                "arguments": "{}",
            },
        },
        {
            "timestamp": "2026-01-01T00:02:00Z",
            "type": "event",
            "payload": {
                "type": "function_call_output",
                "call_id": "zero-call",
                "output": 0,
                "content": "fallback",
            },
        },
        {
            "timestamp": "2026-01-01T00:03:00Z",
            "type": "event",
            "payload": {
                "type": "tool_search_call",
                "call_id": "empty-list",
                "query": "none",
            },
        },
        {
            "timestamp": "2026-01-01T00:04:00Z",
            "type": "event",
            "payload": {
                "type": "tool_search_output",
                "call_id": "empty-list",
                "output": [],
                "content": "fallback",
            },
        },
    ]
    write_jsonl(session, rows)

    ingest(str(session), str(db))

    with open_db(db) as conn:
        assert (
            scalar(conn, "SELECT output FROM tool_calls WHERE call_id='zero-call'")
            == "0"
        )
        assert (
            scalar(
                conn, "SELECT output_chars FROM tool_calls WHERE call_id='zero-call'"
            )
            == 1
        )
        assert (
            scalar(conn, "SELECT output FROM tool_calls WHERE call_id='empty-list'")
            == "[]"
        )
        assert (
            scalar(
                conn, "SELECT output_chars FROM tool_calls WHERE call_id='empty-list'"
            )
            == 2
        )


def test_openai_style_usage_payload_is_normalized_and_raw_payload_is_retained(
    tmp_path: Path,
) -> None:
    session = tmp_path / "usage-shape.jsonl"
    db = tmp_path / "observe.sqlite"
    rows = rows_for_session()[:1] + [
        {
            "timestamp": "2026-01-01T00:01:00Z",
            "type": "event",
            "payload": {
                "type": "token_count",
                "turn_id": "turn-openai-usage",
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 120,
                    "total_tokens": 1160,
                    "input_token_details": {"cached_tokens": 400},
                    "output_token_details": {"reasoning_tokens": 40},
                },
                "last_token_usage": {
                    "input_tokens": 200,
                    "output_tokens": 20,
                    "input_tokens_details": {"cached_tokens": 50},
                    "output_tokens_details": {"reasoning_tokens": 10},
                },
                "model_context_window": 128000,
            },
        },
        {
            "timestamp": "2026-01-01T00:02:00Z",
            "type": "event",
            "payload": {
                "type": "unknown_future_event",
                "future": {"still": "inspectable"},
            },
        },
    ]
    write_jsonl(session, rows)

    result = ingest(str(session), str(db))

    assert result.files_imported == 1
    with open_db(db) as conn:
        usage = conn.execute("SELECT * FROM usage_snapshots").fetchone()
        thread = conn.execute(
            "SELECT * FROM threads WHERE thread_id='thread-root'"
        ).fetchone()
        unknown_payload = scalar(
            conn,
            "SELECT payload_json FROM events WHERE payload_type='unknown_future_event'",
        )

        assert usage["input_tokens"] == 1000
        assert usage["cached_input_tokens"] == 400
        assert usage["uncached_input_tokens"] == 600
        assert usage["output_tokens"] == 120
        assert usage["reasoning_tokens"] == 40
        assert usage["total_tokens"] == 1160
        assert usage["last_input_tokens"] == 200
        assert usage["last_cached_input_tokens"] == 50
        assert usage["last_uncached_input_tokens"] == 150
        assert usage["last_output_tokens"] == 20
        assert usage["last_reasoning_tokens"] == 10
        assert usage["last_total_tokens"] == 230
        assert usage["model_context_window"] == 128000
        assert thread["final_uncached_input_tokens"] == 600
        assert thread["final_total_tokens"] == 1160
        assert json.loads(unknown_payload) == {
            "type": "unknown_future_event",
            "future": {"still": "inspectable"},
        }


def test_malformed_jsonl_lines_are_counted_without_blocking_valid_rows(
    tmp_path: Path,
) -> None:
    session = tmp_path / "mixed.jsonl"
    db = tmp_path / "observe.sqlite"
    valid_rows = rows_for_session()
    lines = [json.dumps(valid_rows[0]), "{not-json", json.dumps(valid_rows[1])]
    session.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = ingest(str(session), str(db))

    assert result.files_seen == 1
    assert result.files_imported == 1
    assert result.malformed_files == 1
    assert result.malformed_lines == 1
    assert result.events == 2
    with open_db(db) as conn:
        assert scalar(conn, "SELECT COUNT(*) FROM events") == 2


def test_fully_malformed_jsonl_file_is_counted_and_skipped(tmp_path: Path) -> None:
    session = tmp_path / "bad.jsonl"
    db = tmp_path / "observe.sqlite"
    session.write_text("{bad\n{also-bad\n", encoding="utf-8")

    result = ingest(str(session), str(db))

    assert result.files_seen == 1
    assert result.files_imported == 0
    assert result.malformed_files == 1
    assert result.malformed_lines == 2
    with open_db(db) as conn:
        assert scalar(conn, "SELECT COUNT(*) FROM files") == 0


def test_unreadable_jsonl_file_is_counted_without_aborting_scan(
    tmp_path: Path, monkeypatch
) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    unreadable = sessions / "unreadable.jsonl"
    unreadable.write_text("{}\n", encoding="utf-8")
    db = tmp_path / "observe.sqlite"
    ingestor = CodexIngestor(db)

    def raise_oserror(path: Path):
        raise OSError("cannot read")

    monkeypatch.setattr(ingestor, "ingest_file", raise_oserror)
    try:
        result = ingestor.ingest_paths([sessions])
    finally:
        ingestor.close()

    assert result.files_seen == 1
    assert result.unreadable_files == 1
    assert result.files_imported == 0


def test_ingest_newest_files_limits_large_history_without_paths(
    tmp_path: Path,
) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    older = sessions / "older.jsonl"
    middle = sessions / "middle.jsonl"
    newest = sessions / "newest.jsonl"
    write_jsonl(older, rows_for_session(thread_id="older", session_id="older-session"))
    write_jsonl(
        middle, rows_for_session(thread_id="middle", session_id="middle-session")
    )
    write_jsonl(
        newest, rows_for_session(thread_id="newest", session_id="newest-session")
    )
    older.touch()
    middle.touch()
    newest.touch()
    os.utime(older, (1000, 1000))
    os.utime(middle, (2000, 2000))
    os.utime(newest, (3000, 3000))
    db = tmp_path / "observe.sqlite"

    result = ingest(str(sessions), str(db), newest_files=2)

    assert result.newest_files_limit == 2
    assert result.files_matched == 3
    assert result.files_seen == 2
    assert result.files_imported == 2
    assert result.files_skipped_by_limit == 1
    with open_db(db) as conn:
        session_ids = {
            row[0] for row in conn.execute("SELECT session_id FROM conversations")
        }
    assert session_ids == {"middle-session", "newest-session"}


def test_utf8_bom_prefixed_jsonl_is_accepted(tmp_path: Path) -> None:
    session = tmp_path / "bom.jsonl"
    db = tmp_path / "observe.sqlite"
    rows = rows_for_session()
    session.write_text(
        "\ufeff" + "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    result = ingest(str(session), str(db))

    assert result.files_imported == 1
    assert result.malformed_files == 0
    assert result.malformed_lines == 0
    with open_db(db) as conn:
        assert scalar(conn, "SELECT COUNT(*) FROM events") == len(rows)
