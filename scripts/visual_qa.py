from __future__ import annotations

import argparse
import contextlib
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from PIL import Image

from codex_observe.schema import SCHEMA_SQL


VISUAL_MANIFEST_SCHEMA_VERSION = "codex-observe.visual-manifest.v1"

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "narrow": {"width": 390, "height": 900},
}


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

EXPECTED_METRIC_CARDS = ["Threads", "Largest thread", "Uncached input"]
EXPECTED_SIDEBAR_RISK_LABELS = ["High risk", "Low risk"]
EXPECTED_SIDEBAR_SESSION_DETAILS = ["6 snapshots"]
EXPECTED_DOWNLOAD_CONTROLS = [
    "Download report MD",
    "Download report JSON",
    "Download comparison MD",
    "Download comparison JSON",
]
EXPECTED_COMPARISON_PREVIEW = {
    "label": "Comparison quick read",
    "verdict": "regressed",
    "triage_movement": "regressed",
    "next_step": "Inspect new diagnostic first: Repeated prompt blocks.",
    "follow_up": "Next validation command",
    "follow_up_command": "codex-observe report --db <db> --session-id <next-session-id> --format json --out next-run-report.json",
}
EXPECTED_COMPARISON_DELTAS = [
    {"label": "Total tokens", "direction": "regressed"},
    {"label": "Usage snapshots", "direction": "changed"},
    {"label": "Largest thread tokens", "direction": "regressed"},
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
    "Largest thread": "33.2k tokens (57.7%)",
    "Uncached input": "22.7k tokens (39.5%)",
}


EXPECTED_RISK_DISTRIBUTION = [
    "Risk distribution",
    "High risk",
    "Low risk",
    "2 imported conversations",
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
  return ['High risk', 'Low risk'].filter((label) => text.includes(label));
}
        """
    )


def sidebar_risk_label_failures(labels: list[str], viewport_name: str) -> list[str]:
    observed = set(labels)
    return [
        f"{viewport_name}: sidebar risk label not found: {label}"
        for label in EXPECTED_SIDEBAR_RISK_LABELS
        if label not in observed
    ]


def collect_sidebar_session_details(page) -> list[str]:
    return page.evaluate(
        r"""
() => {
  const text = document.body.innerText || '';
  return ['6 snapshots'].filter((label) => text.includes(label));
}
        """
    )


def sidebar_session_detail_failures(
    details: list[str], viewport_name: str
) -> list[str]:
    observed = set(details)
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


def download_control_failures(labels: list[str], viewport_name: str) -> list[str]:
    observed = set(labels)
    return [
        f"{viewport_name}: report download control not found: {label}"
        for label in EXPECTED_DOWNLOAD_CONTROLS
        if label not in observed
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
    previews: list[dict[str, str]], viewport_name: str
) -> list[str]:
    if not previews:
        return [f"{viewport_name}: comparison preview card not rendered"]
    body = str(previews[0].get("body") or "")
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
    paths: list[dict[str, str]], viewport_name: str
) -> list[str]:
    if not paths:
        return [f"{viewport_name}: comparison review path not rendered"]
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
    deltas: list[dict[str, str]], viewport_name: str
) -> list[str]:
    if not deltas:
        return [f"{viewport_name}: comparison delta cards not rendered"]
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
    distributions: list[dict[str, str]], viewport_name: str
) -> list[str]:
    if not distributions:
        return [f"{viewport_name}: risk distribution card not rendered"]
    body = str(distributions[0].get("body") or "")
    return [
        f"{viewport_name}: risk distribution missing: {expected}"
        for expected in EXPECTED_RISK_DISTRIBUTION
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
    cards: list[dict[str, str]], viewport_name: str
) -> list[str]:
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
    targets: list[dict[str, str]], viewport_name: str
) -> list[str]:
    if not targets:
        return [f"{viewport_name}: success target card not rendered"]
    observed = targets[0]
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
    action: (card.querySelector('h3 + p')?.innerText || '').replace(/\s+/g, ' ').trim(),
    best_habit: bestHabit[0] || '',
    scale: bestHabit[1] || '',
    proof_target: proofTarget[0] || '',
  };
}).filter((item) => item.label || item.heading || item.best_habit || item.proof_target)
        """
    )


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
    briefings: list[dict[str, str]], viewport_name: str
) -> list[str]:
    if not briefings:
        return [f"{viewport_name}: operator briefing card not rendered"]
    observed = briefings[0]
    failures = []
    label = str(observed.get("label") or "").casefold()
    expected_label = EXPECTED_OPERATOR_BRIEFING["label"].casefold()
    if label != expected_label:
        failures.append(f"{viewport_name}: operator briefing label missing")
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
    checklists: list[dict[str, str]], viewport_name: str
) -> list[str]:
    if not checklists:
        return [f"{viewport_name}: next run checklist card not rendered"]
    body = str(checklists[0].get("body") or "")
    return [
        f"{viewport_name}: next run checklist missing: {expected}"
        for expected in EXPECTED_NEXT_RUN_CHECKLIST
        if expected not in body
    ]


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


