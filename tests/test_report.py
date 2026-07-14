from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_observe.demo import create_demo_database
from codex_observe.report import (
    COMPARISON_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    available_sessions,
    build_report,
    compare_reports,
    default_report_session,
    report_follow_up_commands,
    report_review_path,
    comparison_json,
    comparison_markdown,
    comparison_review_path,
    load_report_json,
    report_json,
    report_markdown,
    session_summaries,
    sort_session_summaries,
    session_summary_lines,
)


PRIVATE_DEMO_STRINGS = [
    "Analyze why this Codex run became expensive",
    "synthetic output line",
    "Get-Content massive.log",
    "Refactor parser normalization",
]


def demo_db(tmp_path: Path) -> Path:
    db = tmp_path / "demo.sqlite"
    create_demo_database(str(db), str(tmp_path / "sessions"))
    return db


def test_build_report_returns_privacy_safe_diagnostics_and_playbook(
    tmp_path: Path,
) -> None:
    db = demo_db(tmp_path)

    report = build_report(str(db))
    serialized = json.dumps(report)

    assert report["schema_version"] == REPORT_SCHEMA_VERSION
    assert report["privacy"]["mode"] == "aggregate-only"
    assert report["session"]["session_id"] == "demo-session-cost-review"
    assert report["summary"]["total_tokens"] == 57510
    assert report["summary"]["repeated_prompt_tokens"] > 0
    assert report["summary"]["largest_tool_output_chars"] > 0
    assert report["summary"]["largest_thread_share_pct"] == 57.7
    assert report["summary"]["repeated_prompt_share_pct"] == 17.4
    assert report["summary"]["uncached_input_share_pct"] == 39.5
    assert report["summary"]["workers"] == 1
    assert report["triage"]["risk_level"] == "high"
    assert report["triage"]["primary_driver"] == "Largest thread drives the run"
    assert (
        report["triage"]["next_action"]
        == "Set a stop condition for the dominant thread"
    )
    assert "Largest thread used 57.7% of total tokens." in report["triage"]["reasons"]
    assert (
        "Repeated prompt blocks used 17.4% of total tokens."
        in report["triage"]["reasons"]
    )
    assert "Uncached input used 39.5% of total tokens." in report["triage"]["reasons"]
    assert report["headline"] == {
        "headline": "57.5k total tokens; largest thread 33.2k (57.7%); repeated prompts 10.0k (17.4%); largest tool output 4.0k chars.",
        "top_diagnostic": "Largest thread drives the run",
        "recommendation": "Set a stop condition for the dominant thread",
    }
    assert report["diagnostics"][0]["Diagnostic"] == "Largest thread drives the run"
    assert (
        report["playbook"][0]["Habit"] == "Set a stop condition for the dominant thread"
    )
    assert report["playbook"][0]["Impact"] == "Targets the largest total-token driver."
    assert report["opportunities"][0] == {
        "Rank": 1,
        "Habit": "Set a stop condition for the dominant thread",
        "Driver": "Largest thread",
        "Scale": "33.2k tokens (57.7% of run)",
        "Why": "This is the biggest aggregate token pool to shorten or split first.",
    }
    assert report["opportunities"][1]["Driver"] == "Uncached input"
    assert report["next_action_detail"] == {
        "action": "apply_next_run_habit",
        "target_type": "playbook_habit",
        "target": "Set a stop condition for the dominant thread",
        "impact": "Targets the largest total-token driver.",
        "source": "Largest thread drives the run: Worker (Parser) used 33.2k tokens (57.7% of thread totals).",
    }
    assert [step["phase"] for step in report["next_run_checklist"]] == [
        "Before next run",
        "During next run",
        "After next run",
    ]
    assert (
        report["next_run_checklist"][0]["action"]
        == "Set a stop condition for the dominant thread"
    )
    assert (
        "largest_thread_share_pct" in report["next_run_checklist"][1]["success_check"]
    )
    assert "Export next-run-report.json" in report["next_run_checklist"][2]["action"]
    assert report["next_commands"] == [
        f"codex-observe sessions --db {db} --json",
        f"codex-observe report --db {db} --session-id demo-session-cost-review --format json --out run-report.json",
    ]
    assert report["next_command_templates"] == [
        f"codex-observe report --db {db} --session-id <next-session-id> --format json --out next-run-report.json",
        "codex-observe compare --before-report run-report.json --after-report next-run-report.json --out run-comparison.md",
    ]
    assert [step["label"] for step in report["review_path"]] == [
        "Save this report JSON",
        "Apply the recommended habit",
        "Export the next run",
        "Compare the workflow change",
    ]
    assert report["review_path"][0]["command"] == (
        f"codex-observe report --db {db} --session-id demo-session-cost-review --format json --out run-report.json"
    )
    assert report["review_path"][-1]["command"] == (
        "codex-observe compare --before-report run-report.json --after-report next-run-report.json --out run-comparison.md"
    )
    assert "command omitted by privacy boundary" in serialized
    assert "no command captured" not in serialized
    for private in PRIVATE_DEMO_STRINGS:
        assert private not in serialized


