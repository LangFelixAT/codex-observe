from __future__ import annotations

import json
import shlex
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .analysis import (
    compactions_df,
    diagnostics_df,
    findings_df,
    fmt_short,
    next_run_playbook_df,
    opportunity_df,
    numericize,
    prepare_threads,
)


REPORT_SCHEMA_VERSION = "codex-observe.report.v1"
COMPARISON_SCHEMA_VERSION = "codex-observe.comparison.v1"


def command_arg(path: Path | str) -> str:
    value = str(path)
    safe_punctuation = "._/\\:~+-"
    if value and all(char.isalnum() or char in safe_punctuation for char in value):
        return value
    if sys.platform == "win32":
        return f'"{value}"'
    return shlex.quote(value)


def aggregate_feedback_handoff() -> dict[str, object]:
    return {
        "runbook": "docs/PUBLIC_TOUR_FEEDBACK.md",
        "issue_template": ".github/ISSUE_TEMPLATE/public_tour_feedback.yml",
        "evidence_rule": "Use synthetic or reviewed-redacted aggregate evidence only; do not include private prompts, raw logs, message text, tool commands, tool output, local paths, or unreviewed screenshots.",
        "safe_sources": [
            "codex-observe report JSON or Markdown",
            "codex-observe comparison JSON or Markdown",
            "reviewer evidence bundle",
        ],
        "do_not_collect": [
            "private prompts",
            "raw Codex logs",
            "message text",
            "tool commands or output",
            "local paths",
            "unreviewed screenshots",
        ],
    }


def latest_ingest_scope(db_path: str | Path) -> dict[str, object] | None:
    db = Path(db_path).expanduser()
    if not db.exists():
        return None
    try:
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            has_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ingest_runs'"
            ).fetchone()
            if not has_table:
                return None
            row = conn.execute(
                """
                SELECT * FROM ingest_runs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.DatabaseError:
        return None
    if row is None:
        return None
    counts = {
        "files_matched": int(row["files_matched"] or 0),
        "files_seen": int(row["files_seen"] or 0),
        "files_imported": int(row["files_imported"] or 0),
        "files_skipped_by_limit": int(row["files_skipped_by_limit"] or 0),
        "threads": int(row["threads"] or 0),
        "events": int(row["events"] or 0),
    }
    skipped = {
        "duplicate_files": int(row["duplicate_files"] or 0),
        "empty_files": int(row["empty_files"] or 0),
        "malformed_files": int(row["malformed_files"] or 0),
        "malformed_lines": int(row["malformed_lines"] or 0),
        "missing_meta_files": int(row["missing_meta_files"] or 0),
        "unreadable_files": int(row["unreadable_files"] or 0),
    }
    sampled = str(row["scan_mode"] or "") == "newest_files"
    warning = None
    if sampled:
        warning = (
            f"Sampled ingest: newest-file limit {int(row['newest_files'] or 0)} selected "
            f"{counts['files_seen']} of {counts['files_matched']} matched JSONL files "
            f"({counts['files_skipped_by_limit']} deferred); treat sessions, reports, comparisons, and dashboard views as sampled evidence."
        )
    return {
        "imported_at": row["imported_at"],
        "scan_limit": {
            "mode": row["scan_mode"],
            "newest_files": row["newest_files"],
        },
        "counts": counts,
        "skipped": skipped,
        "sampled": sampled,
        "warning": warning,
    }


def ingest_scope_markdown_lines(scope: object) -> list[str]:
    if not isinstance(scope, dict):
        return []
    warning = scope.get("warning")
    if not isinstance(warning, str) or not warning:
        return []
    return ["## Ingest Scope", "", f"- {warning}", ""]


def feedback_handoff_markdown_lines(handoff: object) -> list[str]:
    if not isinstance(handoff, dict):
        return []
    lines = ["## Feedback Handoff", ""]
    runbook = handoff.get("runbook")
    issue_template = handoff.get("issue_template")
    evidence_rule = handoff.get("evidence_rule")
    if isinstance(runbook, str):
        lines.append(f"- Runbook: `{runbook}`")
    if isinstance(issue_template, str):
        lines.append(f"- Issue template: `{issue_template}`")
    if isinstance(evidence_rule, str):
        lines.append(f"- Evidence rule: {evidence_rule}")
    safe_sources = handoff.get("safe_sources")
    if isinstance(safe_sources, list) and safe_sources:
        lines.append(
            "- Safe feedback sources: " + "; ".join(str(item) for item in safe_sources)
        )
    do_not_collect = handoff.get("do_not_collect")
    if isinstance(do_not_collect, list) and do_not_collect:
        lines.append(
            "- Do not collect: " + "; ".join(str(item) for item in do_not_collect)
        )
    lines.append("")
    return lines


def _read_sql(conn: sqlite3.Connection, query: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(query, conn, params=params)


def available_sessions(db_path: str) -> list[str]:
    db = Path(db_path).expanduser()
    if not db.exists():
        return []
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT session_id FROM conversations ORDER BY last_seen DESC"
        ).fetchall()
    return [str(row[0]) for row in rows]


RISK_RANK = {"low": 0, "moderate": 1, "high": 2}


def _pct_of_total(value: int | float, total: int | float) -> float:
    if total <= 0 or value <= 0:
        return 0.0
    return round(min(value / total * 100, 100.0), 1)


def sort_session_summaries(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        summaries,
        key=lambda row: (
            RISK_RANK.get(str(row.get("triage_risk") or "unknown"), -1),
            str(row.get("last_seen") or ""),
        ),
        reverse=True,
    )


def session_summaries(db_path: str) -> list[dict[str, Any]]:
    db = Path(db_path).expanduser()
    if not db.exists():
        raise FileNotFoundError(str(db))
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            WITH thread_rollups AS (
              SELECT
                session_id,
                SUM(tool_call_count) AS tool_calls,
                MAX(final_total_tokens) AS largest_thread_tokens
              FROM threads
              GROUP BY session_id
            ),
            guardian_rollups AS (
              SELECT
                session_id,
                SUM(final_input_tokens) AS guardian_input_tokens
              FROM threads
              WHERE agent_role='guardian' OR source_kind='guardian'
              GROUP BY session_id
            ),
            usage_rollups AS (
              SELECT
                t.session_id,
                COUNT(us.thread_id) AS usage_snapshots
              FROM threads t
              JOIN usage_snapshots us ON us.thread_id = t.thread_id
              GROUP BY t.session_id
            ),
            tool_rollups AS (
              SELECT
                t.session_id,
                MAX(tc.output_chars) AS largest_tool_output_chars
              FROM threads t
              JOIN tool_calls tc ON tc.thread_id = t.thread_id
              GROUP BY t.session_id
            ),
            repeated_blocks AS (
              SELECT
                t.session_id,
                SUM(pb.approx_tokens) AS approx_tokens_replayed
              FROM threads t
              JOIN prompt_blocks pb ON pb.thread_id = t.thread_id
              GROUP BY t.session_id, pb.label, pb.block_hash
              HAVING COUNT(*) > 1
            ),
            prompt_rollups AS (
              SELECT
                session_id,
                SUM(approx_tokens_replayed) AS repeated_prompt_tokens
              FROM repeated_blocks
              GROUP BY session_id
            )
            SELECT
              c.session_id,
              c.first_seen,
              c.last_seen,
              c.thread_count,
              c.total_tokens,
              c.total_uncached_input_tokens,
              c.total_cached_input_tokens,
              COALESCE(tr.tool_calls, 0) AS tool_calls,
              COALESCE(ur.usage_snapshots, 0) AS usage_snapshots,
              COALESCE(tr.largest_thread_tokens, 0) AS largest_thread_tokens,
              COALESCE(gr.guardian_input_tokens, 0) AS guardian_input_tokens,
              COALESCE(tor.largest_tool_output_chars, 0) AS largest_tool_output_chars,
              COALESCE(pr.repeated_prompt_tokens, 0) AS repeated_prompt_tokens
            FROM conversations c
            LEFT JOIN thread_rollups tr ON tr.session_id = c.session_id
            LEFT JOIN guardian_rollups gr ON gr.session_id = c.session_id
            LEFT JOIN usage_rollups ur ON ur.session_id = c.session_id
            LEFT JOIN tool_rollups tor ON tor.session_id = c.session_id
            LEFT JOIN prompt_rollups pr ON pr.session_id = c.session_id
            ORDER BY c.last_seen DESC
            """
        ).fetchall()
    summaries = []
    for row in rows:
        total_tokens = int(row["total_tokens"] or 0)
        largest_thread_tokens = int(row["largest_thread_tokens"] or 0)
        repeated_prompt_tokens = int(row["repeated_prompt_tokens"] or 0)
        uncached_input_tokens = int(row["total_uncached_input_tokens"] or 0)
        guardian_input_tokens = int(row["guardian_input_tokens"] or 0)
        largest_tool_output_chars = int(row["largest_tool_output_chars"] or 0)
        largest_thread_share_pct = _pct_of_total(largest_thread_tokens, total_tokens)
        repeated_prompt_share_pct = _pct_of_total(repeated_prompt_tokens, total_tokens)
        uncached_input_share_pct = _pct_of_total(uncached_input_tokens, total_tokens)
        guardian_input_share_pct = _pct_of_total(guardian_input_tokens, total_tokens)
        duration_hours = session_duration_hours(row["first_seen"], row["last_seen"])
        triage = report_triage(
            {
                "summary": {
                    "total_tokens": total_tokens,
                    "session_duration_hours": duration_hours,
                    "largest_thread_share_pct": largest_thread_share_pct,
                    "repeated_prompt_share_pct": repeated_prompt_share_pct,
                    "uncached_input_share_pct": uncached_input_share_pct,
                    "guardian_input_tokens": guardian_input_tokens,
                    "guardian_input_share_pct": guardian_input_share_pct,
                    "largest_tool_output_chars": largest_tool_output_chars,
                    "compactions": 0,
                },
                "headline": {
                    "top_diagnostic": "Run needs triage",
                    "recommendation": "Open the aggregate report for next-action details.",
                },
            }
        )
        summaries.append(
            {
                "session_id": row["session_id"],
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "threads": int(row["thread_count"] or 0),
                "tool_calls": int(row["tool_calls"] or 0),
                "usage_snapshots": int(row["usage_snapshots"] or 0),
                "session_duration_hours": round(duration_hours, 1),
                "session_duration_days": round(duration_hours / 24, 1),
                "total_tokens": total_tokens,
                "uncached_input_tokens": uncached_input_tokens,
                "cached_input_tokens": int(row["total_cached_input_tokens"] or 0),
                "guardian_input_tokens": guardian_input_tokens,
                "triage_risk": triage["risk_level"],
                "largest_thread_share_pct": largest_thread_share_pct,
                "repeated_prompt_share_pct": repeated_prompt_share_pct,
                "uncached_input_share_pct": uncached_input_share_pct,
                "guardian_input_share_pct": guardian_input_share_pct,
                "largest_tool_output_chars": largest_tool_output_chars,
            }
        )
    return sort_session_summaries(summaries)


