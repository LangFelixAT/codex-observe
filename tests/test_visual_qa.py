from __future__ import annotations

import json
import socket
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

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
risk_distribution_failures = visual_qa.risk_distribution_failures
metric_card_failures = visual_qa.metric_card_failures
metric_card_value_failures = visual_qa.metric_card_value_failures
sidebar_risk_label_failures = visual_qa.sidebar_risk_label_failures
sidebar_risk_filter_failures = visual_qa.sidebar_risk_filter_failures
sidebar_focus_filter_failures = visual_qa.sidebar_focus_filter_failures
sidebar_session_search_failures = visual_qa.sidebar_session_search_failures
sidebar_session_detail_failures = visual_qa.sidebar_session_detail_failures
operator_briefing_failures = visual_qa.operator_briefing_failures
action_first_layout_failures = visual_qa.action_first_layout_failures
collect_review_paths = visual_qa.collect_review_paths
review_path_failures = visual_qa.review_path_failures
next_run_checklist_failures = visual_qa.next_run_checklist_failures
next_run_brief_failures = visual_qa.next_run_brief_failures
next_run_copy_control_failures = visual_qa.next_run_copy_control_failures
feedback_handoff_failures = visual_qa.feedback_handoff_failures
download_control_failures = visual_qa.download_control_failures
collect_report_scope_warnings = visual_qa.collect_report_scope_warnings
collect_comparison_selections = visual_qa.collect_comparison_selections
comparison_selection_failures = visual_qa.comparison_selection_failures
comparison_direction_failures = visual_qa.comparison_direction_failures
comparison_preview_failures = visual_qa.comparison_preview_failures
comparison_review_path_failures = visual_qa.comparison_review_path_failures
comparison_delta_failures = visual_qa.comparison_delta_failures
collect_comparison_scope_warnings = visual_qa.collect_comparison_scope_warnings
visual_empty_state_failures = visual_qa.visual_empty_state_failures


def test_port_is_available_detects_existing_listener() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]

        assert visual_qa.port_is_available("127.0.0.1", port) is False


def test_resolve_visual_qa_port_uses_requested_block_when_free(monkeypatch) -> None:
    checked_ports = []

    def fake_port_is_available(host: str, port: int) -> bool:
        assert host == "127.0.0.1"
        checked_ports.append(port)
        return True

    monkeypatch.setattr(visual_qa, "port_is_available", fake_port_is_available)

    assert visual_qa.resolve_visual_qa_port("127.0.0.1", 8501) == 8501
    assert checked_ports == [8501, 8502, 8503]


def test_resolve_visual_qa_port_falls_back_when_default_block_is_busy(
    monkeypatch,
) -> None:
    busy_ports = {8501}

    def fake_port_is_available(host: str, port: int) -> bool:
        return port not in busy_ports

    monkeypatch.setattr(visual_qa, "port_is_available", fake_port_is_available)

    assert visual_qa.resolve_visual_qa_port("127.0.0.1", 8501) == 8600


def test_resolve_visual_qa_port_rejects_explicit_busy_block(monkeypatch) -> None:
    def fake_port_is_available(host: str, port: int) -> bool:
        return port != 8765

    monkeypatch.setattr(visual_qa, "port_is_available", fake_port_is_available)

    with pytest.raises(RuntimeError, match="8765-8767 is busy"):
        visual_qa.resolve_visual_qa_port("127.0.0.1", 8765)


def test_playwright_install_hint_uses_project_extras() -> None:
    assert 'python -m pip install -e ".[visual]"' in PLAYWRIGHT_INSTALL_HINT
    assert 'python -m pip install -e ".[dev]"' in PLAYWRIGHT_INSTALL_HINT
    assert "python -m pip install playwright" not in PLAYWRIGHT_INSTALL_HINT
    assert "python -m playwright install chromium" in PLAYWRIGHT_INSTALL_HINT


def test_stop_process_tree_uses_taskkill_for_windows_children(monkeypatch) -> None:
    calls = []

    class FakeProcess:
        pid = 12345

        def __init__(self) -> None:
            self.wait_timeouts = []

        def poll(self) -> None:
            return None

        def wait(self, timeout: float) -> None:
            self.wait_timeouts.append(timeout)

        def terminate(self) -> None:
            raise AssertionError("Windows cleanup should use taskkill")

        def kill(self) -> None:
            raise AssertionError(
                "taskkill cleanup should not call kill after wait succeeds"
            )

    def fake_run(command, stdout, stderr, check):
        calls.append(
            {"command": command, "stdout": stdout, "stderr": stderr, "check": check}
        )

    monkeypatch.setattr(visual_qa.os, "name", "nt")
    monkeypatch.setattr(visual_qa.subprocess, "run", fake_run)
    process = FakeProcess()

    visual_qa.stop_process_tree(process, timeout_s=3)

    assert calls == [
        {
            "command": ["taskkill", "/PID", "12345", "/T", "/F"],
            "stdout": visual_qa.subprocess.DEVNULL,
            "stderr": visual_qa.subprocess.DEVNULL,
            "check": False,
        }
    ]
    assert process.wait_timeouts == [3]


