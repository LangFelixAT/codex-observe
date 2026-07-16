# Limitations and Next Work

This project is intentionally local-first and source-install only right now. The current public tour and evidence bundle are designed to help reviewers evaluate the product with synthetic data before anyone points it at private Codex logs.

## Current Limitations

- Distribution is source checkout plus editable install. PyPI publishing, binary installers, hosted mode, package-index credentials, and publishing automation remain approval-gated.
- There is no telemetry or hosted sharing mode. The app does not intentionally send session content to external services.
- Parser coverage is strong for known synthetic, Codex `total_token_usage`, OpenAI-style `usage`, redacted-style fixture shapes, and one human-approved private input path checkpoint; large private histories can be sampled first with `--newest-files <n>`, and real-session usefulness testing has already hardened long-running session recommendations, but additional real-log parser expansion remains dependent on human-reviewed redacted fixture promotion.
- Screenshots, copied dashboard rows, exported tables, issue bodies, and evidence bundles are local artifacts and may still contain sensitive paths or aggregate clues. Review generated artifacts before attaching or publishing them.
- The reviewer evidence bundle is synthetic and local-only by default, and it includes a copy of this limitations document for review context. Attaching it externally still requires explicit human approval.
- Completed local backlog drafts were retired instead of published as stale GitHub issues. Fresh GitHub issues should represent new, demoable work only; `docs/TRACKING.md` records the current issue snapshot, local draft state, and approval-gated publishing workflow.

## Real-Log Privacy Gate

The first real-log feedback checkpoint has been exercised against a human-approved private input path. Future parser-shape expansion still requires `docs/REAL_LOG_FEEDBACK.md`, reviewed-redacted fixtures, and explicit human privacy review before anything moves out of ignored `.artifacts/` paths. Do not commit raw logs, private SQLite databases, or unreviewed redacted output.

## Next Planned Work Sources

- Real-user feedback from trying the public tour and reviewer evidence bundle should be privacy-safe and collected with `.github/ISSUE_TEMPLATE/public_tour_feedback.yml` and `docs/PUBLIC_TOUR_FEEDBACK.md`.
- Human-reviewed redacted fixture gaps from `docs/REAL_LOG_FEEDBACK.md`, including any future gaps found after the first private real-log checkpoint.
- Explicitly approved distribution work if the project moves beyond source installs.
- Fresh vertical-slice issue drafts only when the work is actionable, demoable, and not merely a human-input reminder; scaffold them with `python scripts/backlog_publish_plan.py --new-draft` so tests, visual QA, privacy review, and blocked-by sections are present before validation.
