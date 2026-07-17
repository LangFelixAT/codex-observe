from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from codex_observe.demo import create_demo_database
from codex_observe.report import (
    COMPARISON_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    available_sessions,
    build_report,
    command_arg,
    compare_reports,
    comparison_json,
    comparison_markdown,
    comparison_review_path,
    default_report_session,
    load_report_json,
    report_follow_up_commands,
    report_headline,
    report_json,
    report_markdown,
    report_review_path,
    report_triage,
    report_success_target,
    session_portfolio_drivers,
    session_portfolio_summary,
    session_summaries,
    session_success_target_preview,
    session_summary_lines,
    session_validation_commands,
    sort_session_summaries,
)
from codex_observe.schema import SCHEMA_SQL


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
    assert report["summary"]["usage_snapshots"] == 6
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
    assert (
        "Guardian input used 24.3% of total tokens." not in report["triage"]["reasons"]
    )
    assert report["headline"] == {
        "headline": "57.5k total tokens across 6 usage snapshots; largest thread 33.2k (57.7%); repeated prompts 10.0k (17.4%); guardian input 14.0k (24.3%); largest tool output 4.0k chars.",
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
    assert report["next_run_brief"] == {
        "title": "Next Codex run plan",
        "habit": "Set a stop condition for the dominant thread",
        "watch": "Largest thread drives the run",
        "also_watch": [
            "Uncached input - 22.7k tokens (39.5% of run)",
            "Guardian overhead - 14.0k input tokens (24.3% of run)",
            "Repeated prompt blocks - 10.0k tokens (17.4% of run)",
        ],
        "target_metric": "largest_thread_share_pct",
        "current": "57.7%",
        "target": "below 50.0%",
        "guardrail": "Pause or split the run when one thread starts to dominate the work.",
        "verification": "Export the next run as report JSON and compare largest_thread_share_pct before adopting the workflow change.",
        "copy_prompt": "Next Codex run plan:\n- Try: Set a stop condition for the dominant thread\n- Watch: Largest thread drives the run\n- Also watch: Uncached input - 22.7k tokens (39.5% of run); Guardian overhead - 14.0k input tokens (24.3% of run); Repeated prompt blocks - 10.0k tokens (17.4% of run)\n- Target: move largest_thread_share_pct from 57.7% toward below 50.0%\n- Guardrail: Pause or split the run when one thread starts to dominate the work.\n- Afterward: Export the next run as report JSON and compare largest_thread_share_pct before adopting the workflow change.",
    }
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


def test_report_headline_omits_guardian_when_absent() -> None:
    report = {
        "summary": {
            "total_tokens": 1000,
            "usage_snapshots": 2,
            "largest_thread_tokens": 700,
            "largest_thread_share_pct": 70.0,
            "repeated_prompt_tokens": 0,
            "repeated_prompt_share_pct": 0.0,
            "largest_tool_output_chars": 120,
        },
        "diagnostics": [],
        "playbook": [],
    }

    assert report_headline(report)["headline"] == (
        "1.0k total tokens across 2 usage snapshots; largest thread 700 (70.0%); "
        "repeated prompts 0 (0.0%); largest tool output 120 chars."
    )


def test_build_report_prioritizes_multi_day_session_checkpointing(
    tmp_path: Path,
) -> None:
    db = demo_db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            UPDATE conversations
            SET first_seen='2026-01-01T00:00:00Z',
                last_seen='2026-01-04T12:00:00Z'
            WHERE session_id='demo-session-cost-review'
            """
        )

    report = build_report(str(db))

    assert report["summary"]["session_duration_hours"] == 84.0
    assert report["summary"]["session_duration_days"] == 3.5
    assert report["diagnostics"][0] == {
        "Priority": "High",
        "Diagnostic": "Run spans multiple days",
        "Action": "Create a short handoff and start a fresh Codex session at the next durable checkpoint.",
        "Evidence": "Session covered 3.5 days across 6 usage snapshots.",
    }
    assert report["playbook"][0]["Habit"] == (
        "Start a fresh Codex session at each durable checkpoint"
    )
    assert report["playbook"][0]["Impact"] == (
        "Targets long-running session accumulation."
    )
    assert report["opportunities"][0] == {
        "Rank": 1,
        "Habit": "Start a fresh Codex session at each durable checkpoint",
        "Driver": "Session duration",
        "Scale": "3.5 days",
        "Why": "Long-running sessions accumulate stale context; checkpointing and restarting makes the next run easier to control.",
    }
    assert report["triage"]["primary_driver"] == "Run spans multiple days"
    assert report["triage"]["next_action"] == (
        "Start a fresh Codex session at each durable checkpoint"
    )
    assert report["success_target"] == {
        "metric": "session_duration_hours",
        "direction": "lower_is_better",
        "current_value": 84.0,
        "target_value": 24.0,
        "unit": "hours",
        "current": "3.5 days",
        "target": "below 24.0 hours",
        "rationale": "The top opportunity is a long-running session; the next run should restart at durable checkpoints before stale context accumulates.",
        "verification": "Export the next run as report JSON and compare session_duration_hours before adopting the workflow change.",
    }
    assert report["next_run_brief"]["target_metric"] == "session_duration_hours"
    assert report["next_run_brief"]["guardrail"] == (
        "Write a short handoff and start a fresh session before the run crosses one day."
    )
    assert report["next_run_brief"]["also_watch"][0].startswith("Largest thread -")
    assert "Start a fresh Codex session" in report["next_run_brief"]["copy_prompt"]
    assert "before the run crosses one day" in report["next_run_brief"]["copy_prompt"]
    assert report["next_run_checklist"][1]["action"] == (
        "Write a short handoff and start a fresh session before the run crosses one day."
    )
    assert "session_duration_hours" in report["next_run_checklist"][1]["success_check"]


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
    assert "57.5k total tokens across 6 usage snapshots" in markdown
    assert "- Usage snapshots: 6" in markdown
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
    assert "## Next Run Brief" in markdown
    assert "Next Codex run plan:" in markdown
    assert "- Try: Set a stop condition for the dominant thread" in markdown
    assert "- Also watch: Uncached input - 22.7k tokens" in markdown
    assert (
        "- Target: move largest_thread_share_pct from 57.7% toward below 50.0%"
        in markdown
    )
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
    assert (
        payload["next_run_brief"]["habit"]
        == "Set a stop condition for the dominant thread"
    )
    assert payload["next_run_brief"]["target_metric"] == "largest_thread_share_pct"
    assert payload["next_run_brief"]["also_watch"][1].startswith("Guardian overhead -")
    assert "Next Codex run plan" in payload["next_run_brief"]["copy_prompt"]
    assert payload["review_path"][2]["label"] == "Export the next run"
    assert payload["review_path"][3]["success_check"] == (
        "Export the next run as report JSON and compare largest_thread_share_pct before adopting the workflow change."
    )
    assert payload["next_commands"][0] == f"codex-observe sessions --db {db} --json"
    assert "<next-session-id>" in payload["next_command_templates"][0]
    for private in PRIVATE_DEMO_STRINGS:
        assert private not in markdown
        assert private not in json.dumps(payload)


def test_report_command_handoffs_quote_shell_sensitive_database_paths(
    tmp_path: Path,
) -> None:
    db = tmp_path / "Observe DB & Reports" / "codex observe.sqlite"
    db_arg = command_arg(db)

    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA_SQL)

    empty_lines = session_summary_lines(str(db))
    validation_commands = session_validation_commands(str(db), "session-1")
    commands = report_follow_up_commands(str(db), "session-1")
    review_path = report_review_path(
        str(db),
        "session-1",
        {
            "metric": "largest_thread_share_pct",
            "target": "below 50.0%",
            "verification": "Export the next run as report JSON and compare largest_thread_share_pct before adopting the workflow change.",
        },
    )

    assert f"- codex-observe ingest ~/.codex/sessions --db {db_arg}" in empty_lines
    assert f"- codex-observe demo --db {db_arg}" in empty_lines
    assert validation_commands[:3] == [
        f"codex-observe report --db {db_arg} --session-id session-1 --out run-report.md",
        f"codex-observe report --db {db_arg} --session-id session-1 --format json --out run-report.json",
        f"codex-observe report --db {db_arg} --session-id <next-session-id> --format json --out next-run-report.json",
    ]
    assert commands["next_commands"] == [
        f"codex-observe sessions --db {db_arg} --json",
        f"codex-observe report --db {db_arg} --session-id session-1 --format json --out run-report.json",
    ]
    assert commands["next_command_templates"][0] == (
        f"codex-observe report --db {db_arg} --session-id <next-session-id> --format json --out next-run-report.json"
    )
    assert review_path[0]["command"] == commands["next_commands"][1]
    assert review_path[2]["command"] == commands["next_command_templates"][0]


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


def test_session_success_target_preview_skips_satisfied_uncached_target() -> None:
    preview = session_success_target_preview(
        {
            "total_tokens": 1_715_184_509,
            "uncached_input_tokens": 40_328_859,
            "largest_thread_share_pct": 56.7,
            "repeated_prompt_share_pct": 0.9,
            "uncached_input_share_pct": 2.4,
            "largest_tool_output_chars": 40_097,
        }
    )

    assert preview == {
        "action": "Set a stop condition for the dominant thread",
        "current": "56.7%",
        "current_value": 56.7,
        "direction": "lower_is_better",
        "driver": "Largest thread",
        "metric": "largest_thread_share_pct",
        "target": "below 50.0%",
        "target_value": 50.0,
        "unit": "percent_of_run",
    }
    assert preview["target_value"] < preview["current_value"]


def test_report_triage_flags_high_guardian_input_share() -> None:
    triage = report_triage(
        {
            "summary": {
                "largest_thread_share_pct": 20.0,
                "repeated_prompt_share_pct": 0.0,
                "uncached_input_share_pct": 5.0,
                "guardian_input_share_pct": 44.5,
                "guardian_input_tokens": 45_000,
                "largest_tool_output_chars": 100,
                "total_tokens": 10_000,
                "compactions": 0,
            },
            "headline": {
                "top_diagnostic": "Guardian overhead",
                "recommendation": "Limit approval context before guardian checks",
            },
        }
    )

    assert triage == {
        "risk_level": "high",
        "primary_driver": "Guardian overhead",
        "next_action": "Limit approval context before guardian checks",
        "reasons": ["Guardian input used 44.5% of total tokens."],
    }


def test_report_triage_ignores_small_guardian_input_share() -> None:
    triage = report_triage(
        {
            "summary": {
                "largest_thread_share_pct": 20.0,
                "repeated_prompt_share_pct": 0.0,
                "uncached_input_share_pct": 5.0,
                "guardian_input_share_pct": 44.5,
                "guardian_input_tokens": 4_450,
                "largest_tool_output_chars": 100,
                "total_tokens": 10_000,
                "compactions": 0,
            },
            "headline": {
                "top_diagnostic": "Guardian overhead",
                "recommendation": "Limit approval context before guardian checks",
            },
        }
    )

    assert triage == {
        "risk_level": "low",
        "primary_driver": "Guardian overhead",
        "next_action": "Limit approval context before guardian checks",
        "reasons": ["No high-risk cost driver crossed review thresholds."],
    }


def test_guardian_overhead_can_drive_success_targets() -> None:
    preview = session_success_target_preview(
        {
            "total_tokens": 100_000,
            "guardian_input_tokens": 45_000,
            "guardian_input_share_pct": 45.0,
            "largest_thread_share_pct": 20.0,
            "repeated_prompt_share_pct": 0.0,
            "uncached_input_share_pct": 5.0,
            "largest_tool_output_chars": 100,
        }
    )

    assert preview == {
        "action": "Limit approval context before guardian checks",
        "current": "45.0%",
        "current_value": 45.0,
        "direction": "lower_is_better",
        "driver": "Guardian overhead",
        "metric": "guardian_input_share_pct",
        "target": "below 40.0%",
        "target_value": 40.0,
        "unit": "percent_of_run",
    }

    target = report_success_target(
        {
            "summary": {"guardian_input_share_pct": 45.0},
            "opportunities": [{"Driver": "Guardian overhead"}],
        }
    )

    assert target == {
        "metric": "guardian_input_share_pct",
        "direction": "lower_is_better",
        "current_value": 45.0,
        "target_value": 40.0,
        "unit": "percent_of_run",
        "current": "45.0%",
        "target": "below 40.0%",
        "rationale": "The top opportunity is approval context replay; the next run should keep guardian checks narrow and checkpoint before approvals repeat.",
        "verification": "Export the next run as report JSON and compare guardian_input_share_pct before adopting the workflow change.",
    }


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
            "usage_snapshots": 6,
            "session_duration_hours": 0.4,
            "session_duration_days": 0.0,
            "total_tokens": 57510,
            "uncached_input_tokens": 22700,
            "cached_input_tokens": 32000,
            "guardian_input_tokens": 14000,
            "triage_risk": "high",
            "largest_thread_share_pct": 57.7,
            "repeated_prompt_share_pct": 17.4,
            "uncached_input_share_pct": 39.5,
            "guardian_input_share_pct": 24.3,
            "largest_tool_output_chars": 3960,
        },
        {
            "session_id": "demo-session-focused-followup",
            "first_seen": "2026-01-01T12:24:00Z",
            "last_seen": "2026-01-01T12:35:00Z",
            "threads": 3,
            "tool_calls": 1,
            "usage_snapshots": 3,
            "session_duration_hours": 0.2,
            "session_duration_days": 0.0,
            "total_tokens": 8400,
            "uncached_input_tokens": 1200,
            "cached_input_tokens": 6300,
            "guardian_input_tokens": 2500,
            "triage_risk": "low",
            "largest_thread_share_pct": 34.5,
            "repeated_prompt_share_pct": 0.0,
            "uncached_input_share_pct": 14.3,
            "guardian_input_share_pct": 29.8,
            "largest_tool_output_chars": 880,
        },
    ]
    assert "Risk distribution: high 1, medium 0, low 1, unknown 0" in lines
    assert (
        "Session ID | Last seen | Risk | Duration | Threads | Tools | Snapshots | Tool out | Tokens | Uncached"
        in lines
    )
    assert (
        "demo-session-cost-review | 2026-01-01T12:23:00Z | high | 0.0d | 3 | 2 | 6 | 4.0k | 57.5k | 22.7k"
        in lines
    )
    assert (
        "demo-session-focused-followup | 2026-01-01T12:35:00Z | low | 0.0d | 3 | 1 | 3 | 880 | 8.4k | 1.2k"
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
        "Top drivers: largest thread share: 57.7%; repeated prompt share: 17.4%; uncached input share: 39.5%; guardian input share: 24.3%; largest tool output: 4.0k chars"
        in lines
    )
    assert "Next-run target: largest_thread_share_pct 57.7% -> below 50.0%" in lines
    assert "Habit to try: Set a stop condition for the dominant thread" in lines
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


def test_session_listing_prioritizes_multi_day_target_preview(
    tmp_path: Path,
) -> None:
    db = demo_db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            UPDATE conversations
            SET first_seen='2026-01-01T00:00:00Z',
                last_seen='2026-01-04T12:00:00Z'
            WHERE session_id='demo-session-cost-review'
            """
        )

    summaries = session_summaries(str(db))
    recommended = summaries[0]
    lines = "\n".join(session_summary_lines(str(db)))
    target = session_success_target_preview(recommended)

    assert recommended["session_duration_hours"] == 84.0
    assert recommended["session_duration_days"] == 3.5
    assert "Session ID | Last seen | Risk | Duration | Threads" in lines
    assert "demo-session-cost-review | 2026-01-04T12:00:00Z | high | 3.5d" in lines
    assert (
        "Top drivers: session duration: 3.5 days; largest thread share: 57.7%" in lines
    )
    assert (
        "Next-run target: session_duration_hours 3.5 days -> below 24.0 hours" in lines
    )
    assert (
        "Habit to try: Start a fresh Codex session at each durable checkpoint" in lines
    )
    assert target == {
        "metric": "session_duration_hours",
        "direction": "lower_is_better",
        "current_value": 84.0,
        "target_value": 24.0,
        "unit": "hours",
        "current": "3.5 days",
        "target": "below 24.0 hours",
        "driver": "Session duration",
        "action": "Start a fresh Codex session at each durable checkpoint",
    }