def test_report_markdown_and_json_are_shareable_without_private_content(
    tmp_path: Path,
) -> None:
    db = demo_db(tmp_path)
    report = build_report(str(db))

    markdown = report_markdown(report)
    payload = json.loads(report_json(report))

    assert "# Codex Observe Run Report" in markdown
    assert "Privacy: aggregate-only export" in markdown
    assert "## Quick Read" in markdown
    assert (
        "Recommended next habit: Set a stop condition for the dominant thread"
        in markdown
    )
    assert "## Recommended Action" in markdown
    assert "Action: apply next run habit" in markdown
    assert (
        "Target: playbook habit: Set a stop condition for the dominant thread"
        in markdown
    )
    assert "Why: Targets the largest total-token driver." in markdown
    assert (
        "Verify: Export the next run as report JSON and compare largest_thread_share_pct before adopting the workflow change."
        in markdown
    )
    assert "## Triage" in markdown
    assert "Risk level: high" in markdown
    assert "Primary driver: Largest thread drives the run" in markdown
    assert "Why: Largest thread used 57.7% of total tokens." in markdown
    assert "## Next Run Success Target" in markdown
    assert "## Next Run Checklist" in markdown
    assert "Before next run" in markdown
    assert "During next run" in markdown
    assert "After next run" in markdown
    assert "Set a stop condition for the dominant thread" in markdown
    assert "Metric: largest_thread_share_pct" in markdown
    assert "Target: below 50.0%" in markdown
    assert "## Next Run Playbook" in markdown
    assert "Impact: Targets the largest total-token driver." in markdown
    assert "## Review Path" in markdown
    assert "Save this report JSON" in markdown
    assert (
        "Success check: JSON includes schema_version, success_target, next_action_detail, and review_path."
        in markdown
    )
    assert "## Follow-up Commands" in markdown
    assert f"codex-observe sessions --db {db} --json" in markdown
    assert (
        "codex-observe compare --before-report run-report.json --after-report next-run-report.json --out run-comparison.md"
        in markdown
    )
    assert "## Cost Profile" in markdown
    assert "## Opportunity Stack" in markdown
    assert "1. **Set a stop condition for the dominant thread**" in markdown
    assert "Scale: 33.2k tokens (57.7% of run)" in markdown
    assert payload["opportunities"][0]["Driver"] == "Largest thread"
    assert "Largest thread share: 57.7% of total tokens" in markdown
    assert "Repeated prompt tokens" in markdown
    assert "Largest tool output" in markdown
    assert payload["schema_version"] == REPORT_SCHEMA_VERSION
    assert payload["summary"]["cache_pct"] == 58.5
    assert payload["triage"]["risk_level"] == "high"
    assert payload["next_action_detail"]["action"] == "apply_next_run_habit"
    assert payload["next_action_detail"]["target"] == (
        "Set a stop condition for the dominant thread"
    )
    assert payload["next_run_checklist"][0]["phase"] == "Before next run"
    assert payload["next_run_checklist"][2]["phase"] == "After next run"
    assert payload["review_path"][2]["label"] == "Export the next run"
    assert payload["review_path"][3]["success_check"] == (
        "Export the next run as report JSON and compare largest_thread_share_pct before adopting the workflow change."
    )
    assert payload["next_commands"][0] == f"codex-observe sessions --db {db} --json"
    assert "<next-session-id>" in payload["next_command_templates"][0]
    for private in PRIVATE_DEMO_STRINGS:
        assert private not in markdown
        assert private not in json.dumps(payload)


