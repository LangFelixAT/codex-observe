from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_ci_workflow_runs_supported_quality_gate_commands() -> None:
    workflow = read(".github/workflows/ci.yml")

    assert 'python -m pip install -e ".[dev]"' in workflow
    assert "python scripts/clean_install_smoke.py --extra dev" in workflow
    assert "python -m playwright install --with-deps chromium" in workflow
    assert "ruff check" in workflow
    assert "ruff format --check" in workflow
    assert "pytest -q" in workflow
    assert "codex-observe audit --json" in workflow
    assert "codex-observe demo" in workflow
    assert (
        "codex-observe demo --sessions .artifacts/demo/sessions --keep-sessions --json"
        in workflow
    )
    assert (
        "codex-observe ingest .artifacts/demo/sessions --db .artifacts/demo/ingest-contract.sqlite --json"
        in workflow
    )
    assert (
        "codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json"
        in workflow
    )
    assert (
        "codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json"
        in workflow
    )
    assert (
        "codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md"
        in workflow
    )
    assert (
        "codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json"
        in workflow
    )
    assert ".artifacts/demo/run-report.json" in workflow
    assert "aggregate-run-report" in workflow
    assert "python scripts/visual_qa.py" in workflow
    assert "visual-qa-evidence" in workflow
    assert ".artifacts/visual/*.png" in workflow
    assert ".artifacts/visual/visual-qa-manifest.json" in workflow
    assert "actions/upload-artifact@v4" in workflow


def test_pr_template_requires_issue_verification_visual_evidence_and_privacy_review() -> (
    None
):
    template = read(".github/PULL_REQUEST_TEMPLATE.md")

    for required in [
        "## Linked issue",
        "`ruff check`",
        "`ruff format --check`",
        "`pytest -q`",
        "`python scripts/clean_install_smoke.py --extra dev`",
        "`codex-observe audit --json`",
        "`codex-observe demo`",
        "`codex-observe demo --sessions .artifacts/demo/sessions --keep-sessions --json`",
        "`codex-observe ingest .artifacts/demo/sessions --db .artifacts/demo/ingest-contract.sqlite --json`",
        "`codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json`",
        "`codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json`",
        "`codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md`",
        "`codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json`",
        "`codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md`",
        "`codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json`",
        "`python scripts/visual_qa.py`",
        "`python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json`",
        "`codex-observe evidence-bundle --out .artifacts/public-evidence`",
        "## Visual QA evidence",
        "Agent detail selector exercised",
        "metric card evidence",
        "operator-briefing evidence",
        ".artifacts/demo/codex_observe_demo.sqlite",
        "Aggregate report artifacts",
        "Public evidence bundle",
        ".artifacts/public-evidence/README.md",
        ".artifacts/public-evidence/evidence-bundle.json",
        "codex-observe.evidence-bundle.v1",
        ".artifacts/demo/run-report.md",
        ".artifacts/demo/run-report.json",
        ".artifacts/demo/run-comparison.md",
        ".artifacts/demo/run-comparison.json",
        "## Data/privacy review",
        "lint, format, tests, audit, Markdown/JSON report export, aggregate comparison, visual QA, reviewer evidence-bundle generation, and public evidence bundle upload",
        "docs/LIMITATIONS.md",
        "external attachment still has explicit human approval",
    ]:
        assert required in template
    assert "\\n" not in template


def test_backlog_records_completed_slices_no_publishable_drafts_and_external_write_guard() -> (
    None
):
    backlog = read("docs/BACKLOG.md")
    issue_files = sorted((ROOT / ".github/backlog").glob("*.md"))

    assert [path.name for path in issue_files] == []
    assert "requires explicit approval" in backlog
    assert "python scripts/backlog_publish_plan.py" in backlog
    assert "python scripts/backlog_publish_plan.py --json" in backlog
    assert "draft files were deleted" in backlog
    assert "There are currently no publishable local issue drafts" in backlog
    assert "Add a one-command public evidence bundle" in backlog
    assert "codex-observe evidence-bundle" in backlog
    assert "codex-observe.evidence-bundle.v1" in backlog


