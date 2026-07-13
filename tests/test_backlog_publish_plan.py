from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "backlog_publish_plan", ROOT / "scripts/backlog_publish_plan.py"
)
assert SPEC is not None
assert SPEC.loader is not None
backlog_publish_plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backlog_publish_plan)


def test_backlog_publish_plan_discovers_no_publishable_drafts_after_retirement() -> (
    None
):
    drafts = backlog_publish_plan.discover_drafts(ROOT)
    relatives = [relative for _, relative in drafts]

    assert relatives == []
    assert drafts == []


def test_backlog_publish_plan_reports_empty_plan_when_no_fresh_drafts(
    capsys,
) -> None:
    result = backlog_publish_plan.main([])
    output = capsys.readouterr().out

    assert result == 0
    assert "requires explicit approval" in output
    assert "LangFelixAT/codex-observe" in output
    assert "No publishable drafts found" in output
    assert "gh issue create" not in output
    assert "006-release-candidate-ux-evidence.md" not in output
    assert "007-real-log-parser-feedback-loop.md" not in output
    assert "008-public-readme-tour.md" not in output
    assert "009-public-evidence-bundle.md" not in output
    assert "001-first-run-demo.md" not in output


def test_backlog_publish_plan_rejects_private_or_malformed_draft(
    tmp_path: Path,
) -> None:
    draft = tmp_path / "draft.md"
    draft.write_text(
        "## What to build\nUse sample_from_uploaded.sqlite\n\n## Acceptance criteria\n- [ ] leaking\n",
        encoding="utf-8",
    )

    failures = backlog_publish_plan.validate_draft(draft)

    assert any("missing ## Blocked by" in failure for failure in failures)
    assert any("sample_from_uploaded" in failure for failure in failures)


def test_backlog_publish_plan_ignores_all_retired_draft_names(tmp_path: Path) -> None:
    draft_dir = tmp_path / ".github" / "backlog"
    draft_dir.mkdir(parents=True)
    for relative in backlog_publish_plan.RETIRED_DRAFTS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Retired\n\nLabels: `type: slice`\n\n## What to build\nDone\n\n## Acceptance criteria\n- [ ] stale\n\n## Blocked by\nNone\n",
            encoding="utf-8",
        )
    active = draft_dir / "010-active.md"
    active.write_text(
        "# Active\n\nLabels: `type: slice`, `area: parser`\n\n## What to build\nShip it\n\n## Acceptance criteria\n- [ ] publish\n\n## Blocked by\nNone\n",
        encoding="utf-8",
    )

    drafts = backlog_publish_plan.discover_drafts(tmp_path)
    commands = backlog_publish_plan.publish_commands(tmp_path)

    assert drafts == [("Active", ".github/backlog/010-active.md")]
    assert commands == [
        "gh issue create --repo LangFelixAT/codex-observe --title Active --body-file .github/backlog/010-active.md --label 'type: slice' --label 'area: parser'"
    ]


def test_backlog_publish_plan_exposes_machine_readable_empty_publish_plan(
    capsys,
) -> None:
    result = backlog_publish_plan.main(["--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result == 0
    assert payload == {
        "schema_version": backlog_publish_plan.BACKLOG_PUBLISH_SCHEMA_VERSION,
        "status": "ok",
        "repo": "LangFelixAT/codex-observe",
        "requires_approval": True,
        "publishable_drafts": [],
    }
    assert "Backlog draft validation passed" not in output


def test_backlog_publish_plan_structured_plan_matches_command_output() -> None:
    plan = backlog_publish_plan.publish_plan(ROOT)

    assert plan == []
    assert backlog_publish_plan.publish_commands(ROOT) == []


def test_backlog_publish_plan_json_reports_validation_failures(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    draft_dir = tmp_path / ".github" / "backlog"
    draft_dir.mkdir(parents=True)
    draft = draft_dir / "010-leaky.md"
    draft.write_text(
        "# Leaky\n\n## What to build\nUse sample_from_uploaded.sqlite\n\n## Acceptance criteria\n- [ ] fix\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(backlog_publish_plan, "ROOT", tmp_path)

    result = backlog_publish_plan.main(["--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result == 1
    assert (
        payload["schema_version"] == backlog_publish_plan.BACKLOG_PUBLISH_SCHEMA_VERSION
    )
    assert payload["status"] == "failed"
    assert payload["repo"] == "LangFelixAT/codex-observe"
    assert payload["requires_approval"] is True
    assert payload["publishable_drafts"] == []
    assert any("missing ## Blocked by" in failure for failure in payload["failures"])
    assert any("sample_from_uploaded" in failure for failure in payload["failures"])
    assert "Backlog draft validation failed" not in output


def test_backlog_publish_plan_text_still_reports_validation_failures(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    draft_dir = tmp_path / ".github" / "backlog"
    draft_dir.mkdir(parents=True)
    draft = draft_dir / "010-malformed.md"
    draft.write_text("# Malformed\n\n## What to build\nBuild\n", encoding="utf-8")
    monkeypatch.setattr(backlog_publish_plan, "ROOT", tmp_path)

    result = backlog_publish_plan.main([])
    output = capsys.readouterr().out

    assert result == 1
    assert "Backlog draft validation failed:" in output
    assert "missing ## Acceptance criteria" in output
    assert "missing ## Blocked by" in output
