from __future__ import annotations

import json
import os

import sys
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from codex_observe import cli


def dashboard_path() -> str:
    return str(Path(cli.__file__).with_name("dashboard.py"))


def test_serve_passes_host_and_port_to_streamlit_before_app_separator(
    tmp_path: Path,
) -> None:
    db = tmp_path / "observe.sqlite"

    with patch("codex_observe.cli.subprocess.call", return_value=0) as call:
        result = cli.main(
            ["serve", "--host", "127.0.0.1", "--port", "9999", "--db", str(db)]
        )

    assert result == 0
    call.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            dashboard_path(),
            "--server.address",
            "127.0.0.1",
            "--server.port",
            "9999",
            "--",
            "--db",
            str(db),
        ]
    )


def test_scan_and_serve_uses_same_streamlit_host_port_ordering(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    db = tmp_path / "observe.sqlite"

    with (
        patch("codex_observe.cli.ingest") as ingest,
        patch("codex_observe.cli.subprocess.call", return_value=0) as call,
    ):
        ingest.return_value.files_matched = 0
        ingest.return_value.files_skipped_by_limit = 0
        ingest.return_value.newest_files_limit = None
        ingest.return_value.files_seen = 0
        ingest.return_value.files_imported = 0
        ingest.return_value.duplicate_files = 0
        ingest.return_value.threads = 0
        ingest.return_value.events = 0
        result = cli.main(
            [
                "scan-and-serve",
                str(sessions),
                "--host",
                "0.0.0.0",
                "--port",
                "8502",
                "--db",
                str(db),
            ]
        )

    assert result == 0
    ingest.assert_called_once_with(str(sessions), str(db), newest_files=None)
    call.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            dashboard_path(),
            "--server.address",
            "0.0.0.0",
            "--server.port",
            "8502",
            "--",
            "--db",
            str(db),
        ]
    )


def test_scan_and_serve_forwards_newest_files_limit(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    db = tmp_path / "observe.sqlite"

    with (
        patch("codex_observe.cli.ingest") as ingest,
        patch("codex_observe.cli.subprocess.call", return_value=0),
    ):
        ingest.return_value.files_matched = 10
        ingest.return_value.files_skipped_by_limit = 7
        ingest.return_value.newest_files_limit = 3
        ingest.return_value.files_seen = 3
        ingest.return_value.files_imported = 3
        ingest.return_value.duplicate_files = 0
        ingest.return_value.threads = 3
        ingest.return_value.events = 9
        result = cli.main(
            [
                "scan-and-serve",
                str(sessions),
                "--newest-files",
                "3",
                "--db",
                str(db),
            ]
        )

    assert result == 0
    ingest.assert_called_once_with(str(sessions), str(db), newest_files=3)


def test_serve_passes_host_without_port_before_app_separator(tmp_path: Path) -> None:
    db = tmp_path / "observe.sqlite"

    with patch("codex_observe.cli.subprocess.call", return_value=0) as call:
        cli.main(["serve", "--host", "127.0.0.1", "--db", str(db)])

    call.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            dashboard_path(),
            "--server.address",
            "127.0.0.1",
            "--",
            "--db",
            str(db),
        ]
    )


def test_serve_passes_port_without_host_before_app_separator(tmp_path: Path) -> None:
    db = tmp_path / "observe.sqlite"

    with patch("codex_observe.cli.subprocess.call", return_value=0) as call:
        cli.main(["serve", "--port", "9999", "--db", str(db)])

    call.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            dashboard_path(),
            "--server.port",
            "9999",
            "--",
            "--db",
            str(db),
        ]
    )