def test_current_state_handoff_covers_gates_evidence_and_remaining_blocker() -> None:
    current = read("docs/CURRENT.md")
    readme = read("README.md")

    for required in [
        "docs/AMAZING.md",
        "docs/RELEASE.md",
        "docs/LIMITATIONS.md",
        "docs/PUBLIC_TOUR_FEEDBACK.md",
        "docs/TRACKING.md",
        "codex-observe tour",
        "codex-observe demo --serve --host 127.0.0.1 --port 8501",
        "codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json",
        "structured `next_commands`",
        "copy-pasteable",
        "same `--db` path",
        "priority-preserving next-step recommendations",
        "ruff check",
        "ruff format --check",
        "pytest -q",
        "codex-observe audit --json",
        "aggregate triage assessment",
        "required_commands",
        "triage",
        "plain `codex-observe audit` prints",
        "python scripts/visual_qa.py",
        "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json",
        "metric card evidence",
        "operator-briefing evidence",
        "saved manifest schema/contract",
        "codex-observe evidence-bundle",
        "codex-observe.evidence-bundle.v1",
        "There is currently no publishable local issue draft",
        "issues #1-#8 are closed",
        "attaching generated artifacts externally still requires explicit human approval",
        "human-approved private input path",
    ]:
        assert required in current
    assert "docs/CURRENT.md" in readme
    assert "docs/LIMITATIONS.md" in readme
    assert "docs/TRACKING.md" in readme


def test_issue_templates_cover_main_work_types() -> None:
    templates = {
        path.name: path.read_text(encoding="utf-8")
        for path in (ROOT / ".github/ISSUE_TEMPLATE").glob("*.yml")
    }

    assert "implementation_slice.yml" in templates
    assert "parser_gap.yml" in templates
    assert "visual_polish.yml" in templates
    assert "public_tour_feedback.yml" in templates
    assert "config.yml" in templates
    assert "docs/TRACKING.md" in templates["config.yml"]
    assert "Visual/UI polish" in templates["visual_polish.yml"]
    assert "Parser/log shape gap" in templates["parser_gap.yml"]
    assert "Implementation slice" in templates["implementation_slice.yml"]
    assert "Public tour feedback" in templates["public_tour_feedback.yml"]
    assert "sample_from_uploaded.sqlite" not in templates["implementation_slice.yml"]
    assert "sample_from_uploaded.sqlite" not in templates["visual_polish.yml"]
    assert "ruff check" in templates["implementation_slice.yml"]
    assert "ruff format --check" in templates["implementation_slice.yml"]
    assert "ruff check" in templates["visual_polish.yml"]
    assert "ruff format --check" in templates["visual_polish.yml"]
    assert "codex-observe demo" in templates["visual_polish.yml"]
    for template_name in ["implementation_slice.yml", "visual_polish.yml"]:
        assert (
            "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json"
            in templates[template_name]
        )
        assert (
            "codex-observe evidence-bundle --out .artifacts/public-evidence"
            in templates[template_name]
        )
    assert "docs/LIMITATIONS.md" in templates["implementation_slice.yml"]
    assert "codex-observe audit --json" in templates["implementation_slice.yml"]
    assert "docs/REAL_LOG_FEEDBACK.md" in templates["parser_gap.yml"]
    assert "redaction manifest/privacy review" in templates["parser_gap.yml"]
    assert "events.payload_json" in templates["parser_gap.yml"]
    assert "docs/PUBLIC_TOUR_FEEDBACK.md" in templates["public_tour_feedback.yml"]
    assert "docs/LIMITATIONS.md" in templates["public_tour_feedback.yml"]
    assert "Do not paste private prompts" in templates["public_tour_feedback.yml"]
    assert (
        "codex-observe evidence-bundle --out .artifacts/public-evidence"
        in templates["public_tour_feedback.yml"]
    )


