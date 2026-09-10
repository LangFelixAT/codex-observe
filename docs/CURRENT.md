# Current Project State

Checked: 2026-09-10.

## Release Status

Version 0.3.0 is a release candidate being finalized under GitHub Issue #20. The product work is complete; the active task is repository cleanup, final verification, and publishing. No feature work is planned for this release.

The supported distribution is a source checkout with an editable install. PyPI, installers, hosted mode, and telemetry remain out of scope.

## Product

Codex Observe is a local-first observability workbench for Codex session logs. It turns local JSONL history into aggregate diagnostics, identifies the most useful next-run habit, and provides a measurable target for checking whether that habit helped.

The current experience includes:

- a two-run synthetic demo and `codex-observe demo --serve` first-run path;
- bounded real-session ingestion through `codex-observe paths` and `codex-observe private-validate`;
- terminal session triage, Markdown/JSON reports, and chronological comparisons;
- an answer-first Streamlit dashboard with search, Risk and Focus filters, bounded history, run details, reports, comparisons, and downloads;
- local evidence bundles and release auditing for reproducible review.

## Supported Environment

- Python 3.10
- Python 3.11
- Python 3.12
- Windows, macOS, or Linux where the Python dependencies and a Chromium browser can run

## Validation State

- The local regression suite contains 296 tests.
- Ruff lint and formatting gates pass.
- Clean-install smoke exercises the package, CLI entry point, demo, and audit in a fresh environment.
- CI is split into a Python-version Core quality matrix and an independent Visual and release evidence job.
- Browser QA covers desktop and narrow viewports, all dashboard tabs, onboarding states, filters, pagination, downloads, comparisons, and screenshot integrity.
- The reviewed synthetic dashboard image in `docs/assets/dashboard-overview.png` is safe for the public README.

## Real Sessions

The real Codex sessions location resolved by `codex-observe paths` has been exercised through the bounded private-validation workflow. Real-session dashboard behavior has also been checked with:

```bash
python scripts/visual_qa.py --profile real
```

Those databases, reports, screenshots, and session-derived metrics remain in ignored local artifacts. No private session content is required for CI or committed release evidence.

## Remaining Release Work

1. Finish the concise documentation cleanup and rerun all local gates.
2. Confirm the final GitHub Actions run is green on Python 3.10, 3.11, and 3.12 and for browser evidence.
3. Set the GitHub repository description and topics.
4. Publish the `v0.3.0` GitHub release and close Issue #20 with evidence.

## Maintainer Map

- Product bar and maintenance posture: `docs/AMAZING.md`
- Release procedure: `docs/RELEASE.md`
- Known boundaries: `docs/LIMITATIONS.md`
- GitHub issue snapshot and push cadence: `docs/TRACKING.md`
- Distribution policy: `docs/DISTRIBUTION.md`
- Real-log fixture process: `docs/REAL_LOG_FEEDBACK.md`
- Historical completed work: `docs/BACKLOG.md` and `docs/NEXT_WAVE.md`
