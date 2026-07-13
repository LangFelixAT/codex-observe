# Real-Log Parser Feedback Runbook

Use this only after a human explicitly selects a local Codex sessions directory or JSONL file. Do not run it against private logs by default, and do not commit raw logs.

## 1. Generate candidates

```bash
python scripts/redact_fixtures.py <sessions-or-jsonl> --out .artifacts/redacted-fixtures --limit 5
python scripts/redact_fixtures.py <sessions-or-jsonl> --out .artifacts/redacted-fixtures --limit 5 --json
```

The command supports `--json` with `schema_version` for machine-readable generation status and privacy-safe validation failures with error codes. It validates the selected input path before touching output. Missing paths, non-JSONL files, empty directories, and non-positive limits fail without creating or deleting candidate output. The command writes redacted JSONL candidates and `manifest.json`; manifest source/output paths and source-derived candidate filenames are redacted. The manifest includes `privacy_review`, which scans generated JSONL rows and manifest metadata; the status must be `passed` before any candidate can be considered for commit. The script refuses to overwrite arbitrary existing directories; choose an empty output directory or rerun only over a prior redacted fixture candidate directory with a valid manifest.

## 2. Re-run verification

```bash
python scripts/redact_fixtures.py .artifacts/redacted-fixtures --verify-only
```

Stop if this reports `failed`; it checks generated JSONL rows and manifest metadata. Fix the redaction script or discard the candidate directory before continuing.

## 3. Human review checklist

Open `manifest.json` and every generated `redacted-*.jsonl` file. Confirm all of the following before committing anything:

- No prompt text, message text, tool output, shell command, local path, source filename, raw session ID, raw thread ID, raw call ID, or raw turn ID is visible.
- Sensitive fields are placeholders such as `[redacted-text chars=N]`, `[redacted-path]`, redacted argument JSON, or `redacted-<kind>-N` pseudonyms.
- Event types, timestamps, token fields, tool categories, unknown payload shape, and thread/call relationships are still useful for parser tests.
- The fixture demonstrates a parser shape not already covered by synthetic or existing redacted fixtures.

## 4. Decide what to commit

If a safe new shape exists, copy only the reviewed redacted JSONL fixture into `tests/fixtures/redacted/`, add a focused parser test, and update README supported log-shape notes if support changes.

If no safe new shape exists, do not commit generated candidates. Record that outcome in the relevant issue or PR closeout with the `privacy_review` status and a short reason, such as `no new parser shape found` or `candidate discarded during human privacy review`.

## 5. Final verification

Run:

```bash
ruff check
ruff format --check
pytest -q
codex-observe audit --json
python scripts/visual_qa.py
```

Keep `.artifacts/redacted-fixtures/` local and ignored unless a reviewed fixture is intentionally copied into `tests/fixtures/redacted/`.
