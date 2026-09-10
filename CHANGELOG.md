# Changelog

All notable changes to Codex Observe are documented here. The project follows semantic versioning for repository releases.

## [Unreleased]

No unreleased changes.

## [0.3.0] - 2026-09-10

### Highlights

- Delivered a local-first workbench that explains what made a Codex run expensive, recommends one concrete next-run habit, and defines a measurable proof target.
- Added a two-run synthetic demo, an answer-first Streamlit dashboard, aggregate Markdown/JSON reports, and run-to-run comparison.
- Added a bounded real-session validation path that resolves the local Codex sessions directory, samples the newest files first, and keeps generated evidence ignored.

### Analysis and workflow

- Ranked session risk and primary Focus across duration, dominant threads, guardian overhead, prompt replay, uncached input, tool output, and total tokens.
- Added portfolio briefings, opportunity stacks, next-run checklists, copy-ready run briefs, and success targets shared by terminal reports and the dashboard.
- Added chronological comparison with explicit Before/After context, triage movement, metric deltas, opportunity change, and next validation commands.
- Bounded dashboard history to 50 conversations per page with stable selection, search, Risk and Focus filters, and range-aware Previous/Next navigation.
- Added agent detail, token-jump timeline, tool usage, large tool-output, prompt duplication, and raw aggregate table views.

### Reliability and privacy

- Added defensive parsing for known Codex and OpenAI-style usage payloads while retaining unknown events for local inspection.
- Made imports deterministic across re-imports, duplicate files, malformed rows, empty files, and missing session metadata.
- Added privacy-safe `paths`, `private-validate`, `doctor`, `sessions`, `report`, `compare`, and redacted-fixture workflows that avoid raw content in normal terminal output.
- Added a synthetic evidence bundle and release audit covering package health, CLI contracts, reports, comparisons, documentation, and reviewer artifacts.
- Isolated test fixtures from saved screenshots and upgraded visual evidence to manifest schema v2 with exact byte-size and SHA-256 integrity for primary and onboarding captures.

### Validation

- 296 tests cover ingestion, analysis, reports, CLI behavior, dashboard helpers, evidence generation, privacy boundaries, packaging, and workflow documentation.
- CI runs the regression suite on Python 3.10, 3.11, and 3.12, with an independent browser and release-evidence lane.
- Automated visual QA exercises desktop and narrow layouts, every dashboard tab, empty states, filters, pagination, comparisons, downloads, and layout-overflow checks.
- Clean-install smoke verifies the source install, console entry point, synthetic demo, evidence bundle, release audit, Playwright, and Pillow in a fresh environment.

[Unreleased]: https://github.com/LangFelixAT/codex-observe/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/LangFelixAT/codex-observe/releases/tag/v0.3.0