def test_session_portfolio_summary_distinguishes_workflow_patterns() -> None:
    all_high = session_portfolio_summary(
        [
            {"triage_risk": "high"},
            {"triage_risk": "high"},
        ]
    )
    assert all_high == {
        "risk_posture": "all_high",
        "headline": "All 2 sessions are high risk.",
        "action": "Treat this as a workflow pattern: start with the recommended run, apply one habit, then compare the next run before continuing.",
        "filter_note": "Current view includes every imported session.",
        "total_sessions": 2,
        "matching_sessions": 2,
        "high_risk_sessions": 2,
        "medium_risk_sessions": 0,
        "low_risk_sessions": 0,
        "unknown_risk_sessions": 0,
        "high_risk_share_pct": 100.0,
        "top_driver": None,
        "drivers": [],
    }

    mixed = session_portfolio_summary(
        [{"triage_risk": "high"}, {"triage_risk": "low"}],
        [{"triage_risk": "low"}],
    )
    assert mixed["risk_posture"] == "mixed_high"
    assert mixed["headline"] == "1 of 2 sessions are high risk."
    assert mixed["matching_sessions"] == 1
    assert mixed["filter_note"] == "Current filter shows 1 of 2 sessions."


def test_session_portfolio_drivers_rank_cross_session_patterns() -> None:
    drivers = session_portfolio_drivers(
        [
            {
                "triage_risk": "high",
                "total_tokens": 100_000,
                "largest_thread_share_pct": 75.0,
                "session_duration_hours": 30.0,
                "largest_tool_output_chars": 20_000,
            },
            {
                "triage_risk": "high",
                "total_tokens": 50_000,
                "largest_thread_share_pct": 65.0,
                "uncached_input_share_pct": 40.0,
            },
        ]
    )

    assert drivers[0] == {
        "driver": "largest_thread_share_pct",
        "label": "Largest thread concentration",
        "sessions": 2,
        "share_pct": 100.0,
        "max_value": 75.0,
        "max_display": "75.0%",
        "threshold": 50.0,
        "threshold_display": "50.0%",
        "action": "Set stop conditions before one thread dominates repeated work.",
    }
    assert {driver["label"] for driver in drivers} >= {
        "Multi-day session duration",
        "High uncached input share",
        "Large tool output",
    }


