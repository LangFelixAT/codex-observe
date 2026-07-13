from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("visual_qa", ROOT / "scripts" / "visual_qa.py")
assert SPEC and SPEC.loader
visual_qa = module_from_spec(SPEC)
SPEC.loader.exec_module(visual_qa)
screenshot_quality_failures = visual_qa.screenshot_quality_failures
layout_review_failures = visual_qa.layout_review_failures
visible_text_has_error = visual_qa.visible_text_has_error
PLAYWRIGHT_INSTALL_HINT = visual_qa.PLAYWRIGHT_INSTALL_HINT
build_visual_manifest = visual_qa.build_visual_manifest
write_visual_manifest = visual_qa.write_visual_manifest
screenshot_metadata = visual_qa.screenshot_metadata
evidence_path_label = visual_qa.evidence_path_label
visual_manifest_failures = visual_qa.visual_manifest_failures
verify_visual_manifest = visual_qa.verify_visual_manifest
visual_manifest_file_failures = visual_qa.visual_manifest_file_failures
metric_card_failures = visual_qa.metric_card_failures
metric_card_value_failures = visual_qa.metric_card_value_failures
sidebar_risk_label_failures = visual_qa.sidebar_risk_label_failures
operator_briefing_failures = visual_qa.operator_briefing_failures
download_control_failures = visual_qa.download_control_failures
comparison_preview_failures = visual_qa.comparison_preview_failures
comparison_delta_failures = visual_qa.comparison_delta_failures
visual_empty_state_failures = visual_qa.visual_empty_state_failures


def test_playwright_install_hint_uses_project_extras() -> None:
    assert 'python -m pip install -e ".[visual]"' in PLAYWRIGHT_INSTALL_HINT
    assert 'python -m pip install -e ".[dev]"' in PLAYWRIGHT_INSTALL_HINT
    assert "python -m pip install playwright" not in PLAYWRIGHT_INSTALL_HINT
    assert "python -m playwright install chromium" in PLAYWRIGHT_INSTALL_HINT


def test_visible_text_has_error_detects_streamlit_exception_markers() -> None:
    assert visible_text_has_error("StreamlitAPIException: bad widget")
    assert visible_text_has_error("Traceback\nModuleNotFoundError")
    assert not visible_text_has_error("Codex Observe dashboard loaded")


def test_screenshot_quality_failures_accepts_nonblank_viewport_image(
    tmp_path: Path,
) -> None:
    path = tmp_path / "dashboard.png"
    image = Image.new("RGB", (390, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 389, 120), fill=(33, 104, 105))
    draw.rectangle(
        (20, 160, 360, 320), fill=(248, 250, 249), outline=(23, 32, 38), width=4
    )
    draw.text((30, 190), "Codex Observe", fill=(23, 32, 38))
    image.save(path)

    assert (
        screenshot_quality_failures(path, {"width": 390, "height": 900}, "narrow") == []
    )


def test_screenshot_quality_failures_flags_blank_or_wrong_size_image(
    tmp_path: Path,
) -> None:
    path = tmp_path / "blank.png"
    Image.new("RGB", (200, 200), "white").save(path)

    failures = screenshot_quality_failures(
        path, {"width": 390, "height": 900}, "narrow"
    )

    assert any("width" in failure for failure in failures)
    assert any("height" in failure for failure in failures)
    assert any("color variation" in failure for failure in failures)
    assert any("visually blank" in failure for failure in failures)


def test_layout_review_failures_flags_horizontal_overflow_and_clipped_text() -> None:
    failures = layout_review_failures(
        {
            "viewport_width": 390,
            "document_width": 430,
            "overflowing_elements": [{"label": "Wide metric row", "tag": "div"}],
            "clipped_text_elements": [
                {"label": "Repeated prompt diagnostics", "tag": "span"}
            ],
        },
        "narrow",
    )

    assert any("horizontal overflow" in failure for failure in failures)
    assert any("overflows viewport" in failure for failure in failures)
    assert any("visible text appears clipped" in failure for failure in failures)