def test_contributing_guide_matches_quality_and_privacy_bar() -> None:
    contributing = read("CONTRIBUTING.md")
    readme = read("README.md")
    release = read("docs/RELEASE.md")
    ci = read(".github/workflows/ci.yml")

    for required in [
        'python -m pip install -e ".[dev]"',
        "codex-observe audit",
        "python scripts/clean_install_smoke.py --extra dev",
        "ruff check",
        "ruff format --check",
        "pytest -q",
        "python scripts/visual_qa.py",
        "## Traceability cadence",
        "small, reviewable checkpoints",
        "git status --short --branch",
        "push the branch",
        "codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json",
        "aggregate triage risk",
        "aggregate triage risk",
        "codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json",
        "codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md",
        "codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json",
        "codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md",
        "codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json",
        "python scripts/backlog_publish_plan.py",
        "python scripts/backlog_publish_plan.py --json",
        "docs/PUBLIC_TOUR_FEEDBACK.md",
        ".github/ISSUE_TEMPLATE/public_tour_feedback.yml",
        "docs/TRACKING.md",
        "codex-observe evidence-bundle --out .artifacts/public-evidence",
        "codex-observe audit --json",
        "events.payload_json",
        "explicit approval",
        "synthetic fixtures",
        "python scripts/redact_fixtures.py",
        "--verify-only",
        "privacy_review",
    ]:
        assert required in contributing

    assert "## Public Tour" in readme
    for tour_item in [
        "codex-observe tour",
        "codex-observe demo --serve --host 127.0.0.1 --port 8501",
        "Overview operator briefing",
        "Overview triage card",
        "codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json",
        "codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json",
        "aggregate triage risk",
        "aggregate triage risk",
        "codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md",
        "codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json",
        "codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md",
        "quick-read headline",
        "aggregate triage assessment",
        "aggregate triage assessment",
        "largest-change summary",
        "triage-risk movement",
        "diagnostic-change summary",
        "python scripts/visual_qa.py",
        "layout overflow/clipping checks",
        "metric card evidence",
        "aggregate triage assessment",
        "required_commands",
        ".artifacts/visual/visual-qa-manifest.json",
        "codex-observe evidence-bundle --out .artifacts/public-evidence",
        "reviewer README",
        "codex-observe.evidence-bundle.v1",
        "docs/PUBLIC_TOUR_FEEDBACK.md",
        ".github/ISSUE_TEMPLATE/public_tour_feedback.yml",
        "do not commit private logs, private SQLite databases, or unreviewed local artifacts",
    ]:
        assert tour_item in readme
    assert "CONTRIBUTING.md" in readme
    assert "python scripts/redact_fixtures.py" in readme
    assert "docs/REAL_LOG_FEEDBACK.md" in readme
    assert "codex-observe --version" in readme
    assert "codex-observe sessions --db <db>" in readme
    assert "structured `next_commands`" in readme
    assert "copy-pasteable" in readme
    assert "same `--db` path" in readme
    assert "diagnostic priority" in readme
    assert "valid but empty" in readme
    assert "next ingest or demo command" in readme
    for required_readme_gate in [
        "Ruff lint",
        "Ruff format checks",
        "regression suite",
        "clean-install smoke gate",
        "aggregate release audit",
        "synthetic demo generation",
        "aggregate-only session listing",
        "database doctor",
        "aggregate report export",
        "run-report.json",
        "visual QA",
        "evidence-bundle contract check",
        "workflow artifacts",
    ]:
        assert required_readme_gate in readme
    assert "CONTRIBUTING.md" in release
    distribution = read("docs/DISTRIBUTION.md")
    changelog = read("CHANGELOG.md")
    assert "ruff check" in release
    assert "ruff format --check" in release
    assert "python scripts/redact_fixtures.py" in release
    assert "docs/REAL_LOG_FEEDBACK.md" in release
    assert "run-report.json" in release
    assert "run-comparison.md" in release
    assert "run-comparison.json" in release
    assert "triage-risk" in release
    assert "visual QA manifest" in release
    assert "schema/contract evidence" in release
    assert "metric cards" in release
    assert "operator briefing" in release
    assert "required_commands" in release
    assert "structured `next_commands`" in release
    assert "docs/CURRENT.md" in release
    assert "remaining HITL blocker" in release
    assert "docs/LIMITATIONS.md" in release
    assert "release branch is pushed to `origin`" in release
    assert "tracking snapshot" in release
    assert "git status --short --branch" in release
    for required_distribution_item in [
        "codex-observe evidence-bundle --out .artifacts/public-evidence",
        "codex-observe audit --json",
        "run-report.json",
        "run-comparison.md",
        "run-comparison.json",
        "docs/PUBLIC_TOUR_FEEDBACK.md",
        "docs/TRACKING.md",
    ]:
        assert required_distribution_item in distribution
    for required_changelog_item in [
        "codex-observe tour --json",
        "privacy-safe feedback loop",
        "generated public evidence bundle artifact validation",
        "codex-observe evidence-bundle --out .artifacts/public-evidence --skip-visual --json",
        "run-comparison.json",
    ]:
        assert required_changelog_item in changelog
    assert "\\n" not in contributing
    assert "\\n" not in distribution
    for required_ci_item in [
        "Generate reviewer evidence bundle",
        "codex-observe evidence-bundle --out .artifacts/public-evidence",
        "Upload reviewer evidence bundle",
        "public-evidence-bundle",
        ".artifacts/public-evidence/**",
    ]:
        assert required_ci_item in ci


