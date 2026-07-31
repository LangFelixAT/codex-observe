from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from PIL import Image

from codex_observe.schema import SCHEMA_SQL


VISUAL_MANIFEST_SCHEMA_VERSION = "codex-observe.visual-manifest.v1"
PROFILE_DEMO = "demo"
PROFILE_REAL = "real"
VISUAL_PROFILES = {PROFILE_DEMO, PROFILE_REAL}
DEFAULT_VISUAL_QA_PORT = 8501
AUTO_PORT_SEARCH_START = 8600
AUTO_PORT_SEARCH_END = 8700

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "narrow": {"width": 390, "height": 900},
}


def port_is_available(host: str, port: int) -> bool:
    probe_host = "127.0.0.1" if host in {"", "0.0.0.0"} else host
    try:
        with socket.create_connection((probe_host, port), timeout=0.25):
            return False
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
    except OSError:
        return False
    return True


def port_block_is_available(host: str, base_port: int, width: int = 3) -> bool:
    return all(port_is_available(host, base_port + offset) for offset in range(width))


def find_free_port_block(
    host: str,
    *,
    start: int = AUTO_PORT_SEARCH_START,
    end: int = AUTO_PORT_SEARCH_END,
    width: int = 3,
) -> int | None:
    for base_port in range(start, end - width + 2):
        if port_block_is_available(host, base_port, width):
            return base_port
    return None


def resolve_visual_qa_port(host: str, requested_port: int) -> int:
    if requested_port < 1 or requested_port > 65533:
        raise RuntimeError("Visual QA needs a base port between 1 and 65533.")
    if port_block_is_available(host, requested_port):
        return requested_port
    if requested_port != DEFAULT_VISUAL_QA_PORT:
        raise RuntimeError(
            f"Visual QA port block {requested_port}-{requested_port + 2} is busy. "
            "Stop the existing server or pass a different --port."
        )
    fallback = find_free_port_block(host)
    if fallback is None:
        raise RuntimeError(
            f"Visual QA port block {requested_port}-{requested_port + 2} is busy, "
            f"and no free 3-port block was found from {AUTO_PORT_SEARCH_START} "
            f"through {AUTO_PORT_SEARCH_END}. Stop an existing server or pass --port."
        )
    return fallback


def wait_for_server(url: str, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Streamlit did not become ready at {url}: {last_error}")


PLAYWRIGHT_INSTALL_HINT = (
    'Playwright is required for visual QA. Install it with `python -m pip install -e ".[visual]"` '
    'or `python -m pip install -e ".[dev]"`, then run `python -m playwright install chromium`.'
)

TAB_CHECKS = {
    "Overview": "Run triage",
    "Agent detail": "Thread brief",
    "Timeline & jumps": "Timeline quick read",
    "Tools": "Tool quick read",
    "Duplication": "Duplication quick read",
    "Raw tables": "Data inventory",
}
EXPECTED_QUICK_READ_EVIDENCE = [
    {"tab": tab, "text": text} for tab, text in TAB_CHECKS.items()
]

EXPECTED_METRIC_CARDS = [
    "Threads",
    "Focus",
    "Duration",
    "Largest thread",
    "Uncached input",
]
EXPECTED_SIDEBAR_RISK_LABELS = ["High risk", "Low risk"]
EXPECTED_SIDEBAR_RISK_FILTER = ["Risk filter"]
EXPECTED_SIDEBAR_FOCUS_FILTER = {
    "label": "Focus filter",
    "target": "Monitor",
    "exercised": True,
    "filtered": True,
    "selection_valid": True,
    "restored": True,
}
FOCUS_LABELS = [
    "Duration",
    "Thread",
    "Guardian",
    "Replay",
    "Uncached",
    "Tool out",
    "Tokens",
    "Monitor",
]


def focus_option_label(
    option_labels: list[str], target_label: str | None
) -> str | None:
    if target_label == "All focuses":
        return next((label for label in option_labels if label == target_label), None)
    preferred = next(
        (
            label
            for label in option_labels
            if target_label
            and label.startswith(f"{target_label} (")
            and not label.endswith("(0)")
        ),
        None,
    )
    return preferred or next(
        (
            label
            for label in option_labels
            if label != "All focuses" and not label.endswith("(0)")
        ),
        None,
    )


def open_selectbox(selector, viewport_name: str) -> None:
    if viewport_name == "narrow":
        selector.press("ArrowDown")
    else:
        selector.click()


def open_option_labels(page, timeout_ms: int) -> list[str]:
    page.wait_for_function(
        "() => document.querySelectorAll('[role=option]').length > 0",
        timeout=timeout_ms,
    )
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('[role="option"]')).map(
  (option) => (option.innerText || option.textContent || '').trim()
)
        """
    )


def select_open_option(page, option_label: str, timeout_ms: int) -> bool:
    page.wait_for_function(
        r"""
label => Array.from(document.querySelectorAll('[role="option"]')).some(
  (option) => (option.innerText || option.textContent || '').trim() === label
)
        """,
        arg=option_label,
        timeout=timeout_ms,
    )
    return bool(
        page.evaluate(
            r"""
label => {
  const option = Array.from(document.querySelectorAll('[role="option"]')).find(
    (item) => (item.innerText || item.textContent || '').trim() === label
  );
  if (!option) return false;
  option.click();
  return true;
}
            """,
            option_label,
        )
    )


EXPECTED_SIDEBAR_SESSION_SEARCH = ["Find session"]
EXPECTED_SIDEBAR_SESSION_DETAILS = ["Focus: Thread", "24 min duration", "6 snapshots"]
EXPECTED_DOWNLOAD_CONTROLS = [
    "Download report MD",
    "Download report JSON",
    "Download comparison MD",
    "Download comparison JSON",
]
EXPECTED_COMPARISON_SELECTION = {
    "label": "Compare with run",
    "relationship": "Next run",
    "risk": "Low risk",
    "session_id": "demo-session-focused-followup",
}
EXPECTED_COMPARISON_DIRECTION = {
    "label": "Comparison direction",
    "before": "2026-01-01T12:00+00:00 | High risk | 57.5k tokens",
    "after": "2026-01-01T12:24+00:00 | Low risk | 8.4k tokens",
    "basis": "Ordered by start time.",
}
EXPECTED_COMPARISON_PREVIEW = {
    "label": "Comparison quick read",
    "verdict": "improved",
    "triage_movement": "improved",
    "next_step": "Keep the change, then target persisted diagnostic: Largest thread drives the run.",
    "follow_up": "Next validation command",
    "follow_up_command": "codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json",
}
EXPECTED_COMPARISON_DELTAS = [
    {"label": "Total tokens", "direction": "improved"},
    {"label": "Usage snapshots", "direction": "changed"},
    {"label": "Largest thread tokens", "direction": "improved"},
]
EXPECTED_COMPARISON_REVIEW_PATH = [
    "Comparison review path",
    "Read the verdict",
    "Act on the recommendation",
    "Export the next run",
    "Compare against this after run",
    "File safe feedback",
]
EXPECTED_DEFAULT_METRIC_VALUES = {
    "Threads": "3",
    "Focus": "Thread",
    "Duration": "24 min",
    "Largest thread": "33.2k tokens (57.7%)",
    "Uncached input": "22.7k tokens (39.5%)",
}


EXPECTED_RISK_DISTRIBUTION = [
    "Risk distribution",
    "High risk",
    "Low risk",
    "2 imported conversations",
]

EXPECTED_PORTFOLIO_BRIEFING = [
    "Portfolio briefing",
    "1 of 2 sessions are high risk.",
    "Start with the recommended high-risk run",
    "Dominant pattern: Largest thread concentration",
    "max 57.7%",
    "50.0% high risk.",
]

EXPECTED_SUCCESS_TARGET = {
    "metric": "largest_thread_share_pct",
    "current": "57.7%",
    "target": "below 50.0%",
}

EXPECTED_OPERATOR_BRIEFING = {
    "label": "Operator briefing",
    "risk": "High risk",
    "best_habit": "Set a stop condition for the dominant thread",
    "scale": "33.2k tokens (57.7% of run)",
    "proof_target": "largest_thread_share_pct: 57.7% -> below 50.0%",
}
EXPECTED_REVIEW_PATH = [
    "Next review path",
    "Save report JSON",
    "Compare workflow change",
    "Validate next run",
    "File safe feedback",
    "PUBLIC_TOUR_FEEDBACK.md",
]
EXPECTED_NEXT_RUN_CHECKLIST = [
    "Next run checklist",
    "Before next run",
    "During next run",
    "After next run",
    "Set a stop condition for the dominant thread",
    "largest_thread_share_pct",
    "Export next-run-report.json",
]

EXPECTED_NEXT_RUN_BRIEF = [
    "Next run brief",
    "Set a stop condition for the dominant thread",
    "Largest thread drives the run",
    "largest_thread_share_pct: 57.7% -> below 50.0%",
    "Pause or split the run when one thread starts to dominate the work.",
]
EXPECTED_NEXT_RUN_COPY_PROMPT = "Next Codex run plan:"

EXPECTED_FEEDBACK_HANDOFF = [
    "Safe feedback handoff",
    "docs/PUBLIC_TOUR_FEEDBACK.md",
    ".github/ISSUE_TEMPLATE/public_tour_feedback.yml",
    "synthetic or reviewed-redacted aggregate evidence",
    "codex-observe report JSON or Markdown",
    "private prompts",
    "Do not collect",
]

EMPTY_STATE_CHECKS = {
    "missing_database": "No database found",
    "empty_database": "No conversations imported yet",
}
EXPECTED_EMPTY_STATE_COMMAND_LABELS = [
    "Try synthetic data",
    "Ingest private logs locally",
    "Check database health",
]
EXPECTED_EMPTY_STATE_COMMAND_SNIPPETS = [
    "codex-observe demo --serve --db",
    "codex-observe ingest ~/.codex/sessions --db",
    "codex-observe doctor --db",
]


def visible_text_has_error(text: str) -> bool:
    error_markers = [
        "Traceback",
        "Exception",
        "StreamlitAPIException",
        "ModuleNotFoundError",
    ]
    return any(marker in text for marker in error_markers)


def layout_review_failures(
    snapshot: dict[str, object], viewport_name: str
) -> list[str]:
    failures: list[str] = []
    viewport_width = int(snapshot.get("viewport_width") or 0)
    document_width = int(snapshot.get("document_width") or 0)
    if viewport_width and document_width > viewport_width + 2:
        failures.append(
            f"{viewport_name}: horizontal overflow {document_width}px exceeds viewport {viewport_width}px"
        )

    for item in snapshot.get("overflowing_elements", []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("tag") or "element")[:80]
        failures.append(f"{viewport_name}: visible element overflows viewport: {label}")

    for item in snapshot.get("clipped_text_elements", []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("tag") or "text")[:80]
        if label == "Stop":
            continue
        failures.append(f"{viewport_name}: visible text appears clipped: {label}")

    return failures


def collect_sidebar_risk_labels(page) -> list[str]:
    return page.evaluate(
        r"""
