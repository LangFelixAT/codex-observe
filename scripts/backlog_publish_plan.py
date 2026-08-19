from __future__ import annotations

import argparse
import json
import re
import shlex
import textwrap
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
    ".github/backlog/010-bound-dashboard-history-rendering-for-large-session-sets.md",
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
    for required in [
        "## What to build",
        "## Acceptance criteria",
        "## Tests and evidence",
        "## Visual QA",
        "## Privacy review",
        "## Blocked by",
    ]:
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


def slugify_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "new-work"


def next_draft_path(title: str, root: Path = ROOT) -> Path:
    draft_dir = root / DRAFT_DIR
    existing_numbers: list[int] = []
    if draft_dir.exists():
        for path in draft_dir.glob("*.md"):
            match = re.match(r"(\d+)-", path.name)
            if match:
                existing_numbers.append(int(match.group(1)))
    for retired in RETIRED_DRAFTS:
        match = re.match(r"\.github/backlog/(\d+)-", retired)
        if match:
            existing_numbers.append(int(match.group(1)))
    number = (max(existing_numbers) + 1) if existing_numbers else 1
    return draft_dir / f"{number:03d}-{slugify_title(title)}.md"


def draft_template(
    title: str,
    labels: list[str] | None = None,
    what_to_build: str | None = None,
    acceptance: list[str] | None = None,
    tests: list[str] | None = None,
    visual_qa: str | None = None,
    privacy_notes: str | None = None,
    blocked_by: str | None = None,
) -> str:
    label_values = labels or ["type: slice"]
    label_text = ", ".join(f"`{label}`" for label in label_values)
    acceptance_items = acceptance or [
        "Define the user-visible behavior and acceptance evidence before implementation.",
        "Add or update focused tests for the changed behavior.",
        "Update docs or release evidence when the workflow changes.",
    ]
    test_items = tests or [
        "pytest -q",
        "ruff check",
        "ruff format --check",
    ]
    visual_text = visual_qa or (
        "Run `python scripts/visual_qa.py` when the slice changes dashboard UI, "
        "screenshots, or manifest evidence; otherwise state why visual QA is not applicable."
    )
    privacy_text = privacy_notes or (
        "Use synthetic or reviewed-redacted aggregate evidence only. Do not include "
        "raw prompts, tool output, local paths, private session IDs, screenshots from "
        "private logs, or unreviewed redacted fixtures."
    )
    blocked_text = blocked_by or "None."
    body = f"""
# {title}

Labels: {label_text}

## What to build

{what_to_build or "Describe the demoable vertical slice and the user-visible improvement."}

## Acceptance criteria

{chr(10).join(f"- [ ] {item}" for item in acceptance_items)}

## Tests and evidence

{chr(10).join(f"- [ ] `{item}`" for item in test_items)}

## Visual QA

{visual_text}

## Privacy review

{privacy_text}

## Blocked by

{blocked_text}
"""
    return textwrap.dedent(body).strip() + "\n"


def create_draft(
    title: str,
    root: Path = ROOT,
    labels: list[str] | None = None,
    what_to_build: str | None = None,
    acceptance: list[str] | None = None,
    tests: list[str] | None = None,
    visual_qa: str | None = None,
    privacy_notes: str | None = None,
    blocked_by: str | None = None,
) -> Path:
    path = next_draft_path(title, root)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        draft_template(
            title=title,
            labels=labels,
            what_to_build=what_to_build,
            acceptance=acceptance,
            tests=tests,
            visual_qa=visual_qa,
            privacy_notes=privacy_notes,
            blocked_by=blocked_by,
        ),
        encoding="utf-8",
    )
    failures = validate_draft(path)
    if failures:
        raise ValueError("created draft failed validation: " + "; ".join(failures))
    return path


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
        "--new-draft",
        metavar="TITLE",
        help="Create a validated local draft under .github/backlog without publishing it.",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        help="Label for --new-draft; can be passed multiple times.",
    )
    parser.add_argument(
        "--what-to-build",
        help="Initial What to build text for --new-draft.",
    )
    parser.add_argument(
        "--acceptance",
        action="append",
        default=[],
        help="Acceptance criterion for --new-draft; can be passed multiple times.",
    )
    parser.add_argument(
        "--test",
        action="append",
        default=[],
        help="Validation command for --new-draft; can be passed multiple times.",
    )
    parser.add_argument(
        "--visual-qa",
        help="Visual QA expectation for --new-draft.",
    )
    parser.add_argument(
        "--privacy-note",
        help="Privacy review note for --new-draft.",
    )
    parser.add_argument(
        "--blocked-by",
        help="Blocked-by note for --new-draft; defaults to None.",
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

    if args.new_draft:
        created = create_draft(
            args.new_draft,
            ROOT,
            labels=args.label or None,
            what_to_build=args.what_to_build,
            acceptance=args.acceptance or None,
            tests=args.test or None,
            visual_qa=args.visual_qa,
            privacy_notes=args.privacy_note,
            blocked_by=args.blocked_by,
        )
        relative = relative_posix(created, ROOT)
        if args.json:
            print_json_payload(
                {
                    "schema_version": BACKLOG_PUBLISH_SCHEMA_VERSION,
                    "status": "created",
                    "repo": TARGET_REPOSITORY,
                    "requires_approval": True,
                    "draft": relative,
                    "publishable_drafts": publish_plan(ROOT),
                }
            )
        else:
            print(f"Created local backlog draft: {relative}")
            print(
                "Review it, run `python scripts/backlog_publish_plan.py --json`, "
                "and publish only after explicit human approval."
            )
        return 0

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
