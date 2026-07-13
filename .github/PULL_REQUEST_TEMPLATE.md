## Summary

<!-- What user-visible or maintainer-visible behavior changed? -->

## Linked issue

<!-- Link the vertical-slice issue this closes, or explain why this is preparatory work. -->

## Verification

- [ ] `ruff check`
- [ ] `ruff format --check`
- [ ] `pytest -q`
- [ ] `python scripts/clean_install_smoke.py --extra dev`
- [ ] `codex-observe audit`
- [ ] `codex-observe audit --json`
- [ ] `codex-observe demo`
- [ ] `codex-observe demo --sessions .artifacts/demo/sessions --keep-sessions --json` emits `codex-observe.demo.v1` with counts and next commands
- [ ] `codex-observe ingest .artifacts/demo/sessions --db .artifacts/demo/ingest-contract.sqlite --json` emits aggregate-only `codex-observe.ingest.v1` counts and skipped categories
- [ ] `codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json` includes aggregate-only session summaries, `schema_version`, and `recommended_session` for the highest-risk run
- [ ] `codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json` includes `schema_version`
- [ ] `codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md`
- [ ] `codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json`
- [ ] `codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md`
- [ ] `codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json`
- [ ] `python scripts/visual_qa.py`
- [ ] `python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json`
- [ ] `codex-observe evidence-bundle --out .artifacts/public-evidence`
- [ ] CI is expected to pass lint, format, tests, audit, Markdown/JSON report export, aggregate comparison, visual QA, reviewer evidence-bundle generation, and public evidence bundle upload

## Visual QA evidence

<!-- Required for UI-facing changes. Include tested DB source, viewport sizes, and screenshot artifact names. -->

- Database source: `.artifacts/demo/codex_observe_demo.sqlite` or another explicitly synthetic/redacted database
- Desktop screenshot:
- Narrow screenshot:
- Visual QA manifest: schema-versioned, path-safe `.artifacts/visual/visual-qa-manifest.json` with validated manifest evidence, referenced screenshot files, layout review, sidebar risk labels, and expected high-risk metric card evidence
- Aggregate report artifacts: `.artifacts/demo/run-report.md`, `.artifacts/demo/run-report.json`, `.artifacts/demo/run-comparison.md`, `.artifacts/demo/run-comparison.json`; JSON artifacts and audit output include `schema_version`, opportunity stack, and opportunity-change evidence
- Public evidence bundle: `.artifacts/public-evidence/README.md`, `.artifacts/public-evidence/evidence-bundle.json`, visual screenshots when included, and `codex-observe.evidence-bundle.v1` manifest evidence
- Tabs exercised: Overview, Agent detail, Timeline & jumps, Tools, Duplication, Raw tables
- Agent detail selector exercised: yes/no

## Data/privacy review

- [ ] No real session log content, private prompt text, file paths, or tool output were added to committed fixtures/docs/screenshots.
- [ ] Any screenshots or copied table rows are synthetic or intentionally safe to share.
- [ ] New external network writes, telemetry, publishing, or hosted behavior are absent or explicitly approved.
- [ ] `docs/LIMITATIONS.md` was updated or confirmed current for any new limitation, approval-gated behavior, or next-work source.
- [ ] Public evidence bundle artifacts were reviewed before attaching or publishing; external attachment still has explicit human approval.

## Release notes

<!-- One or two bullets a user would care about, or "None" for internal-only changes. -->
