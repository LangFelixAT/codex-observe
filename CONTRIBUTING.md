# Contributing

Codex Observe is an offline observability tool for local Codex session logs. Contributions should preserve the same default posture: local-first, privacy-aware, deterministic, and verifiable.

## Development setup

```bash
python -m pip install -e ".[dev]"
python scripts/clean_install_smoke.py --extra dev
python -m playwright install chromium
```

Use Python 3.10, 3.11, or 3.12. The supported source-install distribution policy is documented in `docs/DISTRIBUTION.md`.

## Planning workflow

- Work from a fresh vertical slice in docs or a published GitHub issue; `docs/TRACKING.md` records the current issue snapshot and `docs/BACKLOG.md` is now a completed closeout record.
- Keep slices demoable on their own.
- Scaffold fresh local issue drafts with `python scripts/backlog_publish_plan.py --new-draft "Short demoable title" --label "type: slice" --label "area: dashboard"` so tests, visual QA, privacy review, and blocked-by sections are present from the start.
- Run `python scripts/backlog_publish_plan.py` before publishing fresh local issue drafts; use `python scripts/backlog_publish_plan.py --json` for machine-readable review metadata.
- Do not publish fresh local issue drafts to GitHub without explicit approval; check `docs/TRACKING.md` before opening or retiring issues.
- Use `.github/PULL_REQUEST_TEMPLATE.md` for verification and privacy evidence.
- Use `.github/ISSUE_TEMPLATE/public_tour_feedback.yml` and `docs/PUBLIC_TOUR_FEEDBACK.md` for privacy-safe public-tour or reviewer-bundle observations before turning feedback into implementation issues.

## Traceability cadence

Keep implementation work in small, reviewable checkpoints. After each coherent slice passes its relevant gates, commit it with a message that names the user-visible or workflow outcome, then push the branch so `origin` has the same trace as the local workspace.

Use this cadence for dashboard/UI polish, parser changes, CLI/report behavior, release docs, and evidence tooling. `codex-observe paths --json` should keep the guided `private-validate --newest-files 25 --json` command discoverable before lower-level manual follow-ups. Do not batch unrelated slices into one large commit unless they were already completed together and have passed the full quality gate; in that case, make one checkpoint commit before starting the next slice.

Before handing off or starting a new slice, run `git status --short --branch` and confirm the working tree is clean or explain the remaining local changes.

## Privacy rules

- Do not commit real Codex session logs, private prompts, raw tool output, local file paths from private machines, or non-synthetic SQLite databases.
- Use synthetic fixtures and `codex-observe demo` for tests, screenshots, docs, reports, and CI artifacts.
- Treat screenshots, raw dashboard tables, report excerpts, and issue text as potentially sensitive unless they are generated from synthetic data.
- New telemetry, hosted mode, publishing credentials, external report uploads, or package-index automation require explicit approval before implementation.

## Local verification

Run the final aggregate-only release audit after visual evidence and `.artifacts/public-evidence` exist. Failed audit runs print a `Failed checks` section, and `codex-observe audit --json` includes `failed_checks` for automation:

```bash
codex-observe evidence-bundle --out .artifacts/public-evidence
codex-observe audit --json
```

Run lint, formatting, and the regression suite:

```bash
ruff check
ruff format --check
codex-observe self-check --json
codex-observe paths --json
pytest -q
```

For CLI/report/privacy-facing changes, also exercise the privacy-safe path handoff and demo commands:

```bash
codex-observe self-check --json
codex-observe paths --json
codex-observe demo
codex-observe demo --sessions .artifacts/demo/sessions --keep-sessions --json
codex-observe ingest .artifacts/demo/sessions --db .artifacts/demo/ingest-contract.sqlite --json
codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json
codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --risk high --focus thread --json
codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json
codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md
codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json
codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md
codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json
```

The session listing is aggregate-only and includes aggregate triage risk, stable Focus values and distributions, composable `--risk`/`--focus` filters, and a structured `recommended_session` drawn from the matching scope so reviewers and automation can choose a run without reading prompts, tool output, or parsing the human `next` string.

For UI-facing changes, run visual QA:

```bash
python scripts/visual_qa.py
```

`codex-observe self-check --visual --json` verifies Pillow and Playwright imports before the browser check. The visual QA script starts Streamlit, clicks Overview, Agent detail, Timeline & jumps, Tools, Duplication, and Raw tables, exercises the Agent detail selector, and writes desktop/narrow screenshots and a validated path-safe visual QA manifest with tab coverage, selector exercise, screenshot metadata, layout review, sidebar risk labels, exercised Risk and Focus filters with narrowed-result, valid-selection, and restored-state evidence, expected high-risk default metric card evidence, operator-briefing evidence, complete initial-viewport tab navigation, checklist -> brief -> native copy prompt -> comparison -> metric ordering, nearest-follow-up comparison selection and chronological comparison direction, and success-target evidence to `.artifacts/visual/`. Recheck saved evidence and referenced screenshot files with `python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json`. For ignored private validation artifacts, use `codex-observe private-validate ~/.codex/sessions --visual --json` to run the bounded private loop plus real-profile browser QA in one command, or rerun only the browser check with `python scripts/visual_qa.py --profile real --db .artifacts/private/real-sessions.sqlite --out .artifacts/private/visual-real`; do not commit those screenshots or manifests.

## Parser changes

- Add synthetic or redacted fixtures for every new log shape. Use `python scripts/redact_fixtures.py <sessions-or-jsonl> --out .artifacts/redacted-fixtures` for local-log-derived fixture candidates, then review `manifest.json` and its automated `privacy_review`, which scans generated JSONL rows and manifest metadata, before committing anything; generated manifest source/output paths and source-derived candidate filenames are redacted, and use `--json` for machine-readable generation status and privacy-safe validation failures with error codes. The script validates the selected input path before touching output and refuses to overwrite arbitrary existing directories; use an empty output directory or a prior redacted candidate directory. Re-run candidate verification with `python scripts/redact_fixtures.py .artifacts/redacted-fixtures --verify-only`, and follow `docs/REAL_LOG_FEEDBACK.md` for the full human review loop.
- Preserve unknown payloads in `events.payload_json`.
- Keep re-import behavior deterministic.
- Update README supported log-shape documentation when support changes.

## Release changes

Release readiness is tracked in `docs/RELEASE.md`. Before calling a release candidate ready, verify:

- `python scripts/clean_install_smoke.py --extra dev`
- `ruff check`
- `ruff format --check`
- `pytest -q`
- `codex-observe self-check --json`
- `codex-observe paths --json`
- `python scripts/visual_qa.py`
- `python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json`
- `codex-observe evidence-bundle --out .artifacts/public-evidence`
- `codex-observe audit --json`

Generated `.artifacts/` outputs are local evidence and are ignored by default. Public-tour feedback should reference synthetic or reviewed-redacted artifacts only, following `docs/PUBLIC_TOUR_FEEDBACK.md`. For report-facing work, keep `.artifacts/demo/run-report.md`, `.artifacts/demo/run-report.json`, `.artifacts/demo/run-comparison.md`, and `.artifacts/demo/run-comparison.json` together so reviewers can inspect the same aggregate evidence as CI. Compare commands that write `--out` also print the aggregate verdict and triage-risk movement for quick terminal review.

