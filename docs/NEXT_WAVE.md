# Next Wave Plan

The first local backlog, this next wave, risk-aware public-demo evidence hardening, and first private real-log checkpoint are implemented and verified locally. Do not publish completed local drafts or human-input reminders as new GitHub issues. Future real-log parser expansion remains HITL-only for reviewed-redacted fixture promotion; completed fresh records `006`, `008`, and `009`, plus the former reminder record `007`, were deleted after closeout. Future work should continue to come from real-user feedback, redacted fixture gaps, or explicitly approved distribution work.

## 1. Redacted real-log fixture workflow

Status: Implemented locally.

Goal: let contributors capture parser shape gaps from local logs without committing private content.

Acceptance criteria:

- [x] A documented command creates redacted fixture candidates from a local sessions directory.
- [x] Redaction preserves event type, token fields, tool category, timestamps, thread relationships, and unknown payload shape.
- [x] Redaction removes message text, prompt previews, tool arguments, tool commands, tool output, and local absolute paths.
- [x] Parser tests include at least one redacted-style fixture that is not synthetic demo data.
- [x] Release/privacy docs explain the human review step before committing any derived fixture.

## 2. Clean-install smoke gate

Status: Implemented locally and wired into CI/release docs.

Goal: prove that the documented source-install path works from a fresh environment.

Acceptance criteria:

- [x] A script installs the checkout into a clean virtual environment.
- [x] The smoke gate verifies `codex-observe --version`, `codex-observe demo`, `codex-observe audit --json`, and package importability.
- [x] The gate verifies the `visual` or `dev` extra installs Playwright and Pillow without launching private data paths.
- [x] CI and release docs state when to run the clean-install gate.
- [x] Failures point at broken metadata, missing files, broken console scripts, or command timeouts.

## 3. Large-log ingestion feedback

Status: Implemented locally for aggregate final summaries.

Goal: make long scans understandable without leaking private content.

Acceptance criteria:

- [x] `codex-observe ingest` and `scan-and-serve` show an aggregate final summary for directory scans; `codex-observe ingest --json` exposes the same privacy-safe status as a schema-versioned automation payload.
- [x] The final summary distinguishes seen files, imported files, duplicates, unreadable files, empty files, malformed files, missing `session_meta` files, malformed lines, threads, and events.
- [x] Local CLI output uses aggregate counts only for skipped-file categories; reports and GitHub-ready templates remain aggregate-only.
- [x] Tests cover duplicate, empty, malformed, missing-meta, and summary formatting behavior. Unreadable-file counting is implemented for `OSError` paths.
- [x] README guidance explains what to do after partial ingestion.

## 4. Report comparison workflow

Status: Implemented locally for report JSON files and same-database session IDs.

Goal: let users check whether a workflow change actually reduced waste.

Acceptance criteria:

- [x] A CLI command compares two privacy-safe report JSON files or two session IDs from one database.
- [x] The comparison highlights before/after values, absolute and percentage deltas for total tokens, usage snapshots, uncached input, largest-thread tokens, repeated-prompt tokens, largest-tool-output chars, tool calls, compactions, opportunity-change movement, and diagnostic changes.
- [x] Markdown and JSON outputs exclude prompt text, tool commands, tool output, and raw event payloads.
- [x] README copy links the next-run playbook/report workflow to the comparison workflow.
- [x] Tests cover improved, regressed, report-file, session-ID, and missing-input comparisons.

## 5. Visual QA evidence manifest

Status: Implemented locally.

Goal: make screenshot evidence easier to review and harder to misinterpret.

Acceptance criteria:

- [x] `scripts/visual_qa.py` writes a schema-versioned JSON manifest next to the screenshots.
- [x] The manifest records local URL, database source, viewport sizes, screenshot filenames, clicked tabs, Agent detail selector exercise, sidebar risk labels, sidebar Risk filter evidence, sidebar session search evidence, usage-snapshot comparison deltas, and expected high-risk default metric cards.
- [x] The script checks minimum screenshot dimensions and obvious blank/exception states.
- [x] README and PR template ask contributors to attach or reference the manifest for UI-facing changes, and `codex-observe audit` verifies saved manifest schema/contract evidence, referenced screenshots, layout review, sidebar-risk labels, sidebar Risk filter evidence, sidebar session search evidence, usage-snapshot comparison deltas, and high-risk metric evidence after visual QA runs.
- [x] Tests cover manifest generation and saved-evidence validation without depending on a live browser.

## Active fresh issue drafts

Draft `010`, `Bound dashboard history rendering for large session sets`, is a fresh, validated, approval-gated proposal at `.github/backlog/010-bound-dashboard-history-rendering-for-large-session-sets.md`. It remains local until explicit approval publishes it as a GitHub issue. The completed `009` evidence-bundle draft was implemented locally as `codex-observe evidence-bundle` and deleted after closeout.

Future parser-shape promotion is tracked through `docs/REAL_LOG_FEEDBACK.md` and reviewed-redacted evidence, not as issue content ready to publish until there is a concrete new gap:

- Real-log parser feedback loop. Status: tooling, runbook, and the first human-approved private checkpoint are complete; any new parser-shape issue or fixture still requires human-reviewed redacted evidence before promotion.
## Closeout

The completed local draft files were deleted after explicit confirmation because they no longer represented open work; `009` was deleted after the evidence-bundle command shipped locally.