def filter_session_summaries_by_risk(
    summaries: list[dict[str, Any]], risk_filter: str | None = None
) -> list[dict[str, Any]]:
    if not risk_filter:
        return summaries
    normalized = risk_filter.strip().lower()
    return [
        row
        for row in summaries
        if str(row.get("triage_risk") or "unknown").lower() == normalized
    ]


def session_report_hint(db_path: str, session_id: str | None = None) -> str:
    session_part = f" --session-id {session_id}" if session_id else ""
    return (
        f"run `codex-observe report --db {command_arg(db_path)}{session_part} --out run-report.md` "
        "to export a shareable aggregate-only report."
    )


def session_risk_distribution(summaries: list[dict[str, Any]]) -> dict[str, int]:
    distribution = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    for row in summaries:
        risk = str(row.get("triage_risk") or "unknown").lower()
        if risk not in distribution:
            risk = "unknown"
        distribution[risk] += 1
    return distribution


def session_risk_distribution_line(distribution: dict[str, int]) -> str:
    return (
        "Risk distribution: "
        f"high {int(distribution.get('high', 0))}, "
        f"medium {int(distribution.get('medium', 0))}, "
        f"low {int(distribution.get('low', 0))}, "
        f"unknown {int(distribution.get('unknown', 0))}"
    )


def _portfolio_driver_catalog() -> list[dict[str, Any]]:
    return [
        {
            "driver": "largest_thread_share_pct",
            "label": "Largest thread concentration",
            "threshold": 50.0,
            "unit": "percent",
            "min_threads": 2,
            "action": "Set stop conditions before one thread dominates repeated work.",
        },
        {
            "driver": "session_duration_hours",
            "label": "Multi-day session duration",
            "threshold": 24.0,
            "unit": "hours",
            "action": "Start fresh sessions at durable checkpoints.",
        },
        {
            "driver": "uncached_input_share_pct",
            "label": "High uncached input share",
            "threshold": 35.0,
            "unit": "percent",
            "action": "Filter or summarize fresh context before it enters the run.",
        },
        {
            "driver": "guardian_input_share_pct",
            "label": "High guardian input share",
            "threshold": 25.0,
            "unit": "percent",
            "action": "Limit approval context before guardian checks.",
        },
        {
            "driver": "repeated_prompt_share_pct",
            "label": "Repeated prompt blocks",
            "threshold": 15.0,
            "unit": "percent",
            "action": "Reference stable instructions instead of replaying them.",
        },
        {
            "driver": "largest_tool_output_chars",
            "label": "Large tool output",
            "threshold": 5_000.0,
            "unit": "chars",
            "action": "Narrow bulky commands before sharing output back into context.",
        },
    ]


def _portfolio_driver_display(value: float, unit: str) -> str:
    if unit == "percent":
        return f"{value:.1f}%"
    if unit == "hours":
        if value >= 24:
            return f"{value / 24:.1f} days"
        return f"{value:.1f} hours"
    if unit == "chars":
        return f"{fmt_short(value)} chars"
    return fmt_short(value)