def write_valid_visual_manifest(root: Path) -> None:
    from PIL import Image, ImageDraw

    manifest_path = root / cli.VISUAL_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tabs = list(cli.EXPECTED_VISUAL_TABS)
    viewports = {
        "desktop": {"width": 1440, "height": 1000},
        "narrow": {"width": 390, "height": 900},
    }
    viewport_results = {}
    for name, viewport in viewports.items():
        screenshot_path = manifest_path.parent / f"dashboard-{name}.png"
        image = Image.new("RGB", (viewport["width"], viewport["height"]), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, viewport["width"], 140), fill=(33, 104, 105))
        draw.rectangle(
            (24, 180, min(viewport["width"] - 24, 680), 360),
            fill=(248, 250, 249),
            outline=(23, 32, 38),
            width=4,
        )
        draw.text((36, 210), "Codex Observe visual QA evidence", fill=(23, 32, 38))
        image.save(screenshot_path)
        viewport_results[name] = {
            "viewport": viewport,
            "screenshot": {
                "filename": screenshot_path.name,
                "width": viewport["width"],
                "height": viewport["height"],
                "bytes": screenshot_path.stat().st_size,
            },
            "tabs_exercised": tabs,
            "quick_read_evidence": list(cli.EXPECTED_VISUAL_QUICK_READ_EVIDENCE),
            "agent_detail_selector_exercised": True,
            "layout_review": {
                "viewport_width": viewport["width"],
                "document_width": viewport["width"],
                "overflowing_elements": [],
                "clipped_text_elements": [],
            },
            "sidebar_risk_labels": sorted(cli.EXPECTED_VISUAL_RISK_LABELS),
            "sidebar_session_details": sorted(
                cli.EXPECTED_VISUAL_SIDEBAR_SESSION_DETAILS
            ),
            "risk_distributions": [
                {
                    "label": "Risk distribution",
                    "body": "Risk distribution 2 imported conversations High risk 1 Medium risk 0 Low risk 1 Unknown 0",
                }
            ],
            "metric_cards": [
                {"label": label, "value": value}
                for label, value in cli.EXPECTED_VISUAL_METRICS.items()
            ],
            "success_targets": [dict(cli.EXPECTED_VISUAL_SUCCESS_TARGET)],
            "download_controls": sorted(cli.EXPECTED_VISUAL_DOWNLOAD_CONTROLS),
            "operator_briefings": [
                {
                    "label": "Operator briefing",
                    "heading": "High risk: Dominant thread concentration",
                    "action": "Inspect the largest thread before changing workflow.",
                    "best_habit": cli.EXPECTED_VISUAL_OPERATOR_BRIEFING["best_habit"],
                    "scale": cli.EXPECTED_VISUAL_OPERATOR_BRIEFING["scale"],
                    "proof_target": cli.EXPECTED_VISUAL_OPERATOR_BRIEFING[
                        "proof_target"
                    ],
                }
            ],
            "review_paths": [
                {
                    "label": "Next review path",
                    "body": "Next review path Save report JSON Compare workflow change Validate next run File safe feedback PUBLIC_TOUR_FEEDBACK.md",
                }
            ],
            "next_run_checklists": [
                {
                    "label": "Next run checklist",
                    "body": "Next run checklist Before next run During next run After next run Set a stop condition for the dominant thread largest_thread_share_pct Export next-run-report.json",
                }
            ],
            "feedback_handoffs": [
                {
                    "label": "Safe feedback handoff",
                    "body": "Safe feedback handoff docs/PUBLIC_TOUR_FEEDBACK.md .github/ISSUE_TEMPLATE/public_tour_feedback.yml synthetic or reviewed-redacted aggregate evidence codex-observe report JSON or Markdown private prompts Do not collect",
                }
            ],
            "comparison_previews": [
                {
                    "label": "Comparison quick read: regressed",
                    "body": "Comparison quick read: regressed Verdict: regressed; largest change: Total tokens +49.1k (regressed). Triage movement: regressed Next step: Inspect new diagnostic first: Repeated prompt blocks. Next validation command codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json",
                }
            ],
            "comparison_review_paths": [
                {
                    "label": "Comparison review path",
                    "body": "Comparison review path Read the verdict Act on the recommendation Export the next run Compare against this after run File safe feedback",
                }
            ],
            "comparison_deltas": [
                {
                    "label": "Total tokens",
                    "before_after": "8.4k -> 57.5k",
                    "delta": "regressed: 49.1k (584.6%)",
                },
                {
                    "label": "Usage snapshots",
                    "before_after": "3 -> 6",
                    "delta": "changed: 3 (100.0%)",
                },
                {
                    "label": "Largest thread tokens",
                    "before_after": "2.9k -> 33.2k",
                    "delta": "regressed: 30.3k (1044.8%)",
                },
            ],
        }

    empty_states = {}
    for state_name, title in cli.EXPECTED_VISUAL_EMPTY_STATES.items():
        state_viewports = {}
        for name, viewport in viewports.items():
            screenshot_path = (
                manifest_path.parent / f"dashboard-{state_name}-{name}.png"
            )
            image = Image.new("RGB", (viewport["width"], viewport["height"]), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, viewport["width"], 120), fill=(33, 104, 105))
            draw.text((36, 180), title, fill=(23, 32, 38))
            image.save(screenshot_path)
            state_viewports[name] = {
                "viewport": viewport,
                "screenshot": {
                    "filename": screenshot_path.name,
                    "width": viewport["width"],
                    "height": viewport["height"],
                    "bytes": screenshot_path.stat().st_size,
                },
                "title": title,
                "body": "Use the commands below to continue.",
                "commands": [
                    {
                        "label": "Try synthetic data",
                        "command": "codex-observe demo --serve --db demo.sqlite --host 127.0.0.1 --port 8501",
                    },
                    {
                        "label": "Ingest private logs locally",
                        "command": "codex-observe ingest ~/.codex/sessions --db demo.sqlite",
                    },
                    {
                        "label": "Check database health",
                        "command": "codex-observe doctor --db demo.sqlite",
                    },
                ],
                "layout_review": {
                    "viewport_width": viewport["width"],
                    "document_width": viewport["width"],
                    "overflowing_elements": [],
                    "clipped_text_elements": [],
                },
            }
        empty_states[state_name] = {
            "database": f".artifacts/visual/{state_name}.sqlite",
            "viewports": state_viewports,
        }

    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": cli.VISUAL_MANIFEST_SCHEMA_VERSION,
                "url": "http://127.0.0.1:8501",
                "database": ".artifacts/demo/codex_observe_demo.sqlite",
                "output_dir": ".artifacts/visual",
                "viewports": viewport_results,
                "empty_states": empty_states,
                "checks": {
                    "tabs_expected": tabs,
                    "streamlit_exception_text": "not found",
                    "screenshot_quality": "passed",
                    "layout_review": "passed",
                    "empty_states": "passed",
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def preserve_visual_manifest():
    manifest_path = Path.cwd() / cli.VISUAL_MANIFEST
    previous_manifest = manifest_path.read_bytes() if manifest_path.exists() else None
    return manifest_path, previous_manifest


def restore_visual_manifest(
    manifest_path: Path, previous_manifest: bytes | None
) -> None:
    if previous_manifest is None:
        manifest_path.unlink(missing_ok=True)
    else:
        manifest_path.write_bytes(previous_manifest)


def test_visual_manifest_evidence_failures_validate_saved_sidebar_metric_and_success_target_evidence(
    tmp_path: Path,
) -> None:
    assert cli.visual_manifest_evidence_failures(tmp_path) == [
        "missing .artifacts/visual/visual-qa-manifest.json; "
        "run `python scripts/visual_qa.py`, then "
        "`python scripts/visual_qa.py --verify-manifest "
        ".artifacts/visual/visual-qa-manifest.json`"
    ]

    write_valid_visual_manifest(tmp_path)
    manifest_path = tmp_path / cli.VISUAL_MANIFEST

    assert cli.visual_manifest_evidence_failures(tmp_path) == []

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["viewports"]["desktop"]["sidebar_risk_labels"] = ["High risk"]
    payload["viewports"]["desktop"]["sidebar_session_details"] = []
    payload["viewports"]["desktop"]["quick_read_evidence"] = [
        {"tab": "Overview", "text": "Run triage"}
    ]
    payload["viewports"]["narrow"]["metric_cards"][1]["value"] = "2.9k tokens (34.5%)"
    payload["viewports"]["desktop"]["success_targets"][0]["current"] = "34.5%"
    payload["viewports"]["desktop"]["operator_briefings"][0]["best_habit"] = (
        "Read raw tables"
    )
    payload["viewports"]["desktop"]["download_controls"] = ["Download report MD"]
    payload["viewports"]["desktop"]["feedback_handoffs"] = []
    payload["viewports"]["desktop"]["comparison_deltas"] = [
        {"label": "Total tokens", "delta": "improved: -49.1k (-85.4%)"}
    ]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    failures = cli.visual_manifest_evidence_failures(tmp_path)

    assert "visual QA manifest desktop missing risk labels: Low risk" in failures
    assert (
        "visual QA manifest desktop missing sidebar session details: 6 snapshots"
        in failures
    )
    assert (
        "visual QA manifest desktop quick-read evidence missing Agent detail: Thread brief"
        in failures
    )
    assert (
        "visual QA manifest narrow Largest thread expected 33.2k tokens (57.7%), got 2.9k tokens (34.5%)"
        in failures
    )
    assert (
        "visual QA manifest desktop success target current expected 57.7%, got 34.5%"
        in failures
    )

    assert (
        "visual QA manifest desktop operator briefing best_habit expected Set a stop condition for the dominant thread, got Read raw tables"
        in failures
    )
    assert (
        "visual QA manifest desktop missing report download controls: Download comparison JSON, Download comparison MD, Download report JSON"
        in failures
    )
    assert (
        "visual QA manifest desktop comparison delta Total tokens missing direction: regressed"
        in failures
    )
    assert (
        "visual QA manifest desktop missing comparison delta: Usage snapshots"
        in failures
    )
    assert (
        "visual QA manifest desktop missing comparison delta: Largest thread tokens"
        in failures
    )
    assert (
        "visual QA manifest missing desktop safe feedback handoff evidence" in failures
    )


def test_visual_manifest_evidence_rejects_stale_minimal_manifest_shape(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / cli.VISUAL_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "viewports": {
                    name: {
                        "sidebar_risk_labels": ["High risk", "Low risk"],
                        "sidebar_session_details": ["6 snapshots"],
                        "metric_cards": [
                            {"label": label, "value": value}
                            for label, value in cli.EXPECTED_VISUAL_METRICS.items()
                        ],
                        "success_targets": [dict(cli.EXPECTED_VISUAL_SUCCESS_TARGET)],
                        "download_controls": sorted(
                            cli.EXPECTED_VISUAL_DOWNLOAD_CONTROLS
                        ),
                    }
                    for name in ["desktop", "narrow"]
                }
            }
        ),
        encoding="utf-8",
    )

    failures = cli.visual_manifest_evidence_failures(tmp_path)

    assert "visual QA manifest checks must be an object" in failures
    assert "visual QA manifest desktop tabs_exercised incomplete" in failures
    assert "visual QA manifest desktop missing quick-read evidence" in failures
    assert "visual QA manifest desktop missing screenshot metadata" in failures
    assert "visual QA manifest desktop missing layout review" in failures
    assert "visual QA manifest missing desktop operator briefing evidence" in failures
    assert (
        "visual QA manifest missing desktop safe feedback handoff evidence" in failures
    )
    assert "visual QA manifest missing desktop comparison preview evidence" in failures
    assert (
        "visual QA manifest missing desktop comparison review path evidence" in failures
    )
    assert "visual QA manifest missing desktop comparison delta evidence" in failures
    assert (
        "visual QA manifest narrow agent detail selector was not exercised" in failures
    )


def test_issue_template_failures_require_evidence_privacy_and_limits(
    tmp_path: Path,
) -> None:
    template_dir = tmp_path / ".github" / "ISSUE_TEMPLATE"
    template_dir.mkdir(parents=True)
    (template_dir / "implementation_slice.yml").write_text(
        "Implementation slice\n"
        "codex-observe audit --json\n"
        "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json\n"
        "codex-observe evidence-bundle --out .artifacts/public-evidence\n"
        "docs/LIMITATIONS.md\n",
        encoding="utf-8",
    )
    (template_dir / "visual_polish.yml").write_text(
        "Visual/UI polish\n"
        "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json\n"
        "codex-observe evidence-bundle --out .artifacts/public-evidence\n"
        "layout review\n"
        "expected high-risk metric card evidence\n",
        encoding="utf-8",
    )
    (template_dir / "parser_gap.yml").write_text(
        "Parser/log shape gap\n"
        "docs/REAL_LOG_FEEDBACK.md\n"
        "redaction manifest/privacy review\n"
        "events.payload_json\n"
        "codex-observe audit --json\n",
        encoding="utf-8",
    )
    (template_dir / "public_tour_feedback.yml").write_text(
        "Public tour feedback\n"
        "codex-observe tour\n"
        "codex-observe tour --json\n"
        "codex-observe evidence-bundle --out .artifacts/public-evidence\n"
        "codex-observe audit --json\n"
        "codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite\n"
        "codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite\n"
        "codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json\n"
        "codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json\n"
        "python scripts/visual_qa.py\n"
        "report/comparison terminal `Next commands` blocks\n"
        "docs/PUBLIC_TOUR_FEEDBACK.md\n"
        "docs/LIMITATIONS.md\n"
        "Do not paste private prompts\n",
        encoding="utf-8",
    )

    assert cli.issue_template_failures(tmp_path) == []

    (template_dir / "visual_polish.yml").write_text(
        "Visual/UI polish\n", encoding="utf-8"
    )

    failures = cli.issue_template_failures(tmp_path)

    assert (
        ".github/ISSUE_TEMPLATE/visual_polish.yml missing codex-observe evidence-bundle --out .artifacts/public-evidence"
        in failures
    )
    assert ".github/ISSUE_TEMPLATE/visual_polish.yml missing layout review" in failures