def test_completed_local_issue_records_stay_separate_from_active_drafts() -> None:
    active_drafts = [
        path.name for path in sorted((ROOT / ".github/backlog").glob("*.md"))
    ]
    assert active_drafts == []
    for retired in [
        "001-first-run-demo.md",
        "002-diagnostics-summary.md",
        "003-visual-regression.md",
        "004-log-shape-resilience.md",
        "005-package-for-real-users.md",
    ]:
        assert retired not in active_drafts

    backlog = read("docs/BACKLOG.md")
    for section in [
        "Polish first-run and demo experience",
        "Add a run diagnostics summary",
        "Build visual regression workflow",
        "Improve log shape resilience",
        "Package for real users",
    ]:
        assert section in backlog
    assert "No new dashboard-facing derived value was added" in backlog
    assert "one-command public evidence bundle" in backlog
    assert "codex-observe.evidence-bundle.v1" in backlog
    assert (
        "lint, format, tests, demo generation, session listing, database doctor, report export, visual QA, reviewer evidence bundle generation, final audit with saved visual evidence validation, and uploads artifacts"
        in backlog
    )


def test_limitations_doc_covers_current_boundaries_and_next_work_sources() -> None:
    limitations = read("docs/LIMITATIONS.md")
    release = read("docs/RELEASE.md")
    current = read("docs/CURRENT.md")

    for required in [
        "source checkout plus editable install",
        "PyPI publishing",
        "binary installers",
        "hosted mode",
        "telemetry",
        "approval-gated",
        "human-approved private input path",
        "docs/REAL_LOG_FEEDBACK.md",
        "reviewer evidence bundle",
        "explicit human approval",
        "Real-user feedback",
        "Fresh GitHub issues",
        "docs/PUBLIC_TOUR_FEEDBACK.md",
        "docs/TRACKING.md",
    ]:
        assert required in limitations
    assert "docs/LIMITATIONS.md" in release
    assert "docs/LIMITATIONS.md" in current


def test_public_tour_feedback_runbook_keeps_feedback_privacy_safe() -> None:
    runbook = read("docs/PUBLIC_TOUR_FEEDBACK.md")
    template = read(".github/ISSUE_TEMPLATE/public_tour_feedback.yml")

    for required in [
        "codex-observe tour",
        "codex-observe evidence-bundle --out .artifacts/public-evidence",
        "`codex-observe tour` ends by pointing reviewers",
        "README.md",
        "LIMITATIONS.md",
        "evidence-bundle.json",
        "Do Not Collect",
        "Private prompts",
        "docs/REAL_LOG_FEEDBACK.md",
        "explicit human approval",
    ]:
        assert required in runbook
    for required in [
        "Public tour feedback",
        "Do not paste private prompts",
        "docs/PUBLIC_TOUR_FEEDBACK.md",
        "docs/LIMITATIONS.md",
        "synthetic or reviewed-redacted",
    ]:
        assert required in template


def test_real_log_feedback_runbook_covers_privacy_review_and_closeout() -> None:
    runbook = read("docs/REAL_LOG_FEEDBACK.md")

    for required in [
        "human explicitly selects",
        "python scripts/redact_fixtures.py <sessions-or-jsonl> --out .artifacts/redacted-fixtures --limit 5",
        "python scripts/redact_fixtures.py .artifacts/redacted-fixtures --verify-only",
        "privacy_review",
        "schema_version",
        "No prompt text, message text, tool output, shell command, local path",
        "tests/fixtures/redacted/",
        "no new parser shape found",
        "candidate discarded during human privacy review",
    ]:
        assert required in runbook


def test_completed_fresh_draft_records_are_not_publishable_ready() -> None:
    next_wave = read("docs/NEXT_WAVE.md")

    assert (
        "completed fresh records `006`, `008`, and `009`, plus the blocked reminder record `007`, were deleted after closeout"
        in next_wave
    )
    assert "saved manifest schema/contract evidence" in next_wave
    assert "There is no current publishable draft record" in next_wave
    assert "codex-observe evidence-bundle" in next_wave
    assert "009" in next_wave
    assert "human-approved local input path still required" in next_wave


def test_tracking_snapshot_records_current_issue_state_and_publish_guard() -> None:
    tracking = read("docs/TRACKING.md")
    current = read("docs/CURRENT.md")
    config = read(".github/ISSUE_TEMPLATE/config.yml")

    for required in [
        "Checked: 2026-07-13",
        "gh issue list --limit 20 --state all --json number,title,state,labels,updatedAt,url",
        "All current GitHub issues are closed",
        "There is no `.github/backlog` directory",
        "no current publishable local issue draft",
        "python scripts/backlog_publish_plan.py --json",
        "explicit human approval",
        "Commit and push the implementation branch",
    ]:
        assert required in tracking
    for issue_number in range(1, 9):
        assert f"#{issue_number}" in tracking
    assert "docs/TRACKING.md" in current
    assert "docs/TRACKING.md" in config
