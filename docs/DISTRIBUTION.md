# Distribution Strategy

Codex Observe is currently distributed as a source checkout with an editable local install.

## Supported install path

```bash
git clone https://github.com/LangFelixAT/codex-observe.git
cd codex-observe
python -m pip install -e .
codex-observe self-check
```

For visual QA and screenshot verification only, the visual extra installs Playwright and Pillow:

```bash
python -m pip install -e ".[visual]"
python -m playwright install chromium
codex-observe self-check --visual --json
```

For contributor verification, install all local dev tools:

```bash
python -m pip install -e ".[dev]"
python -m playwright install chromium
codex-observe self-check --visual --json
```


To prove the source checkout works from a fresh virtual environment without touching private Codex logs, run the clean-install smoke gate. The smoke gate verifies `codex-observe self-check --json` and, for visual/dev extras, `codex-observe self-check --visual --json` as part of the installed console-script contract:

```bash
python scripts/clean_install_smoke.py --extra dev
```

Use `--extra visual` to verify only the visual dependency extra, or omit `--extra` for the minimum install path.
## Supported Python versions

- Python 3.10
- Python 3.11
- Python 3.12

The package metadata and CI workflow should stay aligned with this list.

## Versioning

Current version: `0.3.0`.

Until the first public package-index release, versions are repository release markers rather than PyPI release promises. Use patch versions for bug fixes and parser-shape support, minor versions for user-visible dashboard/reporting changes, and major versions only for incompatible database or CLI behavior.

## Not enabled yet

The following distribution paths are intentionally not enabled:

- PyPI publishing
- binary installers
- hosted dashboard mode
- telemetry or external report upload

Any package-index credentials, publishing automation, hosted mode, or telemetry must be explicitly approved before implementation.

## Data artifacts

Only synthetic demo data should be used in tests, docs, screenshots, and public artifacts. Non-synthetic local SQLite databases and generated screenshots remain ignored by default through `.gitignore`.

The local `sample_from_uploaded.sqlite` file is treated as a private local artifact. It should not be committed or used as release evidence.

## Release readiness

A source-distribution release candidate is ready when:

- `python scripts/clean_install_smoke.py --extra dev` succeeds and verifies `codex-observe self-check --json` and, for visual/dev extras, `codex-observe self-check --visual --json`, the reviewer evidence bundle README, manifest, limitations doc, and feedback issue template.
- `codex-observe evidence-bundle --out .artifacts/public-evidence` creates a synthetic reviewer bundle.
- `codex-observe audit --json` passes after the public evidence bundle exists.
- `ruff check` passes.
- `ruff format --check` passes.
- `pytest -q` passes.
- `codex-observe self-check --json` verifies source-install health without scanning private logs.
- `codex-observe paths --json` verifies the local path handoff without scanning private logs and keeps the guided `private-validate --newest-files 25 --json` command discoverable before lower-level manual follow-ups.
- `codex-observe demo` creates the synthetic database.
- `codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json` returns `status: ok`.
- `codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json` lists aggregate-only session summaries.
- `codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md` creates an aggregate-only report, and the dashboard Overview exposes matching selected-session Markdown/JSON downloads and aggregate comparison Markdown/JSON downloads.
- `codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json` creates the machine-readable report.
- `codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md` creates an aggregate-only comparison.
- `codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json` creates the machine-readable comparison.
- `python scripts/visual_qa.py` passes and produces desktop/narrow screenshots.
- `docs/RELEASE.md`, `CHANGELOG.md`, `README.md`, `docs/CURRENT.md`, `docs/LIMITATIONS.md`, `docs/PUBLIC_TOUR_FEEDBACK.md`, and `docs/TRACKING.md` match the release candidate.