() => {
  const text = document.body.innerText || '';
  return ['High risk', 'Medium risk', 'Low risk', 'Unknown risk'].filter((label) => text.includes(label));
}
        """
    )


def sidebar_risk_label_failures(
    labels: list[str], viewport_name: str, profile: str = PROFILE_DEMO
) -> list[str]:
    observed = set(labels)
    if profile == PROFILE_REAL:
        return [] if observed else [f"{viewport_name}: no sidebar risk label found"]
    return [
        f"{viewport_name}: sidebar risk label not found: {label}"
        for label in EXPECTED_SIDEBAR_RISK_LABELS
        if label not in observed
    ]


def collect_sidebar_risk_filter(page) -> list[str]:
    return page.evaluate(
        r"""
() => {
  const evidence = new Set();
  const text = document.body.innerText || '';
  for (const label of ['Risk filter']) {
    if (text.includes(label)) evidence.add(label);
  }
  for (const element of document.querySelectorAll('[aria-label]')) {
    const label = element.getAttribute('aria-label') || '';
    if (label.includes('Risk filter')) evidence.add('Risk filter');
  }
  return Array.from(evidence);
}
        """
    )


def sidebar_risk_filter_failures(labels: list[str], viewport_name: str) -> list[str]:
    observed = set(labels)
    return [
        f"{viewport_name}: sidebar Risk filter evidence not found: {label}"
        for label in EXPECTED_SIDEBAR_RISK_FILTER
        if label not in observed
    ]


def sidebar_focus_filter_failures(
    evidence: dict[str, object] | None,
    viewport_name: str,
    profile: str = PROFILE_DEMO,
) -> list[str]:
    if not isinstance(evidence, dict):
        return [f"{viewport_name}: sidebar Focus filter evidence not found"]
    failures = []
    stage = str(evidence.get("stage") or "")
    if stage and stage != "complete":
        failures.append(
            f"{viewport_name}: sidebar Focus filter interaction stopped at {stage}"
        )
    if evidence.get("label") != "Focus filter":
        failures.append(f"{viewport_name}: sidebar Focus filter label not found")
    for key in ["exercised", "filtered", "selection_valid", "restored"]:
        if evidence.get(key) is not True:
            failures.append(
                f"{viewport_name}: sidebar Focus filter {key.replace('_', ' ')} not verified"
            )
    target = str(evidence.get("target") or "")
    if profile == PROFILE_DEMO and target != "Monitor":
        failures.append(
            f"{viewport_name}: sidebar Focus filter expected Monitor target, got {target or 'none'}"
        )
    elif profile == PROFILE_REAL and target not in FOCUS_LABELS:
        failures.append(
            f"{viewport_name}: sidebar Focus filter target is not a stable Focus category"
        )
    return failures


def exercise_sidebar_focus_filter(
    page, viewport_name: str, profile: str = PROFILE_DEMO
) -> dict[str, object]:
    evidence: dict[str, object] = {
        "label": "Focus filter",
        "target": None,
        "exercised": False,
        "filtered": False,
        "selection_valid": False,
        "restored": False,
        "stage": "locate-control",
    }
    timeout_ms = 60000 if profile == PROFILE_REAL else 10000
    opened_sidebar = False

    try:
        selector = page.get_by_label("Focus filter")
        visible_selector = next(
            (item for item in selector.all() if item.is_visible()), None
        )
        if visible_selector is None:
            opener = page.get_by_role(
                "button", name=re.compile("open sidebar", re.IGNORECASE)
            )
            if opener.count() > 0:
                opener.first.click()
                opened_sidebar = True
            else:
                opened_sidebar = bool(
                    page.evaluate(
                        r"""
() => {
  const root = document.querySelector('[data-testid="stSidebarCollapsedControl"]');
  const button = root?.matches('button') ? root : root?.querySelector('button');
  if (!button) return false;
  button.click();
  return true;
}
                        """
                    )
                )
            if not opened_sidebar:
                return evidence
            page.get_by_label("Focus filter").first.wait_for(
                state="visible", timeout=timeout_ms
            )
            selector = page.get_by_label("Focus filter")
            visible_selector = next(
                (item for item in selector.all() if item.is_visible()), None
            )
        if visible_selector is None:
            return evidence

        initial_body = page_body_text(page, timeout_ms)
        initial_focus = next(
            (label for label in FOCUS_LABELS if f"Focus: {label}" in initial_body),
            None,
        )
        initial_risk_match = re.search(
            r"\b(High|Medium|Low|Unknown) risk\s*\|", initial_body
        )
        initial_risk = initial_risk_match.group(1) if initial_risk_match else None
        initial_button_label = page.evaluate(
            r"""
() => {
  const selected = Array.from(document.querySelectorAll('button')).find(
    (button) => (button.innerText || '').trim().startsWith('> ')
  );
  if (!selected) return null;
  return (selected.innerText || '').trim().slice(2);
}
            """
        )

        evidence["stage"] = "open-options"
        open_selectbox(visible_selector, viewport_name)
        target_label = "Monitor" if profile == PROFILE_DEMO else initial_focus
        option_labels = open_option_labels(page, timeout_ms)
        target_option = focus_option_label(option_labels, target_label)
        if target_option is None:
            page.keyboard.press("Escape")
            return evidence
        target_label = target_option.rsplit(" (", 1)[0]
        evidence["stage"] = "apply-filter"
        if not select_open_option(page, target_option, timeout_ms):
            return evidence
        page.wait_for_function(
            "() => document.body.innerText.includes('after focus filter')",
            timeout=timeout_ms,
        )
        filtered_body = page_body_text(page, timeout_ms)
        match = re.search(
            r"Showing ([\d,]+) of ([\d,]+) conversations after .*focus filter",
            filtered_body,
        )
        narrowed = bool(
            match
            and int(match.group(1).replace(",", ""))
            < int(match.group(2).replace(",", ""))
        )
        evidence.update(
            {
                "target": target_label,
                "exercised": True,
                "filtered": narrowed,
                "selection_valid": (
                    f"Focus: {target_label}" in filtered_body
                    and "No conversations match" not in filtered_body
                    and not visible_text_has_error(filtered_body)
                ),
            }
        )

        evidence["stage"] = "restore-filter"
        focus_selector = page.get_by_label("Focus filter")
        visible_focus_selector = next(
            item for item in focus_selector.all() if item.is_visible()
        )
        open_selectbox(visible_focus_selector, viewport_name)
        if not select_open_option(page, "All focuses", timeout_ms):
            return evidence
        page.wait_for_function(
            "() => !document.body.innerText.includes('after focus filter')",
            timeout=timeout_ms,
        )

        evidence["stage"] = "restore-session"
        restored_selection = False
        if initial_button_label:
            with contextlib.suppress(Exception):
                page.wait_for_function(
                    r"""
label => Array.from(document.querySelectorAll('button')).some((button) => {
  const text = (button.innerText || '').trim();
  return text === label || text === '> ' + label;
})
                    """,
                    arg=initial_button_label,
                    timeout=timeout_ms,
                )
                restored_selection = page.evaluate(
                    r"""
label => {
  const target = Array.from(document.querySelectorAll('button')).find((button) => {
    const text = (button.innerText || '').trim();
    return text === label || text === '> ' + label;
  });
  if (!target) return false;
  target.click();
  return true;
}
                    """,
                    initial_button_label,
                )
        if not restored_selection and initial_focus:
            with contextlib.suppress(Exception):
                page.wait_for_function(
                    r"""
focus => {
  const marker = '| ' + focus + ' |';
  return Array.from(document.querySelectorAll('button')).some(
    (button) => (button.innerText || '').includes(marker)
  );
}
                    """,
                    arg=initial_focus,
                    timeout=timeout_ms,
                )
                restored_selection = page.evaluate(
                    r"""
focus => {
  const marker = '| ' + focus + ' |';
  const target = Array.from(document.querySelectorAll('button')).find(
    (button) => (button.innerText || '').includes(marker)
  );
  if (!target) return false;
  target.click();
  return true;
}
                    """,
                    initial_focus,
                )
        if not restored_selection and viewport_name == "narrow" and initial_risk:
            risk_selector = page.get_by_label("Risk filter")
            visible_risk_selector = next(
                (item for item in risk_selector.all() if item.is_visible()), None
            )
            if visible_risk_selector is not None:
                visible_risk_selector.evaluate("element => element.click()")
                page.keyboard.type(initial_risk)
                page.keyboard.press("Enter")
                page.wait_for_function(
                    "() => document.body.innerText.includes('after risk filter')",
                    timeout=timeout_ms,
                )
                open_selectbox(page.get_by_label("Risk filter").first, "narrow")
                if not select_open_option(page, "All risks", timeout_ms):
                    return evidence
                page.wait_for_function(
                    "() => !document.body.innerText.includes('after risk filter')",
                    timeout=timeout_ms,
                )
                restored_selection = True
        if restored_selection and initial_button_label:
            page.wait_for_function(
                r"""
label => Array.from(document.querySelectorAll('button')).some(
  (button) => (button.innerText || '').trim() === '> ' + label
)
                """,
                arg=initial_button_label,
                timeout=timeout_ms,
            )
        elif restored_selection and initial_focus:
            page.wait_for_function(
                r"""
focus => {
  const marker = '| ' + focus + ' |';
  return Array.from(document.querySelectorAll('button')).some((button) => {
    const text = (button.innerText || '').trim();
    return text.startsWith('> ') && text.includes(marker);
  });
}
                """,
                arg=initial_focus,
                timeout=timeout_ms,
            )
        if restored_selection and initial_focus:
            page.wait_for_function(
                r"""
focus => {
  const visibleFocusValues = Array.from(document.querySelectorAll('.co-metric-card'))
    .filter((card) => {
      const style = getComputedStyle(card);
      const rect = card.getBoundingClientRect();
      const label = (card.querySelector('.co-metric-label')?.innerText || '').trim();
      return label === 'Focus' && style.display !== 'none' &&
        style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
    })
    .map((card) => (card.querySelector('.co-metric-value')?.innerText || '').trim());
  return visibleFocusValues.length > 0 &&
    visibleFocusValues.every((value) => value === focus);
}
                """,
                arg=initial_focus,
                timeout=timeout_ms,
            )
        restored_body = page_body_text(page, timeout_ms)
        evidence["restored"] = (
            "No conversations match" not in restored_body
            and "after focus filter" not in restored_body
            and (not initial_focus or f"Focus: {initial_focus}" in restored_body)
            and not visible_text_has_error(restored_body)
        )
        evidence["stage"] = "complete"
    except Exception as exc:
        evidence["stage"] = f"failed:{evidence['stage']}:{type(exc).__name__}"
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
    finally:
        if opened_sidebar:
            try:
                closer = page.get_by_role(
                    "button", name=re.compile("close sidebar", re.IGNORECASE)
                )
                if closer.count() > 0 and closer.first.is_visible():
                    closer.first.click()
                else:
                    page.evaluate(
                        r"""
() => {
  const root = document.querySelector('[data-testid="stSidebarCollapseButton"]');
  const button = root?.matches('button') ? root : root?.querySelector('button');
  if (button) button.click();
}
                        """
                    )
            except Exception:
                pass
    return evidence


def collect_sidebar_session_search(page) -> list[str]:
    return page.evaluate(
        r"""
