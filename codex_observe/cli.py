from __future__ import annotations

import argparse
import importlib.util
import textwrap
import json
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__
from .analysis import fmt_short
from .demo import DEFAULT_DEMO_DB, DEFAULT_DEMO_SESSIONS, create_demo_database
from .parser import ingest
from .report import (
    COMPARISON_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    build_report,
    compare_reports,
    comparison_json,
    comparison_markdown,
    load_report_json,
    latest_ingest_scope,
    report_json,
    report_markdown,
    session_report_hint,
    session_risk_distribution,
    session_summaries,
    session_success_target_preview,
    session_summary_lines,
    session_validation_commands,
)


VISUAL_MANIFEST = Path(".artifacts/visual/visual-qa-manifest.json")
VISUAL_MANIFEST_SCHEMA_VERSION = "codex-observe.visual-manifest.v1"
VISUAL_MANIFEST_RECOVERY = (
    "run `python scripts/visual_qa.py`, then "
    f"`python scripts/visual_qa.py --verify-manifest {VISUAL_MANIFEST.as_posix()}`"
)
EXPECTED_VISUAL_RISK_LABELS = {"High risk", "Low risk"}
EXPECTED_VISUAL_SIDEBAR_SESSION_DETAILS = {"6 snapshots"}
EXPECTED_VISUAL_DOWNLOAD_CONTROLS = {
    "Download report MD",
    "Download report JSON",
    "Download comparison MD",
    "Download comparison JSON",
}
EXPECTED_VISUAL_COMPARISON_PREVIEW = {
    "Comparison quick read",
    "regressed",
    "Triage movement: regressed",
    "Inspect new diagnostic first: Repeated prompt blocks.",
    "Next validation command",
    "codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json",
}
EXPECTED_VISUAL_COMPARISON_DELTAS = {
    "Total tokens": "regressed",
    "Usage snapshots": "changed",
    "Largest thread tokens": "regressed",
}
EXPECTED_VISUAL_COMPARISON_REVIEW_PATH = {
    "Comparison review path",
    "Read the verdict",
    "Act on the recommendation",
    "Export the next run",
    "Compare against this after run",
    "File safe feedback",
}
EXPECTED_VISUAL_RISK_DISTRIBUTION = {
    "Risk distribution",
    "High risk",
    "Low risk",
    "2 imported conversations",
}

EXPECTED_VISUAL_METRICS = {
    "Threads": "3",
    "Largest thread": "33.2k tokens (57.7%)",
    "Uncached input": "22.7k tokens (39.5%)",
}
EXPECTED_VISUAL_SUCCESS_TARGET = {
    "metric": "largest_thread_share_pct",
    "current": "57.7%",
    "target": "below 50.0%",
}

EXPECTED_VISUAL_OPERATOR_BRIEFING = {
    "risk": "High risk",
    "best_habit": "Set a stop condition for the dominant thread",
    "scale": "33.2k tokens (57.7% of run)",
    "proof_target": "largest_thread_share_pct: 57.7% -> below 50.0%",
}
EXPECTED_VISUAL_REVIEW_PATH = {
    "Next review path",
    "Save report JSON",
    "Compare workflow change",
    "Validate next run",
    "File safe feedback",
    "PUBLIC_TOUR_FEEDBACK.md",
}
EXPECTED_VISUAL_NEXT_RUN_CHECKLIST = {
    "Next run checklist",
    "Before next run",
    "During next run",
    "After next run",
    "Set a stop condition for the dominant thread",
    "largest_thread_share_pct",
    "Export next-run-report.json",
}

EXPECTED_VISUAL_NEXT_RUN_BRIEF = {
    "Next run brief",
    "Next Codex run plan",
    "Set a stop condition for the dominant thread",
    "Largest thread drives the run",
    "largest_thread_share_pct: 57.7% -> below 50.0%",
    "Pause or split the run when the same aggregate driver starts to dominate.",
    "Copy prompt",
}

EXPECTED_VISUAL_FEEDBACK_HANDOFF = {
    "Safe feedback handoff",
    "docs/PUBLIC_TOUR_FEEDBACK.md",
    ".github/ISSUE_TEMPLATE/public_tour_feedback.yml",
    "synthetic or reviewed-redacted aggregate evidence",
    "codex-observe report JSON or Markdown",
    "private prompts",
    "Do not collect",
}

EXPECTED_VISUAL_TABS = [
    "Overview",
    "Agent detail",
    "Timeline & jumps",
    "Tools",
    "Duplication",
    "Raw tables",
]
EXPECTED_VISUAL_QUICK_READ_EVIDENCE = [
    {"tab": "Overview", "text": "Run triage"},
    {"tab": "Agent detail", "text": "Thread brief"},
    {"tab": "Timeline & jumps", "text": "Timeline quick read"},
    {"tab": "Tools", "text": "Tool quick read"},
    {"tab": "Duplication", "text": "Duplication quick read"},
    {"tab": "Raw tables", "text": "Data inventory"},
]
EXPECTED_TOUR_QUICK_READ_TEXT = [
    "Overview operator briefing",
    "Agent detail thread brief",
    "Timeline quick read",
    "Tools quick read",
    "Duplication quick read",
    "Raw tables data inventory",
]
EXPECTED_VISUAL_VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "narrow": {"width": 390, "height": 900},
}
EXPECTED_VISUAL_SCREENSHOTS = {
    "desktop": "dashboard-desktop.png",
    "narrow": "dashboard-narrow.png",
}
EXPECTED_VISUAL_EMPTY_STATES = {
    "missing_database": "No database found",
    "empty_database": "No conversations imported yet",
}
EXPECTED_VISUAL_EMPTY_STATE_COMMAND_LABELS = {
    "Try synthetic data",
    "Ingest private logs locally",
    "Check database health",
}
EXPECTED_VISUAL_EMPTY_STATE_COMMAND_SNIPPETS = {
    "codex-observe demo --serve --db",
    "codex-observe ingest ~/.codex/sessions --db",
    "codex-observe doctor --db",
}
SESSIONS_SCHEMA_VERSION = "codex-observe.sessions.v1"
DEFAULT_SESSIONS_LIMIT = 50


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


DOCTOR_SCHEMA_VERSION = "codex-observe.doctor.v1"
AUDIT_SCHEMA_VERSION = "codex-observe.audit.v1"
REPORT_FAILURE_SCHEMA_VERSION = "codex-observe.report-failure.v1"
COMPARISON_FAILURE_SCHEMA_VERSION = "codex-observe.comparison-failure.v1"
TOUR_SCHEMA_VERSION = "codex-observe.tour.v1"
DEMO_SCHEMA_VERSION = "codex-observe.demo.v1"
INGEST_SCHEMA_VERSION = "codex-observe.ingest.v1"
EVIDENCE_BUNDLE_SCHEMA_VERSION = "codex-observe.evidence-bundle.v1"
PATHS_SCHEMA_VERSION = "codex-observe.paths.v1"
PRIVATE_VALIDATE_SCHEMA_VERSION = "codex-observe.private-validate.v1"
SELF_CHECK_SCHEMA_VERSION = "codex-observe.self-check.v1"
RELEASE_REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "docs/RELEASE.md",
    "docs/DISTRIBUTION.md",
    "docs/LIMITATIONS.md",
    "docs/PUBLIC_TOUR_FEEDBACK.md",
    "docs/CURRENT.md",
    "docs/TRACKING.md",
    ".github/workflows/ci.yml",
]

RELEASE_REQUIRED_COMMANDS = [
    "ruff check",
    "ruff format --check",
    "pytest -q",
    "codex-observe self-check --json",
    "codex-observe paths --json",
    "python scripts/clean_install_smoke.py --extra dev",
    "codex-observe demo --sessions .artifacts/demo/sessions --keep-sessions --json",
    "codex-observe ingest .artifacts/demo/sessions --db .artifacts/demo/ingest-contract.sqlite --json",
    "python scripts/visual_qa.py",
    "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json",
    "codex-observe evidence-bundle --out .artifacts/public-evidence",
    "codex-observe audit --json",
]

BACKLOG_DRAFT_DIR = Path(".github/backlog")
RETIRED_BACKLOG_DRAFTS = {
    ".github/backlog/001-first-run-demo.md",
    ".github/backlog/002-diagnostics-summary.md",
    ".github/backlog/003-visual-regression.md",
    ".github/backlog/004-log-shape-resilience.md",
    ".github/backlog/005-package-for-real-users.md",
    ".github/backlog/006-release-candidate-ux-evidence.md",
    ".github/backlog/007-real-log-parser-feedback-loop.md",
    ".github/backlog/008-public-readme-tour.md",
    ".github/backlog/009-public-evidence-bundle.md",
}
BACKLOG_FORBIDDEN_PATTERNS = [
    r"sample_from_uploaded\.sqlite",
    r"\.codex[\\/]+sessions",
    r"synthetic output line",
    r"Analyze why this Codex run",
]
DOCTOR_TABLES = [
    "files",
    "conversations",
    "threads",
    "events",
    "usage_snapshots",
    "tool_calls",
    "messages",
    "prompt_blocks",
]


def doctor_next_commands(db: Path, status: str) -> list[str]:
    db_arg = _command_arg(db)
    if status == "ok":
        return [
            f"codex-observe sessions --db {db_arg}",
            f"codex-observe serve --db {db_arg}",
        ]
    if status == "empty":
        return [
            f"codex-observe ingest ~/.codex/sessions --db {db_arg}",
            f"codex-observe demo --db {db_arg}",
        ]
    if status in {"missing", "invalid schema"}:
        return [
            f"codex-observe demo --db {db_arg}",
            f"codex-observe ingest ~/.codex/sessions --db {db_arg}",
        ]
    if status == "unreadable":
        return [f"codex-observe demo --db {db_arg}"]
    return []


def sampled_ingest_next_command(scope: dict[str, object], db_path: Path | str) -> str:
    counts = scope.get("counts")
    scan_limit = scope.get("scan_limit")
    if not isinstance(counts, dict) or not isinstance(scan_limit, dict):
        return f"codex-observe ingest ~/.codex/sessions --db {_command_arg(db_path)}"
    matched = int(counts.get("files_matched") or 0)
    seen = int(counts.get("files_seen") or 0)
    newest_files = int(scan_limit.get("newest_files") or seen or 1)
    next_limit = min(matched, max(newest_files + 1, newest_files * 2))
    if matched and next_limit > newest_files:
        return (
            "codex-observe ingest ~/.codex/sessions "
            f"--newest-files {next_limit} --db {_command_arg(db_path)}"
        )
    return f"codex-observe ingest ~/.codex/sessions --db {_command_arg(db_path)}"


def ingest_scope_lines(scope: object, db_path: Path | str | None = None) -> list[str]:
    if not isinstance(scope, dict):
        return []
    lines = []
    warning = scope.get("warning")
    if isinstance(warning, str) and warning:
        lines.append(f"Ingest scope: {warning}")
    if scope.get("sampled") is not True:
        return lines
    counts = scope.get("counts")
    if isinstance(counts, dict):
        matched = int(counts.get("files_matched") or 0)
        seen = int(counts.get("files_seen") or 0)
        deferred = int(counts.get("files_skipped_by_limit") or 0)
        coverage = round(seen / matched * 100, 1) if matched > 0 else 0.0
        lines.append(
            "Sample coverage: "
            f"{seen} of {matched} matched files processed ({coverage:.1f}%); "
            f"{deferred} deferred."
        )
    if db_path is not None:
        lines.append(
            f"Next sample command: {sampled_ingest_next_command(scope, db_path)}"
        )
    return lines


def doctor_review_path(db: Path, status: str) -> list[dict[str, str]]:
    db_arg = _command_arg(db)
    if status == "ok":
        return [
            {
                "label": "Choose a reportable run",
                "command": f"codex-observe sessions --db {db_arg} --json",
                "success_check": "sessions JSON includes status ok and a recommended_session.",
            },
            {
                "label": "Open the dashboard",
                "command": f"codex-observe serve --db {db_arg}",
                "success_check": "dashboard opens without a missing-database or empty-database state.",
            },
            {
                "label": "Export the recommended report",
                "command": f"codex-observe report --db {db_arg} --out run-report.md",
                "success_check": "report output includes Recommended Action and Next Run Success Target.",
            },
        ]
    if status == "empty":
        return [
            {
                "label": "Ingest local logs",
                "command": f"codex-observe ingest ~/.codex/sessions --db {db_arg}",
                "success_check": "doctor reports a populated ok database after ingest.",
            },
            {
                "label": "Try synthetic data",
                "command": f"codex-observe demo --db {db_arg}",
                "success_check": "demo creates reportable synthetic conversations.",
            },
        ]
    if status in {"missing", "invalid schema"}:
        return [
            {
                "label": "Create synthetic database",
                "command": f"codex-observe demo --db {db_arg}",
                "success_check": "doctor reports status ok for the generated demo database.",
            },
            {
                "label": "Ingest local logs",
                "command": f"codex-observe ingest ~/.codex/sessions --db {db_arg}",
                "success_check": "ingest summary reports imported files, threads, and events.",
            },
        ]
    if status == "unreadable":
        return [
            {
                "label": "Regenerate synthetic database",
                "command": f"codex-observe demo --db {db_arg}",
                "success_check": "new demo database can be opened by doctor.",
            }
        ]
    return []


def doctor_report(db_path: str) -> tuple[int, dict]:
    db = Path(db_path).expanduser()
    report = {
        "schema_version": DOCTOR_SCHEMA_VERSION,
        "database": str(db),
        "status": "ok",
        "tables": {},
        "totals": {
            "total_tokens": 0,
            "uncached_input_tokens": 0,
            "cached_input_tokens": 0,
        },
        "missing_tables": [],
        "next": "run `codex-observe serve --db <this-db>` to inspect the dashboard.",
        "next_commands": [],
        "review_path": [],
        "ingest_scope": None,
    }
    if not db.exists():
        report.update(
            {
                "status": "missing",
                "next_commands": doctor_next_commands(db, "missing"),
                "review_path": doctor_review_path(db, "missing"),
                "next": (
                    f"run `codex-observe demo --db {_command_arg(db)}` for synthetic data or "
                    f"`codex-observe ingest ~/.codex/sessions --db {_command_arg(db)}` for your logs."
                ),
            }
        )
        return 2, report

    try:
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            existing = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            missing = [table for table in DOCTOR_TABLES if table not in existing]
            if missing:
                report.update(
                    {
                        "status": "invalid schema",
                        "missing_tables": missing,
                        "next_commands": doctor_next_commands(db, "invalid schema"),
                        "review_path": doctor_review_path(db, "invalid schema"),
                        "next": (
                            "this file does not look like a Codex Observe database; "
                            f"run `codex-observe demo --db {_command_arg(db)}` for synthetic data "
                            f"or `codex-observe ingest ~/.codex/sessions --db {_command_arg(db)}` after moving this file aside."
                        ),
                    }
                )
                return 1, report

            counts = {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in DOCTOR_TABLES
            }
            totals = conn.execute(
                """
                SELECT
                  COALESCE(SUM(total_tokens), 0) AS total_tokens,
                  COALESCE(SUM(total_uncached_input_tokens), 0) AS uncached_input,
                  COALESCE(SUM(total_cached_input_tokens), 0) AS cached_input
                FROM conversations
                """
            ).fetchone()
    except sqlite3.DatabaseError as exc:
        report.update(
            {
                "status": "unreadable",
                "error": str(exc),
                "next_commands": doctor_next_commands(db, "unreadable"),
                "review_path": doctor_review_path(db, "unreadable"),
                "next": (
                    "check the database path or regenerate it with "
                    f"`codex-observe demo --db {_command_arg(db)}`."
                ),
            }
        )
        return 1, report

    report["tables"] = counts
    report["ingest_scope"] = latest_ingest_scope(db)
    report["totals"] = {
        "total_tokens": int(totals["total_tokens"]),
        "uncached_input_tokens": int(totals["uncached_input"]),
        "cached_input_tokens": int(totals["cached_input"]),
    }
    if counts["conversations"] == 0:
        report["next"] = (
            f"no conversations found; run `codex-observe ingest ~/.codex/sessions --db {_command_arg(db)}` "
            f"or `codex-observe demo --db {_command_arg(db)}`."
        )
        report["next_commands"] = doctor_next_commands(db, "empty")
        report["review_path"] = doctor_review_path(db, "empty")
    else:
        report["next"] = (
            f"run `codex-observe sessions --db {_command_arg(db)}` to choose a reportable conversation, "
            f"or `codex-observe serve --db {_command_arg(db)}` to inspect the dashboard."
        )
        report["next_commands"] = doctor_next_commands(db, "ok")
        report["review_path"] = doctor_review_path(db, "ok")
    return 0, report


def doctor_lines(db_path: str) -> tuple[int, list[str]]:
    status, report = doctor_report(db_path)
    lines = [f"Database: {report['database']}", f"Status: {report['status']}"]
    if report["status"] == "invalid schema":
        lines.append("Missing tables: " + ", ".join(report["missing_tables"]))
    if report["status"] == "unreadable" and report.get("error"):
        lines.append(f"SQLite error: {report['error']}")
    if report["status"] == "ok":
        for table in DOCTOR_TABLES:
            lines.append(f"{table}: {report['tables'][table]}")
        lines.extend(ingest_scope_lines(report.get("ingest_scope"), db_path))
        lines.extend(
            [
                f"total_tokens: {report['totals']['total_tokens']}",
                f"uncached_input_tokens: {report['totals']['uncached_input_tokens']}",
                f"cached_input_tokens: {report['totals']['cached_input_tokens']}",
            ]
        )
    review_path = report.get("review_path")
    if isinstance(review_path, list) and review_path:
        lines.append("Review path:")
        for item in review_path:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('label')}: {item.get('command')}")
            lines.append(f"  Success check: {item.get('success_check')}")
    next_commands = report.get("next_commands")
    if isinstance(next_commands, list) and next_commands:
        lines.append("Next commands:")
        for command in next_commands:
            lines.append(f"- {command}")
    lines.append(f"Next: {report['next']}")
    return status, lines


def pyproject_version(root: Path | None = None) -> str:
    root = root or Path.cwd()
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return ""
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version ="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def active_backlog_drafts(root: Path | None = None) -> list[Path]:
    root = root or Path.cwd()
    draft_dir = root / BACKLOG_DRAFT_DIR
    if not draft_dir.exists():
        return []
    return [
        path
        for path in sorted(draft_dir.glob("*.md"))
        if path.relative_to(root).as_posix() not in RETIRED_BACKLOG_DRAFTS
    ]


def backlog_draft_failures(root: Path | None = None) -> list[str]:
    root = root or Path.cwd()
    failures: list[str] = []
    backlog_path = root / "docs/BACKLOG.md"
    next_wave_path = root / "docs/NEXT_WAVE.md"
    publisher_path = root / "scripts/backlog_publish_plan.py"

    if not publisher_path.exists():
        failures.append("missing scripts/backlog_publish_plan.py")
    else:
        publisher = publisher_path.read_text(encoding="utf-8")
        for required in [
            "LangFelixAT/codex-observe",
            "--repo",
            "--label",
            "--json",
            "BACKLOG_PUBLISH_SCHEMA_VERSION",
            'plan_payload("failed", failures)',
            '"failures"',
            "requires explicit approval",
        ]:
            if required not in publisher:
                failures.append(f"scripts/backlog_publish_plan.py missing {required}")

    if backlog_path.exists():
        backlog = backlog_path.read_text(encoding="utf-8")
        if "python scripts/backlog_publish_plan.py" not in backlog:
            failures.append("docs/BACKLOG.md does not require the dry-run publisher")
        if "python scripts/backlog_publish_plan.py --json" not in backlog:
            failures.append("docs/BACKLOG.md does not document publisher JSON output")
        if "draft files were deleted" not in backlog:
            failures.append("docs/BACKLOG.md does not record retired draft closeout")
    else:
        failures.append("missing docs/BACKLOG.md")

    next_wave = (
        next_wave_path.read_text(encoding="utf-8") if next_wave_path.exists() else ""
    )
    if not next_wave:
        failures.append("missing docs/NEXT_WAVE.md")

    for retired in sorted(RETIRED_BACKLOG_DRAFTS):
        if (root / retired).exists():
            failures.append(f"retired draft still exists: {retired}")

    for path in active_backlog_drafts(root):
        relative = path.relative_to(root).as_posix()
        body = path.read_text(encoding="utf-8")
        title = ""
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        if relative not in next_wave or (title and title not in next_wave):
            failures.append(
                f"docs/NEXT_WAVE.md does not reference active draft {relative}"
            )
        for section in ["## What to build", "## Acceptance criteria", "## Blocked by"]:
            if section not in body:
                failures.append(f"{relative} missing {section}")
        for pattern in BACKLOG_FORBIDDEN_PATTERNS:
            if re.search(pattern, body):
                failures.append(
                    f"{relative} contains private or local-only pattern {pattern}"
                )

    return failures


def dev_tooling_failures(root: Path | None = None) -> list[str]:
    root = root or Path.cwd()
    failures: list[str] = []
    pyproject = root / "pyproject.toml"
    ci = root / ".github/workflows/ci.yml"
    contributing = root / "CONTRIBUTING.md"
    release = root / "docs/RELEASE.md"
    distribution = root / "docs/DISTRIBUTION.md"

    pyproject_text = pyproject.read_text(encoding="utf-8") if pyproject.exists() else ""
    for required in [
        "dev = [",
        '"pillow>=10"',
        '"playwright"',
        '"pytest"',
        '"ruff"',
        "visual = [",
    ]:
        if required not in pyproject_text:
            failures.append(f"pyproject.toml missing {required}")

    expected_by_file = {
        ci: [
            'python -m pip install -e ".[dev]"',
            "ruff check",
            "ruff format --check",
            "pytest -q",
            "python scripts/clean_install_smoke.py --extra dev",
            "codex-observe audit --json",
            "codex-observe demo --sessions .artifacts/demo/sessions --keep-sessions --json",
            "codex-observe ingest .artifacts/demo/sessions --db .artifacts/demo/ingest-contract.sqlite --json",
            "codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md",
            "codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json",
            "codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md",
            "codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json",
            "python scripts/visual_qa.py",
            "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json",
            "aggregate-run-report",
            "visual-qa-evidence",
            "codex-observe evidence-bundle --out .artifacts/public-evidence",
            "public-evidence-bundle",
            ".artifacts/public-evidence/**",
            ".artifacts/demo/run-report.md",
            ".artifacts/demo/run-report.json",
            ".artifacts/demo/run-comparison.md",
            ".artifacts/demo/run-comparison.json",
            ".artifacts/visual/*.png",
            ".artifacts/visual/visual-qa-manifest.json",
        ],
        contributing: [
            'python -m pip install -e ".[dev]"',
            "ruff check",
            "ruff format --check",
            "pytest -q",
        ],
        release: [
            'python -m pip install -e ".[dev]"',
            "Playwright plus Pillow",
            "ruff check",
            "ruff format --check",
            "pytest -q",
        ],
        distribution: [
            'python -m pip install -e ".[dev]"',
            'python -m pip install -e ".[visual]"',
            "Playwright and Pillow",
        ],
    }
    for path, required_values in expected_by_file.items():
        if not path.exists():
            failures.append(f"missing {path.relative_to(root).as_posix()}")
            continue
        body = path.read_text(encoding="utf-8")
        for required in required_values:
            if required not in body:
                failures.append(
                    f"{path.relative_to(root).as_posix()} missing {required}"
                )
    return failures


def issue_template_failures(root: Path | None = None) -> list[str]:
    root = root or Path.cwd()
    templates = {
        "implementation_slice.yml": [
            "Implementation slice",
            "codex-observe audit --json",
            "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json",
            "codex-observe evidence-bundle --out .artifacts/public-evidence",
            "docs/LIMITATIONS.md",
        ],
        "visual_polish.yml": [
            "Visual/UI polish",
            "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json",
            "codex-observe evidence-bundle --out .artifacts/public-evidence",
            "layout review",
            "expected high-risk metric card evidence",
        ],
        "parser_gap.yml": [
            "Parser/log shape gap",
            "docs/REAL_LOG_FEEDBACK.md",
            "redaction manifest/privacy review",
            "events.payload_json",
            "codex-observe audit --json",
        ],
        "public_tour_feedback.yml": [
            "Public tour feedback",
            "codex-observe tour",
            "codex-observe tour --json",
            "codex-observe evidence-bundle --out .artifacts/public-evidence",
            "codex-observe audit --json",
            "codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite",
            "codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite",
            "codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json",
            "codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json",
            "python scripts/visual_qa.py",
            "report/comparison terminal `Next commands` blocks",
            "docs/PUBLIC_TOUR_FEEDBACK.md",
            "docs/LIMITATIONS.md",
            "Do not paste private prompts",
        ],
    }
    failures: list[str] = []
    for filename, required_values in templates.items():
        relative = f".github/ISSUE_TEMPLATE/{filename}"
        path = root / relative
        if not path.exists():
            failures.append(f"missing {relative}")
            continue
        body = path.read_text(encoding="utf-8")
        for required in required_values:
            if required not in body:
                failures.append(f"{relative} missing {required}")
    return failures


