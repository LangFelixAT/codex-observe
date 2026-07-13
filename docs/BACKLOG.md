# GitHub Backlog

This file records completed and retired local vertical-slice planning. The draft files were deleted after completion or when they became human-input reminders rather than implementation slices; publishing issue content to GitHub still requires explicit approval, and completed drafts should not be published as new GitHub issues. There are currently no publishable local issue drafts; the implemented next-wave closeout and completed evidence-bundle slice are summarized in `docs/NEXT_WAVE.md`.

## Labels

Suggested labels used by the templates:

- `type: slice`
- `status: ready`
- `area: dashboard`
- `area: parser`
- `area: release`

## Publish checklist

Before publishing fresh drafts:

- [ ] Run `python scripts/backlog_publish_plan.py` and review the generated `gh issue create` commands.
- [ ] Run `python scripts/backlog_publish_plan.py --json` when automation or reviewers need `schema_version`-marked machine-readable draft metadata.
- [ ] Confirm each generated command includes `--repo LangFelixAT/codex-observe` and the expected `--label` values.
- [ ] Confirm issue contents do not include private session text or local-only paths.
- [ ] Confirm labels either already exist or will be created intentionally.
- [ ] Publish issues in dependency order.
- [ ] Link published issue numbers back into this file or replace this file with tracker links.

## Issue drafts

### 1. Polish first-run and demo experience

Type: AFK

Labels: `type: slice`, `area: dashboard`, `status: ready`

What to build: Make the first minute with Codex Observe feel guided. A user without an existing database should see clear next actions, and a user with no private logs should have an obvious synthetic demo path.

Acceptance criteria:

- [x] The README has a short "try it now" path for real logs and synthetic demo data.
- [x] `codex-observe demo --serve` creates demo data and launches the dashboard.
- [x] `codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json` reports aggregate-only demo database health.
- [x] The dashboard missing-database and empty-database states explain the next command to run.
- [x] The dashboard header and metric surfaces have a coherent visual style.
- [x] `pytest -q` passes.
- [x] `python scripts/visual_qa.py` passes and records desktop/narrow screenshot evidence, sidebar risk labels, and expected high-risk metric cards.

Blocked by: None.

### 2. Add a run diagnostics summary

Type: AFK

Labels: `type: slice`, `area: dashboard`, `status: ready`

What to build: Add an opinionated summary panel that ranks the top causes of context growth and cost for the selected conversation.

Acceptance criteria:

- [x] The dashboard highlights largest thread, largest token jump, largest tool output, repeated prompt blocks, compaction, and guardian overhead when present.
- [x] Each diagnostic includes a concrete action and evidence.
- [x] Diagnostics render as scannable cards with an expandable raw table.
- [x] Empty or missing data produces useful empty states, not blank tables.
- [x] Dashboard helper tests cover ranking and rendering logic.
- [x] Visual QA passes at desktop and narrow widths.

Blocked by: None.

### 3. Build visual regression workflow

Type: AFK

Labels: `type: slice`, `area: dashboard`, `status: ready`

What to build: Add repeatable local and CI visual verification for Streamlit using synthetic representative data.

Acceptance criteria:

- [x] `codex-observe demo` generates representative synthetic data.
- [x] `python scripts/visual_qa.py` clicks all dashboard tabs, exercises the Agent detail selector, and verifies the risk-aware default dashboard evidence.
- [x] Visual QA captures desktop and narrow screenshots.
- [x] GitHub Actions runs lint, format, tests, demo generation, session listing, database doctor, report export, visual QA, reviewer evidence bundle generation, final audit with saved visual evidence validation, and uploads artifacts.
- [x] README explains when visual QA is required.

Blocked by: None.

### 4. Improve log shape resilience

Type: AFK

Labels: `type: slice`, `area: parser`, `status: ready`

What to build: Expand parser normalization for additional Codex event shapes found in real logs while preserving unknown payloads.

Acceptance criteria:

- [x] OpenAI-style token usage payloads are represented in synthetic fixtures.
- [x] Unknown payloads remain inspectable in `events.payload_json`.
- [x] Re-import behavior stays deterministic.
- [x] Existing parser tests continue to pass.
- [x] No new dashboard-facing derived value was added for this parser slice; dashboard-facing derived values remain covered by helper tests.

Blocked by: None.

### 5. Package for real users

Type: HITL

Labels: `type: slice`, `area: release`, `status: ready`

What to build: Document and verify the supported source-install distribution path so people outside this repo can install and use Codex Observe confidently without implying PyPI or hosted distribution is enabled.

Acceptance criteria:

- [x] `docs/RELEASE.md` is complete for the chosen source-install release path.
- [x] The README states supported Python versions, install method, and data privacy expectations.
- [x] Versioning/release decision is documented in `docs/DISTRIBUTION.md`.
- [x] Non-synthetic local sample data handling is decided: keep private/local and ignored.
- [x] Any publish-to-index decision is explicitly approved before credentials or packaging automation are added.

Blocked by: Only package-index publishing, binary installers, hosted mode, telemetry, credentials, or publishing automation require explicit human approval.


### 6. Add a one-command public evidence bundle

Type: AFK

Labels: `type: slice`, `area: release`, `area: dashboard`, `status: ready`

What was built: `codex-observe evidence-bundle` now creates one synthetic local directory with a terminal output and reviewer README with key findings and a review checklist, `LIMITATIONS.md`, `PUBLIC_TOUR_FEEDBACK.md`, the demo database, aggregate report Markdown/JSON, aggregate comparison Markdown/JSON, audit JSON, visual QA artifacts, and a schema-versioned `codex-observe.evidence-bundle.v1` manifest.

Acceptance criteria:

- [x] The command writes all review artifacts under a caller-selected output directory.
- [x] The manifest records artifact paths, check status, privacy metadata, and `codex-observe.evidence-bundle.v1` schema version.
- [x] `--skip-visual` supports faster local and test runs while the default path collects visual QA evidence.
- [x] Text and JSON CLI output point reviewers at the generated evidence.
- [x] The generated bundle README gives reviewers a privacy-safe README and terminal key findings, review checklist, and key artifact paths and sharing cautions.
- [x] The bundle includes `LIMITATIONS.md` so known boundaries, approval-gated work, and next-work sources travel with reviewer evidence.
- [x] Tests cover the manifest contract, artifact creation, and actionable CLI output.

Status: Completed locally and retired from publishable issue state. The `.github/backlog/009-public-evidence-bundle.md` draft file was deleted after closeout.
## Historical gh publishing commands

Generate and validate fresh draft commands locally first:

```bash
python scripts/backlog_publish_plan.py
python scripts/backlog_publish_plan.py --json
```

The historical draft files were deleted because the slices are complete or because the remaining work is blocked on explicit human input. The completed `009` draft was also deleted after local implementation; do not publish it as a new issue.