() => {
  const evidence = new Set();
  const text = document.body.innerText || '';
  for (const label of ['Find session']) {
    if (text.includes(label)) evidence.add(label);
  }
  for (const element of document.querySelectorAll('[aria-label]')) {
    const label = element.getAttribute('aria-label') || '';
    if (label.includes('Find session')) evidence.add('Find session');
  }
  return Array.from(evidence);
}
        """
    )


def sidebar_session_search_failures(labels: list[str], viewport_name: str) -> list[str]:
    observed = set(labels)
    return [
        f"{viewport_name}: sidebar session search evidence not found: {label}"
        for label in EXPECTED_SIDEBAR_SESSION_SEARCH
        if label not in observed
    ]


def collect_sidebar_session_details(page) -> list[str]:
    return page.evaluate(
        r"""
() => {
  const text = document.body.innerText || '';
  const snapshotMatches = text.match(/\b[\d,.]+[kKmMbB]?\s+snapshots?\b/g) || [];
  const durationMatches = text.match(/\b\d+(?:\.\d+)?\s+(?:min|hours?|days?)(?:\s+|[^\w]+)duration\b/g) || [];
  const focusMatches = text.match(/Focus:\s+\w+(?:\s+\w+)?/g) || [];
  return Array.from(new Set([...focusMatches, ...durationMatches, ...snapshotMatches]));
}
        """
    )


def sidebar_session_detail_failures(
    details: list[str], viewport_name: str, profile: str = PROFILE_DEMO
) -> list[str]:
    observed = set(details)
    if profile == PROFILE_REAL:
        return []
    return [
        f"{viewport_name}: sidebar session detail not found: {detail}"
        for detail in EXPECTED_SIDEBAR_SESSION_DETAILS
        if detail not in observed
    ]


def collect_download_controls(page) -> list[str]:
    return page.evaluate(
        r"""
() => {
  const text = document.body.innerText || '';
  return ['Download report MD', 'Download report JSON', 'Download comparison MD', 'Download comparison JSON'].filter((label) => text.includes(label));
}
        """
    )


def download_control_failures(
    labels: list[str], viewport_name: str, profile: str = PROFILE_DEMO
) -> list[str]:
    observed = set(labels)
    expected = (
        ["Download report MD", "Download report JSON"]
        if profile == PROFILE_REAL
        else EXPECTED_DOWNLOAD_CONTROLS
    )
    return [
        f"{viewport_name}: report download control not found: {label}"
        for label in expected
        if label not in observed
    ]


def collect_report_scope_warnings(page) -> list[str]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-report-scope')).map((card) => (card.innerText || '').replace(/\s+/g, ' ').trim()).filter(Boolean)
        """
    )


def collect_comparison_selections(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('[data-testid="stSelectbox"]')).map((control) => ({
  label: (control.querySelector('label')?.innerText || '').replace(/\s+/g, ' ').trim(),
  selected: (control.querySelector('input')?.value || '').replace(/\s+/g, ' ').trim(),
  body: (control.innerText || '').replace(/\s+/g, ' ').trim(),
})).filter((item) => item.label === 'Compare with run')
        """
    )


def comparison_selection_failures(
    selections: list[dict[str, str]],
    viewport_name: str,
    profile: str = PROFILE_DEMO,
) -> list[str]:
    if not selections:
        return (
            []
            if profile == PROFILE_REAL
            else [f"{viewport_name}: comparison selection not rendered"]
        )
    observed = selections[0]
    text = " ".join(
        str(observed.get(key) or "") for key in ["label", "selected", "body"]
    )
    if profile == PROFILE_REAL:
        failures = []
        if "Compare with run" not in text:
            failures.append(f"{viewport_name}: comparison selection missing label")
        if not any(
            relationship in text
            for relationship in [
                "Next run",
                "Previous run",
                "Later run",
                "Earlier run",
                "Same time",
                "Time unavailable",
            ]
        ):
            failures.append(
                f"{viewport_name}: comparison selection missing chronological relationship"
            )
        return failures
    return [
        f"{viewport_name}: comparison selection missing {key}: {expected}"
        for key, expected in EXPECTED_COMPARISON_SELECTION.items()
        if expected not in text
    ]


def collect_comparison_directions(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-comparison-direction')).map((card) => {
  const runs = Array.from(card.querySelectorAll('.co-comparison-direction-run'));
  return {
    label: (card.querySelector('h3')?.innerText || '').replace(/\s+/g, ' ').trim(),
    before: (runs[0]?.querySelector('span')?.innerText || '').replace(/\s+/g, ' ').trim(),
    after: (runs[1]?.querySelector('span')?.innerText || '').replace(/\s+/g, ' ').trim(),
    basis: (card.querySelector('p')?.innerText || '').replace(/\s+/g, ' ').trim(),
  };
}).filter((item) => item.label || item.before || item.after)
        """
    )


def comparison_direction_failures(
    directions: list[dict[str, str]],
    viewport_name: str,
    profile: str = PROFILE_DEMO,
) -> list[str]:
    if not directions:
        return (
            []
            if profile == PROFILE_REAL
            else [f"{viewport_name}: comparison direction card not rendered"]
        )
    observed = directions[0]
    if profile == PROFILE_REAL:
        return [
            f"{viewport_name}: comparison direction missing {key}"
            for key in ["label", "before", "after", "basis"]
            if not str(observed.get(key) or "")
        ]
    return [
        f"{viewport_name}: comparison direction {key} expected {expected}, got {observed.get(key) or 'missing'}"
        for key, expected in EXPECTED_COMPARISON_DIRECTION.items()
        if str(observed.get(key) or "") != expected
    ]


def collect_comparison_previews(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-comparison-preview')).map((card) => ({
  label: (card.querySelector('h3')?.innerText || '').replace(/\s+/g, ' ').trim(),
  body: (card.innerText || '').replace(/\s+/g, ' ').trim(),
})).filter((item) => item.label || item.body)
        """
    )


def comparison_preview_failures(
    previews: list[dict[str, str]],
    viewport_name: str,
    profile: str = PROFILE_DEMO,
) -> list[str]:
    if not previews:
        return (
            []
            if profile == PROFILE_REAL
            else [f"{viewport_name}: comparison preview card not rendered"]
        )
    body = str(previews[0].get("body") or "")
    if profile == PROFILE_REAL:
        return (
            []
            if "Comparison quick read" in body
            else [f"{viewport_name}: comparison preview missing label"]
        )
    failures = []
    for key, expected in EXPECTED_COMPARISON_PREVIEW.items():
        if expected not in body:
            failures.append(
                f"{viewport_name}: comparison preview missing {key}: {expected}"
            )
    return failures


def collect_comparison_scope_warnings(page) -> list[str]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-comparison-scope')).map((card) => (card.innerText || '').replace(/\s+/g, ' ').trim()).filter(Boolean)
        """
    )


def collect_comparison_review_paths(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-comparison-review-path')).map((card) => ({
  label: (card.querySelector('strong')?.innerText || '').replace(/\s+/g, ' ').trim(),
  body: (card.innerText || '').replace(/\s+/g, ' ').trim(),
})).filter((item) => item.label || item.body)
        """
    )


def comparison_review_path_failures(
    paths: list[dict[str, str]],
    viewport_name: str,
    profile: str = PROFILE_DEMO,
) -> list[str]:
    if not paths:
        return (
            []
            if profile == PROFILE_REAL
            else [f"{viewport_name}: comparison review path not rendered"]
        )
    body = str(paths[0].get("body") or "")
    return [
        f"{viewport_name}: comparison review path missing: {expected}"
        for expected in EXPECTED_COMPARISON_REVIEW_PATH
        if expected not in body
    ]


def collect_comparison_deltas(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-comparison-delta')).map((card) => {
  const lines = Array.from(card.querySelectorAll('span')).map((span) => (span.innerText || '').replace(/\s+/g, ' ').trim());
  return {
    label: (card.querySelector('strong')?.innerText || '').replace(/\s+/g, ' ').trim(),
    before_after: lines[0] || '',
    delta: lines[1] || '',
  };
}).filter((item) => item.label || item.delta)
        """
    )


def comparison_delta_failures(
    deltas: list[dict[str, str]],
    viewport_name: str,
    profile: str = PROFILE_DEMO,
) -> list[str]:
    if not deltas:
        return (
            []
            if profile == PROFILE_REAL
            else [f"{viewport_name}: comparison delta cards not rendered"]
        )
    if profile == PROFILE_REAL:
        failures = []
        direction_words = ("improved", "regressed", "changed", "unchanged")
        for index, item in enumerate(deltas, start=1):
            label = str(item.get("label") or "") if isinstance(item, dict) else ""
            delta = str(item.get("delta") or "") if isinstance(item, dict) else ""
            if not label:
                failures.append(
                    f"{viewport_name}: comparison delta card {index} missing label"
                )
            if not any(word in delta for word in direction_words):
                failures.append(
                    f"{viewport_name}: comparison delta {label or index} missing direction"
                )
        return failures
    failures = []
    observed = {
        str(item.get("label") or ""): str(item.get("delta") or "")
        for item in deltas
        if isinstance(item, dict)
    }
    for expected in EXPECTED_COMPARISON_DELTAS:
        label = expected["label"]
        direction = expected["direction"]
        actual = observed.get(label)
        if actual is None:
            failures.append(f"{viewport_name}: comparison delta not found: {label}")
        elif direction not in actual:
            failures.append(
                f"{viewport_name}: comparison delta {label} missing direction: {direction}"
            )
    return failures


def collect_risk_distributions(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-risk-distribution')).map((card) => ({
  label: (card.querySelector('h3')?.innerText || '').replace(/\s+/g, ' ').trim(),
  body: (card.innerText || '').replace(/\s+/g, ' ').trim(),
})).filter((item) => item.label || item.body)
        """
    )


def risk_distribution_failures(
    distributions: list[dict[str, str]],
    viewport_name: str,
    profile: str = PROFILE_DEMO,
) -> list[str]:
    if not distributions:
        return [f"{viewport_name}: risk distribution card not rendered"]
    body = str(distributions[0].get("body") or "")
    if profile == PROFILE_REAL:
        failures = []
        for expected in ["Risk distribution", "imported conversations"]:
            if expected not in body:
                failures.append(
                    f"{viewport_name}: risk distribution missing: {expected}"
                )
        if not any(label in body for label in ["High risk", "Medium risk", "Low risk"]):
            failures.append(f"{viewport_name}: risk distribution missing risk labels")
        return failures
    return [
        f"{viewport_name}: risk distribution missing: {expected}"
        for expected in EXPECTED_RISK_DISTRIBUTION
        if expected not in body
    ]


def collect_portfolio_briefings(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-portfolio-briefing')).map((card) => ({
  label: (card.querySelector('h3')?.innerText || '').replace(/\s+/g, ' ').trim(),
  body: (card.innerText || '').replace(/\s+/g, ' ').trim(),
})).filter((item) => item.label || item.body)
        """
    )


def portfolio_briefing_failures(
    briefings: list[dict[str, str]],
    viewport_name: str,
    profile: str = PROFILE_DEMO,
) -> list[str]:
    if not briefings:
        return [f"{viewport_name}: portfolio briefing card not rendered"]
    body = str(briefings[0].get("body") or "")
    if profile == PROFILE_REAL:
        return [
            f"{viewport_name}: portfolio briefing missing: {expected}"
            for expected in ["Portfolio briefing", "high risk"]
            if expected not in body
        ]
    return [
        f"{viewport_name}: portfolio briefing missing: {expected}"
        for expected in EXPECTED_PORTFOLIO_BRIEFING
        if expected not in body
    ]


