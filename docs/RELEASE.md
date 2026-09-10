# Release Checklist

Version 0.3.0 is ready when a fresh source checkout installs, the automated quality and evidence gates pass, the public docs match the product, and the release can be reproduced without private session data.

## Scope

- Supported distribution is a source checkout with an editable install.
- Supported runtimes are Python 3.10, Python 3.11, and Python 3.12.
- PyPI publishing, binary installers, hosted mode, and telemetry are outside this release.
- Review [the current state](CURRENT.md), [distribution policy](DISTRIBUTION.md), [known limitations](LIMITATIONS.md), and [real-log workflow](REAL_LOG_FEEDBACK.md) before release.

## Prepare

Install the development dependencies and browser:

```bash
python -m pip install -e ".[dev]"
python -m playwright install --with-deps chromium
```

The development extra must provide Ruff, pytest, Playwright plus Pillow.

## Automated Gate

Run from the repository root:

```bash
ruff check
ruff format --check
pytest -q
codex-observe self-check --json
codex-observe self-check --visual --json
codex-observe paths --json
python scripts/clean_install_smoke.py --extra dev

codex-observe demo
codex-observe demo --sessions .artifacts/demo/sessions --keep-sessions --json
codex-observe ingest .artifacts/demo/sessions --db .artifacts/demo/ingest-contract.sqlite --json
codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json
codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json
codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md
codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json
codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md
codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json

python scripts/visual_qa.py
python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json
codex-observe evidence-bundle --out .artifacts/public-evidence
codex-observe audit --json
```

The final audit is a fast contract check, not a substitute for Ruff, pytest, clean-install smoke, or browser QA.

## Manual Review

- Open the desktop and narrow screenshots referenced by the visual QA manifest. Confirm the dashboard is nonblank, readable, free of overlap, and shows useful first-viewport guidance.
- Exercise Overview, Agent detail, Timeline, Tools, Duplication, and Raw tables against the synthetic database.
- Confirm empty and missing database states offer working next actions.
- When locally owned sessions are available, run `python scripts/visual_qa.py --profile real` and inspect the ignored evidence.
- Treat reports, comparisons, screenshots, and logs as potentially sensitive. Perform a human review before sharing any generated artifact.
- Confirm README install, demo, private validation, and dashboard commands still work.

## Privacy

- Normal product paths are local-only and do not intentionally upload session content.
- Keep `.artifacts/`, SQLite databases, raw JSONL, and unreviewed exports out of commits.
- Any fixture derived from real logs must follow `docs/REAL_LOG_FEEDBACK.md` and use `python scripts/redact_fixtures.py` plus its verification workflow.
- Confirm no new external network writes, telemetry, credentials, or hosted behavior were introduced.

## GitHub Release

- [ ] `pyproject.toml` and `codex_observe/__init__.py` contain the same version.
- [ ] `CHANGELOG.md` has a dated entry and accurate user-visible notes.
- [ ] `README.md`, `docs/CURRENT.md`, `docs/DISTRIBUTION.md`, and `docs/LIMITATIONS.md` describe the shipped state.
- [ ] `git status --short --branch` is clean and synchronized after the release branch is pushed to `origin`.
- [ ] GitHub Actions reports green Core quality jobs for every supported Python version.
- [ ] GitHub Actions reports a green Visual and release evidence job with uploaded reports, screenshots, manifest, and evidence bundle.
- [ ] The repository description and topics are current.
- [ ] Create and publish the `v0.3.0` GitHub release from the verified commit.
- [ ] Close the tracking issue with links to the commit, CI run, and release.

## Release Notes

Call out the local-first workflow, supported Python versions, synthetic quick start, bounded real-session validation, visual QA, privacy boundary, source-only distribution, and limitations. Do not claim PyPI or hosted availability.

See `CONTRIBUTING.md` for development practice and `docs/TRACKING.md` for issue and push traceability.