def tracking_doc_failures(root: Path | None = None) -> list[str]:
    root = root or Path.cwd()
    tracking = root / "docs/TRACKING.md"
    if not tracking.exists():
        return ["missing docs/TRACKING.md"]

    body = tracking.read_text(encoding="utf-8")
    required = [
        "Checked: 2026-07-13",
        "gh issue list --limit 20 --state all --json number,title,state,labels,updatedAt,url",
        "All current GitHub issues are closed",
        "There is no `.github/backlog` directory",
        "no current publishable local issue draft",
        "python scripts/backlog_publish_plan.py --json",
        "explicit human approval",
        "Commit and push the implementation branch",
    ]
    failures = [
        f"docs/TRACKING.md missing {item}" for item in required if item not in body
    ]
    for issue_number in range(1, 9):
        if f"#{issue_number}" not in body:
            failures.append(f"docs/TRACKING.md missing issue #{issue_number}")
    return failures


def ci_evidence_bundle_failures(root: Path | None = None) -> list[str]:
    root = root or Path.cwd()
    workflow = root / ".github" / "workflows" / "ci.yml"
    if not workflow.exists():
        return ["missing .github/workflows/ci.yml"]
    body = workflow.read_text(encoding="utf-8")
    required = [
        "Generate reviewer evidence bundle",
        "codex-observe evidence-bundle --out .artifacts/public-evidence",
        "Upload reviewer evidence bundle",
        "public-evidence-bundle",
        ".artifacts/public-evidence/**",
    ]
    return [f"ci workflow missing {item}" for item in required if item not in body]


def public_evidence_bundle_artifact_failures(
    root: Path | None = None,
    bundle_dir: Path | None = None,
) -> list[str]:
    root = root or Path.cwd()
    bundle_dir = bundle_dir or root / ".artifacts" / "public-evidence"
    manifest_path = bundle_dir / "evidence-bundle.json"
    if not manifest_path.exists():
        try:
            label = manifest_path.relative_to(root).as_posix()
        except ValueError:
            label = str(manifest_path)
        return [f"missing {label}"]

    failures: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid evidence bundle manifest JSON: {exc.msg}"]

    if manifest.get("schema_version") != EVIDENCE_BUNDLE_SCHEMA_VERSION:
        failures.append("evidence bundle manifest schema_version mismatch")
    if manifest.get("status") != "ok":
        failures.append("evidence bundle manifest status is not ok")
    privacy = manifest.get("privacy")
    if (
        not isinstance(privacy, dict)
        or privacy.get("private_log_required") is not False
    ):
        failures.append(
            "evidence bundle privacy metadata missing synthetic local-only contract"
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return [*failures, "evidence bundle manifest missing artifacts"]

    review_summary = manifest.get("review_summary")
    if not isinstance(review_summary, list) or not review_summary:
        failures.append("evidence bundle manifest missing review_summary")
    else:
        summary_text = json.dumps(review_summary)
        for required in [
            "Run triage",
            "Top opportunity",
            "Next-run target",
            "Comparison verdict",
            "Audit status",
        ]:
            if required not in summary_text:
                failures.append(f"evidence bundle review_summary missing {required}")
    review_checklist = manifest.get("review_checklist")
    action_plan = manifest.get("action_plan")
    validation_commands = manifest.get("validation_commands")
    feedback_handoff = manifest.get("feedback_handoff")
    if not isinstance(review_checklist, list) or not review_checklist:
        failures.append("evidence bundle manifest missing review_checklist")
    else:
        checklist_text = json.dumps(review_checklist)
        for required in [
            "Confirm the bundle boundary",
            "Read the run outcome",
            "Check workflow-change evidence",
            "Verify release gates",
            "next validation command",
            "comparison review path",
            "File feedback safely",
        ]:
            if required not in checklist_text:
                failures.append(f"evidence bundle review_checklist missing {required}")
    if not isinstance(action_plan, list) or not action_plan:
        failures.append("evidence bundle manifest missing action_plan")
    else:
        action_plan_text = json.dumps(action_plan)
        for required in [
            "Establish the safe review boundary",
            "Read the run diagnosis",
            "Check change evidence",
            "Verify reproducibility gates",
            "Validate the next real run",
            "File feedback safely",
            "success_check",
        ]:
            if required not in action_plan_text:
                failures.append(f"evidence bundle action_plan missing {required}")

    if not isinstance(validation_commands, dict):
        failures.append("evidence bundle manifest missing validation_commands")
    else:
        for key, snippet in {
            "next_report": "codex-observe report --db <db> --session-id <next-session-id>",
            "next_comparison": "codex-observe compare --before-report <after-report.json>",
        }.items():
            value = validation_commands.get(key)
            if not isinstance(value, str) or snippet not in value:
                failures.append(
                    f"evidence bundle validation_commands {key} missing {snippet}"
                )

    if not isinstance(feedback_handoff, dict):
        failures.append("evidence bundle manifest missing feedback_handoff")
    else:
        handoff_text = json.dumps(feedback_handoff)
        for required in [
            "docs/PUBLIC_TOUR_FEEDBACK.md",
            ".github/ISSUE_TEMPLATE/public_tour_feedback.yml",
            "synthetic or reviewed-redacted evidence",
            "reviewer evidence bundle",
            "private prompts",
            "raw logs",
            "unreviewed screenshots",
        ]:
            if required not in handoff_text:
                failures.append(f"evidence bundle feedback_handoff missing {required}")

    terminal_lines = evidence_bundle_lines(str(bundle_dir), manifest)
    terminal_text = "\n".join(terminal_lines)
    for required in [
        "Reviewer action plan:",
        "Key findings:",
        "Review checklist:",
        "Validation commands:",
        "Feedback handoff:",
        "Runbook: docs/PUBLIC_TOUR_FEEDBACK.md",
        "Issue template: .github/ISSUE_TEMPLATE/public_tour_feedback.yml",
        "Safe feedback sources:",
        "Do not collect:",
        "private prompts",
        "Artifacts:",
        "Confirm the bundle boundary: LIMITATIONS.md",
        "Check workflow-change evidence: demo/run-comparison.md",
        "comparison review path",
        "next_report: codex-observe report --db <db> --session-id <next-session-id>",
        "bundle_readme: README.md",
    ]:
        if required not in terminal_text:
            failures.append(f"evidence bundle terminal output missing {required}")
    for before, after in [
        ("Reviewer action plan:", "Key findings:"),
        ("Key findings:", "Review checklist:"),
        ("Review checklist:", "Validation commands:"),
        ("Validation commands:", "Feedback handoff:"),
        ("Feedback handoff:", "Artifacts:"),
    ]:
        if before in terminal_text and after in terminal_text:
            if terminal_text.index(before) > terminal_text.index(after):
                failures.append(
                    f"evidence bundle terminal output orders {before} after {after}"
                )
    expected_artifacts = {
        "bundle_readme": "README.md",
        "limitations_markdown": "LIMITATIONS.md",
        "feedback_runbook": "PUBLIC_TOUR_FEEDBACK.md",
        "feedback_issue_template": ".github/ISSUE_TEMPLATE/public_tour_feedback.yml",
        "report_markdown": "demo/run-report.md",
        "comparison_markdown": "demo/run-comparison.md",
        "audit_json": "audit/audit.json",
    }
    for key, expected in expected_artifacts.items():
        value = artifacts.get(key)
        if value != expected:
            failures.append(
                f"evidence bundle {key} expected {expected}, got {value or 'missing'}"
            )
            continue
        artifact_path = bundle_dir / expected
        if not artifact_path.exists():
            failures.append(f"evidence bundle missing {expected}")

    readme_path = bundle_dir / "README.md"
    if readme_path.exists():
        readme = readme_path.read_text(encoding="utf-8")
        for required in [
            "# Codex Observe Evidence Bundle",
            "## Key Findings",
            "Run triage",
            "Top opportunity",
            "Next-run target",
            "Comparison verdict",
            "Audit status",
            "## Review Checklist",
            "Confirm the bundle boundary",
            "Read the run outcome",
            "Check workflow-change evidence",
            "Verify release gates",
            "next validation command",
            "comparison review path",
            "## Reproduce Locally",
            "codex-observe demo --db demo/codex_observe_demo.sqlite",
            "codex-observe report --db demo/codex_observe_demo.sqlite --out demo/run-report.md",
            "codex-observe compare --before-report demo/run-report.json --after-report demo/run-report.json --out demo/run-comparison.md",
            "codex-observe audit --json",
            "## Feedback Handoff",
            "docs/PUBLIC_TOUR_FEEDBACK.md",
            ".github/ISSUE_TEMPLATE/public_tour_feedback.yml",
            "synthetic or reviewed-redacted evidence",
            "Safe feedback sources",
            "Do not collect",
            "LIMITATIONS.md",
            "PUBLIC_TOUR_FEEDBACK.md",
            "Privacy-safe feedback issue template",
            "File feedback safely",
            "private Codex logs",
            "External publishing or attachment still requires explicit human approval",
        ]:
            if required not in readme:
                failures.append(f"evidence bundle README missing {required}")

    limitations_path = bundle_dir / "LIMITATIONS.md"
    if limitations_path.exists():
        limitations = limitations_path.read_text(encoding="utf-8")
        for required in [
            "# Limitations and Next Work",
            "approval-gated",
            "human-approved private input path",
            "explicit human approval",
        ]:
            if required not in limitations:
                failures.append(f"evidence bundle LIMITATIONS.md missing {required}")

    feedback_path = bundle_dir / "PUBLIC_TOUR_FEEDBACK.md"
    if feedback_path.exists():
        feedback = feedback_path.read_text(encoding="utf-8")
        for required in [
            "# Public Tour Feedback",
            "Safe Feedback Sources",
            "Do Not Collect",
            "Private prompts",
            "External attachment or publication of generated artifacts still requires explicit human approval",
        ]:
            if required not in feedback:
                failures.append(
                    f"evidence bundle PUBLIC_TOUR_FEEDBACK.md missing {required}"
                )

    feedback_issue_template_path = (
        bundle_dir / ".github" / "ISSUE_TEMPLATE" / "public_tour_feedback.yml"
    )
    if feedback_issue_template_path.exists():
        feedback_issue_template = feedback_issue_template_path.read_text(
            encoding="utf-8"
        )
        for required in [
            "Public tour feedback",
            "codex-observe tour --json",
            "codex-observe evidence-bundle --out .artifacts/public-evidence",
            "Do not paste private prompts",
            "reviewer evidence bundle",
            "Privacy review",
            "docs/PUBLIC_TOUR_FEEDBACK.md",
            "docs/LIMITATIONS.md",
        ]:
            if required not in feedback_issue_template:
                failures.append(
                    f"evidence bundle public_tour_feedback.yml missing {required}"
                )
    return failures


def private_artifact_ignore_failures(root: Path | None = None) -> list[str]:
    root = root or Path.cwd()
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return ["missing .gitignore"]
    ignored = set(gitignore.read_text(encoding="utf-8").splitlines())
    required = {
        "__pycache__/",
        "*.pyc",
        "*.sqlite",
        "*.sqlite-*",
        ".env",
        ".venv/",
        "dist/",
        "build/",
        "*.egg-info/",
        ".artifacts/",
    }
    return [f".gitignore missing {pattern}" for pattern in sorted(required - ignored)]


RELEASE_WORKFLOW_DOC_REQUIREMENTS = {
    "README.md": [
        "docs/REAL_LOG_FEEDBACK.md",
        "privacy_review",
        "manifest metadata",
        "--verify-only",
        "--json",
        "machine-readable generation status",
        "error codes",
        "privacy-safe validation failures",
        "validates the selected input path before touching output",
        "manifest source/output paths",
        "source-derived candidate filenames",
        "refuses to overwrite arbitrary existing directories",
        "layout overflow/clipping checks",
        "validated manifest evidence",
        "--verify-manifest",
        "aggregate triage assessment",
        "next-run success target",
        "success_target",
        "schema_version",
        "recommended_session",
        "required_commands",
        "failed_checks",
        "Failed checks",
        "plain-text output",
        ".artifacts/visual/visual-qa-manifest.json",
        "metric card evidence",
        "referenced screenshots",
        "layout review",
        "path-safe",
    ],
    "CONTRIBUTING.md": [
        "docs/REAL_LOG_FEEDBACK.md",
        "privacy_review",
        "manifest metadata",
        "--verify-only",
        "--json",
        "machine-readable generation status",
        "error codes",
        "privacy-safe validation failures",
        "validates the selected input path before touching output",
        "manifest source/output paths",
        "source-derived candidate filenames",
        "refuses to overwrite arbitrary existing directories",
        "recommended_session",
        "python scripts/visual_qa.py",
        "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json",
        "failed_checks",
        "Failed checks",
        "metric card evidence",
        "screenshot metadata",
        "layout review",
    ],
    "docs/RELEASE.md": [
        "docs/REAL_LOG_FEEDBACK.md",
        "privacy_review",
        "manifest metadata",
        "--verify-only",
        "--json",
        "machine-readable generation status",
        "error codes",
        "privacy-safe validation failures",
        "validates the selected input path before touching output",
        "manifest source/output paths",
        "source-derived candidate filenames",
        "refuses to overwrite arbitrary existing directories",
        "visual QA",
        "aggregate triage assessment",
        "schema_version",
        "recommended_session",
        "required_commands",
        "failed_checks",
        "plain-text required command list",
        "plain-text `Failed checks` section",
        "validated manifest evidence",
        "success-target evidence",
        "path-safe visual QA manifest",
        "referenced screenshots",
        "layout review",
        "metric card evidence",
        "docs/CURRENT.md",
    ],
    "docs/REAL_LOG_FEEDBACK.md": [
        "human explicitly selects",
        "privacy_review",
        "manifest metadata",
        "--verify-only",
        "--json",
        "machine-readable generation status",
        "error codes",
        "privacy-safe validation failures",
        "validates the selected input path before touching output",
        "manifest source/output paths",
        "source-derived candidate filenames",
        "refuses to overwrite arbitrary existing directories",
        "tests/fixtures/redacted/",
        "no new parser shape found",
        "candidate discarded during human privacy review",
    ],
    "docs/CURRENT.md": [
        "Current Project State",
        "docs/AMAZING.md",
        "docs/RELEASE.md",
        "docs/LIMITATIONS.md",
        "codex-observe tour",
        "codex-observe demo --serve --host 127.0.0.1 --port 8501",
        "ruff check",
        "ruff format --check",
        "pytest -q",
        "codex-observe audit --json",
        "codex-observe sessions --json",
        "recommended_session",
        "aggregate triage assessment",
        "next-run success target",
        "required_commands",
        "failed_checks",
        "Failed checks",
        "triage",
        "plain `codex-observe audit` prints",
        "python scripts/visual_qa.py",
        "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json",
        "metric card evidence",
        "screenshot metadata",
        "layout review",
        "codex-observe evidence-bundle",
        "codex-observe.evidence-bundle.v1",
        "There is currently no publishable local issue draft",
        "attaching generated artifacts externally still requires explicit human approval",
        "human-approved private input path",
    ],
    "docs/LIMITATIONS.md": [
        "source checkout plus editable install",
        "approval-gated",
        "human-approved private input path",
        "docs/REAL_LOG_FEEDBACK.md",
        "reviewer evidence bundle",
        "explicit human approval",
        "Fresh GitHub issues",
    ],
    "CHANGELOG.md": [
        "privacy review verifier",
        "--verify-only",
        "--json",
        "machine-readable generation status",
        "error codes",
        "privacy-safe validation failures",
        "validates the selected input path before touching output",
        "manifest source/output paths",
        "source-derived candidate filenames",
        "refuses to overwrite arbitrary existing directories",
        "recommended_session",
        "schema_version",
        "visual QA",
        "validated manifest evidence",
        "path-safe visual QA manifest",
        "referenced screenshots",
        "layout review",
        "metric card evidence",
        "required_commands",
        "failed_checks",
    ],
    ".github/PULL_REQUEST_TEMPLATE.md": [
        "## Linked issue",
        "`ruff check`",
        "`ruff format --check`",
        "`pytest -q`",
        "`codex-observe audit`",
        "`codex-observe demo --sessions .artifacts/demo/sessions --keep-sessions --json`",
        "`codex-observe ingest .artifacts/demo/sessions --db .artifacts/demo/ingest-contract.sqlite --json`",
        "`codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json`",
        "recommended_session",
        "schema_version",
        "`codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --out .artifacts/demo/run-report.md`",
        "`codex-observe report --db .artifacts/demo/codex_observe_demo.sqlite --format json --out .artifacts/demo/run-report.json`",
        "`codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md`",
        "`codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json`",
        "`python scripts/visual_qa.py`",
        "## Visual QA evidence",
        ".artifacts/visual/visual-qa-manifest.json",
        "metric card evidence",
        "referenced screenshot files",
        "layout review",
        "path-safe",
        "validated manifest evidence",
        "Aggregate report artifacts",
        "## Data/privacy review",
        "New external network writes, telemetry, publishing, or hosted behavior are absent or explicitly approved.",
    ],
}


def release_workflow_doc_failures(root: Path | None = None) -> list[str]:
    root = root or Path.cwd()
    failures: list[str] = []
    for relative, required_values in RELEASE_WORKFLOW_DOC_REQUIREMENTS.items():
        path = root / relative
        if not path.exists():
            failures.append(f"missing {relative}")
            continue
        body = path.read_text(encoding="utf-8")
        for required in required_values:
            if required not in body:
                failures.append(f"{relative} missing {required}")
        for artifact in ["\\n", "\\r\\n"]:
            if artifact in body:
                failures.append(f"{relative} contains literal newline artifact")
                break
    return failures


def redaction_cli_privacy_failures(root: Path | None = None) -> list[str]:
    root = root or Path.cwd()
    script = root / "scripts" / "redact_fixtures.py"
    if not script.exists():
        return ["missing scripts/redact_fixtures.py"]

    private_input = (
        root / ".artifacts" / "private-redaction-audit" / "missing-private-source.jsonl"
    )
    output_dir = root / ".artifacts" / "redaction-audit-output"
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                str(private_input),
                "--out",
                str(output_dir),
                "--json",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ["redaction --json validation check could not run"]

    failures: list[str] = []
    combined_output = f"{result.stdout}\n{result.stderr}"
    for forbidden in [
        str(private_input),
        "missing-private-source.jsonl",
        "private-redaction-audit",
    ]:
        if forbidden in combined_output:
            failures.append(
                "redaction --json validation failure leaked input path details"
            )
            break

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return failures + ["redaction --json validation failure was not JSON"]

    expected = {
        "status": "failed",
        "error_code": "missing_input",
        "error": "input path does not exist",
        "output_dir": "[redacted-path]",
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            failures.append(f"redaction --json validation failure missing {key}")
    if result.returncode != 2:
        failures.append("redaction --json validation failure exit code was not 2")
    if output_dir.exists():
        failures.append("redaction --json validation touched output directory")

    verify_result = None
    try:
        raw_id_parent = root / ".artifacts"
        raw_id_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="redaction-raw-id-audit-", dir=raw_id_parent
        ) as raw_id_tmp:
            raw_id_dir = Path(raw_id_tmp)
            (raw_id_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "mode": "redacted-fixture-candidate",
                        "review_required": True,
                        "files": [],
                    }
                ),
                encoding="utf-8",
            )
            (raw_id_dir / "redacted-001.jsonl").write_text(
                json.dumps(
                    {
                        "timestamp": "2026-02-01T00:00:00Z",
                        "type": "event",
                        "payload": {
                            "type": "message",
                            "session_id": "session-private",
                            "thread_id": "thread-private",
                        },
                    },
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            verify_result = subprocess.run(
                [sys.executable, str(script), str(raw_id_dir), "--verify-only"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
    except (OSError, subprocess.TimeoutExpired):
        failures.append("redaction verify-only raw ID check could not run")

    if verify_result is not None:
        verify_output = f"{verify_result.stdout}\n{verify_result.stderr}"
        if "session-private" in verify_output or "thread-private" in verify_output:
            failures.append("redaction verify-only raw ID failure leaked raw IDs")
        try:
            verify_payload = json.loads(verify_result.stdout)
        except json.JSONDecodeError:
            failures.append("redaction verify-only raw ID failure was not JSON")
        else:
            findings = verify_payload.get("findings")
            if verify_payload.get("status") != "failed" or not isinstance(
                findings, list
            ):
                failures.append("redaction verify-only raw ID failure missing status")
            elif not any("session_id" in str(finding) for finding in findings):
                failures.append("redaction verify-only raw ID failure missing finding")
        if verify_result.returncode != 1:
            failures.append("redaction verify-only raw ID failure exit code was not 1")
    return failures


def png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def visual_empty_state_evidence_failures(
    empty_states: object, manifest_dir: Path
) -> list[str]:
    failures: list[str] = []
    if not isinstance(empty_states, dict):
        return ["visual QA manifest missing empty-state evidence"]
    for state_name, expected_title in EXPECTED_VISUAL_EMPTY_STATES.items():
        state = empty_states.get(state_name)
        if not isinstance(state, dict):
            failures.append(
                f"visual QA manifest missing {state_name} empty-state evidence"
            )
            continue
        viewports = state.get("viewports")
        if not isinstance(viewports, dict):
            failures.append(
                f"visual QA manifest {state_name} missing viewport evidence"
            )
            continue
        for viewport_name, expected_viewport in EXPECTED_VISUAL_VIEWPORTS.items():
            viewport = viewports.get(viewport_name)
            if not isinstance(viewport, dict):
                failures.append(
                    f"visual QA manifest {state_name} missing {viewport_name} evidence"
                )
                continue
            if viewport.get("viewport") != expected_viewport:
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} viewport size does not match expected"
                )
            if viewport.get("title") != expected_title:
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} title expected {expected_title}"
                )
            commands = viewport.get("commands")
            if not isinstance(commands, list):
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} missing empty-state commands"
                )
            else:
                labels = {
                    str(command.get("label") or "")
                    for command in commands
                    if isinstance(command, dict)
                }
                missing_labels = EXPECTED_VISUAL_EMPTY_STATE_COMMAND_LABELS - labels
                if missing_labels:
                    failures.append(
                        f"visual QA manifest {state_name} {viewport_name} missing empty-state command labels: {', '.join(sorted(missing_labels))}"
                    )
                command_text = "\n".join(
                    str(command.get("command") or "")
                    for command in commands
                    if isinstance(command, dict)
                )
                missing_commands = [
                    snippet
                    for snippet in EXPECTED_VISUAL_EMPTY_STATE_COMMAND_SNIPPETS
                    if snippet not in command_text
                ]
                if missing_commands:
                    failures.append(
                        f"visual QA manifest {state_name} {viewport_name} missing empty-state commands: {', '.join(missing_commands)}"
                    )
            layout = viewport.get("layout_review")
            if not isinstance(layout, dict):
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} missing layout review"
                )
            else:
                viewport_width = int(layout.get("viewport_width") or 0)
                document_width = int(layout.get("document_width") or 0)
                if viewport_width and document_width > viewport_width + 2:
                    failures.append(
                        f"visual QA manifest {state_name} {viewport_name} layout review contains overflow"
                    )
                if layout.get("overflowing_elements"):
                    failures.append(
                        f"visual QA manifest {state_name} {viewport_name} layout review contains overflowing elements"
                    )
                if layout.get("clipped_text_elements"):
                    failures.append(
                        f"visual QA manifest {state_name} {viewport_name} layout review contains clipped text"
                    )
            screenshot = viewport.get("screenshot")
            if not isinstance(screenshot, dict):
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} missing screenshot metadata"
                )
                continue
            filename = screenshot.get("filename")
            if not isinstance(filename, str) or not filename:
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} screenshot filename missing"
                )
                continue
            if Path(filename).name != filename:
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} screenshot filename must be basename-only"
                )
                continue
            screenshot_path = manifest_dir / filename
            if not screenshot_path.exists():
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} screenshot file missing: {filename}"
                )
                continue
            dimensions = png_dimensions(screenshot_path)
            if dimensions is None:
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} screenshot file is not a readable PNG"
                )
                continue
            width, height = dimensions
            if screenshot.get("width") != width:
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} screenshot width does not match file"
                )
            if screenshot.get("height") != height:
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} screenshot height does not match file"
                )
            if width != expected_viewport["width"]:
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} screenshot width mismatch"
                )
            if height < min(600, expected_viewport["height"]):
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} screenshot height too small"
                )
            if (
                int(screenshot.get("bytes") or 0) <= 0
                or screenshot_path.stat().st_size <= 0
            ):
                failures.append(
                    f"visual QA manifest {state_name} {viewport_name} screenshot is empty"
                )
    return failures