def collect_metric_cards(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-metric-card')).map((card) => ({
  label: (card.querySelector('.co-metric-label')?.innerText || '').replace(/\s+/g, ' ').trim(),
  value: (card.querySelector('.co-metric-value')?.innerText || '').replace(/\s+/g, ' ').trim(),
})).filter((card) => card.label && card.value)
        """
    )


def metric_card_failures(cards: list[dict[str, str]], viewport_name: str) -> list[str]:
    labels = {str(card.get("label") or "") for card in cards if isinstance(card, dict)}
    failures = []
    for label in EXPECTED_METRIC_CARDS:
        if label not in labels:
            failures.append(f"{viewport_name}: metric card not rendered: {label}")
    return failures


def quick_read_evidence_failures(evidence: object, viewport_name: str) -> list[str]:
    if not isinstance(evidence, list):
        return [f"{viewport_name}: missing quick-read evidence"]
    observed = {
        str(item.get("tab") or ""): str(item.get("text") or "")
        for item in evidence
        if isinstance(item, dict)
    }
    failures = []
    for expected in EXPECTED_QUICK_READ_EVIDENCE:
        tab = expected["tab"]
        text = expected["text"]
        if observed.get(tab) != text:
            failures.append(
                f"{viewport_name}: quick-read evidence missing {tab}: {text}"
            )
    return failures


def metric_card_value_failures(
    cards: list[dict[str, str]],
    viewport_name: str,
    profile: str = PROFILE_DEMO,
) -> list[str]:
    if profile == PROFILE_REAL:
        return []
    by_label = {
        str(card.get("label") or ""): str(card.get("value") or "")
        for card in cards
        if isinstance(card, dict)
    }
    failures = []
    for label, expected_value in EXPECTED_DEFAULT_METRIC_VALUES.items():
        actual_value = by_label.get(label)
        if actual_value is None:
            continue
        if actual_value != expected_value:
            failures.append(
                f"{viewport_name}: metric card {label} expected {expected_value}, got {actual_value}"
            )
    return failures


def collect_success_targets(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => {
  const targets = Array.from(document.querySelectorAll('.co-success-target')).map((card) => {
    const heading = (card.querySelector('h3')?.innerText || '').replace(/\s+/g, ' ').trim();
    const match = heading.match(/^(.+?):\s*(.+?)\s*->\s*(.+)$/);
    return {
      metric: match ? match[1].trim() : heading,
      current: match ? match[2].trim() : '',
      target: match ? match[3].trim() : '',
    };
  }).filter((item) => item.metric);
  if (targets.length) {
    return targets;
  }
  const text = (document.body.innerText || '').replace(/\s+/g, ' ').trim();
  const fallback = text.match(/(largest_thread_share_pct):\s*(57\.7%)\s*->\s*(below 50\.0%)/);
  return fallback ? [{metric: fallback[1], current: fallback[2], target: fallback[3]}] : [];
}
        """
    )


def success_target_failures(
    targets: list[dict[str, str]],
    viewport_name: str,
    profile: str = PROFILE_DEMO,
) -> list[str]:
    if not targets:
        return [f"{viewport_name}: success target card not rendered"]
    observed = targets[0]
    if profile == PROFILE_REAL:
        return [
            f"{viewport_name}: success target {key} missing"
            for key in ["metric", "current", "target"]
            if not str(observed.get(key) or "")
        ]
    failures = []
    for key, expected_value in EXPECTED_SUCCESS_TARGET.items():
        actual_value = str(observed.get(key) or "")
        if actual_value != expected_value:
            failures.append(
                f"{viewport_name}: success target {key} expected {expected_value}, got {actual_value}"
            )
    return failures


def collect_operator_briefings(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-briefing')).map((card) => {
  const facts = Array.from(card.querySelectorAll('.co-briefing-fact'));
  const factByLabel = (label) => {
    const fact = facts.find((item) => (item.querySelector('strong')?.innerText || '').replace(/\s+/g, ' ').trim() === label);
    return fact ? Array.from(fact.querySelectorAll('p')).map((p) => (p.innerText || '').replace(/\s+/g, ' ').trim()) : [];
  };
  const bestHabit = factByLabel('Best next habit');
  const proofTarget = factByLabel('Proof target');
  return {
    label: (card.querySelector('.co-briefing-label')?.innerText || '').replace(/\s+/g, ' ').trim(),
    heading: (card.querySelector('h3')?.innerText || '').replace(/\s+/g, ' ').trim(),
    action: (card.querySelector('.co-briefing-risk-signal')?.innerText || '').replace(/\s+/g, ' ').trim(),
    best_habit: bestHabit[0] || '',
    scale: bestHabit[1] || '',
    proof_target: proofTarget[0] || '',
  };
}).filter((item) => item.label || item.heading || item.best_habit || item.proof_target)
        """
    )


def collect_answer_first_layout(page) -> dict[str, object]:
    return page.evaluate(
        r"""
() => {
  window.scrollTo(0, 0);
  const briefing = document.querySelector('.co-briefing');
  const metrics = document.querySelector('.co-metric-grid');
  if (!briefing || !metrics) return {};
  const briefingRect = briefing.getBoundingClientRect();
  const metricRect = metrics.getBoundingClientRect();
  return {
    briefing_before_metrics: briefingRect.top < metricRect.top,
    briefing_in_initial_viewport: briefingRect.top >= 0 && briefingRect.bottom <= window.innerHeight,
    briefing_top: Math.round(briefingRect.top),
    briefing_bottom: Math.round(briefingRect.bottom),
    metric_grid_top: Math.round(metricRect.top),
    viewport_height: window.innerHeight,
  };
}
        """
    )


def answer_first_layout_failures(
    layout: dict[str, object], viewport_name: str
) -> list[str]:
    if not layout:
        return [f"{viewport_name}: missing answer-first layout evidence"]
    failures = []
    if layout.get("briefing_before_metrics") is not True:
        failures.append(
            f"{viewport_name}: operator briefing does not precede metric grid"
        )
    if layout.get("briefing_in_initial_viewport") is not True:
        failures.append(
            f"{viewport_name}: operator briefing is not fully visible in initial viewport "
            f"(bottom {layout.get('briefing_bottom', 'unknown')}px, "
            f"viewport {layout.get('viewport_height', 'unknown')}px)"
        )
    return failures


def collect_action_first_layout(page) -> dict[str, object]:
    return page.evaluate(
        r"""
() => {
  window.scrollTo(0, 0);
  const briefing = document.querySelector('.co-briefing');
  const tablist = document.querySelector('[role="tablist"]');
  const checklist = document.querySelector('.co-next-run-checklist');
  const brief = document.querySelector('.co-next-run-brief');
  const comparison = Array.from(document.querySelectorAll('[data-testid="stSelectbox"]')).find(
    (item) => (item.innerText || '').includes('Compare with run')
  );
  const metrics = document.querySelector('.co-metric-grid');
  const copyBlock = Array.from(document.querySelectorAll('[data-testid="stCode"], .stCode')).find(
    (item) => (item.innerText || '').includes('Next Codex run plan:')
  );
  const missing = [
    ['briefing', briefing],
    ['tab navigation', tablist],
    ['next run checklist', checklist],
    ['next run brief', brief],
    ['copyable prompt', copyBlock],
    ['metric grid', metrics],
  ].filter(([, element]) => !element).map(([label]) => label);
  if (missing.length) return {missing};
  const rect = (element) => element.getBoundingClientRect();
  const briefingRect = rect(briefing);
  const tablistRect = rect(tablist);
  const checklistRect = rect(checklist);
  const briefRect = rect(brief);
  const copyRect = rect(copyBlock);
  const comparisonRect = comparison ? rect(comparison) : null;
  const metricRect = rect(metrics);
  const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
  const tabsVisible = tabs.filter((tab) => {
    const tabRect = rect(tab);
    return tabRect.width > 0 && tabRect.height > 0 && tabRect.left >= 0 && tabRect.right <= window.innerWidth && tabRect.top >= 0 && tabRect.bottom <= window.innerHeight;
  });
  return {
    briefing_before_tabs: briefingRect.bottom <= tablistRect.top,
    tabs_before_checklist: tablistRect.bottom <= checklistRect.top,
    checklist_before_brief: checklistRect.bottom <= briefRect.top,
    brief_before_copy_prompt: briefRect.bottom <= copyRect.top,
    comparison_present: Boolean(comparisonRect),
    copy_prompt_before_comparison: !comparisonRect || copyRect.bottom <= comparisonRect.top,
    comparison_before_metrics: !comparisonRect || comparisonRect.bottom <= metricRect.top,
    copy_prompt_before_metrics: copyRect.bottom <= metricRect.top,
    tabs_in_initial_viewport: tablistRect.top >= 0 && tablistRect.bottom <= window.innerHeight,
    tabs_visible_count: tabsVisible.length,
    tabs_total: tabs.length,
    briefing_bottom: Math.round(briefingRect.bottom),
    tablist_top: Math.round(tablistRect.top),
    tablist_bottom: Math.round(tablistRect.bottom),
    checklist_top: Math.round(checklistRect.top),
    brief_top: Math.round(briefRect.top),
    copy_prompt_top: Math.round(copyRect.top),
    comparison_top: comparisonRect ? Math.round(comparisonRect.top) : null,
    metric_grid_top: Math.round(metricRect.top),
    viewport_height: window.innerHeight,
  };
}
        """
    )


def action_first_layout_failures(
    layout: dict[str, object], viewport_name: str, profile: str = "demo"
) -> list[str]:
    if not layout:
        return [f"{viewport_name}: missing action-first layout evidence"]
    missing = layout.get("missing")
    if isinstance(missing, list) and missing:
        return [
            f"{viewport_name}: missing action-first elements: {', '.join(str(item) for item in missing)}"
        ]
    failures = []
    checks = {
        "briefing_before_tabs": "operator briefing does not precede tab navigation",
        "tabs_before_checklist": "tab navigation does not precede next run checklist",
        "checklist_before_brief": "next run checklist does not precede next run brief",
        "brief_before_copy_prompt": "next run brief does not precede copyable prompt",
        "copy_prompt_before_comparison": "copyable prompt does not precede comparison control",
        "comparison_before_metrics": "comparison control does not precede metric grid",
        "copy_prompt_before_metrics": "copyable prompt does not precede metric grid",
        "tabs_in_initial_viewport": "tab navigation is not fully visible in the initial viewport",
    }
    if profile != "real" and layout.get("comparison_present") is not True:
        failures.append(f"{viewport_name}: comparison control is not rendered")
    for key, message in checks.items():
        if layout.get(key) is not True:
            failures.append(f"{viewport_name}: {message}")
    if layout.get("tabs_total") != len(TAB_CHECKS):
        failures.append(
            f"{viewport_name}: tab navigation expected {len(TAB_CHECKS)} tabs, got {layout.get('tabs_total', 'unknown')}"
        )
    if layout.get("tabs_visible_count") != len(TAB_CHECKS):
        failures.append(
            f"{viewport_name}: complete tab navigation is not visible in the initial viewport"
        )
    return failures


def collect_review_paths(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-review-path')).map((card) => ({
  label: (card.querySelector('h3')?.innerText || '').replace(/\s+/g, ' ').trim(),
  body: (card.innerText || '').replace(/\s+/g, ' ').trim(),
})).filter((item) => item.label || item.body)
        """
    )