def test_report_follow_up_commands_are_structured_for_current_and_next_run() -> None:
    commands = report_follow_up_commands("demo.sqlite", "session-1")

    assert commands == {
        "next_commands": [
            "codex-observe sessions --db demo.sqlite --json",
            "codex-observe report --db demo.sqlite --session-id session-1 --format json --out run-report.json",
        ],
        "next_command_templates": [
            "codex-observe report --db demo.sqlite --session-id <next-session-id> --format json --out next-run-report.json",
            "codex-observe compare --before-report run-report.json --after-report next-run-report.json --out run-comparison.md",
        ],
    }


def test_report_review_path_guides_next_run_validation() -> None:
    review_path = report_review_path(
        "demo.sqlite",
        "session-1",
        {
            "metric": "largest_thread_share_pct",
            "target": "below 50.0%",
            "verification": "Export the next run as report JSON and compare largest_thread_share_pct before adopting the workflow change.",
        },
    )

    assert [step["label"] for step in review_path] == [
        "Save this report JSON",
        "Apply the recommended habit",
        "Export the next run",
        "Compare the workflow change",
    ]
    assert review_path[0]["command"] == (
        "codex-observe report --db demo.sqlite --session-id session-1 --format json --out run-report.json"
    )
    assert "largest_thread_share_pct" in review_path[1]["success_check"]
    assert review_path[-1]["success_check"].startswith("Export the next run")


def test_load_report_json_requires_current_report_schema(tmp_path: Path) -> None:
    db = demo_db(tmp_path)
    report = build_report(str(db))
    report_path = tmp_path / "report.json"
    report_path.write_text(report_json(report), encoding="utf-8")

    assert load_report_json(str(report_path))["schema_version"] == REPORT_SCHEMA_VERSION

    stale_report = json.loads(report_json(report))
    stale_report.pop("schema_version")
    stale_path = tmp_path / "stale-report.json"
    stale_path.write_text(json.dumps(stale_report), encoding="utf-8")

    with pytest.raises(
        ValueError, match="unsupported Codex Observe report JSON schema"
    ):
        load_report_json(str(stale_path))

    wrong_schema = json.loads(report_json(report))
    wrong_schema["schema_version"] = "codex-observe.report.v0"
    wrong_schema_path = tmp_path / "wrong-schema-report.json"
    wrong_schema_path.write_text(json.dumps(wrong_schema), encoding="utf-8")

    with pytest.raises(ValueError, match=REPORT_SCHEMA_VERSION):
        load_report_json(str(wrong_schema_path))


def test_available_sessions_returns_latest_first(tmp_path: Path) -> None:
    db = demo_db(tmp_path)

    assert available_sessions(str(db)) == [
        "demo-session-focused-followup",
        "demo-session-cost-review",
    ]
    assert default_report_session(str(db)) == "demo-session-cost-review"


def test_build_report_rejects_missing_or_unknown_session(tmp_path: Path) -> None:
    db = demo_db(tmp_path)

    with pytest.raises(FileNotFoundError):
        build_report(str(tmp_path / "missing.sqlite"))
    with pytest.raises(ValueError, match="session not found"):
        build_report(str(db), "does-not-exist")


def test_sort_session_summaries_prefers_highest_risk_then_latest() -> None:
    summaries = [
        {
            "session_id": "latest-moderate",
            "triage_risk": "moderate",
            "last_seen": "2026-01-01T12:30:00Z",
        },
        {
            "session_id": "older-high",
            "triage_risk": "high",
            "last_seen": "2026-01-01T12:20:00Z",
        },
        {
            "session_id": "newer-high",
            "triage_risk": "high",
            "last_seen": "2026-01-01T12:25:00Z",
        },
        {
            "session_id": "low",
            "triage_risk": "low",
            "last_seen": "2026-01-01T12:35:00Z",
        },
    ]

    sorted_summaries = sort_session_summaries(summaries)

    assert [row["session_id"] for row in sorted_summaries] == [
        "newer-high",
        "older-high",
        "latest-moderate",
        "low",
    ]


