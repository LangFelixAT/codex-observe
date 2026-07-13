# Changelog

All notable changes to Codex Observe will be documented here.

The project follows semantic versioning once release distribution is decided.

## Unreleased

- Added largest-tool-output evidence to structured session recommendation drivers.
- Added largest-tool-output evidence to session summaries and the recommended-action driver list.
- Added structured next-run validation commands to the public evidence bundle manifest, README, CLI output, and audit validation.
- Added dashboard comparison quick-read, metric delta, and next validation command cards plus Markdown/JSON report and comparison downloads for the selected Overview session and visual/audit evidence that the controls render.
- Added an Agent detail thread brief that surfaces the selected thread's cost share, uncached input, tool count, and first inspection action.
- Added a Tools quick read that highlights the noisiest captured output and the first command to tighten.
- Added a Duplication quick read that turns replayed prompt-block estimates into a first cleanup action.
- Added a Timeline quick read that points reviewers to the largest context jump or compaction boundary first.
- Added a Raw tables data inventory that summarizes parsed table counts before showing row-level evidence.
- Updated the public tour to point reviewers at the dashboard quick-read surfaces now covered by visual QA.
- Strengthened visual QA manifests and release audit checks to require structured dashboard quick-read evidence.
- Strengthened release audit checks for public tour dashboard quick-read guidance.
- Added dashboard comparison metric delta cards and visual/audit evidence that they render.
- Updated the public tour to point reviewers at dashboard comparison metric delta cards.
- Added reproduce-local commands to the reviewer evidence bundle README and release audit validation.
- Added follow-up command templates to aggregate comparison Markdown/JSON exports.
- Added the comparison next validation command to the dashboard Overview quick-read card and visual/audit evidence.
- Added a structured reviewer checklist to the public evidence bundle manifest, README, and audit validation.
- Added reviewer key findings to the public evidence bundle manifest, README, and audit validation.
- Added reviewer key findings to the public evidence bundle text output.
- Updated the public tour and audit contract to require evidence bundle key-findings guidance.
- Bundled the privacy-safe public-tour feedback runbook in reviewer evidence bundles.
- Moved evidence bundle terminal key findings before artifact paths.
- Hardened redacted fixture verification against raw identifier-field leaks.
- Extended release audit redaction checks to require raw ID verify-only rejection.
- Added top-level recommended-action sections to report and comparison Markdown exports.
- Added a recommended-action block to plain-text session listings.
- Added success-target feedback to report write confirmations.
- Added next-validation command feedback to comparison write confirmations.
- Updated the public tour to point at recommended-action and terminal validation evidence.

### Added