def test_stop_process_tree_kills_process_when_graceful_stop_times_out(
    monkeypatch,
) -> None:
    class FakeProcess:
        pid = 67890

        def __init__(self) -> None:
            self.terminated = False
            self.killed = False
            self.wait_calls = 0

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float) -> None:
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise visual_qa.subprocess.TimeoutExpired("streamlit", timeout)

        def kill(self) -> None:
            self.killed = True

    monkeypatch.setattr(visual_qa.os, "name", "posix")
    process = FakeProcess()

    visual_qa.stop_process_tree(process, timeout_s=2)

    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == 2


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


def test_layout_review_failures_ignores_transient_streamlit_stop_control() -> None:
    assert (
        layout_review_failures(
            {
                "viewport_width": 390,
                "document_width": 390,
                "overflowing_elements": [],
                "clipped_text_elements": [{"label": "Stop", "tag": "button"}],
            },
            "empty_database narrow",
        )
        == []
    )


def test_metric_card_failures_require_key_overview_cards() -> None:
    cards = [
        {"label": "Threads", "value": "3"},
        {"label": "Focus", "value": "Thread"},
        {"label": "Duration", "value": "24 min"},
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


def test_risk_distribution_failures_require_overview_distribution() -> None:
    assert (
        risk_distribution_failures(
            [
                {
                    "label": "Risk distribution",
                    "body": "Risk distribution 2 imported conversations High risk 1 Medium risk 0 Low risk 1 Unknown 0",
                }
            ],
            "desktop",
        )
        == []
    )

    failures = risk_distribution_failures([], "narrow")

    assert "narrow: risk distribution card not rendered" in failures

    failures = risk_distribution_failures(
        [{"label": "Risk distribution", "body": "Risk distribution"}], "desktop"
    )

    assert "desktop: risk distribution missing: High risk" in failures
    assert "desktop: risk distribution missing: 2 imported conversations" in failures


def test_sidebar_risk_label_failures_require_high_and_low_risk_labels() -> None:
    assert sidebar_risk_label_failures(["High risk", "Low risk"], "desktop") == []

    failures = sidebar_risk_label_failures(["High risk"], "narrow")

    assert "narrow: sidebar risk label not found: Low risk" in failures


def test_sidebar_risk_filter_failures_require_filter_control() -> None:
    assert sidebar_risk_filter_failures(["Risk filter"], "desktop") == []

    failures = sidebar_risk_filter_failures([], "narrow")

    assert "narrow: sidebar Risk filter evidence not found: Risk filter" in failures


def test_collect_sidebar_risk_filter_uses_visible_text_and_aria_labels() -> None:
    class FakePage:
        def evaluate(self, script: str) -> list[str]:
            assert "document.body.innerText" in script
            assert "querySelectorAll('[aria-label]')" in script
            return ["Risk filter"]

    assert visual_qa.collect_sidebar_risk_filter(FakePage()) == ["Risk filter"]


def test_open_selectbox_targets_narrow_combobox_with_trusted_keyboard_input() -> None:
    class FakeSelector:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def press(self, key: str) -> None:
            self.calls.append(("press", key))

        def click(self) -> None:
            self.calls.append(("click", None))

    narrow = FakeSelector()
    desktop = FakeSelector()

    visual_qa.open_selectbox(narrow, "narrow")
    visual_qa.open_selectbox(desktop, "desktop")

    assert narrow.calls == [("press", "ArrowDown")]
    assert desktop.calls == [("click", None)]


def test_focus_option_label_prefers_target_and_skips_empty_categories() -> None:
    options = ["All focuses", "Thread (2)", "Guardian (0)", "Monitor (1)"]

    assert visual_qa.focus_option_label(options, "Thread") == "Thread (2)"
    assert visual_qa.focus_option_label(options, "Guardian") == "Thread (2)"
    assert visual_qa.focus_option_label(options, None) == "Thread (2)"
    assert visual_qa.focus_option_label(options, "All focuses") == "All focuses"
    assert visual_qa.focus_option_label(["All focuses", "Thread (0)"], "Thread") is None


def test_sidebar_focus_filter_failures_require_exercised_filter_contract() -> None:
    evidence = dict(visual_qa.EXPECTED_SIDEBAR_FOCUS_FILTER)

    assert sidebar_focus_filter_failures(evidence, "desktop") == []

    evidence["filtered"] = False
    evidence["restored"] = False
    failures = sidebar_focus_filter_failures(evidence, "narrow")

    assert "narrow: sidebar Focus filter filtered not verified" in failures
    assert "narrow: sidebar Focus filter restored not verified" in failures


def test_sidebar_focus_filter_failures_accept_real_profile_stable_target() -> None:
    evidence = dict(visual_qa.EXPECTED_SIDEBAR_FOCUS_FILTER)
    evidence["target"] = "Guardian"

    assert sidebar_focus_filter_failures(evidence, "desktop", "real") == []


def test_sidebar_session_search_failures_require_find_session_control() -> None:
    assert sidebar_session_search_failures(["Find session"], "desktop") == []

    failures = sidebar_session_search_failures([], "narrow")

    assert "narrow: sidebar session search evidence not found: Find session" in failures


def test_collect_sidebar_session_search_uses_visible_text_and_aria_labels() -> None:
    class FakePage:
        def evaluate(self, script: str) -> list[str]:
            assert "document.body.innerText" in script
            assert "querySelectorAll('[aria-label]')" in script
            return ["Find session"]

    assert visual_qa.collect_sidebar_session_search(FakePage()) == ["Find session"]


def test_sidebar_session_detail_failures_require_snapshot_context() -> None:
    assert (
        sidebar_session_detail_failures(
            ["Focus: Thread", "24 min duration", "6 snapshots"], "desktop"
        )
        == []
    )

    failures = sidebar_session_detail_failures([], "narrow")

    assert "narrow: sidebar session detail not found: Focus: Thread" in failures
    assert "narrow: sidebar session detail not found: 24 min duration" in failures
    assert "narrow: sidebar session detail not found: 6 snapshots" in failures


def test_collect_sidebar_session_details_uses_javascript_word_boundaries() -> None:
    class FakePage:
        def evaluate(self, script: str) -> list[str]:
            assert r"/\b[\d,.]+[kKmMbB]?\s+snapshots?\b/g" in script
            assert (
                r"/\b\d+(?:\.\d+)?\s+(?:min|hours?|days?)(?:\s+|[^\w]+)duration\b/g"
                in script
            )
            assert r"/Focus:\s+\w+(?:\s+\w+)?/g" in script
            assert r"/\\b" not in script
            return ["Focus: Thread", "24 min duration", "6 snapshots"]

    assert visual_qa.collect_sidebar_session_details(FakePage()) == [
        "Focus: Thread",
        "24 min duration",
        "6 snapshots",
    ]


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


def test_collect_report_scope_warnings_reads_warning_cards() -> None:
    class FakePage:
        def evaluate(self, script: str) -> list[str]:
            assert ".co-report-scope" in script
            return ["Ingest scope: Sampled ingest"]

    assert collect_report_scope_warnings(FakePage()) == ["Ingest scope: Sampled ingest"]


def test_collect_comparison_selections_records_selected_relationship() -> None:
    class FakePage:
        def evaluate(self, script: str) -> list[dict[str, str]]:
            assert "stSelectbox" in script
            assert "Compare with run" in script
            return [
                {
                    "label": "Compare with run",
                    "selected": "Next run | Low risk | demo-session-focused-followup",
                    "body": "Compare with run Next run | Low risk | demo-session-focused-followup",
                }
            ]

    selections = collect_comparison_selections(FakePage())

    assert comparison_selection_failures(selections, "desktop") == []
    assert comparison_selection_failures([], "desktop", profile="real") == []


def test_comparison_selection_failures_require_demo_default_and_real_relationship() -> (
    None
):
    failures = comparison_selection_failures(
        [{"label": "Compare with run", "selected": "High risk | unrelated"}],
        "narrow",
    )

    assert "narrow: comparison selection missing relationship: Next run" in failures
    assert "narrow: comparison selection missing risk: Low risk" in failures
    assert (
        "narrow: comparison selection missing session_id: demo-session-focused-followup"
        in failures
    )

    real_failures = comparison_selection_failures(
        [{"label": "Compare with run", "selected": "High risk | run"}],
        "desktop",
        profile="real",
    )
    assert (
        "desktop: comparison selection missing chronological relationship"
        in real_failures
    )


def test_comparison_direction_failures_require_chronological_context() -> None:
    assert (
        comparison_direction_failures(
            [
                {
                    "label": "Comparison direction",
                    "before": "2026-01-01T12:00+00:00 | High risk | 57.5k tokens",
                    "after": "2026-01-01T12:24+00:00 | Low risk | 8.4k tokens",
                    "basis": "Ordered by start time.",
                }
            ],
            "desktop",
        )
        == []
    )

    failures = comparison_direction_failures([], "narrow")

    assert "narrow: comparison direction card not rendered" in failures


def test_real_profile_comparison_direction_is_optional_but_complete_when_present() -> (
    None
):
    assert comparison_direction_failures([], "desktop", profile="real") == []

    failures = comparison_direction_failures(
        [{"label": "Comparison direction", "before": "older"}],
        "desktop",
        profile="real",
    )

    assert "desktop: comparison direction missing after" in failures
    assert "desktop: comparison direction missing basis" in failures


def test_comparison_preview_failures_require_quick_read_contract() -> None:
    assert (
        comparison_preview_failures(
            [
                {
                    "body": "Comparison quick read: improved Triage movement: improved Next step: Keep the change, then target persisted diagnostic: Largest thread drives the run. Next validation command codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json"
                }
            ],
            "desktop",
        )
        == []
    )

    failures = comparison_preview_failures([], "narrow")

    assert "narrow: comparison preview card not rendered" in failures


def test_collect_comparison_scope_warnings_reads_warning_cards() -> None:
    class FakePage:
        def evaluate(self, script: str) -> list[str]:
            assert ".co-comparison-scope" in script
            return ["Ingest scope: Sampled ingest"]

    assert collect_comparison_scope_warnings(FakePage()) == [
        "Ingest scope: Sampled ingest"
    ]


def test_comparison_review_path_failures_require_ordered_steps() -> None:
    assert (
        comparison_review_path_failures(
            [
                {
                    "body": "Comparison review path Read the verdict Act on the recommendation Export the next run Compare against this after run File safe feedback"
                }
            ],
            "desktop",
        )
        == []
    )

    failures = comparison_review_path_failures([], "narrow")

    assert "narrow: comparison review path not rendered" in failures

    failures = comparison_review_path_failures(
        [{"body": "Comparison review path Read the verdict"}], "desktop"
    )

    assert (
        "desktop: comparison review path missing: Act on the recommendation" in failures
    )


def test_comparison_delta_failures_require_metric_delta_cards() -> None:
    assert (
        comparison_delta_failures(
            [
                {"label": "Total tokens", "delta": "improved: -49.1k (-85.4%)"},
                {"label": "Usage snapshots", "delta": "changed: -3 (-50.0%)"},
                {
                    "label": "Largest thread tokens",
                    "delta": "improved: -30.3k (-91.3%)",
                },
            ],
            "desktop",
        )
        == []
    )

    failures = comparison_delta_failures(
        [{"label": "Total tokens", "delta": "regressed: 49.1k (584.6%)"}],
        "narrow",
    )

    assert (
        "narrow: comparison delta Total tokens missing direction: improved" in failures
    )
    assert "narrow: comparison delta not found: Usage snapshots" in failures
    assert "narrow: comparison delta not found: Largest thread tokens" in failures


def test_real_profile_comparison_delta_failures_are_data_driven() -> None:
    assert (
        comparison_delta_failures(
            [
                {"label": "Total tokens", "delta": "regressed: 2.2B (536289.2%)"},
                {"label": "Uncached input tokens", "delta": "changed: 53.4M"},
            ],
            "desktop",
            profile="real",
        )
        == []
    )

    failures = comparison_delta_failures(
        [{"label": "Total tokens", "delta": "2.2B"}],
        "desktop",
        profile="real",
    )

    assert "desktop: comparison delta Total tokens missing direction" in failures


def test_action_first_layout_failures_require_navigation_and_plan_before_metrics() -> (
    None
):
    layout = {
        "briefing_before_tabs": True,
        "tabs_before_checklist": True,
        "checklist_before_brief": True,
        "brief_before_copy_prompt": True,
        "comparison_present": True,
        "copy_prompt_before_comparison": True,
        "comparison_before_metrics": True,
        "copy_prompt_before_metrics": True,
        "tabs_in_initial_viewport": True,
        "tabs_visible_count": 6,
        "tabs_total": 6,
    }

    assert action_first_layout_failures(layout, "desktop") == []

    real_single_run_layout = dict(layout)
    real_single_run_layout["comparison_present"] = False
    assert (
        action_first_layout_failures(real_single_run_layout, "desktop", profile="real")
        == []
    )
    assert (
        "desktop: comparison control is not rendered"
        in action_first_layout_failures(real_single_run_layout, "desktop")
    )

    layout["tabs_in_initial_viewport"] = False
    layout["copy_prompt_before_comparison"] = False
    layout["comparison_before_metrics"] = False
    layout["copy_prompt_before_metrics"] = False
    layout["tabs_visible_count"] = 5
    failures = action_first_layout_failures(layout, "narrow")

    assert (
        "narrow: tab navigation is not fully visible in the initial viewport"
        in failures
    )
    assert "narrow: copyable prompt does not precede comparison control" in failures
    assert "narrow: comparison control does not precede metric grid" in failures
    assert "narrow: copyable prompt does not precede metric grid" in failures
    assert (
        "narrow: complete tab navigation is not visible in the initial viewport"
        in failures
    )


def test_next_run_copy_control_failures_require_prompt_and_native_button() -> None:
    assert (
        next_run_copy_control_failures(
            [
                {
                    "prompt": "Next Codex run plan: Try one habit",
                    "has_copy_button": True,
                    "button_label": "Copy to clipboard",
                }
            ],
            "desktop",
        )
        == []
    )

    failures = next_run_copy_control_failures(
        [{"prompt": "Plan", "has_copy_button": False}], "narrow"
    )

    assert "narrow: next run copy prompt is missing" in failures
    assert "narrow: next run copy button is missing" in failures


def test_review_path_failures_require_next_review_path_contract() -> None:
    assert (
        review_path_failures(
            [
                {
                    "label": "Next review path",
                    "body": "Next review path Save report JSON Compare workflow change Validate next run File safe feedback PUBLIC_TOUR_FEEDBACK.md",
                }
            ],
            "desktop",
        )
        == []
    )

    failures = review_path_failures([], "narrow")

    assert "narrow: next review path card not rendered" in failures


def test_next_run_checklist_failures_require_operational_steps() -> None:
    assert (
        next_run_checklist_failures(
            [
                {
                    "label": "Next run checklist",
                    "body": "Next run checklist Before next run During next run After next run Set a stop condition for the dominant thread largest_thread_share_pct Export next-run-report.json",
                }
            ],
            "desktop",
        )
        == []
    )

    failures = next_run_checklist_failures([], "narrow")

    assert "narrow: next run checklist card not rendered" in failures

    failures = next_run_checklist_failures(
        [{"label": "Next run checklist", "body": "Next run checklist"}], "desktop"
    )

    assert "desktop: next run checklist missing: Before next run" in failures
    assert (
        "desktop: next run checklist missing: Export next-run-report.json" in failures
    )


def test_next_run_brief_failures_require_actionable_plan() -> None:
    assert (
        next_run_brief_failures(
            [
                {
                    "label": "Next run brief",
                    "body": "Next run brief Set a stop condition for the dominant thread Largest thread drives the run largest_thread_share_pct: 57.7% -> below 50.0% Pause or split the run when one thread starts to dominate the work.",
                }
            ],
            "desktop",
        )
        == []
    )

    failures = next_run_brief_failures([], "narrow")

    assert "narrow: next run brief card not rendered" in failures

    failures = next_run_brief_failures(
        [{"label": "Next run brief", "body": "Next run brief"}], "desktop"
    )

    assert (
        "desktop: next run brief missing: Set a stop condition for the dominant thread"
        in failures
    )
    assert (
        "desktop: next run brief missing: largest_thread_share_pct: 57.7% -> below 50.0%"
        in failures
    )


def test_guidance_consistency_failures_require_same_habit_and_target() -> None:
    operator = [
        {
            "best_habit": "Start a fresh session",
            "proof_target": "session_duration_hours: 3.0 days -> below 24.0 hours",
        }
    ]
    target = [
        {
            "metric": "session_duration_hours",
            "current": "3.0 days",
            "target": "below 24.0 hours",
        }
    ]
    aligned_brief = [
        {
            "body": "Next run brief Start a fresh session session_duration_hours: 3.0 days -> below 24.0 hours"
        }
    ]

    assert (
        visual_qa.guidance_consistency_failures(
            operator, target, aligned_brief, "desktop"
        )
        == []
    )

    failures = visual_qa.guidance_consistency_failures(
        operator,
        target,
        [
            {
                "body": "Next run brief Set a stop condition largest_thread_share_pct: 100.0% -> below 50.0%"
            }
        ],
        "narrow",
    )

    assert "narrow: operator habit does not match next run brief" in failures
    assert "narrow: proof target does not match next run brief" in failures


def test_feedback_handoff_failures_require_safe_feedback_contract() -> None:
    assert (
        feedback_handoff_failures(
            [
                {
                    "label": "Safe feedback handoff",
                    "body": "Safe feedback handoff docs/PUBLIC_TOUR_FEEDBACK.md .github/ISSUE_TEMPLATE/public_tour_feedback.yml synthetic or reviewed-redacted aggregate evidence codex-observe report JSON or Markdown private prompts Do not collect",
                }
            ],
            "desktop",
        )
        == []
    )

    failures = feedback_handoff_failures([], "narrow")

    assert "narrow: safe feedback handoff card not rendered" in failures

    failures = feedback_handoff_failures(
        [{"body": "Safe feedback handoff docs/PUBLIC_TOUR_FEEDBACK.md"}],
        "desktop",
    )

    assert "desktop: safe feedback handoff missing: private prompts" in failures


def test_answer_first_layout_failures_require_briefing_before_metrics_in_viewport() -> (
    None
):
    assert (
        visual_qa.answer_first_layout_failures(
            {
                "briefing_before_metrics": True,
                "briefing_in_initial_viewport": True,
                "briefing_top": 120,
                "briefing_bottom": 420,
                "metric_grid_top": 450,
                "viewport_height": 1000,
            },
            "desktop",
        )
        == []
    )

    failures = visual_qa.answer_first_layout_failures(
        {
            "briefing_before_metrics": False,
            "briefing_in_initial_viewport": False,
        },
        "narrow",
    )

    assert "narrow: operator briefing does not precede metric grid" in failures
    assert any(
        failure.startswith(
            "narrow: operator briefing is not fully visible in initial viewport"
        )
        for failure in failures
    )


def test_operator_briefing_failures_require_briefing_contract() -> None:
    assert (
        operator_briefing_failures(
            [
                {
                    "label": "Operator briefing",
                    "heading": "High risk run",
                    "action": "Primary risk signal: Largest thread drives the run.",
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
            "sidebar_risk_filter": ["Risk filter"],
            "sidebar_focus_filter": dict(visual_qa.EXPECTED_SIDEBAR_FOCUS_FILTER),
            "sidebar_session_search": ["Find session"],
            "sidebar_session_details": [
                "Focus: Thread",
                "24 min duration",
                "6 snapshots",
            ],
            "risk_distributions": [
                {
                    "label": "Risk distribution",
                    "body": "Risk distribution 2 imported conversations High risk 1 Medium risk 0 Low risk 1 Unknown 0",
                }
            ],
            "portfolio_briefings": [
                {
                    "label": "Portfolio briefing",
                    "body": "Portfolio briefing 1 of 2 sessions are high risk. Start with the recommended high-risk run, then compare against a lower-risk follow-up to find which habits worked. Dominant pattern: Largest thread concentration in 1 of 2 sessions; max 57.7%. Set stop conditions before one thread dominates repeated work. 50.0% high risk. Current view includes every imported session.",
                }
            ],
            "metric_cards": [
                {"label": "Threads", "value": "3"},
                {"label": "Focus", "value": "Thread"},
                {"label": "Duration", "value": "24 min"},
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
            "report_scope_warnings": [],
            "download_controls": [
                "Download report MD",
                "Download report JSON",
                "Download comparison MD",
                "Download comparison JSON",
            ],
            "answer_first_layout": {
                "briefing_before_metrics": True,
                "briefing_in_initial_viewport": True,
                "briefing_top": 120,
                "briefing_bottom": 420,
                "metric_grid_top": 1500,
                "viewport_height": viewport["height"],
            },
            "action_first_layout": {
                "briefing_before_tabs": True,
                "tabs_before_checklist": True,
                "checklist_before_brief": True,
                "brief_before_copy_prompt": True,
                "comparison_present": True,
                "copy_prompt_before_comparison": True,
                "comparison_before_metrics": True,
                "copy_prompt_before_metrics": True,
                "tabs_in_initial_viewport": True,
                "tabs_visible_count": 6,
                "tabs_total": 6,
                "briefing_bottom": 420,
                "tablist_top": 436,
                "tablist_bottom": 478,
                "checklist_top": 494,
                "brief_top": 750,
                "copy_prompt_top": 1100,
                "comparison_top": 1250,
                "metric_grid_top": 1500,
                "viewport_height": viewport["height"],
            },
            "operator_briefings": [
                {
                    "label": "Operator briefing",
                    "heading": "High risk run",
                    "action": "Primary risk signal: Largest thread drives the run.",
                    "best_habit": "Set a stop condition for the dominant thread",
                    "scale": "33.2k tokens (57.7% of run)",
                    "proof_target": "largest_thread_share_pct: 57.7% -> below 50.0%",
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
            "next_run_briefs": [
                {
                    "label": "Next run brief",
                    "body": "Next run brief Set a stop condition for the dominant thread Largest thread drives the run largest_thread_share_pct: 57.7% -> below 50.0% Pause or split the run when one thread starts to dominate the work.",
                }
            ],
            "next_run_copy_controls": [
                {
                    "prompt": "Next Codex run plan: Try one habit",
                    "has_copy_button": True,
                    "button_label": "Copy to clipboard",
                }
            ],
            "feedback_handoffs": [
                {
                    "label": "Safe feedback handoff",
                    "body": "Safe feedback handoff docs/PUBLIC_TOUR_FEEDBACK.md .github/ISSUE_TEMPLATE/public_tour_feedback.yml synthetic or reviewed-redacted aggregate evidence codex-observe report JSON or Markdown private prompts Do not collect",
                }
            ],
            "comparison_selections": [
                {
                    "label": "Compare with run",
                    "selected": "Next run | Low risk | 12:35 | 8.4k tokens | demo-session-focused-followup",
                    "body": "Compare with run Next run | Low risk | 12:35 | 8.4k tokens | demo-session-focused-followup",
                }
            ],
            "comparison_directions": [
                {
                    "label": "Comparison direction",
                    "before": "2026-01-01T12:00+00:00 | High risk | 57.5k tokens",
                    "after": "2026-01-01T12:24+00:00 | Low risk | 8.4k tokens",
                    "basis": "Ordered by start time.",
                }
            ],
            "comparison_previews": [
                {
                    "label": "Comparison quick read: improved",
                    "body": "Comparison quick read: improved Verdict: improved; largest change: Total tokens -49.1k (improved). Triage movement: improved Next step: Keep the change, then target persisted diagnostic: Largest thread drives the run. Next validation command codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json",
                }
            ],
            "comparison_scope_warnings": [],
            "comparison_review_paths": [
                {
                    "label": "Comparison review path",
                    "body": "Comparison review path Read the verdict Act on the recommendation Export the next run Compare against this after run File safe feedback",
                }
            ],
            "comparison_deltas": [
                {
                    "label": "Total tokens",
                    "before_after": "57.5k -> 8.4k",
                    "delta": "improved: -49.1k (-85.4%)",
                },
                {
                    "label": "Usage snapshots",
                    "before_after": "6 -> 3",
                    "delta": "changed: -3 (-50.0%)",
                },
                {
                    "label": "Largest thread tokens",
                    "before_after": "33.2k -> 2.9k",
                    "delta": "improved: -30.3k (-91.3%)",
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
    assert loaded["viewports"]["desktop"]["sidebar_risk_filter"] == ["Risk filter"]
    assert loaded["viewports"]["desktop"]["sidebar_focus_filter"] == (
        visual_qa.EXPECTED_SIDEBAR_FOCUS_FILTER
    )
    assert loaded["viewports"]["desktop"]["sidebar_session_search"] == ["Find session"]
    assert loaded["viewports"]["desktop"]["sidebar_session_details"] == [
        "Focus: Thread",
        "24 min duration",
        "6 snapshots",
    ]
    assert loaded["viewports"]["desktop"]["risk_distributions"][0]["label"] == (
        "Risk distribution"
    )
    assert loaded["viewports"]["desktop"]["metric_cards"][1] == {
        "label": "Focus",
        "value": "Thread",
    }
    assert loaded["viewports"]["desktop"]["metric_cards"][2] == {
        "label": "Duration",
        "value": "24 min",
    }
    assert loaded["viewports"]["desktop"]["metric_cards"][3] == {
        "label": "Largest thread",
        "value": "33.2k tokens (57.7%)",
    }
    assert loaded["viewports"]["desktop"]["success_targets"][0] == {
        "metric": "largest_thread_share_pct",
        "current": "57.7%",
        "target": "below 50.0%",
    }
    assert loaded["viewports"]["desktop"]["report_scope_warnings"] == []
    assert loaded["viewports"]["desktop"]["download_controls"] == [
        "Download report MD",
        "Download report JSON",
        "Download comparison MD",
        "Download comparison JSON",
    ]
    assert loaded["viewports"]["desktop"]["answer_first_layout"] == {
        "briefing_before_metrics": True,
        "briefing_in_initial_viewport": True,
        "briefing_top": 120,
        "briefing_bottom": 420,
        "metric_grid_top": 1500,
        "viewport_height": 1000,
    }
    assert loaded["viewports"]["desktop"]["action_first_layout"] == {
        "briefing_before_tabs": True,
        "tabs_before_checklist": True,
        "checklist_before_brief": True,
        "brief_before_copy_prompt": True,
        "comparison_present": True,
        "copy_prompt_before_comparison": True,
        "comparison_before_metrics": True,
        "copy_prompt_before_metrics": True,
        "tabs_in_initial_viewport": True,
        "tabs_visible_count": 6,
        "tabs_total": 6,
        "briefing_bottom": 420,
        "tablist_top": 436,
        "tablist_bottom": 478,
        "checklist_top": 494,
        "brief_top": 750,
        "copy_prompt_top": 1100,
        "comparison_top": 1250,
        "metric_grid_top": 1500,
        "viewport_height": 1000,
    }
    assert loaded["viewports"]["desktop"]["operator_briefings"][0] == {
        "label": "Operator briefing",
        "heading": "High risk run",
        "action": "Primary risk signal: Largest thread drives the run.",
        "best_habit": "Set a stop condition for the dominant thread",
        "scale": "33.2k tokens (57.7% of run)",
        "proof_target": "largest_thread_share_pct: 57.7% -> below 50.0%",
    }
    assert (
        loaded["viewports"]["desktop"]["review_paths"][0]["label"] == "Next review path"
    )
    assert (
        "Validate next run" in loaded["viewports"]["desktop"]["review_paths"][0]["body"]
    )
    assert loaded["viewports"]["desktop"]["next_run_checklists"][0]["label"] == (
        "Next run checklist"
    )
    assert (
        "Before next run"
        in loaded["viewports"]["desktop"]["next_run_checklists"][0]["body"]
    )
    assert loaded["viewports"]["desktop"]["next_run_briefs"][0]["label"] == (
        "Next run brief"
    )
    assert loaded["viewports"]["desktop"]["next_run_copy_controls"][0] == {
        "prompt": "Next Codex run plan: Try one habit",
        "has_copy_button": True,
        "button_label": "Copy to clipboard",
    }
    assert loaded["viewports"]["desktop"]["feedback_handoffs"][0]["label"] == (
        "Safe feedback handoff"
    )
    assert (
        "docs/PUBLIC_TOUR_FEEDBACK.md"
        in loaded["viewports"]["desktop"]["feedback_handoffs"][0]["body"]
    )
    assert (
        "Do not collect"
        in loaded["viewports"]["desktop"]["feedback_handoffs"][0]["body"]
    )
    assert loaded["viewports"]["desktop"]["comparison_selections"][0] == {
        "label": "Compare with run",
        "selected": "Next run | Low risk | 12:35 | 8.4k tokens | demo-session-focused-followup",
        "body": "Compare with run Next run | Low risk | 12:35 | 8.4k tokens | demo-session-focused-followup",
    }
    assert loaded["viewports"]["desktop"]["comparison_directions"][0] == {
        "label": "Comparison direction",
        "before": "2026-01-01T12:00+00:00 | High risk | 57.5k tokens",
        "after": "2026-01-01T12:24+00:00 | Low risk | 8.4k tokens",
        "basis": "Ordered by start time.",
    }
    assert loaded["viewports"]["desktop"]["comparison_previews"][0]["label"] == (
        "Comparison quick read: improved"
    )
    assert loaded["viewports"]["desktop"]["comparison_scope_warnings"] == []
    assert loaded["viewports"]["desktop"]["comparison_review_paths"][0]["label"] == (
        "Comparison review path"
    )
    assert (
        "Act on the recommendation"
        in loaded["viewports"]["desktop"]["comparison_review_paths"][0]["body"]
    )
    assert loaded["viewports"]["desktop"]["comparison_deltas"][0] == {
        "label": "Total tokens",
        "before_after": "57.5k -> 8.4k",
        "delta": "improved: -49.1k (-85.4%)",
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
                "risk_distributions": [],
                "metric_cards": [{"label": "Threads", "value": "3"}],
                "success_targets": [],
                "download_controls": ["Download report MD"],
                "action_first_layout": {},
                "operator_briefings": [],
                "review_paths": [],
                "next_run_checklists": [],
                "next_run_briefs": [],
                "next_run_copy_controls": [],
                "feedback_handoffs": [],
                "comparison_directions": [],
                "comparison_previews": [],
                "comparison_review_paths": [],
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
    assert "manifest desktop missing sidebar Risk filter evidence" in failures
    assert "manifest desktop missing sidebar Focus filter evidence" in failures
    assert "manifest desktop missing sidebar session search evidence" in failures
    assert "manifest desktop risk distribution card not rendered" in failures
    assert "manifest desktop metric card not rendered: Largest thread" in failures
    assert "manifest desktop metric card not rendered: Uncached input" in failures
    assert "manifest desktop success target card not rendered" in failures
    assert "manifest desktop missing answer-first layout evidence" in failures
    assert "manifest desktop missing action-first layout evidence" in failures
    assert "manifest desktop operator briefing card not rendered" in failures
    assert "manifest desktop next review path card not rendered" in failures
    assert "manifest desktop next run checklist card not rendered" in failures
    assert "manifest desktop native next run copy control not rendered" in failures
    assert "manifest desktop safe feedback handoff card not rendered" in failures
    assert "manifest desktop missing report scope warning evidence" in failures
    assert "manifest desktop missing comparison selection evidence" in failures
    assert "manifest desktop comparison preview card not rendered" in failures
    assert "manifest desktop comparison review path not rendered" in failures
    assert "manifest desktop missing comparison scope warning evidence" in failures
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


def test_real_profile_manifest_accepts_private_aggregate_variance(
    tmp_path: Path,
) -> None:
    viewport_results = deepcopy(complete_viewport_results(tmp_path))
    for raw in viewport_results.values():
        raw["sidebar_risk_labels"] = ["High risk"]
        raw["sidebar_session_details"] = ["Focus: Thread", "11 snapshots"]
        raw["risk_distributions"] = [
            {
                "label": "Risk distribution",
                "body": "Risk distribution 11 imported conversations High risk 2 Medium risk 4",
            }
        ]
        raw["portfolio_briefings"] = [
            {
                "label": "Portfolio briefing",
                "body": "Portfolio briefing 2 of 11 sessions are high risk. Dominant pattern: Largest thread concentration in 8 of 11 sessions; max 100.0%. Current view includes every imported session.",
            }
        ]
        raw["metric_cards"] = [
            {"label": "Threads", "value": "8"},
            {"label": "Focus", "value": "Thread"},
            {"label": "Duration", "value": "6.9 days"},
            {"label": "Largest thread", "value": "1.1B tokens (56.1%)"},
            {"label": "Uncached input", "value": "47.7M tokens (2.4%)"},
        ]
        raw["success_targets"] = [
            {
                "metric": "largest_thread_share_pct",
                "current": "56.1%",
                "target": "below 50.0%",
            }
        ]
        raw["download_controls"] = ["Download report MD", "Download report JSON"]
        raw["operator_briefings"] = [
            {
                "label": "Operator briefing",
                "heading": "High risk run",
                "action": "Primary risk signal: Largest thread drives the run.",
                "best_habit": "Split the dominant thread",
                "scale": "1.1B tokens (56.1% of run)",
                "proof_target": "largest_thread_share_pct: 56.1% -> below 50.0%",
            }
        ]
        raw["next_run_checklists"] = [
            {
                "label": "Next run checklist",
                "body": "Next run checklist Before next run During next run After next run",
            }
        ]
        raw["next_run_briefs"] = [
            {
                "label": "Next run brief",
                "body": "Next run brief Next Codex run plan Split the dominant thread largest_thread_share_pct: 56.1% -> below 50.0% Copy prompt",
            }
        ]
        raw["comparison_selections"] = []
        raw["comparison_directions"] = []
        raw["comparison_previews"] = []
        raw["comparison_review_paths"] = []
        raw["comparison_deltas"] = []

    manifest = build_visual_manifest(
        url="http://127.0.0.1:8502",
        profile=visual_qa.PROFILE_REAL,
        db_path=".artifacts/private/real-sessions.sqlite",
        output_dir=tmp_path,
        viewport_results=viewport_results,
        empty_state_results=complete_empty_state_results(tmp_path),
    )

    assert manifest["profile"] == visual_qa.PROFILE_REAL
    assert visual_manifest_failures(manifest) == []

    manifest["viewports"]["desktop"]["next_run_briefs"][0]["body"] = (
        "Next run brief Start a fresh session session_duration_hours: "
        "3.0 days -> below 24.0 hours"
    )
    failures = visual_manifest_failures(manifest)

    assert "manifest desktop operator habit does not match next run brief" in failures
    assert "manifest desktop proof target does not match next run brief" in failures


def test_visual_manifest_failures_rejects_unknown_profile(tmp_path: Path) -> None:
    manifest = build_visual_manifest(
        url="http://127.0.0.1:8502",
        profile="unknown",
        db_path=".artifacts/demo/codex_observe_demo.sqlite",
        output_dir=tmp_path,
        viewport_results=complete_viewport_results(tmp_path),
        empty_state_results=complete_empty_state_results(tmp_path),
    )

    assert "manifest profile is unsupported: unknown" in visual_manifest_failures(
        manifest
    )