def test_layout_review_failures_accepts_clean_snapshot() -> None:
    assert (
        layout_review_failures(
            {
                "viewport_width": 1440,
                "document_width": 1440,
                "overflowing_elements": [],
                "clipped_text_elements": [],
            },
            "desktop",
        )
        == []
    )


def test_metric_card_failures_require_key_overview_cards() -> None:
    cards = [
        {"label": "Threads", "value": "3"},
        {"label": "Largest thread", "value": "33.2k tokens (57.7%)"},
        {"label": "Uncached input", "value": "22.7k tokens (39.5%)"},
    ]

    assert metric_card_failures(cards, "desktop") == []
    assert metric_card_value_failures(cards, "desktop") == []

    failures = metric_card_failures([{"label": "Threads", "value": "3"}], "narrow")

    assert "narrow: metric card not rendered: Largest thread" in failures
    assert "narrow: metric card not rendered: Uncached input" in failures


def test_metric_card_value_failures_reject_low_risk_default_selection() -> None:
    failures = metric_card_value_failures(
        [
            {"label": "Threads", "value": "3"},
            {"label": "Largest thread", "value": "2.9k tokens (34.5%)"},
            {"label": "Uncached input", "value": "1.2k tokens (14.3%)"},
        ],
        "desktop",
    )

    assert (
        "desktop: metric card Largest thread expected 33.2k tokens (57.7%), got 2.9k tokens (34.5%)"
        in failures
    )
    assert (
        "desktop: metric card Uncached input expected 22.7k tokens (39.5%), got 1.2k tokens (14.3%)"
        in failures
    )


def test_sidebar_risk_label_failures_require_high_and_low_risk_labels() -> None:
    assert sidebar_risk_label_failures(["High risk", "Low risk"], "desktop") == []

    failures = sidebar_risk_label_failures(["High risk"], "narrow")

    assert "narrow: sidebar risk label not found: Low risk" in failures


def test_download_control_failures_require_report_exports() -> None:
    assert (
        download_control_failures(
            [
                "Download report MD",
                "Download report JSON",
                "Download comparison MD",
                "Download comparison JSON",
            ],
            "desktop",
        )
        == []
    )

    failures = download_control_failures(["Download report MD"], "narrow")

    assert "narrow: report download control not found: Download report JSON" in failures


def test_comparison_preview_failures_require_quick_read_contract() -> None:
    assert (
        comparison_preview_failures(
            [
                {
                    "body": "Comparison quick read: regressed Triage movement: regressed Next step: Inspect new diagnostic first: Repeated prompt blocks. Next validation command codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json"
                }
            ],
            "desktop",
        )
        == []
    )

    failures = comparison_preview_failures([], "narrow")

    assert "narrow: comparison preview card not rendered" in failures


def test_comparison_delta_failures_require_metric_delta_cards() -> None:
    assert (
        comparison_delta_failures(
            [
                {"label": "Total tokens", "delta": "regressed: 49.1k (584.6%)"},
                {
                    "label": "Largest thread tokens",
                    "delta": "regressed: 30.3k (1044.8%)",
                },
            ],
            "desktop",
        )
        == []
    )

    failures = comparison_delta_failures(
        [{"label": "Total tokens", "delta": "improved: -49.1k (-85.4%)"}],
        "narrow",
    )

    assert (
        "narrow: comparison delta Total tokens missing direction: regressed" in failures
    )
    assert "narrow: comparison delta not found: Largest thread tokens" in failures


