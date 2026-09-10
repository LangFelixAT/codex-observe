# Contributing

Codex Observe is a local-first observability tool for Codex session logs. Contributions should remain focused, deterministic, privacy-aware, and easy to verify.

## Development setup

```bash
python -m pip install -e ".[dev]"
python -m playwright install --with-deps chromium
codex-observe self-check --visual --json
```

Supported runtimes are Python 3.10, Python 3.11, and Python 3.12. See `docs/DISTRIBUTION.md` for the source-install policy.

## Planning and traceability

- Start from a GitHub issue or a fresh local draft. `docs/TRACKING.md` is the authoritative issue snapshot.
- Keep changes as small, reviewable checkpoints with one clear user or maintenance outcome.
- Use `python scripts/backlog_publish_plan.py --new-draft "Short title"` when a local draft is useful.
- Run `python scripts/backlog_publish_plan.py --json` before publishing a draft.
- Commit each coherent slice after its relevant gates pass, then push the branch.
- Before handoff, run `git status --short --branch` and explain any remaining changes.

Do not combine unrelated cleanup, feature, parser, and UI work in one commit.

## Quality gates

Every change must pass:

```bash
ruff check
ruff format --check
pytest -q
codex-observe self-check --json
```

Changes to packaging, dependencies, installation, or release workflows must also pass:

```bash
python scripts/clean_install_smoke.py --extra dev
codex-observe audit --json
```

The full release sequence is maintained in `docs/RELEASE.md`; do not duplicate it in pull-request prose.

## Visual changes

Dashboard-facing changes require browser evidence:

```bash
codex-observe demo
python scripts/visual_qa.py
python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json
```

Inspect the referenced desktop and narrow screenshots. Confirm that the dashboard is nonblank, the first viewport is useful, tabs and controls work, and text does not overlap or clip. Generated visual evidence stays under ignored `.artifacts/` paths unless a reviewed synthetic image is intentionally added to documentation.

Use `python scripts/visual_qa.py --profile real` only for locally owned session data. Never commit its output.

## Privacy and parser changes

- Do not commit real sessions, private prompts, tool output, local machine paths, private SQLite databases, or unreviewed exports.
- Prefer synthetic fixtures for tests, screenshots, reports, and CI.
- Preserve unsupported event data in `events.payload_json` so parser changes do not destroy evidence.
- Keep re-import behavior deterministic.
- Update supported-shape documentation when parser behavior changes.

When a real log exposes a parser gap, create a candidate only through the redaction workflow:

```bash
python scripts/redact_fixtures.py <sessions-or-jsonl> --out .artifacts/redacted-fixtures
python scripts/redact_fixtures.py .artifacts/redacted-fixtures --verify-only
```

Review the generated rows, manifest metadata, and `privacy_review` result before moving any candidate into `tests/fixtures/redacted/`. Use `--json` when structured status or error codes are needed. Follow `docs/REAL_LOG_FEEDBACK.md` for the complete process.

New telemetry, hosted behavior, package publishing, credentials, or external uploads require explicit project approval.

## Pull requests

- Link the issue and describe the behavior change.
- List the exact gates run and their result.
- Attach only synthetic or reviewed-redacted evidence.
- For visual work, identify the tested database profile, viewports, screenshots, and manifest.
- Call out limitations or follow-up work rather than hiding it in implementation detail.

Use `.github/PULL_REQUEST_TEMPLATE.md` as the final checklist.

## Release changes

Release changes must update version metadata, `CHANGELOG.md`, `docs/CURRENT.md`, and any affected limitations or distribution guidance. Run every command in `docs/RELEASE.md`, push the verified commit, wait for GitHub Actions, and create the release from that exact commit.