def review_path_failures(paths: list[dict[str, str]], viewport_name: str) -> list[str]:
    if not paths:
        return [f"{viewport_name}: next review path card not rendered"]
    body = str(paths[0].get("body") or "")
    return [
        f"{viewport_name}: next review path missing {expected}"
        for expected in EXPECTED_REVIEW_PATH
        if expected not in body
    ]


def operator_briefing_failures(
    briefings: list[dict[str, str]],
    viewport_name: str,
    profile: str = PROFILE_DEMO,
) -> list[str]:
    if not briefings:
        return [f"{viewport_name}: operator briefing card not rendered"]
    observed = briefings[0]
    failures = []
    label = str(observed.get("label") or "").casefold()
    expected_label = EXPECTED_OPERATOR_BRIEFING["label"].casefold()
    if label != expected_label:
        failures.append(f"{viewport_name}: operator briefing label missing")
    action = str(observed.get("action") or "")
    if not action.startswith("Primary risk signal: "):
        failures.append(f"{viewport_name}: operator briefing risk signal missing")
    if profile == PROFILE_REAL:
        for key in ["heading", "best_habit", "scale", "proof_target"]:
            if not str(observed.get(key) or ""):
                failures.append(f"{viewport_name}: operator briefing {key} missing")
        return failures
    if EXPECTED_OPERATOR_BRIEFING["risk"] not in str(observed.get("heading") or ""):
        failures.append(
            f"{viewport_name}: operator briefing risk expected {EXPECTED_OPERATOR_BRIEFING['risk']}"
        )
    for key in ["best_habit", "scale", "proof_target"]:
        actual = str(observed.get(key) or "")
        expected = EXPECTED_OPERATOR_BRIEFING[key]
        if actual != expected:
            failures.append(
                f"{viewport_name}: operator briefing {key} expected {expected}, got {actual or 'missing'}"
            )
    return failures


def collect_next_run_checklists(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-next-run-checklist')).map((card) => ({
  label: (card.querySelector('h3')?.innerText || '').replace(/\s+/g, ' ').trim(),
  body: (card.innerText || '').replace(/\s+/g, ' ').trim(),
})).filter((item) => item.label || item.body)
        """
    )


def next_run_checklist_failures(
    checklists: list[dict[str, str]],
    viewport_name: str,
    profile: str = PROFILE_DEMO,
) -> list[str]:
    if not checklists:
        return [f"{viewport_name}: next run checklist card not rendered"]
    body = str(checklists[0].get("body") or "")
    expected_items = (
        ["Next run checklist", "Before next run", "During next run", "After next run"]
        if profile == PROFILE_REAL
        else EXPECTED_NEXT_RUN_CHECKLIST
    )
    return [
        f"{viewport_name}: next run checklist missing: {expected}"
        for expected in expected_items
        if expected not in body
    ]


def collect_next_run_briefs(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-next-run-brief')).map((card) => ({
  label: (card.querySelector('h3')?.innerText || '').replace(/\s+/g, ' ').trim(),
  body: (card.innerText || '').replace(/\s+/g, ' ').trim(),
})).filter((item) => item.label || item.body)
        """
    )


def collect_next_run_copy_controls(page) -> list[dict[str, object]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('[data-testid="stCode"], .stCode')).map((block) => {
  const prompt = (block.innerText || '').replace(/\s+/g, ' ').trim();
  const button = block.querySelector('button');
  return {
    prompt,
    has_copy_button: Boolean(button),
    button_label: (button?.getAttribute('aria-label') || button?.getAttribute('title') || '').trim(),
  };
}).filter((item) => item.prompt.includes('Next Codex run plan:'))
        """
    )


def next_run_copy_control_failures(
    controls: list[dict[str, object]], viewport_name: str
) -> list[str]:
    if not controls:
        return [f"{viewport_name}: native next run copy control not rendered"]
    observed = controls[0]
    failures = []
    if EXPECTED_NEXT_RUN_COPY_PROMPT not in str(observed.get("prompt") or ""):
        failures.append(f"{viewport_name}: next run copy prompt is missing")
    if observed.get("has_copy_button") is not True:
        failures.append(f"{viewport_name}: next run copy button is missing")
    return failures


def next_run_brief_failures(
    briefs: list[dict[str, str]], viewport_name: str, profile: str = PROFILE_DEMO
) -> list[str]:
    if not briefs:
        return [f"{viewport_name}: next run brief card not rendered"]
    body = str(briefs[0].get("body") or "")
    expected_items = (
        ["Next run brief"] if profile == PROFILE_REAL else EXPECTED_NEXT_RUN_BRIEF
    )
    return [
        f"{viewport_name}: next run brief missing: {expected}"
        for expected in expected_items
        if expected not in body
    ]


def guidance_consistency_failures(
    operator_briefings: list[dict[str, str]],
    success_targets: list[dict[str, str]],
    next_run_briefs: list[dict[str, str]],
    viewport_name: str,
) -> list[str]:
    if not operator_briefings or not success_targets or not next_run_briefs:
        return []
    operator = operator_briefings[0]
    target = success_targets[0]
    brief_body = str(next_run_briefs[0].get("body") or "")
    habit = str(operator.get("best_habit") or "")
    proof_target = str(operator.get("proof_target") or "")
    expected_target = (
        f"{target.get('metric')}: {target.get('current')} -> {target.get('target')}"
    )
    failures = []
    if habit and habit not in brief_body:
        failures.append(
            f"{viewport_name}: operator habit does not match next run brief"
        )
    if proof_target and proof_target not in brief_body:
        failures.append(f"{viewport_name}: proof target does not match next run brief")
    if proof_target and proof_target != expected_target:
        failures.append(
            f"{viewport_name}: operator proof target does not match success target card"
        )
    return failures


def collect_feedback_handoffs(page) -> list[dict[str, str]]:
    return page.evaluate(
        r"""
() => Array.from(document.querySelectorAll('.co-feedback-handoff')).map((card) => ({
  label: (card.querySelector('h3')?.innerText || '').replace(/\s+/g, ' ').trim(),
  body: (card.innerText || '').replace(/\s+/g, ' ').trim(),
})).filter((item) => item.label || item.body)
        """
    )


def feedback_handoff_failures(
    handoffs: list[dict[str, str]], viewport_name: str
) -> list[str]:
    if not handoffs:
        return [f"{viewport_name}: safe feedback handoff card not rendered"]
    body = str(handoffs[0].get("body") or "")
    return [
        f"{viewport_name}: safe feedback handoff missing: {expected}"
        for expected in EXPECTED_FEEDBACK_HANDOFF
        if expected not in body
    ]


def collect_layout_snapshot(page) -> dict[str, object]:
    return page.evaluate(
        r"""
() => {
  const viewportWidth = window.innerWidth;
  const documentWidth = Math.max(
    document.documentElement.scrollWidth,
    document.body ? document.body.scrollWidth : 0
  );
  const elements = Array.from(document.querySelectorAll('body *'));
  const visible = elements.filter((el) => {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 1 && rect.height > 1 && style.visibility !== 'hidden' && style.display !== 'none';
  });
  const describe = (el, rect) => ({
    tag: el.tagName.toLowerCase(),
    label: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || el.tagName).replace(/\s+/g, ' ').trim().slice(0, 120),
    x: Math.round(rect.x),
    y: Math.round(rect.y),
    width: Math.round(rect.width),
    height: Math.round(rect.height),
  });
  const overflowingElements = [];
  const clippedTextElements = [];
  for (const el of visible) {
    if (viewportWidth < 700 && el.closest('[data-testid="stSidebar"]')) {
      continue;
    }
    const rect = el.getBoundingClientRect();
    const description = describe(el, rect);
    if (description.label.includes('keyboard_double_arrow_left')) {
      continue;
    }
    if (rect.left < -2 || rect.right > viewportWidth + 2) {
      overflowingElements.push(description);
    }
    const text = (el.innerText || '').trim();
    if (text && (el.scrollWidth > el.clientWidth + 2 || el.scrollHeight > el.clientHeight + 2)) {
      const style = window.getComputedStyle(el);
      if (style.overflow === 'hidden' || style.textOverflow === 'ellipsis' || style.whiteSpace === 'nowrap') {
        clippedTextElements.push(description);
      }
    }
    if (overflowingElements.length >= 8 && clippedTextElements.length >= 8) {
      break;
    }
  }
  return {
    viewport_width: viewportWidth,
    document_width: documentWidth,
    overflowing_elements: overflowingElements.slice(0, 8),
    clipped_text_elements: clippedTextElements.slice(0, 8),
  };
}
        """
    )


def page_body_text(page, timeout_ms: int = 5000) -> str:
    try:
        return page.locator("body").inner_text(timeout=timeout_ms)
    except Exception:
        return page.evaluate("() => document.body ? document.body.innerText : ''")


def validate_dashboard_page(
    page, viewport_name: str, profile: str = PROFILE_DEMO
) -> tuple[list[str], dict[str, object]]:
    failures: list[str] = []
    exercised_tabs: list[str] = []
    quick_read_evidence: list[dict[str, str]] = []
    agent_selector_exercised = False
    text = page_body_text(page, 5000)
    if visible_text_has_error(text):
        failures.append(f"{viewport_name}: Streamlit exception text found")
    if "Codex Observe" not in text:
        failures.append(f"{viewport_name}: dashboard title not found")
    try:
        page.wait_for_function(
            "document.querySelector('.co-briefing') && document.querySelector('.co-metric-grid')",
            timeout=45000 if profile == PROFILE_REAL else 10000,
        )
    except Exception:
        pass
    try:
        page.wait_for_function(
            "document.querySelector('[role=\"tablist\"]') && "
            "document.querySelector('.co-next-run-checklist') && "
            "document.querySelector('.co-next-run-brief') && "
            "document.querySelector('.co-metric-grid') && "
            "Array.from(document.querySelectorAll('[data-testid=\"stCode\"], .stCode')).some((item) => (item.innerText || '').includes('Next Codex run plan:'))",
            timeout=45000 if profile == PROFILE_REAL else 10000,
        )
    except Exception:
        pass
    answer_first_layout = collect_answer_first_layout(page)
    failures.extend(answer_first_layout_failures(answer_first_layout, viewport_name))
    action_first_layout = collect_action_first_layout(page)
    failures.extend(
        action_first_layout_failures(action_first_layout, viewport_name, profile)
    )
    page.get_by_role("tab", name="Overview", exact=True).click()
    page.wait_for_timeout(1500 if profile == PROFILE_REAL else 500)
    if profile == PROFILE_REAL:
        try:
            page.wait_for_function(
                "document.querySelectorAll('.co-success-target').length > 0 && "
                "document.querySelectorAll('.co-next-run-checklist').length > 0 && "
                "document.querySelectorAll('.co-feedback-handoff').length > 0",
                timeout=45000,
            )
        except Exception:
            pass
    wait_script = (
        "['High risk', 'Medium risk', 'Low risk'].some((label) => document.body.innerText.includes(label))"
        if profile == PROFILE_REAL
        else "document.body.innerText.includes('High risk') && document.body.innerText.includes('Low risk')"
    )
    try:
        page.wait_for_function(
            wait_script, timeout=10000 if profile == PROFILE_REAL else 5000
        )
    except Exception:
        pass
    sidebar_risk_labels = collect_sidebar_risk_labels(page)
    failures.extend(
        sidebar_risk_label_failures(sidebar_risk_labels, viewport_name, profile)
    )
    sidebar_risk_filter = collect_sidebar_risk_filter(page)
    failures.extend(sidebar_risk_filter_failures(sidebar_risk_filter, viewport_name))
    sidebar_focus_filter = exercise_sidebar_focus_filter(page, viewport_name, profile)
    failures.extend(
        sidebar_focus_filter_failures(sidebar_focus_filter, viewport_name, profile)
    )
    sidebar_session_search = collect_sidebar_session_search(page)
    failures.extend(
        sidebar_session_search_failures(sidebar_session_search, viewport_name)
    )
    sidebar_session_details = collect_sidebar_session_details(page)
    failures.extend(
        sidebar_session_detail_failures(sidebar_session_details, viewport_name, profile)
    )
    risk_distributions = collect_risk_distributions(page)
    failures.extend(
        risk_distribution_failures(risk_distributions, viewport_name, profile)
    )
    portfolio_briefings = collect_portfolio_briefings(page)
    failures.extend(
        portfolio_briefing_failures(portfolio_briefings, viewport_name, profile)
    )
    metric_cards = collect_metric_cards(page)
    failures.extend(metric_card_failures(metric_cards, viewport_name))
    failures.extend(metric_card_value_failures(metric_cards, viewport_name, profile))
    page.evaluate("window.scrollTo(0, Math.min(document.body.scrollHeight, 900))")
    page.wait_for_timeout(1000 if profile == PROFILE_REAL else 500)
    success_targets = collect_success_targets(page)
    operator_briefings = collect_operator_briefings(page)
    review_paths = collect_review_paths(page)
    next_run_checklists = collect_next_run_checklists(page)
    next_run_briefs = collect_next_run_briefs(page)
    next_run_copy_controls = collect_next_run_copy_controls(page)
    feedback_handoffs = collect_feedback_handoffs(page)
    download_controls = collect_download_controls(page)
    report_scope_warnings = collect_report_scope_warnings(page)
    comparison_selections = collect_comparison_selections(page)
    comparison_directions = collect_comparison_directions(page)
    comparison_previews = collect_comparison_previews(page)
    comparison_review_paths = collect_comparison_review_paths(page)
    comparison_scope_warnings = collect_comparison_scope_warnings(page)
    comparison_deltas = collect_comparison_deltas(page)
    page.evaluate("window.scrollTo(0, 0)")
    failures.extend(success_target_failures(success_targets, viewport_name, profile))
    failures.extend(
        operator_briefing_failures(operator_briefings, viewport_name, profile)
    )
    failures.extend(review_path_failures(review_paths, viewport_name))
    failures.extend(
        next_run_checklist_failures(next_run_checklists, viewport_name, profile)
    )
    failures.extend(next_run_brief_failures(next_run_briefs, viewport_name, profile))
    failures.extend(
        next_run_copy_control_failures(next_run_copy_controls, viewport_name)
    )
    failures.extend(
        guidance_consistency_failures(
            operator_briefings, success_targets, next_run_briefs, viewport_name
        )
    )
    failures.extend(feedback_handoff_failures(feedback_handoffs, viewport_name))
    failures.extend(
        download_control_failures(download_controls, viewport_name, profile)
    )
    failures.extend(
        comparison_selection_failures(comparison_selections, viewport_name, profile)
    )
    failures.extend(
        comparison_direction_failures(comparison_directions, viewport_name, profile)
    )
    failures.extend(
        comparison_preview_failures(comparison_previews, viewport_name, profile)
    )
    failures.extend(
        comparison_review_path_failures(comparison_review_paths, viewport_name, profile)
    )
    failures.extend(
        comparison_delta_failures(comparison_deltas, viewport_name, profile)
    )
    overview_text = page_body_text(page, 10000)
    for metric_label in ["Largest thread", "Uncached input"]:
        if metric_label not in overview_text:
            failures.append(
                f"{viewport_name}: overview metric not found: {metric_label}"
            )

    for tab_name, expected_text in TAB_CHECKS.items():
        tab = page.get_by_role("tab", name=tab_name, exact=True)
        if tab.count() != 1:
            failures.append(f"{viewport_name}: tab not found exactly once: {tab_name}")
            continue
        if profile == PROFILE_REAL:
            page.evaluate(
                """