def test_session_summaries_are_aggregate_only(tmp_path: Path) -> None:
    db = demo_db(tmp_path)

    summaries = session_summaries(str(db))
    lines = "\n".join(session_summary_lines(str(db)))
    serialized = json.dumps(summaries) + lines

    assert summaries == [
        {
            "session_id": "demo-session-cost-review",
            "first_seen": "2026-01-01T12:00:00Z",
            "last_seen": "2026-01-01T12:23:00Z",
            "threads": 3,
            "tool_calls": 2,
            "total_tokens": 57510,
            "uncached_input_tokens": 22700,
            "cached_input_tokens": 32000,
            "triage_risk": "high",
            "largest_thread_share_pct": 57.7,
            "repeated_prompt_share_pct": 17.4,
            "uncached_input_share_pct": 39.5,
            "largest_tool_output_chars": 3960,
        },
        {
            "session_id": "demo-session-focused-followup",
            "first_seen": "2026-01-01T12:24:00Z",
            "last_seen": "2026-01-01T12:35:00Z",
            "threads": 3,
            "tool_calls": 1,
            "total_tokens": 8400,
            "uncached_input_tokens": 1200,
            "cached_input_tokens": 6300,
            "triage_risk": "low",
            "largest_thread_share_pct": 34.5,
            "repeated_prompt_share_pct": 0.0,
            "uncached_input_share_pct": 14.3,
            "largest_tool_output_chars": 880,
        },
    ]
    assert "Risk distribution: high 1, medium 0, low 1, unknown 0" in lines
    assert (
        "Session ID | Last seen | Risk | Threads | Tools | Tool out | Tokens | Uncached"
        in lines
    )
    assert (
        "demo-session-cost-review | 2026-01-01T12:23:00Z | high | 3 | 2 | 4.0k | 57.5k | 22.7k"
        in lines
    )
    assert (
        "demo-session-focused-followup | 2026-01-01T12:35:00Z | low | 3 | 1 | 880 | 8.4k | 1.2k"
        in lines
    )
    limited_lines = "\n".join(session_summary_lines(str(db), limit=1))
    assert "demo-session-cost-review | 2026-01-01T12:23:00Z" in limited_lines
    assert "demo-session-focused-followup | 2026-01-01T12:35:00Z" not in limited_lines
    assert "Risk distribution: high 1, medium 0, low 1, unknown 0" in limited_lines
    assert "Showing 1 of 2 sessions." in limited_lines
    assert "Export report for session: demo-session-cost-review" in limited_lines
    assert "Recommended action:" in lines
    assert "Export report for session: demo-session-cost-review" in lines
    assert "Why: highest aggregate triage risk; latest run breaks ties" in lines
    assert "Risk: high" in lines
    assert (
        "Top drivers: largest thread share: 57.7%; repeated prompt share: 17.4%; uncached input share: 39.5%; largest tool output: 4.0k chars"
        in lines
    )
    assert "Review path:" in lines
    assert "Save report JSON: codex-observe report --db" in lines
    assert (
        "--session-id demo-session-cost-review --format json --out run-report.json"
        in lines
    )
    assert (
        "Compare workflow change: codex-observe compare --before-report run-report.json --after-report next-run-report.json --out run-comparison.md"
        in lines
    )
    assert "Next commands:" in lines
    assert (
        "- codex-observe report --db" in lines
        and "--session-id demo-session-cost-review --out run-report.md" in lines
    )
    assert (
        "--session-id demo-session-cost-review --format json --out run-report.json"
        in lines
    )
    assert lines.index("Review path:") < lines.index("Next commands:")
    assert lines.index("Next commands:") < lines.index("Next:")
    assert "File safe feedback: docs/PUBLIC_TOUR_FEEDBACK.md" in lines
    assert (
        "Next: review the highest-risk run (demo-session-cost-review, high risk); run `codex-observe report --db"
        in lines
    )
    assert "--session-id demo-session-cost-review --out run-report.md" in lines
    for private in PRIVATE_DEMO_STRINGS:
        assert private not in serialized