def validate_dashboard_page(
    page, viewport_name: str
) -> tuple[list[str], dict[str, object]]:
    failures: list[str] = []
    exercised_tabs: list[str] = []
    quick_read_evidence: list[dict[str, str]] = []
    agent_selector_exercised = False
    text = page.locator("body").inner_text(timeout=5000)
    if visible_text_has_error(text):
        failures.append(f"{viewport_name}: Streamlit exception text found")
    if "Codex Observe" not in text:
        failures.append(f"{viewport_name}: dashboard title not found")
    try:
        page.wait_for_function(
            "document.body.innerText.includes('High risk') && document.body.innerText.includes('Low risk')",
            timeout=5000,
        )
    except Exception:
        pass
    sidebar_risk_labels = collect_sidebar_risk_labels(page)
    failures.extend(sidebar_risk_label_failures(sidebar_risk_labels, viewport_name))
    sidebar_session_details = collect_sidebar_session_details(page)
    failures.extend(
        sidebar_session_detail_failures(sidebar_session_details, viewport_name)
    )
    risk_distributions = collect_risk_distributions(page)
    failures.extend(risk_distribution_failures(risk_distributions, viewport_name))
    metric_cards = collect_metric_cards(page)
    failures.extend(metric_card_failures(metric_cards, viewport_name))
    failures.extend(metric_card_value_failures(metric_cards, viewport_name))
    page.get_by_role("tab", name="Overview", exact=True).click()
    page.wait_for_timeout(500)
    page.evaluate("window.scrollTo(0, Math.min(document.body.scrollHeight, 900))")
    page.wait_for_timeout(500)
    success_targets = collect_success_targets(page)
    operator_briefings = collect_operator_briefings(page)
    review_paths = collect_review_paths(page)
    next_run_checklists = collect_next_run_checklists(page)
    feedback_handoffs = collect_feedback_handoffs(page)
    download_controls = collect_download_controls(page)
    comparison_previews = collect_comparison_previews(page)
    comparison_review_paths = collect_comparison_review_paths(page)
    comparison_scope_warnings = collect_comparison_scope_warnings(page)
    comparison_deltas = collect_comparison_deltas(page)
    page.evaluate("window.scrollTo(0, 0)")
    failures.extend(success_target_failures(success_targets, viewport_name))
    failures.extend(operator_briefing_failures(operator_briefings, viewport_name))
    failures.extend(review_path_failures(review_paths, viewport_name))
    failures.extend(next_run_checklist_failures(next_run_checklists, viewport_name))
    failures.extend(feedback_handoff_failures(feedback_handoffs, viewport_name))
    failures.extend(download_control_failures(download_controls, viewport_name))
    failures.extend(comparison_preview_failures(comparison_previews, viewport_name))
    failures.extend(
        comparison_review_path_failures(comparison_review_paths, viewport_name)
    )
    failures.extend(comparison_delta_failures(comparison_deltas, viewport_name))
    for metric_label in ["Largest thread", "Uncached input"]:
        if metric_label not in text:
            failures.append(
                f"{viewport_name}: overview metric not found: {metric_label}"
            )

    for tab_name, expected_text in TAB_CHECKS.items():
        tab = page.get_by_role("tab", name=tab_name, exact=True)
        if tab.count() != 1:
            failures.append(f"{viewport_name}: tab not found exactly once: {tab_name}")
            continue
        tab.click()
        exercised_tabs.append(tab_name)
        page.wait_for_timeout(500)
        body = page.locator("body").inner_text(timeout=5000)
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
            comboboxes = page.get_by_role("combobox")
            if comboboxes.count() < 1:
                failures.append(f"{viewport_name}: Agent detail combobox not found")
            else:
                comboboxes.first.click()
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")
                page.wait_for_timeout(500)
                selected_body = page.locator("body").inner_text(timeout=5000)
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
        "metric_cards": metric_cards,
        "sidebar_risk_labels": sidebar_risk_labels,
        "sidebar_session_details": sidebar_session_details,
        "success_targets": success_targets,
        "operator_briefings": operator_briefings,
        "review_paths": review_paths,
        "next_run_checklists": next_run_checklists,
        "feedback_handoffs": feedback_handoffs,
        "download_controls": download_controls,
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
    text = page.locator("body").inner_text(timeout=5000)
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
    db_path: str,
    output_dir: Path,
    viewport_results: dict[str, dict[str, object]],
    empty_state_results: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": VISUAL_MANIFEST_SCHEMA_VERSION,
        "url": url,
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
            risk_failures = sidebar_risk_label_failures(sidebar_risk_labels, name)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in risk_failures
            )

        sidebar_session_details = raw.get("sidebar_session_details")
        if not isinstance(sidebar_session_details, list):
            failures.append(f"manifest {name} missing sidebar session detail evidence")
        else:
            detail_failures = sidebar_session_detail_failures(
                sidebar_session_details, name
            )
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in detail_failures
            )

        risk_distributions = raw.get("risk_distributions")
        if not isinstance(risk_distributions, list):
            failures.append(f"manifest {name} missing risk distribution evidence")
        else:
            distribution_failures = risk_distribution_failures(risk_distributions, name)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in distribution_failures
            )

        metric_cards = raw.get("metric_cards")
        if not isinstance(metric_cards, list):
            failures.append(f"manifest {name} missing metric card evidence")
        else:
            metric_failures = metric_card_failures(metric_cards, name)
            metric_failures.extend(metric_card_value_failures(metric_cards, name))
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in metric_failures
            )

        success_targets = raw.get("success_targets")
        if not isinstance(success_targets, list):
            failures.append(f"manifest {name} missing success target evidence")
        else:
            target_failures = success_target_failures(success_targets, name)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in target_failures
            )

        download_controls = raw.get("download_controls")
        if not isinstance(download_controls, list):
            failures.append(f"manifest {name} missing report download control evidence")
        else:
            control_failures = download_control_failures(download_controls, name)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in control_failures
            )

        operator_briefings = raw.get("operator_briefings")
        if not isinstance(operator_briefings, list):
            failures.append(f"manifest {name} missing operator briefing evidence")
        else:
            briefing_failures = operator_briefing_failures(operator_briefings, name)
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
            checklist_failures = next_run_checklist_failures(next_run_checklists, name)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in checklist_failures
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

        comparison_previews = raw.get("comparison_previews")
        if not isinstance(comparison_previews, list):
            failures.append(f"manifest {name} missing comparison preview evidence")
        else:
            preview_failures = comparison_preview_failures(comparison_previews, name)
            failures.extend(
                failure.replace(f"{name}: ", f"manifest {name} ")
                for failure in preview_failures
            )

        comparison_review_paths = raw.get("comparison_review_paths")
        if not isinstance(comparison_review_paths, list):
            failures.append(f"manifest {name} missing comparison review path evidence")
        else:
            comparison_path_failures = comparison_review_path_failures(
                comparison_review_paths, name
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
            delta_failures = comparison_delta_failures(comparison_deltas, name)
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
                page_failures, evidence = validate_dashboard_page(page, name)
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
    app = Path(__file__).resolve().parents[1] / "codex_observe" / "dashboard.py"
    empty_state_results: dict[str, dict[str, object]] = {}

    state_specs = [
        ("missing_database", output_dir / "missing-dashboard.sqlite", args.port + 1),
        ("empty_database", output_dir / "empty-dashboard.sqlite", args.port + 2),
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
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - cleanup fallback
                process.kill()
                process.wait(timeout=10)

    url = f"http://{args.host}:{args.port}"
    process = subprocess.Popen(
        streamlit_command(app, args.host, args.port, db),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server(url, args.timeout)
        return run_visual_check(url, output_dir, str(db), empty_state_results)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - cleanup fallback
            process.kill()
            process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
