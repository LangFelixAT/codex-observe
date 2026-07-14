from __future__ import annotations

import json

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
    ingest.assert_called_once_with(str(sessions), str(db))
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
    payload["viewports"]["desktop"]["quick_read_evidence"] = [
        {"tab": "Overview", "text": "Run triage"}
    ]
    payload["viewports"]["narrow"]["metric_cards"][1]["value"] = "2.9k tokens (34.5%)"
    payload["viewports"]["desktop"]["success_targets"][0]["current"] = "34.5%"
    payload["viewports"]["desktop"]["operator_briefings"][0]["best_habit"] = (
        "Read raw tables"
    )
    payload["viewports"]["desktop"]["download_controls"] = ["Download report MD"]
    payload["viewports"]["desktop"]["comparison_deltas"] = [
        {"label": "Total tokens", "delta": "improved: -49.1k (-85.4%)"}
    ]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    failures = cli.visual_manifest_evidence_failures(tmp_path)

    assert "visual QA manifest desktop missing risk labels: Low risk" in failures
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
        "visual QA manifest desktop missing comparison delta: Largest thread tokens"
        in failures
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
        "codex-observe evidence-bundle --out .artifacts/public-evidence\n"
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
    assert report.exists()
    assert report.with_suffix(".json").exists()
    assert report.with_name("run-comparison.md").exists()
    assert report.with_name("run-comparison.json").exists()
    assert (
        checks["session listing"]["detail"]
        == "2 sessions; triage risk, status, schema, text recommended action, session table tool-output column, tool-output driver, structured driver summary, recommendation detail, review path, and next commands verified"
    )
    assert checks["database doctor"]["detail"] == (
        "ok; schema, next commands, and review path verified"
    )
    assert checks["aggregate report"]["ok"] is True
    assert "success target" in checks["aggregate report"]["detail"]
    assert checks["visual QA manifest evidence"]["ok"] is True
    assert checks["CI reviewer evidence bundle"]["ok"] is True
    assert checks["public evidence bundle artifacts"]["ok"] is True
    assert checks["issue templates"]["ok"] is True
    assert checks["tracking snapshot"]["ok"] is True
    assert (
        checks["public tour JSON"]["detail"]
        == "schema, privacy, database, evidence bundle, recommended-action evidence, terminal validation evidence, dashboard quick-read and comparison review-path evidence, top-level review path, per-step success checks, and next commands verified"
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
        == "manifest, terminal and reviewer README action plan, key findings, review checklist, feedback runbook, reproduce-local commands, validation commands, limitations doc, aggregate reports, and audit artifact verified"
    )
    assert (
        "visual manifest schema and contract, screenshots, empty states, layout review, risk labels, metric cards, dashboard quick reads, report and comparison downloads, comparison preview, comparison review path, deltas, operator briefing, next review path, and success target verified"
        in checks["visual QA manifest evidence"]["detail"]
    )
    report_payload = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
    assert report_payload["schema_version"] == cli.REPORT_SCHEMA_VERSION
    assert report_payload["success_target"]["metric"] == "largest_thread_share_pct"
    assert report_payload["success_target"]["target_value"] == 50.0
    assert report_payload["next_commands"]
    assert report_payload["next_command_templates"]
    assert report_payload["review_path"][0]["label"] == "Save this report JSON"
    report_text = report.read_text(encoding="utf-8")
    assert "## Next Run Success Target" in report_text
    assert "## Recommended Action" in report_text
    assert "Action: apply next run habit" in report_text
    assert "## Review Path" in report_text
    assert "Save this report JSON" in report_text
    assert "## Follow-up Commands" in report_text


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
    assert "codex-observe demo --db missing.sqlite" in payload["next_commands"]
    assert payload["review_path"][0]["label"] == "Create demo data"
    assert payload["review_path"][1]["label"] == "Ingest local logs"


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


def test_ingest_payload_and_text_include_review_path() -> None:
    result = SimpleNamespace(
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
    assert "Review path:" in text
    assert (
        "Verify database health: codex-observe doctor --db demo.sqlite --json" in text
    )
    assert "Success check: doctor JSON status is ok and review_path is present." in text

    empty_result = SimpleNamespace(
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

    missing = tmp_path / "missing.sqlite"
    missing_status, missing_report = cli.doctor_report(str(missing))

    assert missing_status == 2
    assert missing_report["status"] == "missing"
    assert [item["label"] for item in missing_report["review_path"]] == [
        "Create synthetic database",
        "Ingest local logs",
    ]
    assert missing_report["review_path"][0]["command"] == (
        f"codex-observe demo --db {missing}"
    )


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
    assert (
        "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json"
        in payload["next_commands"]
    )
    assert (
        "codex-observe evidence-bundle --out .artifacts/public-evidence"
        in payload["next_commands"]
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
    assert any("Tool out column" in item for item in evidence)
    assert any("structured aggregate drivers" in item for item in evidence)
    assert any("driver_summary" in item for item in evidence)
    assert any("review_path" in item for item in evidence)
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
    assert payload["review_path"][2]["command"] == (
        "codex-observe sessions --db demo.sqlite --json"
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
    assert "Top opportunity: Largest thread; 33.2k tokens" in report_lines
    assert "Next action: Set a stop condition" in report_lines
    assert (
        "Success target: largest_thread_share_pct: 57.7% -> below 50.0%" in report_lines
    )
    assert "Triage risk: high -> moderate (improved)" in comparison_lines
    assert "Opportunity change: Largest thread improved." in comparison_lines
    assert "Next step: Keep the change." in comparison_lines
    assert (
        "Next validation command: codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json"
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
        assert payload["artifacts"]["report_markdown"] == "demo/run-report.md"
        assert payload["review_summary"][0]["label"] == "Run triage"
        assert payload["review_checklist"][0]["label"] == "Confirm the bundle boundary"
        assert (
            payload["action_plan"][0]["label"] == "Establish the safe review boundary"
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
    assert (
        "next_report: codex-observe report --db <db> --session-id <next-session-id>"
        in captured.out
    )
    assert (
        "next_comparison: codex-observe compare --before-report <after-report.json>"
        in captured.out
    )
    assert "audit_json: audit/audit.json" in captured.out
