from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REDACTION_SCHEMA_VERSION = "codex-observe.redaction.v1"


TEXT_KEYS = {
    "content",
    "message",
    "text",
    "input",
    "output",
    "result",
    "stdout",
    "stderr",
    "preview",
    "command",
    "workdir",
    "cwd",
}
PATH_KEYS = {"path", "file_path", "cwd", "workdir"}
ID_KEYS = {"id", "session_id", "parent_thread_id", "thread_id", "call_id", "turn_id"}
SAFE_STRING_KEYS = {
    "type",
    "role",
    "name",
    "tool_name",
    "thread_source",
    "source_kind",
    "agent_role",
    "model_provider",
    "timestamp",
}
PRIVATE_PATTERNS = [
    re.compile(r"[A-Za-z]:[\\/][^\s\"']+"),
    re.compile(r"/(?:Users|home|tmp|var|private)/[^\s\"']+"),
]


class RedactionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


@dataclass
class RedactionState:
    ids: dict[str, str] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    strings_redacted: int = 0
    paths_redacted: int = 0
    arguments_redacted: int = 0

    def pseudonym(self, kind: str, value: Any) -> Any:
        if value in {None, ""}:
            return value
        raw = str(value)
        cache_key = f"{kind}:{raw}"
        if cache_key not in self.ids:
            self.counters[kind] = self.counters.get(kind, 0) + 1
            self.ids[cache_key] = f"redacted-{kind}-{self.counters[kind]}"
        return self.ids[cache_key]


def looks_like_private_path(value: str) -> bool:
    return any(pattern.search(value) for pattern in PRIVATE_PATTERNS)


def redacted_text(value: str) -> str:
    return f"[redacted-text chars={len(value)}]"


def redact_string(
    value: str, state: RedactionState, *, force_path: bool = False
) -> str:
    if force_path or looks_like_private_path(value):
        state.paths_redacted += 1
        return "[redacted-path]"
    state.strings_redacted += 1
    return redacted_text(value)


def redact_arguments(value: Any, state: RedactionState) -> str:
    state.arguments_redacted += 1
    keys: list[str] = []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = {}
    else:
        parsed = value
    if isinstance(parsed, dict):
        keys = sorted(str(key) for key in parsed.keys())
    return json.dumps({"redacted": True, "keys": keys}, separators=(",", ":"))


def redact_value(value: Any, state: RedactionState, key: str = "") -> Any:
    if isinstance(value, dict):
        return redact_dict(value, state)
    if isinstance(value, list):
        return [redact_value(item, state, key) for item in value]
    if isinstance(value, str):
        if key in SAFE_STRING_KEYS:
            return value
        if key in ID_KEYS:
            return state.pseudonym(key, value)
        return redact_string(value, state, force_path=key in PATH_KEYS)
    return value


def redact_dict(obj: dict[str, Any], state: RedactionState) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in obj.items():
        if key == "arguments":
            redacted[key] = redact_arguments(value, state)
        elif key == "base_instructions" and isinstance(value, dict):
            redacted[key] = {"text": redact_string(str(value.get("text") or ""), state)}
        elif key in TEXT_KEYS:
            redacted[key] = redact_string(
                str(value), state, force_path=key in PATH_KEYS
            )
        elif key in ID_KEYS:
            redacted[key] = state.pseudonym(key, value)
        else:
            redacted[key] = redact_value(value, state, key)
    return redacted


def redact_event(event: dict[str, Any], state: RedactionState) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in event.items():
        if key == "payload" and isinstance(value, dict):
            redacted[key] = redact_dict(value, state)
        elif key in {"timestamp", "type"}:
            redacted[key] = value
        elif key in ID_KEYS:
            redacted[key] = state.pseudonym(key, value)
        else:
            redacted[key] = redact_value(value, state, key)
    return redacted


