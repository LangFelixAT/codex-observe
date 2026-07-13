# Current Project State

This is the short handoff for returning to Codex Observe after time away. The deeper product bar lives in `docs/AMAZING.md`; known limitations and next-work sources live in `docs/LIMITATIONS.md`; release mechanics live in `docs/RELEASE.md`; completed local issue records live in `docs/BACKLOG.md` and `docs/NEXT_WAVE.md`.

## Product State

Codex Observe is currently a local-first workbench for understanding Codex session cost and context growth. A user can generate synthetic demo data with contrasting high- and low-risk runs, inspect the dashboard, export aggregate-only reports, compare runs, collect visual QA evidence, and produce a one-command public evidence bundle with a human-readable index without scanning private logs.

The current core loop is printed by `codex-observe tour`; `codex-observe tour --json` exposes the same synthetic-data commands as a schema-versioned automation contract. The loop is:

1. `codex-observe demo --serve --host 127.0.0.1 --port 8501`; `codex-observe demo --sessions .artifacts/demo/sessions --keep-sessions --json` exposes schema-versioned creation status while keeping synthetic sessions for ingest-contract checks
2. Inspect the Overview operator briefing, triage, diagnostics, cost-share metric cards, Agent detail, Timeline & jumps, Tools, Duplication, and Raw tables.
3. Run `codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json` to verify aggregate database health, `schema_version`, and structured `next_commands`; missing, empty, invalid, and unreadable database recovery hints are copy-pasteable and preserve the same `--db` path.
4. Use risk-aware `codex-observe sessions --json` to pick the highest-risk run through the `schema_version`-marked `status`, structured `recommended_session`, `recommendation_detail`, and `next_commands`, even when a newer low-risk follow-up exists, then export `.artifacts/demo/run-report.md` and `.artifacts/demo/run-report.json` with quick-read, aggregate triage assessment, cost-profile, ranked opportunity stack, next-run success target, diagnostics, structured next-action, and playbook evidence.
5. Compare report JSON files into `.artifacts/demo/run-comparison.md` and `.artifacts/demo/run-comparison.json` with triage-risk movement, opportunity-change movement, metric deltas, structured recommendation targets, and priority-preserving next-step recommendations for persisted diagnostics.
6. Run `python scripts/visual_qa.py` and verify `.artifacts/visual/visual-qa-manifest.json`.
7. Run `codex-observe evidence-bundle --out .artifacts/public-evidence` when reviewers need one synthetic local directory with a reviewer README, `LIMITATIONS.md`, report, comparison, audit, visual QA artifacts, and the `codex-observe.evidence-bundle.v1` manifest.
8. Use `docs/PUBLIC_TOUR_FEEDBACK.md` and `.github/ISSUE_TEMPLATE/public_tour_feedback.yml` for privacy-safe public-tour or reviewer-bundle feedback before turning observations into implementation issues.

## Quality Gates

Before treating a change as release-ready, run these commands. Generate `.artifacts/public-evidence` before the final audit so `codex-observe audit --json` can validate the public evidence bundle README, manifest, `LIMITATIONS.md`, reports, and audit artifact. The audit reports `schema_version`, lists required commands in `required_commands` for automation, and reports actionable failures in `failed_checks`; plain `codex-observe audit` prints the same required command list for humans and a `Failed checks` section when a gate fails:

```bash
ruff check
ruff format --check
pytest -q
python scripts/clean_install_smoke.py --extra dev
codex-observe demo --sessions .artifacts/demo/sessions --keep-sessions --json
codex-observe ingest .artifacts/demo/sessions --db .artifacts/demo/ingest-contract.sqlite --json
python scripts/visual_qa.py
python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json
codex-observe evidence-bundle --out .artifacts/public-evidence
codex-observe audit --json
```

The visual QA manifest records desktop and narrow screenshots, exercised tabs, Agent detail selector exercise, sidebar risk labels, metric card evidence, operator-briefing evidence, success-target evidence, screenshot metadata, and layout review; the final audit verifies the saved manifest schema/contract, referenced screenshots, layout review, sidebar risk labels, high-risk metric evidence, operator-briefing evidence, success-target evidence, and generated public evidence bundle artifacts.

## Tracking State

Completed local planning slices were retired instead of being published as stale GitHub issues. Fresh issue publication still requires explicit approval; public-tour observations should use `.github/ISSUE_TEMPLATE/public_tour_feedback.yml` and `docs/PUBLIC_TOUR_FEEDBACK.md` before becoming implementation issues.

The completed `.github/backlog/009-public-evidence-bundle.md` draft was implemented locally as `codex-observe evidence-bundle` and deleted after closeout. There is currently no publishable local issue draft; attaching generated artifacts externally still requires explicit human approval.
## Remaining Blocker

The real-log parser feedback loop is ready but cannot be completed without a human-approved private input path. Do not run real-log redaction against private sessions until a human explicitly selects the input path, and do not commit raw logs or unreviewed redacted output.
