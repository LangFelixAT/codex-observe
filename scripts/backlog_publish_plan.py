from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRAFT_DIR = Path(".github/backlog")
TARGET_REPOSITORY = "LangFelixAT/codex-observe"
BACKLOG_PUBLISH_SCHEMA_VERSION = "codex-observe.backlog-publish.v1"
RETIRED_DRAFTS = {
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
FORBIDDEN_PATTERNS = [
    r"sample_from_uploaded\.sqlite",
    r"\.codex[\\/]+sessions",
    r"synthetic output line",
    r"Analyze why this Codex run",
]


def relative_posix(path: Path, root: Path = ROOT) -> str:
    return path.relative_to(root).as_posix()


def draft_body(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def draft_title(path: Path) -> str:
    body = draft_body(path)
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def draft_labels(path: Path) -> list[str]:
    body = draft_body(path)
    for line in body.splitlines():
        if line.startswith("Labels:"):
            return re.findall(r"`([^`]+)`", line)
    return []


def discover_drafts(root: Path = ROOT) -> list[tuple[str, str]]:
    draft_dir = root / DRAFT_DIR
    if not draft_dir.exists():
        return []
    drafts: list[tuple[str, str]] = []
    for path in sorted(draft_dir.glob("*.md")):
        relative = relative_posix(path, root)
        if relative in RETIRED_DRAFTS:
            continue
        drafts.append((draft_title(path), relative))
    return drafts


def draft_is_complete(path: Path) -> bool:
    body = draft_body(path)
    return "- [x]" in body and "- [ ]" not in body


def validate_draft(path: Path) -> list[str]:
    failures: list[str] = []
    if not path.exists():
        return [f"{path}: missing"]
    body = draft_body(path)
    for required in ["## What to build", "## Acceptance criteria", "## Blocked by"]:
        if required not in body:
            failures.append(f"{path}: missing {required}")
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, body):
            failures.append(f"{path}: contains private or local-only pattern {pattern}")
    return failures


def publish_plan(root: Path = ROOT) -> list[dict[str, object]]:
    plan: list[dict[str, object]] = []
    for title, body_file in discover_drafts(root):
        path = root / body_file
        if draft_is_complete(path):
            continue
        labels = draft_labels(path)
        command_parts = [
            "gh",
            "issue",
            "create",
            "--repo",
            shlex.quote(TARGET_REPOSITORY),
            "--title",
            shlex.quote(title),
            "--body-file",
            shlex.quote(body_file),
        ]
        for label in labels:
            command_parts.extend(["--label", shlex.quote(label)])
        plan.append(
            {
                "title": title,
                "body_file": body_file,
                "repo": TARGET_REPOSITORY,
                "labels": labels,
                "command": " ".join(command_parts),
            }
        )
    return plan


def publish_commands(root: Path = ROOT) -> list[str]:
    return [str(item["command"]) for item in publish_plan(root)]


def plan_payload(status: str, failures: list[str] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": BACKLOG_PUBLISH_SCHEMA_VERSION,
        "status": status,
        "repo": TARGET_REPOSITORY,
        "requires_approval": True,
        "publishable_drafts": [] if failures else publish_plan(ROOT),
    }
    if failures is not None:
        payload["failures"] = failures
    return payload


def print_json_payload(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate local backlog issue drafts and print safe publishing commands."
    )
    parser.add_argument(
        "--commands-only",
        action="store_true",
        help="Only print gh commands when validation passes.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print validated publish plan metadata as JSON.",
    )
    args = parser.parse_args(argv)

    failures: list[str] = []
    for _, relative in discover_drafts(ROOT):
        failures.extend(validate_draft(ROOT / relative))

    if failures:
        if args.json:
            print_json_payload(plan_payload("failed", failures))
        else:
            print("Backlog draft validation failed:")
            for failure in failures:
                print(f"- {failure}")
        return 1

    plan = publish_plan(ROOT)
    commands = [str(item["command"]) for item in plan]
    if args.json:
        print_json_payload(plan_payload("ok"))
        return 0
    if not args.commands_only:
        print("Backlog draft validation passed.")
        print(
            f"Publishing writes issue content to GitHub repository {TARGET_REPOSITORY} and requires explicit approval."
        )
        if not commands:
            print(
                "No publishable drafts found; local drafts were retired or are waiting on explicit human input."
            )
        print()
    for command in commands:
        print(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