def visual_manifest_evidence_failures(root: Path) -> list[str]:
    manifest_path = root / VISUAL_MANIFEST
    if not manifest_path.exists():
        return [f"missing {VISUAL_MANIFEST.as_posix()}; {VISUAL_MANIFEST_RECOVERY}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"visual QA manifest is not valid JSON: {exc.msg}"]
    if not isinstance(manifest, dict):
        return ["visual QA manifest must be an object"]

    failures: list[str] = []
    if manifest.get("schema_version") != VISUAL_MANIFEST_SCHEMA_VERSION:
        failures.append("visual QA manifest schema_version is missing or unsupported")
    checks = manifest.get("checks")
    if not isinstance(checks, dict):
        failures.append("visual QA manifest checks must be an object")
        checks = {}
    if checks.get("tabs_expected") != EXPECTED_VISUAL_TABS:
        failures.append(
            "visual QA manifest tabs_expected does not match dashboard tabs"
        )
    expected_checks = {
        "streamlit_exception_text": "not found",
        "screenshot_quality": "passed",
        "layout_review": "passed",
    }
    for key, expected in expected_checks.items():
        if checks.get(key) != expected:
            failures.append(f"visual QA manifest check {key} must be {expected}")
    if checks.get("empty_states") != "passed":
        failures.append("visual QA manifest check empty_states must be passed")
    failures.extend(
        visual_empty_state_evidence_failures(
            manifest.get("empty_states"), manifest_path.parent
        )
    )

    viewports = manifest.get("viewports")
    if not isinstance(viewports, dict):
        return failures + ["visual QA manifest missing viewport evidence"]

    for viewport_name, expected_viewport in EXPECTED_VISUAL_VIEWPORTS.items():
        viewport = viewports.get(viewport_name)
        if not isinstance(viewport, dict):
            failures.append(f"visual QA manifest missing {viewport_name} evidence")
            continue
        if viewport.get("viewport") != expected_viewport:
            failures.append(
                f"visual QA manifest {viewport_name} viewport size does not match expected"
            )
        if viewport.get("tabs_exercised") != EXPECTED_VISUAL_TABS:
            failures.append(
                f"visual QA manifest {viewport_name} tabs_exercised incomplete"
            )
        quick_read_evidence = viewport.get("quick_read_evidence")
        if not isinstance(quick_read_evidence, list):
            failures.append(
                f"visual QA manifest {viewport_name} missing quick-read evidence"
            )
        else:
            observed = {
                str(item.get("tab") or ""): str(item.get("text") or "")
                for item in quick_read_evidence
                if isinstance(item, dict)
            }
            for expected in EXPECTED_VISUAL_QUICK_READ_EVIDENCE:
                tab = expected["tab"]
                expected_text = expected["text"]
                if observed.get(tab) != expected_text:
                    failures.append(
                        f"visual QA manifest {viewport_name} quick-read evidence missing {tab}: {expected_text}"
                    )
        if viewport.get("agent_detail_selector_exercised") is not True:
            failures.append(
                f"visual QA manifest {viewport_name} agent detail selector was not exercised"
            )

        screenshot = viewport.get("screenshot")
        if not isinstance(screenshot, dict):
            failures.append(
                f"visual QA manifest {viewport_name} missing screenshot metadata"
            )
        else:
            filename = screenshot.get("filename")
            if not isinstance(filename, str) or not filename:
                failures.append(
                    f"visual QA manifest {viewport_name} screenshot filename missing"
                )
            elif Path(filename).name != filename:
                failures.append(
                    f"visual QA manifest {viewport_name} screenshot filename must be basename-only"
                )
            else:
                screenshot_path = manifest_path.parent / filename
                if not screenshot_path.exists():
                    failures.append(
                        f"visual QA manifest {viewport_name} screenshot file missing: {filename}"
                    )
                else:
                    dimensions = png_dimensions(screenshot_path)
                    if dimensions is None:
                        failures.append(
                            f"visual QA manifest {viewport_name} screenshot file is not a readable PNG"
                        )
                    else:
                        width, height = dimensions
                        if screenshot.get("width") != width:
                            failures.append(
                                f"visual QA manifest {viewport_name} screenshot width does not match file"
                            )
                        if screenshot.get("height") != height:
                            failures.append(
                                f"visual QA manifest {viewport_name} screenshot height does not match file"
                            )
                        if width != expected_viewport["width"]:
                            failures.append(
                                f"visual QA manifest {viewport_name} screenshot width mismatch"
                            )
                        if height < min(600, expected_viewport["height"]):
                            failures.append(
                                f"visual QA manifest {viewport_name} screenshot height too small"
                            )
                    if (
                        int(screenshot.get("bytes") or 0) <= 0
                        or screenshot_path.stat().st_size <= 0
                    ):
                        failures.append(
                            f"visual QA manifest {viewport_name} screenshot is empty"
                        )

        layout = viewport.get("layout_review")
        if not isinstance(layout, dict):
            failures.append(f"visual QA manifest {viewport_name} missing layout review")
        else:
            viewport_width = int(layout.get("viewport_width") or 0)
            document_width = int(layout.get("document_width") or 0)
            if viewport_width and document_width > viewport_width + 2:
                failures.append(
                    f"visual QA manifest {viewport_name} layout review contains overflow"
                )
            if layout.get("overflowing_elements"):
                failures.append(
                    f"visual QA manifest {viewport_name} layout review contains overflowing elements"
                )
            if layout.get("clipped_text_elements"):
                failures.append(
                    f"visual QA manifest {viewport_name} layout review contains clipped text"
                )

        labels = viewport.get("sidebar_risk_labels")
        if not isinstance(labels, list):
            failures.append(
                f"visual QA manifest missing {viewport_name} sidebar risk labels"
            )
        else:
            missing = EXPECTED_VISUAL_RISK_LABELS - {str(label) for label in labels}
            if missing:
                failures.append(
                    f"visual QA manifest {viewport_name} missing risk labels: {', '.join(sorted(missing))}"
                )
        session_details = viewport.get("sidebar_session_details")
        if not isinstance(session_details, list):
            failures.append(
                f"visual QA manifest missing {viewport_name} sidebar session details"
            )
        else:
            missing_details = EXPECTED_VISUAL_SIDEBAR_SESSION_DETAILS - {
                str(detail) for detail in session_details
            }
            if missing_details:
                failures.append(
                    f"visual QA manifest {viewport_name} missing sidebar session details: {', '.join(sorted(missing_details))}"
                )

        risk_distributions = viewport.get("risk_distributions")
        if not isinstance(risk_distributions, list) or not risk_distributions:
            failures.append(
                f"visual QA manifest missing {viewport_name} risk distribution evidence"
            )
        else:
            distribution_text = "\n".join(
                str(item.get("body") or item.get("label") or "")
                for item in risk_distributions
                if isinstance(item, dict)
            )
            missing_distribution = EXPECTED_VISUAL_RISK_DISTRIBUTION - {
                expected
                for expected in EXPECTED_VISUAL_RISK_DISTRIBUTION
                if expected in distribution_text
            }
            if missing_distribution:
                failures.append(
                    f"visual QA manifest {viewport_name} missing risk distribution evidence: {', '.join(sorted(missing_distribution))}"
                )

        metric_cards = viewport.get("metric_cards")
        if not isinstance(metric_cards, list):
            failures.append(f"visual QA manifest missing {viewport_name} metric cards")
            continue
        metrics = {
            str(card.get("label") or ""): str(card.get("value") or "")
            for card in metric_cards
            if isinstance(card, dict)
        }
        for label, expected in EXPECTED_VISUAL_METRICS.items():
            actual = metrics.get(label)
            if actual != expected:
                failures.append(
                    f"visual QA manifest {viewport_name} {label} expected {expected}, got {actual or 'missing'}"
                )
        download_controls = viewport.get("download_controls")
        if not isinstance(download_controls, list):
            failures.append(
                f"visual QA manifest missing {viewport_name} report download control evidence"
            )
        else:
            missing_controls = EXPECTED_VISUAL_DOWNLOAD_CONTROLS - {
                str(label) for label in download_controls
            }
            if missing_controls:
                failures.append(
                    f"visual QA manifest {viewport_name} missing report download controls: {', '.join(sorted(missing_controls))}"
                )
        operator_briefings = viewport.get("operator_briefings")
        if not isinstance(operator_briefings, list) or not operator_briefings:
            failures.append(
                f"visual QA manifest missing {viewport_name} operator briefing evidence"
            )
        else:
            briefing = operator_briefings[0]
            if not isinstance(briefing, dict):
                failures.append(
                    f"visual QA manifest {viewport_name} operator briefing evidence is invalid"
                )
            else:
                heading = str(briefing.get("heading") or "")
                if EXPECTED_VISUAL_OPERATOR_BRIEFING["risk"] not in heading:
                    failures.append(
                        f"visual QA manifest {viewport_name} operator briefing risk expected {EXPECTED_VISUAL_OPERATOR_BRIEFING['risk']}"
                    )
                for key in ["best_habit", "scale", "proof_target"]:
                    expected = EXPECTED_VISUAL_OPERATOR_BRIEFING[key]
                    actual = str(briefing.get(key) or "")
                    if actual != expected:
                        failures.append(
                            f"visual QA manifest {viewport_name} operator briefing {key} expected {expected}, got {actual or 'missing'}"
                        )
        review_paths = viewport.get("review_paths")
        if not isinstance(review_paths, list) or not review_paths:
            failures.append(
                f"visual QA manifest missing {viewport_name} next review path evidence"
            )
        else:
            review_text = "\n".join(
                str(item.get("body") or item.get("label") or "")
                for item in review_paths
                if isinstance(item, dict)
            )
            missing_review_path = EXPECTED_VISUAL_REVIEW_PATH - {
                expected
                for expected in EXPECTED_VISUAL_REVIEW_PATH
                if expected in review_text
            }
            if missing_review_path:
                failures.append(
                    f"visual QA manifest {viewport_name} missing next review path evidence: {', '.join(sorted(missing_review_path))}"
                )

        next_run_checklists = viewport.get("next_run_checklists")
        if not isinstance(next_run_checklists, list) or not next_run_checklists:
            failures.append(
                f"visual QA manifest missing {viewport_name} next run checklist evidence"
            )
        else:
            checklist_text = "\n".join(
                str(item.get("body") or item.get("label") or "")
                for item in next_run_checklists
                if isinstance(item, dict)
            )
            missing_checklist = EXPECTED_VISUAL_NEXT_RUN_CHECKLIST - {
                expected
                for expected in EXPECTED_VISUAL_NEXT_RUN_CHECKLIST
                if expected in checklist_text
            }
            if missing_checklist:
                failures.append(
                    f"visual QA manifest {viewport_name} missing next run checklist evidence: {', '.join(sorted(missing_checklist))}"
                )

        next_run_briefs = viewport.get("next_run_briefs")
        if not isinstance(next_run_briefs, list) or not next_run_briefs:
            failures.append(
                f"visual QA manifest missing {viewport_name} next run brief evidence"
            )
        else:
            brief_text = "\n".join(
                str(item.get("body") or item.get("label") or "")
                for item in next_run_briefs
                if isinstance(item, dict)
            )
            missing_brief = EXPECTED_VISUAL_NEXT_RUN_BRIEF - {
                expected
                for expected in EXPECTED_VISUAL_NEXT_RUN_BRIEF
                if expected in brief_text
            }
            if missing_brief:
                failures.append(
                    f"visual QA manifest {viewport_name} missing next run brief evidence: {', '.join(sorted(missing_brief))}"
                )

        feedback_handoffs = viewport.get("feedback_handoffs")
        if not isinstance(feedback_handoffs, list) or not feedback_handoffs:
            failures.append(
                f"visual QA manifest missing {viewport_name} safe feedback handoff evidence"
            )
        else:
            feedback_text = "\n".join(
                str(item.get("body") or item.get("label") or "")
                for item in feedback_handoffs
                if isinstance(item, dict)
            )
            missing_feedback_handoff = EXPECTED_VISUAL_FEEDBACK_HANDOFF - {
                expected
                for expected in EXPECTED_VISUAL_FEEDBACK_HANDOFF
                if expected in feedback_text
            }
            if missing_feedback_handoff:
                failures.append(
                    f"visual QA manifest {viewport_name} missing safe feedback handoff evidence: {', '.join(sorted(missing_feedback_handoff))}"
                )

        comparison_previews = viewport.get("comparison_previews")
        if not isinstance(comparison_previews, list) or not comparison_previews:
            failures.append(
                f"visual QA manifest missing {viewport_name} comparison preview evidence"
            )
        else:
            preview_text = "\n".join(
                str(item.get("body") or item.get("label") or "")
                for item in comparison_previews
                if isinstance(item, dict)
            )
            missing_preview = EXPECTED_VISUAL_COMPARISON_PREVIEW - {
                expected
                for expected in EXPECTED_VISUAL_COMPARISON_PREVIEW
                if expected in preview_text
            }
            if missing_preview:
                failures.append(
                    f"visual QA manifest {viewport_name} missing comparison preview evidence: {', '.join(sorted(missing_preview))}"
                )
        comparison_review_paths = viewport.get("comparison_review_paths")
        if not isinstance(comparison_review_paths, list) or not comparison_review_paths:
            failures.append(
                f"visual QA manifest missing {viewport_name} comparison review path evidence"
            )
        else:
            comparison_review_text = "\n".join(
                str(item.get("body") or item.get("label") or "")
                for item in comparison_review_paths
                if isinstance(item, dict)
            )
            missing_comparison_review_path = EXPECTED_VISUAL_COMPARISON_REVIEW_PATH - {
                expected
                for expected in EXPECTED_VISUAL_COMPARISON_REVIEW_PATH
                if expected in comparison_review_text
            }
            if missing_comparison_review_path:
                failures.append(
                    f"visual QA manifest {viewport_name} missing comparison review path evidence: {', '.join(sorted(missing_comparison_review_path))}"
                )
        comparison_deltas = viewport.get("comparison_deltas")
        if not isinstance(comparison_deltas, list) or not comparison_deltas:
            failures.append(
                f"visual QA manifest missing {viewport_name} comparison delta evidence"
            )
        else:
            observed_deltas = {
                str(item.get("label") or ""): str(item.get("delta") or "")
                for item in comparison_deltas
                if isinstance(item, dict)
            }
            for label, direction in EXPECTED_VISUAL_COMPARISON_DELTAS.items():
                actual = observed_deltas.get(label)
                if actual is None:
                    failures.append(
                        f"visual QA manifest {viewport_name} missing comparison delta: {label}"
                    )
                elif direction not in actual:
                    failures.append(
                        f"visual QA manifest {viewport_name} comparison delta {label} missing direction: {direction}"
                    )
        success_targets = viewport.get("success_targets")
        if not isinstance(success_targets, list) or not success_targets:
            failures.append(
                f"visual QA manifest missing {viewport_name} success target evidence"
            )
            continue
        success_target = success_targets[0]
        if not isinstance(success_target, dict):
            failures.append(
                f"visual QA manifest {viewport_name} success target evidence is invalid"
            )
            continue
        for key, expected in EXPECTED_VISUAL_SUCCESS_TARGET.items():
            actual = str(success_target.get(key) or "")
            if actual != expected:
                failures.append(
                    f"visual QA manifest {viewport_name} success target {key} expected {expected}, got {actual or 'missing'}"
                )
    return failures


def failed_audit_checks(checks: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "name": str(check["name"]),
            "detail": str(check.get("detail") or ""),
        }
        for check in checks
        if not bool(check["ok"])
    ]


def release_audit_next_message(ok: bool, failed_checks: list[dict[str, str]]) -> str:
    if ok:
        quoted = [f"`{command}`" for command in RELEASE_REQUIRED_COMMANDS]
        return f"run {', '.join(quoted[:-1])}, and {quoted[-1]} before release."
    if not failed_checks:
        return "fix failed checks, then rerun `codex-observe audit`."
    summary = "; ".join(
        f"{check['name']}: {check['detail']}" if check["detail"] else check["name"]
        for check in failed_checks[:3]
    )
    if len(failed_checks) > 3:
        summary += f"; and {len(failed_checks) - 3} more"
    return f"fix failed checks ({summary}), then rerun `codex-observe audit`."