def test_session_portfolio_drivers_ignore_single_thread_largest_share_noise() -> None:
    drivers = session_portfolio_drivers(
        [
            {
                "triage_risk": "high",
                "threads": 1,
                "total_tokens": 40_000,
                "largest_thread_share_pct": 100.0,
                "largest_tool_output_chars": 8_000,
            },
            {
                "triage_risk": "high",
                "threads": 2,
                "total_tokens": 30_000,
                "largest_thread_share_pct": 80.0,
            },
        ]
    )

    largest_thread = next(
        driver for driver in drivers if driver["driver"] == "largest_thread_share_pct"
    )

    assert largest_thread["sessions"] == 1
    assert largest_thread["share_pct"] == 50.0
    assert largest_thread["max_display"] == "80.0%"


def test_session_summaries_bound_replayed_prompt_share_to_total_tokens(
    tmp_path: Path,
) -> None:
    db = demo_db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            UPDATE conversations
            SET total_tokens=1000,
                total_input_tokens=1000,
                total_uncached_input_tokens=100,
                total_cached_input_tokens=900
            WHERE session_id='demo-session-cost-review'
            """
        )
        conn.execute(
            """
            UPDATE prompt_blocks
            SET approx_tokens=2500
            WHERE thread_id IN (
                SELECT thread_id FROM threads
                WHERE session_id='demo-session-cost-review'
            )
            """
        )

    summaries = session_summaries(str(db))
    recommended = next(
        row for row in summaries if row["session_id"] == "demo-session-cost-review"
    )
    report = build_report(str(db), "demo-session-cost-review")

    assert recommended["repeated_prompt_share_pct"] == 100.0
    assert (
        report["summary"]["repeated_prompt_tokens"] > report["summary"]["total_tokens"]
    )
    assert report["summary"]["repeated_prompt_share_pct"] == 100.0


def test_compare_reports_marks_improved_metrics_and_privacy_safe_output(
    tmp_path: Path,
) -> None:
    db = demo_db(tmp_path)
    before = build_report(str(db))
    after = json.loads(json.dumps(before))
    after["session"]["session_id"] = "after-run"
    after["summary"]["total_tokens"] -= 10_000
    after["summary"]["usage_snapshots"] += 2
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
    snapshot_metric = next(
        metric
        for metric in comparison["metrics"]
        if metric["label"] == "Usage snapshots"
    )
    assert snapshot_metric == {
        "metric": "usage_snapshots",
        "label": "Usage snapshots",
        "before": 6,
        "after": 8,
        "delta": 2,
        "delta_pct": 33.3,
        "direction": "changed",
    }
    labels = {metric["label"] for metric in comparison["metrics"]}
    assert "Usage snapshots" in labels
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
    assert "| Usage snapshots | 6 | 8 | 2 | +33.3% | changed |" in markdown
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
            "usage_snapshots": 4,
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
            "usage_snapshots": 4,
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
    cost_directions = {
        metric["direction"]
        for metric in comparison["metrics"]
        if metric["metric"] != "usage_snapshots"
    }
    assert cost_directions == {"regressed"}
    snapshot_metric = next(
        metric
        for metric in comparison["metrics"]
        if metric["metric"] == "usage_snapshots"
    )
    assert snapshot_metric["direction"] == "unchanged"
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