name => {
  const target = Array.from(document.querySelectorAll('[role="tab"]')).find(
    (item) => (item.innerText || '').trim() === name
  );
  if (target) target.click();
}
                """,
                tab_name,
            )
        else:
            tab.click()
        exercised_tabs.append(tab_name)
        page.wait_for_timeout(1000 if profile == PROFILE_REAL else 500)
        if profile == PROFILE_REAL:
            try:
                page.wait_for_function(
                    "expected => document.body.innerText.includes(expected)",
                    arg=expected_text,
                    timeout=60000,
                )
            except Exception:
                pass
        body = page_body_text(page, 10000 if profile == PROFILE_REAL else 5000)
        if visible_text_has_error(body):
            failures.append(
                f"{viewport_name}: Streamlit exception after opening {tab_name}"
            )
        if expected_text not in body:
            failures.append(
                f"{viewport_name}: expected text not found on {tab_name}: {expected_text}"
            )
        else:
            quick_read_evidence.append({"tab": tab_name, "text": expected_text})

        if tab_name == "Agent detail":
            if "Select a thread" not in body:
                failures.append(
                    f"{viewport_name}: Agent detail selector label not visible"
                )
                continue
            thread_selector = page.get_by_label("Select a thread")
            if thread_selector.count() < 1:
                failures.append(f"{viewport_name}: Agent detail combobox not found")
            else:
                thread_selector.first.click()
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")
                page.wait_for_timeout(1500 if profile == PROFILE_REAL else 500)
                try:
                    selected_body = page_body_text(
                        page, 15000 if profile == PROFILE_REAL else 5000
                    )
                except Exception:
                    failures.append(
                        f"{viewport_name}: Agent detail selector rerender timed out"
                    )
                else:
                    if visible_text_has_error(selected_body):
                        failures.append(
                            f"{viewport_name}: Streamlit exception after using Agent detail selector"
                        )
                    else:
                        agent_selector_exercised = True
                page.keyboard.press("Escape")

    layout_snapshot = collect_layout_snapshot(page)
    failures.extend(layout_review_failures(layout_snapshot, viewport_name))

    evidence = {
        "tabs_exercised": exercised_tabs,
        "quick_read_evidence": quick_read_evidence,
        "agent_detail_selector_exercised": agent_selector_exercised,
        "risk_distributions": risk_distributions,
        "portfolio_briefings": portfolio_briefings,
        "metric_cards": metric_cards,
        "sidebar_risk_labels": sidebar_risk_labels,
        "sidebar_risk_filter": sidebar_risk_filter,
        "sidebar_focus_filter": sidebar_focus_filter,
        "sidebar_session_search": sidebar_session_search,
        "sidebar_session_details": sidebar_session_details,
        "success_targets": success_targets,
        "answer_first_layout": answer_first_layout,
        "action_first_layout": action_first_layout,
        "operator_briefings": operator_briefings,
        "review_paths": review_paths,
        "next_run_checklists": next_run_checklists,
        "next_run_briefs": next_run_briefs,
        "next_run_copy_controls": next_run_copy_controls,
        "feedback_handoffs": feedback_handoffs,
        "download_controls": download_controls,
        "report_scope_warnings": report_scope_warnings,
        "comparison_selections": comparison_selections,
        "comparison_directions": comparison_directions,
        "comparison_previews": comparison_previews,
        "comparison_review_paths": comparison_review_paths,
        "comparison_scope_warnings": comparison_scope_warnings,
        "comparison_deltas": comparison_deltas,
        "layout_review": layout_snapshot,
    }
    return failures, evidence


def screenshot_quality_failures(
    path: Path, viewport: dict[str, int], viewport_name: str
) -> list[str]:
    failures: list[str] = []
    if not path.exists():
        return [f"{viewport_name}: screenshot was not written: {path}"]

    with Image.open(path) as image:
        width, height = image.size
        if width != viewport["width"]:
            failures.append(
                f"{viewport_name}: screenshot width {width} != viewport width {viewport['width']}"
            )
        if height < min(600, viewport["height"]):
            failures.append(
                f"{viewport_name}: screenshot height {height} is unexpectedly small"
            )

        sample = image.convert("RGB").resize((min(width, 160), min(height, 160)))
        colors = sample.getcolors(maxcolors=160 * 160)
        if colors is not None and len(colors) < 12:
            failures.append(
                f"{viewport_name}: screenshot has too little color variation"
            )

        luma_extrema = sample.convert("L").getextrema()
        if luma_extrema[1] - luma_extrema[0] < 25:
            failures.append(f"{viewport_name}: screenshot appears visually blank")

    return failures


def screenshot_metadata(path: Path) -> dict[str, object]:
    with Image.open(path) as image:
        width, height = image.size
    return {
        "filename": path.name,
        "width": width,
        "height": height,
        "bytes": path.stat().st_size,
    }


def evidence_path_label(path: str | Path) -> str:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        relative = candidate.resolve().relative_to(Path.cwd().resolve())
    except (OSError, ValueError):
        return "[redacted-path]"
    return relative.as_posix()


def collect_empty_state(page) -> dict[str, object]:
    return page.evaluate(
        r"""