def session_portfolio_drivers(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = len(summaries)
    if total == 0:
        return []
    rows: list[dict[str, Any]] = []
    for order, definition in enumerate(_portfolio_driver_catalog()):
        driver = str(definition["driver"])
        unit = str(definition["unit"])
        threshold = float(definition["threshold"])
        min_threads = definition.get("min_threads")
        values: list[float] = []
        total_impact = 0.0
        for summary in summaries:
            if min_threads is not None and "threads" in summary:
                try:
                    thread_count = int(summary.get("threads") or 0)
                except (TypeError, ValueError):
                    thread_count = 0
                if thread_count < int(min_threads):
                    continue
            try:
                value = float(summary.get(driver) or 0)
            except (TypeError, ValueError):
                value = 0.0
            if value >= threshold:
                values.append(value)
                if unit == "percent":
                    total_impact += (
                        float(summary.get("total_tokens") or 0) * value / 100
                    )
                elif unit == "hours":
                    total_impact += value
                else:
                    total_impact += value
        if not values:
            continue
        max_value = max(values)
        rows.append(
            {
                "driver": driver,
                "label": definition["label"],
                "sessions": len(values),
                "share_pct": round(len(values) / total * 100, 1),
                "max_value": round(max_value, 1),
                "max_display": _portfolio_driver_display(max_value, unit),
                "threshold": threshold,
                "threshold_display": _portfolio_driver_display(threshold, unit),
                "action": definition["action"],
                "_impact": total_impact,
                "_order": order,
            }
        )
    rows.sort(
        key=lambda row: (
            int(row["sessions"]),
            float(row["_impact"]),
            -int(row["_order"]),
        ),
        reverse=True,
    )
    for row in rows:
        row.pop("_impact", None)
        row.pop("_order", None)
    return rows


def session_portfolio_summary(
    summaries: list[dict[str, Any]],
    matching_summaries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    matching = summaries if matching_summaries is None else matching_summaries
    distribution = session_risk_distribution(summaries)
    total = len(summaries)
    matching_count = len(matching)
    high = int(distribution.get("high", 0) or 0)
    medium = int(distribution.get("medium", 0) or 0)
    low = int(distribution.get("low", 0) or 0)
    unknown = int(distribution.get("unknown", 0) or 0)
    high_share = round(high / total * 100, 1) if total else 0.0
    portfolio_drivers = session_portfolio_drivers(summaries)
    top_driver = portfolio_drivers[0] if portfolio_drivers else None

    if total == 0:
        posture = "empty"
        headline = "No sessions imported yet."
        action = "Ingest local logs or create the synthetic demo before looking for workflow patterns."
    elif high == total:
        posture = "all_high"
        headline = f"All {total} sessions are high risk."
        action = "Treat this as a workflow pattern: start with the recommended run, apply one habit, then compare the next run before continuing."
    elif high > 0:
        posture = "mixed_high"
        headline = f"{high} of {total} sessions are high risk."
        action = "Start with the recommended high-risk run, then compare against a lower-risk follow-up to find which habits worked."
    elif medium > 0:
        posture = "watchlist"
        headline = (
            f"No high-risk sessions; {medium} of {total} sessions are medium risk."
        )
        action = "Review the medium-risk run before it turns into a long-lived or repeated-context workflow pattern."
    else:
        posture = "healthy"
        headline = f"No high- or medium-risk sessions across {total} sessions."
        action = "Keep the current workflow, and use comparisons after the next substantial run to catch regressions early."

    if matching_summaries is not None and matching_count != total:
        filter_note = f"Current filter shows {matching_count} of {total} sessions."
    else:
        filter_note = "Current view includes every imported session."

    return {
        "risk_posture": posture,
        "headline": headline,
        "action": action,
        "filter_note": filter_note,
        "total_sessions": total,
        "matching_sessions": matching_count,
        "high_risk_sessions": high,
        "medium_risk_sessions": medium,
        "low_risk_sessions": low,
        "unknown_risk_sessions": unknown,
        "high_risk_share_pct": high_share,
        "top_driver": top_driver,
        "drivers": portfolio_drivers,
    }


def session_portfolio_summary_line(summary: dict[str, Any]) -> str:
    headline = str(summary.get("headline") or "No portfolio summary available.")
    action = str(summary.get("action") or "Review the recommended session.")
    top_driver = summary.get("top_driver")
    if isinstance(top_driver, dict):
        driver_line = (
            f" Dominant pattern: {top_driver.get('label')} in "
            f"{top_driver.get('sessions')} of {summary.get('total_sessions')} sessions "
            f"(max {top_driver.get('max_display')})."
        )
    else:
        driver_line = ""
    return f"Portfolio: {headline} {action}{driver_line}"


def session_success_target_preview(recommended: dict[str, Any]) -> dict[str, Any]:
    duration_hours = float(recommended.get("session_duration_hours") or 0)
    if duration_hours >= 24:
        current_days = duration_hours / 24
        return {
            "metric": "session_duration_hours",
            "direction": "lower_is_better",
            "current_value": round(duration_hours, 1),
            "target_value": 24.0,
            "unit": "hours",
            "current": f"{current_days:.1f} days",
            "target": "below 24.0 hours",
            "driver": "Session duration",
            "action": "Start a fresh Codex session at each durable checkpoint",
        }

    largest_thread = float(recommended.get("largest_thread_share_pct") or 0)
    repeated = float(recommended.get("repeated_prompt_share_pct") or 0)
    uncached = float(recommended.get("uncached_input_share_pct") or 0)
    guardian = float(recommended.get("guardian_input_share_pct") or 0)
    tool_chars = _safe_int(recommended.get("largest_tool_output_chars"))
    total_tokens = _safe_int(recommended.get("total_tokens"))
    largest_thread_tokens = int(total_tokens * largest_thread / 100)
    repeated_tokens = int(total_tokens * repeated / 100)
    uncached_tokens = _safe_int(recommended.get("uncached_input_tokens")) or int(
        total_tokens * uncached / 100
    )
    guardian_tokens = _safe_int(recommended.get("guardian_input_tokens")) or int(
        total_tokens * guardian / 100
    )
    actionable_drivers = [
        ("Largest thread", largest_thread > 50.0, largest_thread_tokens),
        ("Repeated prompt blocks", repeated > 15.0, repeated_tokens),
        ("Uncached input", uncached > 35.0, uncached_tokens),
        ("Guardian overhead", guardian > 25.0, guardian_tokens),
        ("Largest tool output", tool_chars > 5_000, tool_chars / 4),
    ]
    driver = next(
        (
            candidate
            for candidate, _actionable, _impact in sorted(
                actionable_drivers, key=lambda item: item[2], reverse=True
            )
            if _actionable
        ),
        "",
    )

    if driver == "Largest thread":
        current = float(recommended.get("largest_thread_share_pct") or 0)
        target = _pct_target(current, 50.0, 35.0)
        return {
            "metric": "largest_thread_share_pct",
            "direction": "lower_is_better",
            "current_value": current,
            "target_value": target,
            "unit": "percent_of_run",
            "current": f"{current:.1f}%",
            "target": f"below {target:.1f}%",
            "driver": driver,
            "action": "Set a stop condition for the dominant thread",
        }
    if driver == "Repeated prompt blocks":
        current = float(recommended.get("repeated_prompt_share_pct") or 0)
        target = _pct_target(current, 15.0, 8.0)
        return {
            "metric": "repeated_prompt_share_pct",
            "direction": "lower_is_better",
            "current_value": current,
            "target_value": target,
            "unit": "percent_of_run",
            "current": f"{current:.1f}%",
            "target": f"below {target:.1f}%",
            "driver": driver,
            "action": "Reduce replayed prompt blocks before the next run",
        }
    if driver == "Uncached input":
        current = float(recommended.get("uncached_input_share_pct") or 0)
        target = _pct_target(current, 35.0, 20.0)
        return {
            "metric": "uncached_input_share_pct",
            "direction": "lower_is_better",
            "current_value": current,
            "target_value": target,
            "unit": "percent_of_run",
            "current": f"{current:.1f}%",
            "target": f"below {target:.1f}%",
            "driver": driver,
            "action": "Filter or summarize fresh context before the next run",
        }
    if driver == "Guardian overhead":
        current = float(recommended.get("guardian_input_share_pct") or 0)
        target = _pct_target(current, 40.0, 25.0)
        return {
            "metric": "guardian_input_share_pct",
            "direction": "lower_is_better",
            "current_value": current,
            "target_value": target,
            "unit": "percent_of_run",
            "current": f"{current:.1f}%",
            "target": f"below {target:.1f}%",
            "driver": driver,
            "action": "Limit approval context before guardian checks",
        }
    if driver == "Largest tool output":
        current = _safe_int(recommended.get("largest_tool_output_chars"))
        target = 5_000 if current >= 5_000 else 2_000
        return {
            "metric": "largest_tool_output_chars",
            "direction": "lower_is_better",
            "current_value": current,
            "target_value": target,
            "unit": "chars",
            "current": f"{fmt_short(current)} chars",
            "target": f"below {fmt_short(target)} chars",
            "driver": driver,
            "action": "Narrow commands before large tool output enters context",
        }
    total = _safe_int(recommended.get("total_tokens"))
    target = int(total * 0.9) if total else 0
    return {
        "metric": "total_tokens",
        "direction": "lower_is_better",
        "current_value": total,
        "target_value": target,
        "unit": "tokens",
        "current": f"{fmt_short(total)} tokens",
        "target": f"below {fmt_short(target)} tokens",
        "driver": driver or "Total tokens",
        "action": "Use total tokens as the next-run guardrail",
    }


def session_recommended_action_lines(recommended: dict[str, Any]) -> list[str]:
    share_drivers = [
        ("largest thread share", recommended.get("largest_thread_share_pct")),
        ("repeated prompt share", recommended.get("repeated_prompt_share_pct")),
        ("uncached input share", recommended.get("uncached_input_share_pct")),
        ("guardian input share", recommended.get("guardian_input_share_pct")),
    ]
    driver_parts = []
    for label, value in share_drivers:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if numeric > 0:
            driver_parts.append(f"{label}: {numeric:.1f}%")
    tool_output_chars = _safe_int(recommended.get("largest_tool_output_chars"))
    if tool_output_chars > 0:
        driver_parts.append(
            f"largest tool output: {fmt_short(tool_output_chars)} chars"
        )
    duration_hours = float(recommended.get("session_duration_hours") or 0)
    if duration_hours >= 24:
        driver_parts.insert(0, f"session duration: {duration_hours / 24:.1f} days")
    target = session_success_target_preview(recommended)
    return [
        "Recommended action:",
        f"- Export report for session: {recommended['session_id']}",
        "- Why: highest aggregate triage risk; latest run breaks ties",
        f"- Risk: {recommended['triage_risk']}",
        f"- Top drivers: {'; '.join(driver_parts) if driver_parts else 'none recorded'}",
        f"- Next-run target: {target['metric']} {target['current']} -> {target['target']}",
        f"- Habit to try: {target['action']}",
    ]


def session_validation_commands(db_path: str, session_id: str) -> list[str]:
    db_arg = command_arg(db_path)
    return [
        f"codex-observe report --db {db_arg} --session-id {session_id} --out run-report.md",
        f"codex-observe report --db {db_arg} --session-id {session_id} --format json --out run-report.json",
        f"codex-observe report --db {db_arg} --session-id <next-session-id> --format json --out next-run-report.json",
        "codex-observe compare --before-report run-report.json --after-report next-run-report.json --out run-comparison.md",
    ]


def session_review_path_lines(db_path: str, session_id: str) -> list[str]:
    db_arg = command_arg(db_path)
    return [
        "Review path:",
        f"- Save report JSON: codex-observe report --db {db_arg} --session-id {session_id} --format json --out run-report.json",
        f"- Validate next run: codex-observe report --db {db_arg} --session-id <next-session-id> --format json --out next-run-report.json",
        "- Compare workflow change: codex-observe compare --before-report run-report.json --after-report next-run-report.json --out run-comparison.md",
        "- File safe feedback: docs/PUBLIC_TOUR_FEEDBACK.md",
    ]


def session_summary_lines(
    db_path: str, limit: int | None = 50, risk_filter: str | None = None
) -> list[str]:
    summaries = session_summaries(db_path)
    if not summaries:
        db_arg = command_arg(db_path)
        next_commands = [
            f"codex-observe ingest ~/.codex/sessions --db {db_arg}",
            f"codex-observe demo --db {db_arg}",
        ]
        return [
            "No conversations found.",
            "Next commands:",
            *(f"- {command}" for command in next_commands),
            f"Next: run `{next_commands[0]}` or `{next_commands[1]}`.",
        ]
    distribution = session_risk_distribution(summaries)
    filtered = filter_session_summaries_by_risk(summaries, risk_filter)
    portfolio = session_portfolio_summary(summaries, filtered)
    lines = [
        session_risk_distribution_line(distribution),
        session_portfolio_summary_line(portfolio),
    ]
    if risk_filter:
        normalized = risk_filter.strip().lower()
        lines.append(
            f"Filter: {normalized} risk ({len(filtered)} of {len(summaries)} sessions)."
        )
    if not filtered:
        lines.extend(
            [
                "No sessions matched the risk filter.",
                "Next: remove --risk or choose one of high, medium, low, unknown.",
            ]
        )
        return lines
    lines.append(
        "Session ID | Last seen | Risk | Duration | Threads | Tools | Snapshots | Tool out | Tokens | Uncached | Guardian"
    )
    display_limit = len(filtered) if limit is None else max(1, int(limit))
    displayed = filtered[:display_limit]
    for row in displayed:
        lines.append(
            " | ".join(
                [
                    str(row["session_id"]),
                    str(row.get("last_seen") or "unknown"),
                    str(row["triage_risk"]),
                    f"{float(row.get('session_duration_hours') or 0) / 24:.1f}d",
                    str(row["threads"]),
                    str(row["tool_calls"]),
                    fmt_short(row.get("usage_snapshots", 0)),
                    fmt_short(row.get("largest_tool_output_chars", 0)),
                    fmt_short(row["total_tokens"]),
                    fmt_short(row["uncached_input_tokens"]),
                    f"{float(row.get('guardian_input_share_pct') or 0):.1f}%",
                ]
            )
        )
    if len(displayed) < len(filtered):
        if risk_filter:
            lines.append(
                f"Showing {len(displayed)} of {len(filtered)} matching sessions ({len(summaries)} total)."
            )
        else:
            lines.append(f"Showing {len(displayed)} of {len(summaries)} sessions.")
    recommended = filtered[0]
    recommended_session_id = str(recommended["session_id"])
    lines.extend(session_recommended_action_lines(recommended))
    lines.extend(session_review_path_lines(db_path, recommended_session_id))
    next_commands = session_validation_commands(db_path, recommended_session_id)
    lines.append("Next commands:")
    lines.extend(f"- {command}" for command in next_commands)
    next_scope = "matching " if risk_filter else ""
    lines.append(
        f"Next: review the highest-risk {next_scope}run "
        f"({recommended['session_id']}, {recommended['triage_risk']} risk); "
        f"{session_report_hint(db_path, recommended_session_id)}"
    )
    return lines


def default_report_session(db_path: str) -> str:
    summaries = session_summaries(db_path)
    if not summaries:
        raise ValueError("no conversations found in database")
    return str(summaries[0]["session_id"])


def report_follow_up_commands(db_path: str, session_id: str) -> dict[str, list[str]]:
    db_arg = command_arg(db_path)
    return {
        "next_commands": [
            f"codex-observe sessions --db {db_arg} --json",
            f"codex-observe report --db {db_arg} --session-id {session_id} --format json --out run-report.json",
        ],
        "next_command_templates": [
            f"codex-observe report --db {db_arg} --session-id <next-session-id> --format json --out next-run-report.json",
            "codex-observe compare --before-report run-report.json --after-report next-run-report.json --out run-comparison.md",
        ],
    }


def report_review_path(
    db_path: str, session_id: str, success_target: dict[str, Any]
) -> list[dict[str, str]]:
    db_arg = command_arg(db_path)
    metric = str(success_target.get("metric") or "target metric")
    target = str(success_target.get("target") or "the target threshold")
    verification = str(
        success_target.get("verification")
        or "Export the next run as report JSON and compare the target metric."
    )
    return [
        {
            "label": "Save this report JSON",
            "command": f"codex-observe report --db {db_arg} --session-id {session_id} --format json --out run-report.json",
            "success_check": "JSON includes schema_version, success_target, next_action_detail, and review_path.",
        },
        {
            "label": "Apply the recommended habit",
            "command": "Review the Recommended Action and Next Run Playbook sections before the next run.",
            "success_check": f"Next run is planned around improving {metric} toward {target}.",
        },
        {
            "label": "Export the next run",
            "command": f"codex-observe report --db {db_arg} --session-id <next-session-id> --format json --out next-run-report.json",
            "success_check": "next-run-report.json uses the same report schema and aggregate-only privacy mode.",
        },
        {
            "label": "Compare the workflow change",
            "command": "codex-observe compare --before-report run-report.json --after-report next-run-report.json --out run-comparison.md",
            "success_check": verification,
        },
    ]


def report_next_run_guardrail(success_target: dict[str, Any]) -> str:
    metric = str(success_target.get("metric") or "")
    if metric == "session_duration_hours":
        return "Write a short handoff and start a fresh session before the run crosses one day."
    if metric == "largest_thread_share_pct":
        return "Pause or split the run when one thread starts to dominate the work."
    if metric == "largest_tool_output_chars":
        return "Stop broad commands before large output enters the conversation; rerun with a narrower query or saved artifact."
    if metric == "repeated_prompt_share_pct":
        return "Move repeated instructions into a stable reference before launching another worker or approval thread."
    if metric == "uncached_input_share_pct":
        return "Summarize or filter fresh context before adding it to the next prompt."
    if metric == "guardian_input_share_pct":
        return "Keep approval prompts narrow; checkpoint before repeated guardian checks replay the run context."
    if metric == "compactions":
        return "Create a handoff before context has to be compacted."
    return "Pause, split, or summarize before the same driver dominates the run."


def report_next_run_checklist(report: dict[str, Any]) -> list[dict[str, str]]:
    success_target = report.get("success_target", {})
    next_action = report.get("next_action_detail", {})
    playbook = report.get("playbook", []) or []
    habit = "Apply the highest-impact playbook habit."
    if playbook and isinstance(playbook[0], dict) and playbook[0].get("Habit"):
        habit = str(playbook[0]["Habit"])
    target_metric = str(success_target.get("metric") or "target metric")
    current = str(success_target.get("current") or "current value")
    target = str(success_target.get("target") or "target value")
    action_target = str(next_action.get("target") or habit)
    verification = str(
        success_target.get("verification")
        or "Export the next run as report JSON and compare the target metric."
    )
    return [
        {
            "phase": "Before next run",
            "action": habit,
            "success_check": f"The run plan explicitly targets {action_target}.",
        },
        {
            "phase": "During next run",
            "action": report_next_run_guardrail(success_target),
            "success_check": f"{target_metric} moves from {current} toward {target}.",
        },
        {
            "phase": "After next run",
            "action": "Export next-run-report.json and compare it with this baseline.",
            "success_check": verification,
        },
    ]


def report_next_run_also_watch(report: dict[str, Any], limit: int = 3) -> list[str]:
    opportunities = report.get("opportunities", []) or []
    if not isinstance(opportunities, list):
        return []
    items: list[str] = []
    for row in opportunities[1:]:
        if not isinstance(row, dict):
            continue
        driver = str(row.get("Driver") or "").strip()
        scale = str(row.get("Scale") or "").strip()
        if not driver or not scale:
            continue
        items.append(f"{driver} - {scale}")
        if len(items) >= limit:
            break
    return items


def report_next_run_brief(report: dict[str, Any]) -> dict[str, Any]:
    success_target = report.get("success_target", {}) or {}
    next_action = report.get("next_action_detail", {}) or {}
    triage = report.get("triage", {}) or {}
    headline = report.get("headline", {}) or {}
    checklist = report.get("next_run_checklist") or report_next_run_checklist(report)
    habit = str(
        next_action.get("target")
        or headline.get("recommendation")
        or triage.get("next_action")
        or "Apply the top recommended workflow habit."
    )
    metric = str(success_target.get("metric") or "target metric")
    current = str(success_target.get("current") or "current value")
    target = str(success_target.get("target") or "target value")
    driver = str(
        triage.get("primary_driver")
        or headline.get("top_diagnostic")
        or "top aggregate driver"
    )
    verification = str(
        success_target.get("verification")
        or "Export the next run as report JSON and compare it with this baseline."
    )
    guardrail = "Pause, split, or summarize before the same driver dominates the run."
    if (
        isinstance(checklist, list)
        and len(checklist) > 1
        and isinstance(checklist[1], dict)
    ):
        guardrail = str(checklist[1].get("action") or guardrail)
    also_watch = report_next_run_also_watch(report)
    prompt_lines = [
        "Next Codex run plan:",
        f"- Try: {habit}",
        f"- Watch: {driver}",
    ]
    if also_watch:
        prompt_lines.append(f"- Also watch: {'; '.join(also_watch)}")
    prompt_lines.extend(
        [
            f"- Target: move {metric} from {current} toward {target}",
            f"- Guardrail: {guardrail}",
            f"- Afterward: {verification}",
        ]
    )
    prompt = "\n".join(prompt_lines)
    return {
        "title": "Next Codex run plan",
        "habit": habit,
        "watch": driver,
        "also_watch": also_watch,
        "target_metric": metric,
        "current": current,
        "target": target,
        "guardrail": guardrail,
        "verification": verification,
        "copy_prompt": prompt,
    }


def build_report(db_path: str, session_id: str | None = None) -> dict[str, Any]:
    db = Path(db_path).expanduser()
    if not db.exists():
        raise FileNotFoundError(str(db))

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        selected_session = session_id or default_report_session(str(db))
        conv = conn.execute(
            "SELECT * FROM conversations WHERE session_id=?",
            (selected_session,),
        ).fetchone()
        if conv is None:
            raise ValueError(f"session not found: {selected_session}")

        threads = _read_sql(
            conn,
            "SELECT * FROM threads WHERE session_id=? ORDER BY created_at, first_seen",
            (selected_session,),
        )
        usage = _read_sql(
            conn,
            "SELECT * FROM usage_snapshots WHERE thread_id IN (SELECT thread_id FROM threads WHERE session_id=?) ORDER BY timestamp, idx",
            (selected_session,),
        )
        tools = _read_sql(
            conn,
            "SELECT * FROM tool_calls WHERE thread_id IN (SELECT thread_id FROM threads WHERE session_id=?) ORDER BY timestamp",
            (selected_session,),
        )
        events = _read_sql(
            conn,
            """
            SELECT e.*
            FROM events e
            JOIN threads t ON t.thread_id = e.thread_id
            WHERE t.session_id=?
            ORDER BY e.timestamp, e.idx
            """,
            (selected_session,),
        )
        duplicated_blocks = _read_sql(
            conn,
            """
            SELECT label, block_hash, COUNT(*) AS seen, COUNT(DISTINCT thread_id) AS threads,
                   MAX(approx_tokens) AS approx_tokens_each,
                   SUM(approx_tokens) AS approx_tokens_replayed
            FROM prompt_blocks
            WHERE thread_id IN (SELECT thread_id FROM threads WHERE session_id=?)
            GROUP BY label, block_hash
            HAVING COUNT(*) > 1
            ORDER BY approx_tokens_replayed DESC
            LIMIT 300
            """,
            (selected_session,),
        )

    threads = prepare_threads(threads)
    usage = numericize(
        usage,
        [
            "idx",
            "input_tokens",
            "cached_input_tokens",
            "uncached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
        ],
    )
    tools = numericize(tools, ["timeout_ms", "success", "duration_ms", "output_chars"])
    for private_col in ["arguments_json", "command", "workdir", "output"]:
        if private_col in tools.columns:
            tools[private_col] = ""

    diagnostics = diagnostics_df(threads, usage, events, tools, duplicated_blocks)
    findings = findings_df(threads, usage, events)
    compactions = compactions_df(events, usage, threads)

    total_input = int(conv["total_input_tokens"] or 0)
    cached = int(conv["total_cached_input_tokens"] or 0)
    cache_pct = cached / (total_input or 1) * 100
    kind_counts = threads["kind"].value_counts().to_dict() if not threads.empty else {}
    largest_thread = threads.sort_values("final_total_tokens", ascending=False).head(1)
    repeated_prompt_tokens = 0
    if (
        not duplicated_blocks.empty
        and "approx_tokens_replayed" in duplicated_blocks.columns
    ):
        repeated_prompt_tokens = int(
            pd.to_numeric(duplicated_blocks["approx_tokens_replayed"], errors="coerce")
            .fillna(0)
            .sum()
        )
    largest_tool_output_chars = 0
    if not tools.empty and "output_chars" in tools.columns:
        largest_tool_output_chars = int(tools["output_chars"].fillna(0).max())

    guardian_threads = (
        threads[threads["kind"] == "guardian"] if not threads.empty else threads
    )
    guardian_input_tokens = 0
    guardian_output_reasoning_tokens = 0
    if not guardian_threads.empty:
        guardian_input_tokens = int(
            guardian_threads["final_input_tokens"].fillna(0).sum()
        )
        guardian_output_reasoning_tokens = int(
            (
                guardian_threads["final_output_tokens"].fillna(0)
                + guardian_threads["final_reasoning_tokens"].fillna(0)
            ).sum()
        )

    total_tokens = int(conv["total_tokens"] or 0)
    duration_hours = session_duration_hours(conv["first_seen"], conv["last_seen"])
    largest_thread_tokens = (
        int(largest_thread["final_total_tokens"].iloc[0])
        if not largest_thread.empty
        else 0
    )

    opportunities = opportunity_df(
        {
            "total_tokens": total_tokens,
            "largest_thread_tokens": largest_thread_tokens,
            "repeated_prompt_tokens": repeated_prompt_tokens,
            "guardian_input_tokens": guardian_input_tokens,
            "uncached_input_tokens": int(conv["total_uncached_input_tokens"] or 0),
            "largest_tool_output_chars": largest_tool_output_chars,
            "compactions": int(len(compactions)),
            "session_duration_hours": duration_hours,
        }
    )

    diagnostics = add_session_duration_diagnostic(
        diagnostics,
        duration_hours=duration_hours,
        usage_snapshots=int(len(usage)),
    )
    playbook = next_run_playbook_df(diagnostics)

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "privacy": {
            "mode": "aggregate-only",
            "excluded": [
                "message text",
                "prompt block previews",
                "event payload JSON",
                "tool arguments",
                "tool commands",
                "tool output",
            ],
        },
        "ingest_scope": latest_ingest_scope(db),
        "session": {
            "session_id": selected_session,
            "first_seen": conv["first_seen"],
            "last_seen": conv["last_seen"],
        },
        "summary": {
            "threads": int(conv["thread_count"] or 0),
            "workers": int(kind_counts.get("worker", 0)),
            "explorers": int(kind_counts.get("explorer", 0)),
            "guardians": int(kind_counts.get("guardian", 0)),
            "tool_calls": int(threads["tool_call_count"].fillna(0).sum())
            if not threads.empty
            else 0,
            "usage_snapshots": int(len(usage)),
            "session_duration_hours": duration_hours,
            "session_duration_days": round(duration_hours / 24, 1)
            if duration_hours
            else 0.0,
            "compactions": int(len(compactions)),
            "total_tokens": total_tokens,
            "input_tokens": total_input,
            "uncached_input_tokens": int(conv["total_uncached_input_tokens"] or 0),
            "cached_input_tokens": cached,
            "guardian_input_tokens": guardian_input_tokens,
            "guardian_output_reasoning_tokens": guardian_output_reasoning_tokens,
            "guardian_input_share_pct": _pct_of_total(
                guardian_input_tokens, total_tokens
            ),
            "cache_pct": round(cache_pct, 1),
            "largest_thread_tokens": largest_thread_tokens,
            "largest_thread_share_pct": _pct_of_total(
                largest_thread_tokens, total_tokens
            ),
            "largest_thread_kind": str(largest_thread["kind"].iloc[0])
            if not largest_thread.empty
            else "",
            "repeated_prompt_tokens": repeated_prompt_tokens,
            "repeated_prompt_share_pct": _pct_of_total(
                repeated_prompt_tokens, total_tokens
            ),
            "uncached_input_share_pct": _pct_of_total(
                int(conv["total_uncached_input_tokens"] or 0), total_tokens
            ),
            "largest_tool_output_chars": largest_tool_output_chars,
        },
        "diagnostics": diagnostics.to_dict("records"),
        "playbook": playbook.to_dict("records"),
        "opportunities": opportunities.to_dict("records"),
        "findings": findings.to_dict("records"),
    }
    report["headline"] = report_headline(report)
    report["triage"] = report_triage(report)
    report["next_action_detail"] = report_next_action_detail(report)
    report["success_target"] = report_success_target(report)
    report.update(report_follow_up_commands(str(db), selected_session))
    report["review_path"] = report_review_path(
        str(db), selected_session, report["success_target"]
    )
    report["next_run_checklist"] = report_next_run_checklist(report)
    report["next_run_brief"] = report_next_run_brief(report)
    report["feedback_handoff"] = aggregate_feedback_handoff()
    return report


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def session_duration_hours(first_seen: Any, last_seen: Any) -> float:
    first = _parse_timestamp(first_seen)
    last = _parse_timestamp(last_seen)
    if first is None or last is None or last <= first:
        return 0.0
    return round((last - first).total_seconds() / 3600, 1)


def add_session_duration_diagnostic(
    diagnostics: pd.DataFrame,
    *,
    duration_hours: float,
    usage_snapshots: int,
) -> pd.DataFrame:
    if duration_hours < 24:
        return diagnostics
    columns = ["Priority", "Diagnostic", "Action", "Evidence"]
    duration_days = duration_hours / 24
    row = pd.DataFrame(
        [
            {
                "Priority": "High",
                "Diagnostic": "Run spans multiple days",
                "Action": "Create a short handoff and start a fresh Codex session at the next durable checkpoint.",
                "Evidence": f"Session covered {duration_days:.1f} days across {fmt_short(usage_snapshots)} usage snapshots.",
            }
        ],
        columns=columns,
    )
    if diagnostics.empty:
        return row
    existing = diagnostics[
        diagnostics.get("Diagnostic") != "Run spans multiple days"
    ].copy()
    return pd.concat([row, existing], ignore_index=True)[columns]


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _metric_delta(
    before: dict[str, Any],
    after: dict[str, Any],
    key: str,
    label: str,
    *,
    direction_mode: str = "lower_is_better",
) -> dict[str, Any]:
    before_value = _safe_int(before.get(key))
    after_value = _safe_int(after.get(key))
    delta = after_value - before_value
    delta_pct = round(delta / before_value * 100, 1) if before_value else None
    if direction_mode == "neutral":
        direction = "changed" if delta else "unchanged"
    elif delta < 0:
        direction = "improved"
    elif delta > 0:
        direction = "regressed"
    else:
        direction = "unchanged"
    return {
        "metric": key,
        "label": label,
        "before": before_value,
        "after": after_value,
        "delta": delta,
        "delta_pct": delta_pct,
        "direction": direction,
    }


def _diagnostic_names_ordered(report: dict[str, Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for row in report.get("diagnostics", []):
        name = str(row.get("Diagnostic") or "").strip()
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    return names


def _diagnostic_names(report: dict[str, Any]) -> set[str]:
    return set(_diagnostic_names_ordered(report))


def report_headline(report: dict[str, Any]) -> dict[str, str]:
    summary = report.get("summary", {})
    diagnostics = report.get("diagnostics", [])
    playbook = report.get("playbook", [])
    total = fmt_short(summary.get("total_tokens", 0))
    snapshots = fmt_short(summary.get("usage_snapshots", 0))
    largest = fmt_short(summary.get("largest_thread_tokens", 0))
    largest_share = float(summary.get("largest_thread_share_pct", 0) or 0)
    repeated = fmt_short(summary.get("repeated_prompt_tokens", 0))
    repeated_share = float(summary.get("repeated_prompt_share_pct", 0) or 0)
    tool_chars = fmt_short(summary.get("largest_tool_output_chars", 0))
    guardian_input = fmt_short(summary.get("guardian_input_tokens", 0))
    guardian_share = float(summary.get("guardian_input_share_pct", 0) or 0)
    headline_parts = [
        f"{total} total tokens across {snapshots} usage snapshots",
        f"largest thread {largest} ({largest_share:.1f}%)",
        f"repeated prompts {repeated} ({repeated_share:.1f}%)",
    ]
    if guardian_share > 0:
        headline_parts.append(
            f"guardian input {guardian_input} ({guardian_share:.1f}%)"
        )
    headline_parts.append(f"largest tool output {tool_chars} chars")
    top_diagnostic = (
        str(diagnostics[0].get("Diagnostic"))
        if diagnostics and diagnostics[0].get("Diagnostic")
        else "No high-signal diagnostic"
    )
    recommendation = (
        str(playbook[0].get("Habit"))
        if playbook and playbook[0].get("Habit")
        else "Inspect the largest thread before changing workflow."
    )
    return {
        "headline": "; ".join(headline_parts) + ".",
        "top_diagnostic": top_diagnostic,
        "recommendation": recommendation,
    }


def report_triage(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary", {})
    headline = report.get("headline", {})
    largest_share = float(summary.get("largest_thread_share_pct", 0) or 0)
    repeated_share = float(summary.get("repeated_prompt_share_pct", 0) or 0)
    uncached_share = float(summary.get("uncached_input_share_pct", 0) or 0)
    guardian_share = float(summary.get("guardian_input_share_pct", 0) or 0)
    guardian_tokens = _safe_int(summary.get("guardian_input_tokens"))
    tool_chars = _safe_int(summary.get("largest_tool_output_chars"))
    total_tokens = _safe_int(summary.get("total_tokens"))
    compactions = _safe_int(summary.get("compactions"))

    high_reasons: list[str] = []
    moderate_reasons: list[str] = []
    if largest_share >= 50:
        high_reasons.append(
            f"Largest thread used {largest_share:.1f}% of total tokens."
        )
    elif largest_share >= 35:
        moderate_reasons.append(
            f"Largest thread used {largest_share:.1f}% of total tokens."
        )
    if repeated_share >= 15:
        high_reasons.append(
            f"Repeated prompt blocks used {repeated_share:.1f}% of total tokens."
        )
    elif repeated_share >= 8:
        moderate_reasons.append(
            f"Repeated prompt blocks used {repeated_share:.1f}% of total tokens."
        )
    if uncached_share >= 35:
        high_reasons.append(
            f"Uncached input used {uncached_share:.1f}% of total tokens."
        )
    elif uncached_share >= 20:
        moderate_reasons.append(
            f"Uncached input used {uncached_share:.1f}% of total tokens."
        )
    if guardian_share >= 40 and guardian_tokens >= 25_000:
        high_reasons.append(
            f"Guardian input used {guardian_share:.1f}% of total tokens."
        )
    elif guardian_share >= 25 and guardian_tokens >= 25_000:
        moderate_reasons.append(
            f"Guardian input used {guardian_share:.1f}% of total tokens."
        )
    if tool_chars >= 5_000:
        high_reasons.append(f"Largest tool output was {fmt_short(tool_chars)} chars.")
    elif tool_chars >= 2_000:
        moderate_reasons.append(
            f"Largest tool output was {fmt_short(tool_chars)} chars."
        )
    if total_tokens >= 100_000:
        high_reasons.append(f"Run used {fmt_short(total_tokens)} total tokens.")
    elif total_tokens >= 25_000:
        moderate_reasons.append(f"Run used {fmt_short(total_tokens)} total tokens.")
    if compactions:
        moderate_reasons.append(f"Run compacted context {compactions} time(s).")

    if high_reasons:
        risk_level = "high"
        reasons = high_reasons + moderate_reasons
    elif moderate_reasons:
        risk_level = "moderate"
        reasons = moderate_reasons
    else:
        risk_level = "low"
        reasons = ["No high-risk cost driver crossed review thresholds."]

    return {
        "risk_level": risk_level,
        "primary_driver": headline.get("top_diagnostic", "No high-signal diagnostic"),
        "next_action": headline.get(
            "recommendation", "Inspect the largest thread before changing workflow."
        ),
        "reasons": reasons,
    }


def report_next_action_detail(report: dict[str, Any]) -> dict[str, Any]:
    playbook = report.get("playbook", []) or []
    diagnostics = report.get("diagnostics", []) or []
    triage = report.get("triage", {}) or {}
    if playbook:
        first = playbook[0]
        return {
            "action": "apply_next_run_habit",
            "target_type": "playbook_habit",
            "target": str(
                first.get("Habit")
                or "Inspect the largest thread before changing workflow."
            ),
            "impact": str(first.get("Impact") or "Targets the top diagnostic."),
            "source": str(
                first.get("Source")
                or triage.get("primary_driver")
                or "No high-signal diagnostic"
            ),
        }
    if diagnostics:
        first_diagnostic = diagnostics[0]
        return {
            "action": "inspect_top_diagnostic",
            "target_type": "diagnostic",
            "target": str(
                first_diagnostic.get("Diagnostic") or "No high-signal diagnostic"
            ),
            "impact": str(
                first_diagnostic.get("Action")
                or triage.get("next_action")
                or "Inspect the report."
            ),
            "source": str(first_diagnostic.get("Evidence") or "aggregate report"),
        }
    return {
        "action": "inspect_report",
        "target_type": "report",
        "target": str(report.get("session", {}).get("session_id") or "run report"),
        "impact": str(triage.get("next_action") or "Inspect the report."),
        "source": "aggregate report",
    }


def _pct_target(
    current: float, high_threshold: float, moderate_threshold: float
) -> float:
    return high_threshold if current >= high_threshold else moderate_threshold


def report_success_target(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary", {}) or {}
    opportunities = report.get("opportunities", []) or []
    driver = str(opportunities[0].get("Driver") or "") if opportunities else ""

    if driver == "Session duration":
        current = float(summary.get("session_duration_hours") or 0)
        target = 24.0
        current_days = current / 24 if current else 0.0
        return {
            "metric": "session_duration_hours",
            "direction": "lower_is_better",
            "current_value": current,
            "target_value": target,
            "unit": "hours",
            "current": f"{current_days:.1f} days",
            "target": "below 24.0 hours",
            "rationale": "The top opportunity is a long-running session; the next run should restart at durable checkpoints before stale context accumulates.",
            "verification": "Export the next run as report JSON and compare session_duration_hours before adopting the workflow change.",
        }
    if driver == "Largest thread":
        current = float(summary.get("largest_thread_share_pct") or 0)
        target = _pct_target(current, 50.0, 35.0)
        return {
            "metric": "largest_thread_share_pct",
            "direction": "lower_is_better",
            "current_value": current,
            "target_value": target,
            "unit": "percent_of_run",
            "current": f"{current:.1f}%",
            "target": f"below {target:.1f}%",
            "rationale": "The top opportunity is a dominant thread; the next run should prove that work was split or stopped earlier.",
            "verification": "Export the next run as report JSON and compare largest_thread_share_pct before adopting the workflow change.",
        }
    if driver == "Repeated prompt blocks":
        current = float(summary.get("repeated_prompt_share_pct") or 0)
        target = _pct_target(current, 15.0, 8.0)
        return {
            "metric": "repeated_prompt_share_pct",
            "direction": "lower_is_better",
            "current_value": current,
            "target_value": target,
            "unit": "percent_of_run",
            "current": f"{current:.1f}%",
            "target": f"below {target:.1f}%",
            "rationale": "The top opportunity is replayed instructions; the next run should reduce repeated prompt share.",
            "verification": "Export the next run as report JSON and compare repeated_prompt_share_pct before adopting the workflow change.",
        }
    if driver == "Uncached input":
        current = float(summary.get("uncached_input_share_pct") or 0)
        target = _pct_target(current, 35.0, 20.0)
        return {
            "metric": "uncached_input_share_pct",
            "direction": "lower_is_better",
            "current_value": current,
            "target_value": target,
            "unit": "percent_of_run",
            "current": f"{current:.1f}%",
            "target": f"below {target:.1f}%",
            "rationale": "The top opportunity is fresh context cost; the next run should filter or summarize inputs earlier.",
            "verification": "Export the next run as report JSON and compare uncached_input_share_pct before adopting the workflow change.",
        }
    if driver == "Guardian overhead":
        current = float(summary.get("guardian_input_share_pct") or 0)
        target = _pct_target(current, 40.0, 25.0)
        return {
            "metric": "guardian_input_share_pct",
            "direction": "lower_is_better",
            "current_value": current,
            "target_value": target,
            "unit": "percent_of_run",
            "current": f"{current:.1f}%",
            "target": f"below {target:.1f}%",
            "rationale": "The top opportunity is approval context replay; the next run should keep guardian checks narrow and checkpoint before approvals repeat.",
            "verification": "Export the next run as report JSON and compare guardian_input_share_pct before adopting the workflow change.",
        }
    if driver == "Largest tool output":
        current = _safe_int(summary.get("largest_tool_output_chars"))
        target = 5_000 if current >= 5_000 else 2_000
        return {
            "metric": "largest_tool_output_chars",
            "direction": "lower_is_better",
            "current_value": current,
            "target_value": target,
            "unit": "chars",
            "current": f"{fmt_short(current)} chars",
            "target": f"below {fmt_short(target)} chars",
            "rationale": "The top opportunity is bulky tool output; the next run should narrow commands before output enters context.",
            "verification": "Export the next run as report JSON and compare largest_tool_output_chars before adopting the workflow change.",
        }
    if driver == "Context compaction":
        current = _safe_int(summary.get("compactions"))
        return {
            "metric": "compactions",
            "direction": "lower_is_better",
            "current_value": current,
            "target_value": 0,
            "unit": "events",
            "current": f"{current} event(s)",
            "target": "0 events",
            "rationale": "The top opportunity is compaction; the next run should create a handoff before context has to be rewritten.",
            "verification": "Export the next run as report JSON and compare compactions before adopting the workflow change.",
        }

    total = _safe_int(summary.get("total_tokens"))
    target = int(total * 0.9) if total else 0
    return {
        "metric": "total_tokens",
        "direction": "lower_is_better",
        "current_value": total,
        "target_value": target,
        "unit": "tokens",
        "current": f"{fmt_short(total)} tokens",
        "target": f"below {fmt_short(target)} tokens",
        "rationale": "No single opportunity dominates; use total tokens as the next-run guardrail.",
        "verification": "Export the next run as report JSON and compare total_tokens before adopting the workflow change.",
    }


def _risk_level(report: dict[str, Any]) -> str:

    triage = report.get("triage", {})
    risk = str(triage.get("risk_level") or "unknown")
    return risk if risk in RISK_RANK else "unknown"


def triage_risk_comparison(
    before_report: dict[str, Any], after_report: dict[str, Any]
) -> dict[str, str]:
    before = _risk_level(before_report)
    after = _risk_level(after_report)
    before_rank = RISK_RANK.get(before)
    after_rank = RISK_RANK.get(after)
    if before_rank is None or after_rank is None:
        direction = "unknown"
    elif after_rank < before_rank:
        direction = "improved"
    elif after_rank > before_rank:
        direction = "regressed"
    else:
        direction = "unchanged"
    return {"before": before, "after": after, "direction": direction}


def comparison_headline(comparison: dict[str, Any]) -> dict[str, str]:
    verdict = str(comparison.get("verdict") or "unknown")
    metrics = comparison.get("metrics", [])
    changed = [metric for metric in metrics if metric.get("direction") != "unchanged"]
    largest = max(
        changed or metrics, key=lambda m: abs(_safe_int(m.get("delta"))), default={}
    )
    label = str(largest.get("label") or "No metric")
    delta = fmt_short(largest.get("delta", 0))
    direction = str(largest.get("direction") or "unchanged")
    diagnostics = comparison.get("diagnostics", {})
    resolved = len(diagnostics.get("resolved", []))
    new = len(diagnostics.get("new", []))
    return {
        "headline": f"Verdict: {verdict}; largest change: {label} {delta} ({direction}).",
        "diagnostic_change": f"{resolved} resolved diagnostics; {new} new diagnostics.",
    }


def _largest_metric(
    metrics: list[dict[str, Any]], direction: str
) -> dict[str, Any] | None:
    matching = [metric for metric in metrics if metric.get("direction") == direction]
    if not matching:
        return None
    return max(matching, key=lambda metric: abs(_safe_int(metric.get("delta"))))


def comparison_recommendation(comparison: dict[str, Any]) -> str:
    verdict = str(comparison.get("verdict") or "unknown")
    diagnostics = comparison.get("diagnostics", {})
    new_diagnostics = diagnostics.get("new", []) or []
    persisted = diagnostics.get("persisted", []) or []
    metrics = comparison.get("metrics", [])
    largest_regression = _largest_metric(metrics, "regressed")
    largest_improvement = _largest_metric(metrics, "improved")

    if verdict == "regressed":
        if new_diagnostics:
            return f"Inspect new diagnostic first: {new_diagnostics[0]}."
        if largest_regression:
            return f"Inspect the largest regressed metric first: {largest_regression['label']}."
        return "Inspect the after-run report before adopting this workflow change."
    if verdict == "mixed":
        if largest_regression:
            return f"Keep the improved habits, but investigate {largest_regression['label']} before adopting the change."
        return "Review the metric deltas before adopting this workflow change."
    if verdict == "improved":
        if persisted:
            return f"Keep the change, then target persisted diagnostic: {persisted[0]}."
        if largest_improvement:
            return f"Keep the change; strongest improvement is {largest_improvement['label']}."
        return "Keep the change and compare another run to confirm the trend."
    return "No aggregate metric changed; compare against a different run or inspect the reports manually."


def comparison_recommendation_detail(comparison: dict[str, Any]) -> dict[str, Any]:
    verdict = str(comparison.get("verdict") or "unknown")
    diagnostics = comparison.get("diagnostics", {})
    new_diagnostics = diagnostics.get("new", []) or []
    persisted = diagnostics.get("persisted", []) or []
    metrics = comparison.get("metrics", [])
    largest_regression = _largest_metric(metrics, "regressed")
    largest_improvement = _largest_metric(metrics, "improved")

    if verdict == "regressed":
        if new_diagnostics:
            return {
                "action": "inspect_new_diagnostic",
                "target_type": "diagnostic",
                "target": new_diagnostics[0],
                "reason": "A new diagnostic appeared after the workflow change.",
            }
        if largest_regression:
            return {
                "action": "inspect_regressed_metric",
                "target_type": "metric",
                "target": largest_regression["label"],
                "reason": "This metric had the largest aggregate regression.",
            }
        return {
            "action": "inspect_after_report",
            "target_type": "report",
            "target": comparison.get("after", {}).get("session_id", "after run"),
            "reason": "The comparison regressed without a more specific aggregate target.",
        }
    if verdict == "mixed":
        if largest_regression:
            return {
                "action": "investigate_regressed_metric_before_adopting_change",
                "target_type": "metric",
                "target": largest_regression["label"],
                "reason": "The run improved in some areas but this metric regressed most.",
            }
        return {
            "action": "review_metric_deltas",
            "target_type": "comparison",
            "target": "metric deltas",
            "reason": "The comparison is mixed without one dominant regression.",
        }
    if verdict == "improved":
        if persisted:
            return {
                "action": "target_persisted_diagnostic",
                "target_type": "diagnostic",
                "target": persisted[0],
                "reason": "The workflow improved, but this diagnostic still appears.",
            }
        if largest_improvement:
            return {
                "action": "keep_change_and_confirm_improvement",
                "target_type": "metric",
                "target": largest_improvement["label"],
                "reason": "This metric had the strongest aggregate improvement.",
            }
        return {
            "action": "compare_another_run",
            "target_type": "comparison",
            "target": "another run",
            "reason": "The workflow improved; another comparison can confirm the trend.",
        }
    return {
        "action": "compare_different_run",
        "target_type": "comparison",
        "target": "different run",
        "reason": "No aggregate metric changed in this comparison.",
    }


def comparison_next_command_templates(comparison: dict[str, Any]) -> list[str]:
    after = comparison.get("after", {})
    after_session = "<after-session-id>"
    if isinstance(after, dict) and after.get("session_id"):
        after_session = str(after["session_id"])
    return [
        "codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json",
        "codex-observe compare --before-report <after-report.json> --after-report next-run-report.json --out next-run-comparison.md",
        "codex-observe compare --before-session "
        f"{after_session} --after-session <next-session-id> --db <db> --out next-run-comparison.md",
    ]


def comparison_review_path(comparison: dict[str, Any]) -> list[dict[str, str]]:
    verdict = str(comparison.get("verdict") or "unknown")
    recommendation = str(
        comparison.get("recommendation") or "Inspect the reports manually."
    )
    templates = comparison_next_command_templates(comparison)
    return [
        {
            "label": "Read the verdict",
            "command": "Review Quick Read, Triage Risk, Opportunity Change, and Metric Deltas.",
            "success_check": f"Verdict is {verdict} and the recommendation is understood before changing workflow.",
        },
        {
            "label": "Act on the recommendation",
            "command": recommendation,
            "success_check": "The next workflow change targets the recommended diagnostic, metric, or validation step.",
        },
        {
            "label": "Export the next run",
            "command": templates[0],
            "success_check": "next-run-report.json uses codex-observe.report.v1 and aggregate-only privacy mode.",
        },
        {
            "label": "Compare against this after run",
            "command": templates[1],
            "success_check": "next-run-comparison.md shows verdict, opportunity change, triage movement, and metric deltas.",
        },
        {
            "label": "File safe feedback",
            "command": "docs/PUBLIC_TOUR_FEEDBACK.md",
            "success_check": "Feedback excludes private prompts, tool output, local paths, and raw logs.",
        },
    ]


OPPORTUNITY_METRIC_BY_DRIVER = {
    "Largest thread": "largest_thread_tokens",
    "Repeated prompt blocks": "repeated_prompt_tokens",
    "Uncached input": "uncached_input_tokens",
    "Largest tool output": "largest_tool_output_chars",
    "Context compaction": "compactions",
}


def _top_opportunity_from_summary(summary: dict[str, Any]) -> dict[str, Any] | None:
    opportunities = opportunity_df(summary, limit=1).to_dict("records")
    if not opportunities:
        return None
    row = opportunities[0]
    return {
        "driver": str(row.get("Driver") or "unknown"),
        "habit": str(row.get("Habit") or "Inspect the report"),
        "scale": str(row.get("Scale") or "unknown"),
    }


def opportunity_change_comparison(
    before_summary: dict[str, Any],
    after_summary: dict[str, Any],
    metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    before_top = _top_opportunity_from_summary(before_summary)
    after_top = _top_opportunity_from_summary(after_summary)
    if not before_top and not after_top:
        return {
            "before": None,
            "after": None,
            "direction": "unknown",
            "summary": "No aggregate opportunity stack is available for either run.",
        }
    if not before_top:
        return {
            "before": None,
            "after": after_top,
            "direction": "new",
            "summary": f"Top opportunity appeared after the change: {after_top['driver']}.",
        }
    if not after_top:
        return {
            "before": before_top,
            "after": None,
            "direction": "resolved",
            "summary": f"Top opportunity resolved after the change: {before_top['driver']}.",
        }

    before_driver = before_top["driver"]
    after_driver = after_top["driver"]
    if before_driver != after_driver:
        return {
            "before": before_top,
            "after": after_top,
            "direction": "shifted",
            "summary": f"Top opportunity shifted from {before_driver} to {after_driver}.",
        }

    metric_name = OPPORTUNITY_METRIC_BY_DRIVER.get(before_driver)
    direction = "unknown"
    if metric_name:
        direction = next(
            (
                str(metric.get("direction") or "unknown")
                for metric in metrics
                if metric.get("metric") == metric_name
            ),
            "unknown",
        )
    return {
        "before": before_top,
        "after": after_top,
        "direction": direction,
        "summary": f"Top opportunity stayed {before_driver} and {direction}: {before_top['scale']} -> {after_top['scale']}.",
    }


def compare_reports(
    before_report: dict[str, Any], after_report: dict[str, Any]
) -> dict[str, Any]:
    before_summary = before_report.get("summary", {})
    after_summary = after_report.get("summary", {})
    metrics = [
        _metric_delta(before_summary, after_summary, "total_tokens", "Total tokens"),
        _metric_delta(
            before_summary,
            after_summary,
            "usage_snapshots",
            "Usage snapshots",
            direction_mode="neutral",
        ),
        _metric_delta(
            before_summary,
            after_summary,
            "uncached_input_tokens",
            "Uncached input tokens",
        ),
        _metric_delta(
            before_summary,
            after_summary,
            "largest_thread_tokens",
            "Largest thread tokens",
        ),
        _metric_delta(
            before_summary,
            after_summary,
            "repeated_prompt_tokens",
            "Repeated prompt tokens",
        ),
        _metric_delta(
            before_summary,
            after_summary,
            "largest_tool_output_chars",
            "Largest tool output chars",
        ),
        _metric_delta(before_summary, after_summary, "tool_calls", "Tool calls"),
        _metric_delta(before_summary, after_summary, "compactions", "Compactions"),
    ]
    improved = sum(1 for metric in metrics if metric["direction"] == "improved")
    regressed = sum(1 for metric in metrics if metric["direction"] == "regressed")
    if regressed and not improved:
        verdict = "regressed"
    elif improved and not regressed:
        verdict = "improved"
    elif improved or regressed:
        verdict = "mixed"
    else:
        verdict = "unchanged"

    before_diagnostics_ordered = _diagnostic_names_ordered(before_report)
    after_diagnostics_ordered = _diagnostic_names_ordered(after_report)
    before_diagnostics = set(before_diagnostics_ordered)
    after_diagnostics = set(after_diagnostics_ordered)
    comparison = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "privacy": {
            "mode": "aggregate-only",
            "excluded": [
                "message text",
                "prompt block previews",
                "event payload JSON",
                "tool arguments",
                "tool commands",
                "tool output",
            ],
        },
        "before": before_report.get("session", {}),
        "after": after_report.get("session", {}),
        "verdict": verdict,
        "metrics": metrics,
        "triage_risk": triage_risk_comparison(before_report, after_report),
        "opportunity_change": opportunity_change_comparison(
            before_summary, after_summary, metrics
        ),
        "diagnostics": {
            "before": before_diagnostics_ordered,
            "after": after_diagnostics_ordered,
            "resolved": [
                name
                for name in before_diagnostics_ordered
                if name not in after_diagnostics
            ],
            "new": [
                name
                for name in after_diagnostics_ordered
                if name not in before_diagnostics
            ],
            "persisted": [
                name for name in after_diagnostics_ordered if name in before_diagnostics
            ],
        },
    }
    comparison["ingest_scope"] = comparison_ingest_scope(before_report, after_report)
    comparison["headline"] = comparison_headline(comparison)
    comparison["recommendation_detail"] = comparison_recommendation_detail(comparison)
    comparison["recommendation"] = comparison_recommendation(comparison)
    comparison["next_command_templates"] = comparison_next_command_templates(comparison)
    comparison["review_path"] = comparison_review_path(comparison)
    comparison["feedback_handoff"] = aggregate_feedback_handoff()
    return comparison


def comparison_ingest_scope(
    before_report: dict[str, Any], after_report: dict[str, Any]
) -> dict[str, Any] | None:
    before_scope = before_report.get("ingest_scope")
    after_scope = after_report.get("ingest_scope")
    if not isinstance(before_scope, dict) and not isinstance(after_scope, dict):
        return None

    before_sampled = (
        isinstance(before_scope, dict) and before_scope.get("sampled") is True
    )
    after_sampled = isinstance(after_scope, dict) and after_scope.get("sampled") is True
    sampled = before_sampled or after_sampled
    warning = None
    sampled_scope = None
    if sampled:
        warning = (
            "Sampled ingest: at least one comparison input came from a bounded "
            "newest-file sample; treat comparison deltas as sampled evidence."
        )
        for candidate in [after_scope, before_scope]:
            if isinstance(candidate, dict) and candidate.get("sampled") is True:
                sampled_scope = candidate
                break
    scope = {
        "before": before_scope if isinstance(before_scope, dict) else None,
        "after": after_scope if isinstance(after_scope, dict) else None,
        "sampled": sampled,
        "warning": warning,
    }
    if isinstance(sampled_scope, dict):
        for key in ["counts", "scan_limit", "skipped"]:
            value = sampled_scope.get(key)
            if isinstance(value, dict):
                scope[key] = value
    return scope


def comparison_ingest_scope_markdown_lines(scope: object) -> list[str]:
    if not isinstance(scope, dict):
        return []
    warning = scope.get("warning")
    if not isinstance(warning, str) or not warning:
        return []
    return ["## Ingest Scope", "", f"- {warning}", ""]


def load_report_json(path: str) -> dict[str, Any]:
    report_path = Path(path).expanduser()
    if not report_path.exists():
        raise FileNotFoundError(str(report_path))
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or "summary" not in payload
        or "session" not in payload
    ):
        raise ValueError(f"not a Codex Observe report JSON file: {report_path}")
    schema_version = payload.get("schema_version")
    if schema_version != REPORT_SCHEMA_VERSION:
        raise ValueError(
            "unsupported Codex Observe report JSON schema: "
            f"{schema_version or 'missing'}; expected {REPORT_SCHEMA_VERSION}: "
            f"{report_path}"
        )
    return payload


def comparison_markdown(comparison: dict[str, Any]) -> str:
    before = comparison.get("before", {})
    after = comparison.get("after", {})
    lines = [
        "# Codex Observe Run Comparison",
        "",
        "Privacy: aggregate-only comparison. Message text, prompt block previews, event payload JSON, tool arguments, tool commands, and tool output are excluded.",
        "",
        *comparison_ingest_scope_markdown_lines(comparison.get("ingest_scope")),
        "## Sessions",
        "",
        f"- Before: `{before.get('session_id', 'unknown')}`",
        f"- After: `{after.get('session_id', 'unknown')}`",
        f"- Verdict: {comparison.get('verdict', 'unknown')}",
        "",
        "## Quick Read",
        "",
        f"- {comparison.get('headline', {}).get('headline', 'No headline available.')}",
        f"- {comparison.get('headline', {}).get('diagnostic_change', 'No diagnostic change summary available.')}",
        f"- Recommended next step: {comparison.get('recommendation', 'Inspect the reports manually.')}",
        "",
        "## Recommended Action",
        "",
        f"- Recommendation: {comparison.get('recommendation', 'Inspect the reports manually.')}",
        *_action_detail_lines(comparison.get("recommendation_detail")),
        "",
        "## Review Path",
        "",
    ]
    review_path = comparison.get("review_path", [])
    if review_path:
        for index, step in enumerate(review_path, start=1):
            if not isinstance(step, dict):
                continue
            label = str(step.get("label") or f"Step {index}")
            command = str(step.get("command") or "")
            success_check = str(step.get("success_check") or "Confirm the result.")
            lines.extend(
                [
                    f"{index}. **{label}**",
                    f"   Command: `{command}`",
                    f"   Success check: {success_check}",
                    "",
                ]
            )
    else:
        lines.append(
            "- Export the next run as report JSON and compare it against the after report."
        )
        lines.append("")

    lines.extend(feedback_handoff_markdown_lines(comparison.get("feedback_handoff")))

    lines.extend(["## Follow-up Commands", ""])
    templates = comparison.get("next_command_templates", [])
    if templates:
        lines.extend(f"- `{command}`" for command in templates)
    else:
        lines.append(
            "- Export the next run as report JSON and compare it against the after report."
        )
    lines.extend(
        [
            "",
            "## Triage Risk",
            "",
            f"- Before: {comparison.get('triage_risk', {}).get('before', 'unknown')}",
            f"- After: {comparison.get('triage_risk', {}).get('after', 'unknown')}",
            f"- Direction: {comparison.get('triage_risk', {}).get('direction', 'unknown')}",
            "",
            "## Opportunity Change",
            "",
            f"- Direction: {comparison.get('opportunity_change', {}).get('direction', 'unknown')}",
            f"- Summary: {comparison.get('opportunity_change', {}).get('summary', 'No opportunity change summary available.')}",
            "",
            "## Metric Deltas",
            "",
            "| Metric | Before | After | Delta | % change | Direction |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for metric in comparison.get("metrics", []):
        delta_pct = metric.get("delta_pct")
        delta_pct_label = "n/a" if delta_pct is None else f"{delta_pct:+.1f}%"
        lines.append(
            "| {label} | {before} | {after} | {delta} | {delta_pct} | {direction} |".format(
                label=metric["label"],
                before=fmt_short(metric["before"]),
                after=fmt_short(metric["after"]),
                delta=fmt_short(metric["delta"]),
                delta_pct=delta_pct_label,
                direction=metric["direction"],
            )
        )

    diagnostics = comparison.get("diagnostics", {})
    lines.extend(
        [
            "",
            "## Diagnostic Changes",
            "",
            "- Resolved: " + (", ".join(diagnostics.get("resolved", [])) or "none"),
            "- New: " + (", ".join(diagnostics.get("new", [])) or "none"),
            "- Persisted: " + (", ".join(diagnostics.get("persisted", [])) or "none"),
            "",
        ]
    )
    return "\n".join(lines)


def next_run_brief_markdown_lines(brief: object) -> list[str]:
    if not isinstance(brief, dict):
        return []
    prompt = str(brief.get("copy_prompt") or "").strip()
    if not prompt:
        return []
    return [
        "## Next Run Brief",
        "",
        "Use this aggregate-only brief to plan the next Codex run:",
        "",
        "```text",
        prompt,
        "```",
        "",
    ]


def _action_detail_lines(detail: object) -> list[str]:
    if not isinstance(detail, dict):
        return []
    lines: list[str] = []
    action = str(detail.get("action") or "").replace("_", " ").strip()
    target_type = str(detail.get("target_type") or "target").replace("_", " ").strip()
    target = str(detail.get("target") or "").strip()
    reason = str(detail.get("reason") or detail.get("impact") or "").strip()
    source = str(detail.get("source") or "").strip()
    if action:
        lines.append(f"- Action: {action}")
    if target:
        lines.append(f"- Target: {target_type}: {target}")
    if reason:
        lines.append(f"- Why: {reason}")
    if source:
        lines.append(f"- Evidence: {source}")
    return lines


def comparison_json(comparison: dict[str, Any]) -> str:
    return json.dumps(comparison, indent=2, sort_keys=True)


def report_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    session = report["session"]
    success_target = report.get("success_target", {})
    lines = [
        "# Codex Observe Run Report",
        "",
        "Privacy: aggregate-only export. Message text, prompt block previews, event payload JSON, tool arguments, tool commands, and tool output are excluded.",
        "",
        *ingest_scope_markdown_lines(report.get("ingest_scope")),
        "## Session",
        "",
        f"- Session: `{session['session_id']}`",
        f"- First seen: {session.get('first_seen') or 'unknown'}",
        f"- Last seen: {session.get('last_seen') or 'unknown'}",
        "",
        "## Quick Read",
        "",
        f"- {report.get('headline', {}).get('headline', 'No headline available.')}",
        f"- Top diagnostic: {report.get('headline', {}).get('top_diagnostic', 'none')}",
        f"- Recommended next habit: {report.get('headline', {}).get('recommendation', 'none')}",
        "",
        "## Recommended Action",
        "",
        *_action_detail_lines(report.get("next_action_detail")),
        f"- Verify: {success_target.get('verification', 'Export the next run as report JSON and compare the target metric.')}",
        "",
        "## Triage",
        "",
        f"- Risk level: {report.get('triage', {}).get('risk_level', 'unknown')}",
        f"- Primary driver: {report.get('triage', {}).get('primary_driver', 'none')}",
        f"- Next action: {report.get('triage', {}).get('next_action', 'none')}",
    ]
    for reason in report.get("triage", {}).get("reasons", []):
        lines.append(f"- Why: {reason}")

    lines.extend(
        [
            "",
            "## Next Run Success Target",
            "",
            f"- Metric: {success_target.get('metric', 'total_tokens')}",
            f"- Current: {success_target.get('current', 'unknown')}",
            f"- Target: {success_target.get('target', 'unknown')}",
            f"- Why: {success_target.get('rationale', 'Use the next run to validate the recommended habit.')}",
            f"- Verify: {success_target.get('verification', 'Export the next run as report JSON and compare the target metric.')}",
            "",
            "## Summary",
            "",
            f"- Threads: {summary['threads']} ({summary['workers']} workers, {summary['explorers']} explorers, {summary['guardians']} guardians)",
            f"- Tool calls: {summary['tool_calls']}",
            f"- Usage snapshots: {fmt_short(summary.get('usage_snapshots', 0))}",
            f"- Compactions: {summary['compactions']}",
            f"- Total tokens: {fmt_short(summary['total_tokens'])}",
            f"- Input tokens: {fmt_short(summary['input_tokens'])} ({fmt_short(summary['uncached_input_tokens'])} uncached, {summary['cache_pct']:.1f}% cache hit)",
            f"- Guardian input tokens: {fmt_short(summary.get('guardian_input_tokens', 0))}",
            f"- Largest thread: {fmt_short(summary['largest_thread_tokens'])} tokens ({summary['largest_thread_kind'] or 'unknown'})",
            f"- Repeated prompt tokens: {fmt_short(summary.get('repeated_prompt_tokens', 0))}",
            f"- Largest tool output: {fmt_short(summary.get('largest_tool_output_chars', 0))} chars",
            "",
            "## Cost Profile",
            "",
            f"- Largest thread share: {summary.get('largest_thread_share_pct', 0):.1f}% of total tokens",
            f"- Repeated prompt share: {summary.get('repeated_prompt_share_pct', 0):.1f}% of total tokens",
            f"- Uncached input share: {summary.get('uncached_input_share_pct', 0):.1f}% of total tokens",
            f"- Guardian input share: {summary.get('guardian_input_share_pct', 0):.1f}% of total tokens",
            "",
            "## Opportunity Stack",
            "",
        ]
    )
    for row in report.get("opportunities", []):
        lines.extend(
            [
                f"{row['Rank']}. **{row['Habit']}**",
                f"   Driver: {row['Driver']}",
                f"   Scale: {row['Scale']}",
                f"   Why: {row['Why']}",
                "",
            ]
        )
    if not report.get("opportunities"):
        lines.extend(["No opportunity items available.", ""])

    lines.extend(
        [
            "## What To Inspect First",
            "",
        ]
    )
    for row in report["diagnostics"]:
        lines.extend(
            [
                f"### {row['Diagnostic']} ({row['Priority']})",
                "",
                f"- Action: {row['Action']}",
                f"- Evidence: {row['Evidence']}",
                "",
            ]
        )
    if not report["diagnostics"]:
        lines.extend(["No diagnostics available.", ""])

    lines.extend(["## Next Run Playbook", ""])
    for row in report["playbook"]:
        lines.extend(
            [
                f"{row['Step']}. **{row['Habit']}**",
                f"   Impact: {row.get('Impact', 'Targets the top diagnostic.')}",
                f"   {row['Why']}",
                f"   Source: {row['Source']}",
                "",
            ]
        )
    if not report["playbook"]:
        lines.extend(["No playbook items available.", ""])

    lines.extend(next_run_brief_markdown_lines(report.get("next_run_brief")))

    checklist = report.get("next_run_checklist", [])
    if checklist:
        lines.extend(["## Next Run Checklist", ""])
        for index, step in enumerate(checklist, start=1):
            if not isinstance(step, dict):
                continue
            phase = str(step.get("phase") or f"Step {index}")
            action = str(step.get("action") or "Review the report.")
            success_check = str(step.get("success_check") or "Confirm the result.")
            lines.extend(
                [
                    f"{index}. **{phase}**",
                    f"   Action: {action}",
                    f"   Success check: {success_check}",
                    "",
                ]
            )

    review_path = report.get("review_path", [])
    if review_path:
        lines.extend(["## Review Path", ""])
        for index, step in enumerate(review_path, start=1):
            if not isinstance(step, dict):
                continue
            label = str(step.get("label") or f"Step {index}")
            command = str(step.get("command") or "")
            success_check = str(step.get("success_check") or "Confirm the result.")
            lines.extend(
                [
                    f"{index}. **{label}**",
                    f"   Command: `{command}`",
                    f"   Success check: {success_check}",
                    "",
                ]
            )

    lines.extend(feedback_handoff_markdown_lines(report.get("feedback_handoff")))

    lines.extend(["## Follow-up Commands", ""])
    for command in report.get("next_commands", []):
        lines.extend(["```bash", str(command), "```", ""])
    templates = report.get("next_command_templates", [])
    if templates:
        lines.extend(
            [
                "After the next run, replace `<next-session-id>` with the selected session from `codex-observe sessions`:",
                "",
            ]
        )
        for command in templates:
            lines.extend(["```bash", str(command), "```", ""])
    if not report.get("next_commands") and not templates:
        lines.extend(["No follow-up commands available.", ""])

    lines.extend(["## Findings", ""])
    for row in report["findings"]:
        lines.extend(
            [
                f"- **{row['Finding']}**: {row['Why it matters']} Evidence: {row['Evidence']}",
            ]
        )
    if not report["findings"]:
        lines.append("- No findings available.")
    lines.append("")
    return "\n".join(lines)


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True)
