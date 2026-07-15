# Codex Observe

Offline observability dashboard for Codex `.jsonl` session logs.

## Product direction

The current quality bar and implementation backlog live in [docs/AMAZING.md](docs/AMAZING.md), known limitations and next-work sources live in [docs/LIMITATIONS.md](docs/LIMITATIONS.md), privacy-safe public-tour feedback guidance lives in [docs/PUBLIC_TOUR_FEEDBACK.md](docs/PUBLIC_TOUR_FEEDBACK.md), the issue-tracking snapshot lives in [docs/TRACKING.md](docs/TRACKING.md), and the short returning-to-project handoff lives in [docs/CURRENT.md](docs/CURRENT.md). In short, Codex Observe should help a Codex power user understand what made a run expensive and what to change before the next run.

## Try it now

Codex Observe can run entirely against local data. To see the privacy-safe public evaluation path:

```bash
python -m pip install -e .
codex-observe tour
```

To try it without scanning your own logs, generate a synthetic demo database with contrasting high- and low-risk runs; add `--json` when automation needs schema-versioned creation status:

```bash
codex-observe demo --serve --host 127.0.0.1 --port 8501
```
Then open <http://127.0.0.1:8501>.

To confirm the resolved private paths and get a sampled, privacy-safe validation handoff first:

```bash
codex-observe paths
```

The command prints the resolved local Codex sessions path, the Codex Observe database path, existence checks, and next commands without scanning logs or printing filenames, prompts, tool output, session IDs, or aggregate metrics. Use that resolved path for private validation when you want real Codex history rather than synthetic demo input.

To run the bounded private validation loop into ignored artifacts before opening the dashboard:

```bash
codex-observe private-validate ~/.codex/sessions
```

This ingests the newest 25 files by default, checks database health, lists aggregate sessions, exports the recommended aggregate report under `.artifacts/private/`, and keeps terminal output free of private counts, filenames, raw IDs, prompts, tool output, and raw log content.

To scan your own Codex sessions and open the dashboard:

```bash
codex-observe scan-and-serve ~/.codex/sessions
```

## Public Tour

A new user can evaluate the product without private logs. `codex-observe tour` prints this path from the terminal with a top-level review checklist, evidence and success checks to look for at each step, and a terminal feedback handoff plus a final copy-pasteable `Next commands` footer; `codex-observe tour --json` emits the same synthetic-data path plus plain terminal handoff commands, `codex-observe.tour.v1` schema metadata, `review_path`, `feedback_handoff`, and per-step success checks for automation:

