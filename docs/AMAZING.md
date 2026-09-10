# Making Codex Observe Amazing

Status: achieved for Version 0.3.0, subject to the final release checklist.

## Product Bar

Codex Observe is successful when a Codex user can point it at local sessions and quickly answer:

- What made this run expensive?
- Which thread, prompt replay, tool output, approval context, or long-running session drove the cost?
- What single workflow habit should change next?
- What measurable result would prove that change helped?

The product should feel like a focused workbench, not a raw event viewer. The dashboard, terminal output, reports, and comparisons must agree on the diagnosis and next action.

## Quality Bar

- A new user can install from source and reach a useful synthetic dashboard from the README.
- Real-session review starts with bounded local validation and does not require committing private data.
- Ingestion is deterministic across re-imports, duplicate files, partial files, and known log-shape variation.
- Unknown event payloads remain locally inspectable instead of being silently discarded.
- Reports and the dashboard share analysis logic.
- Desktop and narrow layouts are readable, nonblank, and free of overlap or visible exceptions.
- Tests cover parser behavior, analysis, CLI contracts, report generation, dashboard helpers, privacy boundaries, packaging, and workflow docs.
- CI validates Python 3.10, 3.11, and 3.12 independently from browser and release evidence.
- User-facing exports include privacy guidance and terminal sharing warnings.
- Every completed slice has a GitHub issue, a focused commit, pushed history, and verification evidence.

## Version 0.3.0 Outcome

The release includes:

- a product-first README with a reviewed synthetic dashboard image;
- synthetic and real-session start paths;
- aggregate triage, recommendations, success targets, reports, and chronological comparisons;
- an answer-first Streamlit dashboard with bounded navigation and focused filters;
- clean-install, regression, visual, evidence-bundle, and release-audit workflows;
- a local-first privacy boundary and a documented reviewed-redaction path for fixtures.

The implementation history is retained in `docs/BACKLOG.md`, `docs/NEXT_WAVE.md`, and closed GitHub issues. It does not belong in the active product bar.

## Maintenance Mode

No feature work should be added merely to keep the project active. After Version 0.3.0, prioritize:

1. Reproducible bug fixes backed by focused tests.
2. Parser compatibility for observed log shapes using synthetic or reviewed-redacted fixtures.
3. Dependency, CI, documentation, and release maintenance.
4. Small usability corrections supported by visual evidence.
5. Real-user feedback that identifies a concrete failure in the existing workflow.

Create a fresh GitHub issue before implementation. Keep scope narrow, state the user-visible outcome, record the applicable quality gates, and update `docs/TRACKING.md`.

## Non-Goals

PyPI publishing, binary installers, hosted mode, telemetry, external report upload, accounts, collaboration, and cloud storage are not part of the achieved bar. They require a separate product decision rather than incremental scope creep.

The operational release procedure lives in `docs/RELEASE.md`; current status lives in `docs/CURRENT.md`; known boundaries live in `docs/LIMITATIONS.md`.