def test_compare_reports_marks_improved_metrics_and_privacy_safe_output(
    tmp_path: Path,
) -> None:
    db = demo_db(tmp_path)
    before = build_report(str(db))
    after = json.loads(json.dumps(before))
    after["session"]["session_id"] = "after-run"
    after["summary"]["total_tokens"] -= 10_000
    after["summary"]["uncached_input_tokens"] -= 5_000
    after["summary"]["largest_thread_tokens"] -= 8_000
    after["summary"]["repeated_prompt_tokens"] -= 2_000
    after["summary"]["largest_tool_output_chars"] -= 10_000
    after["summary"]["tool_calls"] -= 1
    after["summary"]["compactions"] = 0
    after["diagnostics"] = after["diagnostics"][:1]

    comparison = compare_reports(before, after)
    markdown = comparison_markdown(comparison)
    payload = json.loads(comparison_json(comparison))
    serialized = markdown + json.dumps(payload)

    assert comparison["schema_version"] == COMPARISON_SCHEMA_VERSION
    assert comparison["verdict"] == "improved"
    assert comparison["headline"] == {
        "headline": "Verdict: improved; largest change: Total tokens -10.0k (improved).",
        "diagnostic_change": "5 resolved diagnostics; 0 new diagnostics.",
    }
    assert (
        comparison["recommendation"]
        == "Keep the change, then target persisted diagnostic: Largest thread drives the run."
    )
    assert comparison["triage_risk"] == {
        "before": "high",
        "after": "high",
        "direction": "unchanged",
    }
    assert comparison["opportunity_change"] == {
        "before": {
            "driver": "Largest thread",
            "habit": "Set a stop condition for the dominant thread",
            "scale": "33.2k tokens (57.7% of run)",
        },
        "after": {
            "driver": "Largest thread",
            "habit": "Set a stop condition for the dominant thread",
            "scale": "25.2k tokens (53.0% of run)",
        },
        "direction": "improved",
        "summary": "Top opportunity stayed Largest thread and improved: 33.2k tokens (57.7% of run) -> 25.2k tokens (53.0% of run).",
    }
    assert comparison["metrics"][0] == {
        "metric": "total_tokens",
        "label": "Total tokens",
        "before": 57510,
        "after": 47510,
        "delta": -10000,
        "delta_pct": -17.4,
        "direction": "improved",
    }
    labels = {metric["label"] for metric in comparison["metrics"]}
    assert "Repeated prompt tokens" in labels
    assert "Largest tool output chars" in labels
    assert "# Codex Observe Run Comparison" in markdown
    assert "Privacy: aggregate-only comparison" in markdown
    assert "## Quick Read" in markdown
    assert "## Opportunity Change" in markdown
    assert "Top opportunity stayed Largest thread and improved" in markdown
    assert "## Recommended Action" in markdown
    assert "Action: target persisted diagnostic" in markdown
    assert "Target: diagnostic: Largest thread drives the run" in markdown
    assert "Why: The workflow improved, but this diagnostic still appears." in markdown
    assert "## Review Path" in markdown
    assert "Read the verdict" in markdown
    assert "Compare against this after run" in markdown
    assert "File safe feedback" in markdown
    assert "## Follow-up Commands" in markdown
    assert (
        "codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json"
        in markdown
    )
    assert (
        "codex-observe compare --before-report <after-report.json> --after-report next-run-report.json --out next-run-comparison.md"
        in markdown
    )
    assert (
        "codex-observe compare --before-session after-run --after-session <next-session-id> --db <db> --out next-run-comparison.md"
        in markdown
    )
    assert "| Metric | Before | After | Delta | % change | Direction |" in markdown
    assert "| Total tokens | 57.5k | 47.5k | -10.0k | -17.4% | improved |" in markdown
    assert (
        "Verdict: improved; largest change: Total tokens -10.0k (improved)." in markdown
    )
    assert (
        "Recommended next step: Keep the change, then target persisted diagnostic: Largest thread drives the run."
        in markdown
    )
    assert (
        payload["recommendation"]
        == "Keep the change, then target persisted diagnostic: Largest thread drives the run."
    )
    assert payload["recommendation_detail"] == {
        "action": "target_persisted_diagnostic",
        "target_type": "diagnostic",
        "target": "Largest thread drives the run",
        "reason": "The workflow improved, but this diagnostic still appears.",
    }
    assert payload["schema_version"] == COMPARISON_SCHEMA_VERSION
    assert payload["next_command_templates"] == [
        "codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json",
        "codex-observe compare --before-report <after-report.json> --after-report next-run-report.json --out next-run-comparison.md",
        "codex-observe compare --before-session after-run --after-session <next-session-id> --db <db> --out next-run-comparison.md",
    ]
    assert [step["label"] for step in payload["review_path"]] == [
        "Read the verdict",
        "Act on the recommendation",
        "Export the next run",
        "Compare against this after run",
        "File safe feedback",
    ]
    assert payload["review_path"][3]["command"] == (
        "codex-observe compare --before-report <after-report.json> --after-report next-run-report.json --out next-run-comparison.md"
    )
    assert payload["review_path"][-1]["command"] == "docs/PUBLIC_TOUR_FEEDBACK.md"
    assert payload["triage_risk"]["direction"] == "unchanged"
    assert payload["opportunity_change"]["direction"] == "improved"
    assert payload["opportunity_change"]["before"]["driver"] == "Largest thread"
    assert payload["diagnostics"]["resolved"]
    for private in PRIVATE_DEMO_STRINGS:
        assert private not in serialized