def test_ci_evidence_bundle_failures_require_generation_and_upload(
    tmp_path: Path,
) -> None:
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "Generate reviewer evidence bundle\n"
        "codex-observe evidence-bundle --out .artifacts/public-evidence\n"
        "Upload reviewer evidence bundle\n"
        "public-evidence-bundle\n"
        ".artifacts/public-evidence/**\n",
        encoding="utf-8",
    )

    assert cli.ci_evidence_bundle_failures(tmp_path) == []

    workflow.write_text("codex-observe evidence-bundle\n", encoding="utf-8")

    failures = cli.ci_evidence_bundle_failures(tmp_path)

    assert "ci workflow missing Generate reviewer evidence bundle" in failures
    assert "ci workflow missing public-evidence-bundle" in failures


def test_public_evidence_bundle_artifact_failures_require_limitations(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "public-evidence"
    manifest_path, previous_manifest = preserve_visual_manifest()
    try:
        write_valid_visual_manifest(Path.cwd())
        status, manifest = cli.public_evidence_bundle(str(bundle), run_visual=False)
    finally:
        restore_visual_manifest(manifest_path, previous_manifest)

    assert status == 0
    assert manifest["artifacts"]["limitations_markdown"] == "LIMITATIONS.md"
    assert manifest["artifacts"]["feedback_runbook"] == "PUBLIC_TOUR_FEEDBACK.md"
    assert (
        manifest["artifacts"]["feedback_issue_template"]
        == ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
    )
    assert cli.public_evidence_bundle_artifact_failures(Path.cwd(), bundle) == []

    (bundle / "LIMITATIONS.md").write_text(
        "# Limitations and Next Work\n",
        encoding="utf-8",
    )

    failures = cli.public_evidence_bundle_artifact_failures(Path.cwd(), bundle)

    assert any("approval-gated" in failure for failure in failures)
    assert any("explicit human approval" in failure for failure in failures)
    (bundle / "PUBLIC_TOUR_FEEDBACK.md").write_text(
        "# Public Tour Feedback\n",
        encoding="utf-8",
    )

    failures = cli.public_evidence_bundle_artifact_failures(Path.cwd(), bundle)

    assert any("Do Not Collect" in failure for failure in failures)

    (bundle / ".github" / "ISSUE_TEMPLATE" / "public_tour_feedback.yml").write_text(
        "name: Public tour feedback\n",
        encoding="utf-8",
    )

    failures = cli.public_evidence_bundle_artifact_failures(Path.cwd(), bundle)

    assert any("Privacy review" in failure for failure in failures)

    loaded = json.loads((bundle / "evidence-bundle.json").read_text(encoding="utf-8"))
    without_summary = dict(loaded)
    without_summary.pop("review_summary")
    (bundle / "evidence-bundle.json").write_text(
        json.dumps(without_summary), encoding="utf-8"
    )

    failures = cli.public_evidence_bundle_artifact_failures(Path.cwd(), bundle)

    assert "evidence bundle manifest missing review_summary" in failures

    loaded.pop("review_checklist")
    (bundle / "evidence-bundle.json").write_text(json.dumps(loaded), encoding="utf-8")

    failures = cli.public_evidence_bundle_artifact_failures(Path.cwd(), bundle)

    assert "evidence bundle manifest missing review_checklist" in failures

    loaded = json.loads((bundle / "evidence-bundle.json").read_text(encoding="utf-8"))
    loaded.pop("action_plan")
    (bundle / "evidence-bundle.json").write_text(json.dumps(loaded), encoding="utf-8")

    failures = cli.public_evidence_bundle_artifact_failures(Path.cwd(), bundle)

    assert "evidence bundle manifest missing action_plan" in failures

    loaded = json.loads((bundle / "evidence-bundle.json").read_text(encoding="utf-8"))
    loaded.pop("validation_commands")
    (bundle / "evidence-bundle.json").write_text(json.dumps(loaded), encoding="utf-8")

    failures = cli.public_evidence_bundle_artifact_failures(Path.cwd(), bundle)

    assert "evidence bundle manifest missing validation_commands" in failures

    without_handoff = dict(manifest)
    without_handoff.pop("feedback_handoff")
    (bundle / "evidence-bundle.json").write_text(
        json.dumps(without_handoff), encoding="utf-8"
    )

    failures = cli.public_evidence_bundle_artifact_failures(Path.cwd(), bundle)

    assert "evidence bundle manifest missing feedback_handoff" in failures


def test_public_evidence_bundle_audit_accepts_absolute_bundle_paths(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "public-evidence"
    manifest_path, previous_manifest = preserve_visual_manifest()
    try:
        write_valid_visual_manifest(Path.cwd())
        status, _manifest = cli.public_evidence_bundle(str(bundle), run_visual=False)
    finally:
        restore_visual_manifest(manifest_path, previous_manifest)

    assert status == 0

    failures = cli.public_evidence_bundle_artifact_failures(
        Path.cwd().resolve(), bundle.resolve()
    )

    assert failures == []


def test_public_evidence_bundle_audit_requires_terminal_handoff(
    tmp_path: Path, monkeypatch
) -> None:
    bundle = tmp_path / "public-evidence"
    manifest_path, previous_manifest = preserve_visual_manifest()
    try:
        write_valid_visual_manifest(Path.cwd())
        status, _manifest = cli.public_evidence_bundle(str(bundle), run_visual=False)
    finally:
        restore_visual_manifest(manifest_path, previous_manifest)

    assert status == 0

    monkeypatch.setattr(
        cli,
        "evidence_bundle_lines",
        lambda _output_dir, _manifest: [
            "Evidence bundle: public-evidence",
            "Status: ok",
            "Artifacts:",
        ],
    )

    failures = cli.public_evidence_bundle_artifact_failures(Path.cwd(), bundle)

    assert "evidence bundle terminal output missing Reviewer action plan:" in failures
    assert "evidence bundle terminal output missing Review checklist:" in failures
    assert "evidence bundle terminal output missing Validation commands:" in failures


def test_audit_report_runs_fast_release_checks(tmp_path: Path) -> None:
    db = tmp_path / "demo.sqlite"
    sessions = tmp_path / "sessions"
    report = tmp_path / "run-report.md"
    public_bundle = tmp_path / "public-evidence"
    manifest_path, previous_manifest = preserve_visual_manifest()
    try:
        write_valid_visual_manifest(Path.cwd())
        bundle_status, _bundle = cli.public_evidence_bundle(
            str(public_bundle), run_visual=False
        )
        assert bundle_status == 0
        status, audit = cli.release_audit_report(
            str(db),
            str(sessions),
            str(report),
            public_evidence_dir=public_bundle,
        )
    finally:
        restore_visual_manifest(manifest_path, previous_manifest)

    checks = {check["name"]: check for check in audit["checks"]}
    assert status == 0
    assert audit["status"] == "ok"
    assert audit["schema_version"] == cli.AUDIT_SCHEMA_VERSION
    assert audit["failed_checks"] == []
    assert audit["required_commands"] == cli.RELEASE_REQUIRED_COMMANDS
    assert (
        checks["demo JSON"]["detail"]
        == "schema, counts, database, text next commands, next commands, text review path, and review path verified"
    )
    assert (
        checks["synthetic ingest JSON"]["detail"]
        == "schema, counts, scan limit, skipped categories, privacy review metadata, text privacy warning, text next commands, next commands, text review path, and review path verified"
    )
    assert report.exists()
    assert report.with_suffix(".json").exists()
    assert report.with_name("run-comparison.md").exists()
    assert report.with_name("run-comparison.json").exists()
    assert (
        checks["session listing"]["detail"]
        == "2 sessions; triage risk, risk distribution, status, schema, limit metadata, usage snapshots, text recommended action, session table tool-output column, tool-output driver, structured driver summary, success-target preview, recommendation detail, review path, text next commands, and next commands verified"
    )
    assert checks["database doctor"]["detail"] == (
        "ok; schema, text next commands, next commands, and review path verified"
    )
    assert checks["aggregate report"]["ok"] is True
    assert "success target" in checks["aggregate report"]["detail"]
    assert checks["aggregate comparison"]["ok"] is True
    assert "usage-snapshot deltas" in checks["aggregate comparison"]["detail"]
    assert checks["paths handoff"]["ok"] is True
    assert checks["paths handoff"]["detail"] == (
        "schema, existence checks, privacy no-scan metadata, sampled ingest command, review path, and text handoff verified"
    )
    assert checks["visual QA manifest evidence"]["ok"] is True
    assert checks["CI reviewer evidence bundle"]["ok"] is True
    assert checks["public evidence bundle artifacts"]["ok"] is True
    assert checks["issue templates"]["ok"] is True
    assert checks["tracking snapshot"]["ok"] is True
    assert (
        checks["public tour JSON"]["detail"]
        == "schema, privacy, database, evidence bundle, recommended-action evidence, terminal handoff evidence, terminal validation evidence, dashboard quick-read and comparison review-path evidence, top-level review path, terminal feedback handoff, text next commands, per-step success checks, and next commands verified"
    )
    assert (
        checks["issue templates"]["detail"]
        == "issue templates require demoable evidence, visual QA, public-tour feedback, privacy review, and limitations checks"
    )
    assert (
        checks["tracking snapshot"]["detail"]
        == "GitHub issue snapshot, local draft state, approval gate, and push cadence documented"
    )
    assert (
        checks["redaction validation privacy"]["detail"]
        == "privacy-safe JSON failure uses error codes, does not touch output, and verify-only rejects raw IDs"
    )
    assert (
        checks["CI reviewer evidence bundle"]["detail"]
        == "CI generates and uploads reviewer public evidence bundle"
    )
    assert (
        checks["public evidence bundle artifacts"]["detail"]
        == "manifest, terminal and reviewer README action plan, key findings, review checklist, feedback handoff, feedback runbook, feedback issue template, reproduce-local commands, validation commands, limitations doc, aggregate reports, and audit artifact verified"
    )
    assert (
        "visual manifest schema and contract, screenshots, empty states, layout review, risk labels, sidebar session details, risk distribution, metric cards, dashboard quick reads, report and comparison downloads, comparison preview, comparison review path, deltas, operator briefing, next review path, next-run checklist, safe feedback handoff, and success target verified"
        in checks["visual QA manifest evidence"]["detail"]
    )
    report_payload = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
    assert report_payload["schema_version"] == cli.REPORT_SCHEMA_VERSION
    assert report_payload["success_target"]["metric"] == "largest_thread_share_pct"
    assert report_payload["success_target"]["target_value"] == 50.0
    assert report_payload["next_commands"]
    assert report_payload["next_command_templates"]
    assert report_payload["review_path"][0]["label"] == "Save this report JSON"
    report_handoff = report_payload["feedback_handoff"]
    assert report_handoff["runbook"] == "docs/PUBLIC_TOUR_FEEDBACK.md"
    assert (
        report_handoff["issue_template"]
        == ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
    )
    assert (
        "synthetic or reviewed-redacted aggregate evidence"
        in report_handoff["evidence_rule"]
    )
    assert "codex-observe report JSON or Markdown" in report_handoff["safe_sources"]
    assert "private prompts" in report_handoff["do_not_collect"]
    report_text = report.read_text(encoding="utf-8")
    assert "## Next Run Success Target" in report_text
    assert "## Recommended Action" in report_text
    assert "Action: apply next run habit" in report_text
    assert "## Review Path" in report_text
    assert "Save this report JSON" in report_text
    assert "## Follow-up Commands" in report_text
    assert "## Feedback Handoff" in report_text
    assert "docs/PUBLIC_TOUR_FEEDBACK.md" in report_text
    assert ".github/ISSUE_TEMPLATE/public_tour_feedback.yml" in report_text
    assert "synthetic or reviewed-redacted aggregate evidence" in report_text
    assert "Do not collect" in report_text
    comparison_payload = json.loads(
        report.with_name("run-comparison.json").read_text(encoding="utf-8")
    )
    comparison_handoff = comparison_payload["feedback_handoff"]
    assert comparison_handoff["runbook"] == "docs/PUBLIC_TOUR_FEEDBACK.md"
    assert (
        comparison_handoff["issue_template"]
        == ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
    )
    assert (
        "synthetic or reviewed-redacted aggregate evidence"
        in comparison_handoff["evidence_rule"]
    )
    assert (
        "codex-observe comparison JSON or Markdown"
        in comparison_handoff["safe_sources"]
    )
    assert "private prompts" in comparison_handoff["do_not_collect"]
    comparison_text = report.with_name("run-comparison.md").read_text(encoding="utf-8")
    assert "## Feedback Handoff" in comparison_text
    assert "docs/PUBLIC_TOUR_FEEDBACK.md" in comparison_text
    assert ".github/ISSUE_TEMPLATE/public_tour_feedback.yml" in comparison_text
    assert "synthetic or reviewed-redacted aggregate evidence" in comparison_text
    assert "Do not collect" in comparison_text


def test_audit_cli_json_and_text_outputs_are_privacy_safe(
    tmp_path: Path, capsys
) -> None:
    db = tmp_path / "demo.sqlite"
    sessions = tmp_path / "sessions"
    report = tmp_path / "run-report.md"
    manifest_path, previous_manifest = preserve_visual_manifest()
    try:
        write_valid_visual_manifest(Path.cwd())
        bundle_status, _bundle = cli.public_evidence_bundle(
            ".artifacts/public-evidence", run_visual=False
        )
        assert bundle_status == 0
        result = cli.main(
            [
                "audit",
                "--db",
                str(db),
                "--sessions",
                str(sessions),
                "--report-out",
                str(report),
                "--json",
            ]
        )
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert result == 0
        assert payload["status"] == "ok"
        assert payload["schema_version"] == cli.AUDIT_SCHEMA_VERSION
        assert payload["required_commands"] == cli.RELEASE_REQUIRED_COMMANDS
        assert "synthetic output line" not in captured.out
        assert "Analyze why this Codex run" not in captured.out

        result = cli.main(
            [
                "audit",
                "--db",
                str(db),
                "--sessions",
                str(sessions),
                "--report-out",
                str(report),
            ]
        )
        captured = capsys.readouterr()
    finally:
        restore_visual_manifest(manifest_path, previous_manifest)

    assert result == 0
    assert "Status: ok" in captured.out
    assert "[OK] aggregate report" in captured.out
    assert "[OK] visual QA manifest evidence" in captured.out
    assert "Required commands:" in captured.out
    for command in cli.RELEASE_REQUIRED_COMMANDS:
        assert f"- {command}" in captured.out
    assert "synthetic output line" not in captured.out


def test_sessions_missing_json_payload_is_actionable_and_schema_versioned() -> None:
    payload = cli.sessions_missing_json_payload("missing.sqlite")

    assert payload["schema_version"] == cli.SESSIONS_SCHEMA_VERSION
    assert payload["status"] == "missing"
    assert payload["recommended_session"] is None
    assert payload["recommendation_detail"] is None
    assert payload["sessions"] == []
    assert payload["total_sessions"] == 0
    assert payload["returned_sessions"] == 0
    assert payload["risk_distribution"] == {
        "high": 0,
        "medium": 0,
        "low": 0,
        "unknown": 0,
    }
    assert payload["truncated"] is False
    assert payload["limit"] == cli.DEFAULT_SESSIONS_LIMIT
    assert "codex-observe demo --db missing.sqlite" in payload["next_commands"]
    assert payload["review_path"][0]["label"] == "Create demo data"
    assert payload["review_path"][1]["label"] == "Ingest local logs"


def test_sessions_json_payload_limits_rows_without_changing_recommendation(
    tmp_path: Path,
) -> None:
    db = tmp_path / "demo.sqlite"
    cli.create_demo_database(str(db), str(tmp_path / "sessions"))

    payload = cli.sessions_json_payload(str(db), limit=1)

    assert payload["schema_version"] == cli.SESSIONS_SCHEMA_VERSION
    assert payload["status"] == "ok"
    assert payload["total_sessions"] == 2
    assert payload["returned_sessions"] == 1
    assert payload["risk_distribution"] == {
        "high": 1,
        "medium": 0,
        "low": 1,
        "unknown": 0,
    }
    assert payload["truncated"] is True
    assert payload["limit"] == 1
    assert len(payload["sessions"]) == 1
    assert payload["sessions"][0]["session_id"] == "demo-session-cost-review"
    assert payload["recommended_session"]["session_id"] == "demo-session-cost-review"
    assert payload["recommendation_detail"]["target"] == "demo-session-cost-review"
    assert payload["recommendation_detail"]["success_target_preview"] == {
        "action": "Set a stop condition for the dominant thread",
        "current": "57.7%",
        "current_value": 57.7,
        "direction": "lower_is_better",
        "driver": "Largest thread",
        "metric": "largest_thread_share_pct",
        "target": "below 50.0%",
        "target_value": 50.0,
        "unit": "percent_of_run",
    }


def test_demo_payload_and_text_include_review_path() -> None:
    result = SimpleNamespace(files_imported=6, threads=6, events=34)

    payload = cli.demo_success_payload(
        "demo.sqlite", "sessions", result, keep_sessions=True
    )
    text = "\n".join(cli.demo_success_lines("demo.sqlite", result))

    assert payload["schema_version"] == cli.DEMO_SCHEMA_VERSION
    assert payload["status"] == "ok"
    assert payload["keep_sessions"] is True
    assert payload["next_commands"] == cli.demo_next_commands("demo.sqlite")
    assert [step["label"] for step in payload["review_path"]] == [
        "Verify synthetic database",
        "Pick the reportable run",
        "Export aggregate report",
        "Open dashboard",
    ]
    assert payload["review_path"][0]["command"] == (
        "codex-observe doctor --db demo.sqlite --json"
    )
    assert payload["review_path"][1]["command"] == (
        "codex-observe sessions --db demo.sqlite --json"
    )
    assert "Review path:" in text
    assert (
        "Verify synthetic database: codex-observe doctor --db demo.sqlite --json"
        in text
    )
    assert "Success check: doctor JSON status is ok" in text
    assert "Next commands:" in text
    for command in cli.demo_next_commands("demo.sqlite"):
        assert f"- {command}" in text
    assert text.index("Review path:") < text.index("Next commands:")
    assert text.index("Next commands:") < text.index("Next:")


def test_ingest_payload_and_text_include_review_path() -> None:
    result = SimpleNamespace(
        files_matched=2,
        files_skipped_by_limit=0,
        newest_files_limit=None,
        files_seen=2,
        files_imported=2,
        threads=3,
        events=4,
        duplicate_files=0,
        empty_files=0,
        malformed_files=0,
        missing_meta_files=0,
        unreadable_files=0,
        malformed_lines=0,
    )

    payload = cli.ingest_success_payload("sessions", "demo.sqlite", result)
    text = "\n".join(cli.ingest_success_lines("demo.sqlite", result))

    assert payload["schema_version"] == cli.INGEST_SCHEMA_VERSION
    assert payload["status"] == "ok"
    assert payload["privacy"]["review_required_before_sharing"] is True
    assert "aggregate metrics" in payload["privacy"]["share_warning"]
    assert "redacted fixture candidates" in payload["privacy"]["share_warning"]
    assert payload["counts"]["files_matched"] == 2
    assert payload["counts"]["files_skipped_by_limit"] == 0
    assert payload["scan_limit"] == {"mode": "all", "newest_files": None}
    assert [step["label"] for step in payload["review_path"]] == [
        "Verify database health",
        "Choose a reportable run",
        "Export aggregate report",
        "Open dashboard",
    ]
    assert payload["review_path"][0]["command"] == (
        "codex-observe doctor --db demo.sqlite --json"
    )
    assert payload["review_path"][1]["command"] == (
        "codex-observe sessions --db demo.sqlite --json"
    )
    assert "Privacy: ingest output is aggregate-only" in text
    assert "aggregate metrics before sharing" in text
    assert "Review path:" in text
    assert (
        "Verify database health: codex-observe doctor --db demo.sqlite --json" in text
    )
    assert "Success check: doctor JSON status is ok and review_path is present." in text
    assert "Next commands:" in text
    for command in cli.ingest_next_commands("demo.sqlite"):
        assert f"- {command}" in text
    assert text.index("Review path:") < text.index("Next commands:")
    assert text.index("Next commands:") < text.index("Next:")

    empty_result = SimpleNamespace(
        files_matched=0,
        files_skipped_by_limit=0,
        newest_files_limit=None,
        files_seen=0,
        files_imported=0,
        threads=0,
        events=0,
        duplicate_files=0,
        empty_files=0,
        malformed_files=0,
        missing_meta_files=0,
        unreadable_files=0,
        malformed_lines=0,
    )
    empty_payload = cli.ingest_success_payload("sessions", "empty.sqlite", empty_result)

    assert empty_payload["status"] == "empty"
    assert [step["label"] for step in empty_payload["review_path"]] == [
        "Check input path",
        "Try synthetic data",
        "Verify database health",
    ]


def test_ingest_payload_and_text_include_bounded_scan_summary() -> None:
    result = SimpleNamespace(
        files_matched=12,
        files_skipped_by_limit=7,
        newest_files_limit=5,
        files_seen=5,
        files_imported=5,
        threads=5,
        events=20,
        duplicate_files=0,
        empty_files=0,
        malformed_files=0,
        missing_meta_files=0,
        unreadable_files=0,
        malformed_lines=0,
    )

    payload = cli.ingest_success_payload("sessions", "demo.sqlite", result)
    text = "\n".join(cli.ingest_success_lines("demo.sqlite", result))

    assert payload["counts"]["files_matched"] == 12
    assert payload["counts"]["files_seen"] == 5
    assert payload["counts"]["files_skipped_by_limit"] == 7
    assert payload["scan_limit"] == {"mode": "newest_files", "newest_files": 5}
    assert "newest-file limit 5 selected from 12 matched (7 deferred)" in text


def test_doctor_and_sessions_expose_sampled_ingest_scope(
    tmp_path: Path, capsys
) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    for index, name in enumerate(["older", "middle", "newest"], start=1):
        path = sessions / f"{name}.jsonl"
        row = {
            "type": "session_meta",
            "timestamp": f"2026-01-01T12:0{index}:00Z",
            "payload": {
                "id": f"thread-{name}",
                "session_id": f"session-{name}",
                "timestamp": f"2026-01-01T12:0{index}:00Z",
            },
        }
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        os.utime(path, (index * 1000, index * 1000))
    db = tmp_path / "sampled.sqlite"

    cli.ingest(str(sessions), str(db), newest_files=2)

    _status, doctor = cli.doctor_report(str(db))
    _lines_status, lines = cli.doctor_lines(str(db))
    sessions_payload = cli.sessions_json_payload(str(db))
    scope = doctor["ingest_scope"]

    assert scope["sampled"] is True
    assert scope["scan_limit"] == {"mode": "newest_files", "newest_files": 2}
    assert scope["counts"]["files_matched"] == 3
    assert scope["counts"]["files_seen"] == 2
    assert scope["counts"]["files_skipped_by_limit"] == 1
    assert "Sampled ingest: newest-file limit 2 selected 2 of 3" in scope["warning"]
    assert "Ingest scope: Sampled ingest" in "\n".join(lines)
    assert sessions_payload["ingest_scope"] == scope

    assert cli.main(["sessions", "--db", str(db), "--limit", "1"]) == 0
    plain_sessions = capsys.readouterr().out
    assert "Ingest scope: Sampled ingest" in plain_sessions
    assert "Showing 1 of 2 sessions." in plain_sessions

    report = cli.build_report(str(db))
    assert report["ingest_scope"] == scope
    report_markdown = cli.report_markdown(report)
    report_payload = json.loads(cli.report_json(report))
    assert "## Ingest Scope" in report_markdown
    assert "Sampled ingest: newest-file limit 2 selected 2 of 3" in report_markdown
    assert report_payload["ingest_scope"] == scope

    report_path = tmp_path / "sampled-report.json"
    assert (
        cli.main(
            ["report", "--db", str(db), "--format", "json", "--out", str(report_path)]
        )
        == 0
    )
    report_output = capsys.readouterr().out
    assert "Ingest scope: Sampled ingest" in report_output
    assert (
        "Sampled ingest: newest-file limit 2 selected 2 of 3"
        in report_path.read_text(encoding="utf-8")
    )
    comparison = cli.compare_reports(report, report)
    assert comparison["ingest_scope"]["sampled"] is True
    assert "Sampled ingest" in comparison["ingest_scope"]["warning"]
    comparison_markdown = cli.comparison_markdown(comparison)
    comparison_payload = json.loads(cli.comparison_json(comparison))
    assert "## Ingest Scope" in comparison_markdown
    assert "treat comparison deltas as sampled evidence" in comparison_markdown
    assert comparison_payload["ingest_scope"]["sampled"] is True
    comparison_path = tmp_path / "sampled-comparison.json"
    assert (
        cli.main(
            [
                "compare",
                "--before-report",
                str(report_path),
                "--after-report",
                str(report_path),
                "--format",
                "json",
                "--out",
                str(comparison_path),
            ]
        )
        == 0
    )
    comparison_output = capsys.readouterr().out
    assert "Ingest scope: Sampled ingest" in comparison_output
    assert "Sampled ingest" in comparison_path.read_text(encoding="utf-8")
    assert str(sessions) not in comparison_output
    assert str(sessions) not in json.dumps(scope)
    assert str(sessions) not in plain_sessions
    assert str(sessions) not in report_output


def test_doctor_report_includes_review_path_for_healthy_and_missing_databases(
    tmp_path: Path,
) -> None:
    db = tmp_path / "demo.sqlite"
    sessions = tmp_path / "sessions"
    cli.create_demo_database(str(db), str(sessions), keep_sessions=True)

    status, report = cli.doctor_report(str(db))
    lines_status, lines = cli.doctor_lines(str(db))
    text = "\n".join(lines)

    assert status == 0
    assert lines_status == 0
    assert report["schema_version"] == cli.DOCTOR_SCHEMA_VERSION
    assert report["review_path"] == [
        {
            "label": "Choose a reportable run",
            "command": f"codex-observe sessions --db {db} --json",
            "success_check": "sessions JSON includes status ok and a recommended_session.",
        },
        {
            "label": "Open the dashboard",
            "command": f"codex-observe serve --db {db}",
            "success_check": "dashboard opens without a missing-database or empty-database state.",
        },
        {
            "label": "Export the recommended report",
            "command": f"codex-observe report --db {db} --out run-report.md",
            "success_check": "report output includes Recommended Action and Next Run Success Target.",
        },
    ]
    assert "Review path:" in text
    assert f"Choose a reportable run: codex-observe sessions --db {db} --json" in text
    assert (
        "Success check: sessions JSON includes status ok and a recommended_session."
        in text
    )
    assert "Next commands:" in text
    assert f"- codex-observe sessions --db {db}" in text
    assert f"- codex-observe serve --db {db}" in text
    assert text.index("Review path:") < text.index("Next commands:")
    assert text.index("Next commands:") < text.index("Next:")

    missing = tmp_path / "missing.sqlite"
    missing_status, missing_report = cli.doctor_report(str(missing))
    missing_lines_status, missing_lines = cli.doctor_lines(str(missing))
    missing_text = "\n".join(missing_lines)

    assert missing_status == 2
    assert missing_lines_status == 2
    assert missing_report["status"] == "missing"
    assert [item["label"] for item in missing_report["review_path"]] == [
        "Create synthetic database",
        "Ingest local logs",
    ]
    assert missing_report["review_path"][0]["command"] == (
        f"codex-observe demo --db {missing}"
    )
    assert "Next commands:" in missing_text
    assert f"- codex-observe demo --db {missing}" in missing_text
    assert f"- codex-observe ingest ~/.codex/sessions --db {missing}" in missing_text


def test_session_recommendation_detail_includes_structured_tool_output_driver() -> None:
    detail = cli.session_recommendation_detail(
        {
            "session_id": "session-high",
            "triage_risk": "high",
            "largest_thread_share_pct": 57.7,
            "repeated_prompt_share_pct": 17.4,
            "uncached_input_share_pct": 39.5,
            "largest_tool_output_chars": 3960,
        }
    )

    assert detail["drivers"] == {
        "largest_thread_share_pct": 57.7,
        "repeated_prompt_share_pct": 17.4,
        "uncached_input_share_pct": 39.5,
        "largest_tool_output_chars": 3960,
    }

    review_path = cli.sessions_review_path("demo.sqlite", "session-high")

    assert [step["label"] for step in review_path] == [
        "Save report Markdown",
        "Save report JSON",
        "Compare workflow change",
        "Validate next run",
        "File safe feedback",
    ]
    assert review_path[1]["command"] == (
        "codex-observe report --db demo.sqlite --session-id session-high --format json --out run-report.json"
    )
    assert "codex-observe compare --before-report" in review_path[2]["command"]
    assert review_path[-1]["command"] == "docs/PUBLIC_TOUR_FEEDBACK.md"

    assert detail["driver_summary"] == [
        {
            "driver": "largest_thread_share_pct",
            "label": "Largest thread share",
            "value": 57.7,
            "display": "57.7%",
        },
        {
            "driver": "repeated_prompt_share_pct",
            "label": "Repeated prompt share",
            "value": 17.4,
            "display": "17.4%",
        },
        {
            "driver": "uncached_input_share_pct",
            "label": "Uncached input share",
            "value": 39.5,
            "display": "39.5%",
        },
        {
            "driver": "largest_tool_output_chars",
            "label": "Largest tool output",
            "value": 3960,
            "display": "4.0k chars",
        },
    ]


def test_public_tour_payload_is_private_log_free_and_points_to_visual_verification() -> (
    None
):
    payload = cli.public_tour_payload("demo.sqlite")
    evidence = [item for step in payload["steps"] for item in step.get("evidence", [])]
    success_checks = [
        item for step in payload["steps"] for item in step.get("success_checks", [])
    ]

    assert payload["schema_version"] == cli.TOUR_SCHEMA_VERSION
    assert payload["privacy"]["private_log_required"] is False
    feedback_handoff = payload["feedback_handoff"]
    assert feedback_handoff["runbook"] == "docs/PUBLIC_TOUR_FEEDBACK.md"
    assert (
        feedback_handoff["issue_template"]
        == ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
    )
    assert (
        "synthetic or reviewed-redacted evidence" in feedback_handoff["evidence_rule"]
    )
    assert "private prompts" in feedback_handoff["do_not_collect"]
    assert (
        "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json"
        in payload["next_commands"]
    )
    assert (
        "codex-observe evidence-bundle --out .artifacts/public-evidence"
        in payload["next_commands"]
    )
    assert "codex-observe demo --db demo.sqlite" in payload["next_commands"]
    assert "codex-observe doctor --db demo.sqlite" in payload["next_commands"]
    assert "codex-observe doctor --db demo.sqlite --json" in payload["next_commands"]
    assert "codex-observe sessions --db demo.sqlite" in payload["next_commands"]
    assert "codex-observe sessions --db demo.sqlite --json" in payload["next_commands"]
    assert "codex-observe audit --json" in payload["next_commands"]
    text_lines = cli.public_tour_lines("demo.sqlite")
    assert "Feedback handoff:" in text_lines
    assert "- Runbook: docs/PUBLIC_TOUR_FEEDBACK.md" in text_lines
    assert (
        "- Issue template: .github/ISSUE_TEMPLATE/public_tour_feedback.yml"
        in text_lines
    )
    assert "- Safe feedback sources:" in text_lines
    assert "  - reviewer evidence bundle" in text_lines
    assert "- Do not collect:" in text_lines
    assert "  - private prompts" in text_lines
    assert text_lines.index("Feedback handoff:") < text_lines.index("Next commands:")
    assert "Next commands:" in text_lines
    for command in payload["next_commands"]:
        assert f"- {command}" in text_lines
    assert text_lines.index("Next commands:") > text_lines.index(
        "9. File privacy-safe public-tour feedback:"
    )
    assert any("key findings" in item for item in evidence)
    assert any("review_summary" in item for item in evidence)
    assert any("codex-observe.evidence-bundle.v1" in item for item in evidence)
    assert any("docs/PUBLIC_TOUR_FEEDBACK.md" in item for item in evidence)
    assert any("reviewed-redacted" in item for item in evidence)
    assert any("success_target" in item for item in evidence)
    assert any("success target" in item for item in evidence)
    assert any("recommended-action block" in item for item in evidence)
    assert any("largest tool output" in item for item in evidence)
    assert any("Snapshots and Tool out columns" in item for item in evidence)
    assert any("structured aggregate drivers" in item for item in evidence)
    assert any("driver_summary" in item for item in evidence)
    assert any("review_path" in item for item in evidence)
    assert any(
        "plain doctor output includes terminal Review path" in item for item in evidence
    )
    assert any(
        "plain demo output includes terminal Review path" in item
        for item in success_checks
    )
    assert any(
        "plain doctor output includes copy-pasteable terminal Next commands" in item
        for item in success_checks
    )
    assert any(
        "doctor JSON includes schema_version, structured next_commands, and review_path"
        in item
        for item in evidence
    )
    assert [item["label"] for item in payload["review_path"]] == [
        "Create synthetic evidence",
        "Verify database health",
        "Choose the recommended run",
        "Export aggregate reports",
        "Compare workflow evidence",
        "Verify UI and bundle evidence",
        "Run release audit",
        "File safe feedback",
    ]
    assert payload["review_path"][1]["command"] == (
        "codex-observe doctor --db demo.sqlite"
    )
    assert payload["review_path"][2]["command"] == (
        "codex-observe sessions --db demo.sqlite"
    )
    assert payload["review_path"][-1]["command"] == "docs/PUBLIC_TOUR_FEEDBACK.md"
    assert any("Recommended Action" in item for item in evidence)
    assert any("report terminal confirmation" in item for item in evidence)
    assert any("comparison terminal confirmation" in item for item in evidence)
    assert any("Next validation command" in item for item in evidence)
    assert any("comparison metric delta cards" in item for item in evidence)
    assert any("report and comparison download controls" in item for item in evidence)
    assert len(success_checks) >= len(payload["steps"])
    assert all(step.get("success_checks") for step in payload["steps"])
    assert any("failed_checks is empty" in item for item in success_checks)
    assert any("layout overflow" in item for item in success_checks)
    assert any("explicit publication approval" in item for item in success_checks)
    for expected in [
        "Agent detail thread brief",
        "Timeline quick read",
        "Tools quick read",
        "Duplication quick read",
        "Raw tables data inventory",
    ]:
        assert any(expected in item for item in evidence)


def test_report_and_comparison_written_lines_include_actionable_drivers(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "report.md"
    report_lines = cli.report_written_lines(
        report_path,
        {
            "triage": {
                "risk_level": "high",
                "primary_driver": "Largest thread dominates",
                "next_action": "Set a stop condition",
            },
            "opportunities": [{"Driver": "Largest thread", "Scale": "33.2k tokens"}],
            "success_target": {
                "metric": "largest_thread_share_pct",
                "current": "57.7%",
                "target": "below 50.0%",
            },
            "next_commands": [
                "codex-observe sessions --db demo.sqlite --json",
                "codex-observe report --db demo.sqlite --session-id session-1 --format json --out run-report.json",
            ],
            "next_command_templates": [
                "codex-observe report --db demo.sqlite --session-id <next-session-id> --format json --out next-run-report.json",
                "codex-observe compare --before-report run-report.json --after-report next-run-report.json --out run-comparison.md",
            ],
        },
    )
    comparison_lines = cli.comparison_written_lines(
        tmp_path / "comparison.md",
        {
            "verdict": "improved",
            "triage_risk": {
                "before": "high",
                "after": "moderate",
                "direction": "improved",
            },
            "opportunity_change": {"summary": "Largest thread improved."},
            "recommendation": "Keep the change.",
            "next_command_templates": [
                "codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json"
            ],
        },
    )

    assert f"Wrote aggregate-only report: {report_path}" in report_lines
    assert any(
        "Privacy: review private reports before sharing" in line
        for line in report_lines
    )
    assert any(
        "aggregate metrics can still reveal workflow clues" in line
        for line in report_lines
    )
    assert "Top opportunity: Largest thread; 33.2k tokens" in report_lines
    assert "Next action: Set a stop condition" in report_lines
    assert (
        "Success target: largest_thread_share_pct: 57.7% -> below 50.0%" in report_lines
    )
    assert "Next commands:" in report_lines
    assert "- codex-observe sessions --db demo.sqlite --json" in report_lines
    assert (
        "- codex-observe compare --before-report run-report.json --after-report next-run-report.json --out run-comparison.md"
        in report_lines
    )
    assert any(
        "Privacy: review private comparison reports before sharing" in line
        for line in comparison_lines
    )
    assert any(
        "aggregate deltas can still reveal workflow clues" in line
        for line in comparison_lines
    )
    assert "Triage risk: high -> moderate (improved)" in comparison_lines
    assert "Opportunity change: Largest thread improved." in comparison_lines
    assert "Next step: Keep the change." in comparison_lines
    assert (
        "Next validation command: codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json"
        in comparison_lines
    )
    assert "Next commands:" in comparison_lines
    assert (
        "- codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json"
        in comparison_lines
    )


def test_public_evidence_bundle_writes_privacy_safe_manifest_and_artifacts(
    tmp_path: Path,
) -> None:
    out = tmp_path / "bundle"
    stale_visual_dir = out / "visual"
    stale_visual_dir.mkdir(parents=True)
    (stale_visual_dir / "visual-qa-manifest.json").write_text("{}", encoding="utf-8")
    manifest_path, previous_manifest = preserve_visual_manifest()
    try:
        write_valid_visual_manifest(Path.cwd())
        status, manifest = cli.public_evidence_bundle(str(out), run_visual=False)
    finally:
        restore_visual_manifest(manifest_path, previous_manifest)

    loaded = json.loads((out / "evidence-bundle.json").read_text(encoding="utf-8"))
    artifacts = loaded["artifacts"]

    assert status == 0
    assert manifest == loaded
    assert loaded["schema_version"] == cli.EVIDENCE_BUNDLE_SCHEMA_VERSION
    assert loaded["status"] == "ok"
    assert loaded["privacy"] == {
        "mode": "synthetic-demo",
        "private_log_required": False,
        "raw_content_included": False,
    }
    summary = loaded["review_summary"]
    summary_text = json.dumps(summary)
    assert summary[0]["label"] == "Run triage"
    assert "Top opportunity" in summary_text
    assert "Next-run target" in summary_text
    assert "Comparison verdict" in summary_text
    assert "Audit status" in summary_text
    assert "Largest thread drives the run" in summary_text
    assert str(tmp_path) not in summary_text
    checklist = loaded["review_checklist"]
    checklist_text = json.dumps(checklist)
    assert checklist[0]["label"] == "Confirm the bundle boundary"
    assert "Read the run outcome" in checklist_text
    assert "Check workflow-change evidence" in checklist_text
    assert "Verify release gates" in checklist_text
    assert "next validation command" in checklist_text
    assert "comparison review path" in checklist_text
    assert str(tmp_path) not in checklist_text
    action_plan = loaded["action_plan"]
    action_plan_text = json.dumps(action_plan)
    assert action_plan[0]["label"] == "Establish the safe review boundary"
    assert "Read the run diagnosis" in action_plan_text
    assert "Check change evidence" in action_plan_text
    assert "Verify reproducibility gates" in action_plan_text
    assert "Validate the next real run" in action_plan_text
    assert "File feedback safely" in action_plan_text
    feedback_handoff = loaded["feedback_handoff"]
    assert feedback_handoff["runbook"] == "docs/PUBLIC_TOUR_FEEDBACK.md"
    assert (
        feedback_handoff["issue_template"]
        == ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
    )
    assert (
        "synthetic or reviewed-redacted evidence" in feedback_handoff["evidence_rule"]
    )
    assert "reviewer evidence bundle" in feedback_handoff["safe_sources"]
    assert "private prompts" in feedback_handoff["do_not_collect"]
    assert str(tmp_path) not in json.dumps(feedback_handoff)
    assert "success_check" in action_plan_text
    assert str(tmp_path) not in action_plan_text
    validation_commands = loaded["validation_commands"]
    assert validation_commands["next_report"] == (
        "codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json"
    )
    assert validation_commands["next_comparison"] == (
        "codex-observe compare --before-report <after-report.json> --after-report next-run-report.json --out next-run-comparison.md"
    )
    assert validation_commands["same_database_comparison"] == (
        "codex-observe compare --before-session demo-session-cost-review --after-session <next-session-id> --db <db> --out next-run-comparison.md"
    )
    assert str(tmp_path) not in json.dumps(validation_commands)
    assert loaded["checks"]["demo"]["status"] == "ok"
    assert loaded["checks"]["report"]["schema_version"] == cli.REPORT_SCHEMA_VERSION
    assert (
        loaded["checks"]["comparison"]["schema_version"]
        == cli.COMPARISON_SCHEMA_VERSION
    )
    assert loaded["checks"]["visual_qa"]["status"] == "skipped"
    assert loaded["checks"]["audit"]["schema_version"] == cli.AUDIT_SCHEMA_VERSION
    assert loaded["checks"]["audit"]["status"] == "ok"
    assert "visual_manifest" not in artifacts
    assert "visual_screenshots" not in artifacts
    for key in [
        "bundle_readme",
        "feedback_runbook",
        "feedback_issue_template",
        "database",
        "sessions_dir",
        "report_markdown",
        "report_json",
        "comparison_markdown",
        "comparison_json",
        "audit_json",
    ]:
        assert not Path(artifacts[key]).is_absolute()
        assert (out / artifacts[key]).exists()
    readme = (out / artifacts["bundle_readme"]).read_text(encoding="utf-8")
    assert "# Codex Observe Evidence Bundle" in readme
    assert "LIMITATIONS.md" in readme
    assert "PUBLIC_TOUR_FEEDBACK.md" in readme
    assert ".github/ISSUE_TEMPLATE/public_tour_feedback.yml" in readme
    assert "File feedback safely" in readme
    assert "demo/run-report.md" in readme
    assert "audit/audit.json" in readme
    assert "## Reviewer Action Plan" in readme
    assert "Establish the safe review boundary" in readme
    assert "Read the run diagnosis" in readme
    assert "Validate the next real run" in readme
    assert "Success check:" in readme
    assert "## Key Findings" in readme
    assert "Run triage" in readme
    assert "Top opportunity" in readme
    assert "Next-run target" in readme
    assert "Comparison verdict" in readme
    assert "Audit status" in readme
    assert "## Review Checklist" in readme
    assert "Confirm the bundle boundary" in readme
    assert "Read the run outcome" in readme
    assert "Check workflow-change evidence" in readme
    assert "Verify release gates" in readme
    assert "next validation command" in readme
    assert "comparison review path" in readme
    assert "## Feedback Handoff" in readme
    assert "docs/PUBLIC_TOUR_FEEDBACK.md" in readme
    assert ".github/ISSUE_TEMPLATE/public_tour_feedback.yml" in readme
    assert "synthetic or reviewed-redacted evidence" in readme
    assert "Safe feedback sources" in readme
    assert "Do not collect" in readme
    assert "## Validate The Next Run" in readme
    assert "Next Report" in readme
    assert "Next Comparison" in readme
    assert "Same Database Comparison" in readme
    assert (
        "codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json"
        in readme
    )
    assert "## Reproduce Locally" in readme
    assert "codex-observe demo --db demo/codex_observe_demo.sqlite" in readme
    assert (
        "codex-observe report --db demo/codex_observe_demo.sqlite --out demo/run-report.md"
        in readme
    )
    assert (
        "codex-observe compare --before-report demo/run-report.json --after-report demo/run-report.json --out demo/run-comparison.md"
        in readme
    )
    assert "codex-observe audit --json" in readme
    assert "private Codex logs" in readme
    feedback = (out / artifacts["feedback_runbook"]).read_text(encoding="utf-8")
    assert "# Public Tour Feedback" in feedback
    assert "Do Not Collect" in feedback
    assert "Private prompts" in feedback
    feedback_issue_template = (out / artifacts["feedback_issue_template"]).read_text(
        encoding="utf-8"
    )
    assert "Public tour feedback" in feedback_issue_template
    assert "Do not paste private prompts" in feedback_issue_template
    assert "Privacy review" in feedback_issue_template
    assert "docs/PUBLIC_TOUR_FEEDBACK.md" in feedback_issue_template
    limitations = (out / artifacts["limitations_markdown"]).read_text(encoding="utf-8")
    assert "# Limitations and Next Work" in limitations
    assert "approval-gated" in limitations
    assert "human-approved private input path" in limitations
    assert (
        "External publishing or attachment still requires explicit human approval"
        in readme
    )
    assert "synthetic output line" not in readme
    assert "Analyze why this Codex run" not in readme
    assert "codex-observe demo" in "\n".join(loaded["commands"])
    assert "python scripts/visual_qa.py" not in "\n".join(loaded["commands"])
    serialized = json.dumps(loaded)
    assert "synthetic output line" not in serialized
    assert "Analyze why this Codex run" not in serialized
    assert str(tmp_path) not in serialized


def test_evidence_bundle_cli_json_and_text_outputs_are_actionable(
    tmp_path: Path, capsys
) -> None:
    out = tmp_path / "bundle"
    manifest_path, previous_manifest = preserve_visual_manifest()
    try:
        write_valid_visual_manifest(Path.cwd())
        result = cli.main(
            ["evidence-bundle", "--out", str(out), "--skip-visual", "--json"]
        )
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert result == 0
        assert payload["schema_version"] == cli.EVIDENCE_BUNDLE_SCHEMA_VERSION
        assert payload["status"] == "ok"
        assert payload["artifacts"]["bundle_readme"] == "README.md"
        assert payload["artifacts"]["limitations_markdown"] == "LIMITATIONS.md"
        assert payload["artifacts"]["feedback_runbook"] == "PUBLIC_TOUR_FEEDBACK.md"
        assert (
            payload["artifacts"]["feedback_issue_template"]
            == ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
        )
        assert payload["artifacts"]["report_markdown"] == "demo/run-report.md"
        assert payload["review_summary"][0]["label"] == "Run triage"
        assert payload["review_checklist"][0]["label"] == "Confirm the bundle boundary"
        assert (
            payload["action_plan"][0]["label"] == "Establish the safe review boundary"
        )
        assert payload["feedback_handoff"]["runbook"] == "docs/PUBLIC_TOUR_FEEDBACK.md"
        assert (
            payload["feedback_handoff"]["issue_template"]
            == ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
        )
        assert "next_report" in payload["validation_commands"]
        assert payload["validation_commands"]["next_report"].startswith(
            "codex-observe report --db <db> --session-id <next-session-id>"
        )
        assert payload["next"].startswith(
            "Start with README.md, LIMITATIONS.md, and PUBLIC_TOUR_FEEDBACK.md"
        )
        assert "comparison review path" in json.dumps(payload["review_checklist"])
        assert "visual QA screenshots" not in payload["next"]
        assert str(tmp_path) not in captured.out

        text_out = tmp_path / "bundle-text"
        result = cli.main(["evidence-bundle", "--out", str(text_out), "--skip-visual"])
        captured = capsys.readouterr()
    finally:
        restore_visual_manifest(manifest_path, previous_manifest)

    assert result == 0
    assert "Evidence bundle:" in captured.out
    assert "Status: ok" in captured.out
    assert "bundle_readme: README.md" in captured.out
    assert "limitations_markdown: LIMITATIONS.md" in captured.out
    assert "feedback_runbook: PUBLIC_TOUR_FEEDBACK.md" in captured.out
    assert (
        "feedback_issue_template: .github/ISSUE_TEMPLATE/public_tour_feedback.yml"
        in captured.out
    )
    assert "report_markdown: demo/run-report.md" in captured.out
    assert "Reviewer action plan:" in captured.out
    assert "1. Establish the safe review boundary: LIMITATIONS.md" in captured.out
    assert "5. Validate the next real run: validation_commands" in captured.out
    assert "Key findings:" in captured.out
    assert captured.out.index("Reviewer action plan:") < captured.out.index(
        "Key findings:"
    )
    assert "Review checklist:" in captured.out
    assert captured.out.index("Key findings:") < captured.out.index("Review checklist:")
    assert captured.out.index("Review checklist:") < captured.out.index(
        "Validation commands:"
    )
    assert "Run triage: high risk - Largest thread drives the run" in captured.out
    assert "Top opportunity: Largest thread - 33.2k tokens" in captured.out
    assert "Next-run target: largest_thread_share_pct" in captured.out
    assert "Audit status: ok with 0 failed checks" in captured.out
    assert "Confirm the bundle boundary: LIMITATIONS.md" in captured.out
    assert "Check workflow-change evidence: demo/run-comparison.md" in captured.out
    assert "comparison review path" in captured.out
    assert "Validation commands:" in captured.out
    assert "Feedback handoff:" in captured.out
    assert "Runbook: docs/PUBLIC_TOUR_FEEDBACK.md" in captured.out
    assert (
        "Issue template: .github/ISSUE_TEMPLATE/public_tour_feedback.yml"
        in captured.out
    )
    assert "Safe feedback sources:" in captured.out
    assert "Do not collect:" in captured.out
    assert "private prompts" in captured.out
    assert captured.out.index("Validation commands:") < captured.out.index(
        "Feedback handoff:"
    )
    assert captured.out.index("Feedback handoff:") < captured.out.index("Artifacts:")
    assert (
        "next_report: codex-observe report --db <db> --session-id <next-session-id>"
        in captured.out
    )
    assert (
        "next_comparison: codex-observe compare --before-report <after-report.json>"
        in captured.out
    )
    assert "audit_json: audit/audit.json" in captured.out


def test_paths_command_prints_privacy_safe_private_validation_handoff(
    tmp_path: Path, capsys
) -> None:
    sessions = tmp_path / ".codex" / "sessions"
    sessions.mkdir(parents=True)
    db = tmp_path / ".codex-observe" / "codex_observe.sqlite"

    result = cli.main(["paths", "--sessions-path", str(sessions), "--db", str(db)])
    captured = capsys.readouterr()

    assert result == 0
    assert f"Default Codex sessions path: {sessions}" in captured.out
    assert "Sessions path exists: true" in captured.out
    assert f"Default Codex Observe database: {db}" in captured.out
    assert "Database exists: false" in captured.out
    assert "does not scan logs or print filenames" in captured.out
    assert "Review path:" in captured.out
    assert "Sample newest private logs" in captured.out
    assert (
        f"codex-observe ingest {sessions} --newest-files 25 --db {db} --json"
        in captured.out
    )
    assert f"codex-observe doctor --db {db}" in captured.out
    assert f"codex-observe sessions --db {db}" in captured.out
    assert f"codex-observe serve --db {db}" in captured.out


def test_paths_command_json_is_schema_versioned_and_does_not_scan_logs(
    tmp_path: Path, capsys
) -> None:
    sessions = tmp_path / ".codex" / "sessions"
    sessions.mkdir(parents=True)
    db = tmp_path / ".codex-observe" / "codex_observe.sqlite"

    result = cli.main(
        ["paths", "--sessions-path", str(sessions), "--db", str(db), "--json"]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    assert payload["schema_version"] == cli.PATHS_SCHEMA_VERSION
    assert payload["sessions_path"] == str(sessions)
    assert payload["sessions_path_exists"] is True
    assert payload["database"] == str(db)
    assert payload["database_exists"] is False
    assert payload["privacy"] == {
        "raw_content_included": False,
        "review_required_before_sharing": True,
        "scans_sessions": False,
        "share_warning": "Paths and aggregate artifacts can reveal local workflow clues; review before sharing.",
    }
    assert payload["next_commands"][0] == (
        f"codex-observe ingest {sessions} --newest-files 25 --db {db} --json"
    )
    assert payload["review_path"][0]["label"] == "Sample newest private logs"
