from __future__ import annotations

import tomllib
from pathlib import Path

import codex_observe


ROOT = Path(__file__).resolve().parents[1]


def test_package_metadata_is_release_ready() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["name"] == "codex-observe"
    assert project["version"] == codex_observe.__version__
    assert project["readme"] == "README.md"
    assert project["license"] == "MIT"
    assert project["requires-python"] == ">=3.10"

    urls = project["urls"]
    assert urls["Repository"].startswith("https://github.com/")
    assert urls["Issues"].endswith("/issues")
    assert urls["Changelog"].endswith("/CHANGELOG.md")

    optional = pyproject["project"]["optional-dependencies"]
    assert set(optional["visual"]) == {"pillow>=10", "playwright"}
    assert {"pillow>=10", "playwright", "pytest", "ruff"}.issubset(set(optional["dev"]))

    classifiers = set(project["classifiers"])
    assert "Framework :: Streamlit" in classifiers
    assert "Programming Language :: Python :: 3.10" in classifiers
    assert "Programming Language :: Python :: 3.11" in classifiers
    assert "Programming Language :: Python :: 3.12" in classifiers


def test_release_documents_exist_and_are_plain_utf8() -> None:
    for relative_path in [
        "LICENSE",
        "CHANGELOG.md",
        "docs/RELEASE.md",
        "docs/DISTRIBUTION.md",
        "CONTRIBUTING.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
    ]:
        path = ROOT / relative_path
        raw = path.read_bytes()

        assert raw
        assert not raw.startswith(b"\xef\xbb\xbf")
        raw.decode("utf-8")


def test_changelog_records_current_unreleased_work() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "## Unreleased" in changelog
    assert "codex-observe demo" in changelog
    assert "codex-observe doctor" in changelog
    assert "visual QA" in changelog


def test_distribution_policy_matches_package_metadata_and_readme() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    distribution = (ROOT / "docs/DISTRIBUTION.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    release = (ROOT / "docs/RELEASE.md").read_text(encoding="utf-8")

    assert pyproject["project"]["requires-python"] == ">=3.10"
    for version in ["Python 3.10", "Python 3.11", "Python 3.12"]:
        assert version in distribution
    for classifier in [
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ]:
        assert classifier in pyproject["project"]["classifiers"]

    assert "python -m pip install -e ." in distribution
    assert 'python -m pip install -e ".[visual]"' in distribution
    assert 'python -m pip install -e ".[dev]"' in distribution
    assert "ruff check" in distribution
    assert "ruff format --check" in distribution
    assert "PyPI publishing" in distribution
    assert "explicitly approved" in distribution
    assert "sample_from_uploaded.sqlite" in distribution
    assert "docs/DISTRIBUTION.md" in readme
    assert "docs/DISTRIBUTION.md" in release


def test_release_docs_do_not_contain_literal_newline_escape_artifacts() -> None:
    for relative_path in [
        "README.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "docs/AMAZING.md",
        "docs/BACKLOG.md",
        "docs/DISTRIBUTION.md",
        "docs/NEXT_WAVE.md",
        "docs/REAL_LOG_FEEDBACK.md",
        "docs/RELEASE.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
    ]:
        body = (ROOT / relative_path).read_text(encoding="utf-8")

        assert "`r`n" not in body
        assert "\r\n" not in body