def test_comparison_review_path_guides_follow_up_validation() -> None:
    comparison = {
        "verdict": "mixed",
        "after": {"session_id": "after-run"},
        "recommendation": "Investigate repeated prompt tokens.",
    }

    review_path = comparison_review_path(comparison)

    assert [step["label"] for step in review_path] == [
        "Read the verdict",
        "Act on the recommendation",
        "Export the next run",
        "Compare against this after run",
        "File safe feedback",
    ]
    assert "mixed" in review_path[0]["success_check"]
    assert review_path[1]["command"] == "Investigate repeated prompt tokens."
    assert review_path[2]["command"] == (
        "codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json"
    )
    assert review_path[3]["command"] == (
        "codex-observe compare --before-report <after-report.json> --after-report next-run-report.json --out next-run-comparison.md"
    )


def test_compare_reports_recommendation_uses_after_report_diagnostic_priority() -> None:
    before = {
        "session": {"session_id": "before"},
        "summary": {
            "total_tokens": 1000,
            "uncached_input_tokens": 900,
            "largest_thread_tokens": 800,
            "repeated_prompt_tokens": 700,
            "largest_tool_output_chars": 5000,
            "tool_calls": 20,
            "compactions": 2,
        },
        "diagnostics": [
            {"Diagnostic": "Largest thread drives the run"},
            {"Diagnostic": "Guardian overhead"},
            {"Diagnostic": "Repeated prompt blocks"},
        ],
    }
    after = {
        "session": {"session_id": "after"},
        "summary": {
            "total_tokens": 900,
            "uncached_input_tokens": 800,
            "largest_thread_tokens": 700,
            "repeated_prompt_tokens": 0,
            "largest_tool_output_chars": 1000,
            "tool_calls": 18,
            "compactions": 1,
        },
        "diagnostics": [
            {"Diagnostic": "Largest thread drives the run"},
            {"Diagnostic": "Guardian overhead"},
        ],
    }

    comparison = compare_reports(before, after)

    assert comparison["verdict"] == "improved"
    assert comparison["diagnostics"]["persisted"] == [
        "Largest thread drives the run",
        "Guardian overhead",
    ]
    assert comparison["diagnostics"]["resolved"] == ["Repeated prompt blocks"]
    assert (
        comparison["recommendation"]
        == "Keep the change, then target persisted diagnostic: Largest thread drives the run."
    )


def test_compare_reports_marks_top_opportunity_shift() -> None:
    before = {
        "session": {"session_id": "before"},
        "summary": {
            "total_tokens": 1000,
            "uncached_input_tokens": 100,
            "largest_thread_tokens": 800,
            "repeated_prompt_tokens": 0,
            "largest_tool_output_chars": 0,
            "tool_calls": 1,
            "compactions": 0,
        },
        "diagnostics": [],
    }
    after = {
        "session": {"session_id": "after"},
        "summary": {
            "total_tokens": 1000,
            "uncached_input_tokens": 800,
            "largest_thread_tokens": 100,
            "repeated_prompt_tokens": 0,
            "largest_tool_output_chars": 0,
            "tool_calls": 1,
            "compactions": 0,
        },
        "diagnostics": [],
    }

    comparison = compare_reports(before, after)

    assert comparison["opportunity_change"] == {
        "before": {
            "driver": "Largest thread",
            "habit": "Set a stop condition for the dominant thread",
            "scale": "800 tokens (80.0% of run)",
        },
        "after": {
            "driver": "Uncached input",
            "habit": "Gate large context before it enters the chat",
            "scale": "800 tokens (80.0% of run)",
        },
        "direction": "shifted",
        "summary": "Top opportunity shifted from Largest thread to Uncached input.",
    }
    assert (
        "Top opportunity shifted from Largest thread to Uncached input."
        in comparison_markdown(comparison)
    )