def sensitive_value_is_redacted(key: str, value: Any) -> bool:
    if key == "arguments" and isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return False
        return isinstance(parsed, dict) and parsed.get("redacted") is True
    if key in ID_KEYS:
        if value in {None, ""}:
            return True
        return isinstance(value, str) and bool(
            re.fullmatch(rf"redacted-{re.escape(key)}-\d+", value)
        )
    if key in PATH_KEYS:
        return value == "[redacted-path]"
    if key in TEXT_KEYS:
        return isinstance(value, str) and (
            value == "[redacted-path]" or value.startswith("[redacted-text chars=")
        )
    return True


def privacy_findings_in_value(
    value: Any, *, key: str = "", path: str = "$"
) -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            findings.extend(
                privacy_findings_in_value(
                    child_value, key=str(child_key), path=f"{path}.{child_key}"
                )
            )
        return findings
    if isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(
                privacy_findings_in_value(item, key=key, path=f"{path}[{index}]")
            )
        return findings
    if isinstance(value, str):
        if looks_like_private_path(value):
            findings.append(f"{path}: contains private-looking path")
        if key == "source_name":
            findings.append(f"{path}: manifest must not include source_name")
        if key == "output_name" and not re.fullmatch(r"redacted-\d{3}\.jsonl", value):
            findings.append(
                f"{path}: output_name must use stable redacted-###.jsonl form"
            )
        if key not in SAFE_STRING_KEYS and key in TEXT_KEYS | PATH_KEYS | ID_KEYS | {
            "arguments"
        }:
            if not sensitive_value_is_redacted(key, value):
                findings.append(f"{path}: sensitive field {key!r} is not redacted")
    return findings