1. Run `codex-observe demo --serve --host 127.0.0.1 --port 8501` to create a synthetic database and open the dashboard; plain demo output prints terminal `Review path` and `Next commands` guidance, and `codex-observe demo --json` emits machine-readable demo creation status, structured `next_commands`, and a structured `review_path` with success checks.
2. Inspect the Overview operator briefing, risk distribution card, next-review path, next-run checklist, next-run brief, safe feedback handoff, Overview triage card, dashboard comparison quick-read, sampled-ingest warning when present, review-path, metric delta cards including usage snapshots, safe feedback handoff, and next validation command cards plus report and comparison download controls, diagnostics, and cost-share metrics, Agent detail thread brief, Timeline quick read, Tools quick read, Duplication quick read, and Raw tables data inventory tabs to see how Codex Observe explains cost and context growth.
3. Run `codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite` to verify aggregate database health with terminal `Review path` and `Next commands` guidance; run `codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json` for `schema_version`, structured `next_commands`, and the structured `review_path` before consuming automation output.
4. Run `codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite` to list reportable runs with aggregate triage risk, a recommended-action block, aggregate Snapshots and Tool out columns, a review path, and terminal `Next commands`; output is capped at 50 sessions by default, with `--limit <n>` for larger reviews. Run `codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json` for `schema_version`, `status`, `total_sessions`, `returned_sessions`, `truncated`, aggregate `risk_distribution`, per-session `usage_snapshots`, a structured `recommended_session`, `recommendation_detail` with raw aggregate driver fields and ordered `driver_summary` display labels, a structured `review_path` for report, next-run validation, compare, and safe feedback steps, and structured `next_commands` for baseline report export, next-run report export, and comparison automation without printing prompts or tool output; the demo includes a newer low-risk follow-up so the highest-risk recommendation is visible.
5. Run `codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md`, then `codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json`, to export aggregate-only evidence with a quick-read headline with usage snapshot count, top-level recommended action, terminal success-target, privacy-warning, and next-command confirmation, ranked opportunity stack, recommended next habit, next-run success target, next-run checklist, copy-pasteable next-run brief, follow-up command templates, and structured next-action target, and structured `feedback_handoff` metadata for safe public-tour observations; the dashboard Overview exposes the same selected-run Markdown/JSON report downloads with sampled-ingest warning when present and aggregate comparison quick-read, sampled-ingest warning when present, review-path, metric delta cards including usage snapshots, and next validation command cards plus Markdown/JSON downloads for reviewers who start in the UI.
6. Run `codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md`, then `codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json`, to compare workflow changes with a verdict, largest-change summary, top-level recommended action, terminal next validation command, terminal privacy warning, terminal next-command guidance, opportunity-change summary, percent-delta table, diagnostic-change summary, structured recommendation target, structured review path, structured `feedback_handoff` metadata, follow-up command templates, and triage-risk movement without exposing raw content.
7. Run `python scripts/visual_qa.py` to regenerate desktop and narrow synthetic screenshots plus `.artifacts/visual/visual-qa-manifest.json`; use `python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json` to validate saved manifest evidence, missing/empty database onboarding states, sidebar risk labels, sidebar snapshot-count context, expected high-risk default metric card values, report sampled-ingest warning evidence when present, comparison quick-read, sampled-ingest warning evidence when present, review-path, metric delta cards including usage snapshots, and next validation command cards plus report and comparison download controls, the operator briefing, the next-review path, the next-run checklist, the next-run brief, the safe feedback handoff, the dashboard success target, and referenced screenshot files without launching the dashboard.
8. Run `codex-observe evidence-bundle --out .artifacts/public-evidence` when a reviewer needs one local synthetic bundle whose terminal output and reviewer README both surface an ordered action plan, key findings, a review checklist with comparison review-path guidance, reproduce-local commands, and next-run validation commands, plus `LIMITATIONS.md`, `PUBLIC_TOUR_FEEDBACK.md`, `.github/ISSUE_TEMPLATE/public_tour_feedback.yml`, structured `feedback_handoff` metadata, the demo database, aggregate report Markdown/JSON, aggregate comparison Markdown/JSON, audit JSON, visual screenshots, and a schema-versioned `codex-observe.evidence-bundle.v1` manifest.
9. Run `codex-observe audit --json` to verify the generated synthetic evidence, visual manifest, public bundle, tour contract, issue templates, release metadata, and required command list before treating the result as release evidence.
10. Use [docs/PUBLIC_TOUR_FEEDBACK.md](docs/PUBLIC_TOUR_FEEDBACK.md), [docs/TRACKING.md](docs/TRACKING.md), and `.github/ISSUE_TEMPLATE/public_tour_feedback.yml` to file privacy-safe feedback from the public tour, terminal handoff commands, or reviewer evidence bundle without private logs, raw prompts, tool output, local paths, or unreviewed screenshots; new implementation issues should be fresh, demoable work and still require explicit approval before external publication.

The visual evidence and public evidence bundle are intentionally generated into ignored `.artifacts/` paths. Reference the manifest and screenshot filenames in reviews; do not commit private logs, private SQLite databases, or unreviewed local artifacts.

## Install locally