def release_audit_report(
    db_path: str = DEFAULT_DEMO_DB,
    sessions_path: str = DEFAULT_DEMO_SESSIONS,
    report_out: str = ".artifacts/demo/run-report.md",
    *,
    public_evidence_dir: str | Path | None = None,
    check_public_evidence_bundle: bool = True,
) -> tuple[int, dict]:
    root = Path.cwd()
    checks: list[dict[str, object]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    actual_db_path = db_path
    try:
        result = create_demo_database(actual_db_path, sessions_path, keep_sessions=True)
        demo_detail = f"{result.files_imported} files, {result.threads} threads, {result.events} events"
    except PermissionError:
        requested = Path(db_path).expanduser()
        fallback = requested.with_name(
            f"{requested.stem}-audit{requested.suffix or '.sqlite'}"
        )
        actual_db_path = str(fallback)
        result = create_demo_database(actual_db_path, sessions_path, keep_sessions=True)
        demo_detail = f"{result.files_imported} files, {result.threads} threads, {result.events} events; requested DB was locked, used {actual_db_path}"
    add(
        "demo database",
        result.files_imported > 0 and Path(actual_db_path).exists(),
        demo_detail,
    )

    demo_payload = demo_success_payload(actual_db_path, sessions_path, result)
    demo_lines_text = "\n".join(demo_success_lines(actual_db_path, result))
    demo_review_path = demo_payload.get("review_path")
    demo_has_review_path = (
        isinstance(demo_review_path, list)
        and len(demo_review_path) >= 4
        and all(
            isinstance(step, dict)
            and step.get("label")
            and step.get("command")
            and step.get("success_check")
            for step in demo_review_path
        )
        and any(
            "codex-observe doctor" in str(step.get("command"))
            and "--json" in str(step.get("command"))
            for step in demo_review_path
            if isinstance(step, dict)
        )
        and any(
            "codex-observe sessions" in str(step.get("command"))
            and "--json" in str(step.get("command"))
            for step in demo_review_path
            if isinstance(step, dict)
        )
    )
    demo_json_ok = (
        demo_payload.get("schema_version") == DEMO_SCHEMA_VERSION
        and demo_payload.get("status") == "ok"
        and demo_payload.get("database") == actual_db_path
        and demo_payload.get("counts", {}).get("jsonl_files") == result.files_imported
        and demo_payload.get("counts", {}).get("threads") == result.threads
        and demo_payload.get("counts", {}).get("events") == result.events
        and demo_payload.get("next_commands") == demo_next_commands(actual_db_path)
        and demo_has_review_path
        and "Review path:" in demo_lines_text
        and "Verify synthetic database:" in demo_lines_text
        and "Next commands:" in demo_lines_text
        and all(
            command in demo_lines_text for command in demo_next_commands(actual_db_path)
        )
    )
    add(
        "demo JSON",
        demo_json_ok,
        "schema, counts, database, text next commands, next commands, text review path, and review path verified"
        if demo_json_ok
        else "demo JSON schema_version, counts, database, text next commands, next_commands, text review path, or review_path missing",
    )

    ingest_contract_path = Path(actual_db_path).with_name(
        f"{Path(actual_db_path).stem}-ingest-contract.sqlite"
    )
    if ingest_contract_path.exists():
        ingest_contract_path.unlink()
    ingest_result = ingest(sessions_path, str(ingest_contract_path))
    ingest_payload = ingest_success_payload(
        sessions_path, str(ingest_contract_path), ingest_result
    )
    ingest_lines_text = "\n".join(
        ingest_success_lines(str(ingest_contract_path), ingest_result)
    )
    ingest_review_path = ingest_payload.get("review_path")
    ingest_has_review_path = (
        isinstance(ingest_review_path, list)
        and len(ingest_review_path) >= 3
        and all(
            isinstance(step, dict)
            and step.get("label")
            and step.get("command")
            and step.get("success_check")
            for step in ingest_review_path
        )
        and any(
            "codex-observe doctor" in str(step.get("command"))
            and "--json" in str(step.get("command"))
            for step in ingest_review_path
            if isinstance(step, dict)
        )
        and any(
            "codex-observe sessions" in str(step.get("command"))
            and "--json" in str(step.get("command"))
            for step in ingest_review_path
            if isinstance(step, dict)
        )
    )
    ingest_json_ok = (
        ingest_payload.get("schema_version") == INGEST_SCHEMA_VERSION
        and ingest_payload.get("status") == "ok"
        and ingest_payload.get("privacy", {}).get("raw_content_included") is False
        and ingest_payload.get("privacy", {}).get("review_required_before_sharing")
        is True
        and "aggregate metrics"
        in str(ingest_payload.get("privacy", {}).get("share_warning", ""))
        and ingest_payload.get("counts", {}).get("files_matched")
        == result.files_imported
        and ingest_payload.get("counts", {}).get("files_seen") == result.files_imported
        and ingest_payload.get("counts", {}).get("files_imported")
        == result.files_imported
        and ingest_payload.get("counts", {}).get("files_skipped_by_limit") == 0
        and ingest_payload.get("scan_limit") == {"mode": "all", "newest_files": None}
        and ingest_payload.get("counts", {}).get("threads") == result.threads
        and ingest_payload.get("counts", {}).get("events") == result.events
        and ingest_payload.get("skipped") == ingest_skipped_counts(ingest_result)
        and ingest_payload.get("next_commands")
        == ingest_next_commands(str(ingest_contract_path))
        and ingest_has_review_path
        and "Privacy: ingest output is aggregate-only" in ingest_lines_text
        and "aggregate metrics before sharing" in ingest_lines_text
        and "Review path:" in ingest_lines_text
        and "Verify database health:" in ingest_lines_text
        and "Next commands:" in ingest_lines_text
        and all(
            command in ingest_lines_text
            for command in ingest_next_commands(str(ingest_contract_path))
        )
    )
    add(
        "synthetic ingest JSON",
        ingest_json_ok,
        "schema, counts, scan limit, skipped categories, privacy review metadata, text privacy warning, text next commands, next commands, text review path, and review path verified"
        if ingest_json_ok
        else "synthetic ingest JSON schema_version, counts, scan limit, skipped categories, privacy review metadata, text privacy warning, text next_commands, next_commands, text review path, or review_path missing",
    )

    doctor_status, doctor = doctor_report(actual_db_path)
    doctor_lines_status, doctor_text_lines = doctor_lines(actual_db_path)
    doctor_lines_text = "\n".join(doctor_text_lines)
    doctor_has_schema = doctor.get("schema_version") == DOCTOR_SCHEMA_VERSION
    doctor_review_path = doctor.get("review_path")
    doctor_has_review_path = (
        isinstance(doctor_review_path, list)
        and len(doctor_review_path) >= 3
        and all(
            isinstance(item, dict)
            and item.get("label")
            and item.get("command")
            and item.get("success_check")
            for item in doctor_review_path
        )
        and any(
            "codex-observe sessions" in str(item.get("command"))
            and "--json" in str(item.get("command"))
            for item in doctor_review_path
            if isinstance(item, dict)
        )
    )
    doctor_ok = (
        doctor_status == 0
        and doctor.get("status") == "ok"
        and doctor_has_schema
        and doctor.get("next_commands")
        == doctor_next_commands(Path(actual_db_path), "ok")
        and doctor_has_review_path
        and doctor_lines_status == 0
        and "Review path:" in doctor_lines_text
        and "Next commands:" in doctor_lines_text
        and all(
            command in doctor_lines_text
            for command in doctor_next_commands(Path(actual_db_path), "ok")
        )
    )
    add(
        "database doctor",
        doctor_ok,
        "ok; schema, text next commands, next commands, and review path verified"
        if doctor_ok
        else (
            str(doctor.get("status"))
            if doctor_has_schema
            else "doctor schema_version, text next commands, next_commands, or review_path missing"
        ),
    )

    try:
        sessions_payload = sessions_json_payload(actual_db_path)
        sessions = sessions_payload["sessions"]
        sessions_have_risk = bool(sessions) and all(
            session.get("triage_risk")
            for session in sessions
            if isinstance(session, dict)
        )
        sessions_has_schema = (
            sessions_payload.get("schema_version") == SESSIONS_SCHEMA_VERSION
        )
        sessions_has_status = sessions_payload.get("status") == "ok"
        sessions_has_limit_metadata = (
            sessions_payload.get("total_sessions") == 2
            and sessions_payload.get("returned_sessions") == 2
            and sessions_payload.get("truncated") is False
            and sessions_payload.get("limit") == DEFAULT_SESSIONS_LIMIT
        )
        sessions_has_risk_distribution = (
            sessions_payload.get("risk_distribution", {}).get("high") == 1
            and sessions_payload.get("risk_distribution", {}).get("low") == 1
            and sessions_payload.get("risk_distribution", {}).get("medium") == 0
            and sessions_payload.get("risk_distribution", {}).get("unknown") == 0
        )
        sessions_has_recommendation = bool(sessions_payload.get("recommended_session"))
        recommended_session = sessions_payload.get("recommended_session")
        recommended_session_id = (
            str(recommended_session.get("session_id"))
            if isinstance(recommended_session, dict)
            and recommended_session.get("session_id")
            else None
        )
        sessions_has_next_commands = sessions_payload.get(
            "next_commands"
        ) == sessions_next_commands(actual_db_path, recommended_session_id)
        recommendation_detail = sessions_payload.get("recommendation_detail")
        sessions_has_recommendation_detail = (
            isinstance(recommendation_detail, dict)
            and recommendation_detail.get("target") == recommended_session_id
            and recommendation_detail.get("ranked_by") == ["triage_risk", "last_seen"]
            and isinstance(recommendation_detail.get("drivers"), dict)
            and "largest_tool_output_chars" in recommendation_detail["drivers"]
            and isinstance(recommendation_detail.get("driver_summary"), list)
            and isinstance(recommendation_detail.get("success_target_preview"), dict)
            and recommendation_detail["success_target_preview"].get("metric")
            == "largest_thread_share_pct"
            and recommendation_detail["success_target_preview"].get("target")
            == "below 50.0%"
            and any(
                row.get("driver") == "largest_tool_output_chars"
                for row in recommendation_detail["driver_summary"]
                if isinstance(row, dict)
            )
        )
        sessions_has_review_path = (
            isinstance(sessions_payload.get("review_path"), list)
            and len(sessions_payload.get("review_path", [])) >= 4
            and all(
                isinstance(step, dict)
                and step.get("label")
                and step.get("command")
                and step.get("success_check")
                for step in sessions_payload.get("review_path", [])
            )
            and any(
                "codex-observe compare --before-report" in str(step.get("command"))
                for step in sessions_payload.get("review_path", [])
                if isinstance(step, dict)
            )
        )
        session_lines_text = "\n".join(session_summary_lines(actual_db_path))
        sessions_text_has_recommended_action = (
            "Recommended action:" in session_lines_text
            and "Export report for session:" in session_lines_text
            and "Top drivers:" in session_lines_text
            and "Next-run target:" in session_lines_text
            and "Habit to try:" in session_lines_text
            and "Tool out" in session_lines_text
            and "Snapshots" in session_lines_text
            and "largest tool output:" in session_lines_text
            and "Review path:" in session_lines_text
            and "Save report JSON:" in session_lines_text
            and "Validate next run:" in session_lines_text
            and "Compare workflow change:" in session_lines_text
            and "Next commands:" in session_lines_text
            and all(
                command in session_lines_text
                for command in sessions_next_commands(
                    actual_db_path, recommended_session_id
                )
            )
            and all("largest_tool_output_chars" in row for row in sessions)
            and all("usage_snapshots" in row for row in sessions)
        )
        session_listing_ok = (
            sessions_have_risk
            and sessions_has_schema
            and sessions_has_status
            and sessions_has_risk_distribution
            and sessions_has_recommendation
            and sessions_has_limit_metadata
            and sessions_has_next_commands
            and sessions_has_recommendation_detail
            and sessions_has_review_path
            and sessions_text_has_recommended_action
        )
        add(
            "session listing",
            session_listing_ok,
            f"{len(sessions)} sessions; triage risk, risk distribution, status, schema, limit metadata, usage snapshots, text recommended action, session table tool-output column, tool-output driver, structured driver summary, success-target preview, recommendation detail, review path, text validation next commands, and structured validation next commands verified"
            if session_listing_ok
            else "session listing missing aggregate triage risk, risk_distribution, status, schema_version, limit metadata, usage snapshots, text recommended action, recommended_session, recommendation_detail, review_path, text validation next commands, session table tool-output column, tool-output driver, structured driver summary, success-target preview, validation next_commands, or next_commands",
        )
    except FileNotFoundError as exc:
        sessions = []
        add("session listing", False, str(exc))
    try:
        report = build_report(
            actual_db_path, sessions[0]["session_id"] if sessions else None
        )
        out_path = Path(report_out).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        report_markdown_text = report_markdown(report)
        report_json_text = report_json(report)
        out_path.write_text(report_markdown_text, encoding="utf-8")
        json_out_path = out_path.with_suffix(".json")
        json_out_path.write_text(report_json_text, encoding="utf-8")
        report_payload = json.loads(report_json_text)
        summary = report.get("summary", {})
        triage = report.get("triage", {})
        report_written_text = "\n".join(
            report_written_lines(out_path, report, actual_db_path)
        )
        report_confirmation_has_success_target = (
            "Success target:" in report_written_text
            and "Privacy: review private reports before sharing" in report_written_text
            and "aggregate metrics can still reveal workflow clues"
            in report_written_text
            and "Next commands:" in report_written_text
            and str(report_payload.get("success_target", {}).get("metric"))
            in report_written_text
            and all(
                str(command) in report_written_text
                for command in report_payload.get("next_commands", [])
            )
            and all(
                str(command) in report_written_text
                for command in report_payload.get("next_command_templates", [])
            )
        )
        report_review_path = report_payload.get("review_path")
        report_feedback_handoff = report_payload.get("feedback_handoff")
        report_feedback_text = json.dumps(report_feedback_handoff)
        report_has_feedback_handoff = (
            isinstance(report_feedback_handoff, dict)
            and report_feedback_handoff.get("runbook") == "docs/PUBLIC_TOUR_FEEDBACK.md"
            and report_feedback_handoff.get("issue_template")
            == ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
            and "synthetic or reviewed-redacted aggregate evidence"
            in str(report_feedback_handoff.get("evidence_rule"))
            and "codex-observe report JSON or Markdown" in report_feedback_text
            and "private prompts" in report_feedback_text
            and "## Feedback Handoff" in report_markdown_text
            and "docs/PUBLIC_TOUR_FEEDBACK.md" in report_markdown_text
            and ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
            in report_markdown_text
        )
        report_checklist = report_payload.get("next_run_checklist")
        report_has_next_run_checklist = (
            isinstance(report_checklist, list)
            and len(report_checklist) >= 3
            and all(
                isinstance(step, dict)
                and step.get("phase")
                and step.get("action")
                and step.get("success_check")
                for step in report_checklist
            )
            and "## Next Run Checklist" in report_markdown_text
            and "Before next run" in report_markdown_text
            and "After next run" in report_markdown_text
        )
        report_brief = report_payload.get("next_run_brief")
        report_has_next_run_brief = (
            isinstance(report_brief, dict)
            and report_brief.get("habit")
            and report_brief.get("target_metric")
            and "Next Codex run plan" in str(report_brief.get("copy_prompt") or "")
            and "## Next Run Brief" in report_markdown_text
            and "Next Codex run plan:" in report_markdown_text
        )
        report_has_review_path = (
            isinstance(report_review_path, list)
            and len(report_review_path) >= 4
            and all(
                isinstance(step, dict)
                and step.get("label")
                and step.get("command")
                and step.get("success_check")
                for step in report_review_path
            )
            and any(
                "codex-observe compare --before-report" in str(step.get("command"))
                for step in report_review_path
                if isinstance(step, dict)
            )
        )
        report_has_cost_profile = (
            out_path.exists()
            and out_path.stat().st_size > 0
            and json_out_path.exists()
            and json_out_path.stat().st_size > 0
            and report_payload.get("schema_version") == REPORT_SCHEMA_VERSION
            and "## Cost Profile" in report_markdown_text
            and "## Opportunity Stack" in report_markdown_text
            and "## Recommended Action" in report_markdown_text
            and "Action:" in report_markdown_text
            and "Target:" in report_markdown_text
            and "## Next Run Success Target" in report_markdown_text
            and "## Review Path" in report_markdown_text
            and "Save this report JSON" in report_markdown_text
            and "Usage snapshots:" in report_markdown_text
            and "usage_snapshots" in report_json_text
            and report_payload.get("ingest_scope", {}).get("sampled") is False
            and report_payload.get("ingest_scope", {}).get("scan_limit", {}).get("mode")
            == "all"
            and '"ingest_scope"' in report_json_text
            and "## Follow-up Commands" in report_markdown_text
            and "codex-observe sessions --db" in report_markdown_text
            and "codex-observe compare --before-report" in report_markdown_text
            and "Target: below" in report_markdown_text
            and "Scale: " in report_markdown_text
            and "Largest thread share" in report_markdown_text
            and "## Triage" in report_markdown_text
            and "Risk level:" in report_markdown_text
            and "largest_thread_share_pct" in summary
            and "repeated_prompt_share_pct" in summary
            and "uncached_input_share_pct" in summary
            and triage.get("risk_level")
            and triage.get("next_action")
            and report_payload.get("next_action_detail", {}).get("action")
            and report_payload.get("success_target", {}).get("metric")
            and report_payload.get("success_target", {}).get("target_value") is not None
            and report_has_review_path
            and report_has_next_run_checklist
            and report_has_next_run_brief
            and report_has_feedback_handoff
            and report_confirmation_has_success_target
            and any(
                str(command).startswith("codex-observe sessions --db ")
                and str(command).endswith(" --json")
                for command in report_payload.get("next_commands", [])
            )
            and any(
                "codex-observe compare --before-report" in str(command)
                for command in report_payload.get("next_command_templates", [])
            )
            and report_payload.get("opportunities", [{}])[0].get("Driver")
            and '"opportunities"' in report_json_text
            and '"next_action_detail"' in report_json_text
            and '"success_target"' in report_json_text
            and '"next_commands"' in report_json_text
            and '"next_command_templates"' in report_json_text
            and '"review_path"' in report_json_text
            and '"next_run_checklist"' in report_json_text
            and '"next_run_brief"' in report_json_text
            and '"feedback_handoff"' in report_json_text
        )
        add(
            "aggregate report",
            report_has_cost_profile,
            f"{out_path}; {json_out_path}; recommended action, usage-snapshot summary, cost profile, opportunity stack, terminal success target, terminal privacy warning, next-run checklist, next-run brief, terminal next commands, triage, review path, feedback handoff, follow-up commands, structured next action, ingest scope, and schema verified",
        )
        comparison = compare_reports(report, report)
        comparison_out = out_path.with_name("run-comparison.md")
        comparison_json_out = out_path.with_name("run-comparison.json")
        comparison_markdown_text = comparison_markdown(comparison)
        comparison_json_text = comparison_json(comparison)
        comparison_out.write_text(comparison_markdown_text, encoding="utf-8")
        comparison_json_out.write_text(comparison_json_text, encoding="utf-8")
        comparison_payload = json.loads(comparison_json_text)
        comparison_written_text = "\n".join(
            comparison_written_lines(comparison_out, comparison)
        )
        comparison_confirmation_has_validation_command = (
            "Next validation command:" in comparison_written_text
            and "Privacy: review private comparison reports before sharing"
            in comparison_written_text
            and "aggregate deltas can still reveal workflow clues"
            in comparison_written_text
            and "Next commands:" in comparison_written_text
            and "codex-observe report --db <db> --session-id <next-session-id>"
            in comparison_written_text
            and all(
                str(command) in comparison_written_text
                for command in comparison_payload.get("next_command_templates", [])
            )
        )
        comparison_review_path = comparison_payload.get("review_path")
        comparison_feedback_handoff = comparison_payload.get("feedback_handoff")
        comparison_feedback_text = json.dumps(comparison_feedback_handoff)
        comparison_has_feedback_handoff = (
            isinstance(comparison_feedback_handoff, dict)
            and comparison_feedback_handoff.get("runbook")
            == "docs/PUBLIC_TOUR_FEEDBACK.md"
            and comparison_feedback_handoff.get("issue_template")
            == ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
            and "synthetic or reviewed-redacted aggregate evidence"
            in str(comparison_feedback_handoff.get("evidence_rule"))
            and "codex-observe comparison JSON or Markdown" in comparison_feedback_text
            and "private prompts" in comparison_feedback_text
            and "## Feedback Handoff" in comparison_markdown_text
            and "docs/PUBLIC_TOUR_FEEDBACK.md" in comparison_markdown_text
            and ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
            in comparison_markdown_text
        )
        comparison_has_review_path = (
            isinstance(comparison_review_path, list)
            and len(comparison_review_path) >= 5
            and all(
                isinstance(step, dict)
                and step.get("label")
                and step.get("command")
                and step.get("success_check")
                for step in comparison_review_path
            )
            and any(
                "codex-observe compare --before-report" in str(step.get("command"))
                for step in comparison_review_path
                if isinstance(step, dict)
            )
            and any(
                str(step.get("command")) == "docs/PUBLIC_TOUR_FEEDBACK.md"
                for step in comparison_review_path
                if isinstance(step, dict)
            )
        )
        comparison_has_quick_read = (
            comparison.get("verdict") == "unchanged"
            and comparison_out.exists()
            and comparison_out.stat().st_size > 0
            and comparison_json_out.exists()
            and comparison_json_out.stat().st_size > 0
            and comparison_payload.get("schema_version") == COMPARISON_SCHEMA_VERSION
            and comparison_payload.get("ingest_scope", {}).get("sampled") is False
            and comparison_payload.get("ingest_scope", {})
            .get("before", {})
            .get("scan_limit", {})
            .get("mode")
            == "all"
            and comparison_payload.get("ingest_scope", {})
            .get("after", {})
            .get("scan_limit", {})
            .get("mode")
            == "all"
            and "## Quick Read" in comparison_markdown_text
            and "Verdict: unchanged" in comparison_markdown_text
            and "## Recommended Action" in comparison_markdown_text
            and "Action:" in comparison_markdown_text
            and "Target:" in comparison_markdown_text
            and "## Triage Risk" in comparison_markdown_text
            and "Direction: unchanged" in comparison_markdown_text
            and "## Opportunity Change" in comparison_markdown_text
            and "diagnostics" in comparison_markdown_text
            and "| Metric | Before | After | Delta | % change | Direction |"
            in comparison_markdown_text
            and "Recommended next step:" in comparison_markdown_text
            and "## Review Path" in comparison_markdown_text
            and "Read the verdict" in comparison_markdown_text
            and "File safe feedback" in comparison_markdown_text
            and "## Follow-up Commands" in comparison_markdown_text
            and "codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json"
            in comparison_markdown_text
            and comparison.get("recommendation")
            and comparison.get("recommendation_detail", {}).get("action")
            and comparison_has_review_path
            and comparison_has_feedback_handoff
            and comparison_confirmation_has_validation_command
            and any(
                "codex-observe compare --before-report" in str(command)
                for command in comparison_payload.get("next_command_templates", [])
            )
            and '"verdict": "unchanged"' in comparison_json_text
            and '"recommendation"' in comparison_json_text
            and '"recommendation_detail"' in comparison_json_text
            and '"next_command_templates"' in comparison_json_text
            and '"review_path"' in comparison_json_text
            and '"feedback_handoff"' in comparison_json_text
            and '"opportunity_change"' in comparison_json_text
            and '"ingest_scope"' in comparison_json_text
            and comparison_payload.get("opportunity_change", {}).get("summary")
            and '"delta_pct"' in comparison_json_text
        )
        add(
            "aggregate comparison",
            comparison_has_quick_read,
            f"{comparison_out}; {comparison_json_out}; quick read, recommended action, triage risk, usage-snapshot deltas, opportunity change, terminal validation command, terminal privacy warning, terminal next commands, structured recommendation, review path, feedback handoff, follow-up commands, ingest scope, and schema verified",
        )
    except (FileNotFoundError, ValueError, KeyError) as exc:
        add("aggregate report", False, str(exc))

    for relative in RELEASE_REQUIRED_FILES:
        path = root / relative
        add(
            f"required file: {relative}",
            path.exists() and path.stat().st_size > 0,
            relative,
        )

    project_version = pyproject_version(root)
    add(
        "version metadata",
        bool(project_version) and project_version == __version__,
        f"pyproject={project_version or 'missing'}, package={__version__}",
    )

    try:
        version_result = subprocess.run(
            [sys.executable, "-m", "codex_observe.cli", "--version"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        version_output = version_result.stdout.strip()
        add(
            "CLI version command",
            version_result.returncode == 0
            and version_output == f"codex-observe {__version__}",
            version_output
            or version_result.stderr.strip()
            or f"exit {version_result.returncode}",
        )
    except OSError as exc:
        add("CLI version command", False, str(exc))

    self_check = self_check_payload()
    self_check_checks = self_check.get("checks", [])
    self_check_ok = (
        self_check.get("schema_version") == SELF_CHECK_SCHEMA_VERSION
        and self_check.get("status") == "ok"
        and self_check.get("privacy", {}).get("raw_content_included") is False
        and self_check.get("privacy", {}).get("scans_sessions") is False
        and isinstance(self_check_checks, list)
        and {
            str(check.get("name"))
            for check in self_check_checks
            if isinstance(check, dict)
        }
        == {"python", "package_version", "dashboard_module"}
        and isinstance(self_check.get("next_commands"), list)
        and any(
            "codex-observe tour" in str(command)
            for command in self_check.get("next_commands", [])
        )
        and any(
            "private-validate" in str(command)
            for command in self_check.get("next_commands", [])
        )
        and "sessions" not in self_check
        and "counts" not in self_check
    )
    add(
        "source install self-check",
        self_check_ok,
        "schema, supported runtime, package version, dashboard module, privacy metadata, and next commands verified"
        if self_check_ok
        else "self-check schema, runtime, package version, dashboard module, privacy metadata, next commands, or privacy-safe payload missing",
    )
    paths_payload_check = paths_payload(
        db_path=actual_db_path, sessions_path=sessions_path
    )
    paths_lines_text = "\n".join(
        paths_lines(db_path=actual_db_path, sessions_path=sessions_path)
    )
    paths_commands = paths_payload_check.get("next_commands", [])
    paths_review_path = paths_payload_check.get("review_path", [])
    paths_ok = (
        paths_payload_check.get("schema_version") == PATHS_SCHEMA_VERSION
        and paths_payload_check.get("sessions_path")
        == str(Path(sessions_path).expanduser())
        and paths_payload_check.get("sessions_path_exists") is True
        and paths_payload_check.get("database")
        == str(Path(actual_db_path).expanduser())
        and paths_payload_check.get("database_exists") is True
        and paths_payload_check.get("privacy", {}).get("raw_content_included") is False
        and paths_payload_check.get("privacy", {}).get("scans_sessions") is False
        and paths_payload_check.get("privacy", {}).get("review_required_before_sharing")
        is True
        and isinstance(paths_commands, list)
        and any("--newest-files 25" in str(command) for command in paths_commands)
        and any("codex-observe doctor" in str(command) for command in paths_commands)
        and isinstance(paths_review_path, list)
        and any(
            "Sample newest private logs" == str(step.get("label"))
            for step in paths_review_path
            if isinstance(step, dict)
        )
        and "Privacy: this command does not scan logs" in paths_lines_text
        and "Next commands:" in paths_lines_text
    )
    add(
        "paths handoff",
        paths_ok,
        "schema, existence checks, privacy no-scan metadata, sampled ingest command, review path, and text handoff verified"
        if paths_ok
        else "paths schema, existence checks, privacy no-scan metadata, sampled ingest command, review path, or text handoff missing",
    )

    private_validate_dir = Path(actual_db_path).with_name("private-validate-audit")
    private_validate_status, private_validate = private_validate_payload(
        sessions_path,
        output_dir=private_validate_dir,
        newest_files=25,
    )
    private_validate_artifacts = private_validate.get("artifacts", {})
    private_validate_privacy = private_validate.get("privacy", {})
    private_validate_ok = (
        private_validate_status == 0
        and private_validate.get("schema_version") == PRIVATE_VALIDATE_SCHEMA_VERSION
        and private_validate.get("status") == "ok"
        and private_validate.get("sessions_path_exists") is True
        and private_validate.get("database_exists") is True
        and private_validate.get("newest_files") == 25
        and private_validate.get("report_written") is True
        and private_validate_privacy.get("raw_content_included") is False
        and private_validate_privacy.get("terminal_output_includes_counts") is False
        and private_validate_privacy.get("review_required_before_sharing") is True
        and isinstance(private_validate_artifacts, dict)
        and str(private_validate_artifacts.get("database", "")).endswith(
            "real-sessions.sqlite"
        )
        and str(private_validate_artifacts.get("report_json", "")).endswith(
            "real-run-report.json"
        )
        and isinstance(private_validate.get("next_commands"), list)
        and any(
            "codex-observe serve" in str(command)
            for command in private_validate.get("next_commands", [])
        )
        and "counts" not in private_validate
        and "sessions" not in private_validate
        and "recommended_session" not in private_validate
    )
    add(
        "private validation handoff",
        private_validate_ok,
        "schema, bounded sample, ignored artifacts, report export, privacy metadata, and dashboard next command verified"
        if private_validate_ok
        else "private validation schema, bounded sample, artifacts, report export, privacy metadata, dashboard next command, or privacy-safe top-level payload missing",
    )

    try:
        report_help = subprocess.run(
            [sys.executable, "-m", "codex_observe.cli", "report", "--help"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        compare_help = subprocess.run(
            [sys.executable, "-m", "codex_observe.cli", "compare", "--help"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        help_text = report_help.stdout + compare_help.stdout
        help_errors = report_help.stderr + compare_help.stderr
        help_ok = (
            report_help.returncode == 0
            and compare_help.returncode == 0
            and "ranked opportunity stack" in report_help.stdout
            and "opportunity-change movement" in compare_help.stdout
        )
        add(
            "CLI help product concepts",
            help_ok,
            "report opportunity stack and compare opportunity-change help verified"
            if help_ok
            else (help_errors.strip() or help_text.strip() or "help output missing"),
        )
    except OSError as exc:
        add("CLI help product concepts", False, str(exc))
    readme = (
        (root / "README.md").read_text(encoding="utf-8")
        if (root / "README.md").exists()
        else ""
    )
    add(
        "README distribution link",
        "docs/DISTRIBUTION.md" in readme,
        "docs/DISTRIBUTION.md",
    )
    add(
        "README privacy commands",
        all(
            cmd in readme
            for cmd in [
                "codex-observe tour",
                "codex-observe tour --json",
                "codex-observe paths",
                "codex-observe doctor",
                "codex-observe sessions",
                "codex-observe report",
                "codex-observe compare",
            ]
        ),
        "paths/tour/doctor/sessions/report/compare",
    )

    tour_payload = public_tour_payload(actual_db_path)
    tour_lines_text = "\n".join(public_tour_lines(actual_db_path))
    tour_commands = tour_payload.get("next_commands")
    tour_steps = tour_payload.get("steps", [])
    tour_review_path = tour_payload.get("review_path", [])
    tour_feedback_handoff = tour_payload.get("feedback_handoff", {})
    tour_feedback_handoff_ok = (
        isinstance(tour_feedback_handoff, dict)
        and tour_feedback_handoff.get("runbook") == "docs/PUBLIC_TOUR_FEEDBACK.md"
        and tour_feedback_handoff.get("issue_template")
        == ".github/ISSUE_TEMPLATE/public_tour_feedback.yml"
        and "synthetic or reviewed-redacted evidence"
        in str(tour_feedback_handoff.get("evidence_rule"))
        and "Feedback handoff:" in tour_lines_text
        and "Safe feedback sources:" in tour_lines_text
        and "Do not collect:" in tour_lines_text
        and ".github/ISSUE_TEMPLATE/public_tour_feedback.yml" in tour_lines_text
        and "private prompts" in json.dumps(tour_feedback_handoff)
        and "private prompts" in tour_lines_text
        and "reviewer evidence bundle" in tour_lines_text
    )
    tour_review_path_ok = (
        isinstance(tour_review_path, list)
        and len(tour_review_path) >= 6
        and all(
            isinstance(item, dict)
            and item.get("step")
            and item.get("label")
            and item.get("command")
            and item.get("success_check")
            for item in tour_review_path
        )
        and any(
            str(item.get("command")) == f"codex-observe sessions --db {actual_db_path}"
            for item in tour_review_path
            if isinstance(item, dict)
        )
        and any(
            "docs/PUBLIC_TOUR_FEEDBACK.md" == str(item.get("command"))
            for item in tour_review_path
            if isinstance(item, dict)
        )
    )
    tour_evidence = [
        evidence
        for step in tour_steps
        if isinstance(step, dict)
        for evidence in step.get("evidence", [])
        if isinstance(evidence, str)
    ]
    tour_success_checks = [
        check
        for step in tour_steps
        if isinstance(step, dict)
        for check in step.get("success_checks", [])
        if isinstance(check, str)
    ]
    tour_steps_have_success_checks = bool(tour_steps) and all(
        isinstance(step, dict)
        and isinstance(step.get("success_checks"), list)
        and bool(step.get("success_checks"))
        for step in tour_steps
    )
    tour_ok = (
        tour_payload.get("schema_version") == TOUR_SCHEMA_VERSION
        and tour_payload.get("database") == actual_db_path
        and tour_payload.get("privacy", {}).get("private_log_required") is False
        and isinstance(tour_commands, list)
        and "Next commands:" in tour_lines_text
        and all(command in tour_lines_text for command in tour_commands)
        and f"codex-observe demo --db {actual_db_path}" in tour_commands
        and f"codex-observe doctor --db {actual_db_path}" in tour_commands
        and f"codex-observe doctor --db {actual_db_path} --json" in tour_commands
        and f"codex-observe sessions --db {actual_db_path}" in tour_commands
        and f"codex-observe sessions --db {actual_db_path} --json" in tour_commands
        and "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json"
        in tour_commands
        and "codex-observe evidence-bundle --out .artifacts/public-evidence"
        in tour_commands
        and tour_steps_have_success_checks
        and tour_review_path_ok
        and tour_feedback_handoff_ok
        and any("ranked opportunity stack" in item for item in tour_evidence)
        and any("opportunity-change" in item for item in tour_evidence)
        and any("docs/PUBLIC_TOUR_FEEDBACK.md" in item for item in tour_evidence)
        and any("key findings" in item for item in tour_evidence)
        and any("review_summary" in item for item in tour_evidence)
        and any("reviewed-redacted" in item for item in tour_evidence)
        and any("comparison metric delta cards" in item for item in tour_evidence)
        and any("report sampled-ingest warning" in item for item in tour_evidence)
        and any("comparison sampled-ingest warning" in item for item in tour_evidence)
        and any(
            "report and comparison download controls" in item for item in tour_evidence
        )
        and any("next-run validation, compare" in item for item in tour_evidence)
        and any(
            "baseline Markdown, baseline JSON, next-run JSON" in item
            for item in tour_success_checks
        )
        and all(
            any(expected in item for item in tour_evidence)
            for expected in EXPECTED_TOUR_QUICK_READ_TEXT
        )
        and any("failed_checks is empty" in item for item in tour_success_checks)
        and any("layout overflow" in item for item in tour_success_checks)
        and any("explicit publication approval" in item for item in tour_success_checks)
    )
    add(
        "public tour JSON",
        tour_ok,
        "schema, privacy, database, evidence bundle, recommended-action evidence, terminal handoff evidence, terminal validation evidence, dashboard quick-read, sampled-scope, session validation-loop evidence, and comparison review-path evidence, top-level review path, terminal feedback handoff, text next commands, per-step success checks, and next commands verified"
        if tour_ok
        else "tour JSON schema_version, privacy, database, evidence bundle key findings, recommended-action evidence, terminal handoff evidence, terminal validation evidence, dashboard quick-read evidence, sampled-scope evidence, session validation-loop evidence, comparison review-path evidence, comparison metric delta evidence, report/comparison-download evidence, feedback evidence, top-level review_path, terminal feedback_handoff, text next commands, per-step success checks, or next_commands missing",
    )

    ignore_failures = private_artifact_ignore_failures(root)
    add(
        "private artifact ignores",
        not ignore_failures,
        "sqlite, artifacts, env, cache, and build outputs ignored"
        if not ignore_failures
        else "; ".join(ignore_failures[:3]),
    )

    dev_failures = dev_tooling_failures(root)
    add(
        "dev tooling metadata",
        not dev_failures,
        "dev extra, CI, docs, and evidence artifacts aligned"
        if not dev_failures
        else "; ".join(dev_failures[:3]),
    )

    ci_bundle_failures = ci_evidence_bundle_failures(root)
    add(
        "CI reviewer evidence bundle",
        not ci_bundle_failures,
        "CI generates and uploads reviewer public evidence bundle"
        if not ci_bundle_failures
        else "; ".join(ci_bundle_failures[:3]),
    )

    if check_public_evidence_bundle:
        public_bundle_dir = (
            Path(public_evidence_dir).expanduser()
            if public_evidence_dir is not None
            else root / ".artifacts" / "public-evidence"
        )
        public_bundle_failures = public_evidence_bundle_artifact_failures(
            root, public_bundle_dir
        )
        add(
            "public evidence bundle artifacts",
            not public_bundle_failures,
            "manifest, terminal and reviewer README action plan, key findings, review checklist, feedback handoff, feedback runbook, feedback issue template, reproduce-local commands, validation commands, limitations doc, aggregate reports, and audit artifact verified"
            if not public_bundle_failures
            else "; ".join(public_bundle_failures[:3]),
        )

    issue_template_drift = issue_template_failures(root)
    add(
        "issue templates",
        not issue_template_drift,
        "issue templates require demoable evidence, visual QA, public-tour feedback, privacy review, and limitations checks"
        if not issue_template_drift
        else "; ".join(issue_template_drift[:3]),
    )

    tracking_failures = tracking_doc_failures(root)
    add(
        "tracking snapshot",
        not tracking_failures,
        "GitHub issue snapshot, local draft state, approval gate, and push cadence documented"
        if not tracking_failures
        else "; ".join(tracking_failures[:3]),
    )
    workflow_doc_failures = release_workflow_doc_failures(root)
    add(
        "release workflow docs",
        not workflow_doc_failures,
        "real-log checkpoint, privacy gate, visual QA evidence, and text hygiene aligned"
        if not workflow_doc_failures
        else "; ".join(workflow_doc_failures[:3]),
    )

    visual_manifest_failures = visual_manifest_evidence_failures(root)
    add(
        "visual QA manifest evidence",
        not visual_manifest_failures,
        f"{VISUAL_MANIFEST.as_posix()}; "
        f"{(VISUAL_MANIFEST.parent / EXPECTED_VISUAL_SCREENSHOTS['desktop']).as_posix()}; "
        f"{(VISUAL_MANIFEST.parent / EXPECTED_VISUAL_SCREENSHOTS['narrow']).as_posix()}; "
        "visual manifest schema and contract, screenshots, empty states, layout review, risk labels, sidebar session details, risk distribution, metric cards, dashboard quick reads, report and comparison downloads, report scope-warning evidence, comparison preview, comparison scope-warning evidence, comparison review path, deltas, operator briefing, next review path, next-run checklist, next-run brief, safe feedback handoff, and success target verified"
        if not visual_manifest_failures
        else "; ".join(visual_manifest_failures[:3]),
    )
    redaction_privacy_failures = redaction_cli_privacy_failures(root)
    add(
        "redaction validation privacy",
        not redaction_privacy_failures,
        "privacy-safe JSON failure uses error codes, does not touch output, and verify-only rejects raw IDs"
        if not redaction_privacy_failures
        else "; ".join(redaction_privacy_failures[:3]),
    )

    backlog_failures = backlog_draft_failures(root)
    add(
        "planning backlog",
        not backlog_failures,
        f"{len(active_backlog_drafts(root))} current draft records validated; completed local drafts retired"
        if not backlog_failures
        else "; ".join(backlog_failures[:3]),
    )

    ok = all(bool(check["ok"]) for check in checks)
    failed_checks = failed_audit_checks(checks)
    required_commands = list(RELEASE_REQUIRED_COMMANDS) if ok else []
    audit = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "database": actual_db_path,
        "report": report_out,
        "checks": checks,
        "failed_checks": failed_checks,
        "required_commands": required_commands,
        "next": release_audit_next_message(ok, failed_checks),
    }
    return (0 if ok else 1), audit


def release_audit_lines(
    db_path: str = DEFAULT_DEMO_DB,
    sessions_path: str = DEFAULT_DEMO_SESSIONS,
    report_out: str = ".artifacts/demo/run-report.md",
    *,
    public_evidence_dir: str | Path | None = None,
) -> tuple[int, list[str]]:
    status, audit = release_audit_report(
        db_path,
        sessions_path,
        report_out,
        public_evidence_dir=public_evidence_dir,
    )
    lines = [f"Status: {audit['status']}"]
    for check in audit["checks"]:
        marker = "OK" if check["ok"] else "FAIL"
        detail = f" - {check['detail']}" if check.get("detail") else ""
        lines.append(f"[{marker}] {check['name']}{detail}")
    if audit.get("failed_checks"):
        lines.append("Failed checks:")
        for check in audit["failed_checks"]:
            detail = f" - {check['detail']}" if check.get("detail") else ""
            lines.append(f"- {check['name']}{detail}")
    if audit.get("required_commands"):
        lines.append("Required commands:")
        lines.extend(f"- {command}" for command in audit["required_commands"])
    lines.append(f"Next: {audit['next']}")
    return status, lines


def sessions_missing_json_payload(db_path: str) -> dict[str, object]:
    db_arg = _command_arg(db_path)
    return {
        "schema_version": SESSIONS_SCHEMA_VERSION,
        "database": db_path,
        "status": "missing",
        "sessions": [],
        "total_sessions": 0,
        "returned_sessions": 0,
        "truncated": False,
        "limit": DEFAULT_SESSIONS_LIMIT,
        "risk_distribution": {"high": 0, "medium": 0, "low": 0, "unknown": 0},
        "recommended_session": None,
        "recommendation_detail": None,
        "review_path": sessions_review_path(db_path),
        "next": (
            f"run `codex-observe demo --db {db_arg}` for synthetic data or "
            f"`codex-observe ingest ~/.codex/sessions --db {db_arg}` for local logs."
        ),
        "next_commands": sessions_next_commands(db_path),
    }


def session_driver_summary(recommended: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "driver": "largest_thread_share_pct",
            "label": "Largest thread share",
            "value": recommended.get("largest_thread_share_pct"),
            "display": f"{float(recommended.get('largest_thread_share_pct') or 0):.1f}%",
        },
        {
            "driver": "repeated_prompt_share_pct",
            "label": "Repeated prompt share",
            "value": recommended.get("repeated_prompt_share_pct"),
            "display": f"{float(recommended.get('repeated_prompt_share_pct') or 0):.1f}%",
        },
        {
            "driver": "uncached_input_share_pct",
            "label": "Uncached input share",
            "value": recommended.get("uncached_input_share_pct"),
            "display": f"{float(recommended.get('uncached_input_share_pct') or 0):.1f}%",
        },
        {
            "driver": "largest_tool_output_chars",
            "label": "Largest tool output",
            "value": recommended.get("largest_tool_output_chars"),
            "display": f"{fmt_short(recommended.get('largest_tool_output_chars') or 0)} chars",
        },
    ]


def session_recommendation_detail(recommended: dict[str, object]) -> dict[str, object]:
    return {
        "action": "export_recommended_session_report",
        "target_type": "session",
        "target": recommended.get("session_id"),
        "reason": "Highest aggregate triage risk, with latest run used as the tie-breaker.",
        "ranked_by": ["triage_risk", "last_seen"],
        "risk": recommended.get("triage_risk"),
        "drivers": {
            "largest_thread_share_pct": recommended.get("largest_thread_share_pct"),
            "repeated_prompt_share_pct": recommended.get("repeated_prompt_share_pct"),
            "uncached_input_share_pct": recommended.get("uncached_input_share_pct"),
            "largest_tool_output_chars": recommended.get("largest_tool_output_chars"),
        },
        "driver_summary": session_driver_summary(recommended),
        "success_target_preview": session_success_target_preview(recommended),
    }


def sessions_review_path(
    db_path: str, session_id: str | None = None
) -> list[dict[str, str]]:
    db_arg = _command_arg(db_path)
    if not session_id:
        return [
            {
                "label": "Create demo data",
                "command": f"codex-observe demo --db {db_arg}",
                "success_check": "sessions JSON returns status ok with a recommended_session.",
            },
            {
                "label": "Ingest local logs",
                "command": f"codex-observe ingest ~/.codex/sessions --db {db_arg}",
                "success_check": "doctor reports a valid populated database.",
            },
        ]
    return [
        {
            "label": "Save report Markdown",
            "command": f"codex-observe report --db {db_arg} --session-id {session_id} --out run-report.md",
            "success_check": "Markdown includes Recommended Action and Next Run Success Target.",
        },
        {
            "label": "Save report JSON",
            "command": f"codex-observe report --db {db_arg} --session-id {session_id} --format json --out run-report.json",
            "success_check": "JSON includes schema_version, success_target, and next_action_detail.",
        },
        {
            "label": "Validate next run",
            "command": f"codex-observe report --db {db_arg} --session-id <next-session-id> --format json --out next-run-report.json",
            "success_check": "The next report can be compared against run-report.json.",
        },
        {
            "label": "Compare workflow change",
            "command": "codex-observe compare --before-report run-report.json --after-report next-run-report.json --out run-comparison.md",
            "success_check": "Comparison includes a verdict, triage movement, and next validation command.",
        },
        {
            "label": "File safe feedback",
            "command": "docs/PUBLIC_TOUR_FEEDBACK.md",
            "success_check": "Feedback excludes private prompts, tool output, local paths, and raw logs.",
        },
    ]


def sessions_json_payload(
    db_path: str, limit: int | None = DEFAULT_SESSIONS_LIMIT
) -> dict[str, object]:
    summaries = session_summaries(db_path)
    effective_limit = None if limit is None else max(1, int(limit))
    display_limit = len(summaries) if effective_limit is None else effective_limit
    displayed = summaries[:display_limit]
    payload: dict[str, object] = {
        "schema_version": SESSIONS_SCHEMA_VERSION,
        "database": db_path,
        "status": "ok" if summaries else "empty",
        "sessions": displayed,
        "total_sessions": len(summaries),
        "returned_sessions": len(displayed),
        "truncated": len(displayed) < len(summaries),
        "limit": effective_limit,
        "risk_distribution": session_risk_distribution(summaries),
        "ingest_scope": latest_ingest_scope(db_path),
    }
    if summaries:
        recommended = summaries[0]
        recommended_session_id = str(recommended["session_id"])
        payload["recommended_session"] = recommended
        payload["recommendation_detail"] = session_recommendation_detail(recommended)
        payload["review_path"] = sessions_review_path(db_path, recommended_session_id)
        payload["next"] = session_report_hint(db_path, recommended_session_id)
        payload["next_commands"] = sessions_next_commands(
            db_path, recommended_session_id
        )
    else:
        payload["recommended_session"] = None
        payload["recommendation_detail"] = None
        payload["review_path"] = sessions_review_path(db_path)
        payload["next"] = (
            f"run `codex-observe ingest ~/.codex/sessions --db {_command_arg(db_path)}` or `codex-observe demo --db {_command_arg(db_path)}`."
        )
        payload["next_commands"] = sessions_next_commands(db_path)
    return payload


def public_tour_steps(db_path: str = DEFAULT_DEMO_DB) -> list[dict[str, object]]:
    return [
        {
            "title": "Create demo data and open the dashboard",
            "evidence": [
                "synthetic data path requires no private logs",
                "dashboard opens with representative high- and low-risk runs",
                "dashboard quick reads cover Overview operator briefing, Agent detail thread brief, Timeline quick read, Tools quick read, Duplication quick read, and Raw tables data inventory",
            ],
            "success_checks": [
                "plain demo output includes terminal Review path and Next commands guidance",
                "demo JSON reports status ok with schema_version codex-observe.demo.v1",
                "dashboard opens on the synthetic database without private logs",
            ],
            "commands": [
                "codex-observe demo --serve --host 127.0.0.1 --port 8501",
                f"codex-observe demo --db {db_path}",
                "codex-observe demo --json",
            ],
        },
        {
            "title": "Verify the demo database contract",
            "evidence": [
                "plain doctor output includes terminal Review path and Next commands guidance",
                "doctor JSON includes schema_version, structured next_commands, and review_path",
                "recovery hints preserve the selected database path",
            ],
            "success_checks": [
                "plain doctor output includes copy-pasteable terminal Next commands",
                "doctor JSON status is ok for the demo database",
                "next_commands include sessions and serve commands for the same database",
                "review_path points to sessions JSON, dashboard inspection, and report export",
            ],
            "commands": [
                f"codex-observe doctor --db {db_path}",
                f"codex-observe doctor --db {db_path} --json",
            ],
        },
        {
            "title": "List aggregate-only sessions and the recommended high-risk run",
            "evidence": [
                "recommended_session chooses the highest-risk run",
                "plain-text sessions output includes Snapshots and Tool out columns plus a recommended-action block with top aggregate drivers, including largest tool output",
                "recommendation_detail explains the risk, recency tie-breakers, structured aggregate drivers, and ordered driver_summary display labels",
                "plain-text sessions output includes terminal Next commands for baseline report export, next-run validation, and comparison",
                "review_path turns the recommendation into report, next-run validation, compare, and safe-feedback steps",
            ],
            "success_checks": [
                "recommended_session targets the highest-risk run, not merely the latest run",
                "recommendation_detail.driver_summary includes display labels for aggregate drivers",
                "plain-text sessions output includes Next commands for baseline Markdown, baseline JSON, next-run JSON, and comparison",
                "review_path includes report JSON, next-run validation, comparison, and safe-feedback steps",
            ],
            "commands": [
                f"codex-observe sessions --db {db_path}",
                f"codex-observe sessions --db {db_path} --json",
            ],
        },
        {
            "title": "Export shareable aggregate reports",
            "evidence": [
                "reports include quick-read, triage, top-level Recommended Action, and ranked opportunity stack",
                "report terminal confirmation includes next action and Success target",
                "JSON includes schema_version, opportunities, success_target, and next_action_detail",
                "dashboard report sampled-ingest warning labels bounded private evidence before downloading artifacts",
            ],
            "success_checks": [
                "Markdown report includes Recommended Action and Next Run Success Target sections",
                "JSON report includes schema_version, success_target, next_action_detail, and follow-up commands",
            ],
            "commands": [
                f"codex-observe report --db {db_path} --out .artifacts/demo/run-report.md",
                f"codex-observe report --db {db_path} --format json --out .artifacts/demo/run-report.json",
            ],
        },
        {
            "title": "Compare reports without exposing prompts or tool output",
            "evidence": [
                "comparison highlights triage-risk and opportunity-change movement",
                "comparison terminal confirmation includes Next validation command",
                "recommendation_detail targets persisted or regressed aggregate drivers",
                "dashboard comparison review path turns verdicts into validation steps before downloading artifacts",
                "dashboard comparison metric delta cards show the largest aggregate changes before downloading artifacts",
                "dashboard comparison sampled-ingest warning labels bounded private evidence before downloading artifacts",
            ],
            "success_checks": [
                "Markdown comparison includes opportunity-change movement and next validation command",
                "dashboard comparison review path includes verdict, recommendation, next-run export, comparison, and safe-feedback steps",
                "JSON comparison includes schema_version, recommendation_detail, and next_command_templates",
            ],
            "commands": [
                "codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md",
                "codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --format json --out .artifacts/demo/run-comparison.json",
            ],
        },
        {
            "title": "Capture and verify UI evidence",
            "evidence": [
                "visual manifest records desktop and narrow screenshots",
                "layout review, sidebar risk labels, sidebar session details, metric cards, report sampled-ingest warning evidence, comparison metric delta cards, comparison sampled-ingest warning evidence, comparison review path, report and comparison download controls, operator briefing, next review path, safe feedback handoff, dashboard quick reads, and success target are verified",
                "tab checks cover Agent detail thread brief, Timeline quick read, Tools quick read, Duplication quick read, and Raw tables data inventory",
            ],
            "success_checks": [
                "visual manifest verifies desktop and narrow screenshots",
                "manifest verification records no layout overflow, clipped text, or Streamlit exceptions",
            ],
            "commands": [
                "python scripts/visual_qa.py",
                "python scripts/visual_qa.py --verify-manifest .artifacts/visual/visual-qa-manifest.json",
            ],
        },
        {
            "title": "Create a reviewer-facing evidence bundle",
            "evidence": [
                "bundle text output and README surface key findings before artifact paths",
                "LIMITATIONS.md carries known boundaries and approval-gated work into the bundle",
                "manifest uses codex-observe.evidence-bundle.v1 with review_summary and synthetic demo data only",
            ],
            "success_checks": [
                "bundle README starts with key findings and review checklist before artifact paths",
                "manifest includes action_plan, review_summary, validation_commands, LIMITATIONS.md, and PUBLIC_TOUR_FEEDBACK.md",
            ],
            "commands": [
                "codex-observe evidence-bundle --out .artifacts/public-evidence",
            ],
        },
        {
            "title": "Run the aggregate release audit after visual and bundle evidence exist",
            "evidence": [
                "audit JSON lists required_commands and failed_checks",
                "audit verifies report, comparison, tour, ingest, visual evidence, and public bundle contracts",
            ],
            "success_checks": [
                "audit status is ok and failed_checks is empty",
                "required_commands lists the full local release gate",
            ],
            "commands": ["codex-observe audit --json"],
        },
        {
            "title": "File privacy-safe public-tour feedback",
            "evidence": [
                "docs/PUBLIC_TOUR_FEEDBACK.md explains safe feedback sources and what not to collect",
                ".github/ISSUE_TEMPLATE/public_tour_feedback.yml captures useful, confusing, visual, bundle, and privacy-review notes",
                "feedback should use synthetic or reviewed-redacted evidence only",
            ],
            "success_checks": [
                "feedback avoids private prompts, tool output, local paths, and unreviewed screenshots",
                "new implementation issues remain demoable and require explicit publication approval",
            ],
            "commands": [],
        },
    ]


def public_tour_review_path(db_path: str = DEFAULT_DEMO_DB) -> list[dict[str, object]]:
    return [
        {
            "step": 1,
            "label": "Create synthetic evidence",
            "command": "codex-observe demo --serve --host 127.0.0.1 --port 8501",
            "success_check": "Dashboard opens on synthetic high- and low-risk runs.",
        },
        {
            "step": 2,
            "label": "Verify database health",
            "command": f"codex-observe doctor --db {db_path}",
            "success_check": "Doctor text includes Review path and Next commands; JSON status is ok with schema_version codex-observe.doctor.v1.",
        },
        {
            "step": 3,
            "label": "Choose the recommended run",
            "command": f"codex-observe sessions --db {db_path}",
            "success_check": "Sessions text includes the recommended high-risk run, review path, and terminal Next commands.",
        },
        {
            "step": 4,
            "label": "Export aggregate reports",
            "command": f"codex-observe report --db {db_path} --format json --out .artifacts/demo/run-report.json",
            "success_check": "Report JSON includes success_target and next_action_detail.",
        },
        {
            "step": 5,
            "label": "Compare workflow evidence",
            "command": "codex-observe compare --before-report .artifacts/demo/run-report.json --after-report .artifacts/demo/run-report.json --out .artifacts/demo/run-comparison.md",
            "success_check": "Comparison includes verdict, triage movement, and next validation command.",
        },
        {
            "step": 6,
            "label": "Verify UI and bundle evidence",
            "command": "codex-observe evidence-bundle --out .artifacts/public-evidence",
            "success_check": "Bundle manifest includes action_plan, review_summary, and validation_commands.",
        },
        {
            "step": 7,
            "label": "Run release audit",
            "command": "codex-observe audit --json",
            "success_check": "Audit status is ok and failed_checks is empty.",
        },
        {
            "step": 8,
            "label": "File safe feedback",
            "command": "docs/PUBLIC_TOUR_FEEDBACK.md",
            "success_check": "Feedback excludes private prompts, tool output, local paths, and raw logs.",
        },
    ]


def public_tour_feedback_handoff() -> dict[str, object]:
    return {
        "runbook": "docs/PUBLIC_TOUR_FEEDBACK.md",
        "issue_template": ".github/ISSUE_TEMPLATE/public_tour_feedback.yml",
        "evidence_rule": "Use synthetic or reviewed-redacted evidence only; do not include private prompts, raw logs, tool output, local paths, or unreviewed screenshots.",
        "safe_sources": [
            "codex-observe tour output",
            "synthetic demo dashboard",
            "aggregate-only doctor, sessions, report, and compare output",
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


def public_tour_payload(db_path: str = DEFAULT_DEMO_DB) -> dict[str, object]:
    steps = public_tour_steps(db_path)
    review_path = public_tour_review_path(db_path)
    return {
        "schema_version": TOUR_SCHEMA_VERSION,
        "status": "ok",
        "database": db_path,
        "privacy": {
            "mode": "synthetic-demo",
            "summary": "this path uses synthetic data and aggregate-only exports",
            "private_log_required": False,
        },
        "steps": steps,
        "review_path": review_path,
        "feedback_handoff": public_tour_feedback_handoff(),
        "next_commands": [
            command
            for step in steps
            for command in step["commands"]
            if isinstance(command, str)
        ],
    }


def public_tour_lines(db_path: str = DEFAULT_DEMO_DB) -> list[str]:
    lines = [
        "Codex Observe public tour",
        "Privacy: this path uses synthetic data and aggregate-only exports.",
        "",
        "Review path:",
    ]
    for item in public_tour_review_path(db_path):
        lines.append(f"- {item['step']}. {item['label']}: {item['command']}")
        lines.append(f"  Success check: {item['success_check']}")
    lines.append("")
    steps = public_tour_steps(db_path)
    for index, step in enumerate(steps, start=1):
        lines.append(f"{index}. {step['title']}:")
        for evidence in step.get("evidence", []):
            lines.append(f"   Evidence: {evidence}")
        for check in step.get("success_checks", []):
            lines.append(f"   Success check: {check}")
        lines.extend(f"   {command}" for command in step["commands"])
    feedback_handoff = public_tour_feedback_handoff()
    lines.extend(
        [
            "",
            "Feedback handoff:",
            f"- Runbook: {feedback_handoff['runbook']}",
            f"- Issue template: {feedback_handoff['issue_template']}",
            f"- Evidence rule: {feedback_handoff['evidence_rule']}",
            "- Safe feedback sources:",
        ]
    )
    lines.extend(f"  - {source}" for source in feedback_handoff["safe_sources"])
    lines.append("- Do not collect:")
    lines.extend(f"  - {item}" for item in feedback_handoff["do_not_collect"])
    next_commands = [
        command
        for step in steps
        for command in step["commands"]
        if isinstance(command, str)
    ]
    if next_commands:
        lines.extend(["", "Next commands:"])
        lines.extend(f"- {command}" for command in next_commands)
    return lines


def demo_next_commands(db_path: str) -> list[str]:
    return [
        f"codex-observe doctor --db {db_path} --json",
        f"codex-observe sessions --db {db_path} --json",
        f"codex-observe report --db {db_path} --out .artifacts/demo/run-report.md",
        f"codex-observe serve --db {db_path}",
    ]


def demo_review_path(db_path: str) -> list[dict[str, str]]:
    return [
        {
            "label": "Verify synthetic database",
            "command": f"codex-observe doctor --db {db_path} --json",
            "success_check": "doctor JSON status is ok and schema_version is codex-observe.doctor.v1.",
        },
        {
            "label": "Pick the reportable run",
            "command": f"codex-observe sessions --db {db_path} --json",
            "success_check": "sessions JSON includes recommended_session, recommendation_detail, and review_path.",
        },
        {
            "label": "Export aggregate report",
            "command": f"codex-observe report --db {db_path} --out .artifacts/demo/run-report.md",
            "success_check": "report output includes Recommended Action and Next Run Success Target.",
        },
        {
            "label": "Open dashboard",
            "command": f"codex-observe serve --db {db_path}",
            "success_check": "dashboard opens on synthetic high- and low-risk runs without raw private logs.",
        },
    ]


def demo_success_payload(
    db_path: str,
    sessions_path: str,
    result,
    keep_sessions: bool = False,
    serve: bool = False,
) -> dict[str, object]:
    commands = demo_next_commands(db_path)
    return {
        "schema_version": DEMO_SCHEMA_VERSION,
        "status": "ok",
        "database": db_path,
        "sessions_path": sessions_path,
        "keep_sessions": keep_sessions,
        "serve": serve,
        "counts": {
            "jsonl_files": int(result.files_imported),
            "threads": int(result.threads),
            "events": int(result.events),
        },
        "next": "run the commands in next_commands to verify health, choose a run, export a report, and open the dashboard.",
        "next_commands": commands,
        "review_path": demo_review_path(db_path),
    }


def demo_success_lines(db_path: str, result, serve: bool = False) -> list[str]:
    commands = demo_next_commands(db_path)
    review_path = demo_review_path(db_path)
    lines = [
        (
            f"Created demo database with {result.files_imported} JSONL files, "
            f"{result.threads} threads, {result.events} events into {db_path}"
        ),
        "Review path:",
    ]
    for step in review_path:
        lines.append(f"- {step['label']}: {step['command']}")
        lines.append(f"  Success check: {step['success_check']}")
    lines.extend(
        [
            "Next commands:",
            *(f"- {command}" for command in commands),
        ]
    )
    if serve:
        lines.append(
            "Next: dashboard is launching; use the commands above to verify and export evidence."
        )
    else:
        lines.append(
            "Next: run the commands above to verify health, choose a run, export a report, and open the dashboard."
        )
    return lines


def ingest_summary(result) -> str:
    skipped = []
    for attr, label in [
        ("duplicate_files", "duplicates"),
        ("empty_files", "empty"),
        ("malformed_files", "malformed"),
        ("missing_meta_files", "missing session_meta"),
        ("unreadable_files", "unreadable"),
    ]:
        value = int(getattr(result, attr, 0) or 0)
        if value:
            skipped.append(f"{value} {label}")
    skipped_text = ", ".join(skipped) if skipped else "none"
    malformed_lines = int(getattr(result, "malformed_lines", 0) or 0)
    malformed_detail = (
        f", {malformed_lines} malformed lines skipped" if malformed_lines else ""
    )
    limit = getattr(result, "newest_files_limit", None)
    matched = int(getattr(result, "files_matched", 0) or 0)
    skipped_by_limit = int(getattr(result, "files_skipped_by_limit", 0) or 0)
    limit_detail = ""
    if limit is not None:
        limit_detail = (
            f", newest-file limit {int(limit)} selected from {matched} matched"
            f" ({skipped_by_limit} deferred)"
        )
    return (
        f"Imported {result.files_imported} of {result.files_seen} JSONL files "
        f"({skipped_text} skipped{malformed_detail}{limit_detail}), "
        f"{result.threads} threads, {result.events} events into"
    )


def ingest_skipped_counts(result) -> dict[str, int]:
    return {
        "duplicate_files": int(getattr(result, "duplicate_files", 0) or 0),
        "empty_files": int(getattr(result, "empty_files", 0) or 0),
        "malformed_files": int(getattr(result, "malformed_files", 0) or 0),
        "missing_meta_files": int(getattr(result, "missing_meta_files", 0) or 0),
        "unreadable_files": int(getattr(result, "unreadable_files", 0) or 0),
        "malformed_lines": int(getattr(result, "malformed_lines", 0) or 0),
    }


def ingest_status(result) -> str:
    skipped = ingest_skipped_counts(result)
    if any(value for value in skipped.values()):
        return "partial"
    if int(getattr(result, "files_seen", 0) or 0) == 0:
        return "empty"
    return "ok"


def ingest_next_commands(db_path: str) -> list[str]:
    return [
        f"codex-observe doctor --db {db_path} --json",
        f"codex-observe sessions --db {db_path} --json",
        f"codex-observe serve --db {db_path}",
    ]


def ingest_review_path(db_path: str, status: str) -> list[dict[str, str]]:
    if status in {"ok", "partial"}:
        return [
            {
                "label": "Verify database health",
                "command": f"codex-observe doctor --db {db_path} --json",
                "success_check": "doctor JSON status is ok and review_path is present.",
            },
            {
                "label": "Choose a reportable run",
                "command": f"codex-observe sessions --db {db_path} --json",
                "success_check": "sessions JSON includes recommended_session and review_path.",
            },
            {
                "label": "Export aggregate report",
                "command": f"codex-observe report --db {db_path} --out run-report.md",
                "success_check": "report output includes Recommended Action and Next Run Success Target.",
            },
            {
                "label": "Open dashboard",
                "command": f"codex-observe serve --db {db_path}",
                "success_check": "dashboard opens on the same database without raw log output.",
            },
        ]
    if status == "empty":
        return [
            {
                "label": "Check input path",
                "command": f"codex-observe ingest ~/.codex/sessions --db {db_path}",
                "success_check": "ingest sees JSONL files with session_meta.",
            },
            {
                "label": "Try synthetic data",
                "command": f"codex-observe demo --db {db_path}",
                "success_check": "demo creates reportable conversations for evaluation.",
            },
            {
                "label": "Verify database health",
                "command": f"codex-observe doctor --db {db_path} --json",
                "success_check": "doctor reports status ok after ingest or demo.",
            },
        ]
    return []


def ingest_success_payload(
    sessions_path: str, db_path: str, result, serve: bool = False
) -> dict[str, object]:
    status = ingest_status(result)
    return {
        "schema_version": INGEST_SCHEMA_VERSION,
        "status": status,
        "privacy": {
            "mode": "aggregate-only",
            "private_log_required": True,
            "raw_content_included": False,
            "review_required_before_sharing": True,
            "share_warning": (
                "Review private aggregate databases, aggregate metrics, reports, "
                "screenshots, copied rows, and redacted fixture candidates before sharing."
            ),
        },
        "source": sessions_path,
        "database": db_path,
        "serve": serve,
        "counts": {
            "files_matched": int(getattr(result, "files_matched", 0) or 0),
            "files_seen": int(getattr(result, "files_seen", 0) or 0),
            "files_imported": int(getattr(result, "files_imported", 0) or 0),
            "files_skipped_by_limit": int(
                getattr(result, "files_skipped_by_limit", 0) or 0
            ),
            "threads": int(getattr(result, "threads", 0) or 0),
            "events": int(getattr(result, "events", 0) or 0),
        },
        "scan_limit": {
            "mode": "newest_files"
            if getattr(result, "newest_files_limit", None) is not None
            else "all",
            "newest_files": getattr(result, "newest_files_limit", None),
        },
        "skipped": ingest_skipped_counts(result),
        "next": "run the commands in next_commands to verify health, choose a run, and open the dashboard.",
        "next_commands": ingest_next_commands(db_path),
        "review_path": ingest_review_path(db_path, status),
    }


def ingest_success_lines(db_path: str, result, serve: bool = False) -> list[str]:
    commands = ingest_next_commands(db_path)
    status = ingest_status(result)
    review_path = ingest_review_path(db_path, status)
    lines = [
        f"{ingest_summary(result)} {db_path}",
        (
            "Privacy: ingest output is aggregate-only, but review private databases, "
            "reports, screenshots, copied rows, and aggregate metrics before sharing."
        ),
        "Review path:",
    ]
    for step in review_path:
        lines.append(f"- {step['label']}: {step['command']}")
        lines.append(f"  Success check: {step['success_check']}")
    lines.extend(
        [
            "Next commands:",
            *(f"- {command}" for command in commands),
        ]
    )
    if serve:
        lines.append(
            "Next: dashboard is launching; use the commands above to verify and inspect the database."
        )
    else:
        lines.append(
            "Next: run the commands above to verify health, choose a run, and open the dashboard."
        )
    return lines


def default_db() -> str:
    return str(Path.home() / ".codex-observe" / "codex_observe.sqlite")


def default_sessions_path() -> Path:
    return Path.home() / ".codex" / "sessions"


def _command_arg(path: Path | str) -> str:
    value = str(path)
    safe_punctuation = "._/\\:~+-"
    if value and all(char.isalnum() or char in safe_punctuation for char in value):
        return value
    if sys.platform == "win32":
        return f'"{value}"'
    return shlex.quote(value)


def supported_python() -> bool:
    return (3, 10) <= sys.version_info[:2] <= (3, 12)


def optional_dependency_check(name: str, module: str) -> dict[str, object]:
    found = importlib.util.find_spec(module) is not None
    return {
        "name": name,
        "ok": found,
        "detail": f"{module} importable"
        if found
        else f'{module} missing; install with `python -m pip install -e ".[visual]"`',
    }


def self_check_payload(*, include_visual: bool = False) -> dict[str, object]:
    dashboard_path = Path(__file__).with_name("dashboard.py")
    checks = [
        {
            "name": "python",
            "ok": supported_python(),
            "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
        {
            "name": "package_version",
            "ok": bool(__version__),
            "detail": f"codex-observe {__version__}",
        },
        {
            "name": "dashboard_module",
            "ok": dashboard_path.exists(),
            "detail": "dashboard.py available"
            if dashboard_path.exists()
            else "dashboard.py missing",
        },
    ]
    if include_visual:
        checks.extend(
            [
                optional_dependency_check("visual_pillow", "PIL"),
                optional_dependency_check("visual_playwright", "playwright"),
            ]
        )
    ok = all(bool(check["ok"]) for check in checks)
    return {
        "schema_version": SELF_CHECK_SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "checks": checks,
        "privacy": {
            "raw_content_included": False,
            "scans_sessions": False,
            "review_required_before_sharing": False,
        },
        "visual_checks_included": include_visual,
        "next_commands": [
            "codex-observe tour",
            "codex-observe demo --serve --host 127.0.0.1 --port 8501",
            'python -m pip install -e ".[visual]"',
            "python -m playwright install chromium",
            "codex-observe paths",
            "codex-observe private-validate ~/.codex/sessions --serve --host 127.0.0.1 --port 8501",
        ],
        "next": "run the demo tour first, then use private-validate when you are ready to inspect local Codex history.",
    }


def self_check_lines(payload: dict[str, object]) -> list[str]:
    lines = [
        f"Install check: {payload['status']}",
        "Privacy: this command does not scan sessions or print local paths, prompts, tool output, session IDs, or aggregate metrics.",
        "Checks:",
    ]
    for check in payload.get("checks", []):
        if not isinstance(check, dict):
            continue
        marker = "OK" if check.get("ok") else "FAIL"
        lines.append(f"- [{marker}] {check.get('name')}: {check.get('detail')}")
    lines.append("Next commands:")
    lines.extend(f"- {command}" for command in payload.get("next_commands", []))
    return lines


def paths_payload(db_path: str | None = None, sessions_path: str | None = None) -> dict:
    sessions = (
        Path(sessions_path).expanduser() if sessions_path else default_sessions_path()
    )
    db = Path(db_path).expanduser() if db_path else Path(default_db()).expanduser()
    sessions_arg = _command_arg(sessions)
    db_arg = _command_arg(db)
    return {
        "schema_version": PATHS_SCHEMA_VERSION,
        "sessions_path": str(sessions),
        "sessions_path_exists": sessions.exists(),
        "database": str(db),
        "database_exists": db.exists(),
        "privacy": {
            "raw_content_included": False,
            "scans_sessions": False,
            "review_required_before_sharing": True,
            "share_warning": (
                "Paths and aggregate artifacts can reveal local workflow clues; "
                "review before sharing."
            ),
        },
        "next_commands": [
            f"codex-observe ingest {sessions_arg} --newest-files 25 --db {db_arg} --json",
            f"codex-observe doctor --db {db_arg}",
            f"codex-observe sessions --db {db_arg}",
            f"codex-observe serve --db {db_arg}",
        ],
        "review_path": [
            {
                "label": "Sample newest private logs",
                "command": f"codex-observe ingest {sessions_arg} --newest-files 25 --db {db_arg} --json",
                "success_check": "JSON status is ok and privacy.review_required_before_sharing is true.",
            },
            {
                "label": "Verify aggregate database health",
                "command": f"codex-observe doctor --db {db_arg}",
                "success_check": "Doctor status is ok or prints copy-pasteable recovery commands.",
            },
            {
                "label": "Choose the highest-risk run",
                "command": f"codex-observe sessions --db {db_arg}",
                "success_check": "Sessions output shows aggregate risk distribution and a recommended report command.",
            },
        ],
    }


def paths_lines(
    db_path: str | None = None, sessions_path: str | None = None
) -> list[str]:
    payload = paths_payload(db_path=db_path, sessions_path=sessions_path)
    lines = [
        f"Default Codex sessions path: {payload['sessions_path']}",
        f"Sessions path exists: {str(payload['sessions_path_exists']).lower()}",
        f"Default Codex Observe database: {payload['database']}",
        f"Database exists: {str(payload['database_exists']).lower()}",
        (
            "Privacy: this command does not scan logs or print filenames, prompts, "
            "tool output, session IDs, or aggregate metrics."
        ),
        "Review path:",
    ]
    for step in payload["review_path"]:
        lines.append(f"- {step['label']}: {step['command']}")
        lines.append(f"  Success check: {step['success_check']}")
    lines.append("Next commands:")
    lines.extend(f"- {command}" for command in payload["next_commands"])
    return lines


def private_validate_paths(output_dir: str | Path) -> dict[str, Path]:
    out = Path(output_dir).expanduser()
    return {
        "output_dir": out,
        "database": out / "real-sessions.sqlite",
        "paths_json": out / "real-paths.json",
        "ingest_json": out / "real-ingest.json",
        "doctor_json": out / "real-doctor.json",
        "sessions_json": out / "real-sessions-list.json",
        "report_md": out / "real-run-report.md",
        "report_json": out / "real-run-report.json",
    }


def private_artifact_label(path: Path) -> str:
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.name


def private_visual_qa_command(database: Path, output_dir: Path) -> str:
    script = (Path("scripts") / "visual_qa.py").as_posix()
    return (
        f"python {script} --profile real --db {_command_arg(database)} "
        f"--host 127.0.0.1 --port 8502 --out {_command_arg(output_dir)} --timeout 60"
    )


def private_validate_payload(
    sessions_path: str | None = None,
    *,
    output_dir: str | Path = ".artifacts/private",
    newest_files: int = 25,
) -> tuple[int, dict[str, object]]:
    artifacts = private_validate_paths(output_dir)
    out = artifacts["output_dir"]
    out.mkdir(parents=True, exist_ok=True)
    db_path = str(artifacts["database"])
    sessions = str(
        Path(sessions_path).expanduser() if sessions_path else default_sessions_path()
    )

    paths = paths_payload(db_path=db_path, sessions_path=sessions)
    artifacts["paths_json"].write_text(
        json.dumps(paths, indent=2, sort_keys=True), encoding="utf-8"
    )

    status = "ok"
    error = ""
    report_written = False
    try:
        result = ingest(sessions, db_path, newest_files=newest_files)
        ingest_payload = ingest_success_payload(sessions, db_path, result)
        artifacts["ingest_json"].write_text(
            json.dumps(ingest_payload, indent=2, sort_keys=True), encoding="utf-8"
        )

        doctor_status, doctor = doctor_report(db_path)
        artifacts["doctor_json"].write_text(
            json.dumps(doctor, indent=2, sort_keys=True), encoding="utf-8"
        )
        if doctor_status != 0:
            status = str(doctor.get("status") or "doctor_failed")
            error = str(doctor.get("error") or "doctor check failed")

        sessions_payload = sessions_json_payload(db_path)
        artifacts["sessions_json"].write_text(
            json.dumps(sessions_payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        recommended = sessions_payload.get("recommended_session")
        if status == "ok" and isinstance(recommended, dict):
            report = build_report(db_path, str(recommended.get("session_id") or ""))
            artifacts["report_md"].write_text(report_markdown(report), encoding="utf-8")
            artifacts["report_json"].write_text(report_json(report), encoding="utf-8")
            report_written = True
        elif status == "ok":
            status = "empty"
            error = "No reportable sessions were found after ingest."
    except (FileNotFoundError, PermissionError, ValueError, sqlite3.Error) as exc:
        status = "failed"
        error = str(exc)

    artifact_labels = {
        key: private_artifact_label(path)
        for key, path in artifacts.items()
        if key != "output_dir"
    }
    visual_output_dir = out / "visual-real"
    visual_manifest = visual_output_dir / "visual-qa-manifest.json"
    visual_command = private_visual_qa_command(artifacts["database"], visual_output_dir)
    next_commands = [
        f"codex-observe doctor --db {_command_arg(artifacts['database'])}",
        f"codex-observe sessions --db {_command_arg(artifacts['database'])}",
        f"codex-observe serve --db {_command_arg(artifacts['database'])}",
        visual_command,
    ]
    payload: dict[str, object] = {
        "schema_version": PRIVATE_VALIDATE_SCHEMA_VERSION,
        "status": status,
        "sessions_path_exists": bool(paths.get("sessions_path_exists")),
        "database_exists": artifacts["database"].exists(),
        "newest_files": newest_files,
        "artifacts": artifact_labels,
        "report_written": report_written,
        "privacy": {
            "raw_content_included": False,
            "terminal_output_includes_counts": False,
            "review_required_before_sharing": True,
            "share_warning": (
                "Artifacts are private aggregate evidence; keep them ignored and "
                "review before sharing."
            ),
        },
        "next_commands": next_commands,
        "visual_qa": {
            "profile": "real",
            "command": visual_command,
            "output_dir": private_artifact_label(visual_output_dir),
            "manifest": private_artifact_label(visual_manifest),
            "raw_content_included": False,
            "review_required_before_sharing": True,
        },
    }
    if error:
        payload["error"] = error
    return (0 if status == "ok" else 1), payload


def private_validate_lines(payload: dict[str, object]) -> list[str]:
    lines = [
        f"Private validation status: {payload['status']}",
        (
            "Privacy: terminal output omits private counts, filenames, session IDs, "
            "prompts, tool output, and raw log content."
        ),
        "Artifacts written under ignored private output:",
    ]
    artifacts = payload.get("artifacts", {})
    if isinstance(artifacts, dict):
        for label in [
            "database",
            "paths_json",
            "ingest_json",
            "doctor_json",
            "sessions_json",
            "report_md",
            "report_json",
        ]:
            artifact = artifacts.get(label)
            if artifact:
                lines.append(f"- {label}: {artifact}")
    if payload.get("error"):
        lines.append(f"Error: {payload['error']}")
    visual_qa = payload.get("visual_qa")
    if isinstance(visual_qa, dict) and visual_qa.get("command"):
        lines.append("Private visual QA handoff:")
        lines.append(f"- command: {visual_qa['command']}")
        if visual_qa.get("manifest"):
            lines.append(f"- manifest: {visual_qa['manifest']}")
        lines.append(
            "- privacy: keep generated screenshots and manifests ignored and review before sharing."
        )
    lines.append("Next commands:")
    lines.extend(f"- {command}" for command in payload.get("next_commands", []))
    return lines


def missing_database_hint(db_path: str) -> str:
    db_arg = _command_arg(db_path)
    return (
        f"Run `codex-observe demo` for synthetic data or "
        f"`codex-observe ingest ~/.codex/sessions --db {db_arg}` for local logs."
    )


def sessions_hint(db_path: str) -> str:
    db_arg = _command_arg(db_path)
    return (
        f"Run `codex-observe sessions --db {db_arg}` to list aggregate-only session IDs "
        "and risk, or add `--json` for `recommended_session`."
    )


def sessions_next_commands(db_path: str, session_id: str | None = None) -> list[str]:
    db_arg = _command_arg(db_path)
    if session_id:
        return session_validation_commands(db_arg, session_id)
    return [
        f"codex-observe ingest ~/.codex/sessions --db {db_arg}",
        f"codex-observe demo --db {db_arg}",
    ]


def compare_failure_payload(
    db_path: str,
    status: str,
    error: str,
    input_mode: str,
) -> dict[str, object]:
    db_arg = _command_arg(db_path)
    if input_mode == "sessions":
        next_text = sessions_hint(db_path)
        next_commands = [
            f"codex-observe sessions --db {db_arg}",
            f"codex-observe sessions --db {db_arg} --json",
        ]
    else:
        next_text = report_json_hint(db_path)
        next_commands = [
            f"codex-observe report --db {db_arg} --format json --out run-report.json"
        ]
    return {
        "schema_version": COMPARISON_FAILURE_SCHEMA_VERSION,
        "status": status,
        "input_mode": input_mode,
        "database": db_path,
        "error": error,
        "next": next_text,
        "next_commands": next_commands,
    }


def comparison_written_lines(
    path: Path, comparison: dict, db_path: Path | str | None = None
) -> list[str]:
    risk = comparison.get("triage_risk", {})
    direction = str(risk.get("direction") or "unknown")
    before = str(risk.get("before") or "unknown")
    after = str(risk.get("after") or "unknown")
    opportunity = comparison.get("opportunity_change", {})
    opportunity_summary = ""
    if isinstance(opportunity, dict):
        opportunity_summary = str(opportunity.get("summary") or "").strip()
    recommendation = str(comparison.get("recommendation") or "Inspect the comparison.")
    lines = [
        f"Wrote aggregate-only comparison: {path}",
        "Privacy: review private comparison reports before sharing; aggregate deltas can still reveal workflow clues.",
        f"Verdict: {comparison.get('verdict', 'unknown')}",
        f"Triage risk: {before} -> {after} ({direction})",
    ]
    if opportunity_summary:
        lines.append(f"Opportunity change: {opportunity_summary}")
    lines.extend(ingest_scope_lines(comparison.get("ingest_scope"), db_path))
    lines.append(f"Next step: {recommendation}")
    templates = comparison.get("next_command_templates", [])
    if isinstance(templates, list) and templates:
        lines.append(f"Next validation command: {templates[0]}")
        lines.append("Next commands:")
        lines.extend(f"- {command}" for command in templates)
    return lines


def report_failure_payload(
    db_path: str, status: str, error: str, session_id: str | None = None
) -> dict[str, object]:
    db_arg = _command_arg(db_path)
    if status == "missing":
        next_text = (
            f"run `codex-observe demo --db {db_arg}` for synthetic data or "
            f"`codex-observe ingest ~/.codex/sessions --db {db_arg}` for local logs."
        )
        next_commands = sessions_next_commands(db_path)
    else:
        next_text = sessions_hint(db_path)
        next_commands = [
            f"codex-observe sessions --db {db_arg}",
            f"codex-observe sessions --db {db_arg} --json",
        ]
    return {
        "schema_version": REPORT_FAILURE_SCHEMA_VERSION,
        "database": db_path,
        "status": status,
        "error": error,
        "session_id": session_id,
        "next": next_text,
        "next_commands": next_commands,
    }


def report_written_lines(
    path: Path, report: dict, db_path: Path | str | None = None
) -> list[str]:
    triage = report.get("triage", {})
    risk = str(triage.get("risk_level") or "unknown")
    driver = str(triage.get("primary_driver") or "No high-signal diagnostic")
    action = str(triage.get("next_action") or "Inspect the report.")
    opportunity_line = ""
    opportunities = report.get("opportunities", [])
    if isinstance(opportunities, list) and opportunities:
        first = opportunities[0]
        if isinstance(first, dict):
            opportunity_driver = str(first.get("Driver") or "unknown")
            opportunity_scale = str(first.get("Scale") or "unknown")
            opportunity_line = (
                f"Top opportunity: {opportunity_driver}; {opportunity_scale}"
            )
    lines = [
        f"Wrote aggregate-only report: {path}",
        "Privacy: review private reports before sharing; aggregate metrics can still reveal workflow clues.",
    ]
    lines.extend(ingest_scope_lines(report.get("ingest_scope"), db_path))
    lines.append(f"Triage: {risk} risk; {driver}")
    if opportunity_line:
        lines.append(opportunity_line)
    lines.append(f"Next action: {action}")
    success_target = report.get("success_target", {})
    if isinstance(success_target, dict) and success_target.get("metric"):
        current = str(success_target.get("current") or "unknown")
        target = str(success_target.get("target") or "unknown")
        lines.append(
            f"Success target: {success_target['metric']}: {current} -> {target}"
        )
    commands = report.get("next_commands", [])
    templates = report.get("next_command_templates", [])
    next_commands = []
    if isinstance(commands, list):
        next_commands.extend(str(command) for command in commands)
    if isinstance(templates, list):
        next_commands.extend(str(command) for command in templates)
    if next_commands:
        lines.append("Next commands:")
        lines.extend(f"- {command}" for command in next_commands)
    return lines


def report_json_hint(db_path: str) -> str:
    db_arg = _command_arg(db_path)
    return (
        f"Run `codex-observe report --db {db_arg} --format json --out run-report.json` "
        "to create a comparison input."
    )


def bundle_path_label(path: Path, output_dir: Path) -> str:
    return path.relative_to(output_dir).as_posix()


def write_json_artifact(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def evidence_bundle_review_summary(
    report: dict[str, object],
    comparison: dict[str, object],
    audit_payload: dict[str, object],
) -> list[dict[str, str]]:
    triage = report.get("triage", {})
    success_target = report.get("success_target", {})
    opportunities = report.get("opportunities", [])
    top_opportunity = (
        opportunities[0] if isinstance(opportunities, list) and opportunities else {}
    )
    if not isinstance(top_opportunity, dict):
        top_opportunity = {}
    comparison_headline = comparison.get("headline", {})
    if not isinstance(comparison_headline, dict):
        comparison_headline = {}
    opportunity_change = comparison.get("opportunity_change", {})
    if not isinstance(opportunity_change, dict):
        opportunity_change = {}
    failed_checks = audit_payload.get("failed_checks", [])
    failed_count = len(failed_checks) if isinstance(failed_checks, list) else 0
    return [
        {
            "label": "Run triage",
            "value": f"{triage.get('risk_level', 'unknown')} risk - {triage.get('primary_driver', 'No high-signal diagnostic')}",
            "why_it_matters": str(
                triage.get("next_action") or "Inspect the aggregate report."
            ),
        },
        {
            "label": "Top opportunity",
            "value": f"{top_opportunity.get('Driver', 'No dominant opportunity')} - {top_opportunity.get('Scale', 'unknown scale')}",
            "why_it_matters": str(
                top_opportunity.get("Habit")
                or "Use the opportunity stack to choose the next workflow habit."
            ),
        },
        {
            "label": "Next-run target",
            "value": f"{success_target.get('metric', 'total_tokens')}: {success_target.get('current', 'unknown')} -> {success_target.get('target', 'unknown')}",
            "why_it_matters": str(
                success_target.get("verification")
                or "Compare the next run against this target."
            ),
        },
        {
            "label": "Comparison verdict",
            "value": f"{comparison.get('verdict', 'unknown')} - {comparison_headline.get('headline', 'No comparison headline available.')}",
            "why_it_matters": str(
                comparison.get("recommendation")
                or opportunity_change.get("summary")
                or "Inspect the comparison report."
            ),
        },
        {
            "label": "Audit status",
            "value": f"{audit_payload.get('status', 'unknown')} with {failed_count} failed checks",
            "why_it_matters": "The synthetic evidence bundle should be reproducible before it is attached or published.",
        },
    ]


def evidence_bundle_review_checklist(
    artifacts: dict[str, object], visual_status: object
) -> list[dict[str, str]]:
    checklist = [
        {
            "label": "Confirm the bundle boundary",
            "artifact": str(artifacts.get("limitations_markdown", "LIMITATIONS.md")),
            "look_for": "Synthetic-only scope, approval-gated distribution, and real-log privacy gate requirements.",
        },
        {
            "label": "Read the run outcome",
            "artifact": str(artifacts.get("report_markdown", "demo/run-report.md")),
            "look_for": "Quick read, triage risk, opportunity stack, next-run success target, and follow-up commands.",
        },
        {
            "label": "Check workflow-change evidence",
            "artifact": str(
                artifacts.get("comparison_markdown", "demo/run-comparison.md")
            ),
            "look_for": "Verdict, triage movement, opportunity change, next step, next validation command, and comparison review path.",
        },
        {
            "label": "Verify release gates",
            "artifact": str(artifacts.get("audit_json", "audit/audit.json")),
            "look_for": "status=ok, failed_checks=[], and the required command list for reproducing gates.",
        },
    ]
    checklist.append(
        {
            "label": "File feedback safely",
            "artifact": str(
                artifacts.get("feedback_runbook", "PUBLIC_TOUR_FEEDBACK.md")
            ),
            "look_for": "Safe feedback sources, do-not-collect rules, and approval requirements before publishing artifacts.",
        }
    )
    if visual_status == "ok" and isinstance(artifacts.get("visual_manifest"), str):
        checklist.append(
            {
                "label": "Inspect dashboard evidence",
                "artifact": str(artifacts["visual_manifest"]),
                "look_for": "Desktop/narrow screenshots, operator briefing, safe feedback handoff, quick reads, comparison review path, metric delta cards, and layout review.",
            }
        )
    return checklist


def evidence_bundle_action_plan(
    artifacts: dict[str, object], validation_commands: dict[str, str]
) -> list[dict[str, object]]:
    return [
        {
            "step": 1,
            "label": "Establish the safe review boundary",
            "artifact": str(artifacts.get("limitations_markdown", "LIMITATIONS.md")),
            "action": "Confirm the bundle is synthetic-only and note approval-gated work before sharing anything externally.",
            "success_check": "Reviewer can state what is safe to share and what still requires explicit human approval.",
        },
        {
            "step": 2,
            "label": "Read the run diagnosis",
            "artifact": str(artifacts.get("report_markdown", "demo/run-report.md")),
            "action": "Use the quick read, opportunity stack, recommended action, and next-run target to understand the expensive run.",
            "success_check": "Reviewer can name the top aggregate driver, recommended habit, and measurable next-run target.",
        },
        {
            "step": 3,
            "label": "Check change evidence",
            "artifact": str(
                artifacts.get("comparison_markdown", "demo/run-comparison.md")
            ),
            "action": "Inspect whether the comparison verdict, triage movement, and opportunity movement support the next workflow step.",
            "success_check": "Reviewer can explain whether the workflow improved, regressed, or stayed unchanged without reading private content.",
        },
        {
            "step": 4,
            "label": "Verify reproducibility gates",
            "artifact": str(artifacts.get("audit_json", "audit/audit.json")),
            "action": "Check status, failed_checks, and required_commands before treating the bundle as release evidence.",
            "success_check": "Audit status is ok, failed_checks is empty, and required_commands are available for rerun.",
        },
        {
            "step": 5,
            "label": "Validate the next real run",
            "artifact": "validation_commands",
            "action": str(
                validation_commands.get(
                    "next_report",
                    "codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json",
                )
            ),
            "success_check": "A future report JSON can be compared against the bundled success target before adopting the workflow change.",
        },
        {
            "step": 6,
            "label": "File feedback safely",
            "artifact": str(
                artifacts.get("feedback_runbook", "PUBLIC_TOUR_FEEDBACK.md")
            ),
            "action": "Record useful, confusing, visual, bundle, and privacy notes without private prompts, tool output, or local paths.",
            "success_check": "Feedback uses synthetic or reviewed-redacted evidence and avoids private raw content.",
        },
    ]


def evidence_bundle_readme(manifest: dict[str, object]) -> str:
    artifacts = manifest.get("artifacts", {})
    checks = manifest.get("checks", {})
    review_summary = manifest.get("review_summary")
    review_checklist = manifest.get("review_checklist")
    validation_commands = manifest.get("validation_commands")
    action_plan = manifest.get("action_plan")
    feedback_handoff = manifest.get("feedback_handoff")
    lines = [
        "# Codex Observe Evidence Bundle",
        "",
        f"Status: {manifest.get('status', 'unknown')}",
        "",
        "This bundle uses synthetic demo data only. It does not require private Codex logs, and it does not intentionally include raw prompts, message text, tool commands, tool output, or event payload JSON.",
        "",
        "## Start Here",
        "",
        "- `evidence-bundle.json` is the machine-readable manifest.",
        "- `LIMITATIONS.md` records known boundaries, approval-gated work, and next-work sources.",
    ]
    if isinstance(artifacts, dict):
        recommended = [
            ("limitations_markdown", "Known limitations and next-work sources"),
            ("feedback_runbook", "Privacy-safe feedback runbook"),
            ("feedback_issue_template", "Privacy-safe feedback issue template"),
            ("report_markdown", "Aggregate run report"),
            ("comparison_markdown", "Aggregate comparison report"),
            ("audit_json", "Release audit JSON"),
            ("visual_manifest", "Visual QA manifest"),
        ]
        for key, label in recommended:
            value = artifacts.get(key)
            if isinstance(value, str):
                lines.append(f"- `{value}`: {label}.")
        screenshots = artifacts.get("visual_screenshots")
        if isinstance(screenshots, list) and screenshots:
            joined = ", ".join(f"`{item}`" for item in screenshots)
            lines.append(f"- {joined}: Dashboard screenshots.")

    if isinstance(action_plan, list) and action_plan:
        lines.extend(["", "## Reviewer Action Plan", ""])
        for item in action_plan:
            if not isinstance(item, dict):
                continue
            step = item.get("step") or "?"
            label = str(item.get("label") or "Review step")
            artifact = str(item.get("artifact") or "unknown")
            action = str(item.get("action") or "Review the artifact.")
            success_check = str(item.get("success_check") or "Confirm the result.")
            lines.append(
                f"{step}. **{label}** (`{artifact}`): {action} Success check: {success_check}"
            )

    if isinstance(review_summary, list) and review_summary:
        lines.extend(["", "## Key Findings", ""])
        for item in review_summary:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "Finding")
            value = str(item.get("value") or "unknown").rstrip(".")
            why_it_matters = str(
                item.get("why_it_matters") or "Review the related artifact."
            ).rstrip(".")
            lines.append(f"- {label}: {value}. {why_it_matters}.")
    if isinstance(review_checklist, list) and review_checklist:
        lines.extend(["", "## Review Checklist", ""])
        for item in review_checklist:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "Review artifact")
            artifact = str(item.get("artifact") or "unknown")
            look_for = str(item.get("look_for") or "Review the artifact.")
            lines.append(f"- {label}: `{artifact}` - {look_for}")

    if isinstance(validation_commands, dict) and validation_commands:
        lines.extend(["", "## Validate The Next Run", ""])
        for key in ["next_report", "next_comparison", "same_database_comparison"]:
            command = validation_commands.get(key)
            if isinstance(command, str) and command:
                label = key.replace("_", " ").title()
                lines.append(f"- {label}: `{command}`")

    if isinstance(feedback_handoff, dict) and feedback_handoff:
        lines.extend(["", "## Feedback Handoff", ""])
        runbook = feedback_handoff.get("runbook")
        issue_template = feedback_handoff.get("issue_template")
        evidence_rule = feedback_handoff.get("evidence_rule")
        if isinstance(runbook, str):
            lines.append(f"- Runbook: `{runbook}`")
        if isinstance(issue_template, str):
            lines.append(f"- Issue template: `{issue_template}`")
        if isinstance(evidence_rule, str):
            lines.append(f"- Evidence rule: {evidence_rule}")
        safe_sources = feedback_handoff.get("safe_sources")
        if isinstance(safe_sources, list) and safe_sources:
            lines.append(
                "- Safe feedback sources: "
                + "; ".join(str(item) for item in safe_sources)
            )
        do_not_collect = feedback_handoff.get("do_not_collect")
        if isinstance(do_not_collect, list) and do_not_collect:
            lines.append(
                "- Do not collect: " + "; ".join(str(item) for item in do_not_collect)
            )

    commands = manifest.get("commands")
    if isinstance(commands, list) and commands:
        lines.extend(["", "## Reproduce Locally", ""])
        for command in commands:
            if isinstance(command, str) and command:
                lines.append(f"- `{command}`")

    lines.extend(["", "## Checks", ""])
    if isinstance(checks, dict):
        for key, value in checks.items():
            status = "unknown"
            if isinstance(value, dict):
                status = str(value.get("status", "unknown"))
            lines.append(f"- {key}: {status}")

    lines.extend(
        [
            "",
            "## Before Sharing",
            "",
            "- Review the Markdown reports, audit JSON, manifest, and screenshots when visual QA is included.",
            "- Do not attach private logs, private SQLite databases, or unreviewed local artifacts.",
            "- External publishing or attachment still requires explicit human approval.",
            "",
        ]
    )
    return "\n".join(lines)


def sync_visual_evidence_for_audit(source_dir: Path) -> None:
    target_dir = VISUAL_MANIFEST.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in ["visual-qa-manifest.json", *EXPECTED_VISUAL_SCREENSHOTS.values()]:
        source = source_dir / name
        if source.exists():
            shutil.copy2(source, target_dir / name)


def public_evidence_bundle(
    output_dir: str = ".artifacts/public-evidence",
    *,
    run_visual: bool = True,
) -> tuple[int, dict[str, object]]:
    out = Path(output_dir).expanduser()
    demo_dir = out / "demo"
    visual_dir = out / "visual"
    audit_dir = out / "audit"
    out.mkdir(parents=True, exist_ok=True)
    demo_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    db_path = demo_dir / "codex_observe_demo.sqlite"
    sessions_path = demo_dir / "sessions"
    report_md = demo_dir / "run-report.md"
    report_json_path = demo_dir / "run-report.json"
    comparison_md = demo_dir / "run-comparison.md"
    comparison_json_path = demo_dir / "run-comparison.json"
    audit_json_path = audit_dir / "audit.json"
    manifest_path = out / "evidence-bundle.json"
    readme_path = out / "README.md"
    limitations_path = out / "LIMITATIONS.md"
    feedback_path = out / "PUBLIC_TOUR_FEEDBACK.md"
    feedback_issue_template_path = (
        out / ".github" / "ISSUE_TEMPLATE" / "public_tour_feedback.yml"
    )

    limitations_source = Path("docs") / "LIMITATIONS.md"
    if limitations_source.exists():
        limitations_text = limitations_source.read_text(encoding="utf-8")
    else:
        limitations_text = (
            "# Limitations and Next Work\n\n"
            "The source repository limitations document was not available "
            "when this synthetic bundle was generated. Run `codex-observe audit --json` "
            "from the repository checkout before publishing or attaching artifacts.\n"
        )
    limitations_path.write_text(limitations_text, encoding="utf-8")

    feedback_source = Path("docs") / "PUBLIC_TOUR_FEEDBACK.md"
    if feedback_source.exists():
        feedback_text = feedback_source.read_text(encoding="utf-8")
    else:
        feedback_text = (
            "# Public Tour Feedback\n\n"
            "The source repository feedback runbook was not available when this synthetic bundle was generated. Review generated artifacts for private paths or aggregate clues before sharing.\n"
        )
    feedback_path.write_text(feedback_text, encoding="utf-8")

    feedback_issue_template_path.parent.mkdir(parents=True, exist_ok=True)
    feedback_issue_template_source = (
        Path(".github") / "ISSUE_TEMPLATE" / "public_tour_feedback.yml"
    )
    if feedback_issue_template_source.exists():
        feedback_issue_template_text = feedback_issue_template_source.read_text(
            encoding="utf-8"
        )
    else:
        feedback_issue_template_text = (
            "name: Public tour feedback\n"
            "description: Report privacy-safe feedback from trying the public tour or reviewer evidence bundle\n"
            "body:\n"
            "  - type: markdown\n"
            "    attributes:\n"
            "      value: Do not paste private prompts, raw logs, tool output, local paths, or unreviewed screenshots.\n"
        )
    feedback_issue_template_path.write_text(
        feedback_issue_template_text, encoding="utf-8"
    )

    commands = [
        f"codex-observe demo --db {bundle_path_label(db_path, out)} --sessions {bundle_path_label(sessions_path, out)} --keep-sessions",
        f"codex-observe report --db {bundle_path_label(db_path, out)} --out {bundle_path_label(report_md, out)}",
        f"codex-observe report --db {bundle_path_label(db_path, out)} --format json --out {bundle_path_label(report_json_path, out)}",
        f"codex-observe compare --before-report {bundle_path_label(report_json_path, out)} --after-report {bundle_path_label(report_json_path, out)} --out {bundle_path_label(comparison_md, out)}",
        f"codex-observe compare --before-report {bundle_path_label(report_json_path, out)} --after-report {bundle_path_label(report_json_path, out)} --format json --out {bundle_path_label(comparison_json_path, out)}",
    ]
    if run_visual:
        commands.append(
            f"python scripts/visual_qa.py --db {bundle_path_label(db_path, out)} --out {bundle_path_label(visual_dir, out)}"
        )
    commands.append("codex-observe audit --json")

    statuses: dict[str, object] = {}
    result = create_demo_database(str(db_path), str(sessions_path), keep_sessions=True)
    statuses["demo"] = {
        "status": "ok",
        "jsonl_files": int(result.files_imported),
        "threads": int(result.threads),
        "events": int(result.events),
    }

    report = build_report(str(db_path))
    report_md.write_text(report_markdown(report), encoding="utf-8")
    report_json_path.write_text(report_json(report), encoding="utf-8")
    statuses["report"] = {"status": "ok", "schema_version": REPORT_SCHEMA_VERSION}

    comparison = compare_reports(report, report)
    comparison_md.write_text(comparison_markdown(comparison), encoding="utf-8")
    comparison_json_path.write_text(comparison_json(comparison), encoding="utf-8")
    statuses["comparison"] = {
        "status": "ok",
        "schema_version": COMPARISON_SCHEMA_VERSION,
    }

    visual_manifest = visual_dir / "visual-qa-manifest.json"
    if run_visual:
        visual_command = [
            sys.executable,
            str(Path("scripts") / "visual_qa.py"),
            "--db",
            str(db_path),
            "--out",
            str(visual_dir),
        ]
        visual_result = subprocess.run(
            visual_command,
            check=False,
            capture_output=True,
            text=True,
        )
        if visual_result.returncode == 0:
            sync_visual_evidence_for_audit(visual_dir)
            statuses["visual_qa"] = {
                "status": "ok",
                "manifest": bundle_path_label(visual_manifest, out),
            }
        else:
            statuses["visual_qa"] = {
                "status": "failed",
                "returncode": visual_result.returncode,
                "error": (visual_result.stderr or visual_result.stdout)
                .strip()
                .splitlines()[:5],
            }
    else:
        statuses["visual_qa"] = {"status": "skipped"}

    audit_status, audit_payload = release_audit_report(
        str(audit_dir / "audit-demo.sqlite"),
        str(audit_dir / "sessions"),
        str(audit_dir / "audit-run-report.md"),
        check_public_evidence_bundle=False,
    )
    write_json_artifact(audit_json_path, audit_payload)
    statuses["audit"] = {
        "status": audit_payload.get("status", "unknown"),
        "schema_version": audit_payload.get("schema_version"),
    }

    visual_status = statuses["visual_qa"].get("status")
    artifacts: dict[str, object] = {
        "bundle_readme": bundle_path_label(readme_path, out),
        "limitations_markdown": bundle_path_label(limitations_path, out),
        "feedback_runbook": bundle_path_label(feedback_path, out),
        "feedback_issue_template": bundle_path_label(feedback_issue_template_path, out),
        "database": bundle_path_label(db_path, out),
        "sessions_dir": bundle_path_label(sessions_path, out),
        "report_markdown": bundle_path_label(report_md, out),
        "report_json": bundle_path_label(report_json_path, out),
        "comparison_markdown": bundle_path_label(comparison_md, out),
        "comparison_json": bundle_path_label(comparison_json_path, out),
        "audit_json": bundle_path_label(audit_json_path, out),
    }
    if visual_status == "ok" and visual_manifest.exists():
        artifacts["visual_manifest"] = bundle_path_label(visual_manifest, out)
        artifacts["visual_screenshots"] = [
            bundle_path_label(visual_dir / filename, out)
            for filename in EXPECTED_VISUAL_SCREENSHOTS.values()
            if (visual_dir / filename).exists()
        ]

    status = (
        "ok" if audit_status == 0 and visual_status in {"ok", "skipped"} else "failed"
    )
    review_summary = evidence_bundle_review_summary(report, comparison, audit_payload)
    review_checklist = evidence_bundle_review_checklist(artifacts, visual_status)

    next_step = "Start with README.md, LIMITATIONS.md, and PUBLIC_TOUR_FEEDBACK.md, then review evidence-bundle.json, run-report.md, run-comparison.md, and audit.json before publishing or attaching artifacts."
    if visual_status == "ok":
        next_step = "Start with README.md, LIMITATIONS.md, and PUBLIC_TOUR_FEEDBACK.md, then review evidence-bundle.json, run-report.md, run-comparison.md, audit.json, and visual QA screenshots before publishing or attaching artifacts."

    validation_commands = {}
    templates = comparison.get("next_command_templates", [])
    if isinstance(templates, list):
        template_keys = [
            "next_report",
            "next_comparison",
            "same_database_comparison",
        ]
        validation_commands = {
            key: command
            for key, command in zip(template_keys, templates, strict=False)
            if isinstance(command, str) and command
        }

    action_plan = evidence_bundle_action_plan(artifacts, validation_commands)

    manifest: dict[str, object] = {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "status": status,
        "privacy": {
            "mode": "synthetic-demo",
            "private_log_required": False,
            "raw_content_included": False,
        },
        "commands": commands,
        "artifacts": artifacts,
        "review_summary": review_summary,
        "review_checklist": review_checklist,
        "action_plan": action_plan,
        "validation_commands": validation_commands,
        "feedback_handoff": public_tour_feedback_handoff(),
        "checks": statuses,
        "next": next_step,
    }
    write_json_artifact(manifest_path, manifest)
    readme_path.write_text(evidence_bundle_readme(manifest), encoding="utf-8")
    return 0 if status == "ok" else 1, manifest


def evidence_bundle_lines(output_dir: str, manifest: dict[str, object]) -> list[str]:
    artifacts = manifest.get("artifacts", {})
    review_summary = manifest.get("review_summary")
    review_checklist = manifest.get("review_checklist")
    action_plan = manifest.get("action_plan")
    feedback_handoff = manifest.get("feedback_handoff")
    lines = [
        f"Evidence bundle: {Path(output_dir).expanduser()}",
        f"Status: {manifest.get('status', 'unknown')}",
    ]
    if isinstance(action_plan, list) and action_plan:
        lines.append("Reviewer action plan:")
        for item in action_plan:
            if not isinstance(item, dict):
                continue
            step = item.get("step") or "?"
            label = str(item.get("label") or "Review step")
            artifact = str(item.get("artifact") or "unknown")
            lines.append(f"- {step}. {label}: {artifact}")
    if isinstance(review_summary, list) and review_summary:
        lines.append("Key findings:")
        for item in review_summary:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "Finding")
            value = str(item.get("value") or "unknown")
            lines.append(f"- {label}: {value}")
    if isinstance(review_checklist, list) and review_checklist:
        lines.append("Review checklist:")
        for item in review_checklist:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "Review artifact")
            artifact = str(item.get("artifact") or "unknown")
            look_for = str(item.get("look_for") or "Review the artifact.").rstrip(".")
            lines.append(f"- {label}: {artifact} - {look_for}")
    validation_commands = manifest.get("validation_commands")
    if isinstance(validation_commands, dict) and validation_commands:
        lines.append("Validation commands:")
        for key in ["next_report", "next_comparison", "same_database_comparison"]:
            command = validation_commands.get(key)
            if isinstance(command, str) and command:
                lines.append(f"- {key}: {command}")
    if isinstance(feedback_handoff, dict) and feedback_handoff:
        lines.append("Feedback handoff:")
        runbook = feedback_handoff.get("runbook")
        issue_template = feedback_handoff.get("issue_template")
        evidence_rule = feedback_handoff.get("evidence_rule")
        if isinstance(runbook, str):
            lines.append(f"- Runbook: {runbook}")
        if isinstance(issue_template, str):
            lines.append(f"- Issue template: {issue_template}")
        if isinstance(evidence_rule, str):
            lines.append(f"- Evidence rule: {evidence_rule}")
        safe_sources = feedback_handoff.get("safe_sources")
        if isinstance(safe_sources, list) and safe_sources:
            lines.append("- Safe feedback sources:")
            lines.extend(f"  - {item}" for item in safe_sources)
        do_not_collect = feedback_handoff.get("do_not_collect")
        if isinstance(do_not_collect, list) and do_not_collect:
            lines.append("- Do not collect:")
            lines.extend(f"  - {item}" for item in do_not_collect)
    lines.append("Artifacts:")
    if isinstance(artifacts, dict):
        for key, value in artifacts.items():
            if isinstance(value, list):
                lines.append(f"- {key}: {', '.join(str(item) for item in value)}")
            else:
                lines.append(f"- {key}: {value}")
    lines.append(f"Next: {manifest.get('next', 'Review the bundle artifacts.')}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codex-observe",
        description="Offline observability for Codex JSONL session logs",
        epilog=textwrap.dedent(
            """            Start here:
              codex-observe tour
              codex-observe demo --serve --host 127.0.0.1 --port 8501
              codex-observe doctor --db .artifacts/demo/codex_observe_demo.sqlite --json
              codex-observe sessions --db .artifacts/demo/codex_observe_demo.sqlite --json
              codex-observe scan-and-serve ~/.codex/sessions
              codex-observe report --db ~/.codex-observe/codex_observe.sqlite --out run-report.md

            Privacy: paths, doctor, sessions, report, compare, and audit use aggregate-only outputs; dashboard screenshots and copied rows may still reveal private local content.
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tour = sub.add_parser(
        "tour",
        help="Print the privacy-safe public evaluation path",
        description="Print a synthetic-data tour that exercises the dashboard, aggregate reports, comparison, visual QA, release audit, and evidence bundle.",
    )
    p_tour.add_argument(
        "--db",
        default=DEFAULT_DEMO_DB,
        help="Synthetic SQLite database path to show in commands",
    )
    p_tour.add_argument(
        "--json", action="store_true", help="Emit the tour as schema-versioned JSON"
    )

    p_self = sub.add_parser(
        "self-check",
        help="Verify the local source install without scanning private logs",
        description=(
            "Check the installed command, supported Python runtime, dashboard module, "
            "and next commands without reading Codex session logs."
        ),
    )
    p_self.add_argument(
        "--visual",
        action="store_true",
        help="Also verify Pillow and Playwright imports for visual QA",
    )
    p_self.add_argument(
        "--json",
        action="store_true",
        help="Emit source-install check status as schema-versioned JSON",
    )
    p_paths = sub.add_parser(
        "paths",
        help="Show local default paths and private validation commands",
        description="Show the resolved local Codex sessions path, Codex Observe database path, and privacy-safe next commands without scanning logs.",
    )
    p_paths.add_argument(
        "--sessions-path",
        default=None,
        help="Override the sessions directory shown in next commands",
    )
    p_paths.add_argument(
        "--db",
        default=None,
        help="Override the database path shown in next commands",
    )
    p_paths.add_argument(
        "--json",
        action="store_true",
        help="Emit path guidance as schema-versioned JSON",
    )

    p_private = sub.add_parser(
        "private-validate",
        help="Run the private real-session validation loop into ignored artifacts",
        description=(
            "Ingest a bounded sample of local Codex sessions, verify the database, "
            "list aggregate sessions, and export the recommended aggregate report "
            "under an ignored private artifact directory."
        ),
    )
    p_private.add_argument(
        "sessions_path",
        nargs="?",
        default=str(default_sessions_path()),
        help="Codex sessions directory or JSONL file; defaults to ~/.codex/sessions",
    )
    p_private.add_argument(
        "--out",
        default=".artifacts/private",
        help="Ignored private output directory for database and aggregate evidence",
    )
    p_private.add_argument(
        "--newest-files",
        type=positive_int,
        default=25,
        help="Only ingest the newest N JSONL files; default 25",
    )
    p_private.add_argument(
        "--serve",
        action="store_true",
        help="Launch the dashboard against the private validation database after success",
    )
    p_private.add_argument(
        "--host",
        default=None,
        help="Streamlit host, for example 127.0.0.1",
    )
    p_private.add_argument(
        "--port", default=None, help="Streamlit port, for example 8501"
    )
    p_private.add_argument(
        "--json",
        action="store_true",
        help="Emit privacy-safe private validation status as JSON",
    )
    p_ingest = sub.add_parser(
        "ingest",
        help="Ingest Codex JSONL files into SQLite",
        description="Ingest a Codex sessions directory or JSONL file into a local SQLite database.",
    )
    p_ingest.add_argument(
        "sessions_path",
        nargs="?",
        default=str(default_sessions_path()),
        help="Codex sessions directory or JSONL file; defaults to ~/.codex/sessions",
    )
    p_ingest.add_argument("--db", default=default_db(), help="SQLite database path")
    p_ingest.add_argument(
        "--json", action="store_true", help="Emit aggregate-only ingest status as JSON"
    )
    p_ingest.add_argument(
        "--newest-files",
        type=positive_int,
        default=None,
        help="Only ingest the newest N JSONL files from the input path",
    )

    p_serve = sub.add_parser(
        "serve",
        help="Launch the Streamlit dashboard",
        description="Launch the Streamlit dashboard for an existing Codex Observe database.",
    )
    p_serve.add_argument("--db", default=default_db(), help="SQLite database path")
    p_serve.add_argument(
        "--host", default=None, help="Streamlit host, for example 127.0.0.1"
    )
    p_serve.add_argument(
        "--port", default=None, help="Streamlit port, for example 8501"
    )

    p_scan = sub.add_parser(
        "scan-and-serve",
        help="Ingest then launch the dashboard",
        description="Ingest local Codex sessions, then launch the Streamlit dashboard.",
    )
    p_scan.add_argument(
        "sessions_path",
        nargs="?",
        default=str(default_sessions_path()),
        help="Codex sessions directory or JSONL file; defaults to ~/.codex/sessions",
    )
    p_scan.add_argument("--db", default=default_db(), help="SQLite database path")
    p_scan.add_argument(
        "--host", default=None, help="Streamlit host, for example 127.0.0.1"
    )
    p_scan.add_argument("--port", default=None, help="Streamlit port, for example 8501")
    p_scan.add_argument(
        "--newest-files",
        type=positive_int,
        default=None,
        help="Only ingest the newest N JSONL files from the input path before serving",
    )

    p_demo = sub.add_parser(
        "demo",
        help="Create a synthetic demo database, optionally launch the dashboard",
        description="Create representative synthetic data for trying Codex Observe without private logs.",
        epilog="Example: codex-observe demo --serve --host 127.0.0.1 --port 8501",
    )
    p_demo.add_argument(
        "--db", default=DEFAULT_DEMO_DB, help="Synthetic SQLite database path"
    )
    p_demo.add_argument(
        "--sessions",
        default=DEFAULT_DEMO_SESSIONS,
        help="Temporary synthetic sessions directory",
    )
    p_demo.add_argument(
        "--keep-sessions",
        action="store_true",
        help="Keep generated synthetic JSONL files",
    )
    p_demo.add_argument(
        "--serve",
        action="store_true",
        help="Launch the dashboard after generating demo data",
    )
    p_demo.add_argument(
        "--host", default=None, help="Streamlit host, for example 127.0.0.1"
    )
    p_demo.add_argument("--port", default=None, help="Streamlit port, for example 8501")
    p_demo.add_argument(
        "--json", action="store_true", help="Emit demo creation status as JSON"
    )

    p_bundle = sub.add_parser(
        "evidence-bundle",
        help="Create a local synthetic public evidence bundle",
        description="Create synthetic demo, report, comparison, audit, and visual QA evidence in one local bundle directory.",
    )
    p_bundle.add_argument(
        "--out",
        default=".artifacts/public-evidence",
        help="Output directory for the local evidence bundle",
    )
    p_bundle.add_argument(
        "--skip-visual",
        action="store_true",
        help="Skip browser visual QA generation; intended for fast contract tests",
    )
    p_bundle.add_argument(
        "--json", action="store_true", help="Emit the bundle manifest as JSON"
    )

    p_audit = sub.add_parser(
        "audit",
        help="Run fast release-readiness checks without printing private log content",
        description="Run aggregate-only release checks using synthetic demo data and repository metadata.",
    )
    p_audit.add_argument(
        "--db", default=DEFAULT_DEMO_DB, help="Synthetic audit database path"
    )
    p_audit.add_argument(
        "--sessions",
        default=DEFAULT_DEMO_SESSIONS,
        help="Temporary synthetic sessions directory",
    )
    p_audit.add_argument(
        "--report-out",
        default=".artifacts/demo/run-report.md",
        help="Aggregate report path written during audit",
    )
    p_audit.add_argument(
        "--public-evidence-dir",
        default=".artifacts/public-evidence",
        help="Generated evidence bundle directory validated during audit",
    )
    p_audit.add_argument(
        "--json", action="store_true", help="Emit aggregate-only JSON for automation"
    )
    p_doctor = sub.add_parser(
        "doctor",
        help="Check a Codex Observe database without printing private log content",
    )
    p_doctor.add_argument("--db", default=default_db(), help="SQLite database path")
    p_doctor.add_argument(
        "--json", action="store_true", help="Emit aggregate-only JSON for automation"
    )

    p_sessions = sub.add_parser(
        "sessions",
        help="List imported conversations without printing private log content",
    )
    p_sessions.add_argument("--db", default=default_db(), help="SQLite database path")
    p_sessions.add_argument(
        "--json", action="store_true", help="Emit aggregate-only JSON for automation"
    )
    p_sessions.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_SESSIONS_LIMIT,
        help="Maximum sessions to print or return; default 50",
    )

    p_compare = sub.add_parser(
        "compare",
        help="Compare two privacy-safe run reports or two sessions from one database",
        description="Compare aggregate-only reports or session summaries and include a verdict, largest-change summary, opportunity-change movement, and diagnostic changes.",
        epilog=textwrap.dedent(
            """            Examples:
              codex-observe compare --before-report before.json --after-report after.json --out run-comparison.md
              codex-observe compare --db ~/.codex-observe/codex_observe.sqlite --before-session before-run --after-session after-run --format json
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_compare.add_argument(
        "--db",
        default=default_db(),
        help="SQLite database path for session-to-session comparison",
    )
    p_compare.add_argument(
        "--before-session", default=None, help="Baseline session id from --db"
    )
    p_compare.add_argument(
        "--after-session", default=None, help="Comparison session id from --db"
    )
    p_compare.add_argument(
        "--before-report",
        default=None,
        help="Baseline JSON report from codex-observe report --format json",
    )
    p_compare.add_argument(
        "--after-report",
        default=None,
        help="Comparison JSON report from codex-observe report --format json",
    )
    p_compare.add_argument(
        "--format", choices=["md", "json"], default="md", help="Output format"
    )
    p_compare.add_argument(
        "--out", default=None, help="Write comparison to this path instead of stdout"
    )
    p_report = sub.add_parser(
        "report",
        help="Export a privacy-safe run report for one conversation",
        description="Export an aggregate-only report with a quick-read headline, ranked opportunity stack, diagnostics, and next-run playbook.",
        epilog=textwrap.dedent(
            """            Examples:
              codex-observe sessions --db ~/.codex-observe/codex_observe.sqlite
              codex-observe report --db ~/.codex-observe/codex_observe.sqlite --out run-report.md
              codex-observe report --db ~/.codex-observe/codex_observe.sqlite --session-id <id> --format json --out run-report.json
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_report.add_argument("--db", default=default_db(), help="SQLite database path")
    p_report.add_argument(
        "--session-id",
        default=None,
        help="Conversation/session id to report; defaults to highest triage risk, latest as tie-breaker",
    )
    p_report.add_argument(
        "--format", choices=["md", "json"], default="md", help="Output format"
    )
    p_report.add_argument(
        "--out", default=None, help="Write report to this path instead of stdout"
    )
    args = parser.parse_args(argv)

    if args.cmd == "tour":
        if args.json:
            print(json.dumps(public_tour_payload(args.db), indent=2, sort_keys=True))
        else:
            print("\n".join(public_tour_lines(args.db)))
        return 0
    if args.cmd == "self-check":
        payload = self_check_payload(include_visual=args.visual)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("\n".join(self_check_lines(payload)))
        return 0 if payload.get("status") == "ok" else 1
    if args.cmd == "paths":
        if args.json:
            print(
                json.dumps(
                    paths_payload(db_path=args.db, sessions_path=args.sessions_path),
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(
                "\n".join(
                    paths_lines(db_path=args.db, sessions_path=args.sessions_path)
                )
            )
        return 0
    if args.cmd == "private-validate":
        status, payload = private_validate_payload(
            args.sessions_path, output_dir=args.out, newest_files=args.newest_files
        )
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("\n".join(private_validate_lines(payload)))
        if not args.serve or status != 0:
            return status
        app_path = Path(__file__).with_name("dashboard.py")
        cmd = [sys.executable, "-m", "streamlit", "run", str(app_path)]
        if args.host:
            cmd.extend(["--server.address", args.host])
        if args.port:
            cmd.extend(["--server.port", str(args.port)])
        private_db = private_validate_paths(args.out)["database"]
        cmd.extend(["--", "--db", str(private_db)])
        return subprocess.call(cmd)
    if args.cmd == "evidence-bundle":
        status, manifest = public_evidence_bundle(
            args.out, run_visual=not args.skip_visual
        )
        if args.json:
            print(json.dumps(manifest, indent=2, sort_keys=True))
        else:
            print("\n".join(evidence_bundle_lines(args.out, manifest)))
        return status

    if args.cmd == "audit":
        if args.json:
            status, audit = release_audit_report(
                args.db,
                args.sessions,
                args.report_out,
                public_evidence_dir=args.public_evidence_dir,
            )
            print(json.dumps(audit, indent=2, sort_keys=True))
            return status
        status, lines = release_audit_lines(
            args.db,
            args.sessions,
            args.report_out,
            public_evidence_dir=args.public_evidence_dir,
        )
        print("\n".join(lines))
        return status
    if args.cmd == "doctor":
        if args.json:
            status, report = doctor_report(args.db)
            print(json.dumps(report, indent=2, sort_keys=True))
            return status
        status, lines = doctor_lines(args.db)
        print("\n".join(lines))
        return status

    if args.cmd == "sessions":
        try:
            if args.json:
                print(
                    json.dumps(
                        sessions_json_payload(args.db, limit=args.limit),
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                lines = ingest_scope_lines(latest_ingest_scope(args.db), args.db)
                lines.extend(session_summary_lines(args.db, limit=args.limit))
                print("\n".join(lines))
        except FileNotFoundError:
            if args.json:
                print(
                    json.dumps(
                        sessions_missing_json_payload(args.db),
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print(f"Database not found: {args.db}", file=sys.stderr)
                print(missing_database_hint(args.db), file=sys.stderr)
            return 2
        return 0

    if args.cmd == "compare":
        has_report_inputs = bool(args.before_report or args.after_report)
        has_session_inputs = bool(args.before_session or args.after_session)
        if has_report_inputs and has_session_inputs:
            error = "Use either --before-report/--after-report or --before-session/--after-session, not both."
            if args.format == "json":
                print(
                    json.dumps(
                        compare_failure_payload(
                            args.db, "invalid_input", error, "mixed"
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print(error, file=sys.stderr)
            return 1
        try:
            if has_report_inputs:
                if not args.before_report or not args.after_report:
                    error = "Both --before-report and --after-report are required for report comparison."
                    if args.format == "json":
                        print(
                            json.dumps(
                                compare_failure_payload(
                                    args.db, "incomplete_input", error, "reports"
                                ),
                                indent=2,
                                sort_keys=True,
                            )
                        )
                    else:
                        print(error, file=sys.stderr)
                        print(report_json_hint(args.db), file=sys.stderr)
                    return 1
                before = load_report_json(args.before_report)
                after = load_report_json(args.after_report)
            else:
                if not args.before_session or not args.after_session:
                    error = "Both --before-session and --after-session are required for session comparison."
                    if args.format == "json":
                        print(
                            json.dumps(
                                compare_failure_payload(
                                    args.db, "incomplete_input", error, "sessions"
                                ),
                                indent=2,
                                sort_keys=True,
                            )
                        )
                    else:
                        print(error, file=sys.stderr)
                        print(sessions_hint(args.db), file=sys.stderr)
                    return 1
                before = build_report(args.db, args.before_session)
                after = build_report(args.db, args.after_session)
        except FileNotFoundError as exc:
            if args.format == "json":
                if has_session_inputs:
                    payload = compare_failure_payload(
                        args.db,
                        "missing",
                        f"database not found: {args.db}",
                        "sessions",
                    )
                else:
                    payload = compare_failure_payload(
                        args.db, "missing", f"file not found: {exc}", "reports"
                    )
                print(json.dumps(payload, indent=2, sort_keys=True))
            elif has_session_inputs:
                print(f"Database not found: {args.db}", file=sys.stderr)
                print(missing_database_hint(args.db), file=sys.stderr)
            else:
                print(f"File not found: {exc}", file=sys.stderr)
                print(report_json_hint(args.db), file=sys.stderr)
            return 2
        except (ValueError, json.JSONDecodeError) as exc:
            if args.format == "json":
                input_mode = "sessions" if has_session_inputs else "reports"
                print(
                    json.dumps(
                        compare_failure_payload(
                            args.db, "unavailable", str(exc), input_mode
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print(str(exc), file=sys.stderr)
                if has_session_inputs:
                    print(sessions_hint(args.db), file=sys.stderr)
                else:
                    print(report_json_hint(args.db), file=sys.stderr)
            return 1

        comparison = compare_reports(before, after)
        output = (
            comparison_json(comparison)
            if args.format == "json"
            else comparison_markdown(comparison)
        )
        if args.out:
            out_path = Path(args.out).expanduser()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output, encoding="utf-8")
            comparison_db_path = args.db if has_session_inputs else None
            print(
                "\n".join(
                    comparison_written_lines(out_path, comparison, comparison_db_path)
                )
            )
        else:
            print(output)
        return 0
    if args.cmd == "report":
        try:
            report = build_report(args.db, args.session_id)
        except FileNotFoundError:
            if args.format == "json":
                print(
                    json.dumps(
                        report_failure_payload(
                            args.db,
                            "missing",
                            f"database not found: {args.db}",
                            args.session_id,
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print(f"Database not found: {args.db}", file=sys.stderr)
                print(missing_database_hint(args.db), file=sys.stderr)
            return 2
        except ValueError as exc:
            if args.format == "json":
                print(
                    json.dumps(
                        report_failure_payload(
                            args.db, "unavailable", str(exc), args.session_id
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print(str(exc), file=sys.stderr)
                print(sessions_hint(args.db), file=sys.stderr)
            return 1
        output = (
            report_json(report) if args.format == "json" else report_markdown(report)
        )
        if args.out:
            out_path = Path(args.out).expanduser()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output, encoding="utf-8")
            print("\n".join(report_written_lines(out_path, report, args.db)))
        else:
            print(output)
        return 0
    if args.cmd == "demo":
        Path(args.db).expanduser().parent.mkdir(parents=True, exist_ok=True)
        result = create_demo_database(
            args.db, args.sessions, keep_sessions=args.keep_sessions
        )
        if args.json:
            print(
                json.dumps(
                    demo_success_payload(
                        args.db,
                        args.sessions,
                        result,
                        keep_sessions=args.keep_sessions,
                        serve=args.serve,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print("\n".join(demo_success_lines(args.db, result, args.serve)))
        if not args.serve:
            return 0

    if args.cmd in {"ingest", "scan-and-serve"}:
        Path(args.db).expanduser().parent.mkdir(parents=True, exist_ok=True)
        result = ingest(args.sessions_path, args.db, newest_files=args.newest_files)
        if args.cmd == "ingest" and args.json:
            print(
                json.dumps(
                    ingest_success_payload(args.sessions_path, args.db, result),
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(
                "\n".join(
                    ingest_success_lines(args.db, result, args.cmd == "scan-and-serve")
                )
            )
        if args.cmd == "ingest":
            return 0

    app_path = Path(__file__).with_name("dashboard.py")
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    if args.host:
        cmd.extend(["--server.address", args.host])
    if args.port:
        cmd.extend(["--server.port", str(args.port)])
    cmd.extend(["--", "--db", args.db])
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