def test_compare_reports_marks_triage_risk_changes() -> None:
    before = {"triage": {"risk_level": "high"}, "summary": {}, "diagnostics": []}
    after = {"triage": {"risk_level": "low"}, "summary": {}, "diagnostics": []}

    comparison = compare_reports(before, after)

    assert comparison["triage_risk"] == {
        "before": "high",
        "after": "low",
        "direction": "improved",
    }
    markdown = comparison_markdown(comparison)
    assert "## Triage Risk" in markdown
    assert "Direction: improved" in markdown
    assert "## Opportunity Change" in markdown


def test_compare_reports_marks_regressed_metrics() -> None:
    before = {
        "session": {"session_id": "before"},
        "summary": {
            "total_tokens": 10,
            "uncached_input_tokens": 5,
            "largest_thread_tokens": 8,
            "repeated_prompt_tokens": 3,
            "largest_tool_output_chars": 4,
            "tool_calls": 1,
            "compactions": 0,
        },
        "diagnostics": [],
    }
    after = {
        "session": {"session_id": "after"},
        "summary": {
            "total_tokens": 20,
            "uncached_input_tokens": 15,
            "largest_thread_tokens": 18,
            "repeated_prompt_tokens": 6,
            "largest_tool_output_chars": 204,
            "tool_calls": 2,
            "compactions": 1,
        },
        "diagnostics": [],
    }

    comparison = compare_reports(before, after)

    assert comparison["verdict"] == "regressed"
    assert {metric["direction"] for metric in comparison["metrics"]} == {"regressed"}
    assert comparison["metrics"][0]["delta_pct"] == 100.0
    assert (
        comparison["recommendation"]
        == "Inspect the largest regressed metric first: Largest tool output chars."
    )
    assert comparison["recommendation_detail"] == {
        "action": "inspect_regressed_metric",
        "target_type": "metric",
        "target": "Largest tool output chars",
        "reason": "This metric had the largest aggregate regression.",
    }


def test_compare_reports_recommendation_uses_largest_delta_for_mixed_runs() -> None:
    before = {
        "session": {"session_id": "before"},
        "summary": {
            "total_tokens": 1000,
            "uncached_input_tokens": 500,
            "largest_thread_tokens": 800,
            "repeated_prompt_tokens": 300,
            "largest_tool_output_chars": 400,
            "tool_calls": 10,
            "compactions": 1,
        },
        "diagnostics": [],
    }
    after = {
        "session": {"session_id": "after"},
        "summary": {
            "total_tokens": 900,
            "uncached_input_tokens": 520,
            "largest_thread_tokens": 700,
            "repeated_prompt_tokens": 1200,
            "largest_tool_output_chars": 200,
            "tool_calls": 8,
            "compactions": 0,
        },
        "diagnostics": [],
    }

    comparison = compare_reports(before, after)

    assert comparison["verdict"] == "mixed"
    assert (
        comparison["recommendation"]
        == "Keep the improved habits, but investigate Repeated prompt tokens before adopting the change."
    )


def test_compare_reports_recommendation_uses_largest_improvement_without_persisted_diagnostics() -> (
    None
):
    before = {
        "session": {"session_id": "before"},
        "summary": {
            "total_tokens": 1000,
            "uncached_input_tokens": 900,
            "largest_thread_tokens": 800,
            "repeated_prompt_tokens": 700,
            "largest_tool_output_chars": 5000,
            "tool_calls": 20,
            "compactions": 2,
        },
        "diagnostics": [{"Diagnostic": "Resolved diagnostic"}],
    }
    after = {
        "session": {"session_id": "after"},
        "summary": {
            "total_tokens": 900,
            "uncached_input_tokens": 850,
            "largest_thread_tokens": 750,
            "repeated_prompt_tokens": 650,
            "largest_tool_output_chars": 1000,
            "tool_calls": 18,
            "compactions": 1,
        },
        "diagnostics": [],
    }

    comparison = compare_reports(before, after)

    assert comparison["schema_version"] == COMPARISON_SCHEMA_VERSION
    assert comparison["verdict"] == "improved"
    assert (
        comparison["recommendation"]
        == "Keep the change; strongest improvement is Largest tool output chars."
    )