Supported distribution is currently a source checkout with editable install. Python 3.10, 3.11, and 3.12 are supported; PyPI publishing, binary installers, hosted mode, and telemetry are not enabled without explicit approval. See [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) and [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

```bash
cd codex-observe
python -m pip install -e .
```

Verify the installed command:

```bash
codex-observe --version
```

## Run

Ingest sessions and open the dashboard:

```bash
codex-observe scan-and-serve ~/.codex/sessions
```

On Windows CMD:

```bat
codex-observe paths
codex-observe scan-and-serve "%USERPROFILE%\.codex\sessions"
```

The default database is stored at:

```text
~/.codex-observe/codex_observe.sqlite
```


Use `codex-observe paths` to show the resolved default sessions path and database path, report whether they exist, and print a sampled `--newest-files 25` ingest command plus doctor, sessions, and serve follow-ups without scanning logs or printing filenames, prompts, tool output, session IDs, or aggregate metrics. On Windows this resolves the default sessions directory from `%USERPROFILE%\.codex\sessions`. Use `codex-observe private-validate ~/.codex/sessions` when you want one command to write the bounded real-session database, path handoff, ingest status, doctor status, session listing, and recommended aggregate report into ignored `.artifacts/private/` files before launching the dashboard.

After ingestion, the CLI prints an aggregate summary that distinguishes imported files, duplicates, empty files, malformed files, files missing `session_meta`, unreadable files, malformed lines skipped, threads, and events, plus a privacy warning to review private databases, reports, screenshots, copied rows, and aggregate metrics before sharing. Use `codex-observe ingest ~/.codex/sessions` for terminal `Review path` and `Next commands` guidance, or `codex-observe ingest ~/.codex/sessions --json` for a `codex-observe.ingest.v1` aggregate-only payload with counts, skipped categories, privacy metadata including `review_required_before_sharing`, structured `next_commands`, and a structured `review_path`. For large real histories, start with `codex-observe ingest ~/.codex/sessions --newest-files 25 --json`; the JSON reports how many JSONL files matched, how many were processed, and how many were deferred by the newest-file limit without printing raw log content, and later doctor, sessions, report, comparison, and dashboard surfaces show the persisted sampled-ingest scope; terminal doctor and sessions output also prints sample coverage and the next `--newest-files` expansion command. A partial ingest can still be useful; run `codex-observe doctor --db <db>` next to confirm the resulting database is valid. Doctor recovery hints and terminal `Next commands` are copy-pasteable and preserve the same `--db` path for missing, empty, invalid, or unreadable databases. Doctor JSON also includes structured `next_commands` and a structured `review_path`; a healthy populated database points to `codex-observe sessions --db <db>` for report selection, `codex-observe serve --db <db>` for dashboard inspection, and report export as the next review steps.

To serve an existing database without scanning first:

```bash
codex-observe serve --db ~/.codex-observe/codex_observe.sqlite
```

To check a database without opening the dashboard or printing private log content:

```bash
codex-observe doctor --db ~/.codex-observe/codex_observe.sqlite
```

To list reportable conversation IDs and aggregate triage risk without printing private log content:

```bash
codex-observe sessions --db ~/.codex-observe/codex_observe.sqlite
```

If the database has conversations, codex-observe sessions shows any persisted sampled-ingest scope warning with sample coverage and the next expansion command, the aggregate risk distribution, each run's aggregate risk, usage snapshot count, and Tool out column, a recommended-action block with the highest-risk session and top aggregate drivers including largest tool output, and the next report command for that session, using latest run as the tie-breaker. Large histories are capped to 50 printed or returned sessions by default; pass `--limit <n>` when you need a larger page while the recommendation is still ranked across the full database. With `--json`, the payload includes `schema_version`, `status`, `total_sessions`, `returned_sessions`, `truncated`, aggregate `risk_distribution`, per-session `usage_snapshots`, a structured `recommended_session`, `recommendation_detail` with raw aggregate driver fields and ordered `driver_summary` display labels, a structured `review_path` for report, next-run validation, compare, and safe feedback steps, a structured success-target preview for the recommended run, and structured `next_commands` for baseline report export, next-run report export, and comparison automation; missing databases also return a machine-readable JSON recovery payload with the same exit code. If the database is valid but empty, it prints the next ingest or demo command instead of a blank table.

To export a shareable aggregate-only run report for the recommended highest-risk conversation:

```bash
codex-observe report --db ~/.codex-observe/codex_observe.sqlite --out run-report.md
```

Use `--format json` for automation or `--session-id <id>` to report a specific conversation. Report JSON includes `schema_version`, summary `usage_snapshots`, persisted `ingest_scope` when available, `success_target`, `next_action_detail`, a structured `next_run_checklist`, a structured `next_run_brief`, a structured `review_path`, and structured `feedback_handoff` metadata so automation can verify the aggregate artifact contract, measure the next-run target, consume the top next-run action, and walk the validation steps before reading display text; if report generation fails in `--format json` mode, the CLI returns a `codex-observe.report-failure.v1` payload with `status`, `error`, and recovery `next_commands`. If a session id is stale or mistyped, `codex-observe report` points back to `codex-observe sessions --db <db>` so you can list available aggregate-only session IDs. When `--out` is used, the CLI prints a privacy-safe triage, top-opportunity, sampled-ingest scope and sample-coverage guidance when present, next-action, and success-target confirmation after writing the file. Reports include a quick-read headline, aggregate triage assessment, persisted ingest scope when available, a next-run success target, a copy-pasteable next-run brief, a review path, a feedback handoff, follow-up command templates, summary totals including usage snapshots, cost profile percentages, a ranked opportunity stack, diagnostics, and an impact-targeted next-run playbook; they exclude message text, prompt previews, event payload JSON, tool arguments, tool commands, and tool output.

To compare whether a workflow change reduced waste, export two JSON reports and compare them:

```bash
codex-observe report --db ~/.codex-observe/codex_observe.sqlite --session-id before-run --format json --out before.json
codex-observe report --db ~/.codex-observe/codex_observe.sqlite --session-id after-run --format json --out after.json
codex-observe compare --before-report before.json --after-report after.json --out run-comparison.md
```

You can also compare two sessions directly from one database:

```bash
codex-observe compare --db ~/.codex-observe/codex_observe.sqlite --before-session before-run --after-session after-run --format json
```

When `--out` is used, the CLI prints a privacy-safe comparison confirmation with verdict, triage-risk movement, opportunity-change summary, sampled-ingest scope and sample coverage when either input report came from a bounded sample, the next sample-expansion command for same-database comparisons, next step, and next validation command. Comparisons are aggregate-only and highlight before/after values, absolute and percentage deltas for total tokens, usage snapshots, uncached input, largest-thread tokens, repeated-prompt tokens, largest-tool-output chars, tool calls, compactions, opportunity-change movement, diagnostic changes, triage-risk movement, a human recommended next step, follow-up command templates, a structured review path, and a structured recommendation target that preserves diagnostic priority when choosing persisted issues to target next. Comparison JSON also includes `schema_version`, persisted `ingest_scope` when available, `review_path`, and `feedback_handoff` for automation-safe contract checks; if comparison setup fails in `--format json` mode, the CLI returns a `codex-observe.comparison-failure.v1` payload with `status`, `input_mode`, `error`, and recovery `next_commands`. `codex-observe compare --before-report/--after-report` rejects missing or unsupported report `schema_version` values; regenerate stale inputs with `codex-observe report --format json`.

`serve` and `scan-and-serve` accept `--host` and `--port`. These are passed to Streamlit before the dashboard app arguments:

```bash
codex-observe serve --db ./codex_observe.sqlite --host 127.0.0.1 --port 9999
codex-observe scan-and-serve ~/.codex/sessions --db ./codex_observe.sqlite --host 127.0.0.1 --port 9999
codex-observe scan-and-serve ~/.codex/sessions --newest-files 25 --db ./codex_observe.sqlite --host 127.0.0.1 --port 9999
```

## Data privacy

Codex Observe runs against local Codex session logs and local SQLite databases. It does not intentionally send session content to external services. `codex-observe doctor` reports aggregate table/token counts only and prints terminal `Review path` plus `Next commands`; it also supports `--json` with `schema_version`, structured `next_commands`, and a structured `review_path` for automation. It does not print message text, tool output, payload JSON, or prompt blocks. Treat screenshots, copied table rows, and issue text as potentially sensitive because they may include prompts, file paths, command output, or tool results. See [docs/RELEASE.md](docs/RELEASE.md) for release and privacy checks.

## Supported log shapes

The parser is defensive because Codex JSONL payloads are not guaranteed stable. The currently supported shapes are:

- `session_meta` rows with thread/session metadata, including root sessions and spawned subagent threads.
- Message payloads with `type=message` plus `role` and `content`, and legacy `user_message` / `agent_message` payloads.
- `token_count` payloads with Codex `total_token_usage` or OpenAI-style `usage`, including nested cached/reasoning token details, `last_token_usage`, and `model_context_window`.
- Tool calls: `function_call`, `custom_tool_call`, and `tool_search_call`.
- Tool outputs: `function_call_output`, `custom_tool_call_output`, `tool_search_output`, and `patch_apply_end`.
- Compaction markers from top-level `compacted` events and `context_compacted` payloads.
- Large prompt blocks extracted from message text for duplication analysis.

Unknown and unsupported payloads are still retained in `events.payload_json` so raw source data remains inspectable after ingestion.

## Derived values

Authoritative token totals come from Codex `token_count` events. Conversation and thread rollups use the final token snapshot for each thread.

Approximate token values are only text-size estimates used for message snippets and repeated prompt block analysis. They are not authoritative billing or model-usage counts.

Re-importing the same file path refreshes the event-derived rows for that thread. Importing identical content from a different path records a duplicate file row and points it at the canonical imported path.

## What it shows

- conversation list grouped by day
- root / worker / explorer / guardian labeling
- token attribution by thread and role
- cache-adjusted token totals
- worker/thread detail view with an actionable thread brief
- likely worker launch prompt / goal reconstruction
- context compaction events
- largest token jumps
- tool distribution and largest tool outputs
- guardian overhead
- prompt duplication breakdown
- impact-targeted next-run playbook with concrete workflow habits
- privacy-safe Markdown or JSON report export with a quick-read headline
- raw tables for inspection


## Redacted fixtures

Parser gaps found in real local logs should be reduced to redacted fixture candidates before they are used in issues or tests:

```bash
python scripts/redact_fixtures.py ~/.codex/sessions --out .artifacts/redacted-fixtures --limit 5
```

The script writes redacted JSONL files plus `manifest.json`. It preserves event types, timestamps, token fields, tool categories, unknown payload shape, and thread/call relationships while redacting message text, prompt text, tool arguments, tool commands, tool output, local paths, raw IDs, manifest source/output paths, and source-derived candidate filenames. The manifest includes `schema_version` and an automated `privacy_review` that scans generated JSONL rows and manifest metadata; use `--json` for machine-readable generation status and privacy-safe validation failures with error codes. You can re-run it with `python scripts/redact_fixtures.py .artifacts/redacted-fixtures --verify-only`. Review every generated file and manifest before committing any fixture; the script validates the selected input path before touching output and refuses to overwrite arbitrary existing directories. Follow [docs/REAL_LOG_FEEDBACK.md](docs/REAL_LOG_FEEDBACK.md) for the full human review loop.

## Visual QA

For UI-facing changes, run the dashboard against a representative database and capture desktop plus narrow screenshots:

```bash
codex-observe demo
python scripts/visual_qa.py
```

The script clicks every main dashboard tab, exercises the Agent detail selector, writes screenshots plus a schema-versioned, path-safe `.artifacts/visual/visual-qa-manifest.json`, validates manifest evidence covers desktop/narrow viewports and records validated manifest evidence for desktop/narrow viewports, tabs, screenshots, selector exercise, missing/empty database onboarding states, sidebar risk labels, sidebar snapshot-count context, expected high-risk default metric cards, operator briefing, risk distribution, next-run checklist, next-run brief, safe feedback handoff, dashboard success target, and layout review, and fails if expected tab content, obvious Streamlit exception checks, layout overflow/clipping checks, or screenshot quality checks fail. It requires Playwright, Pillow, and a Chromium browser runtime locally; if missing, install the visual extra and browser runtime with:

```bash
python -m pip install -e ".[visual]"
python -m playwright install chromium
```

## Project workflow

Contributors should follow [CONTRIBUTING.md](CONTRIBUTING.md) for setup, privacy rules, verification commands, and release evidence.
Completed and retired local slice records are tracked in [docs/BACKLOG.md](docs/BACKLOG.md), implemented next-wave closeout is tracked in [docs/NEXT_WAVE.md](docs/NEXT_WAVE.md), and the completed `009` public evidence bundle slice is implemented locally as `codex-observe evidence-bundle`. Fresh work should be scaffolded with `python scripts/backlog_publish_plan.py --new-draft "Short demoable title" --label "type: slice" --label "area: dashboard"` and promoted into new GitHub issues only after explicit approval and once it is more than a human-input reminder; public-tour observations should use the privacy-safe feedback template and `docs/PUBLIC_TOUR_FEEDBACK.md` before becoming implementation work. PRs should use the repository template to link the relevant issue when one exists, list verification commands, record visual QA evidence, record public evidence bundle artifacts when generated, and confirm `docs/LIMITATIONS.md` remains current.

## CI quality gate

Pull requests run the clean-install smoke gate, Ruff lint, Ruff format checks, the regression suite, the aggregate release audit, synthetic demo generation, demo JSON contract check, aggregate ingest JSON contract check, aggregate-only session listing, database doctor, aggregate report export, aggregate report comparison, evidence-bundle contract check, and visual QA. CI uploads the aggregate run report, comparison report, desktop/narrow dashboard screenshots, visual QA manifest with missing/empty database onboarding evidence, metric card evidence, report sampled-ingest warning evidence when present, comparison review-path, sampled-ingest warning evidence when present, and usage-snapshot metric delta evidence, operator-briefing evidence, risk-distribution evidence, next-review path evidence, safe-feedback-handoff evidence, next-run-checklist evidence, and success-target evidence, and the reviewer public evidence bundle as workflow artifacts.

## Validate locally

Generate a reviewer-facing synthetic evidence bundle when you need one local directory whose terminal output and reviewer README both surface an ordered action plan, key findings, a review checklist with comparison review-path guidance, reproduce-local commands, next-run validation commands, structured `feedback_handoff` metadata, `LIMITATIONS.md`, `PUBLIC_TOUR_FEEDBACK.md`, `.github/ISSUE_TEMPLATE/public_tour_feedback.yml`, report, comparison, audit, and visual QA artifacts:

```bash
codex-observe evidence-bundle --out .artifacts/public-evidence
```

Run the final aggregate-only release audit after visual evidence has been generated and verified:

```bash
codex-observe audit
```

The audit verifies the `codex-observe paths` handoff schema, no-scan privacy metadata, sampled `--newest-files 25` command, review path, and paths handoff evidence. The dashboard missing-database and empty-database states now show copy-pasteable next actions for synthetic demo data, local ingestion, and database health checks. The audit generates synthetic demo data, runs database/session/report checks, verifies schema-versioned demo creation JSON, synthetic ingest JSON review path and private-sharing review metadata, public tour JSON top-level review path, plain text next-command footer, baseline-to-next-run validation-loop evidence, comparison review-path guidance, and quick-read guidance, generated public evidence bundle artifacts including terminal handoff checklist, validation commands, and `LIMITATIONS.md`, CI reviewer evidence-bundle generation/upload, issue template evidence/privacy requirements, release metadata files, redaction validation privacy including raw-ID `--verify-only` rejection, saved visual QA manifest schema/contract evidence for referenced screenshots, missing/empty database onboarding states, layout review, sidebar risk labels, sidebar snapshot-count context, high-risk metric cards, dashboard quick-read evidence, report sampled-ingest warning evidence when present, comparison quick-read, sampled-ingest warning evidence when present, review-path, metric delta cards including usage snapshots, and next validation command cards plus report and comparison download controls, operator briefing, risk distribution, next-run checklist, next-run brief, safe feedback handoff, and dashboard success target, aggregate report usage-snapshot summary, cost-profile, success-target, terminal privacy warning, triage, structured review path, structured feedback handoff, structured follow-up commands, structured next-action, and `schema_version` evidence, aggregate comparison usage-snapshot deltas, terminal privacy warning, quick-read, triage-risk, opportunity-change, percent-delta, structured review path, structured feedback handoff, follow-up command templates, command-help product concepts, and `schema_version` evidence, and planning backlog closeout, writes `.artifacts/demo/run-report.md`, `.artifacts/demo/run-report.json`, `.artifacts/demo/run-comparison.md`, and `.artifacts/demo/run-comparison.json`, includes `schema_version`, machine-readable `required_commands`, and `failed_checks` lists in `--json` output, and prints the same required command list plus a `Failed checks` section in plain-text output when a gate fails. It does not run Ruff, `pytest`, clean-install smoke, or browser visual QA; run those first before the final audit.

Run the clean-install smoke gate to prove a fresh source checkout can install, create synthetic demo data, generate the reviewer evidence bundle README/manifest plus bundled limitations doc and feedback issue template, audit that generated bundle, and import optional dev dependencies:

```bash
python scripts/clean_install_smoke.py --extra dev
```

Run lint, formatting, the privacy-safe path handoff check, and the regression suite:

```bash
ruff check
ruff format --check
codex-observe paths --json
pytest -q
```

For UI-facing dashboard changes, browser-verify Streamlit against a database that contains at least one conversation, multiple threads, usage snapshots, tool calls, and prompt blocks. `codex-observe demo` creates a synthetic database with those shapes. Click through these tabs at desktop and narrow/mobile widths and confirm there is no visible Streamlit exception: Overview, Agent detail thread brief, Timeline quick read, Tools quick read, Duplication quick read, and Raw tables data inventory. Exercise the Agent detail thread selector during the check. Record the local URL, tested database source, viewport sizes, screenshot filenames, and `.artifacts/visual/visual-qa-manifest.json` in the PR or issue.