- Synthetic demo database workflow through `codex-observe demo`, including `--serve` for a one-command first run and `--json` for schema-versioned creation status.
- Privacy-safe database health checks through `codex-observe doctor` with text output, JSON `schema_version` metadata, structured `next_commands`, and copy-pasteable recovery hints that preserve the selected `--db` path.
- Privacy-safe session listing through `codex-observe sessions` for choosing reportable conversations without printing prompts or tool output, including `schema_version` and `status` metadata, a machine-readable `recommended_session`, structured `recommendation_detail`, structured `next_commands`, and machine-readable missing-database JSON output.
- Privacy-safe Markdown/JSON run reports through `codex-observe report`, including `schema_version` metadata, a quick-read headline, cost profile percentages, a ranked aggregate opportunity stack, aggregate diagnostics, structured next-action metadata, schema-versioned JSON failure payloads, and an impact-targeted next-run playbook; comparison inputs with missing or unsupported report schema versions are rejected with a regeneration hint.
- Fast release-readiness audit through `codex-observe audit`, covering demo data, doctor/session/report flows, Markdown/JSON report artifacts with cost-profile and `schema_version` evidence, comparison quick-read, opportunity-change, percent-delta, command-help product concepts, `schema_version`, JSON evidence, demo creation JSON contract evidence, public tour JSON contract evidence including privacy-safe feedback guidance, generated public evidence bundle artifact validation, full visual manifest contract evidence with referenced screenshots and layout review, release metadata, dev tooling metadata, CI reviewer evidence-bundle generation/upload, issue template evidence/privacy requirements, redaction validation privacy, planning backlog closeout, audit JSON `schema_version`, machine-readable `required_commands`, and actionable `failed_checks` failure summaries.
- Polished dashboard header, empty states, cost-share overview metrics, an aggregate opportunity stack, diagnostics cards, actionable overview guidance, and next-run playbook.
- Tab-covering visual QA with screenshot quality checks for desktop and narrow viewports plus uploaded manifest evidence, metric card evidence, and success-target evidence.
- GitHub issue templates, PR template, planning backlog closeout, release checklist, source-install distribution docs, privacy-safe public-tour feedback runbook/template, and CI workflow.
- `visual` and `dev` optional dependency groups for screenshot QA and full contributor verification, including explicit Playwright and Pillow dependencies.
- Public README tour for evaluating the synthetic demo, aggregate report quick read, opportunity stack, opportunity-change comparison workflow, visual QA evidence, reviewer evidence bundle, final audit, and privacy-safe feedback loop before using private logs, plus schema-versioned `codex-observe tour --json` output with evidence bullets for automation.
- Responsive dashboard metric cards, narrow tab wrapping, verify-only validated manifest evidence and referenced screenshot files in path-safe visual QA manifests, and visual QA layout overflow/clipping review for release-candidate UX evidence.
- Redacted fixture privacy review verifier and `--verify-only` mode for the real-log parser feedback loop, including generated JSONL row and manifest metadata checks.
- Redacted fixture generation supports `--json` for machine-readable generation status and privacy-safe validation failures with error codes, validates the selected input path before touching output, redacts manifest source/output paths and source-derived candidate filenames, and refuses to overwrite arbitrary existing directories; use an empty output directory or a prior redacted candidate directory. `codex-observe ingest --json` now emits aggregate-only `codex-observe.ingest.v1` counts, skipped categories, privacy metadata, and next commands for automation.

### Changed

- Dashboard tables use current Streamlit `width="stretch"` behavior.
- README first-run path now uses synthetic data instead of any local private sample database.
- Report and dashboard diagnostics share non-UI analysis helpers, keeping CLI exports independent from Streamlit; reports and comparisons now include aggregate-only quick-read summaries, opportunity/change summaries, plus structured next-step recommendations and schema-versioned comparison failure payloads that preserve diagnostic priority for persisted issues.
- CLI doctor, report, sessions, and compare paths now print privacy-safe next commands for healthy databases, successful session listings, missing databases, unknown sessions, and incomplete comparison inputs.
- CI now runs Ruff lint, Ruff format check, pytest, audit, demo generation, demo JSON contract verification, synthetic ingest JSON contract verification, session listing, database doctor, report export, visual QA, reviewer evidence-bundle generation, and artifact uploads; release audit verifies those report and visual evidence artifact paths.
- GitHub issue and PR templates now require synthetic/redacted visual evidence instead of private local sample databases.

### Parser

- Token usage normalization now supports Codex `total_token_usage` and OpenAI-style `usage` payloads, including cached/reasoning token details and model context windows.
- Unknown payloads remain retained in `events.payload_json` for raw inspection after ingestion.
- Re-import and duplicate-file behavior remain deterministic.

### Verification

- `ruff check`
- `ruff format --check`
- `pytest -q`
- `codex-observe audit --json`
- `codex-observe tour --json`
- `codex-observe demo`
- `codex-observe demo --sessions .artifacts/demo/sessions --keep-sessions --json`
- `codex-observe ingest .artifacts/demo/sessions --db .artifacts/demo/ingest-contract.sqlite --json`
- `codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json`
- `codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json`
- `codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md`
- `codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json`
- `codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md`
- `codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json`
- `codex-observe evidence-bundle --out .artifacts/public-evidence --skip-visual --json`
- `python scripts/visual_qa.py`
