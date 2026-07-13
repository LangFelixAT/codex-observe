# Release Checklist

Codex Observe is an offline tool for local Codex session logs. A release is ready only when a new user can install it, understand the data boundaries, and verify that the dashboard works on representative data.

## Data and privacy

- Codex Observe reads local `.jsonl` session logs and local SQLite databases.
- The app does not intentionally send session content to any external service.
- Streamlit serves the dashboard locally by default when launched with `127.0.0.1`.
- Users should treat screenshots, exported tables, issue bodies, and bug reports as potentially sensitive because they may contain prompts, file paths, command output, or tool results.
- Any future telemetry, hosted mode, sharing feature, or package publishing credential must be explicitly designed and approved before implementation.

## Pre-release checks

- [ ] `ruff check` passes.
- [ ] `ruff format --check` passes.
- [ ] `pytest -q` passes.
- [ ] GitHub Actions CI passes for lint, format, tests, Markdown/JSON aggregate report export, aggregate comparison, visual QA, and reviewer evidence-bundle artifact upload.
- [ ] The release branch is pushed to `origin`, `git status --short --branch` is clean/synced, and any local-only evidence or unfinished work is explicitly called out before handoff.
- [ ] `codex-observe demo` passes, `codex-observe demo --sessions .artifacts/demo/sessions --keep-sessions --json` emits `codex-observe.demo.v1`, and `codex-observe ingest .artifacts/demo/sessions --db .artifacts/demo/ingest-contract.sqlite --json` emits aggregate-only `codex-observe.ingest.v1` counts and skipped-category evidence.
- [ ] `codex-observe audit` passes after visual QA and `.artifacts/public-evidence` exist, including schema-versioned demo creation JSON, synthetic ingest JSON, public tour JSON evidence including dashboard quick-read guidance and report/comparison-download evidence, generated public evidence bundle README reproduce-local commands, manifest, and limitations artifacts, CI reviewer evidence-bundle generation/upload, issue template evidence/privacy requirements, tracking snapshot evidence, saved visual manifest schema/contract evidence for referenced screenshots, missing/empty database onboarding states, layout review, sidebar risk labels, high-risk metric cards, dashboard quick-read evidence, comparison quick-read, metric delta, and next validation command cards plus report and comparison download controls, operator briefing, and dashboard success target, the redaction validation privacy check for privacy-safe JSON failures with error codes, plain-text required command list, plain-text `Failed checks` section on failures, and `codex-observe audit --json` includes `schema_version` plus the machine-readable `required_commands` and `failed_checks` verification lists; audit also checks that report/compare help surfaces advertise opportunity-stack and opportunity-change concepts.
- [ ] `codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json` passes with `schema_version` and structured `next_commands` evidence.
- [ ] `codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json` lists aggregate-only session summaries, `schema_version`, `status`, a structured `recommended_session`, `recommendation_detail`, and structured `next_commands` for the highest-risk run, and missing database JSON remains machine-readable.
- [ ] `codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md` creates an aggregate-only Markdown report with cost-profile evidence, aggregate triage assessment, and a next-run success target and follow-up command templates.
- [ ] `codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json` creates the matching aggregate-only JSON report with `schema_version` and structured follow-up commands, structured next-action and success-target evidence; report JSON failure paths return schema-versioned recovery payloads.
- [ ] `codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md` creates an aggregate-only comparison report with quick-read, triage-risk, opportunity-change, percent-delta, structured recommendation, and follow-up command evidence, and `codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json` creates matching machine-readable comparison evidence with `schema_version` evidence; comparison JSON failure paths return schema-versioned recovery payloads.
- [ ] `python scripts/visual_qa.py` passes against the generated synthetic demo database, and `python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json` validates the saved manifest evidence, missing/empty database onboarding states, sidebar risk labels, expected high-risk default metric card values, comparison quick-read, metric delta, and next validation command cards plus report and comparison download controls, operator briefing, dashboard success target, and referenced screenshot files.
- [ ] `codex-observe evidence-bundle --out .artifacts/public-evidence` creates a reviewer-facing synthetic bundle with a reviewer README containing reproduce-local commands, `LIMITATIONS.md`, report, comparison, audit, visual QA artifacts, and `codex-observe.evidence-bundle.v1` manifest evidence. This bundle is optional/reviewer-facing and still local-only by default.
- [ ] `python scripts/clean_install_smoke.py --extra dev` succeeds in a clean environment. The clean-install smoke gate runs `python -m pip install -e ".[dev]"` inside the temporary virtual environment, verifies the skipped-visual evidence bundle README/manifest/limitations contract, runs audit against that generated bundle with `--public-evidence-dir`, and verifies Playwright plus Pillow imports for visual QA.
- [ ] `LICENSE`, `CHANGELOG.md`, and package metadata in `pyproject.toml` are present and accurate.
- [ ] Report and dashboard diagnostics use the same shared analysis helpers.
- [ ] Desktop and narrow screenshots pass automated nonblank/viewport quality checks and are reviewed for obvious layout problems, text overlap, and Streamlit exceptions.
- [ ] Visual QA covers Overview, Agent detail thread brief, Timeline quick read, Tools quick read, Duplication quick read, Raw tables data inventory, the Agent detail selector, structured quick-read evidence, and validated manifest evidence for desktop/narrow screenshots, missing/empty database onboarding states, sidebar risk labels, expected high-risk default metric cards, operator briefing, dashboard success target, and layout review.
- [ ] README install, demo, ingestion, serve, validation commands, and dashboard empty-state next actions are accurate.
- [ ] `CONTRIBUTING.md` verification and privacy guidance matches this checklist.
- [ ] `docs/AMAZING.md` reflects the current product bar and active fresh backlog drafts.
- [ ] `docs/CURRENT.md` reflects the current product state, quality gates, visual evidence contract, tracking snapshot, and remaining HITL blocker.
- [ ] `docs/LIMITATIONS.md` reflects current limitations, approval-gated non-goals, remaining HITL blocker, and next planned work sources, and `docs/PUBLIC_TOUR_FEEDBACK.md` plus `.github/ISSUE_TEMPLATE/public_tour_feedback.yml` keep public-tour feedback privacy-safe.
- [ ] `docs/TRACKING.md` records the current GitHub issue snapshot, local draft state, explicit approval requirement for `gh issue create`, and commit/push traceability cadence; open GitHub issues are either closed, deferred, or represented in active fresh backlog drafts.
- [ ] PR template verification, Markdown/JSON aggregate report artifacts, comparison artifact, audit-verified public evidence bundle README/manifest/limitations doc, visual screenshots, path-safe visual QA manifest with missing/empty database onboarding states, sidebar risk labels and expected high-risk metric card evidence, comparison metric delta evidence, report-and-comparison-download-control evidence, operator-briefing evidence, success-target evidence, limitations review, and privacy sections are completed for the release PR.
- [ ] Version in `pyproject.toml` and `codex_observe/__init__.py` is updated consistently.
- [ ] Any generated screenshots or local databases are excluded from commits unless intentionally added as fixtures. Any fixture derived from local logs followed `docs/REAL_LOG_FEEDBACK.md`, was first generated with `python scripts/redact_fixtures.py`, reviewed with its manifest and automated `privacy_review` over generated JSONL rows and manifest metadata, used `--json` for machine-readable generation status and privacy-safe validation failures with error codes when needed, optionally rechecked with `python scripts/redact_fixtures.py .artifacts/redacted-fixtures --verify-only`, protected by the script rule that validates the selected input path before touching output and refuses to overwrite arbitrary existing directories, and checked for private text, tool output, commands, local paths, manifest source/output paths, and source-derived candidate filenames.

## Release notes checklist

- [ ] Summarize user-visible dashboard changes.
- [ ] Summarize parser/log shape changes.
- [ ] Call out migration or re-ingestion recommendations.
- [ ] Mention visual QA screenshots, manifest, and tested database source.
- [ ] Mention known limitations and next planned slices from `docs/LIMITATIONS.md`.

## Distribution decision

Current supported distribution: source checkout with editable install. See `docs/DISTRIBUTION.md` for the authoritative install path, Python support policy, versioning rules, private artifact policy, and explicit non-goals. See `docs/LIMITATIONS.md` for known limitations, approval-gated work, and next planned work sources.

PyPI publishing, binary installers, hosted mode, telemetry, package-index credentials, and publishing automation remain blocked until explicitly approved.

