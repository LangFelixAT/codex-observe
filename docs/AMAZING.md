# Making Codex Observe Amazing

## Product bar

Codex Observe is amazing when a Codex power user can point it at local session logs and quickly answer:

- What made this run expensive?
- Which root thread, worker, explorer, or guardian consumed the most context?
- Which prompt blocks were replayed unnecessarily?
- Which tool calls produced unusually large output?
- What should I change in my workflow to reduce waste on the next run?

The product should feel like a focused workbench, not a raw table dump. Every screen should explain cost and context growth in terms a user can act on.

## Quality bar

- Setup is obvious from the README, `codex-observe doctor`, and the empty dashboard state.
- Ingestion is deterministic across re-runs, duplicate files, partial files, and known Codex log shape drift.
- Dashboard pages are polished at desktop and narrow widths, with no Streamlit exceptions or text overlap.
- Visual changes are checked against a real database with representative conversations, threads, usage snapshots, tools, and prompt blocks.
- Tests cover parser behavior, CLI argument ordering, dashboard helper logic, and any non-trivial UI data transformations.
- GitHub issues track vertical slices that are demoable on their own; `docs/TRACKING.md` records the current issue snapshot and unpublished planning lives in docs until external issue creation is explicitly approved.

## Current findings

- The parser and ingestion suite are solid for known JSONL shapes and now normalize both Codex `total_token_usage` and OpenAI-style `usage` token payloads while retaining unknown payloads; large real-history checks can be bounded with `--newest-files` so users can validate recent logs before committing to a full scan, and sampled databases now carry persisted scan-scope warnings, sample-coverage summaries, and expansion-command guidance into later doctor, sessions, report, comparison, and dashboard steps.
- Shared diagnostics, report recommendations, and aggregate-only quick-read summaries now live in non-UI modules, so CLI exports do not depend on Streamlit dashboard side effects.
- The dashboard now has a stronger first-run experience with copy-pasteable empty-state commands, first-class `codex-observe demo` and privacy-safe `codex-observe doctor` commands with copy-pasteable recovery hints, a two-session synthetic demo with contrasting high- and low-risk runs, a risk-aware dashboard default, sidebar session search, and sidebar risk labels, a tab-covering local and CI visual QA workflow with screenshot quality checks plus structured quick-read manifest evidence for missing/empty database onboarding states, sidebar risk labels, sidebar Risk filter evidence, sidebar session search evidence, sidebar snapshot-count evidence, high-risk metric cards, Overview sample-coverage card and report sampled-ingest warning evidence when present, comparison quick-read, sampled-ingest warning evidence when present, review-path, metric delta cards including usage snapshots, safe feedback handoff, next-run brief, and next validation command cards plus report/comparison download controls, and the Overview operator briefing, risk distribution, next-run checklist, next-run brief, aggregate report artifact export with sampled-ingest warning when present, dashboard comparison quick-read, review-path, metric delta, and next validation command cards plus Markdown/JSON report and comparison downloads, share-aware Overview cost metrics, a polished actionable diagnostics card summary, Agent detail thread brief, Timeline quick read, Tools quick read, Duplication quick read, Raw tables data inventory, a ranked opportunity stack plus a next-run playbook that turn diagnostics into impact-targeted workflow habits, a privacy-safe session listing command with aggregate risk distribution, triage-risk filtering, largest-tool-output driver evidence, and next-run target preview, a privacy-safe report export with a quick-read headline that includes usage-snapshot scale, triage assessment, persisted sampled-ingest warnings when available, measurable next-run success target, structured next-run checklist, copy-pasteable next-run brief, terminal sharing warnings, and follow-up command templates for sharing run evidence, and aggregate reports/comparisons that carry structured feedback handoff metadata, persisted sampled-ingest warnings and coverage metadata when available, and terminal sharing warnings, show opportunity-change movement, preserve diagnostic priority in next-step recommendations, and include follow-up command templates. Release/privacy checks live in `docs/RELEASE.md`, and the current source-install distribution policy lives in `docs/DISTRIBUTION.md`.
- The first local backlog and the next wave are implemented locally: redacted fixture generation, clean-install smoke, large-log ingest feedback, aggregate report comparison, a visual QA evidence manifest, and final audit verification of saved visual evidence are in place.
- The repo had no open GitHub issues in the 2026-07-13 tracking snapshot, so completed local draft files were deleted instead of being published as stale GitHub issues. Future issue drafts should represent fresh work only; public-tour observations now have a privacy-safe feedback template before they become implementation issues; release-candidate UX evidence and public README tour polish are implemented locally, the completed `009` draft is implemented locally by `codex-observe evidence-bundle` with a reviewer README, bundled limitations doc, and retired from publishable issue state, and the first real-log parser feedback checkpoint has been exercised through a human-approved private input path while future fixture promotion remains HITL-only and privacy-reviewed.
- The README now frames the product value, source-install policy, multi-session synthetic demo path, privacy-safe commands including `codex-observe paths`, supported log shapes, visual QA evidence with missing/empty database onboarding states, sidebar risk labels, sidebar Risk filter evidence, sidebar session search evidence, sidebar snapshot-count evidence, and expected high-risk metrics, aggregate comparison workflow, contributor workflow, and links to `docs/LIMITATIONS.md` for known limitations and next-work sources.