def verify_redacted_output(output_dir: Path) -> dict[str, Any]:
    root = output_dir.expanduser()
    findings: list[str] = []
    files_checked = 0
    rows_checked = 0
    manifest_path = root / "manifest.json"
    if not root.exists():
        return {
            "status": "failed",
            "files_checked": 0,
            "rows_checked": 0,
            "findings": [f"missing output directory: {root}"],
        }
    if not manifest_path.exists():
        findings.append("missing manifest.json")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(f"manifest.json is not valid JSON: {exc}")
        else:
            if manifest.get("review_required") is not True:
                findings.append("manifest.json does not require human review")
            if manifest.get("mode") != "redacted-fixture-candidate":
                findings.append("manifest.json has unexpected mode")
            for finding in privacy_findings_in_value(manifest):
                findings.append(f"manifest.json: {finding}")

    for file_path in sorted(root.glob("*.jsonl")):
        files_checked += 1
        with file_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, raw in enumerate(handle, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                rows_checked += 1
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError as exc:
                    findings.append(f"{file_path.name}:{line_no}: invalid JSON: {exc}")
                    continue
                for finding in privacy_findings_in_value(row):
                    findings.append(f"{file_path.name}:{line_no}: {finding}")

    return {
        "schema_version": REDACTION_SCHEMA_VERSION,
        "status": "passed" if not findings else "failed",
        "files_checked": files_checked,
        "rows_checked": rows_checked,
        "findings": findings,
    }


def output_dir_is_redacted_candidate(output_dir: Path) -> bool:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return manifest.get("mode") == "redacted-fixture-candidate"


def prepare_output_dir(output_dir: Path) -> None:
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        return
    if not output_dir.is_dir():
        raise RedactionError("output_not_directory", "output path is not a directory")
    if any(output_dir.iterdir()) and not output_dir_is_redacted_candidate(output_dir):
        raise RedactionError(
            "refuse_overwrite",
            "refusing to overwrite non-redacted output directory; choose an empty directory or an existing redacted fixture candidate directory",
        )
    shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def discover_input_files(input_path: Path, *, limit: int | None = None) -> list[Path]:
    source = input_path.expanduser()
    if not source.exists():
        raise RedactionError("missing_input", "input path does not exist")
    if source.is_file():
        if source.suffix.lower() != ".jsonl":
            raise RedactionError("non_jsonl_input", "input file is not a JSONL file")
        files = [source]
    elif source.is_dir():
        files = sorted(source.rglob("*.jsonl"))
        if not files:
            raise RedactionError(
                "empty_input", "input directory contains no JSONL files"
            )
    else:
        raise RedactionError(
            "unsupported_input", "input path is neither a file nor directory"
        )
    if limit is not None:
        if limit < 1:
            raise RedactionError("invalid_limit", "limit must be at least 1")
        files = files[:limit]
    return files


def redact_jsonl_file(src: Path, dst: Path, index: int) -> dict[str, Any]:
    state = RedactionState()
    rows_written = 0
    malformed_lines = 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    with (
        src.open("r", encoding="utf-8", errors="replace") as inp,
        dst.open("w", encoding="utf-8", newline="\n") as out,
    ):
        for line_no, raw in enumerate(inp, start=1):
            raw = raw.strip()
            if not raw:
                continue
            if line_no == 1:
                raw = raw.lstrip("\ufeff")
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                malformed_lines += 1
                continue
            redacted = redact_event(
                event if isinstance(event, dict) else {"value": event}, state
            )
            out.write(
                json.dumps(redacted, separators=(",", ":"), sort_keys=True) + "\n"
            )
            rows_written += 1
    return {
        "source_index": index,
        "source_kind": "jsonl",
        "output_name": dst.name,
        "rows_written": rows_written,
        "malformed_lines_skipped": malformed_lines,
        "strings_redacted": state.strings_redacted,
        "paths_redacted": state.paths_redacted,
        "arguments_redacted": state.arguments_redacted,
        "ids_redacted": len(state.ids),
    }


def redact_sessions(
    input_path: Path, output_dir: Path, *, limit: int | None = None
) -> dict[str, Any]:
    source = input_path.expanduser()
    files = discover_input_files(source, limit=limit)
    out = output_dir.expanduser()
    prepare_output_dir(out)

    results = []
    for index, src in enumerate(files, start=1):
        dst = out / f"redacted-{index:03d}.jsonl"
        results.append(redact_jsonl_file(src, dst, index))

    manifest = {
        "schema_version": REDACTION_SCHEMA_VERSION,
        "mode": "redacted-fixture-candidate",
        "source": {
            "kind": "file" if source.is_file() else "directory",
            "path": "[redacted-path]",
        },
        "output_dir": "[redacted-path]",
        "files_seen": len(files),
        "files_written": sum(1 for item in results if item["rows_written"]),
        "review_required": True,
        "privacy_contract": [
            "message text redacted",
            "prompt text redacted",
            "tool arguments redacted",
            "tool commands redacted",
            "tool output redacted",
            "local paths redacted",
            "ids pseudonymized",
        ],
        "files": results,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    manifest["privacy_review"] = verify_redacted_output(out)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create redacted Codex JSONL fixture candidates for parser-shape tests."
    )
    parser.add_argument("input", help="Codex sessions directory or one JSONL file")
    parser.add_argument("--out", default=".artifacts/redacted-fixtures")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit generation status or failure details as JSON.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify an existing redacted fixture candidate directory instead of writing new files.",
    )
    args = parser.parse_args(argv)

    if args.verify_only:
        review = verify_redacted_output(Path(args.input))
        print(json.dumps(review, indent=2, sort_keys=True))
        return 0 if review["status"] == "passed" else 1

    try:
        manifest = redact_sessions(Path(args.input), Path(args.out), limit=args.limit)
    except RedactionError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": REDACTION_SCHEMA_VERSION,
                        "status": "failed",
                        "error_code": exc.code,
                        "error": exc.public_message,
                        "output_dir": "[redacted-path]",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"Redaction failed: {exc}")
        return 2
    review = manifest["privacy_review"]
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print(
            f"Wrote {manifest['files_written']} redacted fixture candidates to {manifest['output_dir']}. Privacy review {review['status']}; review manifest.json before committing any file."
        )
    return 0 if review["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
