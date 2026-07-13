from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from codex_observe.parser import ingest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "redact_fixtures", ROOT / "scripts" / "redact_fixtures.py"
)
assert SPEC is not None
assert SPEC.loader is not None
redact_fixtures = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = redact_fixtures
SPEC.loader.exec_module(redact_fixtures)

PRIVATE_STRINGS = [
    "Please inspect my private repo",
    "Get-Content C:/Users/felix/private.txt",
    "secret tool output",
    "C:/Users/felix/private-repo",
]


def write_private_log(path: Path) -> None:
    rows = [
        {
            "timestamp": "2026-02-01T00:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": "thread-private",
                "session_id": "session-private",
                "source": "root",
                "thread_source": "root",
                "cwd": "C:/Users/felix/private-repo",
                "cli_version": "0.3.0",
                "model_provider": "openai",
                "timestamp": "2026-02-01T00:00:00Z",
                "base_instructions": {"text": "private base instructions"},
            },
        },
        {
            "timestamp": "2026-02-01T00:01:00Z",
            "type": "event",
            "payload": {
                "type": "message",
                "role": "user",
                "content": "Please inspect my private repo",
                "turn_id": "turn-private",
            },
        },
        {
            "timestamp": "2026-02-01T00:02:00Z",
            "type": "event",
            "payload": {
                "type": "token_count",
                "turn_id": "turn-private",
                "usage": {
                    "input_tokens": 1200,
                    "output_tokens": 120,
                    "total_tokens": 1360,
                    "input_token_details": {"cached_tokens": 400},
                    "output_token_details": {"reasoning_tokens": 40},
                },
                "model_context_window": 128000,
            },
        },
        {
            "timestamp": "2026-02-01T00:03:00Z",
            "type": "event",
            "payload": {
                "type": "function_call",
                "call_id": "call-private",
                "name": "shell_command",
                "arguments": json.dumps(
                    {
                        "command": "Get-Content C:/Users/felix/private.txt",
                        "workdir": "C:/Users/felix/private-repo",
                    }
                ),
                "turn_id": "turn-private",
            },
        },
        {
            "timestamp": "2026-02-01T00:04:00Z",
            "type": "event",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-private",
                "output": "secret tool output",
                "turn_id": "turn-private",
            },
        },
        {
            "timestamp": "2026-02-01T00:05:00Z",
            "type": "event",
            "payload": {
                "type": "unknown_future_event",
                "future": {"nested": "secret"},
            },
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_redact_sessions_removes_private_content_and_preserves_shape(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private.jsonl"
    output = tmp_path / "redacted"
    write_private_log(source)

    manifest = redact_fixtures.redact_sessions(source, output)
    redacted_file = output / "redacted-001.jsonl"
    text = redacted_file.read_text(encoding="utf-8")

    assert manifest["schema_version"] == redact_fixtures.REDACTION_SCHEMA_VERSION
    assert manifest["files_written"] == 1
    assert manifest["source"] == {"kind": "file", "path": "[redacted-path]"}
    assert manifest["files"][0]["source_index"] == 1
    assert manifest["files"][0]["source_kind"] == "jsonl"
    assert manifest["files"][0]["output_name"] == "redacted-001.jsonl"
    assert "private.jsonl" not in json.dumps(manifest)
    assert manifest["review_required"] is True
    assert manifest["privacy_review"]["status"] == "passed"
    assert manifest["privacy_review"]["files_checked"] == 1
    for private in PRIVATE_STRINGS:
        assert private not in text
    assert "shell_command" in text
    assert "token_count" in text
    assert "unknown_future_event" in text
    assert "redacted-session_id-1" in text
    assert '"arguments":"{\\"redacted\\":true' in text

    db = tmp_path / "observe.sqlite"
    result = ingest(str(redacted_file), str(db))
    assert result.files_imported == 1
    assert result.events == 6


def test_committed_redacted_style_fixture_is_ingestible_and_private_safe(
    tmp_path: Path,
) -> None:
    fixture = ROOT / "tests" / "fixtures" / "redacted" / "real-shape-redacted.jsonl"
    text = fixture.read_text(encoding="utf-8")

    for private in PRIVATE_STRINGS:
        assert private not in text
    assert "[redacted-text" in text
    assert "[redacted-path]" in text

    db = tmp_path / "observe.sqlite"
    result = ingest(str(fixture), str(db))

    assert result.files_imported == 1
    assert result.events == 6


def test_verify_redacted_output_rejects_unredacted_sensitive_fields(
    tmp_path: Path,
) -> None:
    output = tmp_path / "redacted"
    output.mkdir()
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "mode": "redacted-fixture-candidate",
                "review_required": True,
                "files": [],
            }
        ),
        encoding="utf-8",
    )
    (output / "redacted-001-bad.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-02-01T00:00:00Z",
                "type": "event",
                "payload": {
                    "type": "message",
                    "content": "Please inspect C:/Users/felix/private.txt",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    review = redact_fixtures.verify_redacted_output(output)

    assert review["status"] == "failed"
    assert any("private-looking path" in finding for finding in review["findings"])
    assert any("sensitive field" in finding for finding in review["findings"])


def test_verify_only_cli_reports_existing_candidate_status(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "private.jsonl"
    output = tmp_path / "redacted"
    write_private_log(source)
    redact_fixtures.redact_sessions(source, output)

    result = redact_fixtures.main([str(output), "--verify-only"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    assert payload["schema_version"] == redact_fixtures.REDACTION_SCHEMA_VERSION
    assert payload["status"] == "passed"
    assert payload["files_checked"] == 1


def test_redact_sessions_refuses_to_overwrite_non_candidate_directory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private.jsonl"
    output = tmp_path / "existing"
    write_private_log(source)
    output.mkdir()
    keep = output / "keep.txt"
    keep.write_text("do not delete", encoding="utf-8")

    try:
        redact_fixtures.redact_sessions(source, output)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected overwrite refusal")

    assert "refusing to overwrite non-redacted output directory" in message
    assert keep.read_text(encoding="utf-8") == "do not delete"


def test_redact_sessions_allows_replacing_existing_candidate_directory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private.jsonl"
    output = tmp_path / "redacted"
    write_private_log(source)

    first = redact_fixtures.redact_sessions(source, output)
    stale = output / "stale.txt"
    stale.write_text("safe to replace", encoding="utf-8")
    second = redact_fixtures.redact_sessions(source, output)

    assert first["privacy_review"]["status"] == "passed"
    assert second["privacy_review"]["status"] == "passed"
    assert not stale.exists()
    assert (output / "manifest.json").exists()


def test_redact_cli_reports_refused_output_directory_without_deleting_it(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "private.jsonl"
    output = tmp_path / "existing"
    write_private_log(source)
    output.mkdir()
    keep = output / "keep.txt"
    keep.write_text("do not delete", encoding="utf-8")

    result = redact_fixtures.main([str(source), "--out", str(output)])
    captured = capsys.readouterr()

    assert result == 2
    assert (
        "Redaction failed: refusing to overwrite non-redacted output directory"
        in captured.out
    )
    assert keep.read_text(encoding="utf-8") == "do not delete"


def test_redact_sessions_rejects_missing_input_before_creating_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "missing.jsonl"
    output = tmp_path / "redacted"

    try:
        redact_fixtures.redact_sessions(source, output)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected missing input failure")

    assert "input path does not exist" in message
    assert not output.exists()


def test_redact_sessions_rejects_empty_input_directory_before_touching_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions"
    output = tmp_path / "redacted"
    source.mkdir()

    try:
        redact_fixtures.redact_sessions(source, output)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected empty input failure")

    assert "input directory contains no JSONL files" in message
    assert not output.exists()


def test_redact_sessions_rejects_non_jsonl_file_before_touching_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "notes.txt"
    output = tmp_path / "redacted"
    source.write_text("not jsonl", encoding="utf-8")

    try:
        redact_fixtures.redact_sessions(source, output)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected non-jsonl input failure")

    assert "input file is not a JSONL file" in message
    assert not output.exists()


def test_redact_cli_reports_missing_input_without_creating_output(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "missing.jsonl"
    output = tmp_path / "redacted"

    result = redact_fixtures.main([str(source), "--out", str(output)])
    captured = capsys.readouterr()

    assert result == 2
    assert "Redaction failed: input path does not exist" in captured.out
    assert not output.exists()


def test_redact_sessions_rejects_non_positive_limit_before_touching_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private.jsonl"
    output = tmp_path / "redacted"
    write_private_log(source)

    try:
        redact_fixtures.redact_sessions(source, output, limit=0)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected limit failure")

    assert message == "limit must be at least 1"
    assert not output.exists()


def test_redact_cli_json_reports_generation_manifest(tmp_path: Path, capsys) -> None:
    source = tmp_path / "private.jsonl"
    output = tmp_path / "redacted"
    write_private_log(source)

    result = redact_fixtures.main([str(source), "--out", str(output), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    assert payload["schema_version"] == redact_fixtures.REDACTION_SCHEMA_VERSION
    assert payload["mode"] == "redacted-fixture-candidate"
    assert payload["output_dir"] == "[redacted-path]"
    assert payload["source"] == {"kind": "file", "path": "[redacted-path]"}
    assert payload["files"][0]["output_name"] == "redacted-001.jsonl"
    assert "private.jsonl" not in captured.out
    assert payload["files_written"] == 1
    assert payload["review_required"] is True
    assert payload["privacy_review"]["status"] == "passed"
    assert "Wrote " not in captured.out


def test_redact_cli_json_reports_validation_failure_without_touching_output(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "missing.jsonl"
    output = tmp_path / "redacted"

    result = redact_fixtures.main([str(source), "--out", str(output), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 2
    assert payload == {
        "schema_version": redact_fixtures.REDACTION_SCHEMA_VERSION,
        "status": "failed",
        "error_code": "missing_input",
        "error": "input path does not exist",
        "output_dir": "[redacted-path]",
    }
    assert "Redaction failed" not in captured.out
    assert "missing.jsonl" not in captured.out
    assert str(tmp_path) not in captured.out
    assert not output.exists()


def test_redact_sessions_uses_stable_candidate_names_for_directory_inputs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions"
    output = tmp_path / "redacted"
    source.mkdir()
    first = source / "private-one.jsonl"
    second = source / "private-two.jsonl"
    write_private_log(first)
    write_private_log(second)

    manifest = redact_fixtures.redact_sessions(source, output)
    serialized = json.dumps(manifest)

    assert manifest["source"] == {"kind": "directory", "path": "[redacted-path]"}
    assert [row["output_name"] for row in manifest["files"]] == [
        "redacted-001.jsonl",
        "redacted-002.jsonl",
    ]
    assert [row["source_index"] for row in manifest["files"]] == [1, 2]
    assert (output / "redacted-001.jsonl").exists()
    assert (output / "redacted-002.jsonl").exists()
    assert "private-one" not in serialized
    assert "private-two" not in serialized


def test_verify_redacted_output_rejects_manifest_source_path_leaks(
    tmp_path: Path,
) -> None:
    output = tmp_path / "redacted"
    output.mkdir()
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "mode": "redacted-fixture-candidate",
                "review_required": True,
                "source": "C:/Users/felix/private-session.jsonl",
                "files": [],
            }
        ),
        encoding="utf-8",
    )

    review = redact_fixtures.verify_redacted_output(output)

    assert review["status"] == "failed"
    assert any(
        finding == "manifest.json: $.source: contains private-looking path"
        for finding in review["findings"]
    )


def test_verify_redacted_output_rejects_manifest_source_filename_leaks(
    tmp_path: Path,
) -> None:
    output = tmp_path / "redacted"
    output.mkdir()
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "mode": "redacted-fixture-candidate",
                "review_required": True,
                "source": {"kind": "file", "path": "[redacted-path]"},
                "files": [
                    {
                        "source_name": "private-session.jsonl",
                        "output_name": "redacted-001-private-session.jsonl",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    review = redact_fixtures.verify_redacted_output(output)

    assert review["status"] == "failed"
    assert any("source_name" in finding for finding in review["findings"])
    assert any("output_name" in finding for finding in review["findings"])
