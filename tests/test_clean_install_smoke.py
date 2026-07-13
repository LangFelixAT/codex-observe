from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clean_install_smoke", ROOT / "scripts" / "clean_install_smoke.py"
)
assert SPEC is not None
assert SPEC.loader is not None
clean_install_smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = clean_install_smoke
SPEC.loader.exec_module(clean_install_smoke)


def test_install_target_supports_plain_and_extra_installs() -> None:
    assert clean_install_smoke.install_target("none") == str(ROOT)
    assert clean_install_smoke.install_target("dev") == f"{ROOT}[dev]"
    assert clean_install_smoke.install_target("visual") == f"{ROOT}[visual]"


def test_evidence_bundle_check_verifies_manifest_readme_and_skipped_visual(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "evidence-bundle.json").write_text(
        '{"schema_version":"codex-observe.evidence-bundle.v1","artifacts":{"bundle_readme":"README.md","limitations_markdown":"LIMITATIONS.md"}}',
        encoding="utf-8",
    )
    (bundle / "README.md").write_text(
        "# Codex Observe Evidence Bundle\nprivate Codex logs\n", encoding="utf-8"
    )
    (bundle / "LIMITATIONS.md").write_text(
        "# Limitations and Next Work\napproval-gated\n", encoding="utf-8"
    )

    check = clean_install_smoke.evidence_bundle_check(bundle)

    assert "codex-observe.evidence-bundle.v1" in check
    assert "README.md" in check
    assert "LIMITATIONS.md" in check
    assert "limitations_markdown" in check
    assert "visual_manifest" in check
    assert "# Codex Observe Evidence Bundle" in check
    assert "private Codex logs" in check
    assert "approval-gated" in check


def test_smoke_commands_verify_console_script_demo_audit_bundle_and_imports(
    tmp_path: Path,
) -> None:
    paths = clean_install_smoke.SmokePaths(
        root=ROOT, env_dir=tmp_path / ".venv-smoke", work_dir=tmp_path / "work"
    )

    commands = clean_install_smoke.smoke_commands(paths, "dev")
    flattened = [" ".join(command) for command in commands]

    assert any("pip install --upgrade pip" in command for command in flattened)
    assert any(
        "pip install -e" in command and "[dev]" in command for command in flattened
    )
    assert any(
        "codex-observe" in command and "--version" in command for command in flattened
    )
    assert any(
        "codex-observe" in command and " demo " in command for command in flattened
    )
    assert any(
        "codex-observe" in command and " audit " in command for command in flattened
    )
    assert any(
        "codex-observe" in command and " evidence-bundle " in command
        for command in flattened
    )
    assert any("--skip-visual" in command for command in flattened)
    assert any("--public-evidence-dir" in command for command in flattened)
    bundle_index = next(
        index
        for index, command in enumerate(flattened)
        if " evidence-bundle " in command
    )
    audit_index = next(
        index for index, command in enumerate(flattened) if " audit " in command
    )
    assert bundle_index < audit_index
    assert any("evidence bundle ok" in command for command in flattened)
    assert any("import codex_observe" in command for command in flattened)
    assert any("import playwright" in command for command in flattened)
    assert any("from PIL import Image" in command for command in flattened)
    assert all(".codex" not in command for command in flattened)


def test_smoke_commands_do_not_require_playwright_for_plain_install(
    tmp_path: Path,
) -> None:
    paths = clean_install_smoke.SmokePaths(
        root=ROOT, env_dir=tmp_path / ".venv-smoke", work_dir=tmp_path / "work"
    )

    flattened = "\n".join(
        " ".join(command)
        for command in clean_install_smoke.smoke_commands(paths, "none")
    )

    assert "import playwright" not in flattened
    assert "from PIL import Image" not in flattened
    assert " demo " in flattened
    assert " audit " in flattened
    assert " evidence-bundle " in flattened
    assert "--skip-visual" in flattened
    assert "--public-evidence-dir" in flattened


def test_main_uses_temp_directory_and_removes_it_for_success(tmp_path: Path) -> None:
    work_dir = tmp_path / "smoke"

    with patch.object(clean_install_smoke, "run_smoke") as run_smoke:
        result = clean_install_smoke.main(
            ["--work-dir", str(work_dir), "--timeout", "1"]
        )

    assert result == 0
    run_smoke.assert_called_once()
    assert not work_dir.exists()


def test_main_keeps_environment_when_requested(tmp_path: Path) -> None:
    work_dir = tmp_path / "smoke"

    with patch.object(clean_install_smoke, "run_smoke"):
        result = clean_install_smoke.main(
            ["--work-dir", str(work_dir), "--keep-env", "--timeout", "1"]
        )

    assert result == 0
    assert work_dir.exists()