## First issue backlog

### 1. Polish first-run and demo experience

Status: Implemented locally.

Type: AFK

What to build: Make the first minute with Codex Observe feel guided. A user without an existing database should see clear next actions, and a user with the sample database should have an obvious demo path.

Acceptance criteria:

- The README has a short "try it now" path for either real logs or synthetic demo data.
- The dashboard missing-database and empty-database states explain copy-pasteable next commands for synthetic demo data, local ingestion, and database health checks.
- The dashboard header and metric surfaces have a coherent visual style.
- `pytest -q` passes.
- A desktop and narrow-width visual check is recorded in the issue closeout.

### 2. Add a run diagnostics summary

Status: Implemented locally; keep expanding recommendations as new real-log patterns appear.

Type: AFK

What to build: Add an opinionated summary panel that ranks the top causes of context growth and cost for the selected conversation.

Acceptance criteria:

- The dashboard highlights the largest thread, largest token jump, largest tool output, repeated prompt blocks, compaction, and guardian overhead when present.
- Each diagnostic includes a concrete action and evidence, rendered as a scannable card with an expandable raw table.
- Diagnostics generate a next-run playbook with concrete workflow habits.
- Empty or missing data produces useful empty states, not blank tables.
- Dashboard helper tests cover the ranking logic.
- Visual QA passes at desktop and narrow widths after changes.

### 3. Build visual regression workflow

Status: Implemented locally and wired into CI.

Type: AFK

What to build: Add a repeatable local visual verification workflow for Streamlit using a representative SQLite database.

Acceptance criteria:

- The repo documents how to launch the dashboard for visual QA.
- The workflow generates synthetic demo data via `codex-observe demo`, clicks all dashboard tabs, exercises the Agent detail selector, captures desktop and narrow screenshots, and records missing/empty database onboarding states, sidebar risk labels, sidebar Risk filter evidence, sidebar session search evidence, sidebar snapshot-count evidence, expected high-risk default metric cards, report sampled-ingest warning evidence when present, comparison quick-read, sampled-ingest warning evidence when present, review-path, metric delta cards including usage snapshots, safe feedback handoff, and next validation command cards plus report/comparison download controls, plus operator-briefing, risk-distribution, next-run-checklist, and next-run-brief evidence in the manifest.
- The workflow fails or clearly flags visible Streamlit exceptions.
- The README explains when visual QA is required.

### 4. Improve log shape resilience

Status: Implemented for OpenAI-style usage payloads; continue expanding as new real-log patterns appear.

Type: AFK

What to build: Expand parser normalization for additional Codex event shapes found in real logs while preserving unknown payloads.

Acceptance criteria:

- OpenAI-style token usage payloads are represented in focused fixtures.
- Unknown payloads remain inspectable in raw events.
- Re-import behavior stays deterministic.
- Existing parser tests continue to pass.

### 5. Package for real users

Status: Source-install distribution policy implemented locally; package-index publishing remains approval-gated.

Type: HITL

What to build: Decide the distribution path and release polish needed for people outside this repo to install and use Codex Observe confidently.

Acceptance criteria:

- The repo has a release checklist.
- The README states supported Python versions, install method, and data privacy expectations.
- The versioning/release decision is documented.
- Any publish-to-index decision is explicitly approved before credentials or packaging automation are added.
