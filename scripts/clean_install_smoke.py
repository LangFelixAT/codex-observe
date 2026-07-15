from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import venv
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SmokePaths:
    root: Path
    env_dir: Path
    work_dir: Path

    @property
    def python(self) -> Path:
        if sys.platform == "win32":
            return self.env_dir / "Scripts" / "python.exe"
        return self.env_dir / "bin" / "python"

    @property
    def codex_observe(self) -> Path:
        if sys.platform == "win32":
            return self.env_dir / "Scripts" / "codex-observe.exe"
        return self.env_dir / "bin" / "codex-observe"

    @property
    def demo_db(self) -> Path:
        return self.work_dir / "demo.sqlite"

    @property
    def demo_sessions(self) -> Path:
        return self.work_dir / "sessions"

    @property
    def audit_report(self) -> Path:
        return self.work_dir / "run-report.md"

    @property
    def evidence_bundle(self) -> Path:
        return self.work_dir / "public-evidence"


def install_target(extra: str) -> str:
    if extra == "none":
        return str(ROOT)
    return f"{ROOT}[{extra}]"


def evidence_bundle_check(bundle_dir: Path) -> str:
    bundle_literal = repr(str(bundle_dir))
    return (
        "import json; "
        "from pathlib import Path; "
        f"root=Path({bundle_literal}); "
        "manifest=json.loads((root / 'evidence-bundle.json').read_text(encoding='utf-8')); "
        "readme=(root / 'README.md').read_text(encoding='utf-8'); "
        "limitations=(root / 'LIMITATIONS.md').read_text(encoding='utf-8'); "
        "feedback=(root / 'PUBLIC_TOUR_FEEDBACK.md').read_text(encoding='utf-8'); "
        "issue_template=(root / '.github' / 'ISSUE_TEMPLATE' / 'public_tour_feedback.yml').read_text(encoding='utf-8'); "
        "assert manifest['schema_version'] == 'codex-observe.evidence-bundle.v1'; "
        "assert manifest['artifacts']['bundle_readme'] == 'README.md'; "
        "assert manifest['artifacts']['limitations_markdown'] == 'LIMITATIONS.md'; "
        "assert manifest['artifacts']['feedback_runbook'] == 'PUBLIC_TOUR_FEEDBACK.md'; "
        "assert manifest['artifacts']['feedback_issue_template'] == '.github/ISSUE_TEMPLATE/public_tour_feedback.yml'; "
        "assert 'visual_manifest' not in manifest['artifacts']; "
        "assert isinstance(manifest['review_summary'], list) and manifest['review_summary']; "
        "assert isinstance(manifest['review_checklist'], list) and manifest['review_checklist']; "
        "assert '# Codex Observe Evidence Bundle' in readme; "
        "assert 'private Codex logs' in readme; "
        "assert '## Key Findings' in readme; "
        "assert '## Review Checklist' in readme; "
        "assert 'PUBLIC_TOUR_FEEDBACK.md' in readme; "
        "assert '.github/ISSUE_TEMPLATE/public_tour_feedback.yml' in readme; "
        "assert '# Limitations and Next Work' in limitations; "
        "assert 'approval-gated' in limitations; "
        "assert '# Public Tour Feedback' in feedback; "
        "assert 'Public tour feedback' in issue_template; "
        "assert 'Do not paste private prompts' in issue_template; "
        "assert 'Privacy review' in issue_template; "
        "assert 'docs/PUBLIC_TOUR_FEEDBACK.md' in issue_template; "
        "print('evidence bundle ok')"
    )


def smoke_commands(paths: SmokePaths, extra: str) -> list[list[str]]:
    commands = [
        [str(paths.python), "-m", "pip", "install", "--upgrade", "pip"],
        [str(paths.python), "-m", "pip", "install", "-e", install_target(extra)],
        [str(paths.codex_observe), "--version"],
        [str(paths.codex_observe), "self-check", "--json"],
        [
            str(paths.codex_observe),
            "demo",
            "--db",
            str(paths.demo_db),
            "--sessions",
            str(paths.demo_sessions),
        ],
        [
            str(paths.codex_observe),
            "evidence-bundle",
            "--out",
            str(paths.evidence_bundle),
            "--skip-visual",
        ],
        [
            str(paths.codex_observe),
            "audit",
            "--db",
            str(paths.demo_db),
            "--sessions",
            str(paths.demo_sessions),
            "--report-out",
            str(paths.audit_report),
            "--public-evidence-dir",
            str(paths.evidence_bundle),
            "--json",
        ],
        [
            str(paths.python),
            "-c",
            evidence_bundle_check(paths.evidence_bundle),
        ],
        [
            str(paths.python),
            "-c",
            "import codex_observe; print(codex_observe.__version__)",
        ],
    ]
    if extra in {"visual", "dev"}:
        commands.extend(
            [
                [str(paths.codex_observe), "self-check", "--visual", "--json"],
                [str(paths.python), "-c", "import playwright; print('playwright ok')"],
                [str(paths.python), "-c", "from PIL import Image; print('pillow ok')"],
            ]
        )
    return commands


def run_command(command: list[str], timeout: float) -> None:
    printable = " ".join(command)
    print(f"$ {printable}")
    subprocess.run(command, cwd=ROOT, check=True, timeout=timeout)


def run_smoke(paths: SmokePaths, extra: str, timeout: float) -> None:
    print(f"Creating clean virtual environment at {paths.env_dir}")
    venv.EnvBuilder(with_pip=True, clear=True).create(paths.env_dir)
    paths.work_dir.mkdir(parents=True, exist_ok=True)
    for command in smoke_commands(paths, extra):
        run_command(command, timeout)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install Codex Observe into a clean venv and run synthetic smoke checks."
    )
    parser.add_argument(
        "--extra",
        choices=["none", "visual", "dev"],
        default="none",
        help="Optional dependency extra to install and verify.",
    )
    parser.add_argument(
        "--work-dir",
        default=None,
        help="Directory for the temporary venv and synthetic artifacts. Defaults to a temp dir.",
    )
    parser.add_argument(
        "--keep-env",
        action="store_true",
        help="Keep the temporary venv and synthetic artifacts after the run.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-command timeout in seconds.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if args.work_dir:
        base_dir = Path(args.work_dir).expanduser().resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir = tempfile.TemporaryDirectory(prefix="codex-observe-smoke-")
        base_dir = Path(temp_dir.name).resolve()

    paths = SmokePaths(
        root=ROOT, env_dir=base_dir / ".venv-smoke", work_dir=base_dir / "work"
    )
    try:
        run_smoke(paths, args.extra, args.timeout)
    except subprocess.CalledProcessError as exc:
        print(
            f"Clean-install smoke failed with exit code {exc.returncode}.",
            file=sys.stderr,
        )
        return exc.returncode or 1
    except subprocess.TimeoutExpired as exc:
        print(
            f"Clean-install smoke timed out while running: {exc.cmd}", file=sys.stderr
        )
        return 1
    finally:
        if args.keep_env:
            print(f"Kept smoke environment at {base_dir}")
        elif temp_dir is None:
            shutil.rmtree(base_dir, ignore_errors=True)
        else:
            temp_dir.cleanup()

    print("Clean-install smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