() => ({
  title: (document.querySelector('.co-empty h2')?.innerText || '').replace(/\s+/g, ' ').trim(),
  body: (document.querySelector('.co-empty p')?.innerText || '').replace(/\s+/g, ' ').trim(),
  commands: Array.from(document.querySelectorAll('.co-empty-action')).map((card) => ({
    label: (card.querySelector('strong')?.innerText || '').replace(/\s+/g, ' ').trim(),
    command: (card.querySelector('code')?.innerText || '').replace(/\s+/g, ' ').trim(),
  })).filter((item) => item.label || item.command),
})
        """
    )


def empty_state_failures(
    state_name: str, evidence: dict[str, object], viewport_name: str
) -> list[str]:
    failures: list[str] = []
    expected_title = EMPTY_STATE_CHECKS[state_name]
    if evidence.get("title") != expected_title:
        failures.append(
            f"{state_name} {viewport_name}: empty-state title expected {expected_title}"
        )
    commands = evidence.get("commands")
    if not isinstance(commands, list):
        return failures + [
            f"{state_name} {viewport_name}: missing empty-state commands"
        ]
    labels = {
        str(command.get("label") or "")
        for command in commands
        if isinstance(command, dict)
    }
    command_text = "\n".join(
        str(command.get("command") or "")
        for command in commands
        if isinstance(command, dict)
    )
    for label in EXPECTED_EMPTY_STATE_COMMAND_LABELS:
        if label not in labels:
            failures.append(
                f"{state_name} {viewport_name}: empty-state command label missing: {label}"
            )
    for snippet in EXPECTED_EMPTY_STATE_COMMAND_SNIPPETS:
        if snippet not in command_text:
            failures.append(
                f"{state_name} {viewport_name}: empty-state command missing: {snippet}"
            )
    return failures


def validate_empty_state_page(
    page, state_name: str, viewport_name: str
) -> tuple[list[str], dict[str, object]]:
    failures: list[str] = []
    text = page_body_text(page, 5000)
    if visible_text_has_error(text):
        failures.append(f"{state_name} {viewport_name}: Streamlit exception text found")
    if "Codex Observe" not in text:
        failures.append(f"{state_name} {viewport_name}: dashboard title not found")
    evidence = collect_empty_state(page)
    failures.extend(empty_state_failures(state_name, evidence, viewport_name))
    layout_snapshot = collect_layout_snapshot(page)
    failures.extend(
        layout_review_failures(layout_snapshot, f"{state_name} {viewport_name}")
    )
    evidence["layout_review"] = layout_snapshot
    return failures, evidence


def create_empty_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_SQL)


def streamlit_command(app: Path, host: str, port: int, db: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.address",
        host,
        "--server.port",
        str(port),
        "--server.headless",
        "true",
        "--",
        "--db",
        str(db),
    ]


def stop_process_tree(process: subprocess.Popen[object], timeout_s: float = 10) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:  # pragma: no cover - cleanup fallback
        process.kill()
        process.wait(timeout=timeout_s)


def run_empty_state_check(
    url: str, output_dir: Path, state_name: str
) -> tuple[int, dict[str, dict[str, object]]]:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        print(PLAYWRIGHT_INSTALL_HINT, file=sys.stderr)
        return 2, {}

    failures: list[str] = []
    viewport_results: dict[str, dict[str, object]] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for name, viewport in VIEWPORTS.items():
                page = browser.new_page(viewport=viewport)
                page.goto(url, wait_until="networkidle")
                expected_title = EMPTY_STATE_CHECKS[state_name]
                try:
                    page.wait_for_function(
                        "expected => (document.querySelector('.co-empty h2')?.innerText || '').includes(expected)",
                        arg=expected_title,
                        timeout=7000,
                    )
                except Exception:
                    page.wait_for_timeout(1000)
                page_failures, evidence = validate_empty_state_page(
                    page, state_name, name
                )
                failures.extend(page_failures)
                screenshot_path = output_dir / f"dashboard-{state_name}-{name}.png"
                page.screenshot(path=screenshot_path, full_page=True)
                failures.extend(
                    screenshot_quality_failures(
                        screenshot_path, viewport, f"{state_name} {name}"
                    )
                )
                viewport_results[name] = {
                    "viewport": viewport,
                    "screenshot": screenshot_metadata(screenshot_path),
                    **evidence,
                }
                page.close()
        finally:
            browser.close()

    if failures:
        print(f"Visual QA {state_name} failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1, viewport_results
    return 0, viewport_results


def visual_empty_state_failures(
    empty_states: object, manifest_dir: Path | None = None
) -> list[str]:
    failures: list[str] = []
    if not isinstance(empty_states, dict):
        return ["manifest missing empty-state evidence"]
    for state_name in EMPTY_STATE_CHECKS:
        state = empty_states.get(state_name)
        if not isinstance(state, dict):
            failures.append(f"manifest missing {state_name} empty-state evidence")
            continue
        viewports = state.get("viewports")
        if not isinstance(viewports, dict):
            failures.append(f"manifest {state_name} missing viewport evidence")
            continue
        for viewport_name, expected_viewport in VIEWPORTS.items():
            raw = viewports.get(viewport_name)
            if not isinstance(raw, dict):
                failures.append(
                    f"manifest {state_name} missing {viewport_name} viewport evidence"
                )
                continue
            if raw.get("viewport") != expected_viewport:
                failures.append(
                    f"manifest {state_name} {viewport_name} viewport size does not match expected"
                )
            failures.extend(
                failure.replace(
                    f"{state_name} {viewport_name}: ",
                    f"manifest {state_name} {viewport_name} ",
                )
                for failure in empty_state_failures(state_name, raw, viewport_name)
            )
            layout = raw.get("layout_review")
            if not isinstance(layout, dict):
                failures.append(
                    f"manifest {state_name} {viewport_name} missing layout review"
                )
            elif layout_review_failures(layout, f"{state_name} {viewport_name}"):
                failures.append(
                    f"manifest {state_name} {viewport_name} layout review contains failures"
                )
            screenshot = raw.get("screenshot")
            if not isinstance(screenshot, dict):
                failures.append(
                    f"manifest {state_name} {viewport_name} missing screenshot metadata"
                )
                continue
            filename = screenshot.get("filename")
            if not isinstance(filename, str) or not filename:
                failures.append(
                    f"manifest {state_name} {viewport_name} screenshot filename missing"
                )
                continue
            if Path(filename).name != filename:
                failures.append(
                    f"manifest {state_name} {viewport_name} screenshot filename must be basename-only"
                )
                continue
            if screenshot.get("width") != expected_viewport["width"]:
                failures.append(
                    f"manifest {state_name} {viewport_name} screenshot width mismatch"
                )
            if int(screenshot.get("height") or 0) < min(
                600, expected_viewport["height"]
            ):
                failures.append(
                    f"manifest {state_name} {viewport_name} screenshot height too small"
                )
            if int(screenshot.get("bytes") or 0) <= 0:
                failures.append(
                    f"manifest {state_name} {viewport_name} screenshot is empty"
                )
            if manifest_dir is not None:
                screenshot_path = manifest_dir / filename
                if not screenshot_path.exists():
                    failures.append(
                        f"manifest {state_name} {viewport_name} screenshot file missing: {filename}"
                    )
    return failures


def build_visual_manifest(
    *,
    url: str,
    profile: str = PROFILE_DEMO,
    db_path: str,
    output_dir: Path,
    viewport_results: dict[str, dict[str, object]],
    empty_state_results: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": VISUAL_MANIFEST_SCHEMA_VERSION,
        "url": url,
        "profile": profile,
        "database": evidence_path_label(db_path),
        "output_dir": evidence_path_label(output_dir),
        "viewports": viewport_results,
        "empty_states": empty_state_results,
        "checks": {
            "tabs_expected": list(TAB_CHECKS.keys()),
            "streamlit_exception_text": "not found",
            "screenshot_quality": "passed",
            "layout_review": "passed",
            "empty_states": "passed",
        },
    }


def write_visual_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def visual_manifest_failures(manifest: dict[str, object]) -> list[str]:
    failures: list[str] = []
    profile = str(manifest.get("profile") or PROFILE_DEMO)
    if profile not in VISUAL_PROFILES:
        failures.append(f"manifest profile is unsupported: {profile}")
        profile = PROFILE_DEMO
    if manifest.get("schema_version") != VISUAL_MANIFEST_SCHEMA_VERSION:
        failures.append("manifest schema_version is missing or unsupported")

    checks = manifest.get("checks")
    if not isinstance(checks, dict):
        failures.append("manifest checks must be an object")
        checks = {}
    if checks.get("tabs_expected") != list(TAB_CHECKS.keys()):
        failures.append("manifest tabs_expected does not match dashboard tabs")
    for key in [
        "streamlit_exception_text",
        "screenshot_quality",
        "layout_review",
        "empty_states",
    ]:
        expected = "not found" if key == "streamlit_exception_text" else "passed"
        if checks.get(key) != expected:
            failures.append(f"manifest check {key} must be {expected}")

    failures.extend(visual_empty_state_failures(manifest.get("empty_states")))

    viewports = manifest.get("viewports")
    if not isinstance(viewports, dict):
        return failures + ["manifest viewports must be an object"]
    for name, expected_viewport in VIEWPORTS.items():
        raw = viewports.get(name)
        if not isinstance(raw, dict):
            failures.append(f"manifest missing {name} viewport evidence")
            continue
        if raw.get("viewport") != expected_viewport:
            failures.append(f"manifest {name} viewport size does not match expected")
        if raw.get("tabs_exercised") != list(TAB_CHECKS.keys()):
            failures.append(f"manifest {name} tabs_exercised incomplete")
        failures.extend(
            failure.replace(f"{name}: ", f"manifest {name} ")
            for failure in quick_read_evidence_failures(
                raw.get("quick_read_evidence"), name
            )
        )
        if raw.get("agent_detail_selector_exercised") is not True:
            failures.append(f"manifest {name} agent detail selector was not exercised")

        screenshot = raw.get("screenshot")
        if not isinstance(screenshot, dict):
            failures.append(f"manifest {name} missing screenshot metadata")
        else:
            if screenshot.get("width") != expected_viewport["width"]:
                failures.append(f"manifest {name} screenshot width mismatch")
            if int(screenshot.get("height") or 0) < min(
                600, expected_viewport["height"]
            ):
                failures.append(f"manifest {name} screenshot height too small")
            if int(screenshot.get("bytes") or 0) <= 0:
                failures.append(f"manifest {name} screenshot is empty")

        sidebar_risk_labels = raw.get("sidebar_risk_labels")
        if not isinstance(sidebar_risk_labels, list):
            failures.append(f"manifest {name} missing sidebar risk label evidence")
        else:
            risk_failures = sidebar_risk_label_failures(
                sidebar_risk_labels, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in risk_failures
            )

        sidebar_risk_filter = raw.get("sidebar_risk_filter")
        if not isinstance(sidebar_risk_filter, list):
            failures.append(f"manifest {name} missing sidebar Risk filter evidence")
        else:
            filter_failures = sidebar_risk_filter_failures(sidebar_risk_filter, name)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in filter_failures
            )
        sidebar_focus_filter = raw.get("sidebar_focus_filter")
        if not isinstance(sidebar_focus_filter, dict):
            failures.append(f"manifest {name} missing sidebar Focus filter evidence")
        else:
            focus_filter_failures = sidebar_focus_filter_failures(
                sidebar_focus_filter, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in focus_filter_failures
            )

        sidebar_session_search = raw.get("sidebar_session_search")
        if not isinstance(sidebar_session_search, list):
            failures.append(f"manifest {name} missing sidebar session search evidence")
        else:
            search_failures = sidebar_session_search_failures(
                sidebar_session_search, name
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in search_failures
            )

        sidebar_session_details = raw.get("sidebar_session_details")
        if not isinstance(sidebar_session_details, list):
            failures.append(f"manifest {name} missing sidebar session detail evidence")
        else:
            detail_failures = sidebar_session_detail_failures(
                sidebar_session_details, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in detail_failures
            )

        risk_distributions = raw.get("risk_distributions")
        if not isinstance(risk_distributions, list):
            failures.append(f"manifest {name} missing risk distribution evidence")
        else:
            distribution_failures = risk_distribution_failures(
                risk_distributions, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in distribution_failures
            )

        portfolio_briefings = raw.get("portfolio_briefings")
        if not isinstance(portfolio_briefings, list):
            failures.append(f"manifest {name} missing portfolio briefing evidence")
        else:
            portfolio_failures = portfolio_briefing_failures(
                portfolio_briefings, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in portfolio_failures
            )

        metric_cards = raw.get("metric_cards")
        if not isinstance(metric_cards, list):
            failures.append(f"manifest {name} missing metric card evidence")
        else:
            metric_failures = metric_card_failures(metric_cards, name)
            metric_failures.extend(
                metric_card_value_failures(metric_cards, name, profile)
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in metric_failures
            )

        success_targets = raw.get("success_targets")
        if not isinstance(success_targets, list):
            failures.append(f"manifest {name} missing success target evidence")
        else:
            target_failures = success_target_failures(success_targets, name, profile)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in target_failures
            )

        download_controls = raw.get("download_controls")
        if not isinstance(download_controls, list):
            failures.append(f"manifest {name} missing report download control evidence")
        else:
            control_failures = download_control_failures(
                download_controls, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in control_failures
            )

        answer_first_layout = raw.get("answer_first_layout")
        if not isinstance(answer_first_layout, dict):
            failures.append(f"manifest {name} missing answer-first layout evidence")
        else:
            ordering_failures = answer_first_layout_failures(answer_first_layout, name)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in ordering_failures
            )

        action_first_layout = raw.get("action_first_layout")
        if not isinstance(action_first_layout, dict):
            failures.append(f"manifest {name} missing action-first layout evidence")
        else:
            action_failures = action_first_layout_failures(
                action_first_layout, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in action_failures
            )

        operator_briefings = raw.get("operator_briefings")
        if not isinstance(operator_briefings, list):
            failures.append(f"manifest {name} missing operator briefing evidence")
        else:
            briefing_failures = operator_briefing_failures(
                operator_briefings, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in briefing_failures
            )

        review_paths = raw.get("review_paths")
        if not isinstance(review_paths, list):
            failures.append(f"manifest {name} missing next review path evidence")
        else:
            path_failures = review_path_failures(review_paths, name)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in path_failures
            )

        next_run_checklists = raw.get("next_run_checklists")
        if not isinstance(next_run_checklists, list):
            failures.append(f"manifest {name} missing next run checklist evidence")
        else:
            checklist_failures = next_run_checklist_failures(
                next_run_checklists, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in checklist_failures
            )

        next_run_briefs = raw.get("next_run_briefs")
        if not isinstance(next_run_briefs, list):
            failures.append(f"manifest {name} missing next run brief evidence")
        else:
            brief_failures = next_run_brief_failures(next_run_briefs, name, profile)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in brief_failures
            )

        next_run_copy_controls = raw.get("next_run_copy_controls")
        if not isinstance(next_run_copy_controls, list):
            failures.append(f"manifest {name} missing next run copy control evidence")
        else:
            copy_failures = next_run_copy_control_failures(next_run_copy_controls, name)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in copy_failures
            )

        if (
            isinstance(operator_briefings, list)
            and isinstance(success_targets, list)
            and isinstance(next_run_briefs, list)
        ):
            consistency_failures = guidance_consistency_failures(
                operator_briefings, success_targets, next_run_briefs, name
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in consistency_failures
            )

        feedback_handoffs = raw.get("feedback_handoffs")
        if not isinstance(feedback_handoffs, list):
            failures.append(f"manifest {name} missing safe feedback handoff evidence")
        else:
            handoff_failures = feedback_handoff_failures(feedback_handoffs, name)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in handoff_failures
            )

        report_scope_warnings = raw.get("report_scope_warnings")
        if not isinstance(report_scope_warnings, list):
            failures.append(f"manifest {name} missing report scope warning evidence")
        comparison_selections = raw.get("comparison_selections")
        if not isinstance(comparison_selections, list):
            failures.append(f"manifest {name} missing comparison selection evidence")
        else:
            selection_failures = comparison_selection_failures(
                comparison_selections, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in selection_failures
            )

        comparison_directions = raw.get("comparison_directions")
        if not isinstance(comparison_directions, list):
            failures.append(f"manifest {name} missing comparison direction evidence")
        else:
            direction_failures = comparison_direction_failures(
                comparison_directions, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in direction_failures
            )

        comparison_previews = raw.get("comparison_previews")
        if not isinstance(comparison_previews, list):
            failures.append(f"manifest {name} missing comparison preview evidence")
        else:
            preview_failures = comparison_preview_failures(
                comparison_previews, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in preview_failures
            )

        comparison_review_paths = raw.get("comparison_review_paths")
        if not isinstance(comparison_review_paths, list):
            failures.append(f"manifest {name} missing comparison review path evidence")
        else:
            comparison_path_failures = comparison_review_path_failures(
                comparison_review_paths, name, profile
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in comparison_path_failures
            )
        comparison_scope_warnings = raw.get("comparison_scope_warnings")
        if not isinstance(comparison_scope_warnings, list):
            failures.append(
                f"manifest {name} missing comparison scope warning evidence"
            )
        comparison_deltas = raw.get("comparison_deltas")
        if not isinstance(comparison_deltas, list):
            failures.append(f"manifest {name} missing comparison delta evidence")
        else:
            delta_failures = comparison_delta_failures(comparison_deltas, name, profile)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in delta_failures
            )

        layout = raw.get("layout_review")
        if not isinstance(layout, dict):
            failures.append(f"manifest {name} missing layout review")
        elif layout_review_failures(layout, name):
            failures.append(f"manifest {name} layout review contains failures")
    return failures


def visual_manifest_file_failures(
    manifest: dict[str, object], manifest_dir: Path
) -> list[str]:
    failures: list[str] = []
    viewports = manifest.get("viewports")
    if not isinstance(viewports, dict):
        return failures
    for name in VIEWPORTS:
        raw = viewports.get(name)
        if not isinstance(raw, dict):
            continue
        screenshot = raw.get("screenshot")
        if not isinstance(screenshot, dict):
            continue
        filename = screenshot.get("filename")
        if not isinstance(filename, str) or not filename:
            failures.append(f"manifest {name} screenshot filename missing")
            continue
        if Path(filename).name != filename:
            failures.append(
                f"manifest {name} screenshot filename must be basename-only"
            )
            continue
        screenshot_path = manifest_dir / filename
        if not screenshot_path.exists():
            failures.append(f"manifest {name} screenshot file missing: {filename}")
            continue
        try:
            actual = screenshot_metadata(screenshot_path)
        except OSError as exc:
            failures.append(f"manifest {name} screenshot file unreadable: {exc}")
            continue
        for key in ["width", "height"]:
            if screenshot.get(key) != actual.get(key):
                failures.append(f"manifest {name} screenshot {key} does not match file")
        if int(screenshot.get("bytes") or 0) <= 0 or int(actual.get("bytes") or 0) <= 0:
            failures.append(f"manifest {name} screenshot is empty")
    failures.extend(
        visual_empty_state_failures(manifest.get("empty_states"), manifest_dir)
    )
    return failures


def verify_visual_manifest(path: Path) -> tuple[int, list[str]]:
    if not path.exists():
        return 2, [f"missing visual QA manifest: {path}"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return 1, [f"visual QA manifest is not valid JSON: {exc}"]
    if not isinstance(manifest, dict):
        return 1, ["visual QA manifest must be a JSON object"]
    failures = visual_manifest_failures(manifest)
    failures.extend(visual_manifest_file_failures(manifest, path.parent))
    return (0 if not failures else 1), failures


def run_visual_check(
    url: str,
    output_dir: Path,
    db_path: str,
    empty_state_results: dict[str, dict[str, object]],
    profile: str = PROFILE_DEMO,
) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        print(
            PLAYWRIGHT_INSTALL_HINT,
            file=sys.stderr,
        )
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    viewport_results: dict[str, dict[str, object]] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for name, viewport in VIEWPORTS.items():
                page = browser.new_page(viewport=viewport)
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(1500)
                page_failures, evidence = validate_dashboard_page(page, name, profile)
                failures.extend(page_failures)
                page.get_by_role("tab", name="Overview", exact=True).click()
                page.wait_for_timeout(500)
                screenshot_path = output_dir / f"dashboard-{name}.png"
                page.screenshot(path=screenshot_path, full_page=True)
                failures.extend(
                    screenshot_quality_failures(screenshot_path, viewport, name)
                )
                viewport_results[name] = {
                    "viewport": viewport,
                    "screenshot": screenshot_metadata(screenshot_path),
                    **evidence,
                }
                page.close()
        finally:
            browser.close()

    if failures:
        print("Visual QA failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    manifest_path = output_dir / "visual-qa-manifest.json"
    manifest = build_visual_manifest(
        url=url,
        profile=profile,
        db_path=db_path,
        output_dir=output_dir,
        viewport_results=viewport_results,
        empty_state_results=empty_state_results,
    )
    manifest_failures = visual_manifest_failures(manifest)
    if manifest_failures:
        print("Visual QA manifest failed:", file=sys.stderr)
        for failure in manifest_failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    write_visual_manifest(manifest_path, manifest)
    print(f"Visual QA passed. Screenshots and manifest written to {output_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a local visual QA pass for the Codex Observe Streamlit dashboard."
    )
    parser.add_argument(
        "--db",
        default=".artifacts/demo/codex_observe_demo.sqlite",
        help="SQLite database to open in the dashboard.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument(
        "--out", default=".artifacts/visual", help="Directory for screenshots."
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for Streamlit startup.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(VISUAL_PROFILES),
        default=PROFILE_DEMO,
        help="Expectation profile: strict demo fixture checks or structure-focused real data checks.",
    )
    parser.add_argument(
        "--verify-manifest",
        default=None,
        help="Validate an existing visual QA manifest without launching the dashboard.",
    )
    args = parser.parse_args()

    if args.verify_manifest:
        status, failures = verify_visual_manifest(Path(args.verify_manifest))
        if failures:
            print("Visual QA manifest verification failed:", file=sys.stderr)
            for failure in failures:
                print(f"- {failure}", file=sys.stderr)
        else:
            print(f"Visual QA manifest verified: {args.verify_manifest}")
        return status

    db = Path(args.db)
    if not db.exists():
        print(
            f"Database not found: {db}. Run `codex-observe demo` first, or pass --db.",
            file=sys.stderr,
        )
        return 2

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        visual_port = resolve_visual_qa_port(args.host, args.port)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if visual_port != args.port:
        print(
            f"Visual QA port block {args.port}-{args.port + 2} is busy; "
            f"using {visual_port}-{visual_port + 2} instead.",
            file=sys.stderr,
        )
    app = Path(__file__).resolve().parents[1] / "codex_observe" / "dashboard.py"
    empty_state_results: dict[str, dict[str, object]] = {}

    state_specs = [
        ("missing_database", output_dir / "missing-dashboard.sqlite", visual_port + 1),
        ("empty_database", output_dir / "empty-dashboard.sqlite", visual_port + 2),
    ]
    for state_name, state_db, state_port in state_specs:
        if state_db.exists():
            with contextlib.suppress(OSError):
                state_db.unlink()
        if state_name == "empty_database":
            create_empty_database(state_db)
        url = f"http://{args.host}:{state_port}"
        process = subprocess.Popen(
            streamlit_command(app, args.host, state_port, state_db),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_for_server(url, args.timeout)
            state_status, viewport_results = run_empty_state_check(
                url, output_dir, state_name
            )
            if state_status != 0:
                return state_status
            empty_state_results[state_name] = {
                "database": evidence_path_label(state_db),
                "viewports": viewport_results,
            }
        finally:
            stop_process_tree(process)

    url = f"http://{args.host}:{visual_port}"
    process = subprocess.Popen(
        streamlit_command(app, args.host, visual_port, db),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server(url, args.timeout)
        return run_visual_check(
            url, output_dir, str(db), empty_state_results, args.profile
        )
    finally:
        stop_process_tree(process)


if __name__ == "__main__":
    raise SystemExit(main())