def test_operator_briefing_failures_require_briefing_contract() -> None:
    assert (
        operator_briefing_failures(
            [
                {
                    "label": "Operator briefing",
                    "heading": "High risk: Dominant thread concentration",
                    "best_habit": "Set a stop condition for the dominant thread",
                    "scale": "33.2k tokens (57.7% of run)",
                    "proof_target": "largest_thread_share_pct: 57.7% -> below 50.0%",
                }
            ],
            "desktop",
        )
        == []
    )

    failures = operator_briefing_failures([], "narrow")

    assert "narrow: operator briefing card not rendered" in failures


def test_evidence_path_label_preserves_relative_paths_and_redacts_external_absolute_paths(
    tmp_path: Path,
) -> None:
    assert evidence_path_label(".artifacts/demo/codex_observe_demo.sqlite") == (
        ".artifacts/demo/codex_observe_demo.sqlite"
    )
    assert evidence_path_label(tmp_path / "private.sqlite") == "[redacted-path]"


def complete_viewport_results(tmp_path: Path) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    for name, viewport in visual_qa.VIEWPORTS.items():
        screenshot = tmp_path / f"dashboard-{name}.png"
        Image.new("RGB", (viewport["width"], viewport["height"]), (42, 120, 121)).save(
            screenshot
        )
        results[name] = {
            "viewport": viewport,
            "screenshot": screenshot_metadata(screenshot),
            "tabs_exercised": list(visual_qa.TAB_CHECKS.keys()),
            "quick_read_evidence": list(visual_qa.EXPECTED_QUICK_READ_EVIDENCE),
            "agent_detail_selector_exercised": True,
            "sidebar_risk_labels": ["High risk", "Low risk"],
            "metric_cards": [
                {"label": "Threads", "value": "3"},
                {"label": "Largest thread", "value": "33.2k tokens (57.7%)"},
                {"label": "Uncached input", "value": "22.7k tokens (39.5%)"},
            ],
            "success_targets": [
                {
                    "metric": "largest_thread_share_pct",
                    "current": "57.7%",
                    "target": "below 50.0%",
                }
            ],
            "download_controls": [
                "Download report MD",
                "Download report JSON",
                "Download comparison MD",
                "Download comparison JSON",
            ],
            "operator_briefings": [
                {
                    "label": "Operator briefing",
                    "heading": "High risk: Dominant thread concentration",
                    "action": "Inspect the largest thread before changing workflow.",
                    "best_habit": "Set a stop condition for the dominant thread",
                    "scale": "33.2k tokens (57.7% of run)",
                    "proof_target": "largest_thread_share_pct: 57.7% -> below 50.0%",
                }
            ],
            "comparison_previews": [
                {
                    "label": "Comparison quick read: regressed",
                    "body": "Comparison quick read: regressed Verdict: regressed; largest change: Total tokens +49.1k (regressed). Triage movement: regressed Next step: Inspect new diagnostic first: Repeated prompt blocks. Next validation command codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json",
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
            "layout_review": {
                "viewport_width": viewport["width"],
                "document_width": viewport["width"],
                "overflowing_elements": [],
                "clipped_text_elements": [],
            },
        }
    return results


def complete_empty_state_results(tmp_path: Path) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    for state_name, title in visual_qa.EMPTY_STATE_CHECKS.items():
        viewport_results: dict[str, dict[str, object]] = {}
        for name, viewport in visual_qa.VIEWPORTS.items():
            screenshot = tmp_path / f"dashboard-{state_name}-{name}.png"
            Image.new(
                "RGB", (viewport["width"], viewport["height"]), (248, 250, 249)
            ).save(screenshot)
            viewport_results[name] = {
                "viewport": viewport,
                "screenshot": screenshot_metadata(screenshot),
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
        results[state_name] = {
            "database": f".artifacts/visual/{state_name}.sqlite",
            "viewports": viewport_results,
        }
    return results


def test_visual_manifest_records_review_evidence(tmp_path: Path) -> None:
    viewport_results = complete_viewport_results(tmp_path)

    manifest = build_visual_manifest(
        url="http://127.0.0.1:8502",
        db_path=".artifacts/demo/codex_observe_demo.sqlite",
        output_dir=tmp_path,
        viewport_results=viewport_results,
        empty_state_results=complete_empty_state_results(tmp_path),
    )
    manifest_path = tmp_path / "visual-qa-manifest.json"
    write_visual_manifest(manifest_path, manifest)
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert loaded["url"] == "http://127.0.0.1:8502"
    assert loaded["database"] == ".artifacts/demo/codex_observe_demo.sqlite"
    assert loaded["output_dir"] == "[redacted-path]"
    assert loaded["checks"]["tabs_expected"] == list(visual_qa.TAB_CHECKS.keys())
    assert loaded["checks"]["layout_review"] == "passed"
    assert loaded["checks"]["empty_states"] == "passed"
    assert (
        loaded["viewports"]["desktop"]["screenshot"]["filename"]
        == "dashboard-desktop.png"
    )
    assert loaded["viewports"]["desktop"]["screenshot"]["width"] == 1440
    assert loaded["viewports"]["desktop"]["tabs_exercised"] == list(
        visual_qa.TAB_CHECKS.keys()
    )
    assert loaded["viewports"]["desktop"]["quick_read_evidence"] == list(
        visual_qa.EXPECTED_QUICK_READ_EVIDENCE
    )
    assert loaded["viewports"]["desktop"]["agent_detail_selector_exercised"] is True
    assert loaded["viewports"]["desktop"]["sidebar_risk_labels"] == [
        "High risk",
        "Low risk",
    ]
    assert loaded["viewports"]["desktop"]["metric_cards"][1] == {
        "label": "Largest thread",
        "value": "33.2k tokens (57.7%)",
    }
    assert loaded["viewports"]["desktop"]["success_targets"][0] == {
        "metric": "largest_thread_share_pct",
        "current": "57.7%",
        "target": "below 50.0%",
    }
    assert loaded["viewports"]["desktop"]["download_controls"] == [
        "Download report MD",
        "Download report JSON",
        "Download comparison MD",
        "Download comparison JSON",
    ]
    assert loaded["viewports"]["desktop"]["operator_briefings"][0] == {
        "label": "Operator briefing",
        "heading": "High risk: Dominant thread concentration",
        "action": "Inspect the largest thread before changing workflow.",
        "best_habit": "Set a stop condition for the dominant thread",
        "scale": "33.2k tokens (57.7% of run)",
        "proof_target": "largest_thread_share_pct: 57.7% -> below 50.0%",
    }
    assert loaded["viewports"]["desktop"]["comparison_previews"][0]["label"] == (
        "Comparison quick read: regressed"
    )
    assert loaded["viewports"]["desktop"]["comparison_deltas"][0] == {
        "label": "Total tokens",
        "before_after": "8.4k -> 57.5k",
        "delta": "regressed: 49.1k (584.6%)",
    }
    assert loaded["viewports"]["desktop"]["layout_review"]["document_width"] == 1440
    assert (
        loaded["empty_states"]["missing_database"]["viewports"]["desktop"]["title"]
        == "No database found"
    )
    assert (
        loaded["empty_states"]["empty_database"]["viewports"]["narrow"]["commands"][0][
            "label"
        ]
        == "Try synthetic data"
    )
    assert visual_manifest_failures(loaded) == []


def test_visual_manifest_failures_rejects_incomplete_evidence(tmp_path: Path) -> None:
    manifest = build_visual_manifest(
        url="http://127.0.0.1:8502",
        db_path=".artifacts/demo/codex_observe_demo.sqlite",
        output_dir=tmp_path,
        viewport_results={
            "desktop": {
                "viewport": {"width": 1440, "height": 1000},
                "screenshot": {
                    "filename": "dashboard-desktop.png",
                    "width": 100,
                    "height": 100,
                    "bytes": 0,
                },
                "tabs_exercised": ["Overview"],
                "agent_detail_selector_exercised": False,
                "sidebar_risk_labels": ["High risk"],
                "metric_cards": [{"label": "Threads", "value": "3"}],
                "success_targets": [],
                "download_controls": ["Download report MD"],
                "operator_briefings": [],
                "comparison_previews": [],
                "comparison_deltas": [],
                "layout_review": {
                    "viewport_width": 390,
                    "document_width": 430,
                    "overflowing_elements": [{"label": "wide", "tag": "div"}],
                    "clipped_text_elements": [],
                },
            }
        },
        empty_state_results={},
    )

    failures = visual_manifest_failures(manifest)

    assert "manifest desktop tabs_exercised incomplete" in failures
    assert "manifest desktop missing quick-read evidence" in failures
    assert "manifest desktop agent detail selector was not exercised" in failures
    assert "manifest desktop screenshot width mismatch" in failures
    assert "manifest desktop screenshot is empty" in failures
    assert "manifest desktop sidebar risk label not found: Low risk" in failures
    assert "manifest desktop metric card not rendered: Largest thread" in failures
    assert "manifest desktop metric card not rendered: Uncached input" in failures
    assert "manifest desktop success target card not rendered" in failures
    assert "manifest desktop operator briefing card not rendered" in failures
    assert "manifest desktop comparison preview card not rendered" in failures
    assert "manifest desktop comparison delta cards not rendered" in failures
    assert (
        "manifest desktop report download control not found: Download report JSON"
        in failures
    )
    assert "manifest desktop layout review contains failures" in failures
    assert "manifest missing narrow viewport evidence" in failures
    assert "manifest missing missing_database empty-state evidence" in failures
    assert "manifest missing empty_database empty-state evidence" in failures


def test_verify_visual_manifest_reports_success_and_failures(tmp_path: Path) -> None:
    manifest = build_visual_manifest(
        url="http://127.0.0.1:8502",
        db_path=".artifacts/demo/codex_observe_demo.sqlite",
        output_dir=tmp_path,
        viewport_results=complete_viewport_results(tmp_path),
        empty_state_results=complete_empty_state_results(tmp_path),
    )
    path = tmp_path / "visual-qa-manifest.json"
    write_visual_manifest(path, manifest)

    assert manifest["schema_version"] == visual_qa.VISUAL_MANIFEST_SCHEMA_VERSION
    assert verify_visual_manifest(path) == (0, [])

    missing_status, missing_failures = verify_visual_manifest(tmp_path / "missing.json")
    assert missing_status == 2
    assert any("missing visual QA manifest" in failure for failure in missing_failures)

    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    bad_status, bad_failures = verify_visual_manifest(bad)
    assert bad_status == 1
    assert any("not valid JSON" in failure for failure in bad_failures)


def test_verify_visual_manifest_checks_referenced_screenshot_files(
    tmp_path: Path,
) -> None:
    manifest = build_visual_manifest(
        url="http://127.0.0.1:8502",
        db_path=".artifacts/demo/codex_observe_demo.sqlite",
        output_dir=tmp_path,
        viewport_results=complete_viewport_results(tmp_path),
        empty_state_results=complete_empty_state_results(tmp_path),
    )
    path = tmp_path / "visual-qa-manifest.json"
    write_visual_manifest(path, manifest)

    (tmp_path / "dashboard-narrow.png").unlink()
    missing_status, missing_failures = verify_visual_manifest(path)

    assert missing_status == 1
    assert (
        "manifest narrow screenshot file missing: dashboard-narrow.png"
        in missing_failures
    )

    Image.new("RGB", (390, 900), (42, 120, 121)).save(tmp_path / "dashboard-narrow.png")
    manifest["viewports"]["desktop"]["screenshot"]["bytes"] = 0
    assert "manifest desktop screenshot is empty" in visual_manifest_file_failures(
        manifest, tmp_path
    )
